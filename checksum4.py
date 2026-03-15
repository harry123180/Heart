import struct, numpy as np

path = 'C:/Users/TSIC/Documents/GitHub/Heart/233.dat'
with open(path, 'rb') as f:
    data = f.read()

# Key finding: data blocks have embedded ASCII diary events
# Let's find where diary events start in each block and separate ECG from diary
# Also: try folded sums and multi-byte sums

def folded_sum(raw, bits=16):
    """Fold a 32-bit sum into N bits (like Fletcher or Adler)"""
    s = sum(raw)
    mask = (1 << bits) - 1
    return (s & mask) + (s >> bits)

print('=== Diary event detection in blocks ===')
print('Looking for ASCII printable regions near block end')
for bi in [3, 4, 8, 13, 18]:
    off = bi * 512
    bd = data[off+10:off+508]
    v = struct.unpack_from('<I', data, off+508)[0]
    # Find last run of printable ASCII
    last_ascii_end = 0
    for i in range(len(bd)-1, -1, -1):
        b = bd[i]
        if 32 <= b <= 126 or b in (0x0a, 0x0d, 0x00):
            last_ascii_end = i
            break
    # Find start of that ASCII run
    start = last_ascii_end
    while start > 0 and (32 <= bd[start-1] <= 126 or bd[start-1] in (0x0a, 0x0d, 0x00)):
        start -= 1
    ascii_region = bd[start:last_ascii_end+1]
    pure_ecg = bd[:start]
    print(f'  Block {bi}: stored=0x{v:08x}')
    print(f'    ASCII region [{start}:{last_ascii_end+1}]: {bytes(ascii_region).decode("ascii","replace")!r}')
    print(f'    Pure ECG region: {len(pure_ecg)} bytes = {len(pure_ecg)*2//3} samples')
    pure_samps = []
    for i in range(0, len(pure_ecg)-2, 3):
        b0, b1, b2 = pure_ecg[i], pure_ecg[i+1], pure_ecg[i+2]
        pure_samps.append(b0 | ((b1 & 0xF) << 8))
        pure_samps.append((b1 >> 4) | (b2 << 4))
    if pure_samps:
        print(f'    Pure ECG sum: {sum(pure_samps)}, mean: {np.mean(pure_samps):.1f}')
    print()

print()
print('=== Systematic formula search ===')
block3 = data[3*512:4*512]
stored = struct.unpack_from('<I', block3, 508)[0]
raw = block3[10:508]  # 498 bytes

# Try various 32-bit fold combinations
results = []

# Add all bytes with different multiplicative factors
for factor in range(1, 8):
    s = sum(b * factor for b in raw) & 0xFFFFFFFF
    if s == stored:
        results.append(f'sum(b*{factor}) for b in raw[10:508]')

# Sum pairs of bytes as uint16 LE
for step in [2, 3, 4]:
    u = sum(struct.unpack_from('<H', raw, i)[0] for i in range(0, len(raw)-1, step))
    if u == stored:
        results.append(f'sum(uint16_LE) step={step}')

# Xor-folded sum
xf = 0
for b in raw:
    xf = ((xf << 8) | b) & 0xFFFFFFFF
if xf == stored:
    results.append('shift-accumulate XOR')

# Sum with byte position weighting
for i, b in enumerate(raw):
    pass  # too slow to test all weighting schemes

# Check: sum of raw bytes in HEADER + DATA (full 508 bytes)
all_508 = block3[:508]
for method_name, vals in [
    ('sum_bytes[0:508]', sum(all_508)),
    ('sum_bytes[4:508]', sum(block3[4:508])),
    ('sum_bytes_folded16', folded_sum(raw)),
    ('fletcher32_simplified', None),
]:
    if vals is not None and vals == stored:
        results.append(method_name)

# Fletcher-32 checksum
def fletcher32(data):
    s1, s2 = 0, 0
    for b in data:
        s1 = (s1 + b) % 65535
        s2 = (s2 + s1) % 65535
    return (s2 << 16) | s1

f32 = fletcher32(raw)
if f32 == stored:
    results.append('Fletcher32 of raw[10:508]')
f32_all = fletcher32(block3[:508])
if f32_all == stored:
    results.append('Fletcher32 of block3[0:508]')
f32_4 = fletcher32(block3[4:508])
if f32_4 == stored:
    results.append('Fletcher32 of block3[4:508]')

print(f'Stored: 0x{stored:08x} = {stored}')
print(f'Fletcher32 of [10:508]: 0x{f32:08x} = {f32}  match={f32==stored}')
print(f'Fletcher32 of [0:508]:  0x{f32_all:08x} = {f32_all}  match={f32_all==stored}')
print(f'Fletcher32 of [4:508]:  0x{f32_4:08x} = {f32_4}  match={f32_4==stored}')
print()

# Adler-32
def adler32(data):
    MOD_ADLER = 65521
    a, b = 1, 0
    for byte in data:
        a = (a + byte) % MOD_ADLER
        b = (b + a) % MOD_ADLER
    return (b << 16) | a

a32 = adler32(raw)
a32_all = adler32(block3[:508])
print(f'Adler32 of [10:508]: 0x{a32:08x} = {a32}  match={a32==stored}')
print(f'Adler32 of [0:508]:  0x{a32_all:08x} = {a32_all}  match={a32_all==stored}')
print()

# Try: What if it's a RUNNING (cumulative) sum of something from block 0?
# Or what if it's simply: number of flash bytes written / some_unit?
# bytes_written at end of block N = (N+1) * 512
# block 3: 4*512 = 2048 bytes. But stored=269174. Not that.

# What if there's a 32-bit "sample accumulator" that the firmware maintains
# and stores at each block boundary?
# Accumulator = sum of all samples ever written, modulo 2^32
cumulative_samples = 0
print('=== Cumulative sample accumulator (from recording start) ===')
for bi in range(3, 56):
    off = bi * 512
    bd = data[off+10:off+508]
    if sum(bd) == 0:
        break
    samps = []
    for i in range(0, len(bd)-2, 3):
        b0, b1, b2 = bd[i], bd[i+1], bd[i+2]
        samps.append(b0 | ((b1 & 0xF) << 8))
        samps.append((b1 >> 4) | (b2 << 4))
    cumulative_samples += sum(samps)
    v = struct.unpack_from('<I', data, off+508)[0]
    # Various transforms
    c32 = cumulative_samples & 0xFFFFFFFF
    c_div = (cumulative_samples // (bi-2)) if bi > 2 else cumulative_samples
    print(f'  Block {bi:2d}: stored={v:7d}  cumsum={cumulative_samples:9d}  cummod32={c32:9d}  block_sum={sum(samps):7d}')

print()
if results:
    print('MATCHES FOUND:', results)
else:
    print('NO formula match found for bytes 508-511.')
    print()
    print('CONCLUSION: Bytes 508-511 likely use a proprietary checksum algorithm.')
    print('The value consistently gives ~800 when divided by 332 (samples/block),')
    print('suggesting it relates to the MIDPOINT ADC level of the signal,')
    print('possibly the AVERAGE or MEDIAN sample value * 332.')
    print()
    # Final check: sum using the VALUES divided by 2 (to get ~800 from ~1600)
    sle = []
    for i in range(0, len(raw)-2, 3):
        b0, b1, b2 = raw[i], raw[i+1], raw[i+2]
        sle.append(b0 | ((b1 & 0xF) << 8))
        sle.append((b1 >> 4) | (b2 << 4))
    # Filter: exclude lead-off values
    non_lo = [s for s in sle if s != 0x777]
    lo_count = len(sle) - len(non_lo)
    print(f'Block 3: {lo_count} lead-off (1911), {len(non_lo)} real samples')
    print(f'Sum of real samples: {sum(non_lo)}')
    print(f'Sum of real/2: {sum(non_lo)//2}')
    # What if each 12-bit sample is compressed to 10 bits for checksum?
    s10 = sum(s >> 2 for s in sle)  # top 10 bits
    s10b = sum(s & 0x3FF for s in sle)  # bottom 10 bits
    print(f'Sum of (s>>2) [top 10 bits]: {s10}  match={s10==stored}')
    print(f'Sum of (s&0x3FF) [bot 10 bits]: {s10b}  match={s10b==stored}')
    # 12-bit to 8-bit: take only high byte
    s8hi = sum(s >> 4 for s in sle)  # upper 8 bits
    s8lo = sum(s & 0xFF for s in sle)  # lower 8 bits
    print(f'Sum of (s>>4) [top 8 bits]: {s8hi}  match={s8hi==stored}')
    print(f'Sum of (s&0xFF) [bot 8 bits]: {s8lo}  match={s8lo==stored}')

    # What if ONLY S1 (even samples, lower 12 bits of 3-byte group)?
    s1_vals = sle[0::2]
    s2_vals = sle[1::2]
    print(f'Sum S1 only: {sum(s1_vals)}, /166={sum(s1_vals)/166:.1f}  match={sum(s1_vals)==stored}')
    print(f'Sum S2 only: {sum(s2_vals)}, /166={sum(s2_vals)/166:.1f}  match={sum(s2_vals)==stored}')

    # What if stored = sum of JUST the first byte of each 3-byte triplet * some scale?
    b0s = [raw[i] for i in range(0, len(raw)-2, 3)]
    b1s = [raw[i+1] for i in range(0, len(raw)-2, 3)]
    b2s = [raw[i+2] for i in range(0, len(raw)-2, 3)]
    print(f'Sum of B0 bytes (*1): {sum(b0s)}, (*2): {sum(b0s)*2}, (*3): {sum(b0s)*3}')
    print(f'Sum of B2 bytes (*1): {sum(b2s)}, (*2): {sum(b2s)*2}, (*3): {sum(b2s)*3}')
    print(f'Sum of B0+B2 bytes: {sum(b0s)+sum(b2s)}  match={sum(b0s)+sum(b2s)==stored}')
    # B0 | B2<<8 (treating pairs as 16-bit)?
    b02_16 = sum(b0 | (b2<<8) for b0, b2 in zip(b0s, b2s))
    print(f'Sum of (B0|(B2<<8)): {b02_16}  match={b02_16==stored}')
    # B0 * 256 + B2?
    b02_scaled = sum(b0 * 256 + b2 for b0, b2 in zip(b0s, b2s))
    print(f'Sum of (B0*256+B2): {b02_scaled}  match={b02_scaled==stored}')
