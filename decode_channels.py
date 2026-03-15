import struct, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt

filepath = 'C:/Users/TSIC/Documents/GitHub/Heart/flash.dat'
with open(filepath, 'rb') as f:
    data = f.read()

BLOCK_SIZE = 512
DATA_OFFSET = 10
TAIL_BYTES = 4
BYTES_PER_BLOCK = BLOCK_SIZE - DATA_OFFSET - TAIL_BYTES  # 498
SR = 180

def extract_raw(start_block, num_blocks):
    raw = bytearray()
    for bi in range(start_block, start_block + num_blocks):
        off = bi * BLOCK_SIZE + DATA_OFFSET
        raw.extend(data[off:off + BYTES_PER_BLOCK])
    return bytes(raw)

def decode_12bit_le(raw_bytes):
    s = []
    for i in range(0, len(raw_bytes)-2, 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        s.append(b0 | ((b1 & 0xF) << 8))
        s.append((b1 >> 4) | (b2 << 4))
    return np.array(s, dtype=np.float32)

def bandpass(x, fs, lo=0.5, hi=40):
    b, a = butter(4, [lo/(fs/2), hi/(fs/2)], btype='band')
    return filtfilt(b, a, x)

# Use a section 5 minutes into the recording for stable signal
# 5min * 60s * 180Hz = 54000 samples = 54000/332 ≈ 163 blocks
START = 3 + 163
N_BLOCKS = 120   # ~60s worth

raw = extract_raw(START, N_BLOCKS)
s_all = decode_12bit_le(raw)

# Strategy 1: single channel (all samples)
ch_single = s_all
# Strategy 2: interleaved 2-channel (odd/even)
ch1 = s_all[0::2]   # even idx
ch2 = s_all[1::2]   # odd idx
# Strategy 3: every 3rd sample (3-channel view)
ch_a = s_all[0::3]
ch_b = s_all[1::3]
ch_c = s_all[2::3]

def to_mv(x):
    return (x - np.median(x)) * 12.5 / 1000.0  # mV

# Filter each  (for 2-channel, effective SR is SR/2 = 90 Hz)
SR2 = SR / 2

fig, axes = plt.subplots(5, 1, figsize=(20, 18))
fig.suptitle('DR200 Lead Analysis (12-bit LE, 5min into recording)\nOption B decoding', fontsize=13)

# Panel 1: full single-channel, filtered
N10 = 10 * SR
t1 = np.arange(N10) / SR
sig = to_mv(ch_single[:N10])
sig_f = bandpass(sig, SR)
axes[0].plot(t1, sig_f, lw=0.5, color='navy')
axes[0].set_title('Single-channel (all samples), bandpass 0.5–40 Hz @ 180 Hz')
axes[0].set_ylabel('mV')
axes[0].grid(True, alpha=0.3)

# Panel 2&3: split even/odd
N10_2 = 10 * int(SR2)
t2 = np.arange(N10_2) / SR2
for ax, ch, label, color in [
    (axes[1], ch1, 'Ch1 (even idx), bandpass @ 90 Hz', 'steelblue'),
    (axes[2], ch2, 'Ch2 (odd idx),  bandpass @ 90 Hz', 'firebrick'),
]:
    sig = to_mv(ch[:N10_2])
    sig_f = bandpass(sig, SR2)
    ax.plot(t2, sig_f, lw=0.5, color=color)
    ax.set_title(label)
    ax.set_ylabel('mV')
    ax.grid(True, alpha=0.3)
    rng = sig_f.max() - sig_f.min()
    ax.text(0.98, 0.95, f'p-p: {rng:.2f} mV', transform=ax.transAxes,
            ha='right', va='top', fontsize=9)

# Panel 4: zoom on Ch1, 3 seconds
N3 = 3 * int(SR2)
t3 = np.arange(N3) / SR2
sig_ch1 = to_mv(ch1[:N3])
sig_ch1_f = bandpass(sig_ch1, SR2)
axes[3].plot(t3, sig_ch1_f, lw=0.7, color='steelblue', marker='o', markersize=2)
axes[3].set_title('Ch1 zoom (3 sec) - checking for P/QRS/T morphology')
axes[3].set_ylabel('mV')
axes[3].grid(True, alpha=0.3)

# Panel 5: FFT of single channel to check HR frequency
from numpy.fft import rfft, rfftfreq
N_fft = min(len(ch_single), 32*1024)
freqs = rfftfreq(N_fft, d=1/SR)
fft_mag = np.abs(rfft(ch_single[:N_fft] - np.mean(ch_single[:N_fft])))
axes[4].semilogy(freqs[:int(len(freqs)*60/SR)+1], fft_mag[:int(len(freqs)*60/SR)+1], lw=0.7)
axes[4].set_xlim(0, 60)
axes[4].set_xlabel('Frequency (Hz)')
axes[4].set_title('FFT spectrum (0–60 Hz) - should see HR peak ~1-2 Hz if correct decode')
axes[4].grid(True, alpha=0.3)
# Mark expected HR range
axes[4].axvspan(0.8, 2.5, alpha=0.2, color='green', label='Typical HR 0.8–2.5 Hz')
axes[4].legend(fontsize=9)

for ax in axes:
    ax.set_xlabel('Time (s)')

plt.tight_layout()
out = 'C:/Users/TSIC/Documents/GitHub/Heart/channel_analysis.png'
plt.savefig(out, dpi=120, bbox_inches='tight')
print(f'Saved: {out}')

# Quick report
print(f'Single channel: {len(s_all)} samples, {len(s_all)/SR:.1f} sec')
print(f'Ch1 pp range (filtered): {(to_mv(ch1[:N10_2])).std()*12:.2f} mV (12σ)')
print(f'Ch2 pp range (filtered): {(to_mv(ch2[:N10_2])).std()*12:.2f} mV (12σ)')
