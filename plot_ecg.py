import struct, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

filepath = 'C:/Users/TSIC/Documents/GitHub/Heart/flash.dat'
with open(filepath, 'rb') as f:
    data = f.read()

BLOCK_SIZE = 512
DATA_OFFSET = 10
BYTES_PER_BLOCK = 498  # 498/3 = 166 pairs = 332 samples per block
SR = 180
LAST_ACTIVE_BLOCK = 148

# --- Decode 12-bit LE (Option B) block by block ---
def decode_block_12bit_le(raw_bytes):
    s = []
    for i in range(0, len(raw_bytes)-2, 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        s.append(b0 | ((b1 & 0xF) << 8))
        s.append((b1 >> 4) | (b2 << 4))
    return s

all_samples = []
for bi in range(3, LAST_ACTIVE_BLOCK + 1):
    off = bi * BLOCK_SIZE + DATA_OFFSET
    bd = data[off:off + BYTES_PER_BLOCK]
    all_samples.extend(decode_block_12bit_le(bd))

s = np.array(all_samples, dtype=np.float32)
t = np.arange(len(s)) / SR

print(f'Total samples: {len(s)} ({len(s)/SR:.1f} sec = {len(s)/SR/60:.2f} min)')
print(f'Value range: {s.min():.0f} - {s.max():.0f}  (baseline ~ {np.median(s):.0f})')
print(f'Std: {s.std():.1f} counts = {s.std()*12.5/1000:.2f} mV (if 12.5uV/LSB)')

# Convert to mV centered at median
s_mv = (s - np.median(s)) * 12.5 / 1000.0

fig = plt.figure(figsize=(22, 16))
fig.suptitle('DR200 Holter - ECG Waveform (12-bit LE packed, Option B)\n'
             f'Recording: 02:46:27 on 2026-02-06 | SR=180Hz | ~{len(s)/SR:.0f}s | Patient 2121',
             fontsize=12)

# Panel 1: full overview (raw counts)
ax1 = fig.add_subplot(4, 1, 1)
ax1.plot(t, s, lw=0.4, color='navy', alpha=0.8)
ax1.set_title('Full Recording - Raw ADC Counts')
ax1.set_ylabel('ADC count')
ax1.set_xlabel('Time (s)')
ax1.axhline(np.median(s), color='red', lw=0.8, linestyle='--', alpha=0.5, label='Median baseline')
ax1.legend(fontsize=8)
ax1.grid(True, alpha=0.3)

# Panel 2: 10s zoom (raw)
ax2 = fig.add_subplot(4, 1, 2)
t10, s10 = t[:SR*10], s[:SR*10]
ax2.plot(t10, s10, lw=0.8, color='steelblue')
ax2.set_title('First 10 seconds (raw counts)')
ax2.set_ylabel('ADC count')
ax2.set_xlabel('Time (s)')
ax2.grid(True, alpha=0.3)

# Panel 3: 10s zoom mV with light smoothing
from scipy.ndimage import uniform_filter1d
ax3 = fig.add_subplot(4, 1, 3)
s10_mv = s_mv[:SR*10]
# simple moving average to smooth out high-freq noise
s10_sm = uniform_filter1d(s10_mv, size=3)
ax3.plot(t10, s10_mv, lw=0.4, color='lightcoral', alpha=0.5, label='Raw')
ax3.plot(t10, s10_sm, lw=0.9, color='darkred', label='3-pt MA')
ax3.set_title('First 10 seconds (mV, 12.5uV/LSB, baseline subtracted)')
ax3.set_ylabel('mV')
ax3.set_xlabel('Time (s)')
ax3.legend(fontsize=8)
ax3.grid(True, alpha=0.3)

# Panel 4: frequency spectrum
ax4 = fig.add_subplot(4, 1, 4)
from numpy.fft import rfft, rfftfreq
N_fft = len(s)
freqs = rfftfreq(N_fft, d=1/SR)
fft_mag = np.abs(rfft(s - s.mean()))
# plot 0-30 Hz
mask = freqs <= 30
ax4.semilogy(freqs[mask], fft_mag[mask], lw=0.7, color='purple')
ax4.axvspan(0.8, 3.0, alpha=0.15, color='green', label='Expected HR range (48-180 bpm)')
ax4.set_xlabel('Frequency (Hz)')
ax4.set_ylabel('Magnitude (log)')
ax4.set_title('FFT Spectrum - HR peak should appear at 0.8-3 Hz if correct ECG')
ax4.legend(fontsize=8)
ax4.grid(True, alpha=0.3)

plt.tight_layout()
out = 'C:/Users/TSIC/Documents/GitHub/Heart/ecg_analysis.png'
plt.savefig(out, dpi=130, bbox_inches='tight')
print(f'\nSaved: {out}')
