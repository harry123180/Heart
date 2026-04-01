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
    double sampleRate  = 180.0;
    int    numChannels = 1;
    double durationSec = 0.0;
    int    totalSamples = 0;
    int    numBlocks    = 0;

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

    // Locate unpackdc.exe (checks standard paths)
    static QString findUnpackdc();

private:
    static constexpr int BLOCK_SIZE      = 512;
    static constexpr int DATA_OFFSET     = 10;
    static constexpr int ECG_BYTES       = 460;

    // IBF format from unpackdc: int16 LE, 12.5 uV/LSB (per NE Monitoring IBF spec)
    static constexpr double IBF_UV_PER_LSB = 12.5;
    static constexpr int    IBF_LEAD_OFF   = -32768; // INT16_MIN = sentinel

    static void parseConfig(const QByteArray& raw, ECGData& out);
    static int  findLastDataBlock(const QByteArray& raw);

    // High-pass filter: subtract running mean over windowSamples
    static QVector<float> hpFilter(const QVector<float>& in, int windowSamples);
};
