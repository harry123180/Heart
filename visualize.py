import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.signal import butter, filtfilt, find_peaks
from numpy.fft import rfft, rfftfreq
import csv

# ---- Load decoded data ----
times, ch0 = [], []
with open('C:/Users/TSIC/Documents/GitHub/Heart/output/ecg_data.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        times.append(float(row['time_s']))
        ch0.append(float(row['ch0_uv']))

t  = np.array(times)
s  = np.array(ch0)   # microvolts
SR = 180

def bpf(x, lo=0.5, hi=40, fs=SR):
    b, a = butter(3, [lo/(fs/2), hi/(fs/2)], btype='band')
    return filtfilt(b, a, x)

s_f = bpf(s)

# Find cleanest 10-second window
win = 10 * SR
best_start, best_score = 0, np.inf
for start in range(0, len(s) - win, SR):
    seg = s_f[start:start+win]
    score = np.percentile(np.abs(np.diff(seg)), 95)
    if score < best_score:
        best_score = score
        best_start = start

print(f'Best window: t={best_start/SR:.1f}s  score={best_score:.0f}')

LEAD_OFF_UV = (1911 - 2048) * 12.5  # = -1712.5 uV

def auto_scale(seg_uv, margin=0.3):
    seg_c = seg_uv - np.median(seg_uv)
    p2, p98 = np.percentile(seg_c, 2), np.percentile(seg_c, 98)
    rng = max(abs(p2), abs(p98)) + margin * 1000
    return (-rng/1000, rng/1000)

def ecg_grid(ax, t_start, duration, amp_range=(-2, 2)):
    ax.set_facecolor('#fffef5')
    ax.set_xlim(t_start, t_start + duration)
    ax.set_ylim(amp_range)
    for x in np.arange(t_start, t_start+duration+0.001, 0.2):
        ax.axvline(x, color='#ffbbbb', lw=0.5, zorder=0)
    for y in np.arange(amp_range[0], amp_range[1]+0.001, 0.5):
        ax.axhline(y, color='#ffbbbb', lw=0.5, zorder=0)
    for x in np.arange(t_start, t_start+duration+0.001, 0.04):
        ax.axvline(x, color='#ffe4e4', lw=0.2, zorder=0)
    for y in np.arange(amp_range[0], amp_range[1]+0.001, 0.1):
        ax.axhline(y, color='#ffe4e4', lw=0.2, zorder=0)
    ax.set_ylabel('mV', fontsize=9)

# ---- Figure ----
fig = plt.figure(figsize=(22, 18), facecolor='white')
fig.suptitle(
    'DR200/HE Holter ECG  |  Patient 2121  |  2026-02-06  02:46:27\n'
    'SN=046040 V4.47  |  SR=180 Hz  |  12-bit LE packed  |  12.5 uV/LSB  |  Bandpass 0.5-40 Hz',
    fontsize=12, fontweight='bold', y=0.99
)

gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.48, wspace=0.3)

# --- Panel 1: Full overview ---
ax1 = fig.add_subplot(gs[0, :])
ds = 3
ax1.plot(t[::ds], s[::ds]/1000, lw=0.3, color='#1565C0', alpha=0.8)
ax1.set_facecolor('#f5f7ff')
ax1.set_xlabel('Time (s)', fontsize=9)
ax1.set_ylabel('mV', fontsize=9)
ax1.set_title('Full Recording Overview (Raw ADC counts -> mV)', fontsize=10, fontweight='bold')
ax1.axvspan(best_start/SR, (best_start+win)/SR, color='yellow', alpha=0.3, label='Analysis window')
ax1.axhline(0, color='gray', lw=0.5)
ax1.grid(True, alpha=0.25)
ax1.legend(fontsize=9)
lo_mask = np.abs(s - LEAD_OFF_UV) < 50
in_lo = False
lo_start = 0
for i in range(len(lo_mask)):
    if lo_mask[i] and not in_lo:
        in_lo = True
        lo_start = i
    elif not lo_mask[i] and in_lo:
        in_lo = False
        ax1.axvspan(t[lo_start], t[i], color='#ff5252', alpha=0.15, zorder=0)
ax1.text(0.995, 0.97, 'Red shading = Lead-off periods',
         transform=ax1.transAxes, ha='right', va='top', fontsize=8, color='#c62828')

# --- Panel 2: 10-second ECG strip ---
ax2 = fig.add_subplot(gs[1, :])
i0, i1 = best_start, best_start + win
seg10 = s_f[i0:i1]
t10   = t[i0:i1]
seg10_mv = (seg10 - np.median(seg10)) / 1000
sc = auto_scale(seg10 - np.median(seg10))
ecg_grid(ax2, t10[0], 10, amp_range=sc)
ax2.plot(t10, seg10_mv, lw=0.9, color='black', zorder=5)
ax2.set_xlabel('Time (s)', fontsize=9)
ax2.set_title(f'10-second ECG Strip (t={t10[0]:.1f}-{t10[-1]:.1f}s)', fontsize=10, fontweight='bold')

# --- Panel 3: 3-second zoom ---
ax3 = fig.add_subplot(gs[2, 0])
i0_3 = best_start + int(2*SR)
i1_3 = i0_3 + 3*SR
seg3    = s_f[i0_3:i1_3]
t3      = t[i0_3:i1_3]
seg3_mv = (seg3 - np.median(seg3)) / 1000
sc3     = auto_scale(seg3 - np.median(seg3), margin=0.15)
ecg_grid(ax3, t3[0], 3, amp_range=sc3)
ax3.plot(t3, seg3_mv, lw=1.1, color='black', zorder=5)
ax3.set_xlabel('Time (s)', fontsize=9)
ax3.set_title('3-second Detail (0.04s/div, 0.1 mV/div)', fontsize=10, fontweight='bold')

# R-peak detection
try:
    inv = seg3_mv.copy()
    if abs(inv.min()) > inv.max():
        inv = -inv
    thr = np.percentile(inv, 72)
    pks, _ = find_peaks(inv, height=thr, distance=int(0.28*SR))
    if len(pks) >= 2:
        rr  = np.diff(t3[pks])
        hr  = 60 / rr.mean()
        for pk in pks:
            ax3.axvline(t3[pk], color='red', lw=1.0, alpha=0.7, zorder=7)
        ax3.text(0.02, 0.97, f'HR ~ {hr:.0f} bpm  ({len(pks)} peaks)',
                 transform=ax3.transAxes, ha='left', va='top', fontsize=9,
                 color='red', fontweight='bold',
                 bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
except Exception as e:
    print(f'Peak detect: {e}')

# --- Panel 4: FFT ---
ax4 = fig.add_subplot(gs[2, 1])
fft_mag = np.abs(rfft(s_f - s_f.mean()))
freqs   = rfftfreq(len(s_f), d=1/SR)
m = (freqs > 0.2) & (freqs <= 30)
ax4.semilogy(freqs[m], fft_mag[m], lw=0.8, color='#6A1B9A')
ax4.axvspan(0.8, 3.0, alpha=0.18, color='#66BB6A', label='HR 48-180 bpm')
ax4.set_xlabel('Frequency (Hz)', fontsize=9)
ax4.set_ylabel('Magnitude (log)', fontsize=9)
ax4.set_title('Power Spectrum (full recording)', fontsize=10, fontweight='bold')
ax4.grid(True, alpha=0.25)
ax4.set_facecolor('#faf8ff')
ax4.legend(fontsize=8)

# Mark top 3 peaks in HR band
hr_m = (freqs >= 0.8) & (freqs <= 3.0)
hr_freqs = freqs[hr_m]
hr_mag   = fft_mag[hr_m]
if len(hr_mag) > 0:
    top3 = np.argsort(hr_mag)[-3:][::-1]
    for idx in top3:
        f = hr_freqs[idx]
        ax4.axvline(f, color='red', lw=1.2, linestyle='--', alpha=0.8)
        ax4.text(f + 0.05, hr_mag[idx]*0.8, f'{f:.2f}Hz\n({f*60:.0f}bpm)',
                 fontsize=7, color='red', va='top')

# --- Panel 5: Amplitude histogram ---
ax5 = fig.add_subplot(gs[3, 0])
valid_mv = s_f / 1000
valid_mv_c = valid_mv - np.median(valid_mv)
ax5.hist(valid_mv_c, bins=250, color='#1565C0', alpha=0.75, density=True)
ax5.set_xlabel('Amplitude (mV, baseline-removed)', fontsize=9)
ax5.set_ylabel('Density', fontsize=9)
ax5.set_title('Amplitude Distribution', fontsize=10, fontweight='bold')
ax5.grid(True, alpha=0.25)
ax5.set_facecolor('#f0f8ff')
std_mv = valid_mv_c.std()
ax5.axvline(-2*std_mv, color='orange', lw=1, linestyle='--', label=f'+-2σ ({2*std_mv:.1f} mV)')
ax5.axvline(+2*std_mv, color='orange', lw=1, linestyle='--')
ax5.text(0.98, 0.95, f'Std={std_mv*1000:.0f} uV\n({std_mv:.2f} mV)',
         transform=ax5.transAxes, ha='right', va='top', fontsize=9,
         bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))
ax5.legend(fontsize=8)

# --- Panel 6: Summary table ---
ax6 = fig.add_subplot(gs[3, 1])
ax6.axis('off')
lo_pct = lo_mask.mean() * 100
summary = [
    ('Recording date',  '2026-02-06'),
    ('Start time',      '02:46:27'),
    ('Duration',        f'{len(t)/SR:.1f} s  ({len(t)/SR/60:.2f} min)'),
    ('Total samples',   f'{len(t):,}'),
    ('Sample rate',     '180 Hz'),
    ('Bit resolution',  '12-bit  (12.5 uV/LSB)'),
    ('Encoding',        '12-bit LE packed (3B=2S)'),
    ('Channels',        'SampleStorageFormat = 1'),
    ('Lead-off time',   f'{lo_pct:.1f}%  of recording'),
    ('Signal std',      f'{std_mv*1000:.0f} uV  ({std_mv:.2f} mV)'),
    ('Patient ID',      '2121'),
    ('Recorder SN',     '046040  (FW V4.47)'),
    ('Diary events',    '8 event types programmed'),
]
ax6.set_title('Recording Summary', fontsize=10, fontweight='bold')
y = 0.97
for label, val in summary:
    ax6.text(0.04, y, label + ':', fontsize=8.5, fontweight='bold',
             transform=ax6.transAxes, va='top', color='#1a237e')
    ax6.text(0.52, y, val, fontsize=8.5, transform=ax6.transAxes, va='top')
    y -= 0.071
rect = plt.Rectangle((0.01, 0.01), 0.98, 0.98, fill=False,
                      edgecolor='#1565C0', lw=1.5, transform=ax6.transAxes)
ax6.add_patch(rect)

out = 'C:/Users/TSIC/Documents/GitHub/Heart/output/ecg_detail.png'
plt.savefig(out, dpi=145, bbox_inches='tight', facecolor='white')
print(f'Saved: {out}')
