cmake_minimum_required(VERSION 3.20)

project(gpilc VERSION 1.0.0 LANGUAGES CXX)

add_executable(gpilc src/main.cpp)
target_compile_features(gpilc PRIVATE cxx_std_20)

if(MSVC)
    target_compile_options(gpilc PRIVATE /W4 /permissive-)
else()
    target_compile_options(gpilc PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(MINGW)
    target_link_options(gpilc PRIVATE -static -static-libgcc -static-libstdc++)
endif()

enable_testing()
add_test(NAME gpilc-self-test COMMAND gpilc --self-test)
