#include "ecgview.h"
#include <QPainter>
#include <QPen>
#include <QWheelEvent>
#include <QMouseEvent>
#include <QContextMenuEvent>
#include <QMenu>
#include <QFont>
#include <QFontMetrics>
#include <cmath>
#include <algorithm>

// ─── theme colors ─────────────────────────────────────────────────────────────

struct Theme {
    QColor bg;         // plot fill
    QColor gridMin;    // minor grid lines
    QColor gridMaj;    // major grid lines
    QColor zeroline;
    QColor signal;
    QColor loFill;     // lead-off fill (ARGB)
    QColor text;
    QColor border;
    QColor crosshair;
    QColor bubbleBg;
    QColor bubbleBorder;
    QColor outerBg;    // widget area outside plot
};

static Theme lightTheme() {
    // ECG paper mode: cream background, pink/red grid lines, black signal
    return { QColor(255,248,240),          // bg:          #FFF8F0 cream paper
             QColor(240,160,160,120),      // gridMin:     rgba(240,160,160,120) light pink
             QColor(200,60,60,200),        // gridMaj:     rgba(200,60,60,200)   red
             QColor(180,40,40,200),        // zeroline:    rgba(180,40,40,200)   dark red
             QColor(0x1A1A1A),             // signal:      near-black
             QColor(255,80,80,45),         // loFill:      translucent red
             QColor(0x333333),             // text
             QColor(0xC8A090),             // border:      brownish
             QColor(0x0055AA),             // crosshair:   blue
             QColor(255,255,210,220),      // bubbleBg
             QColor(0x0055AA),             // bubbleBorder
             QColor(0xE8E0D8) };           // outerBg:     #E8E0D8 dark cream
}

static Theme darkTheme() {
    // CRT phosphor monitor mode: black background, green signal/grid
    return { QColor(0,0,0),                // bg:          pure black
             QColor(0,90,0,100),           // gridMin:     rgba(0,90,0,100)   dark green
             QColor(0,140,0,180),          // gridMaj:     rgba(0,140,0,180)  mid green
             QColor(0,180,0,200),          // zeroline:    rgba(0,180,0,200)  bright green
             QColor(0,224,64),             // signal:      #00E040 phosphor green
             QColor(200,40,40,55),         // loFill:      translucent red
             QColor(0,192,64),             // text:        dim green
             QColor(0,64,0),               // border:      dark green
             QColor(0,255,128),            // crosshair:   bright green
             QColor(0,20,0,230),           // bubbleBg:    near-black green
             QColor(0,192,64),             // bubbleBorder
             QColor(10,10,10) };           // outerBg:     #0A0A0A near-black
}

// ─── constructor ─────────────────────────────────────────────────────────────

EcgView::EcgView(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setMinimumSize(400, 200);
    setCursor(Qt::CrossCursor);
    setFocusPolicy(Qt::StrongFocus);
}

// ─── data ─────────────────────────────────────────────────────────────────────

void EcgView::setData(const QVector<float>& samples_uv,
                      const QVector<bool>&  leadOff,
                      double sampleRate) {
    m_data = samples_uv;
    m_lo   = leadOff;
    m_sr   = (sampleRate > 0) ? sampleRate : 180.0;

    while (m_lo.size() < m_data.size()) m_lo.append(false);

    buildLoSpans();
    resetView();
}

void EcgView::buildLoSpans() {
    m_loSpans.clear();
    if (m_lo.isEmpty()) return;

    bool inLO = false;
    double loStart = 0;
    int n = m_lo.size();

    for (int i = 0; i < n; i++) {
        double t = (double)i / m_sr;
        if (m_lo[i] && !inLO) {
            inLO = true;
            loStart = t;
        } else if (!m_lo[i] && inLO) {
            inLO = false;
            m_loSpans.append({loStart, t});
        }
    }
    if (inLO) m_loSpans.append({loStart, (double)(n - 1) / m_sr});
}

double EcgView::totalDuration() const {
    return m_data.isEmpty() ? 0.0 : (double)m_data.size() / m_sr;
}

// ─── dark mode ────────────────────────────────────────────────────────────────

void EcgView::setDarkMode(bool dark) {
    m_dark = dark;
    markDirty();   // signal color is theme-dependent → mark both dirty
}

// ─── view helpers ─────────────────────────────────────────────────────────────

QRect EcgView::plotRect() const {
    return QRect(ML, MT, width() - ML - MR, height() - MT - MB);
}

QPointF EcgView::dataToPixel(double t, double v_mV) const {
    QRect pr = plotRect();
    double px = pr.left() + (t - m_xMin) / (m_xMax - m_xMin) * pr.width();
    double py = pr.top()  + (m_yMax - v_mV) / (m_yMax - m_yMin) * pr.height();
    return {px, py};
}

std::pair<double,double> EcgView::pixelToData(const QPoint& p) const {
    QRect pr = plotRect();
    double t = m_xMin + (double)(p.x() - pr.left()) / pr.width()  * (m_xMax - m_xMin);
    double v = m_yMax - (double)(p.y() - pr.top())  / pr.height() * (m_yMax - m_yMin);
    return {t, v};
}

void EcgView::clampView() {
    if (m_xMax - m_xMin < 0.02) { double c = (m_xMax+m_xMin)/2; m_xMin=c-0.01; m_xMax=c+0.01; }
    if (m_yMax - m_yMin < 0.02) { double c = (m_yMax+m_yMin)/2; m_yMin=c-0.01; m_yMax=c+0.01; }
    double dur = totalDuration();
    if (dur > 0) {
        double span = m_xMax - m_xMin;
        double mg = span * 0.5;
        if (m_xMin < -mg)       { m_xMin = -mg;       m_xMax = m_xMin + span; }
        if (m_xMax > dur + mg)  { m_xMax = dur + mg;  m_xMin = m_xMax - span; }
    }
}

// markDirty: both layers need rebuild (data/Y/theme change)
void EcgView::markDirty() {
    m_bufDirty    = true;
    m_signalDirty = true;
    update();
}

// markBufferDirty: only grid/labels need rebuild (X pan/zoom)
void EcgView::markBufferDirty() {
    m_bufDirty = true;
    update();
}

// ─── public view control ──────────────────────────────────────────────────────

void EcgView::resetView() {
    m_xMin = 0;
    m_xMax = qMin(totalDuration(), 10.0);
    if (m_xMax <= 0) m_xMax = 10.0;
    autoScaleY();
    markDirty();
    emit viewChanged(m_xMin, m_xMax);
}

void EcgView::setViewRange(double xMin, double xMax) {
    m_xMin = xMin; m_xMax = xMax;
    clampView();
    autoScaleY();
    markDirty();
    emit viewChanged(m_xMin, m_xMax);
}

void EcgView::autoScaleY() {
    if (m_data.isEmpty()) { m_yMin = -2.0; m_yMax = 2.0; return; }

    int iStart = qMax(0, (int)(m_xMin * m_sr));
    int iEnd   = qMin(m_data.size() - 1, (int)(m_xMax * m_sr + 1));

    QVector<float> valid;
    valid.reserve(iEnd - iStart + 1);
    for (int i = iStart; i <= iEnd; i++)
        if (!m_lo[i]) valid.append(m_data[i] / 1000.0f);

    if (valid.isEmpty()) { m_yMin = -2.0; m_yMax = 2.0; return; }

    int p1i  = qMax(0, (int)(valid.size() * 0.01));
    int p99i = qMin(valid.size()-1, (int)(valid.size() * 0.99));
    std::nth_element(valid.begin(), valid.begin() + p1i,  valid.end());
    float p1  = valid[p1i];
    std::nth_element(valid.begin(), valid.begin() + p99i, valid.end());
    float p99 = valid[p99i];

    float margin = qMax((p99 - p1) * 0.25f, 0.2f);
    m_yMin = (double)(p1  - margin);
    m_yMax = (double)(p99 + margin);
}

// ─── zoom ─────────────────────────────────────────────────────────────────────

void EcgView::zoomX(double factor, double centerSec) {
    double span = m_xMax - m_xMin;
    double ratio = (span > 0) ? (centerSec - m_xMin) / span : 0.5;
    double newSpan = span * factor;
    m_xMin = centerSec - ratio * newSpan;
    m_xMax = m_xMin + newSpan;
    clampView();
    // Grid must update; signal strip reused via scaling until edge check triggers rebuild
    markBufferDirty();
    emit viewChanged(m_xMin, m_xMax);
}

void EcgView::zoomY(double factor, double centerMV) {
    double span = m_yMax - m_yMin;
    double ratio = (span > 0) ? (centerMV - m_yMin) / span : 0.5;
    double newSpan = span * factor;
    m_yMin = centerMV - ratio * newSpan;
    m_yMax = m_yMin + newSpan;
    clampView();
    markDirty();   // Y changed → signal strip must be rebuilt
}

// ─── mouse events ─────────────────────────────────────────────────────────────

void EcgView::wheelEvent(QWheelEvent* e) {
    if (m_data.isEmpty()) return;
    double factor = std::pow(0.80, e->angleDelta().y() / 120.0);
    auto [t, v] = pixelToData(e->pos());
    if (e->modifiers() & Qt::ControlModifier) zoomY(factor, v);
    else                                       zoomX(factor, t);
}

void EcgView::mousePressEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton && plotRect().contains(e->pos())) {
        m_panning = true; m_panStart = e->pos();
        m_panX0=m_xMin; m_panX1=m_xMax; m_panY0=m_yMin; m_panY1=m_yMax;
        m_panDx = 0; m_panDy = 0;
        // Composite full frame (grid + signal) into snapshot for fast pan blit
        m_panGridSnap = QPixmap(size());
        QPainter snap(&m_panGridSnap);
        snap.drawPixmap(0, 0, m_buffer);
        if (!m_data.isEmpty() && !m_signalStrip.isNull())
            drawSignalFromStrip(snap);
        setCursor(Qt::ClosedHandCursor);
    }
}

void EcgView::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        m_panning = false;
        m_panGridSnap = QPixmap();  // release snapshot memory
        setCursor(Qt::CrossCursor);
        // Rebuild grid/labels at final position once; signal strip stays valid
        markBufferDirty();
    }
}

void EcgView::mouseMoveEvent(QMouseEvent* e) {
    if (m_panning) {
        QRect pr = plotRect();
        double dx = -(double)(e->pos().x()-m_panStart.x()) / pr.width()  * (m_panX1-m_panX0);
        double dy =  (double)(e->pos().y()-m_panStart.y()) / pr.height() * (m_panY1-m_panY0);
        m_xMin=m_panX0+dx; m_xMax=m_panX1+dx;
        m_yMin=m_panY0+dy; m_yMax=m_panY1+dy;
        clampView();
        // Store pixel offset for fast pan preview — NO dirty flags, NO buffer rebuild
        m_panDx = e->pos().x() - m_panStart.x();
        m_panDy = e->pos().y() - m_panStart.y();
        update();
        emit viewChanged(m_xMin, m_xMax);
    } else {
        m_hover     = e->pos();
        m_showHover = plotRect().contains(e->pos());
        update();   // crosshair only — no buffer rebuild

        if (m_showHover && !m_data.isEmpty()) {
            auto [t, v] = pixelToData(e->pos());
            int idx = qBound(0, (int)(t * m_sr), m_data.size()-1);
            bool lo = m_lo[idx];
            emit sampleHovered(t, lo ? v*1000.0 : (double)m_data[idx], !lo);
        }
    }
}

void EcgView::mouseDoubleClickEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        m_xMin = 0; m_xMax = totalDuration();
        autoScaleY();
        markDirty();
        emit viewChanged(m_xMin, m_xMax);
    }
}

void EcgView::contextMenuEvent(QContextMenuEvent* e) {
    QMenu menu(this);
    auto addZoom = [&](const QString& s, double sec) {
        menu.addAction(s, [this, sec]{
            double c=(m_xMin+m_xMax)/2;
            setViewRange(c-sec/2, c+sec/2);
        });
    };
    addZoom("縮放 5 秒",  5);
    addZoom("縮放 10 秒", 10);
    addZoom("縮放 30 秒", 30);
    menu.addAction("顯示全部",     [this]{ setViewRange(0, totalDuration()); });
    menu.addSeparator();
    menu.addAction("Y 軸自動縮放", [this]{ autoScaleY(); markDirty(); });
    menu.exec(e->globalPos());
}

void EcgView::leaveEvent(QEvent*) {
    m_showHover = false;
    update();
}

void EcgView::resizeEvent(QResizeEvent*) {
    markDirty();   // both layers: height changed
}

// ─── signal strip ─────────────────────────────────────────────────────────────

bool EcgView::needStripRebuild() const {
    if (m_signalStrip.isNull()) return true;
    if (m_stripYMin != m_yMin || m_stripYMax != m_yMax) return true;

    // Rebuild when zoomed in significantly: strip too coarse for current zoom.
    // (zoomX only calls markBufferDirty, so this is the only zoom trigger.)
    QRect pr = plotRect();
    if (pr.width() > 0 && m_xMax > m_xMin && m_stripT1 > m_stripT0) {
        double stripPxPerSec = (double)m_signalStrip.width() / (m_stripT1 - m_stripT0);
        double viewPxPerSec  = (double)pr.width() / (m_xMax - m_xMin);
        if (viewPxPerSec > stripPxPerSec * 2.0) return true;
    }

    // Rebuild when viewport approaches within 20% of strip edge (prefetch),
    // but NOT when strip already covers the data boundary — can't extend further.
    double dur    = totalDuration();
    double margin = (m_xMax - m_xMin) * 0.20;
    bool nearLeft  = (m_xMin < m_stripT0 + margin) && (m_stripT0 > 0.0);
    bool nearRight = (m_xMax > m_stripT1 - margin) && (m_stripT1 < dur);
    return nearLeft || nearRight;
}

void EcgView::rebuildSignalStrip() {
    if (m_data.isEmpty()) { m_signalStrip = QPixmap(); return; }

    QRect pr = plotRect();
    if (pr.width() <= 0 || pr.height() <= 0) return;

    double viewSpan = m_xMax - m_xMin;
    double dur      = totalDuration();

    // Cover viewport ± 2× view span, clamped to data bounds
    double t0 = qMax(0.0, m_xMin - 2.0 * viewSpan);
    double t1 = qMin(dur,  m_xMax + 2.0 * viewSpan);
    if (t1 <= t0) { t0 = 0; t1 = qMax(0.01, dur); }

    // Width proportional to time span covered, capped at 8192px
    double stripTimeSpan = t1 - t0;
    int stripW = (int)(stripTimeSpan / viewSpan * pr.width());
    stripW = qBound(pr.width(), stripW, 8192);
    int stripH = pr.height();

    m_signalStrip = QPixmap(stripW, stripH);
    m_signalStrip.fill(Qt::transparent);

    QPainter sp(&m_signalStrip);
    sp.setRenderHint(QPainter::Antialiasing, true);
    drawSignalForRange(sp, QRect(0, 0, stripW, stripH), t0, t1, m_yMin, m_yMax);

    m_stripT0   = t0;
    m_stripT1   = t1;
    m_stripYMin = m_yMin;
    m_stripYMax = m_yMax;
}

void EcgView::drawSignalForRange(QPainter& p, const QRect& r,
                                 double t0, double t1,
                                 double yMin, double yMax) {
    if (m_data.isEmpty() || r.width() <= 0 || r.height() <= 0) return;

    Theme th = m_dark ? darkTheme() : lightTheme();
    double xRange = t1 - t0;
    double yRange = yMax - yMin;
    if (xRange <= 0 || yRange <= 0) return;

    int n      = m_data.size();
    int iStart = qMax(0, (int)(t0 * m_sr) - 1);
    int iEnd   = qMin(n-1, (int)(t1 * m_sr) + 1);
    int nVis   = iEnd - iStart + 1;

    p.setPen(QPen(th.signal, m_dark ? 1.2 : 1.0));

    auto toPixY = [&](float uv) {
        return r.top() + (yMax - uv/1000.0) / yRange * r.height();
    };

    if (nVis <= r.width() * 2) {
        // Direct polyline with lead-off breaks
        QPolygonF seg;
        seg.reserve(nVis);
        for (int i = iStart; i <= iEnd; i++) {
            if (m_lo[i]) {
                if (!seg.isEmpty()) { p.drawPolyline(seg); seg.clear(); }
                continue;
            }
            double px = r.left() + ((double)i/m_sr - t0) / xRange * r.width();
            seg << QPointF(px, toPixY(m_data[i]));
        }
        if (!seg.isEmpty()) p.drawPolyline(seg);
    } else {
        // Min-max decimation: one vertical segment per pixel column
        QVector<QLineF> lines;
        lines.reserve(r.width());
        for (int col = 0; col < r.width(); col++) {
            double ct0 = t0 + (double)col       / r.width() * xRange;
            double ct1 = t0 + (double)(col + 1) / r.width() * xRange;
            int i0 = qMax(iStart, (int)(ct0 * m_sr));
            int i1 = qMin(iEnd,   (int)(ct1 * m_sr));
            float vmin = 1e9f, vmax = -1e9f;
            for (int i = i0; i <= i1; i++) {
                if (!m_lo[i]) { vmin=qMin(vmin,m_data[i]); vmax=qMax(vmax,m_data[i]); }
            }
            if (vmin <= vmax) {
                double px = r.left() + col;
                lines << QLineF(px, toPixY(vmax), px, toPixY(vmin));
            }
        }
        p.drawLines(lines);
    }
}

void EcgView::drawSignalFromStrip(QPainter& p) {
    if (m_signalStrip.isNull()) return;

    QRect pr = plotRect();
    double xRange    = m_xMax - m_xMin;
    double stripSpan = m_stripT1 - m_stripT0;
    if (xRange <= 0 || stripSpan <= 0) return;

    // Clip visible time range to strip coverage — anything outside is blank
    double visT0 = qMax(m_xMin, m_stripT0);
    double visT1 = qMin(m_xMax, m_stripT1);
    if (visT0 >= visT1) return;

    // Dst sub-rect within plotRect corresponding to [visT0, visT1]
    int dstX = pr.left() + (int)((visT0 - m_xMin) / xRange * pr.width());
    int dstW = (int)((visT1 - visT0) / xRange * pr.width());
    if (dstW < 1) return;

    // Src sub-rect within strip corresponding to [visT0, visT1]
    double scaleX = m_signalStrip.width() / stripSpan;
    int srcX = (int)((visT0 - m_stripT0) * scaleX);
    int srcW = (int)((visT1 - visT0)     * scaleX);
    srcX = qBound(0, srcX, m_signalStrip.width() - 1);
    srcW = qBound(1, srcW, m_signalStrip.width() - srcX);

    QRect dstRect(dstX, pr.top(), dstW, pr.height());
    QRect srcRect(srcX, 0, srcW, m_signalStrip.height());

    p.setRenderHint(QPainter::SmoothPixmapTransform, false);
    p.drawPixmap(dstRect, m_signalStrip, srcRect);
}

// ─── paint ────────────────────────────────────────────────────────────────────

void EcgView::paintEvent(QPaintEvent*) {
    // ── Fast pan path ───────────────────────────────────────────────────────
    // Grid snapshot pixel-shift + signal strip blit — zero QPixmap allocation,
    // zero grid recalculation.  O(pixels) GPU blit only.
    if (m_panning && !m_panGridSnap.isNull()) {
        // Fast pan: blit full-frame snapshot shifted — O(pixels), zero recalculation
        Theme th = m_dark ? darkTheme() : lightTheme();
        QPainter p(this);
        p.fillRect(rect(), th.outerBg);
        p.drawPixmap(m_panDx, m_panDy, m_panGridSnap);
        // Erase margin overhang exposed by shift
        p.fillRect(0,           0,            ML,      height(), th.outerBg);
        p.fillRect(width()-MR,  0,            MR,      height(), th.outerBg);
        p.fillRect(0,           0,            width(), MT,       th.outerBg);
        p.fillRect(0,           height()-MB,  width(), MB,       th.outerBg);
        if (m_showHover) drawCrosshair(p);
        return;
    }

    // ── Normal path ─────────────────────────────────────────────────────────
    // Layer 1: rebuild background buffer (grid + lead-off + labels) if dirty.
    if (m_bufDirty || m_buffer.size() != size()) {
        m_buffer = QPixmap(size());
        QPainter bp(&m_buffer);
        bp.setRenderHint(QPainter::Antialiasing, false);
        drawBackground(bp);
        if (!m_data.isEmpty()) {
            drawGrid(bp);
            drawLeadOff(bp);
        }
        drawAxisLabels(bp);
        drawInfoOverlay(bp);
        m_bufDirty = false;
    }

    // Layer 2: rebuild signal strip if dirty (Y/data/theme change).
    // NOT triggered by pan. On pan, the existing strip is blitted at a
    // different sub-rect offset — zero signal recalculation.
    if (!m_data.isEmpty()) {
        if (m_signalDirty || m_signalStrip.isNull()) {
            rebuildSignalStrip();
            m_signalDirty = false;
        } else if (needStripRebuild()) {
            // Viewport approaching strip edge — lazy rebuild
            rebuildSignalStrip();
        }
    }

    // Blit background layer (grid, lead-off, labels)
    QPainter p(this);
    p.drawPixmap(0, 0, m_buffer);

    // Blit correct sub-rect of signal strip onto plotRect
    if (!m_data.isEmpty() && !m_signalStrip.isNull()) {
        drawSignalFromStrip(p);
    }

    // Crosshair on top — never cached
    if (m_showHover) drawCrosshair(p);
}

// ─── buffer drawing routines ──────────────────────────────────────────────────

void EcgView::drawBackground(QPainter& p) {
    Theme t = m_dark ? darkTheme() : lightTheme();
    p.fillRect(rect(), t.outerBg);
    p.fillRect(plotRect(), t.bg);
    p.setPen(QPen(t.border, 1));
    p.drawRect(plotRect().adjusted(0,0,-1,-1));
}

void EcgView::drawGrid(QPainter& p) {
    Theme t = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();
    if (pr.width() <= 0 || pr.height() <= 0) return;

    double xRange = m_xMax - m_xMin;
    double yRange = m_yMax - m_yMin;

    // Fixed medical-standard ECG grid — 25 mm/s, 10 mm/mV
    static constexpr double X_MINOR = 0.04, X_MAJOR = 0.2;
    static constexpr double Y_MINOR = 0.1,  Y_MAJOR = 0.5;

    // Performance guard: skip grid tiers whose pixel spacing would be < threshold
    double pxPerXMinor = X_MINOR / xRange * pr.width();
    double pxPerYMinor = Y_MINOR / yRange * pr.height();
    double pxPerXMajor = X_MAJOR / xRange * pr.width();
    double pxPerYMajor = Y_MAJOR / yRange * pr.height();
    bool drawXMinor = (pxPerXMinor >= 0.5);
    bool drawYMinor = (pxPerYMinor >= 0.5);
    bool drawXMajor = (pxPerXMajor >= 1.0);
    bool drawYMajor = (pxPerYMajor >= 1.0);

    QVector<QLineF> minorH, minorV, majorH, majorV;

    if (drawXMinor) {
        for (double x = std::ceil(m_xMin/X_MINOR)*X_MINOR; x <= m_xMax; x += X_MINOR) {
            double px = pr.left() + (x-m_xMin)/xRange*pr.width();
            minorV << QLineF(px, pr.top(), px, pr.bottom());
        }
    }
    if (drawYMinor) {
        for (double y = std::ceil(m_yMin/Y_MINOR)*Y_MINOR; y <= m_yMax; y += Y_MINOR) {
            double py = pr.top() + (m_yMax-y)/yRange*pr.height();
            minorH << QLineF(pr.left(), py, pr.right(), py);
        }
    }
    if (drawXMajor) {
        for (double x = std::ceil(m_xMin/X_MAJOR)*X_MAJOR; x <= m_xMax; x += X_MAJOR) {
            double px = pr.left() + (x-m_xMin)/xRange*pr.width();
            majorV << QLineF(px, pr.top(), px, pr.bottom());
        }
    }
    if (drawYMajor) {
        for (double y = std::ceil(m_yMin/Y_MAJOR)*Y_MAJOR; y <= m_yMax; y += Y_MAJOR) {
            double py = pr.top() + (m_yMax-y)/yRange*pr.height();
            majorH << QLineF(pr.left(), py, pr.right(), py);
        }
    }

    p.setPen(QPen(t.gridMin, 0.5)); p.drawLines(minorV); p.drawLines(minorH);
    p.setPen(QPen(t.gridMaj, 1.0)); p.drawLines(majorV); p.drawLines(majorH);

    // Zero line: solid 1.5px (isoelectric baseline)
    if (m_yMin < 0 && m_yMax > 0) {
        double py = pr.top() + m_yMax/yRange*pr.height();
        p.setPen(QPen(t.zeroline, 1.5, Qt::SolidLine));
        p.drawLine(QLineF(pr.left(), py, pr.right(), py));
    }
}

void EcgView::drawLeadOff(QPainter& p) {
    Theme t = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();
    double xRange = m_xMax - m_xMin;

    p.setBrush(t.loFill);
    p.setPen(Qt::NoPen);

    for (auto& [s0, s1] : m_loSpans) {
        if (s1 < m_xMin || s0 > m_xMax) continue;
        double x0 = pr.left() + qMax(0.0, (s0-m_xMin)/xRange) * pr.width();
        double x1 = pr.left() + qMin(1.0, (s1-m_xMin)/xRange) * pr.width();
        p.fillRect(QRectF(x0, pr.top(), x1-x0, pr.height()), t.loFill);
    }
}

void EcgView::drawAxisLabels(QPainter& p) {
    Theme t = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();
    p.setPen(t.text);
    QFont f = p.font(); f.setPointSize(8); p.setFont(f);

    double xRange = m_xMax - m_xMin;
    double yRange = m_yMax - m_yMin;

    // X step aligned to 0.2s major grid multiples, chosen by pixel density
    double pxPerXMajor = 0.2 / xRange * pr.width();
    double xStep = (pxPerXMajor >= 60) ? 0.2
                 : (pxPerXMajor >= 12) ? 1.0
                 : (pxPerXMajor >= 6)  ? 5.0
                 :                       10.0;

    for (double x = std::ceil(m_xMin/xStep)*xStep; x <= m_xMax+0.001; x += xStep) {
        double px = pr.left() + (x-m_xMin)/xRange*pr.width();
        if (px < pr.left()-5 || px > pr.right()+5) continue;
        QString lbl = (xStep < 1.0) ? QString::number(x,'f',1)+"s"
                                    : QString::number((int)std::round(x))+"s";
        p.drawText(QRectF(px-25, pr.bottom()+4, 50, 14), Qt::AlignHCenter, lbl);
        p.setPen(QPen(t.zeroline, 0.5));
        p.drawLine(QPointF(px, pr.bottom()), QPointF(px, pr.bottom()+3));
        p.setPen(t.text);
    }

    // Y step aligned to 0.5mV major grid multiples, chosen by pixel density
    double pxPerYMajor = 0.5 / yRange * pr.height();
    double yStep = (pxPerYMajor >= 30) ? 0.5
                 : (pxPerYMajor >= 10) ? 1.0
                 :                       2.0;

    for (double y = std::ceil(m_yMin/yStep)*yStep; y <= m_yMax+0.001; y += yStep) {
        double py = pr.top() + (m_yMax-y)/yRange*pr.height();
        if (py < pr.top()-5 || py > pr.bottom()+5) continue;
        p.drawText(QRectF(0, py-8, ML-4, 16), Qt::AlignRight|Qt::AlignVCenter,
                   QString::number(y,'f',yStep<1?1:0)+"mV");
    }
}

void EcgView::drawInfoOverlay(QPainter& p) {
    Theme t = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();
    if (m_data.isEmpty()) {
        p.setPen(QColor(0xAAAAAA));
        QFont f = p.font(); f.setPointSize(12); p.setFont(f);
        p.drawText(pr, Qt::AlignCenter,
                   "\u8acb\u900f\u904e\u300c\u6a94\u6848 \u2192 \u958b\u555f\u300d\u8f09\u5165 .dat \u6a94\u6848\n\n"
                   "\u6eda\u8f2a\uff1a\u7e2e\u653e X \u8ef8\nCtrl + \u6eda\u8f2a\uff1a\u7e2e\u653e Y \u8ef8\n"
                   "\u5de6\u9375\u62d6\u66f3\uff1a\u5e73\u79fb\n\u96d9\u64ca\uff1a\u91cd\u8a2d\u8996\u5716\n\u53f3\u9375\uff1a\u5feb\u901f\u7e2e\u653e\u9078\u55ae");
        return;
    }
    QFont f = p.font(); f.setPointSize(8); p.setFont(f);

    // Top-left: scale annotation
    double xRange = m_xMax - m_xMin;
    QString scaleStr;
    if (xRange <= 60.0) {
        scaleStr = "25 mm/s | 10 mm/mV";
    } else {
        double pxPerMajor = 0.2 / xRange * pr.width();
        double xStep = (pxPerMajor >= 60) ? 0.2
                     : (pxPerMajor >= 12) ? 1.0
                     : (pxPerMajor >= 6)  ? 5.0
                     :                      10.0;
        if (xStep < 1.0)
            scaleStr = QString::number(xStep,'f',1) + " s/div";
        else
            scaleStr = QString::number((int)xStep) + " s/div";
    }
    p.setPen(t.text);
    p.drawText(QRect(pr.left()+4, pr.top()+2, 160, 14), Qt::AlignLeft, scaleStr);

    // Top-right: view range info
    p.setPen(QColor(m_dark ? 0x407050 : 0x888888));
    QString info = QString("%1 - %2 s  (%3 s)")
                       .arg(m_xMin, 0, 'f', 2).arg(m_xMax, 0, 'f', 2).arg(xRange, 0, 'f', 2);
    p.drawText(QRect(pr.right()-220, pr.top()+2, 218, 14), Qt::AlignRight, info);
}

void EcgView::drawCrosshair(QPainter& p) {
    Theme t = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();
    if (!pr.contains(m_hover)) return;

    auto [ts, v] = pixelToData(m_hover);

    p.setPen(QPen(t.crosshair, 1, Qt::DashLine));
    p.drawLine(QPointF(m_hover.x(), pr.top()), QPointF(m_hover.x(), pr.bottom()));
    p.drawLine(QPointF(pr.left(), m_hover.y()), QPointF(pr.right(), m_hover.y()));

    if (!m_data.isEmpty()) {
        int idx = qBound(0, (int)(ts * m_sr), m_data.size()-1);
        bool lo = m_lo[idx];
        double uv = lo ? v*1000.0 : (double)m_data[idx];
        QString txt = lo
            ? QString("\u6642\u9593 = %1 \u79d2\n\u3010\u96fb\u6975\u812b\u843d\u3011").arg(ts, 0, 'f', 3)
            : QString("\u6642\u9593 = %1 \u79d2\n%2 \u5fae\u4f0f\n%3 \u6beb\u4f0f")
                  .arg(ts, 0, 'f', 3).arg(uv, 0, 'f', 1).arg(uv/1000.0, 0, 'f', 3);

        QFont f = p.font(); f.setPointSize(8); p.setFont(f);
        QFontMetrics fm(f);
        QRect br = fm.boundingRect(QRect(0,0,200,100), Qt::AlignLeft, txt);
        br.setWidth(br.width()+10); br.setHeight(br.height()+8);

        int bx = m_hover.x()+10, by = m_hover.y()-br.height()-4;
        if (bx+br.width() > pr.right())  bx = m_hover.x()-br.width()-10;
        if (by < pr.top())               by = m_hover.y()+10;
        br.moveTo(bx, by);

        p.fillRect(br, t.bubbleBg);
        p.setPen(QPen(t.bubbleBorder, 1));
        p.drawRect(br);
        p.setPen(lo ? Qt::red : (m_dark ? QColor(0x90CAF9) : Qt::black));
        p.drawText(br.adjusted(5,4,-5,-4), Qt::AlignLeft, txt);
    }
}
