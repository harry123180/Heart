#include "ecgview_canvas.h"
#include <QPainter>
#include <QWheelEvent>
#include <QMouseEvent>
#include <QContextMenuEvent>
#include <QMenu>
#include <cmath>
#include <algorithm>

// ─── theme ────────────────────────────────────────────────────────────────────

struct Theme {
    QColor bg, outerBg, border;
    QColor gridMin, gridMaj, zeroline;
    QColor signal;
    QColor loFill;
    QColor text, crosshair;
};

static Theme darkTheme() {
    Theme t;
    t.bg       = QColor("#000000");
    t.outerBg  = QColor("#0A0A0A");
    t.border   = QColor("#1A4A1A");
    t.gridMin  = QColor(0, 90, 0, 100);
    t.gridMaj  = QColor(0, 140, 0, 180);
    t.zeroline = QColor(0, 180, 0, 200);
    t.signal   = QColor("#00E040");
    t.loFill   = QColor(180, 40, 40, 40);
    t.text     = QColor("#44BB44");
    t.crosshair= QColor(0, 200, 0, 160);
    return t;
}

static Theme lightTheme() {
    Theme t;
    t.bg       = QColor("#FFF8F0");
    t.outerBg  = QColor("#E8E0D8");
    t.border   = QColor("#C08080");
    t.gridMin  = QColor(240, 160, 160, 120);
    t.gridMaj  = QColor(200, 60,  60,  200);
    t.zeroline = QColor(180, 40,  40,  200);
    t.signal   = QColor("#1A1A1A");
    t.loFill   = QColor(200, 60, 60, 30);
    t.text     = QColor("#333333");
    t.crosshair= QColor(60, 60, 180, 160);
    return t;
}

// ─── construction ─────────────────────────────────────────────────────────────

EcgViewCanvas::EcgViewCanvas(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setMinimumSize(400, 200);
    setCursor(Qt::CrossCursor);
    setFocusPolicy(Qt::StrongFocus);
}

// ─── data ─────────────────────────────────────────────────────────────────────

double EcgViewCanvas::totalDuration() const {
    return m_sr > 0 ? m_data.size() / m_sr : 0.0;
}

void EcgViewCanvas::setData(const QVector<float>& samples_uv,
                             const QVector<bool>&  leadOff,
                             double sampleRate) {
    m_data = samples_uv;
    m_lo   = leadOff;
    m_sr   = (sampleRate > 0) ? sampleRate : 180.0;
    while (m_lo.size() < m_data.size()) m_lo.append(false);
    buildLoSpans();
    resetView();
}

void EcgViewCanvas::buildLoSpans() {
    m_loSpans.clear();
    if (m_lo.isEmpty()) return;
    bool inLO = false;
    double loStart = 0;
    for (int i = 0; i < m_lo.size(); i++) {
        double t = (double)i / m_sr;
        if (m_lo[i] && !inLO) { inLO = true; loStart = t; }
        else if (!m_lo[i] && inLO) { inLO = false; m_loSpans.append({loStart, t}); }
    }
    if (inLO) m_loSpans.append({loStart, totalDuration()});
}

// ─── view control ─────────────────────────────────────────────────────────────

void EcgViewCanvas::resetView() {
    m_xMin = 0;
    m_xMax = qMin(totalDuration(), 10.0);
    if (m_xMax <= 0) m_xMax = 10.0;
    autoScaleY();
    markDirty();
    emit viewChanged(m_xMin, m_xMax);
}

void EcgViewCanvas::autoScaleY() {
    if (m_data.isEmpty()) { m_yMin = -2; m_yMax = 2; return; }
    int iStart = qMax(0, (int)(m_xMin * m_sr));
    int iEnd   = qMin(m_data.size()-1, (int)(m_xMax * m_sr));
    float vmin = 1e9f, vmax = -1e9f;
    for (int i = iStart; i <= iEnd; i++) {
        if (!m_lo[i]) { vmin = qMin(vmin, m_data[i]); vmax = qMax(vmax, m_data[i]); }
    }
    if (vmin > vmax) { m_yMin = -2; m_yMax = 2; return; }
    double pad = qMax(0.1, (vmax - vmin) / 1000.0 * 0.15);
    m_yMin = vmin / 1000.0 - pad;
    m_yMax = vmax / 1000.0 + pad;
    clampView();
}

void EcgViewCanvas::setViewRange(double xMin, double xMax) {
    m_xMin = xMin; m_xMax = xMax;
    clampView();
    autoScaleY();
    markDirty();
    emit viewChanged(m_xMin, m_xMax);
}

void EcgViewCanvas::setDarkMode(bool dark) {
    m_dark = dark;
    markDirty();
}

void EcgViewCanvas::clampView() {
    if (m_xMax - m_xMin < 0.02) { double c=(m_xMax+m_xMin)/2; m_xMin=c-0.01; m_xMax=c+0.01; }
    if (m_yMax - m_yMin < 0.02) { double c=(m_yMax+m_yMin)/2; m_yMin=c-0.01; m_yMax=c+0.01; }
    double dur = totalDuration();
    if (dur > 0) {
        double span = m_xMax - m_xMin;
        double mg   = span * 0.5;
        if (m_xMin < -mg)       { m_xMin = -mg;      m_xMax = m_xMin + span; }
        if (m_xMax > dur + mg)  { m_xMax = dur + mg; m_xMin = m_xMax - span; }
    }
}

void EcgViewCanvas::markDirty() {
    m_bufDirty = true;
    update();
}

// ─── layout ───────────────────────────────────────────────────────────────────

QRect EcgViewCanvas::plotRect() const {
    return QRect(ML, MT, width()-ML-MR, height()-MT-MB);
}

QPointF EcgViewCanvas::dataToPixel(double t, double v_mV) const {
    QRect pr = plotRect();
    double px = pr.left() + (t - m_xMin) / (m_xMax - m_xMin) * pr.width();
    double py = pr.top()  + (m_yMax - v_mV) / (m_yMax - m_yMin) * pr.height();
    return {px, py};
}

std::pair<double,double> EcgViewCanvas::pixelToData(const QPoint& p) const {
    QRect pr = plotRect();
    double t = m_xMin + (double)(p.x() - pr.left()) / pr.width()  * (m_xMax - m_xMin);
    double v = m_yMax - (double)(p.y() - pr.top())  / pr.height() * (m_yMax - m_yMin);
    return {t, v};
}

// ─── rendering ────────────────────────────────────────────────────────────────

void EcgViewCanvas::renderBuffer() {
    m_buffer = QPixmap(size());
    QPainter p(&m_buffer);
    p.setRenderHint(QPainter::Antialiasing, false);

    Theme th = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();

    // ── background ──
    p.fillRect(rect(), th.outerBg);
    p.fillRect(pr, th.bg);
    p.setPen(QPen(th.border, 1));
    p.drawRect(pr.adjusted(0, 0, -1, -1));

    if (pr.width() <= 0 || pr.height() <= 0) { m_bufDirty = false; return; }

    double xRange = m_xMax - m_xMin;
    double yRange = m_yMax - m_yMin;
    if (xRange <= 0 || yRange <= 0) { m_bufDirty = false; return; }

    // ── ECG grid (fixed 25mm/s, 10mm/mV) ──
    static constexpr double X_MINOR = 0.04, X_MAJOR = 0.2;
    static constexpr double Y_MINOR = 0.1,  Y_MAJOR = 0.5;

    double pxPerXMinor = X_MINOR / xRange * pr.width();
    double pxPerYMinor = Y_MINOR / yRange * pr.height();
    double pxPerXMajor = X_MAJOR / xRange * pr.width();
    double pxPerYMajor = Y_MAJOR / yRange * pr.height();

    QVector<QLineF> minV, minH, majV, majH;

    if (pxPerXMinor >= 0.5)
        for (double x = std::ceil(m_xMin/X_MINOR)*X_MINOR; x <= m_xMax; x += X_MINOR)
            minV << QLineF(pr.left()+(x-m_xMin)/xRange*pr.width(), pr.top(),
                           pr.left()+(x-m_xMin)/xRange*pr.width(), pr.bottom());

    if (pxPerYMinor >= 0.5)
        for (double y = std::ceil(m_yMin/Y_MINOR)*Y_MINOR; y <= m_yMax; y += Y_MINOR)
            minH << QLineF(pr.left(), pr.top()+(m_yMax-y)/yRange*pr.height(),
                           pr.right(), pr.top()+(m_yMax-y)/yRange*pr.height());

    if (pxPerXMajor >= 1.0)
        for (double x = std::ceil(m_xMin/X_MAJOR)*X_MAJOR; x <= m_xMax; x += X_MAJOR)
            majV << QLineF(pr.left()+(x-m_xMin)/xRange*pr.width(), pr.top(),
                           pr.left()+(x-m_xMin)/xRange*pr.width(), pr.bottom());

    if (pxPerYMajor >= 1.0)
        for (double y = std::ceil(m_yMin/Y_MAJOR)*Y_MAJOR; y <= m_yMax; y += Y_MAJOR)
            majH << QLineF(pr.left(), pr.top()+(m_yMax-y)/yRange*pr.height(),
                           pr.right(), pr.top()+(m_yMax-y)/yRange*pr.height());

    p.setPen(QPen(th.gridMin, 0.5)); p.drawLines(minV); p.drawLines(minH);
    p.setPen(QPen(th.gridMaj, 1.0)); p.drawLines(majV); p.drawLines(majH);

    if (m_yMin < 0 && m_yMax > 0) {
        double py = pr.top() + m_yMax / yRange * pr.height();
        p.setPen(QPen(th.zeroline, 1.5, Qt::SolidLine));
        p.drawLine(QLineF(pr.left(), py, pr.right(), py));
    }

    // ── lead-off shading ──
    p.setPen(Qt::NoPen);
    for (auto& [s0, s1] : m_loSpans) {
        if (s1 < m_xMin || s0 > m_xMax) continue;
        double x0 = pr.left() + qMax(0.0,(s0-m_xMin)/xRange) * pr.width();
        double x1 = pr.left() + qMin(1.0,(s1-m_xMin)/xRange) * pr.width();
        p.fillRect(QRectF(x0, pr.top(), x1-x0, pr.height()), th.loFill);
    }

    // ── signal ──
    if (!m_data.isEmpty()) {
        p.setRenderHint(QPainter::Antialiasing, true);
        p.setClipRect(pr);
        p.setPen(QPen(th.signal, m_dark ? 1.2 : 1.0));

        int n      = m_data.size();
        int iStart = qMax(0,   (int)(m_xMin * m_sr) - 1);
        int iEnd   = qMin(n-1, (int)(m_xMax * m_sr) + 1);
        int nVis   = iEnd - iStart + 1;

        auto toPixX = [&](int i) {
            return pr.left() + ((double)i/m_sr - m_xMin) / xRange * pr.width();
        };
        auto toPixY = [&](float uv) {
            return pr.top() + (m_yMax - uv/1000.0) / yRange * pr.height();
        };

        if (nVis <= pr.width() * 2) {
            // Polyline — smooth for zoomed-in views
            QPolygonF seg;
            seg.reserve(nVis);
            for (int i = iStart; i <= iEnd; i++) {
                if (m_lo[i]) {
                    if (!seg.isEmpty()) { p.drawPolyline(seg); seg.clear(); }
                    continue;
                }
                seg << QPointF(toPixX(i), toPixY(m_data[i]));
            }
            if (!seg.isEmpty()) p.drawPolyline(seg);
        } else {
            // Min-max decimation — one vertical segment per screen pixel column
            QVector<QLineF> lines;
            lines.reserve(pr.width());
            for (int col = 0; col < pr.width(); col++) {
                double ct0 = m_xMin + (double)col       / pr.width() * xRange;
                double ct1 = m_xMin + (double)(col + 1) / pr.width() * xRange;
                int i0 = qMax(iStart, (int)(ct0 * m_sr));
                int i1 = qMin(iEnd,   (int)(ct1 * m_sr));
                float vmin = 1e9f, vmax = -1e9f;
                for (int i = i0; i <= i1; i++)
                    if (!m_lo[i]) { vmin=qMin(vmin,m_data[i]); vmax=qMax(vmax,m_data[i]); }
                if (vmin <= vmax)
                    lines << QLineF(pr.left()+col, toPixY(vmax),
                                    pr.left()+col, toPixY(vmin));
            }
            p.drawLines(lines);
        }

        p.setClipping(false);
    }

    // ── axis labels ──
    p.setRenderHint(QPainter::Antialiasing, false);
    p.setPen(th.text);
    QFont f = p.font(); f.setPointSize(8); p.setFont(f);

    double pxPerXMaj = X_MAJOR / xRange * pr.width();
    double xStep = (pxPerXMaj >= 60) ? 0.2
                 : (pxPerXMaj >= 12) ? 1.0
                 : (pxPerXMaj >= 6)  ? 5.0 : 10.0;
    for (double x = std::ceil(m_xMin/xStep)*xStep; x <= m_xMax; x += xStep) {
        int px = (int)(pr.left() + (x-m_xMin)/xRange*pr.width());
        if (px < pr.left() || px > pr.right()) continue;
        QString lbl = (xStep < 1.0) ? QString::number(x,'f',2)+"s"
                                     : QString::number((int)qRound(x))+"s";
        p.drawText(px-24, pr.bottom()+3, 48, MB-3, Qt::AlignHCenter|Qt::AlignTop, lbl);
    }

    double pxPerYMaj = Y_MAJOR / yRange * pr.height();
    double yStep = (pxPerYMaj >= 30) ? 0.5 : (pxPerYMaj >= 10) ? 1.0 : 2.0;
    for (double y = std::ceil(m_yMin/yStep)*yStep; y <= m_yMax; y += yStep) {
        int py = (int)(pr.top() + (m_yMax-y)/yRange*pr.height());
        if (py < pr.top() || py > pr.bottom()) continue;
        p.drawText(0, py-9, ML-4, 18, Qt::AlignRight|Qt::AlignVCenter,
                   QString::number(y,'f',1)+"mV");
    }

    // ── scale info overlay ──
    p.setFont(QFont(f.family(), 7));
    QString scaleStr = (xRange > 60)
        ? QString("%1s/div").arg(xStep,0,'f',0)
        : "25mm/s | 10mm/mV";
    p.drawText(pr.left()+4, pr.top()+2, 200, 16, Qt::AlignLeft|Qt::AlignTop, scaleStr);

    m_bufDirty = false;
}

// ─── paintEvent ───────────────────────────────────────────────────────────────

void EcgViewCanvas::paintEvent(QPaintEvent*) {
    // Fast pan: blit full-frame snapshot shifted
    if (m_panning && !m_panSnap.isNull()) {
        Theme th = m_dark ? darkTheme() : lightTheme();
        QPainter p(this);
        p.fillRect(rect(), th.outerBg);
        p.drawPixmap(m_panDx, m_panDy, m_panSnap);
        p.fillRect(0,          0,           ML,      height(), th.outerBg);
        p.fillRect(width()-MR, 0,           MR,      height(), th.outerBg);
        p.fillRect(0,          0,           width(), MT,       th.outerBg);
        p.fillRect(0,          height()-MB, width(), MB,       th.outerBg);
        if (m_showHover) drawCrosshair(p);
        return;
    }

    // Normal: rebuild if dirty, then blit
    if (m_bufDirty || m_buffer.size() != size())
        renderBuffer();

    QPainter p(this);
    p.drawPixmap(0, 0, m_buffer);
    if (m_showHover) drawCrosshair(p);
}

// ─── crosshair ────────────────────────────────────────────────────────────────

void EcgViewCanvas::drawCrosshair(QPainter& p) {
    Theme th = m_dark ? darkTheme() : lightTheme();
    QRect pr = plotRect();
    if (!pr.contains(m_hover)) return;

    auto [ts, v] = pixelToData(m_hover);
    p.setPen(QPen(th.crosshair, 1, Qt::DashLine));
    p.drawLine(QPointF(m_hover.x(), pr.top()),  QPointF(m_hover.x(), pr.bottom()));
    p.drawLine(QPointF(pr.left(),   m_hover.y()), QPointF(pr.right(), m_hover.y()));

    if (!m_data.isEmpty()) {
        int idx = qBound(0, (int)(ts * m_sr), m_data.size()-1);
        bool lo = m_lo[idx];
        double uv = lo ? v*1000.0 : (double)m_data[idx];
        QString txt = lo
            ? QString("t=%1s\n[lead-off]").arg(ts,0,'f',3)
            : QString("t=%1s\n%2uV\n%3mV").arg(ts,0,'f',3).arg(uv,0,'f',1).arg(uv/1000,0,'f',3);
        QRect tr(m_hover.x()+6, m_hover.y()-40, 120, 56);
        if (tr.right() > pr.right()) tr.moveLeft(m_hover.x()-126);
        p.setPen(QColor(0,0,0,140));
        p.drawText(tr.adjusted(1,1,1,1), Qt::AlignLeft, txt);
        p.setPen(th.crosshair);
        p.drawText(tr, Qt::AlignLeft, txt);
    }
}

// ─── mouse ────────────────────────────────────────────────────────────────────

void EcgViewCanvas::mousePressEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton && plotRect().contains(e->pos())) {
        m_panning = true; m_panStart = e->pos();
        m_panX0=m_xMin; m_panX1=m_xMax; m_panY0=m_yMin; m_panY1=m_yMax;
        m_panDx = 0; m_panDy = 0;
        // Ensure buffer is current before snapping
        if (m_bufDirty || m_buffer.size() != size()) renderBuffer();
        m_panSnap = m_buffer;
        setCursor(Qt::ClosedHandCursor);
    }
}

void EcgViewCanvas::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        // Compute final view position once on release — not per mouse-move event
        QRect pr = plotRect();
        double dx = -(double)m_panDx / pr.width()  * (m_panX1 - m_panX0);
        double dy =  (double)m_panDy / pr.height() * (m_panY1 - m_panY0);
        m_xMin = m_panX0 + dx; m_xMax = m_panX1 + dx;
        m_yMin = m_panY0 + dy; m_yMax = m_panY1 + dy;
        clampView();
        m_panning = false;
        m_panSnap = QPixmap();
        setCursor(Qt::CrossCursor);
        markDirty();
        emit viewChanged(m_xMin, m_xMax);
    }
}

void EcgViewCanvas::mouseMoveEvent(QMouseEvent* e) {
    if (m_panning) {
        // Pan: only track pixel offset — zero computation, zero emit
        m_panDx = e->pos().x() - m_panStart.x();
        m_panDy = e->pos().y() - m_panStart.y();
        update();
    } else {
        m_hover     = e->pos();
        m_showHover = plotRect().contains(e->pos());
        update();
        if (m_showHover && !m_data.isEmpty()) {
            auto [t, v] = pixelToData(e->pos());
            int idx = qBound(0, (int)(t * m_sr), m_data.size()-1);
            bool lo = m_lo[idx];
            emit sampleHovered(t, lo ? v*1000.0 : (double)m_data[idx], !lo);
        }
    }
}

void EcgViewCanvas::mouseDoubleClickEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        m_xMin = 0; m_xMax = totalDuration();
        autoScaleY();
        markDirty();
        emit viewChanged(m_xMin, m_xMax);
    }
}

void EcgViewCanvas::leaveEvent(QEvent*) {
    m_showHover = false;
    update();
}

void EcgViewCanvas::resizeEvent(QResizeEvent*) {
    markDirty();
}

// ─── zoom ─────────────────────────────────────────────────────────────────────

void EcgViewCanvas::zoomX(double factor, double centerSec) {
    double span  = m_xMax - m_xMin;
    double ratio = (span > 0) ? (centerSec - m_xMin) / span : 0.5;
    double ns    = span * factor;
    m_xMin = centerSec - ratio * ns;
    m_xMax = m_xMin + ns;
    clampView();
    markDirty();
    emit viewChanged(m_xMin, m_xMax);
}

void EcgViewCanvas::zoomY(double factor, double centerMV) {
    double span  = m_yMax - m_yMin;
    double ratio = (span > 0) ? (centerMV - m_yMin) / span : 0.5;
    double ns    = span * factor;
    m_yMin = centerMV - ratio * ns;
    m_yMax = m_yMin + ns;
    clampView();
    markDirty();
}

void EcgViewCanvas::wheelEvent(QWheelEvent* e) {
    double factor = (e->angleDelta().y() > 0) ? 0.8 : 1.25;
    auto [t, v] = pixelToData(e->position().toPoint());
    if (e->modifiers() & Qt::ControlModifier) zoomY(factor, v);
    else                                       zoomX(factor, t);
}

// ─── context menu ─────────────────────────────────────────────────────────────

void EcgViewCanvas::contextMenuEvent(QContextMenuEvent* e) {
    QMenu menu(this);
    auto addZoom = [&](const QString& s, double sec) {
        menu.addAction(s, [this, sec] {
            double mid = (m_xMin + m_xMax) / 2;
            m_xMin = qMax(0.0, mid - sec/2);
            m_xMax = m_xMin + sec;
            clampView(); markDirty();
            emit viewChanged(m_xMin, m_xMax);
        });
    };
    addZoom("2s",  2);  addZoom("5s",  5);  addZoom("10s", 10);
    addZoom("30s", 30); addZoom("60s", 60); addZoom("全覽", totalDuration());
    menu.addSeparator();
    menu.addAction("Y 軸自動縮放", [this]{ autoScaleY(); markDirty(); });
    menu.exec(e->globalPos());
}
