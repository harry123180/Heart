#pragma once
#include <QMainWindow>
#include <QLabel>
#include <QComboBox>
#include <QTableWidget>
#include <QTabWidget>
#include <QFutureWatcher>
#include "dr200parser.h"
#include "ecgview_canvas.h"
#include "spectrumview.h"

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit MainWindow(QWidget* parent = nullptr);
    void openFilePath(const QString& path);   // open a specific file (cmd-line / drag-drop)

private slots:
    void openFile();
    void exportCsv();
    void onFileLoaded();           // called when background parse finishes
    void onChannelChanged(int ch);
    void onViewChanged(double xMin, double xMax);
    void onSampleHovered(double t, double uv, bool onSignal);
    void fillTable();
    void zoomViewTo(double sec);
    void toggleDarkMode(bool dark);

private:
    void setupUi();
    void applyThemeToWindow(bool dark);
    void loadData(const ECGData& d);
    void updateInfoPanel();

    ECGData m_ecg;
    bool    m_dark = true;   // 預設深色模式
    QAction* m_actDark = nullptr;

    // Background file parsing
    QFutureWatcher<ECGData> m_parseWatcher;

    // ── left panel labels ──
    QLabel*    m_lblFile;
    QLabel*    m_lblPatient;
    QLabel*    m_lblDate;
    QLabel*    m_lblSN;
    QLabel*    m_lblDuration;
    QLabel*    m_lblSamples;
    QLabel*    m_lblChannels;
    QLabel*    m_lblLeadOff;
    QComboBox* m_chSel;

    // ── main area ──
    QTabWidget*   m_tabs;
    EcgViewCanvas* m_ecgView;
    SpectrumView* m_specView;
    QTableWidget* m_table;

    // ── status ──
    QLabel* m_statusLeft;
    QLabel* m_statusRight;
};
