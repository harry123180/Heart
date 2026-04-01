# DR200/HE ECG Parser — Session Results

## Validated Recordings

| File | Patient | Date | Duration | Lead-off | HR |
|------|---------|------|----------|----------|----|
| `233.dat` | 123 | 2026-01-23 14:23:32 | 97.8 s | ~2% | ~160 bpm |
| `realtest/flash.dat` | 100 | 2026-03-16 09:40:30 | 1256 s (20.93 min) | 0.3% | ~83 bpm |

---

## Validation Against BioTrace+ Reference

`realtest/flash.dat` was recorded simultaneously with a MindMedia BioTrace+
biofeedback session (`realtest/0316test.PDF.pdf`).

| | Value |
|---|---|
| BioTrace+ session start | 09:50:10 (offset +9m40s from flash.dat) |
| BioTrace+ mean HR (BVP) | **82.76 bpm** |
| ECG-derived HR (same window) | **83.0 bpm** |
| Difference | **+0.2 bpm (0.24%)** |

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
