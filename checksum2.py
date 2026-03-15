import struct, numpy as np

path = 'C:/Users/TSIC/Documents/GitHub/Heart/233.dat'
with open(path, 'rb') as f:
    data = f.read()

block3 = data[3*512:4*512]
stored = struct.unpack_from('<I', block3, 508)[0]
raw = block3[10:508]   # 498 bytes of sample data

print(f'Stored value: 0x{stored:08x} = {stored}')
print(f'Raw bytes (first 12): {raw[:12].hex()}')
print()

# What if the firmware uses BIG-ENDIAN 12-bit packing?
# S1 = (B0 << 4) | (B1 >> 4)
# S2 = ((B1 & 0xF) << 8) | B2
def decode_be(raw):
    s = []
    for i in range(0, len(raw)-2, 3):
        b0, b1, b2 = raw[i], raw[i+1], raw[i+2]
        s.append((b0 << 4) | (b1 >> 4))
        s.append(((b1 & 0xF) << 8) | b2)
    return np.array(s)

def decode_le(raw):
    s = []
    for i in range(0, len(raw)-2, 3):
        b0, b1, b2 = raw[i], raw[i+1], raw[i+2]
        s.append(b0 | ((b1 & 0xF) << 8))
        s.append((b1 >> 4) | (b2 << 4))
    return np.array(s)

sle = decode_le(raw)
sbe = decode_be(raw)

print(f'LE samples: n={len(sle)}, sum={sle.sum()}, mean={sle.mean():.1f}')
print(f'BE samples: n={len(sbe)}, sum={sbe.sum()}, mean={sbe.mean():.1f}')
print(f'  BE sum == stored? {sbe.sum() == stored}')
print()

# Try just summing ODD or EVEN indexed samples
print('Partial sum tests:')
print(f'  sum(sle[0::2]) = {sle[0::2].sum()} (every S1)')
print(f'  sum(sle[1::2]) = {sle[1::2].sum()} (every S2)')
print(f'  sum(sbe[0::2]) = {sbe[0::2].sum()}')
print(f'  sum(sbe[1::2]) = {sbe[1::2].sum()}')
print()

# What about sum of raw BYTES (unsigned)?
raw_bytes = np.frombuffer(raw, dtype=np.uint8)
print(f'Sum of raw bytes [10:508]: {raw_bytes.sum()}')
print()

# Sum of raw uint16 LE over 498 bytes (249 pairs)
u16 = np.frombuffer(raw[:498], dtype=np.uint16)
print(f'Sum of uint16 LE ({len(u16)} values): {u16.sum()}')
u16be = np.frombuffer(raw[:498], dtype='>u2')
print(f'Sum of uint16 BE ({len(u16be)} values): {u16be.sum()}')
print()

# What if the "checksum" is actually the counter from NEXT block?
# i.e., it's not a checksum but the SAMPLE INDEX of first sample in NEXT block?
# block 3 has 332 samples, so first sample in block 4 = 332
# But stored = 269174... not 332.

# What if stored[508:512] contains TWO 16-bit values?
lo16 = struct.unpack_from('<H', block3, 508)[0]
hi16 = struct.unpack_from('<H', block3, 510)[0]
print(f'bytes 508-509 as uint16 LE: 0x{lo16:04x} = {lo16}')
print(f'bytes 510-511 as uint16 LE: 0x{hi16:04x} = {hi16}')
print()

# Cross-block analysis: look at stored values vs block index
print('Block-by-block stored values:')
for bi in range(3, 20):
    off = bi * 512
    bd = data[off+10:off+508]
    if sum(bd) == 0:
        break
    v = struct.unpack_from('<I', data, off+508)[0]
    sle_i = decode_le(bd)
    sbe_i = decode_be(bd)
    lo = struct.unpack_from('<H', data, off+508)[0]
    hi = struct.unpack_from('<H', data, off+510)[0]
    print(f'  block{bi:3d}: stored=0x{v:08x}={v:7d}  LE_sum={sle_i.sum():7d}  BE_sum={sbe_i.sum():7d}  lo16={lo:5d} hi16={hi:5d}')

print()

# Hypothesis: stored value = sum of S1 (even-indexed LE samples) only?
# Let's check the ratio
print('Ratio analysis:')
for bi in range(3, 10):
    off = bi * 512
    bd = data[off+10:off+508]
    if sum(bd) == 0:
        break
    v = struct.unpack_from('<I', data, off+508)[0]
    sle_i = decode_le(bd)
    ratio = v / sle_i.sum() if sle_i.sum() > 0 else 0
    s1_sum = int(sle_i[0::2].sum())
    s2_sum = int(sle_i[1::2].sum())
    print(f'  block{bi}: stored={v}, LE_sum={sle_i.sum()}, ratio={ratio:.4f}, S1_sum={s1_sum}, S2_sum={s2_sum}')

print()
# Check if stored value has any relation to the counter in bytes 6-9
print('Counter (bytes 6-9) vs stored (bytes 508-511):')
for bi in range(3, 10):
    off = bi * 512
    bd = data[off+10:off+508]
    if sum(bd) == 0:
        break
    v = struct.unpack_from('<I', data, off+508)[0]
    ctr = struct.unpack_from('<I', data, off+6)[0]
    print(f'  block{bi}: counter={ctr}, stored={v}, diff={v-ctr}, ratio={v/ctr:.4f}')
