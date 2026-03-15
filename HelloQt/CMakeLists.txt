cmake_minimum_required(VERSION 3.16)
project(HelloQt)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt5 REQUIRED COMPONENTS Core Gui Widgets)

add_executable(HelloQt WIN32 main.cpp)

target_compile_options(HelloQt PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/utf-8>)
target_link_libraries(HelloQt Qt5::Core Qt5::Gui Qt5::Widgets)
