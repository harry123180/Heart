import struct, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

filepath = 'C:/Users/TSIC/Documents/GitHub/Heart/flash.dat'
with open(filepath, 'rb') as f:
    data = f.read()

BLOCK_SIZE = 512
HEADER_BLOCKS = 3       # blocks 0,1,2 = config
DATA_OFFSET = 10        # bytes into each block before samples start
TAIL_BYTES = 4          # checksum at end
BYTES_PER_BLOCK = BLOCK_SIZE - DATA_OFFSET - TAIL_BYTES  # = 498
SAMPLE_RATE = 180

def decode_12bit_le(raw_bytes):
    """12-bit packed, little-endian nibbles (Option B):
       S1 = B0 | ((B1 & 0xF) << 8)
       S2 = (B1 >> 4) | (B2 << 4)
    """
    samples = []
    for i in range(0, len(raw_bytes)-2, 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        s1 = b0 | ((b1 & 0xF) << 8)
        s2 = (b1 >> 4) | (b2 << 4)
        samples.extend([s1, s2])
    return np.array(samples, dtype=np.int16)

def decode_12bit_be(raw_bytes):
    """12-bit packed, big-endian nibbles (Option A):
       S1 = (B0 << 4) | (B1 >> 4)
       S2 = ((B1 & 0xF) << 8) | B2
    """
    samples = []
    for i in range(0, len(raw_bytes)-2, 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        s1 = (b0 << 4) | (b1 >> 4)
        s2 = ((b1 & 0xF) << 8) | b2
        samples.extend([s1, s2])
    return np.array(samples, dtype=np.int16)

def decode_int16_le(raw_bytes):
    """Plain 16-bit little-endian"""
    n = len(raw_bytes) // 2
    return np.array(struct.unpack_from(f'<{n}h', raw_bytes[:n*2]))

def extract_blocks(start_block, num_blocks):
    raw = bytearray()
    for bi in range(start_block, start_block + num_blocks):
        offset = bi * BLOCK_SIZE + DATA_OFFSET
        raw.extend(data[offset:offset + BYTES_PER_BLOCK])
    return bytes(raw)

# Extract from early recording (skip first 60 seconds of potential startup artifacts)
# 180 Hz x 60 sec / 332 samples per block ≈ 32 blocks to skip
START_BLOCK = HEADER_BLOCKS + 32   # ~60 sec in
NUM_BLOCKS = 60                    # ~30 sec of data (depending on format)

raw = extract_blocks(START_BLOCK, NUM_BLOCKS)

s_le = decode_12bit_le(raw)
s_be = decode_12bit_be(raw)
s16  = decode_int16_le(raw)

# Clip to first 10s for each (number of samples depends on decode)
N_LE = min(len(s_le), 10 * SAMPLE_RATE)
N_BE = min(len(s_be), 10 * SAMPLE_RATE)
N_16 = min(len(s16),  10 * SAMPLE_RATE)

t_le = np.arange(N_LE) / SAMPLE_RATE
t_be = np.arange(N_BE) / SAMPLE_RATE
t_16 = np.arange(N_16) / SAMPLE_RATE

fig, axes = plt.subplots(3, 1, figsize=(18, 12))
fig.suptitle('DR200 ECG Decode Comparison\n(Block 35+, ~60s into recording)', fontsize=14)

# subtract median to remove DC offset for visualization
for ax, t, s, title in [
    (axes[0], t_le, s_le[:N_LE], 'Option B: 12-bit LE nibble packed (S1=B0|((B1&0xF)<<8), S2=(B1>>4)|(B2<<4))'),
    (axes[1], t_be, s_be[:N_BE], 'Option A: 12-bit BE nibble packed (S1=(B0<<4)|(B1>>4), S2=((B1&0xF)<<8)|B2)'),
    (axes[2], t_16, s16[:N_16],  'Raw int16 LE (249 samples/block)'),
]:
    s_centered = s - np.median(s)
    ax.plot(t, s_centered, linewidth=0.6, color='steelblue')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('ADC counts (DC removed)')
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, t[-1])
    # Show amplitude range info
    ax.text(0.02, 0.95, f'Range: {s_centered.min():.0f} to {s_centered.max():.0f} counts  '
            f'({s_centered.min()*12.5/1000:.2f} to {s_centered.max()*12.5/1000:.2f} mV)',
            transform=ax.transAxes, fontsize=9, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
out = 'C:/Users/TSIC/Documents/GitHub/Heart/decode_comparison.png'
plt.savefig(out, dpi=120, bbox_inches='tight')
print(f'Saved: {out}')

# Also print stats for option B
print(f'\nOption B stats (first 10s): min={s_le[:N_LE].min()}, max={s_le[:N_LE].max()}, '
      f'median={np.median(s_le[:N_LE]):.1f}, std={s_le[:N_LE].std():.1f}')
print(f'Option A stats: min={s_be[:N_BE].min()}, max={s_be[:N_BE].max()}, median={np.median(s_be[:N_BE]):.1f}')
print(f'int16 LE stats: min={s16[:N_16].min()}, max={s16[:N_16].max()}, median={np.median(s16[:N_16]):.1f}')
