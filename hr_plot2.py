"""
Better HR plot: clip Y-axis to show ECG properly, exclude artifact spike
"""
import sys, numpy as np
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from scipy.ndimage import uniform_filter1d

IBF      = r"C:\Users\TSIC\Documents\GitHub\Heart\output\realtest\realtest_ch0.ibf"
OUT      = r"C:\Users\TSIC\Documents\GitHub\Heart\output\realtest\hr_analysis2.png"
FS       = 180.0
REC_START = datetime(2026, 3, 16, 9, 40, 30)
BT_START  = datetime(2026, 3, 16, 9, 50, 10)
BT_END    = datetime(2026, 3, 16, 10,  2,  9)
BT_MEAN_HR = 82.76

# Load IBF
raw = np.fromfile(IBF, dtype='<i2').astype(np.float32)
lead_off = (raw == -32768)
raw[lead_off] = np.nan

# HP filter
filled = np.where(np.isnan(raw), 0.0, raw)
dc     = uniform_filter1d(filled, size=int(FS))
hp     = raw - dc
hp_clean = np.where(np.isnan(hp), 0.0, hp)

# R-peak detection
REFRACT = int(0.25 * FS)
WIN     = int(10 * FS)
peaks   = []
for i in range(1, len(hp_clean) - 1):
    if lead_off[max(0,i-5):i+6].any(): continue
    if hp_clean[i] <= hp_clean[i-1] or hp_clean[i] <= hp_clean[i+1]: continue
    lo = max(0, i - WIN//2); hi = min(len(hp_clean), i + WIN//2)
    thresh = 0.60 * np.max(np.abs(hp_clean[lo:hi]))
    if abs(hp_clean[i]) < thresh: continue
    if peaks and (i - peaks[-1]) < REFRACT:
        if abs(hp_clean[i]) > abs(hp_clean[peaks[-1]]): peaks[-1] = i
        continue
    peaks.append(i)
peaks = np.array(peaks)

rr_sec    = np.diff(peaks) / FS
hr_bpm    = 60.0 / rr_sec
peak_times = REC_START + np.array([timedelta(seconds=p/FS) for p in peaks[1:]])
valid     = (hr_bpm >= 40) & (hr_bpm <= 180)
pt_v      = peak_times[valid]
hr_v      = hr_bpm[valid]

# BioTrace window stats
bt_mask   = np.array([(BT_START <= t <= BT_END) for t in pt_v])
bt_mean   = hr_v[bt_mask].mean() if bt_mask.sum() > 5 else None

# Clock time array
t_clock = np.array([REC_START + timedelta(seconds=i/FS) for i in range(len(hp_clean))])

# ── Plot ───────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 1, figsize=(18, 12))
fig.suptitle(f'Patient 100 | 2026-03-16 | DR200/HE vs BioTrace+ Validation', fontsize=13, fontweight='bold')

# Colour palette
ECG_COLOR = '#00C040'
HR_COLOR  = '#2060FF'

# --- Panel 1: Full recording ECG (Y clipped to ±3000 to exclude artifact) ---
ax = axes[0]
DEC = 4
y_clip = 3000
hp_disp = np.clip(hp_clean, -y_clip, y_clip)
ax.plot(t_clock[::DEC], hp_disp[::DEC], color=ECG_COLOR, linewidth=0.2)
ax.axvspan(BT_START, BT_END, alpha=0.12, color='royalblue', label='BioTrace+ window')
ax.set_ylim(-y_clip, y_clip)
ax.set_title('Full ECG (HP filtered, Y clipped ±3000 to show waveform)')
ax.set_ylabel('Amplitude (µV)')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0,60,2)))
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

# --- Panel 2: HR over clock time ---
ax = axes[1]
ax.plot(pt_v, hr_v, color=HR_COLOR, linewidth=1.0, marker='o', markersize=2, label='Instantaneous HR')
ax.axvspan(BT_START, BT_END, alpha=0.12, color='royalblue')
ax.axhline(BT_MEAN_HR, color='red', linestyle='--', linewidth=1.5, label=f'BioTrace+ ref {BT_MEAN_HR:.1f} bpm')
if bt_mean is not None:
    ax.axhline(bt_mean, color='orange', linestyle='--', linewidth=1.5, label=f'ECG window mean {bt_mean:.1f} bpm')
ax.set_ylim(40, 160)
ax.set_title(f'Heart Rate over Time  |  BioTrace+ ref: {BT_MEAN_HR:.1f} bpm  |  ECG window mean: {bt_mean:.1f} bpm  |  Δ = {bt_mean-BT_MEAN_HR:+.1f} bpm')
ax.set_ylabel('HR (bpm)')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0,60,2)))
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

# --- Panel 3: Zoom into BioTrace+ window, 30s strip ---
ax = axes[2]
STRIP_START = BT_START + timedelta(minutes=3)   # pick a quiet segment
STRIP_END   = STRIP_START + timedelta(seconds=30)
s0 = int((STRIP_START - REC_START).total_seconds() * FS)
s1 = int((STRIP_END   - REC_START).total_seconds() * FS)
t_strip  = t_clock[s0:s1]
ecg_strip = np.clip(hp_clean[s0:s1], -3000, 3000)
ax.plot(t_strip, ecg_strip, color=ECG_COLOR, linewidth=0.6)

# Mark R-peaks in this strip
pk_strip = [p for p in peaks if s0 <= p < s1]
if pk_strip:
    pk_t = [REC_START + timedelta(seconds=p/FS) for p in pk_strip]
    pk_v = [np.clip(hp_clean[p], -3000, 3000) + 200 for p in pk_strip]
    ax.scatter(pk_t, pk_v, marker='v', color='red', s=40, zorder=5, label='R-peaks')
    rr  = np.diff(pk_strip) / FS
    avg = 60 / rr.mean() if len(rr) > 0 else 0
    ax.set_title(f'30-second ECG strip ({STRIP_START.strftime("%H:%M:%S")})  |  HR in strip: {avg:.1f} bpm')
else:
    ax.set_title(f'30-second ECG strip ({STRIP_START.strftime("%H:%M:%S")})')

ax.set_ylabel('Amplitude (µV)')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
ax.xaxis.set_major_locator(mdates.SecondLocator(bysecond=range(0,60,5)))
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUT, dpi=130)
print(f"Saved: {OUT}")
print(f"\nValidation summary:")
print(f"  BioTrace+ mean HR : {BT_MEAN_HR:.2f} bpm")
print(f"  ECG derived HR    : {bt_mean:.2f} bpm")
print(f"  Difference        : {bt_mean - BT_MEAN_HR:+.2f} bpm ({abs(bt_mean-BT_MEAN_HR)/BT_MEAN_HR*100:.2f}%)")
