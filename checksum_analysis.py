import struct, numpy as np, binascii

path = 'C:/Users/TSIC/Documents/GitHub/Heart/233.dat'
with open(path, 'rb') as f:
    data = f.read()

block3 = data[3*512:4*512]
stored = struct.unpack_from('<I', block3, 508)[0]
print(f'Stored checksum (233.dat block3): 0x{stored:08x} = {stored}')

# Decode 12-bit samples
def decode_samples(raw):
    s = []
    for i in range(0, len(raw)-2, 3):
        b0, b1, b2 = raw[i], raw[i+1], raw[i+2]
        s.append(b0 | ((b1 & 0xF) << 8))
        s.append((b1 >> 4) | (b2 << 4))
    return np.array(s)

raw = block3[10:508]
samples = decode_samples(raw)
s_sum = int(samples.sum())
print(f'Sum of decoded 12-bit samples: {s_sum} = 0x{s_sum:08x}  match={stored==s_sum}')
print()

# Range analysis across all blocks
print('Checksum range analysis:')
vals = []
s_sums = []
for bi in range(3, 60):
    off = bi * 512
    bd = data[off+10:off+508]
    if sum(bd) > 0:
        v = struct.unpack_from('<I', data, off+508)[0]
        vals.append(v)
        s = decode_samples(bd)
        s_sums.append(int(s.sum()))

vals = np.array(vals)
s_sums = np.array(s_sums)
diffs = vals - s_sums
print(f'  Stored values:   min=0x{vals.min():08x} max=0x{vals.max():08x}')
print(f'  Sample sums:     min=0x{s_sums.min():08x} max=0x{s_sums.max():08x}')
print(f'  stored - sample_sum diffs: {diffs[:8].tolist()}')
print(f'  Are all diffs equal? {len(set(diffs.tolist())) == 1}')
print(f'  Diff range: min={diffs.min()} max={diffs.max()}')
print()

# Try various CRC variants
print('CRC variants on block3:')
for start, end, label in [(0,508,'[0:508]'), (4,508,'[4:508]'), (10,508,'[10:508]'),
                           (0,512,'[0:512]'), (6,508,'[6:508]')]:
    crc = binascii.crc32(block3[start:end]) & 0xFFFFFFFF
    print(f'  CRC32{label}: 0x{crc:08x}  match={stored==crc}')

# Try CRC16 stored as 32-bit
import struct
for start, end, label in [(0,508,'[0:508]'), (10,508,'[10:508]')]:
    # Pure Python CRC16
    crc = 0xFFFF
    for b in block3[start:end]:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    print(f'  CRC16{label}: 0x{crc:08x}  match={stored==crc}')

print()
# Key observation: stored values cluster around 250k-270k
# 332 samples * median(~780) = 259,000 ≈ 0x3F000
# This suggests SUM of raw decoded samples IS the checksum
# Let's check with flash.dat
print('=== flash.dat cross-check ===')
with open('C:/Users/TSIC/Documents/GitHub/Heart/flash.dat', 'rb') as f:
    data2 = f.read()
for bi in range(3, 8):
    off = bi * 512
    stored2 = struct.unpack_from('<I', data2, off+508)[0]
    raw2 = data2[off+10:off+508]
    s2 = decode_samples(raw2)
    s2_sum = int(s2.sum())
    diff2 = stored2 - s2_sum
    print(f'  Block {bi}: stored=0x{stored2:08x}  sample_sum=0x{s2_sum:08x}  diff={diff2}')

print()
# Insight on counter bytes 6-9
print('=== Counter analysis deep dive ===')
# Counter starts at 1212, increments 1216 per block
# Note: 1212 = 1216 - 4
# And 1216 = 512 + 704
# What is 704? 704 = 512 + 192 = 512 + 192...
# OR: 1216 / 180 = 6.755... not clean
# BUT: 1216 * 180 = 218880 bytes/sec...
# Wait: think in samples
# 332 samples/block * ? = 1216
# 1216/332 = 3.662...
# What if unit is 1/(180*something)?
#
# NEW IDEA: check if counter = cumulative byte offset in the SAMPLE DATA stream
# (ignoring block headers)
# Block 3 data: 498 bytes, counter starts at 1212
# Bytes before block 3 data: config text
# Config block 0 has ~340 bytes of text content
# But counter[0] = 1212, not 340
#
# ANOTHER NEW IDEA: counter = cumulative 12-bit SAMPLE INDEX * 4 / 3?
# 332 samples * 4/3 = 442.67... not 1216
#
# Wait: 1216 = 332 samples * (12/4 + 1/4)?
#
# Let me check: does counter = block_number * 1216 + (1212 - 3*1216)?
# 1212 - 3*1216 = 1212 - 3648 = -2436... negative, so NO
#
# What if the 3 config blocks ALSO have a counter, just not read by us?
# Config block 0 would have counter at offset 6
for bi in range(3):
    cnt = struct.unpack_from('<I', data, bi*512+6)[0]
    sub = struct.unpack_from('<H', data, bi*512+4)[0]
    print(f'  Config block {bi}: sub=0x{sub:04x}, bytes6-9={data[bi*512+6:bi*512+10].hex()}, counter={cnt}')

# Check: is 1212 = 3 * 404?
# And does each config block have counter that's related to its content size?
print(f'  1212 / 3 = {1212/3} (= 404 per config block?)')
print(f'  404 / 4 = {404/4}   (101 units of 4 bytes?)')
print(f'  1216 / 4 = {1216//4} (304 units of 4 bytes per data block)')
print(f'  498 bytes data / (4/3 bytes per sample unit) = {498 * 3/4:.1f}')
print(f'  498 * (1216/498) = {498 * 1216/498:.1f} = 1216 (trivially true)')
print()
print('Conclusion: counter is likely firmware-internal write counter,')
print('unit = 4 bytes (32-bit words). Each data block writes 304 words of sample data.')
print(f'304 words * 4 bytes = {304*4} bytes (vs 498 available... 498-1216/4*4={498-304*4})')
print(f'Actually 1216 / 4 = 304 words, but 304 * 1.5 bytes/sample (12-bit) = {304*1.5} samples')
print(f'But we have 332 samples per block... diff = {332-304*1.5}')
