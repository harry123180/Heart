#pragma once
#include <QWidget>
#include <QPixmap>
#include <QVector>
#include <QFutureWatcher>
#include <complex>

struct SpectrumResult {
    QVector<double> freqs;   // Hz
    QVector<double> mag;     // linear magnitude
    double peakHz  = 0;
    double magMax  = 1.0;    // cached max — computed ONCE in worker thread
    double logMin  = 0;      // log10(magMax * 0.001) — cached
    double logMax  = 0;      // log10(magMax * 1.5)   — cached
};

class SpectrumView : public QWidget {
    Q_OBJECT
public:
    explicit SpectrumView(QWidget* parent = nullptr);
    ~SpectrumView();

    void setData(const QVector<float>& samples_uv,
                 const QVector<bool>&  leadOff,
                 double sampleRate);
    void setDarkMode(bool dark);
    void clear();

    // Y-axis display modes
    enum class YMode { Log, Linear, dB };
    // X-axis scale modes
    enum class XMode { Linear, Log };

protected:
    void paintEvent(QPaintEvent*) override;
    void wheelEvent(QWheelEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mouseDoubleClickEvent(QMouseEvent*) override;
    void contextMenuEvent(QContextMenuEvent*) override;
    void leaveEvent(QEvent*) override;
    void resizeEvent(QResizeEvent*) override;

private slots:
    void onFftDone();

private:
    SpectrumResult m_result;
    double m_sr   = 180.0;
    double m_fMin = 0.0, m_fMax = 30.0;
    bool   m_computing = false;
    bool   m_dark = false;

    YMode  m_yMode = YMode::Log;
    XMode  m_xMode = XMode::Linear;

    QPixmap m_buffer;
    bool    m_bufDirty = true;

    QPoint m_hover;
    bool   m_showHover = false;

    QFutureWatcher<SpectrumResult> m_watcher;

    static constexpr int ML=60, MR=12, MT=30, MB=46;

    QRect  plotRect() const;
    double dataToPixelX(double f) const;
    double dataToPixelY(double mag) const;
    double pixelToFreq(int px) const;

    void drawSpectrum(QPainter& p);
    void drawCrosshair(QPainter& p);
    void drawYAxisLabels(QPainter& p);

    static SpectrumResult compute(QVector<float> sig, double sr);
    static void fftInPlace(std::vector<std::complex<double>>& x);
};
