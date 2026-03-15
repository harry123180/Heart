#include <QApplication>
#include "mainwindow.h"

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    app.setApplicationName("DR200/HE ECG Viewer");
    app.setOrganizationName("HeartLab");

    MainWindow w;
    w.show();

    // If a file path is given on the command line, open it immediately
    // e.g. ECGViewer.exe "C:\path\to\recording.dat"
    if (argc >= 2) {
        QString path = QString::fromLocal8Bit(argv[1]);
        if (!path.isEmpty())
            w.openFilePath(path);
    }

    return app.exec();
}
