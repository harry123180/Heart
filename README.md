# DR200/HE Holter Recorder — ECG Viewer & Parser

Reverse-engineered parser and Qt5 viewer for NorthEast Monitoring DR200/HE
Holter recorder SD card data (`flash.dat`).

## Quick Start

```powershell
cd ECGViewer
powershell -File build_ecg.ps1   # build
powershell -File run_ecg.ps1     # run
```

Load any `flash.dat` from a DR200/HE recorder via **檔案 → 開啟**。

## Requirements

- `C:\nm\bin\unpackdc.exe` — official NE Monitoring decoder (not included)
- Qt5 via Anaconda: `C:\Users\TSIC\AppData\Local\anaconda3\Library\bin`
- MSVC 2022 build tools

## Session Results & Analysis

See **[RESULTS.md](RESULTS.md)** for:
- Validation against BioTrace+ reference (HR error: +0.2 bpm)
- List of bugs fixed (parser rewrite, scale fix, block boundary detection)
- IBF and flash.dat format specification

## Format Reference

See **[FORMAT_SPEC.md](FORMAT_SPEC.md)** for complete reverse-engineered
flash.dat block format.

## Files

| File | Description |
|------|-------------|
| `ECGViewer/` | Qt5 C++ viewer application |
| `ECGViewer/dr200parser.cpp` | flash.dat → IBF → µV pipeline |
| `hr_analysis.py` | Python HR analysis with BioTrace+ comparison |
| `hr_plot2.py` | HR visualization with multi-panel plot |
| `extract_ecg.py` | Safe IBF extraction (copy before unpackdc) |
| `FORMAT_SPEC.md` | Complete flash.dat format specification |
| `RESULTS.md` | Validation results and bug fixes |

## Architecture

```
flash.dat
  └─ findLastDataBlock()    counter-based scan (not zero-streak)
  └─ QTemporaryFile copy    unpackdc ERASES its input
  └─ unpackdc.exe           official decoder → ecg_ch0.ibf
  └─ IBF int16 LE           12.5 µV/LSB, 180 Hz
  └─ O(n) HP filter         remove DC electrode polarization
  └─ ECGData → ECGView      Qt5 rendering
```
