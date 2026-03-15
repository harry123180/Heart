import struct, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, find_peaks
from scipy.ndimage import uniform_filter1d

filepath = 'C:/Users/TSIC/Documents/GitHub/Heart/flash.dat'
with open(filepath, 'rb') as f:
    data = f.read()

BLOCK_SIZE = 512
DATA_OFFSET = 10
BYTES_PER_BLOCK = 498
SR = 180
LAST_BLOCK = 148

# Collect raw bytes across all valid blocks
raw_all = bytearray()
for bi in range(3, LAST_BLOCK+1):
    off = bi * BLOCK_SIZE + DATA_OFFSET
    raw_all.extend(data[off:off+BYTES_PER_BLOCK])

raw_bytes = np.frombuffer(bytes(raw_all), dtype=np.uint8).astype(np.float32)

# ---- Method 1: 12-bit packed LE (single channel) ----
def decode_12bit_le(raw_bytes_buf):
    out = []
    rb = bytes(raw_bytes_buf)
    for i in range(0, len(rb)-2, 3):
        b0, b1, b2 = rb[i], rb[i+1], rb[i+2]
        out.append(b0 | ((b1 & 0xF) << 8))
        out.append((b1 >> 4) | (b2 << 4))
    return np.array(out, dtype=np.float32)

s12 = decode_12bit_le(bytes(raw_all))
t12 = np.arange(len(s12)) / SR

# ---- Method 2: B2 bytes only (every 3rd byte starting at 2) ----
# B2 = upper 8 bits of S2. If ECG signal is mainly in upper bits, B2 would look like ECG
b2_stream = raw_bytes[2::3]   # 166 values per block
t_b2 = np.arange(len(b2_stream)) / (SR * 2/3)  # B2 = 1 per 3 bytes = SR/1.5 = 120 Hz

# ---- Method 3: ALL bytes as 8-bit stream ----
# If device actually stores 8-bit (the 12-bit spec might be ADC resolution, not storage)
t_u8 = np.arange(len(raw_bytes)) / (SR * 3/2)   # 1.5x more bytes than samples

# ---- Bandpass filter ----
def bpf(x, lo=0.5, hi=40, fs=SR):
    b, a = butter(3, [lo/(fs/2), hi/(fs/2)], btype='band')
    return filtfilt(b, a, x)

# ---- Autocorrelation to find heartrate ----
seg = s12[:SR*60]  # first 60 seconds
seg = seg - seg.mean()
acorr = np.correlate(seg, seg, mode='full')
acorr = acorr[len(acorr)//2:]
acorr = acorr / acorr[0]
lag = np.arange(len(acorr)) / SR

# Find heartrate peak in 0.4-2.0 sec range (30-150 bpm)
i0 = int(0.4 * SR)
i1 = int(2.0 * SR)
peak_lags, _ = find_peaks(acorr[i0:i1], height=0.05)
if len(peak_lags) > 0:
    hr_lag = (peak_lags[0] + i0) / SR
    hr_bpm = 60 / hr_lag
    print(f'Autocorrelation HR estimate: lag={hr_lag:.3f}s = {hr_bpm:.1f} bpm')
else:
    hr_lag = None
    print('No clear HR peak found in autocorrelation')

fig = plt.figure(figsize=(22, 18))
fig.suptitle('DR200 ECG Final Analysis', fontsize=13)

# Panel 1: Zoom into 3 seconds of 12-bit decoded (t=30-33s)
ax1 = fig.add_subplot(4, 2, (1,2))
i_start = int(30*SR)
i_end = int(33*SR)
seg3 = s12[i_start:i_end]
t3 = t12[i_start:i_end]
seg3_c = seg3 - np.median(seg3)
ax1.plot(t3 - t3[0], seg3_c, lw=0.7, color='navy', label='12-bit LE decoded')
ax1.plot(t3 - t3[0], uniform_filter1d(seg3_c, 7), lw=1.2, color='red', label='7-pt MA')
ax1.set_title('3-second zoom (12-bit LE decoded, t=30-33s)')
ax1.set_ylabel('ADC counts (DC removed)')
ax1.set_xlabel('Time (s)')
ax1.legend(fontsize=9)
ax1.grid(True, alpha=0.3)

# Panel 2: B2 bytes (120Hz) zoom
ax2 = fig.add_subplot(4, 2, 3)
b2_start = int(30 * 120)
b2_end = int(33 * 120)
b2_seg = b2_stream[b2_start:b2_end]
t_b2_seg = np.arange(len(b2_seg)) / 120
b2_c = b2_seg - np.median(b2_seg)
ax2.plot(t_b2_seg, b2_c, lw=0.7, color='darkgreen')
ax2.set_title('B2 bytes only (upper 8 bits, 120Hz effective) @ t=30-33s')
ax2.set_ylabel('uint8 (DC removed)')
ax2.set_xlabel('Time (s)')
ax2.grid(True, alpha=0.3)

# Panel 3: B0 bytes
ax3 = fig.add_subplot(4, 2, 4)
b0_stream = raw_bytes[0::3]
b0_start = int(30 * 120)
b0_end = int(33 * 120)
b0_seg = b0_stream[b0_start:b0_end]
b0_c = b0_seg - np.median(b0_seg)
ax3.plot(t_b2_seg, b0_c, lw=0.7, color='darkorange')
ax3.set_title('B0 bytes only (lower 8 bits, 120Hz effective) @ t=30-33s')
ax3.set_ylabel('uint8 (DC removed)')
ax3.set_xlabel('Time (s)')
ax3.grid(True, alpha=0.3)

# Panel 4: Autocorrelation
ax4 = fig.add_subplot(4, 2, 5)
ax4.plot(lag[:int(3*SR)], acorr[:int(3*SR)], lw=0.8, color='purple')
if hr_lag:
    ax4.axvline(hr_lag, color='red', lw=1.5, linestyle='--', label=f'HR={hr_bpm:.1f} bpm')
ax4.set_title('Autocorrelation of 12-bit decoded signal (first 60s)')
ax4.set_xlabel('Lag (s)')
ax4.set_ylabel('Correlation')
ax4.legend(fontsize=9)
ax4.grid(True, alpha=0.3)

# Panel 5: Full 12-bit recording bandpass
ax5 = fig.add_subplot(4, 2, 6)
s12_filtered = bpf(s12, 0.5, 40, SR)
ax5.plot(t12, s12_filtered, lw=0.3, color='steelblue', alpha=0.8)
ax5.set_title('Full recording bandpass 0.5-40 Hz (12-bit LE)')
ax5.set_ylabel('Filtered counts')
ax5.set_xlabel('Time (s)')
ax5.grid(True, alpha=0.3)

# Panel 6: FFT
ax6 = fig.add_subplot(4, 2, (7,8))
from numpy.fft import rfft, rfftfreq
fft_s = np.abs(rfft(s12 - s12.mean()))
freqs_s = rfftfreq(len(s12), d=1/SR)
fft_b2 = np.abs(rfft(b2_stream - b2_stream.mean()))
freqs_b2 = rfftfreq(len(b2_stream), d=1/120.0)
mask_s = freqs_s <= 30
mask_b2 = freqs_b2 <= 30
ax6.semilogy(freqs_s[mask_s], fft_s[mask_s]/fft_s[mask_s].max(), lw=0.6, color='navy', alpha=0.7, label='12-bit decoded (180Hz)')
ax6.semilogy(freqs_b2[mask_b2], fft_b2[mask_b2]/fft_b2[mask_b2].max(), lw=0.6, color='green', alpha=0.7, label='B2 bytes (120Hz)')
ax6.axvspan(0.8, 3.0, alpha=0.15, color='yellow', label='Typical HR 48-180 bpm')
ax6.set_xlabel('Frequency (Hz)')
ax6.set_ylabel('Norm. Magnitude (log)')
ax6.set_title('Power spectrum comparison')
ax6.legend(fontsize=9)
ax6.grid(True, alpha=0.3)

plt.tight_layout()
out = 'C:/Users/TSIC/Documents/GitHub/Heart/ecg_final.png'
plt.savefig(out, dpi=130, bbox_inches='tight')
print(f'Saved: {out}')
