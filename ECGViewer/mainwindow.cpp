#include "mainwindow.h"
#include <QMenuBar>
#include <QStatusBar>
#include <QFileDialog>
#include <QSplitter>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QFormLayout>
#include <QPushButton>
#include <QMessageBox>
#include <QHeaderView>
#include <QApplication>
#include <QTextStream>
#include <QFile>
#include <QProgressDialog>
#include <QAction>
#include <QtConcurrent/QtConcurrent>

// ─── 建構子 ───────────────────────────────────────────────────────────────────

MainWindow::MainWindow(QWidget* parent) : QMainWindow(parent) {
    setWindowTitle("DR200/HE Holter 心電圖檢視器");
    resize(1280, 760);
    setupUi();

    connect(&m_parseWatcher, &QFutureWatcher<ECGData>::finished,
            this, &MainWindow::onFileLoaded);

    // 預設深色模式
    m_actDark->setChecked(true);
    toggleDarkMode(true);
}

// ─── 介面配置 ─────────────────────────────────────────────────────────────────

void MainWindow::setupUi() {
    // ── 選單列 ──
    QMenu* fileMenu = menuBar()->addMenu("檔案(&F)");
    auto actOpen = fileMenu->addAction("開啟 .dat 檔案(&O)...");
    actOpen->setShortcut(QKeySequence::Open);
    connect(actOpen, &QAction::triggered, this, &MainWindow::openFile);
    fileMenu->addSeparator();
    auto actExport = fileMenu->addAction("匯出 CSV(&E)...");
    actExport->setShortcut(QKeySequence("Ctrl+E"));
    connect(actExport, &QAction::triggered, this, &MainWindow::exportCsv);
    fileMenu->addSeparator();
    fileMenu->addAction("結束(&X)", qApp, &QApplication::quit);

    QMenu* viewMenu = menuBar()->addMenu("檢視(&V)");
    viewMenu->addAction("重設視圖(&R)",     [this]{ m_ecgView->resetView(); })->setShortcut(QKeySequence("R"));
    viewMenu->addAction("顯示全部(&A)",     [this]{ if(m_ecg.valid) m_ecgView->setViewRange(0, m_ecgView->totalDuration()); });
    viewMenu->addAction("Y 軸自動縮放(&Y)", [this]{ m_ecgView->autoScaleY(); m_ecgView->update(); });
    viewMenu->addSeparator();
    viewMenu->addAction("縮放 5 秒",   [this]{ zoomViewTo(5.0);  })->setShortcut(QKeySequence("5"));
    viewMenu->addAction("縮放 10 秒",  [this]{ zoomViewTo(10.0); })->setShortcut(QKeySequence("1"));
    viewMenu->addAction("縮放 30 秒",  [this]{ zoomViewTo(30.0); })->setShortcut(QKeySequence("3"));
    viewMenu->addSeparator();
    m_actDark = viewMenu->addAction("深色模式(&D)");
    m_actDark->setCheckable(true);
    m_actDark->setShortcut(QKeySequence("D"));
    connect(m_actDark, &QAction::toggled, this, &MainWindow::toggleDarkMode);

    // ── 左側面板 ──
    QWidget* left = new QWidget;
    left->setFixedWidth(215);
    QVBoxLayout* lv = new QVBoxLayout(left);
    lv->setContentsMargins(6,6,6,6);
    lv->setSpacing(8);

    auto mkLbl = [](){ auto l=new QLabel("--"); l->setWordWrap(true); return l; };

    // 錄製資訊群組
    QGroupBox* gbInfo = new QGroupBox("錄製資訊");
    QFormLayout* fl = new QFormLayout(gbInfo);
    fl->setSpacing(3); fl->setContentsMargins(6,14,6,6);
    fl->addRow("檔案：",     m_lblFile     = mkLbl());
    fl->addRow("病患：",     m_lblPatient  = mkLbl());
    fl->addRow("日期：",     m_lblDate     = mkLbl());
    fl->addRow("序號：",     m_lblSN       = mkLbl());
    fl->addRow("時長：",     m_lblDuration = mkLbl());
    fl->addRow("樣本數：",   m_lblSamples  = mkLbl());
    fl->addRow("通道：",     m_lblChannels = mkLbl());
    fl->addRow("電極脫落：", m_lblLeadOff  = mkLbl());
    lv->addWidget(gbInfo);

    // 顯示設定群組
    QGroupBox* gbDisp = new QGroupBox("顯示設定");
    QVBoxLayout* dv = new QVBoxLayout(gbDisp);
    dv->setContentsMargins(6,14,6,6); dv->setSpacing(5);

    dv->addWidget(new QLabel("選擇通道："));
    m_chSel = new QComboBox;
    m_chSel->addItem("通道 0");
    connect(m_chSel, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &MainWindow::onChannelChanged);
    dv->addWidget(m_chSel);

    // 快速縮放按鈕
    dv->addWidget(new QLabel("快速縮放："));
    QHBoxLayout* zh = new QHBoxLayout;
    for (auto [lbl, sec] : std::initializer_list<std::pair<const char*, double>>{
            {"5秒",5},{"10秒",10},{"全部",-1}}) {
        auto btn = new QPushButton(lbl);
        btn->setFixedHeight(24);
        double s = sec;
        connect(btn, &QPushButton::clicked, [this,s]{
            if (s < 0) { if(m_ecg.valid) m_ecgView->setViewRange(0, m_ecgView->totalDuration()); }
            else zoomViewTo(s);
        });
        zh->addWidget(btn);
    }
    dv->addLayout(zh);
    lv->addWidget(gbDisp);

    // 匯出按鈕
    auto btnExp = new QPushButton("匯出 CSV（全部）");
    btnExp->setFixedHeight(30);
    connect(btnExp, &QPushButton::clicked, this, &MainWindow::exportCsv);
    lv->addWidget(btnExp);

    // 區間匯出群組
    QGroupBox* gbRange = new QGroupBox("區間選擇");
    QVBoxLayout* rv = new QVBoxLayout(gbRange);
    rv->setContentsMargins(6,14,6,6); rv->setSpacing(5);

    QFormLayout* rf = new QFormLayout;
    rf->setSpacing(3);
    m_spinRangeStart = new QDoubleSpinBox;
    m_spinRangeStart->setRange(0, 99999); m_spinRangeStart->setDecimals(2);
    m_spinRangeStart->setSuffix(" 秒"); m_spinRangeStart->setValue(0);
    m_spinRangeEnd = new QDoubleSpinBox;
    m_spinRangeEnd->setRange(0, 99999); m_spinRangeEnd->setDecimals(2);
    m_spinRangeEnd->setSuffix(" 秒"); m_spinRangeEnd->setValue(10);
    rf->addRow("起始：", m_spinRangeStart);
    rf->addRow("結束：", m_spinRangeEnd);
    rv->addLayout(rf);

    auto btnJump = new QPushButton("跳至此區間");
    btnJump->setFixedHeight(26);
    connect(btnJump, &QPushButton::clicked, this, [this]{
        m_ecgView->setViewRange(m_spinRangeStart->value(), m_spinRangeEnd->value());
    });
    rv->addWidget(btnJump);

    auto btnRangeExp = new QPushButton("匯出此區間 CSV");
    btnRangeExp->setFixedHeight(26);
    connect(btnRangeExp, &QPushButton::clicked, this, &MainWindow::exportRangeCsv);
    rv->addWidget(btnRangeExp);

    lv->addWidget(gbRange);
    lv->addStretch();

    // ── 主要分頁 ──
    m_tabs = new QTabWidget;
    m_tabs->setDocumentMode(true);

    m_ecgView = new EcgViewCanvas;
    connect(m_ecgView, &EcgViewCanvas::viewChanged,   this, &MainWindow::onViewChanged);
    connect(m_ecgView, &EcgViewCanvas::sampleHovered, this, &MainWindow::onSampleHovered);
    m_tabs->addTab(m_ecgView, "心電圖檢視");

    m_specView = new SpectrumView;
    m_tabs->addTab(m_specView, "頻譜分析");

    m_table = new QTableWidget;
    m_table->setColumnCount(5);
    m_table->setHorizontalHeaderLabels({"索引","時間(秒)","微伏(uV)","毫伏(mV)","電極脫落"});
    m_table->horizontalHeader()->setStretchLastSection(true);
    m_table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_table->setAlternatingRowColors(true);
    m_tabs->addTab(m_table, "數據表格");

    connect(m_tabs, &QTabWidget::currentChanged, this, [this](int i){
        if (i == 2) fillTable();
    });

    // ── 分割器 ──
    QSplitter* sp = new QSplitter(Qt::Horizontal);
    sp->addWidget(left);
    sp->addWidget(m_tabs);
    sp->setStretchFactor(0, 0);
    sp->setStretchFactor(1, 1);
    sp->setSizes({215, 1065});
    setCentralWidget(sp);

    // ── 狀態列 ──
    m_statusLeft  = new QLabel("就緒 — 請透過「檔案 \u2192 開啟」載入 .dat 檔案");
    m_statusRight = new QLabel;
    statusBar()->addWidget(m_statusLeft, 1);
    statusBar()->addPermanentWidget(m_statusRight);
}

// ─── 深色模式 ─────────────────────────────────────────────────────────────────

void MainWindow::toggleDarkMode(bool dark) {
    m_dark = dark;
    m_ecgView->setDarkMode(dark);
    m_specView->setDarkMode(dark);
    applyThemeToWindow(dark);
}

void MainWindow::applyThemeToWindow(bool dark) {
    if (dark) {
        qApp->setStyleSheet(
            "QMainWindow, QWidget { background:#0D1525; color:#C0D0E0; }"
            "QMenuBar { background:#0D1525; color:#C0D0E0; }"
            "QMenuBar::item:selected { background:#1A2840; }"
            "QMenu { background:#0D1525; color:#C0D0E0; border:1px solid #2A4060; }"
            "QMenu::item:selected { background:#1A3050; }"
            "QGroupBox { border:1px solid #2A4060; border-radius:4px; margin-top:6px;"
            "            color:#90CAF9; font-weight:bold; font-size:11px; }"
            "QGroupBox::title { subcontrol-origin:margin; left:6px; color:#90CAF9; }"
            "QTabWidget::pane { border:1px solid #2A4060; }"
            "QTabBar::tab { background:#0D1525; color:#90CAF9; padding:5px 14px; border:1px solid #2A4060; }"
            "QTabBar::tab:selected { background:#1A3050; color:#E0F0FF; }"
            "QPushButton { background:#1A3050; color:#90CAF9; border:1px solid #2A4060;"
            "              border-radius:3px; padding:4px 8px; }"
            "QPushButton:hover { background:#2A4060; }"
            "QComboBox { background:#1A3050; color:#C0D0E0; border:1px solid #2A4060; padding:3px; }"
            "QComboBox QAbstractItemView { background:#0D1525; color:#C0D0E0; "
            "                              selection-background-color:#1A3050; }"
            "QLabel { color:#C0D0E0; font-size:11px; }"
            "QStatusBar { background:#060E18; color:#90A0B0; }"
            "QTableWidget { background:#0D1B2A; color:#C0D0E0; gridline-color:#1A2840;"
            "               alternate-background-color:#111F30; }"
            "QHeaderView::section { background:#0D1525; color:#90CAF9; border:1px solid #2A4060; padding:3px; }"
            "QScrollBar:vertical { background:#0D1525; width:10px; border:none; }"
            "QScrollBar::handle:vertical { background:#2A4060; border-radius:4px; min-height:20px; }"
            "QScrollBar:horizontal { background:#0D1525; height:10px; border:none; }"
            "QScrollBar::handle:horizontal { background:#2A4060; border-radius:4px; min-width:20px; }"
            "QSplitter::handle { background:#1A2840; }"
        );
    } else {
        qApp->setStyleSheet("");
    }
}

// ─── 開啟檔案（背景執行緒）────────────────────────────────────────────────────

void MainWindow::openFile() {
    if (m_parseWatcher.isRunning()) return;

    QString path = QFileDialog::getOpenFileName(
        this, "開啟 Holter .dat 檔案", QString(),
        "Holter 資料 (*.dat);;所有檔案 (*.*)");
    if (path.isEmpty()) return;
    openFilePath(path);
}

void MainWindow::openFilePath(const QString& path) {
    if (m_parseWatcher.isRunning()) return;

    setWindowTitle("載入中... — DR200/HE 心電圖檢視器");
    m_statusLeft->setText("背景解析中：" + path);
    m_ecgView->setData({}, {}, 180);
    m_specView->clear();

    QFuture<ECGData> fut = QtConcurrent::run(
        [path](){ return DR200Parser::parse(path); });
    m_parseWatcher.setFuture(fut);
}

void MainWindow::onFileLoaded() {
    ECGData data = m_parseWatcher.result();

    if (!data.valid) {
        QMessageBox::critical(this, "錯誤", "解析失敗：\n" + data.errorMsg);
        setWindowTitle("DR200/HE 心電圖檢視器");
        m_statusLeft->setText("載入失敗。");
        return;
    }

    m_ecg = data;

    m_chSel->blockSignals(true);
    m_chSel->clear();
    for (int ch = 0; ch < data.numChannels; ch++)
        m_chSel->addItem(QString("通道 %1").arg(ch));
    m_chSel->blockSignals(false);

    loadData(data);
    setWindowTitle(QString("心電圖檢視器 — 病患 %1 | %2 %3")
                       .arg(data.patientId.isEmpty() ? "未知" : data.patientId)
                       .arg(data.startDate).arg(data.startTime));
}

void MainWindow::loadData(const ECGData& d) {
    int ch = qBound(0, m_chSel->currentIndex(), qMax(0, d.numChannels-1));
    if (d.valid && ch < d.channels_uv.size()) {
        m_ecgView->setData(d.channels_uv[ch], d.leadOff[ch], d.sampleRate);
        m_specView->setData(d.channels_uv[ch], d.leadOff[ch], d.sampleRate);
    }
    updateInfoPanel();

    if (d.totalSamples == 0) {
        m_statusLeft->setText(
            QString("已載入（無信號）：病患 %1 | %2 — 此錄製檔案不含 ECG 資料")
                .arg(d.patientId.isEmpty() ? "未知" : d.patientId)
                .arg(d.startDate + " " + d.startTime));
    } else {
        m_statusLeft->setText(
            QString("已載入：病患 %1 | %2 | %3 秒 | %4 個樣本")
                .arg(d.patientId).arg(d.startDate+" "+d.startTime)
                .arg(d.durationSec,0,'f',1).arg(d.totalSamples));
    }
}

// ─── 資訊面板 ─────────────────────────────────────────────────────────────────

void MainWindow::updateInfoPanel() {
    if (!m_ecg.valid) return;
    const ECGData& d = m_ecg;
    m_lblFile->setText(d.rawConfig.value("_filepath").section('/',-1).section('\\',-1));
    m_lblPatient->setText(d.patientId.isEmpty() ? "--" : d.patientId);
    m_lblDate->setText(d.startDate + "\n" + d.startTime);
    m_lblSN->setText(d.serialNumber + " " + d.firmware);
    m_lblDuration->setText(QString("%1 秒（%2 分）")
                               .arg(d.durationSec,0,'f',1).arg(d.durationSec/60,0,'f',2));
    m_lblSamples->setText(QString::number(d.totalSamples));
    m_lblChannels->setText(QString("%1 通道 @ %2 Hz  [fmt:%3]")
                               .arg(d.numChannels)
                               .arg(d.sampleRate,0,'f',0)
                               .arg(d.rawConfig.value("SampleStorageFormat","?")));

    if (!d.leadOff.isEmpty() && !d.leadOff[0].isEmpty()) {
        int lo = (int)std::count(d.leadOff[0].constBegin(), d.leadOff[0].constEnd(), true);
        double pct = 100.0 * lo / d.leadOff[0].size();
        m_lblLeadOff->setText(QString("%1%").arg(pct,0,'f',1));
        m_lblLeadOff->setStyleSheet(pct > 20 ? "color:#FF6060;" : "color:#66BB6A;");
    }
}

// ─── 通道切換 ─────────────────────────────────────────────────────────────────

void MainWindow::onChannelChanged(int ch) {
    if (!m_ecg.valid || ch < 0 || ch >= m_ecg.numChannels) return;
    m_ecgView->setData(m_ecg.channels_uv[ch], m_ecg.leadOff[ch], m_ecg.sampleRate);
    m_specView->setData(m_ecg.channels_uv[ch], m_ecg.leadOff[ch], m_ecg.sampleRate);
}

// ─── 狀態回呼 ─────────────────────────────────────────────────────────────────

void MainWindow::onViewChanged(double xMin, double xMax) {
    m_statusRight->setText(
        QString("視圖：%1 \u2013 %2 秒  |  範圍：%3 秒")
            .arg(xMin,0,'f',2).arg(xMax,0,'f',2).arg(xMax-xMin,0,'f',2));
    // sync spinboxes to current view
    if (m_spinRangeStart && m_spinRangeEnd) {
        m_spinRangeStart->blockSignals(true);
        m_spinRangeEnd->blockSignals(true);
        m_spinRangeStart->setValue(xMin);
        m_spinRangeEnd->setValue(xMax);
        m_spinRangeStart->blockSignals(false);
        m_spinRangeEnd->blockSignals(false);
    }
}

void MainWindow::onSampleHovered(double t, double uv, bool onSig) {
    m_statusLeft->setText(
        onSig
        ? QString("時間 = %1 秒    %2 微伏（%3 毫伏）")
              .arg(t,0,'f',3).arg(uv,0,'f',1).arg(uv/1000,0,'f',3)
        : QString("時間 = %1 秒").arg(t,0,'f',3));
}

// ─── 縮放輔助 ─────────────────────────────────────────────────────────────────

void MainWindow::zoomViewTo(double sec) {
    if (!m_ecg.valid) return;
    double mid = (m_ecgView->viewXMin() + m_ecgView->viewXMax()) / 2;
    m_ecgView->setViewRange(qMax(0.0, mid - sec/2), mid + sec/2);
}

// ─── 數據表格 ─────────────────────────────────────────────────────────────────

void MainWindow::fillTable() {
    if (!m_ecg.valid) return;
    int ch = qBound(0, m_chSel->currentIndex(), m_ecg.numChannels-1);
    const auto& data = m_ecg.channels_uv[ch];
    const auto& lo   = m_ecg.leadOff[ch];
    double sr = m_ecg.sampleRate;

    int iStart = qMax(0, (int)(m_ecgView->viewXMin()*sr));
    int iEnd   = qMin(data.size()-1, (int)(m_ecgView->viewXMax()*sr));
    if (iEnd - iStart > 4999) iEnd = iStart + 4999;

    int n = iEnd - iStart + 1;
    m_table->setUpdatesEnabled(false);
    m_table->setRowCount(n);

    for (int row = 0; row < n; row++) {
        int i  = iStart + row;
        bool lf = (i < lo.size()) && lo[i];
        float uv = data[i];

        auto ci = [lf](const QString& s) {
            auto item = new QTableWidgetItem(s);
            if (lf) item->setBackground(QColor(100,30,30));
            return item;
        };
        m_table->setItem(row, 0, ci(QString::number(i)));
        m_table->setItem(row, 1, ci(QString::number((double)i/sr,'f',4)));
        m_table->setItem(row, 2, ci(lf ? "電極脫落" : QString::number(uv,'f',1)));
        m_table->setItem(row, 3, ci(lf ? "電極脫落" : QString::number(uv/1000,'f',4)));
        m_table->setItem(row, 4, ci(lf ? "是" : "否"));
    }
    m_table->setUpdatesEnabled(true);
    m_table->resizeColumnsToContents();
}

// ─── 區間 CSV 匯出 ────────────────────────────────────────────────────────────

void MainWindow::exportRangeCsv() {
    if (!m_ecg.valid) {
        QMessageBox::information(this, "匯出", "尚未載入資料。");
        return;
    }

    double t0 = m_spinRangeStart->value();
    double t1 = m_spinRangeEnd->value();
    if (t0 >= t1) {
        QMessageBox::warning(this, "區間錯誤", "結束時間必須大於起始時間。");
        return;
    }

    QString path = QFileDialog::getSaveFileName(
        this, "匯出區間 CSV", QString(), "CSV 檔案 (*.csv)");
    if (path.isEmpty()) return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        QMessageBox::critical(this, "錯誤", "無法寫入：" + path);
        return;
    }

    double sr = m_ecg.sampleRate;
    int iStart = qMax(0,            (int)(t0 * sr));
    int iEnd   = qMin(m_ecg.totalSamples - 1, (int)(t1 * sr));

    file.write("\xEF\xBB\xBF"); // UTF-8 BOM for Excel
    QTextStream out(&file);
    out.setCodec("UTF-8");
    out << QString::fromUtf8("# DR200/HE 區間匯出\n")
        << QString::fromUtf8("# 病患：") << m_ecg.patientId << "\n"
        << QString::fromUtf8("# 日期：") << m_ecg.startDate << " " << m_ecg.startTime << "\n"
        << QString::fromUtf8("# 區間：") << t0 << " ~ " << t1 << QString::fromUtf8(" 秒\n")
        << QString::fromUtf8("# 取樣率：") << sr << " Hz\n#\n";

    out << QString::fromUtf8("索引,時間(秒)");
    for (int ch = 0; ch < m_ecg.numChannels; ch++)
        out << QString(",通道%1微伏,通道%1毫伏,通道%1電極脫落").arg(ch);
    out << "\n";

    int n = iEnd - iStart + 1;
    QProgressDialog prog("匯出區間中...", "取消", 0, n, this);
    prog.setWindowModality(Qt::WindowModal);
    prog.setWindowTitle("匯出區間 CSV");

    for (int i = iStart; i <= iEnd; i++) {
        int row = i - iStart;
        if (row % 5000 == 0) { prog.setValue(row); qApp->processEvents(); }
        if (prog.wasCanceled()) break;
        out << i << "," << QString::number((double)i / sr, 'f', 5);
        for (int ch = 0; ch < m_ecg.numChannels; ch++) {
            bool lf = (i < m_ecg.leadOff[ch].size()) && m_ecg.leadOff[ch][i];
            float uv = m_ecg.channels_uv[ch][i];
            if (lf) out << ",,,1";
            else out << "," << QString::number(uv, 'f', 2)
                     << "," << QString::number(uv / 1000, 'f', 5) << ",0";
        }
        out << "\n";
    }
    prog.setValue(n);
    QMessageBox::information(this, "匯出完成",
        QString("已匯出 %1 筆資料（%2 ~ %3 秒）至：\n%4")
            .arg(n).arg(t0, 0, 'f', 2).arg(t1, 0, 'f', 2).arg(path));
}

// ─── CSV 匯出 ─────────────────────────────────────────────────────────────────

void MainWindow::exportCsv() {
    if (!m_ecg.valid) {
        QMessageBox::information(this, "匯出", "尚未載入資料。");
        return;
    }

    QString path = QFileDialog::getSaveFileName(
        this, "匯出 CSV", QString(), "CSV 檔案 (*.csv)");
    if (path.isEmpty()) return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly|QIODevice::Text)) {
        QMessageBox::critical(this, "錯誤", "無法寫入：" + path);
        return;
    }

    file.write("\xEF\xBB\xBF"); // UTF-8 BOM for Excel
    QTextStream out(&file);
    out.setCodec("UTF-8");
    out << QString::fromUtf8("# DR200/HE Holter 心電圖匯出\n")
        << QString::fromUtf8("# 病患：") << m_ecg.patientId << "\n"
        << QString::fromUtf8("# 日期：") << m_ecg.startDate << " " << m_ecg.startTime << "\n"
        << QString::fromUtf8("# 序號：") << m_ecg.serialNumber << " " << m_ecg.firmware << "\n"
        << QString::fromUtf8("# 取樣率：") << m_ecg.sampleRate << " Hz\n"
        << QString::fromUtf8("# 通道數：") << m_ecg.numChannels << "\n"
        << QString::fromUtf8("# 比例：12.5 uV/LSB，ADC 中心值 2048\n#\n");

    out << QString::fromUtf8("索引,時間(秒)");
    for (int ch = 0; ch < m_ecg.numChannels; ch++)
        out << QString(",通道%1微伏,通道%1毫伏,通道%1電極脫落").arg(ch);
    out << "\n";

    int n = m_ecg.totalSamples;
    QProgressDialog prog("匯出中...", "取消", 0, n, this);
    prog.setWindowModality(Qt::WindowModal);
    prog.setWindowTitle("匯出 CSV");

    for (int i = 0; i < n; i++) {
        if (i % 5000 == 0) { prog.setValue(i); qApp->processEvents(); }
        if (prog.wasCanceled()) break;
        out << i << "," << QString::number((double)i/m_ecg.sampleRate,'f',5);
        for (int ch = 0; ch < m_ecg.numChannels; ch++) {
            bool lf = (i < m_ecg.leadOff[ch].size()) && m_ecg.leadOff[ch][i];
            float uv = m_ecg.channels_uv[ch][i];
            if (lf) out << ",,,1";
            else out << "," << QString::number(uv,'f',2)
                     << "," << QString::number(uv/1000,'f',5) << ",0";
        }
        out << "\n";
    }
    prog.setValue(n);
    QMessageBox::information(this, "匯出完成",
        QString("已匯出 %1 筆資料至：\n%2").arg(n).arg(path));
}
