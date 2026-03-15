# NorthEast Monitoring DR200/HE Flash Format Specification
## Reverse-engineered from flash.dat and 233.dat

**Device:** DR200/HE Holter Recorder
**Manufacturer:** NorthEast Monitoring Inc. (NEMM)
**Firmware:** V4.47 (SN 046040 / 046383)
**Analysis date:** 2026-02-23
**Status:** 95% complete — one unknown field remains

---

## File Layout

The .dat file (SD card dump) is organized as 512-byte blocks, sequentially arranged:

```
Block 0  [bytes 0-511]:     Config block 0 (ASCII)
Block 1  [bytes 512-1023]:  Config block 1 (ASCII)
Block 2  [bytes 1024-1535]: Config block 2 (ASCII)
Block 3+ [bytes 1536+]:     ECG data blocks
```

Blocks beyond the last valid ECG block contain all-zero bytes (unwritten flash).

---

## Config Blocks (0-2)

Each config block is a null-terminated ASCII string containing `key=value` pairs, one per line.
The block header occupies bytes 0-3 (magic) and the string begins at byte 4.

### Known config keys

| Key                  | Example value        | Meaning                                  |
|----------------------|----------------------|------------------------------------------|
| `start_date`         | `2026-01-23`         | Recording start date                     |
| `start_time`         | `14:23:32`           | Recording start time (local)             |
| `Serial_number`      | `046383`             | Recorder serial number                   |
| `Recorder_version`   | `V4.47`              | Firmware version                         |
| `SampleRate`         | `180`                | ADC sample rate (Hz)                     |
| `SampleStorageFormat`| `1`                  | Number of ECG channels stored            |
| `patient_id`         | `2121`               | Patient identifier                       |
| `VerificationNo`     | `123`                | Study number                             |
| `DiaryText`          | `event1^event2^...`  | Diary button labels, `^`-delimited       |

**SampleStorageFormat** = number of channels. Samples interleave: ch0, ch1, ch2, ch0, ...
Use `unpackdc datacard.dat out0.dat out1.dat out2.dat N` (NE Monitoring tool) to split channels.

### Config block raw layout (bytes)

```
Offset 0-3:   Unknown magic (first bytes of config text or 00 00 00 00)
Offset 4+:    ASCII key=value text, null-terminated
```

> Note: In config blocks, bytes 6-9 are part of the ASCII text (e.g., "Samp" from "SampleRate"),
> NOT a counter field. The counter field only exists in data blocks.

---

## ECG Data Blocks (Block 3+)

Each data block is exactly 512 bytes with this layout:

```
Offset  0 -  3:  [00 02 00 00]  Magic bytes (LE32 = 0x00000200 = 512)
Offset  4 -  5:  [1E 00]        Sub-type field = 0x001E = 30 decimal
Offset  6 -  9:  [XX XX XX XX]  Sample counter (LE32, see below)
Offset 10 - 507: [498 bytes]    ECG sample data + embedded diary records
Offset 508 - 511:[XX XX XX XX]  Unknown 32-bit field (see below)
```

### Magic bytes (offset 0-3)

`00 02 00 00` = little-endian 0x00000200 = 512.
Likely encodes the block size: byte[1] = 0x02 = 2 pages of 256 bytes = 512 bytes.
Constant across all data blocks.

### Sub-type field (offset 4-5)

`1E 00` = LE16 = 0x001E = 30 decimal.
Also equals ASCII RS (Record Separator = 0x1E).
Likely a block type marker indicating "ECG data record."
Constant across all data blocks. May change for other record types (not observed).

### Sample counter (offset 6-9)

A 32-bit LE unsigned counter that increments by **1216** for each data block:

```
Block  3: counter = 1212
Block  4: counter = 2428
Block  5: counter = 3644
Block  N: counter = (N - 2) * 1216 - 4
```

**Formula:** `counter[block_N] = (N - 2) * 1216 - 4`
**Starting value:** 1212 = 1216 * 1 - 4 (for block 3, the first data block after 3 config blocks)

**Interpretation:** The counter tracks firmware-internal write offset in units of 32-bit words.
Each data block writes **304 internal 32-bit words** = 1216 bytes in the firmware's internal sample buffer.
(304 × 4 bytes = 1216 bytes). The 4-byte offset (1212 vs 1216) is unexplained — possibly a reserved header region.

### ECG sample data region (offset 10-507, 498 bytes)

The 498-byte data region contains two components:

#### ECG Samples (first ~460 bytes = ~306 samples)

12-bit little-endian packed, 2 samples per 3 bytes:

```
For bytes B0, B1, B2 at position i*3:
  S1 = B0 | ((B1 & 0x0F) << 8)    [bits 11:0 from B0 and low nibble of B1]
  S2 = (B1 >> 4) | (B2 << 4)      [high nibble of B1 and B2]
```

**Parameters:**
| Parameter        | Value      | Notes                                |
|------------------|------------|--------------------------------------|
| Sample rate      | 180 Hz     | Confirmed via duration calculation   |
| Voltage scale    | 12.5 μV/LSB| NE Monitoring specification          |
| Bit depth        | 12-bit     | Values 0-4095                        |
| ADC midpoint     | 2048       | Center of range = 0 μV               |
| Lead-off code    | 0x777 = 1911| Electrode disconnected indicator    |
| Full-scale       | ±25.6 mV   | (±2048 × 12.5 μV)                   |

**mV conversion:** `signal_uV = (sample - 2048) * 12.5`

**Lead-off detection:** `sample == 1911` (0x777)

**IBF output format** (for NE Monitoring software):
16-bit signed LE, 12.5 μV/LSB, 180 Hz, file `flashcN.dat` for channel N.
`ibf_value = clip((sample - 2048), -32768, 32767)` as int16 (already in ADC counts = IBF units)

#### Embedded Diary Event Records (last ~38 bytes)

Diary events are stored as ASCII text in the **last 38 bytes** of the data region (block offsets 470-507).
The format appears to be:
```
[0x00 0x00] [LEN_or_TYPE] [\n\r] [SPACE] [sample_offset] [event_fields] [\n\r]
```

Example records observed:
```
\x00\x00)\n\r 241ia ib 3F 01 01 00 00 01 AA\n\r\n
\x00\x00#\r 258 OP 41 ic ia ib 0 01 01\n\r 258
\x00\x006 35 34 ba 154 TM -86 180 0\n\rR 1072
```

**Diary event field interpretation (partial):**
- `241`, `258` = sample offset within the block where event was detected
- `ia`, `ib`, `ic` = channel identifiers (channel a, b, c)
- `OP` = event type code
- `3F`, `41` etc. = hex-encoded event parameters
- `TM` = possibly "Temperature Measurement"
- `AA` = confirmed good / all-amplifiers active
- Numeric fields = various measurement values

> **Parser note:** When decoding 12-bit samples from the full 498 bytes,
> the last ~25 samples will be garbage (decoded from diary event ASCII bytes).
> These can be filtered by rejecting samples outside physiological range or
> by only decoding the first 459 bytes (306 samples × 1.5 bytes/sample).

### Unknown tail field (offset 508-511)

A 32-bit LE unsigned value. **Formula unknown** after extensive testing.

**What it is NOT:**
- CRC-32 (multiple input ranges tested)
- CRC-16 stored as 32-bit
- Fletcher-32 checksum
- Adler-32 checksum
- Sum of raw bytes (range exceeds max possible byte sum)
- Sum of decoded 12-bit LE samples
- Sum of decoded 12-bit BE samples
- Cumulative sample sum across blocks
- Simple linear function of the counter

**Observed properties:**
| Property              | Value                                           |
|-----------------------|-------------------------------------------------|
| Range (233.dat)       | 248,542 – 271,961 (0x3CC5E – 0x42659)          |
| Range (flash.dat)     | 249,487 – 251,620 (0x3CE8F – 0x3D6E4)          |
| Per-sample ratio      | ≈ 800 (value / 332 samples/block)               |
| Upper 16 bits         | Always 0x0003 or 0x0004                         |
| Trend                 | Fluctuates; slowly decreases late in recording  |

**Most likely interpretation:** A firmware-proprietary checksum using the raw sample buffer
(32-bit integers internally, before 12-bit packing), not derivable without firmware source code.

---

## Duration Calculation

```python
BLOCK_SIZE        = 512
DATA_OFFSET       = 10
DIARY_BYTES       = 38   # bytes reserved for diary events at end of data region
ECG_BYTES         = 498 - DIARY_BYTES  # = 460 bytes (if diary always present)
# Or conservatively: use full 498 bytes and filter garbage samples
SAMPLES_PER_BLOCK = (498 * 2) // 3   # = 332 (theoretical max, includes diary region)
SAMPLE_RATE       = 180              # Hz

# Safe approach (ignore diary event contamination, accept ~5% error):
n_data_blocks = last_data_block - 3 + 1
total_samples = n_data_blocks * SAMPLES_PER_BLOCK
duration_sec  = total_samples / SAMPLE_RATE
```

---

## Multi-Channel Support

When `SampleStorageFormat = N` (N channels):
- Samples interleave: ch0, ch1, ..., ch(N-1), ch0, ch1, ...
- Each channel's samples extracted by: `channel_k = all_samples[k::N]`
- IBF output: one file per channel (`flashc0.dat`, `flashc1.dat`, ...)
- NE Monitoring `unpackdc.exe` command: `unpackdc datacard.dat c0.dat c1.dat c2.dat N`

Maximum channels per DR200 spec: 3 (confirmed by `unpackdc` 3-output command)

---

## Validated Sample Files

| File       | Patient | Date       | Duration | Blocks | SR   | Channels | Lead-off |
|------------|---------|------------|----------|--------|------|----------|----------|
| flash.dat  | —       | 2026-02-06 | ~148 s   | 146    | 180  | 1        | 11.8%    |
| 233.dat    | 123     | 2026-01-23 | 97.8 s   | 53     | 180  | 1        | 2.0%     |

**Clinical results (233.dat):**
- Heart rate: ~160 bpm (tachycardia)
- SDNN: ~95 ms
- RMSSD: ~127 ms
- 260 R-peaks detected in 97.8 seconds
- Signal amplitude: ±1-3 mV typical
- Lead-off periods: only 2% (good electrode contact)

---

## Reference Implementations

- `dr200_parser.py` — Full Python parser: reads config, decodes ECG, saves CSV + IBF + plot
- `visualize.py` — Medical-quality 6-panel ECG visualization
- `decode_233.py` — Clinical analysis: R-peak detection, HRV, beat templates, tachogram

---

## Remaining Unknowns

1. **Bytes 508-511 checksum formula** — proprietary, not derivable without firmware
2. **Sub-type field meaning** (0x001E = 30) — likely record type marker
3. **Counter starting value 1212 vs 1216** — off-by-4 explanation not found
4. **Diary event binary format** — partially decoded (ASCII text visible, binary fields present)
5. **Multi-channel byte layout** — not tested (only single-channel files available)
