# The "original": a small game engine compiled the way a shipped binary would be: optimised, no symbols.
cmake_minimum_required(VERSION 3.20)
project(tinyquest_original LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_executable(tinyquest src/tinyquest.cpp)
set_target_properties(tinyquest PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin/$<0:>")
if(MSVC)
  # no PDB, no debug info
  target_compile_options(tinyquest PRIVATE /O1 /Ob0 /GS-)
  target_link_options(tinyquest PRIVATE /DEBUG:NONE)
  target_compile_definitions(tinyquest PRIVATE _CRT_SECURE_NO_WARNINGS)
elseif(APPLE)
  # macOS executables are always PIE; Apple's ld calls -s obsolete, -x drops every local symbol
  target_compile_options(tinyquest PRIVATE -O1 -fno-inline)
  target_link_options(tinyquest PRIVATE -Wl,-x)
else()
  # -fno-inline keeps the functions apart (like many older games); -s strips every symbol
  target_compile_options(tinyquest PRIVATE -O1 -fno-inline -fno-pie)
  target_link_options(tinyquest PRIVATE -s -no-pie)
endif()
