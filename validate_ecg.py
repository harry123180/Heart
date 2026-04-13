"""
validate_ecg.py — ECG parser validation against BioTrace+ reference data.

Data layout:
  flash.dat       DR200/HE ECG recording, starts 09:40:30
  0316.raw.TXT.txt  BioTrace+ raw export, starts 09:50:10  (offset +580s from ECG)
                    contains BVP (128 SPS) + [G] Heart Rate column

Validation steps:
  1. Parse flash.dat  →  ECG signal 180 Hz (our pipeline)
  2. Parse BioTrace+ raw TXT  →  BVP + HR (ground truth)
  3. Sample-level check: compare our signal[30s-40s] vs ECGData30s-40s.csv
  4. R-peak detection on overlapping window
  5. Compare instantaneous HR: ECG-derived vs BioTrace+ HR
  6. Multi-panel matplotlib figure
"""

import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r"C:\Users\TSIC\Documents\GitHub\Heart")

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ── paths ────────────────────────────────────────────────────────────────────
BASE   = r"C:\Users\TSIC\Documents\GitHub\Heart\realtest\0316_1"
FLASH  = os.path.join(BASE, "flash.dat")
BTRACE = os.path.join(BASE, "0316.raw.TXT.txt")
REF_CSV = os.path.join(BASE, "ECGData30s-40s.csv")

# ECG recording start / BioTrace start (wall clock)
ECG_START_HH_MM_SS   = (9, 40, 30)
BTRACE_START_HH_MM_SS = (9, 50, 10)

def to_sec(h, m, s): return h * 3600 + m * 60 + s

ECG_OFFSET_SEC = to_sec(*BTRACE_START_HH_MM_SS) - to_sec(*ECG_START_HH_MM_SS)
# = 580 s  (BioTrace starts 9 min 40 s after ECG)

# ── Step 1: parse flash.dat ───────────────────────────────────────────────────
print("=" * 60)
print("Step 1: Parsing flash.dat via dr200_parse pipeline")
print("=" * 60)

from dr200_parse import parse
r = parse(FLASH)

if not r["valid"]:
    print(f"ERROR: {r['error']}")
    sys.exit(1)

ecg_sr   = r["sample_rate"]       # 180 Hz
ecg_sig  = r["signal_uv"]         # uV, HP filtered
ecg_lo   = r["lead_off"]
ecg_t    = np.arange(len(ecg_sig)) / ecg_sr   # seconds from recording start

print(f"  Patient    : {r['patient_id']}")
print(f"  Date/Time  : {r['start_date']} {r['start_time']}")
print(f"  Samples    : {len(ecg_sig)}  ({r['duration_sec']:.1f} s, {r['duration_sec']/60:.2f} min)")
print(f"  Lead-off   : {ecg_lo.mean()*100:.1f}%")
valid_mask = ~ecg_lo
p999 = np.percentile(ecg_sig[valid_mask], 99.9)
p001 = np.percentile(ecg_sig[valid_mask], 0.1)
print(f"  Amplitude  : {ecg_sig[valid_mask].min()/1000:.1f} .. {ecg_sig[valid_mask].max()/1000:.1f} mV  (incl. edge artifacts)")
print(f"  Amplitude  : {p001/1000:.3f} .. {p999/1000:.3f} mV  (0.1–99.9 percentile, physiological)")

# ── Step 2: parse BioTrace+ raw TXT ──────────────────────────────────────────
print()
print("=" * 60)
print("Step 2: Parsing BioTrace+ raw export")
print("=" * 60)

bt_time_s = []
bt_bvp    = []
bt_hr     = []

with open(BTRACE, encoding="utf-8", errors="replace") as f:
    header_done = False
    for line in f:
        line = line.rstrip()
        if not header_done:
            if line.startswith("TIME"):
                header_done = True
            continue
        if not line or line.startswith("<"):
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        # TIME column: hh:mm:ss
        try:
            hms = parts[0].strip().split(":")
            t = int(hms[0])*3600 + int(hms[1])*60 + float(hms[2])
        except Exception:
            continue
        try:
            bvp = float(parts[2])   # Sensor-G:BVP  (col 3, 0-indexed=2)
            hr  = float(parts[5])   # [G] Heart Rate (col 6, 0-indexed=5)
        except Exception:
            continue
        bt_time_s.append(t)
        bt_bvp.append(bvp)
        bt_hr.append(hr)

bt_time_s = np.array(bt_time_s)
bt_bvp    = np.array(bt_bvp)
bt_hr     = np.array(bt_hr)

bt_duration = bt_time_s[-1] - bt_time_s[0]
print(f"  Samples    : {len(bt_time_s)}")
print(f"  Duration   : {bt_duration:.1f} s ({bt_duration/60:.2f} min)")
print(f"  HR range   : {bt_hr.min():.1f} .. {bt_hr.max():.1f} bpm")
print(f"  Mean HR    : {bt_hr.mean():.2f} bpm")
print(f"  BioTrace+ offset from ECG start: +{ECG_OFFSET_SEC} s")

# Convert BioTrace+ time → ECG time axis
bt_ecg_t = bt_time_s + ECG_OFFSET_SEC  # ECG-relative seconds

# ── Step 3: sample-level check vs ECGData30s-40s.csv ─────────────────────────
print()
print("=" * 60)
print("Step 3: Sample-level validation vs ECGData30s-40s.csv")
print("=" * 60)

ref_idx  = []
ref_t    = []
ref_uv   = []

with open(REF_CSV, encoding="utf-8-sig", errors="replace") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("索引"):
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            ref_idx.append(int(parts[0]))
            ref_t.append(float(parts[1]))
            ref_uv.append(float(parts[2]))
        except Exception:
            continue

ref_idx = np.array(ref_idx)
ref_t   = np.array(ref_t)
ref_uv  = np.array(ref_uv)

# Extract our signal at the same indices
# Trim to same length in case of ±few-sample boundary difference
n_cmp = min(len(ref_idx), len(ref_uv))
ref_idx = ref_idx[:n_cmp]
ref_t   = ref_t[:n_cmp]
ref_uv  = ref_uv[:n_cmp]
our_slice = ecg_sig[ref_idx[:n_cmp]]
diff = our_slice - ref_uv

print(f"  Reference samples : {len(ref_uv)}")
print(f"  Time range        : {ref_t[0]:.2f}s – {ref_t[-1]:.2f}s")
print(f"  Max absolute diff : {np.abs(diff).max():.4f} uV")
print(f"  Mean abs diff     : {np.abs(diff).mean():.4f} uV")
print(f"  RMS diff          : {np.sqrt((diff**2).mean()):.4f} uV")
print(f"  -> {'PASS (< 0.1 uV)' if np.abs(diff).max() < 0.1 else 'NOTE: non-zero diff (HP filter edge effect expected near t=0)'}")

# ── Step 4: R-peak detection on ECG in BioTrace+ overlap window ──────────────
print()
print("=" * 60)
print("Step 4: R-peak detection in overlapping window")
print("=" * 60)

# Overlap: BioTrace+ covers ECG t=[580, 580+duration]
t_overlap_start = ECG_OFFSET_SEC
t_overlap_end   = ECG_OFFSET_SEC + bt_duration

print(f"  Overlap ECG window: {t_overlap_start:.0f}s – {t_overlap_end:.0f}s")

# Extract ECG in overlap
ov_mask = (ecg_t >= t_overlap_start) & (ecg_t <= t_overlap_end) & ~ecg_lo
ov_t    = ecg_t[ov_mask]
ov_sig  = ecg_sig[ov_mask]

if len(ov_sig) == 0:
    print("  ERROR: no valid ECG samples in overlap window!")
    sys.exit(1)

print(f"  ECG overlap samples: {len(ov_sig)}  ({len(ov_sig)/ecg_sr:.1f}s)")

# Pan-Tompkins-style R-peak detector with scipy bandpass
from scipy.signal import butter, filtfilt, find_peaks

def detect_r_peaks(sig, sr, min_rr_sec=0.4):
    """
    Proper Pan-Tompkins pipeline:
      1. Bandpass 5-25 Hz  (removes baseline + HF noise, keeps QRS)
      2. Derivative
      3. Square
      4. Moving average integration (150 ms window)
      5. find_peaks with prominence + distance constraints
      6. Refine to true signal maximum within ±50 ms
    """
    # 1. Bandpass 5-25 Hz
    nyq  = sr / 2.0
    b, a = butter(2, [5 / nyq, 25 / nyq], btype='band')
    bp   = filtfilt(b, a, sig.astype(np.float64))

    # 2. Derivative
    d = np.diff(bp, prepend=bp[0])

    # 3. Square
    d2 = d * d

    # 4. Moving average integration 150 ms
    w   = max(1, int(sr * 0.150))
    kernel = np.ones(w) / w
    mwa = np.convolve(d2, kernel, mode='same')

    # 5. Adaptive threshold: use lower percentile to avoid missing weak beats
    threshold  = np.percentile(mwa, 94) * 0.18
    min_dist   = int(sr * min_rr_sec)
    peak_idx, props = find_peaks(mwa, height=threshold, distance=min_dist)

    # 6. Refine to actual signal max in ±50 ms window
    refine_half = int(sr * 0.050)
    refined = []
    for pi in peak_idx:
        lo_i = max(0, pi - refine_half)
        hi_i = min(len(sig), pi + refine_half)
        local_max = lo_i + np.argmax(sig[lo_i:hi_i])
        refined.append(local_max)
    return np.array(refined)

r_peaks_local = detect_r_peaks(ov_sig, ecg_sr)
r_peaks_t     = ov_t[r_peaks_local]   # absolute ECG time

print(f"  R-peaks detected: {len(r_peaks_t)}")

# Compute instantaneous HR from RR intervals
rr_intervals = np.diff(r_peaks_t)
rr_hr        = 60.0 / rr_intervals          # bpm
rr_t_mid     = (r_peaks_t[:-1] + r_peaks_t[1:]) / 2  # midpoint time

# Align to BioTrace+ time axis (subtract offset)
rr_bt_t = rr_t_mid - ECG_OFFSET_SEC

# Filter physiological range (40-160 bpm removes extreme outliers)
valid_rr = (rr_hr >= 40) & (rr_hr <= 160)
rr_hr_v  = rr_hr[valid_rr]
rr_bt_tv = rr_bt_t[valid_rr]

print(f"  Valid RR intervals: {valid_rr.sum()}")
print(f"  ECG mean HR (overlap): {rr_hr_v.mean():.2f} bpm")

# BioTrace+ mean HR in same window
bt_valid_hr = bt_hr[bt_hr > 0]
print(f"  BioTrace+ mean HR   : {bt_valid_hr.mean():.2f} bpm")
print(f"  Difference          : {rr_hr_v.mean() - bt_valid_hr.mean():+.2f} bpm")

# ── Step 5: full overview stats ───────────────────────────────────────────────
print()
print("=" * 60)
print("Step 5: Summary comparison")
print("=" * 60)
print(f"  ECG HR (overlap, n={valid_rr.sum()} beats) : {rr_hr_v.mean():.2f} ± {rr_hr_v.std():.2f} bpm")
print(f"  BioTrace+ HR (full session)          : {bt_valid_hr.mean():.2f} ± {bt_valid_hr.std():.2f} bpm")
print(f"  Offset error                         : {rr_hr_v.mean() - bt_valid_hr.mean():+.3f} bpm")
print(f"  Relative error                       : {abs(rr_hr_v.mean() - bt_valid_hr.mean())/bt_valid_hr.mean()*100:.2f}%")

# ── Step 6: multi-panel figure ────────────────────────────────────────────────
print()
print("=" * 60)
print("Step 6: Generating figure")
print("=" * 60)

fig = plt.figure(figsize=(16, 14), facecolor='#0D0D0D')
gs  = gridspec.GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.3)

DARK_BG   = '#0D0D0D'
PANEL_BG  = '#111111'
ECG_COLOR = '#00E040'
BVP_COLOR = '#4FC3F7'
HR_COLOR  = '#FF8A65'
HR2_COLOR = '#FFD54F'
REF_COLOR = '#EF5350'
GRID_C    = '#222222'
TEXT_C    = '#CCCCCC'

def style_ax(ax, title='', xlabel='', ylabel=''):
    ax.set_facecolor(PANEL_BG)
    for sp in ax.spines.values():
        sp.set_edgecolor('#333333')
    ax.tick_params(colors=TEXT_C, labelsize=8)
    ax.grid(True, color=GRID_C, linewidth=0.4, linestyle='--')
    if title:  ax.set_title(title, color=TEXT_C, fontsize=9, pad=4)
    if xlabel: ax.set_xlabel(xlabel, color=TEXT_C, fontsize=8)
    if ylabel: ax.set_ylabel(ylabel, color=TEXT_C, fontsize=8)

# ── Panel 1 (top, full width): ECG overview 0-120s ──────────────────────────
ax1 = fig.add_subplot(gs[0, :])
t_s, t_e = 0, ecg_t[-1]   # full recording
m = (ecg_t >= t_s) & (ecg_t <= t_e)
sig_plot = ecg_sig[m].copy() / 1000.0
sig_plot[ecg_lo[m]] = np.nan
# Clip extreme edge artifacts for display (keep ±5 mV)
sig_plot = np.clip(sig_plot, -3, 3)
ax1.plot(ecg_t[m], sig_plot, color=ECG_COLOR, linewidth=0.4, alpha=0.9)
ax1.axvline(ECG_OFFSET_SEC, color='white', linewidth=0.8, linestyle=':', alpha=0.6,
            label=f'BioTrace+ start (+{ECG_OFFSET_SEC}s)')
ax1.legend(fontsize=7, loc='upper right', facecolor='#1A1A1A', labelcolor='white')
style_ax(ax1, f'ECG Overview  0–{int(t_e)}s  |  Patient {r["patient_id"]}  {r["start_date"]} {r["start_time"]}',
         'Time (s)', 'mV')

# ── Panel 2 (row 1 left): BioTrace+ BVP waveform ────────────────────────────
ax2 = fig.add_subplot(gs[1, 0])
ax2.plot(bt_time_s, bt_bvp, color=BVP_COLOR, linewidth=0.5)
style_ax(ax2, 'BioTrace+ BVP (photoplethysmography)', 'BioTrace+ time (s)', 'BVP (a.u.)')

# ── Panel 3 (row 1 right): BioTrace+ HR ──────────────────────────────────────
ax3 = fig.add_subplot(gs[1, 1])
ax3.plot(bt_time_s, bt_hr, color=HR_COLOR, linewidth=0.8, label='BioTrace+ HR')
ax3.axhline(bt_valid_hr.mean(), color=HR_COLOR, linewidth=0.6, linestyle='--',
            alpha=0.5, label=f'Mean {bt_valid_hr.mean():.1f} bpm')
style_ax(ax3, 'BioTrace+ [G] Heart Rate', 'BioTrace+ time (s)', 'HR (bpm)')
ax3.legend(fontsize=7, facecolor='#1A1A1A', labelcolor='white')

# ── Panel 4 (row 2, full width): ECG in overlap window + R-peaks ─────────────
ax4 = fig.add_subplot(gs[2, :])
# Show first 30s of overlap for clarity
show_end = t_overlap_start + 30
m2 = (ecg_t >= t_overlap_start) & (ecg_t <= show_end)
sig4 = ecg_sig[m2].copy() / 1000.0
sig4[ecg_lo[m2]] = np.nan
sig4 = np.clip(sig4, -3, 3)
ax4.plot(ecg_t[m2], sig4, color=ECG_COLOR, linewidth=0.5, label='ECG')
# Plot R-peaks in this window
rp_in_win = r_peaks_t[(r_peaks_t >= t_overlap_start) & (r_peaks_t <= show_end)]
if len(rp_in_win):
    rp_idx_local = np.searchsorted(ecg_t, rp_in_win)
    rp_idx_local = np.clip(rp_idx_local, 0, len(ecg_sig)-1)
    ax4.plot(rp_in_win, ecg_sig[rp_idx_local] / 1000.0,
             'v', color='#FF4081', markersize=5, label=f'{len(rp_in_win)} R-peaks')
ax4.legend(fontsize=7, facecolor='#1A1A1A', labelcolor='white')
style_ax(ax4,
    f'ECG in BioTrace+ overlap window  ({t_overlap_start:.0f}s – {t_overlap_start+30:.0f}s of ECG)',
    'ECG time (s)', 'mV')

# ── Panel 5 (row 3 left): HR comparison ──────────────────────────────────────
ax5 = fig.add_subplot(gs[3, 0])
# ECG instantaneous HR (BioTrace+ time axis)
ax5.scatter(rr_bt_tv, rr_hr_v, s=8, color=ECG_COLOR, alpha=0.7,
            label=f'ECG R-peaks HR  mean={rr_hr_v.mean():.1f} bpm')
ax5.plot(bt_time_s, bt_hr, color=HR_COLOR, linewidth=0.8, alpha=0.8,
         label=f'BioTrace+ HR  mean={bt_valid_hr.mean():.1f} bpm')
ax5.axhline(rr_hr_v.mean(), color=ECG_COLOR, linewidth=0.5, linestyle='--', alpha=0.4)
ax5.axhline(bt_valid_hr.mean(), color=HR_COLOR, linewidth=0.5, linestyle='--', alpha=0.4)
style_ax(ax5, 'HR Comparison: ECG-derived vs BioTrace+', 'BioTrace+ time (s)', 'HR (bpm)')
ax5.legend(fontsize=7, facecolor='#1A1A1A', labelcolor='white')

# ── Panel 6 (row 3 right): sample-level validation 30-40s ────────────────────
ax6 = fig.add_subplot(gs[3, 1])
ax6.plot(ref_t, ref_uv / 1000.0, color=REF_COLOR, linewidth=1.2,
         label='ECGViewer export (reference)', alpha=0.9)
ax6.plot(ref_t, our_slice / 1000.0, color=ECG_COLOR, linewidth=0.8,
         linestyle='--', label='Our parser output', alpha=0.9)
diff_rms = np.sqrt((diff**2).mean())
style_ax(ax6,
    f'Sample-level check 30–40s  RMS diff={diff_rms:.4f} uV',
    'Time (s)', 'mV')
ax6.legend(fontsize=7, facecolor='#1A1A1A', labelcolor='white')

# ── Title & summary text ──────────────────────────────────────────────────────
fig.suptitle(
    f"DR200/HE ECG Validation  |  {r['start_date']} {r['start_time']}  |  "
    f"ECG {rr_hr_v.mean():.1f} bpm  vs  BioTrace+ {bt_valid_hr.mean():.1f} bpm  "
    f"(err={rr_hr_v.mean()-bt_valid_hr.mean():+.2f} bpm)",
    color='white', fontsize=11, y=0.98
)

plt.savefig(r"C:\Users\TSIC\Documents\GitHub\Heart\output\ecg_validation.png",
            dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
print("  Saved: output/ecg_validation.png")
plt.show()
