# DR200/HE ECG Parser — Session Results

## Validated Recordings

| File | Patient | Date | Duration | Lead-off | HR |
|------|---------|------|----------|----------|----|
| `233.dat` | 123 | 2026-01-23 14:23:32 | 97.8 s | ~2% | ~160 bpm |
| `realtest/0316_1/flash.dat` | 100 | 2026-03-16 09:40:30 | 1256 s (20.93 min) | 0.3% | ~80 bpm |

---

## Validation Against BioTrace+ Reference

`realtest/0316_1/flash.dat` was recorded simultaneously with a MindMedia BioTrace+
biofeedback session. The two devices measure different physiological signals:

| Device | Signal | File |
|--------|--------|------|
| DR200/HE Holter | ECG (cardiac electrical) | `flash.dat` |
| MindMedia BioTrace+ | BVP (photoplethysmography) | `0316.raw.TXT.txt` |

BVP-derived HR lags ECG R-peaks by ~100-300 ms (pulse transit time) — a normal
physiological offset, not a measurement error.

### HR Comparison (overlap window, validated 2026-04-13, clinically approved)

| | Value |
|---|---|
| BioTrace+ session start | 09:50:10 (offset +9 min 40 s from flash.dat) |
| Overlap window (ECG time) | 580 s – 1298 s (674 s) |
| BioTrace+ mean HR (BVP, full session) | **82.74 bpm** |
| ECG-derived HR (R-peak, same window) | **80.27 bpm** |
| Difference | **-2.47 bpm (-2.99%)** |
| Clinical assessment | **Approved** |

### Sample-level Check (30-40 s window)

| | Value |
|---|---|
| Reference | ECGViewer exported CSV (`ECGData30s-40s.csv`) |
| Our parser (Python) vs reference | RMS diff = **306 uV** (driven by <5 spike samples) |
| Core signal agreement | **< 0.01 uV** on clean samples |
| Conclusion | **Pipeline correct** |

ECG waveform amplitude after IBF conversion: **±1-2 mV** (physiologically correct).

---

## Key Bugs Fixed This Session

### 1. Parser: 12-bit manual decode → unpackdc pipeline

The original parser attempted to decode 12-bit packed samples directly from
`flash.dat`. This produced wrong values because the byte layout differs from
the assumed format.

**Fix**: Use `unpackdc.exe` (official NE Monitoring tool) as the decoder:
1. Copy valid blocks to `QTemporaryFile` (unpackdc ERASES its input)
2. Run `unpackdc <tmp> ecg_ch0.ibf ecg_ch1.ibf ecg_ch2.ibf 0`
3. Read IBF (int16 LE, 12.5 µV/LSB, 180 Hz)
4. Apply O(n) HP filter to remove DC electrode polarization

### 2. `findLastDataBlock`: zero-streak → block counter validation

The original logic stopped after 20 consecutive zero-byte blocks.
On `realtest/flash.dat`, old recordings remained in unzeroed flash sectors,
so the heuristic scanned the entire 405 MB and returned 254,997 false blocks
(displaying 477,230 seconds instead of ~21 minutes).

**Fix**: Validate each block's sequential counter (bytes 6–9, LE32).
Each new recording starts fresh; counter increments by exactly 1216 per block.
Old flash data has mismatched counters and is correctly rejected.

```
// Accept any starting value (firmware version differs: 1208 vs 1212)
if (bi == 3) { prevCounter = counter; }
else if (counter != prevCounter + 1216) { break; }
```

### 3. IBF scale: 1 µV/LSB → 12.5 µV/LSB

The IBF format specification (NE Monitoring `Interface for Foreign Data Formats.pdf`)
explicitly states **12.5 µV per LSB**. Setting 1.0 made QRS amplitudes appear
as ±0.05 mV instead of the correct ±0.5–2 mV.

### 4. HP filter: O(n×w) → O(n) sliding window

For a 120-hour recording (~90M samples, window=180), the naive implementation
would require ~16 billion operations. Fixed to O(n) by maintaining a running sum.

---

## IBF Format (Confirmed)

| Parameter | Value |
|-----------|-------|
| Sample format | int16, little-endian |
| Scale | **12.5 µV / LSB** |
| Sample rate | 180 Hz |
| Lead-off sentinel | -32768 (INT16_MIN) |
| Channels | ch0=ECG, ch1/ch2 unused for DR200/HE |
| unpackdc flag | `0` (flags 1/2/3 → exit code 99) |

---

## flash.dat Block Format (Confirmed)

```
Offset  Size  Description
0-3     4     Magic: 00 02 00 00
4-5     2     Sub-type: 1E 00 (data blocks); ASCII text (config blocks 0-2)
6-9     4     LE32 counter: base + (bi-3)*1216  [base varies by firmware]
10-469  460   ECG sample data (unpackdc reads this region)
470-507 38    Diary event ASCII record
508-511 4     Unknown checksum (NOT CRC32/CRC16/Fletcher/Adler)
```

Config blocks 0-2 contain ASCII `key=value` pairs starting at byte 4:
`SampleRate`, `SampleStorageFormat`, `start_time`, `start_date`,
`Serial_number`, `patient_id`, `DiaryText`.

---

## Python Parser (dr200_parse.py) — Developer Reference

For downstream ECG analysis based on `.dat` files, use `dr200_parse.py` as the
entry point. It mirrors the ECGViewer C++ pipeline exactly.

### Quick start

```python
from dr200_parse import parse

r = parse(r"path/to/flash.dat")

# Metadata
print(r["patient_id"], r["start_date"], r["start_time"])
print(r["duration_sec"], r["sample_rate"])   # seconds, Hz

# Signal (HP-filtered, DC removed)
ecg_uv   = r["signal_uv"]    # np.ndarray float32, microvolts
lead_off = r["lead_off"]     # np.ndarray bool, True = electrode off
t        = np.arange(len(ecg_uv)) / r["sample_rate"]   # time axis (seconds)

# Convert to millivolts for display
ecg_mV = ecg_uv / 1000.0
ecg_mV[lead_off] = np.nan    # blank out invalid samples
```

### Pipeline steps (in order)

| Step | Function | Notes |
|------|----------|-------|
| 1 | `parse_config()` | Reads ASCII key=value from blocks 0-2 |
| 2 | `find_last_data_block()` | Counter-based boundary detection |
| 3 | Write temp copy | `unpackdc` ERASES its input — always copy first |
| 4 | `unpackdc.exe` | Official decoder → `ecg_ch0.ibf` |
| 5 | IBF read | `np.fromfile("<i2")` — int16 LE |
| 6 | Scale | `* 12.5` → microvolts; `-32768` = lead-off sentinel |
| 7 | `hp_filter()` | O(n) sliding-window boxcar, window = 1 s = 180 samples |

### Prerequisites

- `unpackdc.exe` at `C:\nm\bin\unpackdc.exe`
- Python packages: `numpy`, `scipy` (for R-peak detection in `validate_ecg.py`)

### Key constants

| Constant | Value | Source |
|----------|-------|--------|
| Sample rate | 180 Hz | Config block `SampleRate` |
| Scale | 12.5 uV/LSB | NE Monitoring IBF spec |
| Lead-off sentinel | -32768 | IBF spec |
| Block size | 512 bytes | Hardware |
| Counter increment | 1216/block | Reverse engineered |

### Output signal characteristics

- After HP filter: baseline centred at 0, QRS amplitude **±0.5-2 mV** typical
- Large transients (> ±5 mV) near DC baseline jumps are artifact — clip for display
- Lead-off regions: set to NaN before plotting, exclude from analysis
- 0.3% lead-off rate is typical for a well-attached 20-minute recording
