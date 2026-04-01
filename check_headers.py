"""
Dump the first 12 bytes of blocks 0-6 from realtest/flash.dat
to verify magic bytes and counter values.
"""
import sys, struct
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DAT = r"C:\Users\TSIC\Documents\GitHub\Heart\realtest\flash.dat"
BLOCK = 512

with open(DAT, 'rb') as f:
    data = f.read(7 * BLOCK)

for bi in range(7):
    blk = data[bi*BLOCK:(bi+1)*BLOCK]
    hdr = blk[:12]
    hex_str = ' '.join(f'{b:02X}' for b in hdr)
    counter = struct.unpack_from('<I', blk, 6)[0]
    expected = (bi - 2) * 1216 - 4 if bi >= 3 else -1
    print(f"Block {bi}: [{hex_str}]  counter={counter}  expected={expected}  match={counter==expected if bi>=3 else 'N/A'}")

# Also check a few blocks around where 18 min would end
# 18 min * 60s * 180Hz / 306 samples/block ~ 635 blocks
print()
print("Checking blocks around expected end (~635):")
with open(DAT, 'rb') as f:
    for bi in [630, 635, 636, 637, 638, 640, 650]:
        f.seek(bi * BLOCK)
        blk = f.read(BLOCK)
        if len(blk) < 10:
            break
        hdr = blk[:12]
        hex_str = ' '.join(f'{b:02X}' for b in hdr)
        counter = struct.unpack_from('<I', blk, 6)[0]
        expected = (bi - 2) * 1216 - 4
        print(f"Block {bi}: [{hex_str}]  counter={counter}  expected={expected}  match={counter==expected}")
