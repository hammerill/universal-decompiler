# TinyQuest reconstruction. C++17, CMake >= 3.20; MSVC (x64) on Windows, GCC/Clang (x86-64) on Linux.
cmake_minimum_required(VERSION 3.20)
project(tinyquest_reconstruction LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(CMAKE_SIZEOF_VOID_P EQUAL 4)
  message(WARNING "32-bit build: the release target is 64-bit")
endif()

add_executable(tinyquest
  src/main.cpp
  src/game/world.cpp
  src/game/text.cpp
  src/platform/platform_stdio.cpp)
target_include_directories(tinyquest PRIVATE src)
set_target_properties(tinyquest PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin/$<0:>")
if(MSVC)
  target_compile_options(tinyquest PRIVATE /W4 /permissive- /utf-8)
  target_compile_definitions(tinyquest PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(tinyquest PRIVATE -Wall -Wextra)
endif()
