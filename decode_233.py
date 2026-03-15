import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.signal import butter, filtfilt, find_peaks
from numpy.fft import rfft, rfftfreq
import struct, os

filepath = 'C:/Users/TSIC/Documents/GitHub/Heart/233.dat'
with open(filepath, 'rb') as f:
    data = f.read()

BLOCK_SIZE      = 512
DATA_OFFSET     = 10
BYTES_PER_BLOCK = 498
SR              = 180
UV_PER_LSB      = 12.5
LEAD_OFF        = 0x777   # = 1911

# ---- Decode 12-bit LE ----
def decode_12bit_le(buf):
    out = []
    for i in range(0, len(buf) - 2, 3):
        b0, b1, b2 = buf[i], buf[i+1], buf[i+2]
        out.append(b0 | ((b1 & 0x0F) << 8))
        out.append((b1 >> 4) | (b2 << 4))
    return np.array(out, dtype=np.int32)

# ---- Find data bounds ----
last_active = 3
total_blocks = len(data) // BLOCK_SIZE
for bi in range(3, total_blocks):
    off = bi * BLOCK_SIZE + DATA_OFFSET
    if any(b != 0 for b in data[off:off+BYTES_PER_BLOCK]):
        last_active = bi
    else:
        if not any(any(b != 0 for b in data[(bi+k)*BLOCK_SIZE+DATA_OFFSET:(bi+k)*BLOCK_SIZE+DATA_OFFSET+BYTES_PER_BLOCK])
                   for k in range(1, min(10, total_blocks-bi))):
            break

# ---- Collect raw bytes ----
raw = bytearray()
for bi in range(3, last_active + 1):
    off = bi * BLOCK_SIZE + DATA_OFFSET
    raw.extend(data[off:off + BYTES_PER_BLOCK])

samples_raw = decode_12bit_le(bytes(raw))
s_uv  = (samples_raw.astype(np.float64) - 2048) * UV_PER_LSB
t     = np.arange(len(s_uv)) / SR
lo_mask = (samples_raw == LEAD_OFF)

print(f'Duration: {len(t)/SR:.1f}s  Samples: {len(t):,}  Lead-off: {lo_mask.mean()*100:.1f}%')
print(f'ADC range: {samples_raw.min()} - {samples_raw.max()}')

# ---- Filters ----
def bpf(x, lo=0.5, hi=40, fs=SR):
    b, a = butter(3, [lo/(fs/2), hi/(fs/2)], btype='band')
    return filtfilt(b, a, x)

def lpf(x, hi=15, fs=SR):
    b, a = butter(3, hi/(fs/2), btype='low')
    return filtfilt(b, a, x)

# Fill lead-off for filtering
s_filled = s_uv.copy()
if (~lo_mask).any():
    baseline = np.median(s_uv[~lo_mask])
else:
    baseline = 0.0
s_filled[lo_mask] = baseline

s_bp  = bpf(s_filled)        # diagnostic 0.5-40 Hz
s_lp  = lpf(s_filled, 15)    # smooth for R-peak detection
s_bp[lo_mask] = np.nan

# Center
s_bp_mv = (s_bp - np.nanmedian(s_bp)) / 1000.0
s_uv_c  = s_uv - baseline

# ---- R-peak detection ----
sig_for_peaks = np.nan_to_num(s_bp_mv)
inv = -sig_for_peaks if abs(np.nanmin(sig_for_peaks)) > np.nanmax(sig_for_peaks) else sig_for_peaks
thr = np.percentile(inv[inv != 0], 75)
peaks, props = find_peaks(inv, height=thr, distance=int(0.25 * SR))
if len(peaks) > 1:
    rr    = np.diff(t[peaks])
    hr    = 60.0 / rr.mean()
    hr_std = 60.0 / rr.std() if rr.std() > 0 else 0
    print(f'HR: {hr:.1f} bpm  RR mean={rr.mean()*1000:.0f}ms  std={rr.std()*1000:.0f}ms  n={len(peaks)} beats')
else:
    hr = 0; rr = np.array([])
    print('Not enough peaks detected')

# ---- ECG grid helper ----
def ecg_grid(ax, t0, dur, amp=(-2,2)):
    ax.set_facecolor('#fffef5')
    ax.set_xlim(t0, t0 + dur)
    ax.set_ylim(amp)
    for x in np.arange(t0, t0+dur+0.001, 0.2):
        ax.axvline(x, color='#ffb3b3', lw=0.6, zorder=0)
    for y in np.arange(amp[0], amp[1]+0.001, 0.5):
        ax.axhline(y, color='#ffb3b3', lw=0.6, zorder=0)
    for x in np.arange(t0, t0+dur+0.001, 0.04):
        ax.axvline(x, color='#ffe8e8', lw=0.2, zorder=0)
    for y in np.arange(amp[0], amp[1]+0.001, 0.1):
        ax.axhline(y, color='#ffe8e8', lw=0.2, zorder=0)

def smart_ylim(seg_mv, margin=1.2):
    p2, p98 = np.nanpercentile(seg_mv, 1), np.nanpercentile(seg_mv, 99)
    rng = max(abs(p2), abs(p98)) * margin
    rng = max(rng, 0.5)
    return (-rng, rng)

# ---- Figure ----
fig = plt.figure(figsize=(22, 20), facecolor='white')
fig.suptitle(
    'DR200/HE Holter ECG  |  Patient 123  |  2026-01-23  14:23:32\n'
    f'SN=046383 V4.47  |  {len(t)/SR:.1f}s ({len(t)/SR/60:.2f} min)  |  '
    f'SR=180 Hz  |  12-bit LE packed  |  12.5 uV/LSB',
    fontsize=13, fontweight='bold', y=0.995
)

gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.52, wspace=0.3)

# ======== P1: Full recording ========
ax1 = fig.add_subplot(gs[0, :])
ax1.plot(t, s_uv_c / 1000, lw=0.4, color='#1565C0', alpha=0.8, label='Raw ADC')
ax1.plot(t, np.nan_to_num(s_bp_mv), lw=0.7, color='#B71C1C', alpha=0.6, label='Bandpass 0.5-40Hz')
ax1.axhline(0, color='gray', lw=0.5)
ax1.set_facecolor('#f5f7ff')
ax1.set_xlabel('Time (s)', fontsize=9)
ax1.set_ylabel('mV', fontsize=9)
ax1.set_title('Full Recording (97.8 s)  —  Raw + Filtered', fontsize=10, fontweight='bold')
ax1.legend(fontsize=9, loc='upper right')
ax1.grid(True, alpha=0.25)
if len(peaks) > 1:
    ax1.plot(t[peaks], np.nan_to_num(s_bp_mv)[peaks], 'v', color='red',
             markersize=4, label=f'R-peaks ({len(peaks)})', zorder=6)
    ax1.legend(fontsize=9)
# lead-off shading
for i in np.where(np.diff(lo_mask.astype(int)) == 1)[0]:
    ends = np.where(np.diff(lo_mask.astype(int)[i:]) == -1)[0]
    end = i + (ends[0] if len(ends) > 0 else 10)
    ax1.axvspan(t[i], t[min(end, len(t)-1)], color='#ff5252', alpha=0.18, zorder=0)

# ======== P2: 10-second ECG strip (ECG paper) ========
ax2 = fig.add_subplot(gs[1, :])
# Find a 10s window with fewest lead-off samples
win = min(10*SR, len(t))
best_start, best_lo = 0, len(t)
for st in range(0, len(t)-win, SR//2):
    lo_cnt = lo_mask[st:st+win].sum()
    if lo_cnt < best_lo:
        best_lo = lo_cnt
        best_start = st

i0, i1 = best_start, best_start + win
t_strip = t[i0:i1]
seg_mv  = s_bp_mv[i0:i1]
ylim2   = smart_ylim(seg_mv)
ecg_grid(ax2, t_strip[0], t_strip[-1]-t_strip[0], amp=ylim2)
ax2.plot(t_strip, seg_mv, lw=0.9, color='black', zorder=5)
pk_in   = peaks[(peaks >= i0) & (peaks < i1)]
if len(pk_in) > 1:
    rr_strip = np.diff(t[pk_in])
    hr_strip = 60.0 / rr_strip.mean()
    ax2.plot(t[pk_in], seg_mv[pk_in - i0], 'v', color='red',
             markersize=5, zorder=7, label=f'R-peak ({hr_strip:.0f} bpm)')
    ax2.legend(fontsize=9)
ax2.set_xlabel('Time (s)', fontsize=9)
ax2.set_title(f'10-second ECG Strip (t={t_strip[0]:.1f}-{t_strip[-1]:.1f}s)  '
              f'[0.04s/small-div  0.1mV/small-div]', fontsize=10, fontweight='bold')

# ======== P3: 5-second zoom ========
ax3 = fig.add_subplot(gs[2, :])
w5 = 5 * SR
i0_5 = best_start + int(1.5*SR)
i1_5 = min(i0_5 + w5, len(t))
t5  = t[i0_5:i1_5]
s5  = s_bp_mv[i0_5:i1_5]
ylim3 = smart_ylim(s5)
ecg_grid(ax3, t5[0], t5[-1]-t5[0], amp=ylim3)
ax3.plot(t5, s5, lw=1.2, color='black', zorder=5)
pk5 = peaks[(peaks >= i0_5) & (peaks < i1_5)]
if len(pk5) >= 2:
    rr5 = np.diff(t[pk5])
    for pk in pk5:
        ax3.axvline(t[pk], color='red', lw=0.8, alpha=0.65, zorder=7)
    ax3.text(0.01, 0.97,
             f'HR = {60/rr5.mean():.1f} bpm  |  RR = {rr5.mean()*1000:.0f} ms  |  '
             f'{len(pk5)} beats in 5s',
             transform=ax3.transAxes, va='top', ha='left', fontsize=10,
             fontweight='bold', color='red',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))
ax3.set_xlabel('Time (s)', fontsize=9)
ax3.set_title('5-second Detail View', fontsize=10, fontweight='bold')

# ======== P4: Averaged beat (template) ========
ax4 = fig.add_subplot(gs[3, 0])
beat_hw = int(0.4 * SR)   # ±400ms window around each R-peak
beats = []
for pk in peaks:
    if pk - beat_hw >= 0 and pk + beat_hw < len(s_bp_mv):
        beat = s_bp_mv[pk - beat_hw: pk + beat_hw]
        beats.append(beat - np.nanmedian(beat))
if len(beats) >= 3:
    beats_arr = np.array(beats)
    beat_mean = np.nanmean(beats_arr, axis=0)
    beat_std  = np.nanstd(beats_arr, axis=0)
    bt = np.linspace(-beat_hw/SR*1000, beat_hw/SR*1000, len(beat_mean))
    ax4.fill_between(bt, beat_mean - beat_std, beat_mean + beat_std,
                     alpha=0.25, color='steelblue', label='±1 SD')
    ax4.plot(bt, beat_mean, lw=1.5, color='#1565C0', label=f'Mean beat (n={len(beats)})')
    ax4.axvline(0, color='red', lw=1, linestyle='--', label='R-peak')
    ax4.axhline(0, color='gray', lw=0.5)
    ax4.set_xlabel('Time relative to R-peak (ms)', fontsize=9)
    ax4.set_ylabel('mV', fontsize=9)
    ax4.set_title('Averaged Beat Template', fontsize=10, fontweight='bold')
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)
    ax4.set_facecolor('#f0f8ff')

# ======== P5: RR interval tachogram ========
ax5 = fig.add_subplot(gs[3, 1])
if len(peaks) > 1:
    rr_ms = np.diff(t[peaks]) * 1000
    t_rr  = t[peaks[1:]]
    ax5.plot(t_rr, rr_ms, 'o-', color='#2E7D32', markersize=4, lw=1.2)
    ax5.axhline(rr_ms.mean(), color='red', lw=1.2, linestyle='--',
                label=f'Mean RR={rr_ms.mean():.0f}ms ({60000/rr_ms.mean():.1f}bpm)')
    ax5.fill_between(t_rr,
                     rr_ms.mean()-rr_ms.std(), rr_ms.mean()+rr_ms.std(),
                     alpha=0.2, color='green', label=f'±1SD={rr_ms.std():.1f}ms')
    ax5.set_xlabel('Time (s)', fontsize=9)
    ax5.set_ylabel('RR interval (ms)', fontsize=9)
    ax5.set_title(f'RR Tachogram  —  HR Variability', fontsize=10, fontweight='bold')
    ax5.legend(fontsize=8)
    ax5.grid(True, alpha=0.3)
    ax5.set_facecolor('#f8fff8')

# ======== P6: FFT ========
ax6 = fig.add_subplot(gs[4, 0])
valid_sig = s_bp_mv[~lo_mask & ~np.isnan(s_bp_mv)]
if len(valid_sig) > 0:
    fft_m = np.abs(rfft(valid_sig - valid_sig.mean()))
    fft_f = rfftfreq(len(valid_sig), d=1/SR)
    m = (fft_f > 0.3) & (fft_f <= 45)
    ax6.semilogy(fft_f[m], fft_m[m], lw=0.8, color='#6A1B9A')
    ax6.axvspan(0.8, 3.0, alpha=0.18, color='#A5D6A7', label='HR band 48-180 bpm')
    if hr > 0:
        ax6.axvline(hr/60, color='red', lw=1.5, linestyle='--', label=f'{hr:.0f} bpm')
        ax6.axvline(hr/60*2, color='orange', lw=1, linestyle=':', label=f'2nd harmonic')
    ax6.set_xlabel('Frequency (Hz)', fontsize=9)
    ax6.set_ylabel('Magnitude (log)', fontsize=9)
    ax6.set_title('Power Spectrum', fontsize=10, fontweight='bold')
    ax6.legend(fontsize=8)
    ax6.grid(True, alpha=0.3)
    ax6.set_facecolor('#faf8ff')

# ======== P7: Summary ========
ax7 = fig.add_subplot(gs[4, 1])
ax7.axis('off')
if len(peaks) > 1:
    rr_all = np.diff(t[peaks]) * 1000
    sdnn   = rr_all.std()
    rmssd  = np.sqrt(np.mean(np.diff(rr_all)**2))
else:
    rr_all = np.array([0]); sdnn = 0; rmssd = 0

summary = [
    ('Patient ID',     '123'),
    ('Recording',      '2026-01-23  14:23:32'),
    ('Duration',       f'{len(t)/SR:.1f} s  ({len(t)/SR/60:.2f} min)'),
    ('Beats detected', f'{len(peaks)}  beats'),
    ('Mean HR',        f'{hr:.1f} bpm' if hr > 0 else 'N/A'),
    ('Mean RR',        f'{rr_all.mean():.0f} ms' if len(peaks)>1 else 'N/A'),
    ('SDNN',           f'{sdnn:.1f} ms  (HRV)'),
    ('RMSSD',          f'{rmssd:.1f} ms  (HRV)'),
    ('Lead-off',       f'{lo_mask.mean()*100:.1f}%'),
    ('Signal amplitude', f'{np.nanstd(s_bp_mv)*1000:.0f} uV  ({np.nanstd(s_bp_mv):.2f} mV)'),
    ('Recorder SN',    '046383  (V4.47)'),
    ('Encoding',       '12-bit LE packed,  12.5 uV/LSB'),
]
ax7.set_title('Clinical Summary', fontsize=10, fontweight='bold')
y = 0.97
for label, val in summary:
    ax7.text(0.04, y, label + ':', fontsize=9, fontweight='bold',
             transform=ax7.transAxes, va='top', color='#1a237e')
    ax7.text(0.52, y, val, fontsize=9, transform=ax7.transAxes, va='top')
    y -= 0.078
ax7.add_patch(plt.Rectangle((0.01,0.01), 0.98, 0.98, fill=False,
                              edgecolor='#1565C0', lw=1.5, transform=ax7.transAxes))

out = 'C:/Users/TSIC/Documents/GitHub/Heart/output/233_ecg.png'
os.makedirs(os.path.dirname(out), exist_ok=True)
plt.savefig(out, dpi=145, bbox_inches='tight', facecolor='white')
print(f'Saved: {out}')
