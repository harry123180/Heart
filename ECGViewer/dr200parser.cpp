#include "dr200parser.h"
#include <QFile>
#include <QDir>
#include <QProcess>
#include <QTemporaryFile>
#include <QCoreApplication>
#include <QTextStream>
#include <algorithm>
#include <cstdint>

// ─── Locate unpackdc.exe ──────────────────────────────────────────────────────

QString DR200Parser::findUnpackdc() {
    QStringList candidates = {
        R"(C:\nm\bin\unpackdc.exe)",
        QCoreApplication::applicationDirPath() + "/unpackdc.exe",
        QCoreApplication::applicationDirPath() + "/../nm/bin/unpackdc.exe",
    };
    for (const QString& p : candidates) {
        if (QFile::exists(p)) return p;
    }
    return {};
}

// ─── public entry point ───────────────────────────────────────────────────────

ECGData DR200Parser::parse(const QString& filepath) {
    ECGData out;

    // --- Step 1: open & validate file ---
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

    // --- Step 2: parse config (blocks 0-2) ---
    parseConfig(raw, out);
    out.sampleRate  = out.rawConfig.value("SampleRate", "180").toDouble();
    out.numChannels = 1; // DR200/HE: single ECG channel

    // --- Step 3: find valid data range ---
    int lastBlock = findLastDataBlock(raw);
    if (lastBlock < 3) {
        out.numBlocks    = 0;
        out.totalSamples = 0;
        out.durationSec  = 0.0;
        out.channels_uv.resize(1);
        out.leadOff.resize(1);
        out.rawConfig["_filepath"] = filepath;
        out.valid = true;
        return out;
    }
    out.numBlocks = lastBlock - 3 + 1;

    // --- Step 4: write truncated copy to temp (unpackdc ERASES its input) ---
    QString unpackdc = findUnpackdc();
    if (unpackdc.isEmpty()) {
        out.errorMsg = "unpackdc.exe not found. Place it at C:\\nm\\bin\\unpackdc.exe";
        return out;
    }

    QTemporaryFile tmpDat;
    tmpDat.setFileTemplate(QDir::tempPath() + "/flash_XXXXXX.dat");
    if (!tmpDat.open()) {
        out.errorMsg = "Cannot create temp file";
        return out;
    }
    int validBytes = (lastBlock + 1) * BLOCK_SIZE;
    tmpDat.write(raw.constData(), validBytes);
    tmpDat.close(); // flush, but keep file (setAutoRemove is true by default)

    QString tmpPath = tmpDat.fileName();

    // --- Step 5: run unpackdc on the temp copy ---
    QString ch0Path = QDir::tempPath() + "/ecg_ch0.ibf";
    QString ch1Path = QDir::tempPath() + "/ecg_ch1.ibf";
    QString ch2Path = QDir::tempPath() + "/ecg_ch2.ibf";

    // Remove old IBF files if present
    QFile::remove(ch0Path);
    QFile::remove(ch1Path);
    QFile::remove(ch2Path);

    QProcess proc;
    proc.start(unpackdc, {tmpPath, ch0Path, ch1Path, ch2Path, "0"});
    if (!proc.waitForFinished(120000)) {
        out.errorMsg = "unpackdc timed out";
        return out;
    }
    if (proc.exitCode() != 0) {
        out.errorMsg = QString("unpackdc failed (exit %1)").arg(proc.exitCode());
        return out;
    }

    // --- Step 6: read IBF ch0 (int16 LE) ---
    QFile ibf0(ch0Path);
    if (!ibf0.open(QIODevice::ReadOnly) || ibf0.size() == 0) {
        out.errorMsg = "IBF ch0 empty or missing after unpackdc";
        return out;
    }
    QByteArray ibfRaw = ibf0.read(out.numBlocks * 400 * 2 + 4096); // generous read
    ibf0.close();

    int nSamples = ibfRaw.size() / 2; // int16 = 2 bytes each
    const int16_t* ibfData = reinterpret_cast<const int16_t*>(ibfRaw.constData());

    // --- Step 7: convert int16 -> float uV, mark lead-off ---
    QVector<float> raw_uv(nSamples);
    QVector<bool>  lo(nSamples, false);

    for (int i = 0; i < nSamples; i++) {
        int16_t v = ibfData[i];
        if (v == (int16_t)IBF_LEAD_OFF) {
            lo[i]     = true;
            raw_uv[i] = 0.0f; // placeholder; display will skip these
        } else {
            raw_uv[i] = (float)(v * IBF_UV_PER_LSB);
        }
    }

    // --- Step 8: high-pass filter (remove DC electrode polarization) ---
    // Window = 1 second = sampleRate samples
    int hpWindow = (int)out.sampleRate;
    QVector<float> hp_uv = hpFilter(raw_uv, hpWindow);

    // Zero out lead-off positions in filtered signal
    for (int i = 0; i < nSamples; i++) {
        if (lo[i]) hp_uv[i] = 0.0f;
    }

    // --- Step 9: populate ECGData ---
    out.totalSamples = nSamples;
    out.durationSec  = nSamples / out.sampleRate;
    out.channels_uv.resize(1);
    out.leadOff.resize(1);
    out.channels_uv[0] = hp_uv;
    out.leadOff[0]     = lo;

    out.rawConfig["_filepath"]  = filepath;
    out.rawConfig["_ibf_path"]  = ch0Path;
    out.rawConfig["_ibf_samples"] = QString::number(nSamples);
    out.valid = true;
    return out;
}

// ─── high-pass filter ─────────────────────────────────────────────────────────

QVector<float> DR200Parser::hpFilter(const QVector<float>& in, int windowSamples) {
    int n = in.size();
    QVector<float> out(n, 0.0f);
    if (n == 0) return out;

    // O(n) sliding-window boxcar HP filter (centred, symmetric)
    // LP = running mean over [-half, +half]; HP = signal - LP
    int half = windowSamples / 2;
    double winSum = 0.0;
    int    winCnt = 0;

    // Pre-load the first [0, half] samples into the window
    for (int i = 0; i <= std::min(half, n - 1); i++) {
        winSum += in[i];
        winCnt++;
    }

    for (int i = 0; i < n; i++) {
        // Advance right edge of window
        int addIdx = i + half + 1;
        if (addIdx < n) { winSum += in[addIdx]; winCnt++; }

        // Retire left edge of window
        int removeIdx = i - half;
        if (removeIdx > 0) { winSum -= in[removeIdx - 1]; winCnt--; }

        out[i] = (winCnt > 0) ? in[i] - (float)(winSum / winCnt) : 0.0f;
    }
    return out;
}

// ─── config parsing ───────────────────────────────────────────────────────────

void DR200Parser::parseConfig(const QByteArray& raw, ECGData& out) {
    QString text;
    for (int bi = 0; bi < 3; bi++) {
        int off = bi * BLOCK_SIZE + 4;
        int len = BLOCK_SIZE - 8;
        const char* ptr = raw.constData() + off;
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
            out.rawConfig[l.left(eq).trimmed()] = l.mid(eq + 1).trimmed();
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
    int lastActive  = 2;
    uint32_t prevCounter = 0;

    for (int bi = 3; bi < totalBlocks; bi++) {
        const uint8_t* blk = reinterpret_cast<const uint8_t*>(raw.constData()) + bi * BLOCK_SIZE;

        // Validate block magic: must be 00 02 00 00 1E 00
        if (blk[0] != 0x00 || blk[1] != 0x02 || blk[2] != 0x00 || blk[3] != 0x00 ||
            blk[4] != 0x1E || blk[5] != 0x00)
            break;

        uint32_t counter = static_cast<uint32_t>(blk[6])
                         | (static_cast<uint32_t>(blk[7]) << 8)
                         | (static_cast<uint32_t>(blk[8]) << 16)
                         | (static_cast<uint32_t>(blk[9]) << 24);

        if (bi == 3) {
            // Accept any starting counter value (firmware version may differ)
            prevCounter = counter;
        } else {
            // Counter must increment by exactly 1216 each block
            if (counter != prevCounter + 1216)
                break;
            prevCounter = counter;
        }

        lastActive = bi;
    }
    return lastActive;
}
