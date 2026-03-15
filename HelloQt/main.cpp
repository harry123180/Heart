#include <QApplication>
#include <QWidget>
#include <QPushButton>
#include <QLabel>
#include <QVBoxLayout>
#include <QMessageBox>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    QWidget window;
    window.setWindowTitle("Hello Qt");
    window.setMinimumSize(300, 150);

    QVBoxLayout *layout = new QVBoxLayout(&window);

    QLabel *label = new QLabel("按下按鈕試試看", &window);
    label->setAlignment(Qt::AlignCenter);

    QPushButton *btn = new QPushButton("Hello World!", &window);

    QObject::connect(btn, &QPushButton::clicked, [&]() {
        QMessageBox::information(&window, "Hi", "你好，世界！\nQt 運作正常。");
        label->setText("按了！");
    });

    layout->addWidget(label);
    layout->addWidget(btn);

    window.show();
    return app.exec();
}
