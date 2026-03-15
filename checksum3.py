import struct, numpy as np

path = 'C:/Users/TSIC/Documents/GitHub/Heart/233.dat'
with open(path, 'rb') as f:
    data = f.read()

# Hex dump of first data block (block 3)
print('=== Block 3 full hex dump (512 bytes) ===')
block3 = data[3*512:4*512]
for row in range(0, 512, 16):
    hex_part = ' '.join(f'{b:02x}' for b in block3[row:row+16])
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in block3[row:row+16])
    print(f'  {row:03x}: {hex_part:<48}  {asc_part}')

print()

# Look at a block that has REAL data (not all lead-off)
# Scan for first block with non-lead-off samples
print('=== Scanning for blocks with real ECG data ===')
for bi in range(3, 60):
    off = bi * 512
    bd = data[off+10:off+508]
    non77 = sum(1 for b in bd if b != 0x77)
    if non77 > 0:
        v = struct.unpack_from('<I', data, off+508)[0]
        print(f'  Block {bi}: {non77} non-0x77 bytes out of 498, stored=0x{v:08x}={v}')
        # Hex dump of header + first/last bytes
        blk = data[off:off+512]
        print(f'    Header:  {blk[:10].hex()}')
        print(f'    Data[0:9]:  {blk[10:20].hex()}')
        print(f'    Data[-10:]: {blk[498:508].hex()}')
        print(f'    Tail:    {blk[508:512].hex()}')
        print()
        if non77 > 200:
            break

print()
# What if bytes 508-511 aren't "checksum" but rather CUMULATIVE SAMPLE SUM
# where samples are encoded DIFFERENTLY?
# Let's decode block 3 samples and see their actual values
block3 = data[3*512:4*512]
raw = block3[10:508]
print('=== Sample values in block 3 (first 20 and last 20) ===')
samples = []
for i in range(0, len(raw)-2, 3):
    b0, b1, b2 = raw[i], raw[i+1], raw[i+2]
    s1 = b0 | ((b1 & 0xF) << 8)
    s2 = (b1 >> 4) | (b2 << 4)
    samples.extend([s1, s2])

print(f'Total samples: {len(samples)}')
print(f'First 20: {samples[:20]}')
print(f'Last 20:  {samples[-20:]}')
print(f'Non-lead-off count (!=1911): {sum(1 for s in samples if s != 1911)}')
print(f'Lead-off count (==1911):     {sum(1 for s in samples if s == 1911)}')
non_lo = [s for s in samples if s != 1911]
if non_lo:
    print(f'Non-lead-off values: min={min(non_lo)}, max={max(non_lo)}, mean={np.mean(non_lo):.1f}')
    print(f'Sum of non-lead-off: {sum(non_lo)}')
    print(f'Sum of ALL:          {sum(samples)}')

stored = struct.unpack_from('<I', block3, 508)[0]
print(f'Stored: {stored}')
print()

# Check if stored = sum of samples that are NOT 1911 plus n*1911/something
# Or perhaps the firmware uses a DIFFERENT lead-off code in the checksum?

# New hypothesis: stored = SUM of min(sample, 1023) or sum of (sample & 0x3FF)?
test_trunc = sum(s & 0x3FF for s in samples)
test_hi4 = sum(s >> 8 for s in samples)
test_lo8 = sum(s & 0xFF for s in samples)
test_raw_bytes = sum(raw)
print('Alternative sum tests on block 3:')
print(f'  sum(s & 0x3FF):  {test_trunc}  match={stored == test_trunc}')
print(f'  sum(s >> 8):     {test_hi4}   match={stored == test_hi4}')
print(f'  sum(s & 0xFF):   {test_lo8}   match={stored == test_lo8}')
print(f'  sum(raw_bytes):  {test_raw_bytes}  match={stored == test_raw_bytes}')
print()

# The big question: what if stored is NOT related to current block content at all?
# But rather it's a CUMULATIVE counter across all previous blocks?
# Like: stored in block N = sum of all sample values from block 3 to block N?
cumsum = 0
print('Cumulative sample sum test:')
for bi in range(3, 15):
    off = bi * 512
    bd = data[off+10:off+508]
    if sum(bd) == 0:
        break
    samps = []
    for i in range(0, len(bd)-2, 3):
        b0, b1, b2 = bd[i], bd[i+1], bd[i+2]
        samps.append(b0 | ((b1 & 0xF) << 8))
        samps.append((b1 >> 4) | (b2 << 4))
    cumsum += sum(samps)
    v = struct.unpack_from('<I', data, off+508)[0]
    print(f'  Block {bi}: block_sum={sum(samps):7d}  cumsum={cumsum:9d}  stored={v:7d}  match={v==cumsum}')

print()
# What if the 4 bytes at end ARE raw sample data (overflow from 498 bytes)?
# 498 = 3*166, so 498 bytes = 166 pairs = 332 samples. Exact fit. No overflow.
# BUT: what if data starts at offset 6 (not 10)?
# bytes 6-9 = counter, if those ARE actually sample data:
# Then sample data = bytes[6:508] = 502 bytes / 3 = 167.33... not exact
# bytes[4:508] = 504 / 3 = 168 pairs = 336 samples. Let's try:
print('What if sample data starts at offset 4? (bytes[4:508], 504 bytes, 336 samples)')
raw4 = block3[4:508]
samps4 = []
for i in range(0, len(raw4)-2, 3):
    b0, b1, b2 = raw4[i], raw4[i+1], raw4[i+2]
    samps4.append(b0 | ((b1 & 0xF) << 8))
    samps4.append((b1 >> 4) | (b2 << 4))
print(f'  n={len(samps4)}, sum={sum(samps4)}, stored={stored}, match={stored==sum(samps4)}')

print()
# What if it's bytes[0:508]?
raw0 = block3[0:508]
samps0 = []
for i in range(0, len(raw0)-2, 3):
    b0, b1, b2 = raw0[i], raw0[i+1], raw0[i+2]
    samps0.append(b0 | ((b1 & 0xF) << 8))
    samps0.append((b1 >> 4) | (b2 << 4))
print(f'Decode[0:508]: n={len(samps0)}, sum={sum(samps0)}, stored={stored}, match={stored==sum(samps0)}')

# Look at a different block with all real data - find one with no 0x77 bytes
print()
print('=== Find a block with ZERO lead-off samples ===')
for bi in range(3, 60):
    off = bi * 512
    bd = data[off+10:off+508]
    n77 = sum(1 for b in bd if b == 0x77)
    if n77 == 0 and sum(bd) > 0:
        v = struct.unpack_from('<I', data, off+508)[0]
        samps = []
        for i in range(0, len(bd)-2, 3):
            b0, b1, b2 = bd[i], bd[i+1], bd[i+2]
            samps.append(b0 | ((b1 & 0xF) << 8))
            samps.append((b1 >> 4) | (b2 << 4))
        s_sum = sum(samps)
        print(f'Block {bi}: n77=0, sum={s_sum}, stored={v}, diff={v-s_sum}, ratio={v/s_sum:.4f}')
        print(f'  First 20 samples: {samps[:20]}')
        print(f'  Mean: {np.mean(samps):.1f}')
        print(f'  stored/332: {v/332:.1f}')
        print(f'  (stored - 332*800): {v - 332*800}')
        print(f'  sum - stored: {s_sum - v}')
        if bi >= 7:
            break
