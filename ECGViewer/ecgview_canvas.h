#pragma once
#include <QWidget>
#include <QPixmap>
#include <QVector>
#include <QPair>

// EcgViewCanvas — simplified single-buffer ECG renderer.
//
// Architecture:
//   m_buffer = bg + grid + lead-off + signal + labels  (one unified canvas)
//   paintEvent: dirty → rebuild m_buffer → blit → crosshair
//   Pan: take full-frame snapshot at press, blit shifted during drag,
//        markDirty on release.  Zero strip management complexity.
class EcgViewCanvas : public QWidget {
    Q_OBJECT
public:
    explicit EcgViewCanvas(QWidget* parent = nullptr);

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
    void paintEvent(QPaintEvent*)        override;
    void wheelEvent(QWheelEvent*)        override;
    void mousePressEvent(QMouseEvent*)   override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void mouseMoveEvent(QMouseEvent*)    override;
    void mouseDoubleClickEvent(QMouseEvent*) override;
    void contextMenuEvent(QContextMenuEvent*) override;
    void leaveEvent(QEvent*)             override;
    void resizeEvent(QResizeEvent*)      override;

private:
    // ── data ──
    QVector<float> m_data;
    QVector<bool>  m_lo;
    double m_sr = 180.0;
    QVector<QPair<double,double>> m_loSpans;

    // ── view ──
    double m_xMin = 0, m_xMax = 10;
    double m_yMin = -2, m_yMax = 2;

    // ── canvas buffer (full render, no signal strip) ──
    QPixmap m_buffer;
    bool    m_bufDirty = true;

    // ── pan state ──
    bool    m_panning = false;
    QPoint  m_panStart;
    double  m_panX0, m_panX1, m_panY0, m_panY1;
    QPixmap m_panSnap;
    int     m_panDx = 0, m_panDy = 0;

    // ── hover ──
    QPoint m_hover;
    bool   m_showHover = false;

    // ── theme ──
    bool m_dark = false;

    // ── margins ──
    static constexpr int ML = 58, MR = 12, MT = 12, MB = 36;

    // ── drawing ──
    QRect   plotRect() const;
    QPointF dataToPixel(double t, double v_mV) const;
    std::pair<double,double> pixelToData(const QPoint& px) const;

    void renderBuffer();          // rebuild m_buffer (all layers)
    void drawCrosshair(QPainter&);

    // ── helpers ──
    void clampView();
    void zoomX(double factor, double centerSec);
    void zoomY(double factor, double centerMV);
    void markDirty();
    void buildLoSpans();
};
