#pragma once
#include <QWidget>
#include <QPixmap>
#include <QVector>
#include <QPair>

// ECG viewer — layered rendering:
//   m_buffer:      background + grid + lead-off + labels  (no signal)
//   m_signalStrip: pre-rendered signal curve for wide time range
//
// Pan = O(pixels) blit of signal strip sub-rect — zero signal recalculation.
// Signal strip is rebuilt ONLY when Y range or data changes.
class EcgView : public QWidget {
    Q_OBJECT
public:
    explicit EcgView(QWidget* parent = nullptr);

    void setData(const QVector<float>& samples_uv,
                 const QVector<bool>&  leadOff,
                 double sampleRate);

    void setDarkMode(bool dark);
    void resetView();
    void autoScaleY();
    void setViewRange(double xMin, double xMax);

    double viewXMin()      const { return m_xMin; }
    double viewXMax()      const { return m_xMax; }
    double totalDuration() const;

signals:
    void viewChanged(double xMin, double xMax);
    void sampleHovered(double time_s, double value_uv, bool onSignal);

protected:
    void paintEvent(QPaintEvent*) override;
    void wheelEvent(QWheelEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mouseDoubleClickEvent(QMouseEvent*) override;
    void contextMenuEvent(QContextMenuEvent*) override;
    void leaveEvent(QEvent*) override;
    void resizeEvent(QResizeEvent*) override;

private:
    // ── data ──
    QVector<float> m_data;
    QVector<bool>  m_lo;
    double m_sr = 180.0;

    // Pre-computed lead-off spans {start_sec, end_sec}
    QVector<QPair<double,double>> m_loSpans;

    // ── view ──
    double m_xMin = 0, m_xMax = 10;
    double m_yMin = -2, m_yMax = 2;

    // ── background buffer (grid + lead-off + labels, NO signal) ──
    QPixmap m_buffer;
    bool    m_bufDirty = true;

    // ── signal strip (transparent, pre-rendered for wide time range) ──
    // Rebuilt only when Y range, data, or theme changes — NOT on pan.
    QPixmap m_signalStrip;
    double  m_stripT0    = 0.0;
    double  m_stripT1    = 0.0;
    double  m_stripYMin  = -2.0;
    double  m_stripYMax  =  2.0;
    bool    m_signalDirty = true;

    // ── pan state ──
    bool   m_panning = false;
    QPoint m_panStart;
    double m_panX0, m_panX1, m_panY0, m_panY1;
    QPixmap m_panGridSnap;   // snapshot of m_buffer at pan start (grid only, no signal)
    int     m_panDx = 0, m_panDy = 0;  // pixel offset for grid pixel-shift during pan

    // ── hover ──
    QPoint m_hover;
    bool   m_showHover = false;

    // ── dark mode ──
    bool m_dark = false;

    // ── layout margins ──
    static constexpr int ML = 58, MR = 12, MT = 12, MB = 36;

    // ── helpers ──
    QRect   plotRect() const;
    QPointF dataToPixel(double t, double v_mV) const;
    std::pair<double,double> pixelToData(const QPoint& px) const;

    void drawBackground(QPainter& p);
    void drawGrid(QPainter& p);
    void drawLeadOff(QPainter& p);
    void drawAxisLabels(QPainter& p);
    void drawInfoOverlay(QPainter& p);
    void drawCrosshair(QPainter& p);

    // ── signal strip ──
    void rebuildSignalStrip();
    void drawSignalForRange(QPainter& p, const QRect& targetRect,
                            double t0, double t1, double yMin, double yMax);
    void drawSignalFromStrip(QPainter& p);
    bool needStripRebuild() const;

    void clampView();
    void zoomX(double factor, double centerSec);
    void zoomY(double factor, double centerMV);
    void markDirty();          // marks both buffer and signal dirty
    void markBufferDirty();    // marks only buffer dirty (grid/labels), not signal

    void buildLoSpans();
};
