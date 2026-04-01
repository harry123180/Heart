"""
Safe ECG extraction: copy 233.dat first, run unpackdc on COPY, keep original intact.
Then analyze IBF output to understand the correct format.
"""
import sys, subprocess, shutil, tempfile, os, numpy as np
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SRC_DAT  = r"C:\Users\TSIC\Documents\GitHub\Heart\233.dat"
UNPACKDC = r"C:\nm\bin\unpackdc.exe"
OUT_DIR  = r"C:\Users\TSIC\Documents\GitHub\Heart\output\ibf"

os.makedirs(OUT_DIR, exist_ok=True)

ch0 = os.path.join(OUT_DIR, "233_ch0.ibf")
ch1 = os.path.join(OUT_DIR, "233_ch1.ibf")
ch2 = os.path.join(OUT_DIR, "233_ch2.ibf")

# --- Step 1: copy to temp (unpackdc will ERASE the input file) ---
tmp = tempfile.NamedTemporaryFile(suffix='.dat', delete=False)
tmp_path = tmp.name
tmp.close()
print(f"Copying {SRC_DAT} -> {tmp_path} ...")
shutil.copy2(SRC_DAT, tmp_path)
orig_size = os.path.getsize(SRC_DAT)
print(f"Original: {orig_size:,} bytes (preserved)")
print(f"Copy:     {os.path.getsize(tmp_path):,} bytes")

# --- Step 2: run unpackdc on the COPY ---
print(f"\nRunning unpackdc on copy...")
r = subprocess.run(
    [UNPACKDC, tmp_path, ch0, ch1, ch2, "0"],
    capture_output=True, timeout=120
)
print(f"unpackdc exit: {r.returncode}")
if r.returncode != 0:
    print("STDERR:", r.stderr[:300])
    sys.exit(1)

# Verify original untouched
final_size = os.path.getsize(SRC_DAT)
print(f"Original after unpackdc: {final_size:,} bytes {'OK' if final_size == orig_size else 'CHANGED!'}")

# Clean up temp
if os.path.exists(tmp_path):
    os.unlink(tmp_path)

# --- Step 3: analyze IBF output ---
ibf0 = np.fromfile(ch0, dtype='<i2')
ibf1 = np.fromfile(ch1, dtype='<i2')
ibf2 = np.fromfile(ch2, dtype='<i2')

print(f"\nIBF ch0: {len(ibf0)} samples")
print(f"IBF ch1: {len(ibf1)} samples")
print(f"IBF ch2: {len(ibf2)} samples")
print(f"Duration @ 180 Hz: {len(ibf0)/180:.2f} s")
print()

print(f"ch0 range (int16): {ibf0.min()} ~ {ibf0.max()}")
print(f"ch0 first 30: {ibf0[:30].tolist()}")

# Find "lead-off" sentinel: find long constant runs
diffs = np.diff(ibf0.astype(np.int32))
nz = np.where(diffs != 0)[0]
if len(nz) > 0:
    ecg_start = nz[0] + 1
    print(f"\nFirst sample variation at index {ecg_start}: {ibf0[ecg_start-1]} -> {ibf0[ecg_start]}")

# Find heartbeat peaks (look for regular large peaks in known ECG window)
# Use middle 20 seconds to avoid start/end artifacts
mid = len(ibf0) // 2
window = ibf0[mid : mid + 3600].astype(np.int32)  # 20s @ 180Hz
mn, mx = window.min(), window.max()
thresh = mn + (mx - mn) * 0.7
peaks = []
for i in range(1, len(window)-1):
    if window[i] >= thresh and window[i] > window[i-1] and window[i] > window[i+1]:
        if not peaks or i - peaks[-1] > 30:  # min 200ms refractory
            peaks.append(i)

if len(peaks) >= 2:
    intervals = np.diff(peaks)
    mean_rr = np.mean(intervals)
    hr = 60.0 / (mean_rr / 180.0)
    print(f"\nHeartbeat analysis (mid 20s window):")
    print(f"  Detected {len(peaks)} peaks, RR mean={mean_rr:.1f} samples = {hr:.1f} bpm")
    print(f"  Peak values: {[int(window[p]) for p in peaks[:5]]}")
    print(f"  Amplitude range: {mn} ~ {mx}")
    print(f"  If 1 uV/LSB: {mx} uV = {mx/1000:.2f} mV peak")

print("\nSaved IBF files to:", OUT_DIR)
