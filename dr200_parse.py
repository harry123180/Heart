"""
dr200_parse.py — Python equivalent of ECGViewer's DR200Parser pipeline.

Pipeline:
  flash.dat
    -> parseConfig()        read ASCII key=value from blocks 0-2
    -> findLastDataBlock()  counter-based scan (magic + relative +1216)
    -> write truncated copy to temp file
    -> unpackdc.exe         official decoder -> ecg_ch0.ibf (int16 LE)
    -> 12.5 uV/LSB scale    convert to microvolts
    -> mark lead-off        -32768 sentinel
    -> hpFilter()           O(n) sliding-window high-pass (remove DC)

Usage:
    python dr200_parse.py <flash.dat>
    python dr200_parse.py <flash.dat> --plot
    python dr200_parse.py <flash.dat> --csv out.csv
"""

import sys
import os
import struct
import subprocess
import tempfile
import argparse
import numpy as np

# ── Constants (must match dr200parser.h) ─────────────────────────────────────
BLOCK_SIZE      = 512
DATA_OFFSET     = 10
ECG_BYTES       = 460
IBF_UV_PER_LSB  = 12.5
IBF_LEAD_OFF    = -32768   # int16 sentinel for lead-off
SAMPLE_RATE     = 180.0    # default; overridden by SampleRate in config
HP_WINDOW_SEC   = 1.0      # high-pass filter window = 1 second

UNPACKDC_CANDIDATES = [
    r"C:\nm\bin\unpackdc.exe",
]

# ── find unpackdc.exe ─────────────────────────────────────────────────────────

def find_unpackdc():
    # Also check same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = UNPACKDC_CANDIDATES + [
        os.path.join(script_dir, "unpackdc.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

# ── config parsing (blocks 0-2) ───────────────────────────────────────────────

def parse_config(raw: bytes) -> dict:
    """Read ASCII key=value pairs from config blocks 0, 1, 2 (bytes 4 onward)."""
    text = ""
    for bi in range(3):
        off = bi * BLOCK_SIZE + 4
        chunk = raw[off: off + BLOCK_SIZE - 8]
        null_pos = chunk.find(b'\x00')
        if null_pos >= 0:
            chunk = chunk[:null_pos]
        text += chunk.decode("latin-1", errors="replace")

    cfg = {}
    for line in text.splitlines():
        line = line.strip()
        if '=' in line:
            k, _, v = line.partition('=')
            cfg[k.strip()] = v.strip()
    return cfg

# ── block boundary detection ──────────────────────────────────────────────────

def find_last_data_block(raw: bytes) -> int:
    """
    Scan data blocks starting at block index 3.
    Accept block if:
      - magic bytes 0-5 == 00 02 00 00 1E 00
      - LE32 counter at bytes 6-9 increments by exactly 1216 from block 3 onward
    Returns index of last valid block (>= 3), or 2 if none found.
    """
    total_blocks = len(raw) // BLOCK_SIZE
    last_active  = 2
    prev_counter = None

    for bi in range(3, total_blocks):
        off = bi * BLOCK_SIZE
        blk = raw[off: off + BLOCK_SIZE]

        # Validate magic
        if blk[0:6] != b'\x00\x02\x00\x00\x1e\x00':
            break

        counter = struct.unpack_from('<I', blk, 6)[0]

        if prev_counter is None:
            # Block 3: accept any starting counter value
            prev_counter = counter
        else:
            if counter != prev_counter + 1216:
                break
            prev_counter = counter

        last_active = bi

    return last_active

# ── O(n) sliding-window high-pass filter ─────────────────────────────────────

def hp_filter(signal: np.ndarray, window_samples: int) -> np.ndarray:
    """
    Subtract the centred boxcar mean over [-half, +half] from each sample.
    Equivalent to dr200parser.cpp::hpFilter().
    """
    n    = len(signal)
    half = window_samples // 2
    out  = np.zeros(n, dtype=np.float32)

    win_sum = 0.0
    win_cnt = 0

    # Pre-load [0, half]
    for i in range(min(half + 1, n)):
        win_sum += signal[i]
        win_cnt += 1

    for i in range(n):
        # Advance right edge
        add_idx = i + half + 1
        if add_idx < n:
            win_sum += signal[add_idx]
            win_cnt += 1

        # Retire left edge
        remove_idx = i - half
        if remove_idx > 0:
            win_sum -= signal[remove_idx - 1]
            win_cnt -= 1

        out[i] = (signal[i] - win_sum / win_cnt) if win_cnt > 0 else 0.0

    return out

# ── main parse function ───────────────────────────────────────────────────────

def parse(filepath: str) -> dict:
    """
    Full DR200Parser pipeline.

    Returns dict with keys:
        config        - raw key=value config dict
        patient_id    - str
        start_date    - str
        start_time    - str
        serial_number - str
        sample_rate   - float (Hz)
        num_blocks    - int
        total_samples - int
        duration_sec  - float
        signal_uv     - np.ndarray float32, microvolts, HP-filtered
        lead_off      - np.ndarray bool, True where signal invalid
        ibf_path      - path of raw IBF file (temp)
        valid         - bool
        error         - str or None
    """

    result = {
        "valid": False, "error": None,
        "config": {}, "patient_id": "", "start_date": "", "start_time": "",
        "serial_number": "", "sample_rate": SAMPLE_RATE,
        "num_blocks": 0, "total_samples": 0, "duration_sec": 0.0,
        "signal_uv": np.array([], dtype=np.float32),
        "lead_off":  np.array([], dtype=bool),
        "ibf_path": None,
    }

    # Step 1: read file
    with open(filepath, "rb") as f:
        raw = f.read()

    total_blocks = len(raw) // BLOCK_SIZE
    if total_blocks < 4:
        result["error"] = "File too small (< 4 blocks)"
        return result

    # Step 2: parse config
    cfg = parse_config(raw)
    result["config"]        = cfg
    result["patient_id"]    = cfg.get("patient_id", "").strip()
    result["start_date"]    = cfg.get("start_date", "").strip()
    result["start_time"]    = cfg.get("start_time", "").strip()
    result["serial_number"] = cfg.get("Serial_number", "").strip()
    result["sample_rate"]   = float(cfg.get("SampleRate", "180"))

    # Step 3: find valid data range
    last_block = find_last_data_block(raw)
    if last_block < 3:
        result["valid"] = True
        return result

    result["num_blocks"] = last_block - 3 + 1

    # Step 4: write truncated copy to temp (unpackdc ERASES its input)
    unpackdc = find_unpackdc()
    if not unpackdc:
        result["error"] = "unpackdc.exe not found. Place it at C:\\nm\\bin\\unpackdc.exe"
        return result

    valid_bytes = (last_block + 1) * BLOCK_SIZE

    tmp_dir = tempfile.gettempdir()
    tmp_dat = os.path.join(tmp_dir, "flash_py_tmp.dat")
    ch0_ibf = os.path.join(tmp_dir, "ecg_ch0_py.ibf")
    ch1_ibf = os.path.join(tmp_dir, "ecg_ch1_py.ibf")
    ch2_ibf = os.path.join(tmp_dir, "ecg_ch2_py.ibf")

    with open(tmp_dat, "wb") as f:
        f.write(raw[:valid_bytes])

    # Remove stale IBF files
    for p in [ch0_ibf, ch1_ibf, ch2_ibf]:
        if os.path.exists(p):
            os.remove(p)

    # Step 5: run unpackdc
    ret = subprocess.run(
        [unpackdc, tmp_dat, ch0_ibf, ch1_ibf, ch2_ibf, "0"],
        timeout=120
    )
    if ret.returncode != 0:
        result["error"] = f"unpackdc failed (exit {ret.returncode})"
        return result

    if not os.path.exists(ch0_ibf) or os.path.getsize(ch0_ibf) == 0:
        result["error"] = "IBF ch0 empty or missing after unpackdc"
        return result

    result["ibf_path"] = ch0_ibf

    # Step 6: read IBF (int16 LE)
    ibf_data = np.fromfile(ch0_ibf, dtype="<i2")
    n_samples = len(ibf_data)

    # Step 7: convert to uV, mark lead-off
    lead_off = (ibf_data == IBF_LEAD_OFF)
    raw_uv   = np.where(lead_off, 0.0, ibf_data.astype(np.float32) * IBF_UV_PER_LSB)

    # Step 8: high-pass filter (window = 1 second = sample_rate samples)
    hp_window = int(result["sample_rate"] * HP_WINDOW_SEC)
    hp_uv = hp_filter(raw_uv.astype(np.float32), hp_window)
    hp_uv[lead_off] = 0.0  # zero out lead-off in filtered signal

    # Step 9: populate result
    result["total_samples"] = n_samples
    result["duration_sec"]  = n_samples / result["sample_rate"]
    result["signal_uv"]     = hp_uv
    result["lead_off"]      = lead_off
    result["valid"]         = True
    return result

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="DR200/HE flash.dat parser (mirrors ECGViewer)")
    ap.add_argument("file", help="Path to flash.dat")
    ap.add_argument("--plot", action="store_true", help="Show ECG waveform plot")
    ap.add_argument("--csv",  metavar="OUT", help="Save signal to CSV file")
    ap.add_argument("--start", type=float, default=None, help="Plot start time (seconds)")
    ap.add_argument("--end",   type=float, default=None, help="Plot end time (seconds)")
    args = ap.parse_args()

    print(f"Parsing: {args.file}")
    r = parse(args.file)

    if not r["valid"]:
        print(f"ERROR: {r['error']}")
        sys.exit(1)

    sr = r["sample_rate"]
    print(f"  Patient    : {r['patient_id']}")
    print(f"  Date/Time  : {r['start_date']} {r['start_time']}")
    print(f"  Serial     : {r['serial_number']}")
    print(f"  Blocks     : {r['num_blocks']}")
    print(f"  Samples    : {r['total_samples']}")
    print(f"  Duration   : {r['duration_sec']:.1f} s ({r['duration_sec']/60:.2f} min)")
    print(f"  Sample rate: {sr:.0f} Hz")
    lo_pct = r['lead_off'].mean() * 100
    print(f"  Lead-off   : {lo_pct:.1f}%")

    sig = r["signal_uv"]
    valid_mask = ~r["lead_off"]
    if valid_mask.any():
        print(f"  Amplitude  : {sig[valid_mask].min()/1000:.3f} mV .. {sig[valid_mask].max()/1000:.3f} mV")

    if args.csv:
        t = np.arange(len(sig)) / sr
        lo = r["lead_off"].astype(int)
        out = np.column_stack([t, sig / 1000.0, lo])
        np.savetxt(args.csv, out, delimiter=",", header="time_s,ecg_mV,lead_off", comments="")
        print(f"  CSV saved  : {args.csv}")

    if args.plot:
        import matplotlib.pyplot as plt

        t = np.arange(len(sig)) / sr
        t_start = args.start if args.start is not None else 0.0
        t_end   = args.end   if args.end   is not None else min(t_start + 30.0, t[-1])

        mask = (t >= t_start) & (t <= t_end)
        ts   = t[mask]
        ss   = sig[mask] / 1000.0   # uV -> mV
        lo   = r["lead_off"][mask]
        ss[lo] = np.nan

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.plot(ts, ss, linewidth=0.6, color='#00E040')
        ax.set_facecolor('#000000')
        fig.patch.set_facecolor('#0A0A0A')
        ax.set_xlabel("Time (s)", color='white')
        ax.set_ylabel("mV", color='white')
        ax.set_title(
            f"DR200/HE ECG  —  Patient {r['patient_id']}  {r['start_date']} {r['start_time']}",
            color='white')
        ax.tick_params(colors='white')
        for spine in ax.spines.values():
            spine.set_edgecolor('#333333')
        ax.grid(True, color='#003300', linewidth=0.4)
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    main()
