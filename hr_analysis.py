"""
HR Analysis for realtest/flash.dat
- Extracts IBF via unpackdc (on a temp copy)
- Detects R-peaks, computes instantaneous HR
- Plots HR over clock time
- Compares with BioTrace+ reference window (09:50:10 - 10:02:09, mean 82.76 bpm)
"""
import sys, os, struct, shutil, tempfile, subprocess, numpy as np
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# ── Config ─────────────────────────────────────────────────────────────────────
DAT      = r"C:\Users\TSIC\Documents\GitHub\Heart\realtest\flash.dat"
UNPACKDC = r"C:\nm\bin\unpackdc.exe"
OUT_DIR  = r"C:\Users\TSIC\Documents\GitHub\Heart\output\realtest"
FS       = 180.0      # sample rate
BLOCK    = 512
# Recording start (from config block)
REC_START = datetime(2026, 3, 16, 9, 40, 30)
# BioTrace+ reference window
BT_START  = datetime(2026, 3, 16, 9, 50, 10)
BT_END    = datetime(2026, 3, 16, 10,  2,  9)
BT_MEAN_HR = 82.76

os.makedirs(OUT_DIR, exist_ok=True)

# ── Step 1: find valid block count via counter check ───────────────────────────
print("Scanning flash.dat for valid blocks...")
MAGIC = bytes([0x00, 0x02, 0x00, 0x00, 0x1E, 0x00])
last_active = 2
prev_counter = None

with open(DAT, 'rb') as f:
    bi = 3
    while True:
        f.seek(bi * BLOCK)
        blk = f.read(BLOCK)
        if len(blk) < BLOCK:
            break
        if blk[:6] != MAGIC:
            break
        counter = struct.unpack_from('<I', blk, 6)[0]
        if prev_counter is None:
            prev_counter = counter
        else:
            if counter != prev_counter + 1216:
                break
            prev_counter = counter
        last_active = bi
        bi += 1

num_blocks = last_active - 3 + 1
valid_bytes = (last_active + 1) * BLOCK
print(f"Valid blocks: {num_blocks} (block 3..{last_active}), ~{num_blocks*306/FS:.1f}s = {num_blocks*306/FS/60:.1f} min")

# ── Step 2: copy truncated file and run unpackdc ───────────────────────────────
ch0 = os.path.join(OUT_DIR, "realtest_ch0.ibf")
ch1 = os.path.join(OUT_DIR, "realtest_ch1.ibf")
ch2 = os.path.join(OUT_DIR, "realtest_ch2.ibf")
for p in [ch0, ch1, ch2]:
    if os.path.exists(p): os.unlink(p)

tmp = tempfile.NamedTemporaryFile(suffix='.dat', delete=False)
tmp_path = tmp.name
tmp.close()

print(f"Copying {valid_bytes:,} bytes to temp...")
with open(DAT, 'rb') as src, open(tmp_path, 'wb') as dst:
    remaining = valid_bytes
    while remaining > 0:
        chunk = src.read(min(1024*1024, remaining))
        if not chunk: break
        dst.write(chunk)
        remaining -= len(chunk)

print("Running unpackdc...")
r = subprocess.run([UNPACKDC, tmp_path, ch0, ch1, ch2, "0"],
                   capture_output=True, timeout=120)
os.unlink(tmp_path)
print(f"unpackdc exit: {r.returncode}")
if r.returncode != 0:
    print("STDERR:", r.stderr[:300])
    sys.exit(1)

# ── Step 3: load IBF ───────────────────────────────────────────────────────────
raw = np.fromfile(ch0, dtype='<i2').astype(np.float32)
print(f"IBF samples: {len(raw)}, duration: {len(raw)/FS:.1f}s = {len(raw)/FS/60:.1f} min")

# Replace lead-off sentinel
lead_off = (raw == -32768)
raw[lead_off] = np.nan

# ── Step 4: HP filter (remove DC, 1-second window) ────────────────────────────
from scipy.ndimage import uniform_filter1d
filled = np.where(np.isnan(raw), 0.0, raw)
dc = uniform_filter1d(filled, size=int(FS))
hp = raw - dc
print(f"HP filter done. Valid range: {np.nanmin(hp):.0f} ~ {np.nanmax(hp):.0f}")

# ── Step 5: R-peak detection ───────────────────────────────────────────────────
# Use 10-second sliding window for adaptive threshold
WIN_SEC  = 10
REFRACT  = int(0.25 * FS)  # 250 ms refractory period

hp_clean = np.where(np.isnan(hp), 0.0, hp)
win = int(WIN_SEC * FS)
peaks = []

for i in range(1, len(hp_clean) - 1):
    # Skip lead-off
    if lead_off[max(0,i-5):i+6].any():
        continue
    # Local maximum
    if hp_clean[i] <= hp_clean[i-1] or hp_clean[i] <= hp_clean[i+1]:
        continue
    # Adaptive threshold: 60% of local window max
    lo = max(0, i - win//2)
    hi = min(len(hp_clean), i + win//2)
    thresh = 0.60 * np.max(np.abs(hp_clean[lo:hi]))
    if abs(hp_clean[i]) < thresh:
        continue
    # Refractory
    if peaks and (i - peaks[-1]) < REFRACT:
        # Keep the larger peak
        if abs(hp_clean[i]) > abs(hp_clean[peaks[-1]]):
            peaks[-1] = i
        continue
    peaks.append(i)

peaks = np.array(peaks)
print(f"Detected {len(peaks)} R-peaks")

# ── Step 6: instantaneous HR ──────────────────────────────────────────────────
if len(peaks) < 2:
    print("Not enough peaks detected!")
    sys.exit(1)

rr_samples = np.diff(peaks)
rr_sec     = rr_samples / FS
hr_bpm     = 60.0 / rr_sec

# Time axis (clock time)
peak_times = REC_START + np.array([timedelta(seconds=p/FS) for p in peaks[1:]])

# ── Step 7: filter physiological HR range (30-220 bpm) ───────────────────────
valid = (hr_bpm >= 30) & (hr_bpm <= 220)
peak_times_v = peak_times[valid]
hr_v         = hr_bpm[valid]

print(f"Valid HR estimates: {valid.sum()}")
print(f"Mean HR (full recording): {hr_v.mean():.1f} bpm")

# Mean HR in BioTrace+ window
bt_mask = np.array([(BT_START <= t <= BT_END) for t in peak_times_v])
if bt_mask.sum() > 5:
    bt_mean = hr_v[bt_mask].mean()
    print(f"Mean HR in BioTrace+ window ({BT_START.strftime('%H:%M:%S')}-{BT_END.strftime('%H:%M:%S')}): {bt_mean:.1f} bpm")
    print(f"BioTrace+ reference: {BT_MEAN_HR:.2f} bpm | Difference: {bt_mean - BT_MEAN_HR:+.1f} bpm")

# ── Step 8: plot ──────────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 1, figsize=(18, 12))
fig.suptitle(f'realtest/flash.dat — Patient 100 — {REC_START.strftime("%Y-%m-%d %H:%M:%S")}', fontsize=13)

# Time array for signal
t_clock = [REC_START + timedelta(seconds=i/FS) for i in range(len(hp))]
t_clock = np.array(t_clock)

# Panel 1: full ECG (HP filtered, decimated for speed)
dec = 4
ax = axes[0]
ax.plot(t_clock[::dec], hp_clean[::dec], 'g-', linewidth=0.2, alpha=0.8)
ax.axvspan(BT_START, BT_END, alpha=0.15, color='blue', label='BioTrace+ window')
ax.set_title('ECG (HP filtered, full recording)')
ax.set_ylabel('Amplitude')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 2: HR over time
ax = axes[1]
ax.plot(peak_times_v, hr_v, 'b-o', linewidth=1, markersize=2, label='Instantaneous HR')
ax.axvspan(BT_START, BT_END, alpha=0.15, color='blue')
ax.axhline(BT_MEAN_HR, color='red', linestyle='--', linewidth=1.5,
           label=f'BioTrace+ mean {BT_MEAN_HR:.1f} bpm')
if bt_mask.sum() > 5:
    ax.axhline(bt_mean, color='orange', linestyle='--', linewidth=1.5,
               label=f'ECG mean in window {bt_mean:.1f} bpm')
ax.set_title('Heart Rate over Time')
ax.set_ylabel('HR (bpm)')
ax.set_ylim(40, 160)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 3: zoom into BioTrace+ window
ax = axes[2]
t0 = BT_START - timedelta(minutes=1)
t1 = BT_END   + timedelta(minutes=1)
mask_zoom = (t_clock >= t0) & (t_clock <= t1)
ax.plot(t_clock[mask_zoom][::dec], hp_clean[mask_zoom][::dec], 'g-', linewidth=0.3)
pk_zoom = (peak_times_v >= t0) & (peak_times_v <= t1)
ax.scatter(peak_times_v[pk_zoom], [np.nanmax(hp_clean)*0.7]*pk_zoom.sum(),
           marker='v', color='red', s=15, label='R-peaks', zorder=5)
ax.axvspan(BT_START, BT_END, alpha=0.15, color='blue', label='BioTrace+ window')
ax.set_title(f'ECG zoom: BioTrace+ window ({BT_START.strftime("%H:%M:%S")} - {BT_END.strftime("%H:%M:%S")})')
ax.set_ylabel('Amplitude')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
ax.xaxis.set_major_locator(mdates.MinuteLocator())
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

plt.tight_layout()
out_png = os.path.join(OUT_DIR, 'hr_analysis.png')
plt.savefig(out_png, dpi=120)
print(f"\nSaved: {out_png}")
