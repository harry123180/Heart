"""
Simulate new findLastDataBlock logic on realtest/flash.dat
"""
import sys, struct
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DAT = r"C:\Users\TSIC\Documents\GitHub\Heart\realtest\flash.dat"
BLOCK = 512

lastActive = 2
prevCounter = 0

with open(DAT, 'rb') as f:
    bi = 3
    while True:
        f.seek(bi * BLOCK)
        blk = f.read(BLOCK)
        if len(blk) < BLOCK:
            print(f"EOF at block {bi}")
            break

        # Magic check: 00 02 00 00 1E 00
        if blk[0] != 0x00 or blk[1] != 0x02 or blk[2] != 0x00 or blk[3] != 0x00 or \
           blk[4] != 0x1E or blk[5] != 0x00:
            print(f"Magic mismatch at block {bi}: {blk[:6].hex()}")
            break

        counter = struct.unpack_from('<I', blk, 6)[0]

        if bi == 3:
            prevCounter = counter
            print(f"Block 3 base counter: {counter}")
        else:
            expected = prevCounter + 1216
            if counter != expected:
                print(f"Counter mismatch at block {bi}: got {counter}, expected {expected} (diff={counter-expected})")
                break
            prevCounter = counter

        lastActive = bi
        bi += 1

        # Print progress every 100 blocks
        if bi % 100 == 0:
            print(f"  ... block {bi-1} OK, counter={prevCounter}")

print(f"\nlastActive = {lastActive}")
print(f"numBlocks = {lastActive - 3 + 1} (if >= 3)")
print(f"Duration estimate: {(lastActive-3+1)*306/180:.1f} seconds = {(lastActive-3+1)*306/180/60:.1f} minutes")
