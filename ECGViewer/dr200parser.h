#pragma once
#include <QString>
#include <QVector>
#include <QMap>
#include <QStringList>

struct ECGData {
    // Config
    QString patientId;
    QString startDate;
    QString startTime;
    QString serialNumber;
    QString firmware;
    QStringList diaryEvents;
    QMap<QString, QString> rawConfig;

    // Recording params
    double sampleRate = 180.0;
    int    numChannels = 1;
    double durationSec = 0.0;
    int    totalSamples = 0;
    int    numBlocks = 0;

    // Signal data: [channel][sample index]  unit = microvolts
    QVector<QVector<float>> channels_uv;
    // Lead-off mask: [channel][sample index]
    QVector<QVector<bool>>  leadOff;

    bool    valid = false;
    QString errorMsg;
};

class DR200Parser {
public:
    static ECGData parse(const QString& filepath);

private:
    // Block layout constants
    static constexpr int BLOCK_SIZE   = 512;
    static constexpr int DATA_OFFSET  = 10;
    // BUG FIX #1: only first 460 bytes are ECG samples; last 38 bytes are diary events
    static constexpr int ECG_BYTES    = 460;
    static constexpr int LEAD_OFF_ADC = 0x777; // = 1911
    static constexpr double UV_PER_LSB = 12.5;
    static constexpr int ADC_CENTER    = 2048;
    static constexpr int MAX_ZERO_BLOCKS = 20; // stop scan after this many consecutive zero blocks

    // Internal helpers (operate on raw file bytes)
    static void parseConfig(const QByteArray& raw, ECGData& out);
    static int  findLastDataBlock(const QByteArray& raw);
    static QVector<int32_t> decode12bitLE(const uint8_t* buf, int byteCount);
};
