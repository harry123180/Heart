#include "spectrumview.h"
#include <QPainter>
#include <QPen>
#include <QWheelEvent>
#include <QMouseEvent>
#include <QContextMenuEvent>
#include <QMenu>
#include <QActionGroup>
#include <QtConcurrent/QtConcurrent>
#include <cmath>
#include <algorithm>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// HR frequency bands (Hz) with clinical meaning
struct Band { double fLo, fHi; const char* name; const char* bpm; };
static constexpr Band BANDS[] = {
    { 0.8,  3.0, "\345\277\203\347\216\207\345\270\266", "48\342\200\22\302\240180 bpm" },  // 心率帶
};

SpectrumView::SpectrumView(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setMinimumSize(300, 200);
    connect(&m_watcher, &QFutureWatcher<SpectrumResult>::finished,
            this, &SpectrumView::onFftDone);
}

SpectrumView::~SpectrumView() {
    m_watcher.cancel();
    m_watcher.waitForFinished();
}

void SpectrumView::clear() {
    m_watcher.cancel();
    m_result = {};
    m_computing = false;
    m_bufDirty  = true;
    update();
}

void SpectrumView::setDarkMode(bool dark) {
    m_dark     = dark;
    m_bufDirty = true;
    update();
}

// ─── setData ─────────────────────────────────────────────────────────────────

void SpectrumView::setData(const QVector<float>& samples_uv,
                           const QVector<bool>&  leadOff,
                           double sampleRate) {
    m_watcher.cancel();
    m_watcher.waitForFinished();

    m_sr        = sampleRate;
    m_fMax      = qMin(sampleRate / 2.0, 60.0);
    m_fMin      = 0.0;
    m_computing = true;
    m_result    = {};
    m_bufDirty  = true;
    update();

    QVector<float> sig;
    sig.reserve(samples_uv.size());
    {
        float median = 0;
        QVector<float> valid;
        valid.reserve(samples_uv.size());
        for (int i = 0; i < samples_uv.size(); i++)
            if (i >= leadOff.size() || !leadOff[i]) valid.append(samples_uv[i]);
        if (!valid.isEmpty()) {
            std::nth_element(valid.begin(), valid.begin() + valid.size()/2, valid.end());
            median = valid[valid.size()/2];
        }
        for (int i = 0; i < samples_uv.size(); i++) {
            bool lo = (i < leadOff.size()) && leadOff[i];
            sig.append(lo ? median : samples_uv[i]);
        }
    }

    QFuture<SpectrumResult> fut = QtConcurrent::run(SpectrumView::compute, sig, sampleRate);
    m_watcher.setFuture(fut);
}

void SpectrumView::onFftDone() {
    m_result    = m_watcher.result();
    m_computing = false;
    m_bufDirty  = true;
    update();
}

// ─── FFT worker ───────────────────────────────────────────────────────────────

void SpectrumView::fftInPlace(std::vector<std::complex<double>>& x) {
    int n = (int)x.size();
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(x[i], x[j]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = -2.0 * M_PI / len;
        std::complex<double> wlen(std::cos(ang), std::sin(ang));
        for (int i = 0; i < n; i += len) {
            std::complex<double> w(1.0);
            for (int j = 0; j < len/2; j++) {
                auto u = x[i+j], v = x[i+j+len/2]*w;
                x[i+j] = u+v; x[i+j+len/2] = u-v;
                w *= wlen;
            }
        }
    }
}

SpectrumResult SpectrumView::compute(QVector<float> sig, double sr) {
    SpectrumResult res;
    if (sig.isEmpty()) return res;

    int n = sig.size();
    int N = 1;
    while (N < n && N < 65536) N <<= 1;

    double mean = 0;
    for (float v : sig) mean += v;
    mean /= n;

    std::vector<std::complex<double>> cx(N, 0);
    for (int i = 0; i < qMin(n, N); i++) {
        double w = 0.5 * (1.0 - std::cos(2.0*M_PI*i/(N-1)));
        cx[i] = {(sig[i]-mean)*w, 0.0};
    }

    fftInPlace(cx);

    int half = N/2 + 1;
    double norm = 2.0 / N;
    res.freqs.reserve(half);
    res.mag.reserve(half);

    double peakMag = 0;
    res.magMax = 1e-12;

    for (int k = 0; k < half; k++) {
        double f   = (double)k * sr / N;
        double mag = std::abs(cx[k]) * norm;
        res.freqs.append(f);
        res.mag.append(mag);
        res.magMax = qMax(res.magMax, mag);
        if (f >= 0.5 && f <= 4.0 && mag > peakMag) {
            peakMag = mag;
            res.peakHz = f;
        }
    }

    res.logMin = std::log10(res.magMax * 0.001);
    res.logMax = std::log10(res.magMax * 1.5);

    return res;
}

// ─── coordinates ─────────────────────────────────────────────────────────────

QRect SpectrumView::plotRect() const {
    return QRect(ML, MT, width()-ML-MR, height()-MT-MB);
}

double SpectrumView::dataToPixelX(double f) const {
    QRect pr = plotRect();
    if (m_xMode == XMode::Log) {
        double fLo = qMax(m_fMin, 0.01);
        double fHi = qMax(m_fMax, fLo + 0.1);
        if (f <= 0) return pr.left();
        double t = (std::log10(f) - std::log10(fLo)) / (std::log10(fHi) - std::log10(fLo));
        return pr.left() + t * pr.width();
    }
    double range = m_fMax - m_fMin;
    return pr.left() + (range > 0 ? (f - m_fMin) / range : 0.0) * pr.width();
}

double SpectrumView::dataToPixelY(double mag) const {
    QRect pr = plotRect();
    double t = 0;
    if (m_yMode == YMode::Log) {
        double lm = (mag > 0) ? std::log10(mag) : m_result.logMin;
        t = (qBound(m_result.logMin, lm, m_result.logMax) - m_result.logMin)
            / (m_result.logMax - m_result.logMin);
    } else if (m_yMode == YMode::Linear) {
        t = (m_result.magMax > 0) ? mag / m_result.magMax : 0.0;
        t = qBound(0.0, t, 1.0);
    } else {  // dB
        double db = (mag > 0 && m_result.magMax > 0)
                    ? 20.0 * std::log10(mag / m_result.magMax)
                    : -60.0;
        t = (db + 60.0) / 60.0;
        t = qBound(0.0, t, 1.0);
    }
    return pr.bottom() - t * pr.height();
}

double SpectrumView::pixelToFreq(int px) const {
    QRect pr = plotRect();
    if (m_xMode == XMode::Log) {
        double fLo = qMax(m_fMin, 0.01);
        double fHi = qMax(m_fMax, fLo + 0.1);
        double t = (double)(px - pr.left()) / pr.width();
        return std::pow(10.0, std::log10(fLo) + t * (std::log10(fHi) - std::log10(fLo)));
    }
    return m_fMin + (double)(px - pr.left()) / pr.width() * (m_fMax - m_fMin);
}

// ─── mouse ────────────────────────────────────────────────────────────────────

void SpectrumView::wheelEvent(QWheelEvent* e) {
    double factor = std::pow(0.80, e->angleDelta().y()/120.0);
    double f      = pixelToFreq(e->pos().x());
    double range  = m_fMax - m_fMin;
    double newR   = range * factor;
    double ratio  = (range > 0) ? (f - m_fMin) / range : 0.5;
    m_fMin = f - ratio * newR;
    m_fMax = m_fMin + newR;
    m_fMin = qMax(0.0, m_fMin);
    m_fMax = qMin(m_sr / 2.0, qMax(m_fMin + 0.5, m_fMax));
    m_bufDirty = true;
    update();
}

void SpectrumView::mouseMoveEvent(QMouseEvent* e) {
    m_hover     = e->pos();
    m_showHover = plotRect().contains(e->pos());
    update();
}

void SpectrumView::mouseDoubleClickEvent(QMouseEvent*) {
    m_fMin = 0; m_fMax = qMin(m_sr / 2.0, 60.0);
    m_bufDirty = true;
    update();
}

void SpectrumView::contextMenuEvent(QContextMenuEvent* e) {
    QMenu menu(this);
    menu.setTitle("顯示設定");

    // ── Y 軸模式 ──
    QMenu* yMenu = menu.addMenu("Y 軸：顯示模式");
    QActionGroup* yGrp = new QActionGroup(&menu);
    yGrp->setExclusive(true);
    auto addY = [&](const QString& label, YMode mode) {
        auto a = yMenu->addAction(label, [this, mode]{ m_yMode = mode; m_bufDirty = true; update(); });
        a->setCheckable(true);
        a->setChecked(m_yMode == mode);
        yGrp->addAction(a);
    };
    addY("對數（Log）",   YMode::Log);
    addY("線性（Linear）", YMode::Linear);
    addY("分貝（dB）",    YMode::dB);

    // ── X 軸模式 ──
    QMenu* xMenu = menu.addMenu("X 軸：頻率刻度");
    QActionGroup* xGrp = new QActionGroup(&menu);
    xGrp->setExclusive(true);
    auto addX = [&](const QString& label, XMode mode) {
        auto a = xMenu->addAction(label, [this, mode]{ m_xMode = mode; m_bufDirty = true; update(); });
        a->setCheckable(true);
        a->setChecked(m_xMode == mode);
        xGrp->addAction(a);
    };
    addX("線性（Linear Hz）", XMode::Linear);
    addX("對數（Log Hz）",    XMode::Log);

    menu.addSeparator();

    // ── 快速頻率範圍 ──
    QMenu* rMenu = menu.addMenu("快速頻率範圍");
    auto addR = [&](const QString& lbl, double lo, double hi) {
        rMenu->addAction(lbl, [this, lo, hi]{ m_fMin=lo; m_fMax=hi; m_bufDirty=true; update(); });
    };
    addR("0 – 5 Hz（心率）",    0,  5);
    addR("0 – 15 Hz（ECG）",    0, 15);
    addR("0 – 30 Hz（標準）",   0, 30);
    addR("0 – 60 Hz（全頻）",   0, 60);

    menu.exec(e->globalPos());
}

void SpectrumView::leaveEvent(QEvent*) { m_showHover = false; update(); }
void SpectrumView::resizeEvent(QResizeEvent*) { m_bufDirty = true; update(); }

// ─── paint ────────────────────────────────────────────────────────────────────

void SpectrumView::paintEvent(QPaintEvent*) {
    if (m_bufDirty || m_buffer.size() != size()) {
        m_buffer = QPixmap(size());
        QPainter bp(&m_buffer);
        drawSpectrum(bp);
        m_bufDirty = false;
    }
    QPainter p(this);
    p.drawPixmap(0, 0, m_buffer);
    if (m_showHover && !m_result.freqs.isEmpty()) drawCrosshair(p);
}

// ─── spectrum drawing ─────────────────────────────────────────────────────────

void SpectrumView::drawSpectrum(QPainter& p) {
    QRect pr = plotRect();

    QColor bg     = m_dark ? QColor(0x060E18) : QColor(0xF8F8FF);
    QColor plotBg = m_dark ? QColor(0x0D1B2A) : QColor(0xFAF8FF);
    QColor txtCol = m_dark ? QColor(0x90CAF9) : QColor(0x333333);
    QColor gridC  = m_dark ? QColor(0x1A2A3A) : QColor(0xDDDDDD);
    QColor sigC   = m_dark ? QColor(0xCE93D8) : QColor(0x6A1B9A);

    p.fillRect(rect(), bg);
    p.fillRect(pr, plotBg);

    // Title
    QFont tf = p.font(); tf.setPointSize(9); tf.setBold(true); p.setFont(tf);
    p.setPen(txtCol);
    if (m_computing) {
        p.drawText(QRect(0,0,width(),MT), Qt::AlignCenter, "頻譜計算中...");
        p.setPen(QColor(0x888888));
        p.drawText(pr, Qt::AlignCenter, "請稍候，正在執行 FFT 運算...");
        return;
    }
    if (m_result.freqs.isEmpty()) {
        QFont hf = p.font(); hf.setPointSize(11); hf.setBold(false); p.setFont(hf);
        p.setPen(QColor(0xAAAAAA));
        p.drawText(pr, Qt::AlignCenter, "請載入 .dat 檔案以計算頻譜");
        return;
    }

    QString modeStr;
    if      (m_yMode == YMode::Log)    modeStr = "Y:對數";
    else if (m_yMode == YMode::Linear) modeStr = "Y:線性";
    else                               modeStr = "Y:dB";
    if (m_xMode == XMode::Log) modeStr += " X:對數";

    p.drawText(QRect(0,0,width(),MT), Qt::AlignCenter,
               QString("功率頻譜  |  心率峰值：%1 Hz = %2 bpm  [%3]")
                   .arg(m_result.peakHz,0,'f',2).arg(m_result.peakHz*60,0,'f',0).arg(modeStr));

    // ── Heart rate band shading (0.8–3.0 Hz) with label ──
    {
        double x0 = dataToPixelX(qMax(0.8, m_fMin));
        double x1 = dataToPixelX(qMin(3.0, m_fMax));
        if (x1 > x0 + 2) {
            p.fillRect(QRectF(x0, pr.top(), x1-x0, pr.height()),
                       m_dark ? QColor(0,100,0,55) : QColor(80,200,80,35));
            // Band label inside the shaded area
            QFont bf = p.font(); bf.setPointSize(7); bf.setBold(false); p.setFont(bf);
            p.setPen(m_dark ? QColor(0,200,80,180) : QColor(0,120,0,200));
            double midX = (x0 + x1) / 2.0;
            p.drawText(QRectF(x0+2, pr.top()+4, x1-x0-4, 28),
                       Qt::AlignHCenter | Qt::AlignTop | Qt::TextWordWrap,
                       "心率帶\n48\357\275\236180 bpm");
        }
    }

    // ── Grid ──
    double fRange = m_fMax - m_fMin;
    double fStep  = (fRange > 30) ? 5.0 : (fRange > 15) ? 2.0 : 1.0;
    {
        QVector<QLineF> glines;
        if (m_xMode == XMode::Linear) {
            for (double f = std::ceil(m_fMin/fStep)*fStep; f <= m_fMax; f += fStep)
                glines << QLineF(dataToPixelX(f), pr.top(), dataToPixelX(f), pr.bottom());
        } else {
            // Log grid at 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50 Hz
            for (double f : {0.1,0.2,0.5,1.0,2.0,5.0,10.0,20.0,50.0}) {
                if (f > m_fMin && f < m_fMax)
                    glines << QLineF(dataToPixelX(f), pr.top(), dataToPixelX(f), pr.bottom());
            }
        }
        p.setPen(QPen(gridC, 0.7));
        p.drawLines(glines);
    }

    // ── Spectrum curve ──
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setPen(QPen(sigC, 1.3));
    {
        int W = pr.width();
        QPolygonF poly;
        poly.reserve(W);
        int nBins = m_result.freqs.size();

        for (int col = 0; col < W; col++) {
            double f0 = pixelToFreq(pr.left() + col);
            double f1 = pixelToFreq(pr.left() + col + 1);

            int k0 = qBound(0, (int)(f0 / m_sr * 2 * (nBins-1)), nBins-1);
            int k1 = qBound(0, (int)(f1 / m_sr * 2 * (nBins-1)) + 1, nBins-1);

            double best = 0;
            for (int k = k0; k <= k1; k++)
                best = qMax(best, m_result.mag[k]);

            if (best > 0)
                poly << QPointF(pr.left() + col, dataToPixelY(best));
        }
        p.drawPolyline(poly);
    }
    p.setRenderHint(QPainter::Antialiasing, false);

    // ── HR band boundary dashed lines ──
    p.setPen(QPen(QColor(0x2E7D32), 1.2, Qt::DashLine));
    for (double f : {0.8, 3.0}) {
        if (f > m_fMin && f < m_fMax) {
            double px = dataToPixelX(f);
            p.drawLine(QLineF(px, pr.top(), px, pr.bottom()));
        }
    }

    // ── Peak annotation ──
    if (m_result.peakHz > m_fMin && m_result.peakHz < m_fMax) {
        double peakMag = 0;
        for (int k = 0; k < m_result.freqs.size(); k++) {
            if (std::abs(m_result.freqs[k] - m_result.peakHz) < 0.15) {
                peakMag = m_result.mag[k]; break;
            }
        }
        double px = dataToPixelX(m_result.peakHz);
        double py = dataToPixelY(peakMag);
        p.setPen(QPen(Qt::red, 1.5));
        p.drawLine(QLineF(px, pr.bottom(), px, py));
        QFont lf = p.font(); lf.setPointSize(8); lf.setBold(false); p.setFont(lf);
        p.setPen(Qt::red);
        p.drawText(QPointF(px+3, py+14),
                   QString("%1 Hz = %2 bpm").arg(m_result.peakHz,0,'f',2).arg(m_result.peakHz*60,0,'f',0));
    }

    // ── X axis labels ──
    QFont af = p.font(); af.setPointSize(8); af.setBold(false); p.setFont(af);
    p.setPen(txtCol);
    if (m_xMode == XMode::Linear) {
        for (double f = std::ceil(m_fMin/fStep)*fStep; f <= m_fMax; f += fStep) {
            double px = dataToPixelX(f);
            p.drawText(QRectF(px-20, pr.bottom()+4, 40, 14), Qt::AlignCenter,
                       QString::number(f,'f',f<10?1:0)+"Hz");
        }
    } else {
        for (double f : {0.1,0.2,0.5,1.0,2.0,5.0,10.0,20.0,50.0}) {
            if (f > m_fMin && f < m_fMax) {
                double px = dataToPixelX(f);
                p.drawText(QRectF(px-16, pr.bottom()+4, 32, 14), Qt::AlignCenter,
                           QString::number(f,'f',f<1?1:0)+"Hz");
            }
        }
    }
    p.drawText(QRect(0, height()-MB+28, width(), 14), Qt::AlignCenter, "頻率（Hz）— 右鍵切換顯示模式");

    // ── Y axis labels & mode annotation ──
    drawYAxisLabels(p);

    // ── Border ──
    p.setPen(QPen(m_dark ? QColor(0x2A4060) : QColor(0xBBBBCC), 1));
    p.drawRect(pr.adjusted(0,0,-1,-1));
}

void SpectrumView::drawYAxisLabels(QPainter& p) {
    QRect pr = plotRect();
    QColor txtCol = m_dark ? QColor(0x90CAF9) : QColor(0x333333);
    QFont af = p.font(); af.setPointSize(7); p.setFont(af);
    p.setPen(txtCol);

    if (m_yMode == YMode::dB) {
        // Fixed dB ticks: 0, -20, -40, -60
        for (int db = 0; db >= -60; db -= 20) {
            // t = (db + 60) / 60; py = pr.bottom - t * pr.height
            double t  = (db + 60.0) / 60.0;
            double py = pr.bottom() - t * pr.height();
            p.drawText(QRectF(0, py-7, ML-4, 14), Qt::AlignRight|Qt::AlignVCenter,
                       QString::number(db)+"dB");
        }
        p.drawText(QRect(2, MT, ML-4, pr.height()), Qt::AlignRight|Qt::AlignTop, "振幅\n(dB)");
    } else if (m_yMode == YMode::Linear) {
        // 5 evenly spaced ticks: 0%, 25%, 50%, 75%, 100%
        for (int pct = 0; pct <= 100; pct += 25) {
            double t  = pct / 100.0;
            double py = pr.bottom() - t * pr.height();
            p.drawText(QRectF(0, py-7, ML-4, 14), Qt::AlignRight|Qt::AlignVCenter,
                       QString::number(pct)+"%");
        }
        p.drawText(QRect(2, MT, ML-4, pr.height()), Qt::AlignRight|Qt::AlignTop, "振幅\n(線性)");
    } else {
        p.drawText(QRect(2, MT, ML-4, pr.height()), Qt::AlignRight|Qt::AlignTop, "振幅\n(對數)");
    }
}

// ─── crosshair ────────────────────────────────────────────────────────────────

void SpectrumView::drawCrosshair(QPainter& p) {
    QRect pr = plotRect();
    if (!pr.contains(m_hover)) return;

    double f = pixelToFreq(m_hover.x());

    QColor cc = m_dark ? QColor(0x64B5F6) : QColor(0x0055AA);
    p.setPen(QPen(cc, 1, Qt::DashLine));
    p.drawLine(m_hover.x(), pr.top(), m_hover.x(), pr.bottom());

    QFont lf = p.font(); lf.setPointSize(8); p.setFont(lf);
    p.setPen(m_dark ? QColor(0x90CAF9) : QColor(0x333333));

    QString info = (f > 0)
        ? QString("%1 Hz  =  %2 bpm").arg(f,0,'f',2).arg(f*60,0,'f',0)
        : QString("%1 Hz").arg(f,0,'f',2);
    int tw = p.fontMetrics().horizontalAdvance(info) + 8;
    int tx = (m_hover.x() + tw + 4 < pr.right()) ? m_hover.x()+4 : m_hover.x()-tw-4;
    QRect tbr(tx, pr.top()+4, tw, 16);
    p.fillRect(tbr, m_dark ? QColor(10,25,45,210) : QColor(255,255,220,210));
    p.drawText(tbr, Qt::AlignCenter, info);
}
