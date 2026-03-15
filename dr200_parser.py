#!/usr/bin/env python3
"""
DR200/HE Holter Recorder flash.dat Parser
NorthEast Monitoring Inc.

Reverse-engineered format:
  - 512-byte blocks
  - Blocks 0-2: ASCII config (key=value)
  - Blocks 3+:  ECG sample data
    Block header (10 bytes):  [00 02 00 00] [sub_type 2B] [sample_offset 4B]
    Sample data  (498 bytes): 12-bit packed LE, SampleStorageFormat channels
    Checksum     (4 bytes):   end of block

12-bit LE packing (2 samples per 3 bytes):
  S1 = B0 | ((B1 & 0x0F) << 8)
  S2 = (B1 >> 4) | (B2 << 4)

Scale: 12.5 uV/LSB (NE Monitoring spec)
Lead-off code: 0x777 = 1911 (when electrodes disconnected)
"""

import os, re, struct, csv
import numpy as np

BLOCK_SIZE      = 512
DATA_OFFSET     = 10
TAIL_BYTES      = 4
BYTES_PER_BLOCK = BLOCK_SIZE - DATA_OFFSET - TAIL_BYTES  # 498
SAMPLE_RATE     = 180     # Hz
UV_PER_LSB      = 12.5   # microvolts per LSB
LEAD_OFF_CODE   = 0x777  # = 1911 decimal


class DR200Parser:
    def __init__(self, filepath):
        self.filepath = filepath
        self.config = {}
        self.channels = []
        self.duration_sec = 0
        self._load()

    def _load(self):
        with open(self.filepath, 'rb') as f:
            self.raw = f.read()
        self._parse_config()
        self._find_data_bounds()
        self._decode_samples()

    def _parse_config(self):
        config_text = ''
        for bi in range(4):
            off = bi * BLOCK_SIZE + 4
            block = self.raw[off:off + BLOCK_SIZE - 8]
            try:
                null_pos = block.index(0)
                config_text += block[:null_pos].decode('ascii', errors='replace')
            except ValueError:
                config_text += block.decode('ascii', errors='replace')

        for line in config_text.splitlines():
            line = line.strip()
            if '=' in line:
                k, _, v = line.partition('=')
                self.config[k.strip()] = v.strip()

        diary_raw = self.config.get('DiaryText', '')
        self.diary_events = [e.strip() for e in diary_raw.split('^') if e.strip()]

        print('=== Recording Configuration ===')
        for k in ['start_date', 'start_time', 'Serial_number', 'Recorder_version',
                  'SampleRate', 'SampleStorageFormat', 'patient_id', 'VerificationNo']:
            if k in self.config:
                print(f'  {k}: {self.config[k]}')
        print(f'  Diary events: {self.diary_events}')

    def _find_data_bounds(self):
        total_blocks = len(self.raw) // BLOCK_SIZE
        self.first_data_block = 3
        self.last_data_block = 3

        for bi in range(3, total_blocks):
            off = bi * BLOCK_SIZE + DATA_OFFSET
            bd = self.raw[off:off + BYTES_PER_BLOCK]
            if any(b != 0 for b in bd):
                self.last_data_block = bi

        n_blocks = self.last_data_block - self.first_data_block + 1
        samples_per_block = (BYTES_PER_BLOCK * 2) // 3  # 332 for 12-bit LE
        n_channels = int(self.config.get('SampleStorageFormat', 1))
        samples_total = n_blocks * samples_per_block
        self.duration_sec = samples_total / SAMPLE_RATE

        print(f'\n=== Data Bounds ===')
        print(f'  Data blocks:   {self.first_data_block} to {self.last_data_block} ({n_blocks} blocks)')
        print(f'  Samples/block: {samples_per_block} (12-bit LE packed)')
        print(f'  Total samples: {samples_total:,}')
        print(f'  Duration:      {self.duration_sec:.1f}s = {self.duration_sec/60:.2f} min')
        print(f'  SampleStorageFormat (channels): {n_channels}')

    def _decode_12bit_le(self, raw_bytes_buf):
        out = []
        rb = bytes(raw_bytes_buf)
        for i in range(0, len(rb) - 2, 3):
            b0, b1, b2 = rb[i], rb[i+1], rb[i+2]
            out.append(b0 | ((b1 & 0x0F) << 8))
            out.append((b1 >> 4) | (b2 << 4))
        return np.array(out, dtype=np.int32)

    def _decode_samples(self):
        raw_all = bytearray()
        for bi in range(self.first_data_block, self.last_data_block + 1):
            off = bi * BLOCK_SIZE + DATA_OFFSET
            raw_all.extend(self.raw[off:off + BYTES_PER_BLOCK])

        samples_raw = self._decode_12bit_le(bytes(raw_all))
        n_channels = int(self.config.get('SampleStorageFormat', 1))
        self.n_channels = n_channels

        if n_channels == 1:
            self.channels = [samples_raw.astype(np.float32)]
        else:
            self.channels = [samples_raw[ch::n_channels].astype(np.float32)
                             for ch in range(n_channels)]

        # Convert to microvolts, centered at ADC midpoint 2048
        self.channels_uv = [(ch - 2048) * UV_PER_LSB for ch in self.channels]

        n_samples = len(self.channels[0])
        self.time_sec = np.arange(n_samples) / SAMPLE_RATE
        self.lead_off_mask = [(ch == LEAD_OFF_CODE) for ch in self.channels]

        print(f'\n=== Decoded Samples ===')
        for i, (ch, ch_uv) in enumerate(zip(self.channels, self.channels_uv)):
            lead_off_pct = self.lead_off_mask[i].mean() * 100
            valid = ch_uv[~self.lead_off_mask[i]]
            print(f'  Channel {i}: {len(ch):,} samples, lead-off={lead_off_pct:.1f}%')
            if len(valid) > 0:
                pp = valid.max() - valid.min()
                print(f'    Valid range: {valid.min():.0f} to {valid.max():.0f} uV  '
                      f'(pp={pp:.0f} uV = {pp/1000:.2f} mV)')

    def save_csv(self, out_path):
        with open(out_path, 'w', newline='') as f:
            writer = csv.writer(f)
            headers = ['time_s'] + [f'ch{i}_uv' for i in range(self.n_channels)] + \
                      [f'ch{i}_lead_off' for i in range(self.n_channels)]
            writer.writerow(headers)
            for i in range(len(self.time_sec)):
                row = [f'{self.time_sec[i]:.6f}']
                for ch_uv in self.channels_uv:
                    row.append(f'{ch_uv[i]:.2f}')
                for mask in self.lead_off_mask:
                    row.append('1' if mask[i] else '0')
                writer.writerow(row)
        print(f'Saved CSV: {out_path} ({len(self.time_sec):,} rows)')

    def save_ibf(self, out_dir):
        """
        Save in NE Monitoring IBF format:
        flashc0.dat, flashc1.dat, ...
        16-bit signed LE, 12.5 uV/LSB, 180 Hz
        """
        os.makedirs(out_dir, exist_ok=True)
        for i, ch_uv in enumerate(self.channels_uv):
            out_path = os.path.join(out_dir, f'flashc{i}.dat')
            ibf_values = np.clip(ch_uv / UV_PER_LSB, -32768, 32767).astype(np.int16)
            ibf_values.tofile(out_path)
            sz = os.path.getsize(out_path)
            print(f'Saved IBF channel {i}: {out_path} ({len(ibf_values):,} samples, {sz:,} bytes)')

    def plot(self, out_path, max_sec=60):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from scipy.signal import butter, filtfilt

        def bpf(x, lo=0.5, hi=40, fs=SAMPLE_RATE):
            b, a = butter(3, [lo/(fs/2), hi/(fs/2)], btype='band')
            return filtfilt(b, a, x)

        n_ch = self.n_channels
        n_rows = n_ch * 2 + 1
        fig, axes = plt.subplots(n_rows, 1, figsize=(20, 4 * n_rows))
        if n_rows == 1:
            axes = [axes]

        start_info = f"{self.config.get('start_date','?')} {self.config.get('start_time','?')}"
        fig.suptitle(
            f'DR200/HE Holter ECG | Patient {self.config.get("patient_id","?").strip()}\n'
            f'Recording: {start_info} | SR={SAMPLE_RATE}Hz | '
            f'{self.duration_sec:.0f}s ({self.duration_sec/60:.1f} min) | '
            f'SN={self.config.get("Serial_number","?")}',
            fontsize=11
        )

        n_plot = min(int(max_sec * SAMPLE_RATE), len(self.time_sec))
        t = self.time_sec[:n_plot]

        for i, (ch_uv, mask) in enumerate(zip(self.channels_uv, self.lead_off_mask)):
            ch_seg = ch_uv[:n_plot]
            mask_seg = mask[:n_plot]

            # Raw
            ax_raw = axes[i * 2]
            ax_raw.plot(t, ch_seg / 1000, lw=0.4, color='steelblue', alpha=0.8)
            if mask_seg.any():
                ymin, ymax = ch_seg.min()/1000 - 0.5, ch_seg.max()/1000 + 0.5
                ax_raw.fill_between(t, ymin, ymax, where=mask_seg,
                                    color='red', alpha=0.2, label='Lead-off')
            ax_raw.set_title(f'Channel {i} - Raw (mV)', fontsize=9)
            ax_raw.set_ylabel('mV')
            ax_raw.grid(True, alpha=0.3)
            ax_raw.legend(fontsize=8)

            # Filtered
            ax_filt = axes[i * 2 + 1]
            filled = ch_seg.copy()
            if (~mask_seg).any():
                filled[mask_seg] = np.median(ch_seg[~mask_seg])
            filt = bpf(filled)
            filt[mask_seg] = np.nan
            ax_filt.plot(t, filt / 1000, lw=0.6, color='navy')
            ax_filt.set_title(f'Channel {i} - Bandpass 0.5-40 Hz (mV)', fontsize=9)
            ax_filt.set_ylabel('mV')
            ax_filt.grid(True, alpha=0.3)

        # FFT
        ax_fft = axes[-1]
        from numpy.fft import rfft, rfftfreq
        ch0 = self.channels_uv[0]
        valid = ch0[~self.lead_off_mask[0]]
        if len(valid) > 0:
            fft_mag = np.abs(rfft(valid - valid.mean()))
            freqs = rfftfreq(len(valid), d=1/SAMPLE_RATE)
            mask_f = freqs <= 30
            ax_fft.semilogy(freqs[mask_f], fft_mag[mask_f], lw=0.6, color='purple')
            ax_fft.axvspan(0.8, 3.0, alpha=0.15, color='green', label='HR 48-180 bpm')
            ax_fft.set_xlabel('Frequency (Hz)')
            ax_fft.set_ylabel('Magnitude (log)')
            ax_fft.set_title('FFT Spectrum (Ch0)')
            ax_fft.legend(fontsize=8)
            ax_fft.grid(True, alpha=0.3)

        for ax in axes[:-1]:
            ax.set_xlabel('Time (s)')

        plt.tight_layout()
        plt.savefig(out_path, dpi=130, bbox_inches='tight')
        print(f'Saved plot: {out_path}')


# =================== MAIN ===================
if __name__ == '__main__':
    import sys
    flash_dat = sys.argv[1] if len(sys.argv) > 1 else 'C:/Users/TSIC/Documents/GitHub/Heart/flash.dat'
    out_dir   = sys.argv[2] if len(sys.argv) > 2 else 'C:/Users/TSIC/Documents/GitHub/Heart/output'

    parser = DR200Parser(flash_dat)

    os.makedirs(out_dir, exist_ok=True)
    parser.save_csv(os.path.join(out_dir, 'ecg_data.csv'))
    parser.save_ibf(os.path.join(out_dir, 'ibf'))
    parser.plot(os.path.join(out_dir, 'ecg_overview.png'), max_sec=60)

    print('\nDone! Output files:')
    for root, dirs, files in os.walk(out_dir):
        for fn in files:
            fp = os.path.join(root, fn)
            print(f'  {fp}  ({os.path.getsize(fp):,} bytes)')
