import struct, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt

filepath = 'C:/Users/TSIC/Documents/GitHub/Heart/flash.dat'
with open(filepath, 'rb') as f:
    data = f.read()

BLOCK_SIZE = 512
DATA_OFFSET = 10
BYTES_PER_BLOCK = 498
SR = 180
LAST_BLOCK = 148

def decode_12bit_le(raw_bytes):
    s = []
    for i in range(0, len(raw_bytes)-2, 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        s.append(b0 | ((b1 & 0xF) << 8))
        s.append((b1 >> 4) | (b2 << 4))
    return s

# Decode all blocks
raw_all = bytearray()
for bi in range(3, LAST_BLOCK+1):
    off = bi * BLOCK_SIZE + DATA_OFFSET
    raw_all.extend(data[off:off+BYTES_PER_BLOCK])
s = np.array(decode_12bit_le(bytes(raw_all)), dtype=np.float32)
t = np.arange(len(s)) / SR

print(f'Decoded {len(s)} samples, {len(s)/SR:.1f}s')

# --- Hypothesis 1: Signed 12-bit, center at 2048 ---
s_signed = s.copy()
s_signed[s_signed >= 2048] -= 4096  # convert to signed

# --- Hypothesis 2: Differential/delta encoding ---
# First value is absolute, rest are deltas
s_delta = np.cumsum(s_signed)

# --- Hypothesis 3: Only channel 1 (even samples) ---
s_ch1 = s[0::2]   # first of each pair

# --- Hypothesis 4: Only channel 2 (odd samples) ---
s_ch2 = s[1::2]

# --- Hypothesis 5: Raw bytes as uint8 stream directly ---
raw_u8 = np.frombuffer(bytes(raw_all), dtype=np.uint8).astype(np.float32)

# Plot comparison using 30-60s window (after startup artifacts)
start_s = 30
end_s = 60
i0 = int(start_s * SR)
i1 = int(end_s * SR)
i0_2 = i0 // 2
i1_2 = i1 // 2

def lpf(x, cutoff=40, fs=SR):
    b, a = butter(4, cutoff/(fs/2), btype='low')
    return filtfilt(b, a, x)

def bpf(x, lo=0.5, hi=40, fs=SR):
    b, a = butter(3, [lo/(fs/2), hi/(fs/2)], btype='band')
    return filtfilt(b, a, x)

fig, axes = plt.subplots(5, 1, figsize=(22, 20))
fig.suptitle('DR200 Decode Hypotheses Test (t=30-60s window)', fontsize=12)

# H1: signed 12-bit
x1 = s_signed[i0:i1]
axes[0].plot(t[i0:i1], bpf(x1), lw=0.6, color='navy')
axes[0].set_title(f'H1: Signed 12-bit, bandpass 0.5-40Hz | range {x1.min():.0f} to {x1.max():.0f} cnt = {(x1.max()-x1.min())*12.5/1000:.1f} mV pp')
axes[0].set_ylabel('counts')
axes[0].grid(True, alpha=0.3)

# H2: differential (signed) - show 5 seconds only (cumsum grows quickly)
x2 = s_signed[:5*SR]
x2_cum = np.cumsum(x2 - x2.mean())
t2 = np.arange(len(x2)) / SR
axes[1].plot(t2, x2_cum, lw=0.6, color='darkgreen')
axes[1].set_title(f'H2: Delta/cumsum of signed (first 5s) | shows if differential encoding')
axes[1].set_ylabel('cumsum')
axes[1].grid(True, alpha=0.3)

# H3: Ch1 (even samples at 90Hz effective)
t3 = np.arange(i0_2, i1_2) / (SR/2)
x3 = s_ch1[i0_2:i1_2] - np.median(s_ch1)
b3, a3 = butter(3, [0.5/(SR/4), 40/(SR/4)], btype='band')
x3f = filtfilt(b3, a3, x3)
axes[2].plot(t3, x3f, lw=0.6, color='firebrick')
axes[2].set_title(f'H3: Ch1 only (even idx, 90Hz), bandpass | pp={x3.max()-x3.min():.0f} cnt = {(x3.max()-x3.min())*12.5/1000:.1f} mV')
axes[2].set_ylabel('counts (DC removed)')
axes[2].grid(True, alpha=0.3)

# H4: Raw uint8 bytes
ib0 = i0 * 3 // 2
ib1 = i1 * 3 // 2
t4 = np.arange(ib0, ib1) / SR
x4 = raw_u8[ib0:ib1] - np.median(raw_u8[ib0:ib1])
axes[3].plot(t4, x4, lw=0.5, color='darkorange')
axes[3].set_title('H5: Raw uint8 stream (no decoding) - see if raw bytes show ECG pattern')
axes[3].set_ylabel('uint8 value (DC removed)')
axes[3].grid(True, alpha=0.3)

# H5: looking at specific byte positions (every 3rd byte starting at 0, 1, 2)
for start_byte, color, label in [(0, 'blue', 'B0'), (1, 'green', 'B1'), (2, 'red', 'B2')]:
    chunk = raw_u8[start_byte::3]
    ic0, ic1 = ib0//3, ib1//3
    axes[4].plot(np.arange(ic0, min(ic1, len(chunk)))/90, 
                chunk[ic0:ic1] - np.median(chunk[ic0:ic1]), 
                lw=0.5, color=color, alpha=0.7, label=label)
axes[4].legend(fontsize=9)
axes[4].set_title('H6: Each byte position in triplet separately (B0, B1, B2) at 90Hz')
axes[4].set_ylabel('uint8 (DC removed)')
axes[4].set_xlabel('Time (s)')
axes[4].grid(True, alpha=0.3)

for ax in axes[:-1]:
    ax.set_xlabel('Time (s)')

plt.tight_layout()
out = 'C:/Users/TSIC/Documents/GitHub/Heart/hypotheses.png'
plt.savefig(out, dpi=120, bbox_inches='tight')
print(f'Saved: {out}')

# Stats
print(f'\nSigned 12-bit stats:')
print(f'  min={s_signed.min():.0f}, max={s_signed.max():.0f}, std={s_signed.std():.1f}')
print(f'  std in mV: {s_signed.std()*12.5/1000:.2f} mV')
print(f'\nUnique count of s_signed: {len(np.unique(s_signed))}')
