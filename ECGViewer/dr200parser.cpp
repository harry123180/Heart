#include "dr200parser.h"
#include <QFile>
#include <QTextStream>
#include <algorithm>

// ─── public entry point ───────────────────────────────────────────────────────

ECGData DR200Parser::parse(const QString& filepath) {
    ECGData out;

    QFile f(filepath);
    if (!f.open(QIODevice::ReadOnly)) {
        out.errorMsg = "Cannot open file: " + filepath;
        return out;
    }
    QByteArray raw = f.readAll();
    f.close();

    int totalBlocks = raw.size() / BLOCK_SIZE;
    if (totalBlocks < 4) {
        out.errorMsg = "File too small (< 4 blocks)";
        return out;
    }

    // BUG FIX #2: parse only blocks 0-2 for config (not 0-3)
    parseConfig(raw, out);

    out.sampleRate  = out.rawConfig.value("SampleRate", "180").toDouble();
    out.numChannels = out.rawConfig.value("SampleStorageFormat", "1").toInt();
    if (out.numChannels < 1 || out.numChannels > 8) out.numChannels = 1;

    // BUG FIX #3: efficient data bounds scan — stop after MAX_ZERO_BLOCKS consecutive zeros
    int lastBlock = findLastDataBlock(raw);
    if (lastBlock < 3) {
        // Empty recording: config is present but no ECG data was written.
        // Return valid with zero channels so the viewer can show metadata.
        out.numBlocks    = 0;
        out.totalSamples = 0;
        out.durationSec  = 0.0;
        out.numChannels  = qMax(1, out.numChannels);
        out.channels_uv.resize(out.numChannels);
        out.leadOff.resize(out.numChannels);
        out.rawConfig["_filepath"] = filepath;
        out.valid = true;
        return out;
    }
    out.numBlocks = lastBlock - 3 + 1;

    // Collect raw ECG bytes (first ECG_BYTES per block only — diary region excluded)
    QByteArray ecgRaw;
    ecgRaw.reserve(out.numBlocks * ECG_BYTES);
    for (int bi = 3; bi <= lastBlock; bi++) {
        int off = bi * BLOCK_SIZE + DATA_OFFSET;
        ecgRaw.append(raw.constData() + off, ECG_BYTES);
    }

    // Decode 12-bit LE packed samples
    QVector<int32_t> adcVals = decode12bitLE(
        reinterpret_cast<const uint8_t*>(ecgRaw.constData()), ecgRaw.size());

    int nCh  = out.numChannels;
    int nTot = adcVals.size();
    // Trim to multiple of nCh
    nTot = (nTot / nCh) * nCh;

    out.totalSamples = nTot / nCh;
    out.durationSec  = out.totalSamples / out.sampleRate;

    // Allocate channels
    out.channels_uv.resize(nCh);
    out.leadOff.resize(nCh);
    for (int ch = 0; ch < nCh; ch++) {
        out.channels_uv[ch].resize(out.totalSamples);
        out.leadOff[ch].resize(out.totalSamples);
    }

    // De-interleave and convert
    // Samples are stored: ch0, ch1, ..., ch(N-1), ch0, ch1, ...
    for (int sample = 0; sample < out.totalSamples; sample++) {
        for (int ch = 0; ch < nCh; ch++) {
            int32_t adc = adcVals[sample * nCh + ch];
            out.leadOff[ch][sample]    = (adc == LEAD_OFF_ADC);
            out.channels_uv[ch][sample] = (float)((adc - ADC_CENTER) * UV_PER_LSB);
        }
    }

    out.rawConfig["_filepath"] = filepath;
    out.valid = true;
    return out;
}

// ─── config parsing ───────────────────────────────────────────────────────────

void DR200Parser::parseConfig(const QByteArray& raw, ECGData& out) {
    QString text;
    // Only blocks 0, 1, 2 are config
    for (int bi = 0; bi < 3; bi++) {
        int off = bi * BLOCK_SIZE + 4; // skip 4-byte magic
        int len = BLOCK_SIZE - 8;
        const char* ptr = raw.constData() + off;
        // read up to null terminator
        int nullPos = -1;
        for (int i = 0; i < len; i++) {
            if (ptr[i] == 0) { nullPos = i; break; }
        }
        if (nullPos >= 0)
            text += QString::fromLatin1(ptr, nullPos);
        else
            text += QString::fromLatin1(ptr, len);
    }

    for (const QString& line : text.split('\n')) {
        QString l = line.trimmed().remove('\r');
        int eq = l.indexOf('=');
        if (eq > 0) {
            QString key = l.left(eq).trimmed();
            QString val = l.mid(eq + 1).trimmed();
            out.rawConfig[key] = val;
        }
    }

    out.patientId    = out.rawConfig.value("patient_id").trimmed();
    out.startDate    = out.rawConfig.value("start_date").trimmed();
    out.startTime    = out.rawConfig.value("start_time").trimmed();
    out.serialNumber = out.rawConfig.value("Serial_number").trimmed();
    out.firmware     = out.rawConfig.value("Recorder_version").trimmed();

    QString diary = out.rawConfig.value("DiaryText");
    for (const QString& e : diary.split('^'))
        if (!e.trimmed().isEmpty()) out.diaryEvents << e.trimmed();
}

// ─── data bounds detection ────────────────────────────────────────────────────

int DR200Parser::findLastDataBlock(const QByteArray& raw) {
    int totalBlocks = raw.size() / BLOCK_SIZE;
    int lastActive  = 2; // will be updated if any data block found
    int zeroStreak  = 0;

    for (int bi = 3; bi < totalBlocks; bi++) {
        int off = bi * BLOCK_SIZE + DATA_OFFSET;
        const char* ptr = raw.constData() + off;

        bool hasData = false;
        for (int i = 0; i < ECG_BYTES; i++) {
            if (ptr[i] != 0) { hasData = true; break; }
        }

        if (hasData) {
            lastActive = bi;
            zeroStreak = 0;
        } else {
            zeroStreak++;
            // BUG FIX #3: stop early after consecutive zero blocks
            if (zeroStreak >= MAX_ZERO_BLOCKS) break;
        }
    }
    return lastActive;
}

// ─── 12-bit LE decoder ────────────────────────────────────────────────────────

QVector<int32_t> DR200Parser::decode12bitLE(const uint8_t* buf, int byteCount) {
    int pairs = (byteCount / 3);
    QVector<int32_t> out;
    out.reserve(pairs * 2);

    for (int i = 0; i < pairs; i++) {
        uint8_t b0 = buf[i * 3 + 0];
        uint8_t b1 = buf[i * 3 + 1];
        uint8_t b2 = buf[i * 3 + 2];
        out.append((int32_t)(b0 | ((b1 & 0x0F) << 8)));
        out.append((int32_t)((b1 >> 4) | (b2 << 4)));
    }
    return out;
}
