cmake_minimum_required(VERSION 3.16)
project(ECGViewer)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt5 REQUIRED COMPONENTS Core Gui Widgets Concurrent)

set(SOURCES
    main.cpp
    mainwindow.h      mainwindow.cpp
    dr200parser.h     dr200parser.cpp
    ecgview.h         ecgview.cpp
    ecgview_canvas.h  ecgview_canvas.cpp
    spectrumview.h    spectrumview.cpp
    app.rc
)

add_executable(ECGViewer WIN32 ${SOURCES})
target_compile_options(ECGViewer PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/utf-8>)
target_link_libraries(ECGViewer Qt5::Core Qt5::Gui Qt5::Widgets Qt5::Concurrent)
