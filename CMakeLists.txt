cmake_minimum_required(VERSION 3.24)

# Version is single-sourced by scikit-build-core's regex metadata provider
# from src/pytimestretch/__about__.py; CMake's own project() version is not
# read anywhere, so it stays a fixed placeholder.
project(pytimestretch LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

if(MSVC)
  # /utf-8: source files here (and in the vendored Rubber Band/Signalsmith
  # headers) are UTF-8; MSVC otherwise assumes the active code page.
  # /bigobj: nanobind's binding translation units generate enough sections
  # (template-heavy nb::class_/enum registrations) to exceed the default
  # COFF object's 2^16 section limit.
  add_compile_options(/utf-8 /bigobj)
endif()

find_package(Python 3.10 COMPONENTS Interpreter Development.Module REQUIRED)

execute_process(
  COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_STRIP_TRAILING_WHITESPACE
  OUTPUT_VARIABLE nanobind_ROOT
)
find_package(nanobind CONFIG REQUIRED)

# Pinned upstream revision, recorded into engine_info() so a build can be
# traced back to the exact submodule commit it was compiled against. Falls
# back to the plan's pinned tag when .git is unavailable (an sdist build
# ships the sources but not rubberband's own .git metadata).
set(PYTIMESTRETCH_RB_REVISION "v4.0.0")
find_package(Git QUIET)
if(Git_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/rubberband/.git")
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/extern/rubberband" rev-parse HEAD
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYTIMESTRETCH_RB_REVISION_GIT
    RESULT_VARIABLE PYTIMESTRETCH_RB_GIT_RESULT
  )
  if(PYTIMESTRETCH_RB_GIT_RESULT EQUAL 0 AND PYTIMESTRETCH_RB_REVISION_GIT)
    set(PYTIMESTRETCH_RB_REVISION "${PYTIMESTRETCH_RB_REVISION_GIT}")
  endif()
endif()

nanobind_add_module(
  _rubberband
  NB_STATIC
  native/rubberband_module.cpp
  extern/rubberband/single/RubberBandSingle.cpp
)

target_include_directories(_rubberband PRIVATE extern/rubberband)

# Rubber Band single-file build defines (pedalboard precedent, minus FFTW —
# we vendor the plain built-in FFT / vDSP configuration, no FFTW). These
# mirror RubberBandSingle.cpp's own `#ifndef ALREADY_CONFIGURED` defaults
# (USE_BQRESAMPLER=1, NO_THREADING via NO_THREADING/NO_TIMING/
# NO_THREAD_CHECKS, built-in FFT off Apple / vDSP on Apple) — set explicitly
# here rather than relying on the file's self-configuration, so the choice
# is visible and independently verifiable per platform.
target_compile_definitions(
  _rubberband
  PRIVATE
  ALREADY_CONFIGURED
  USE_BQRESAMPLER=1
  NO_TIMING=1
  NO_THREADING=1
  NO_THREAD_CHECKS=1
  PYTIMESTRETCH_RB_SOURCE_REVISION="${PYTIMESTRETCH_RB_REVISION}"
)

if(APPLE)
  target_compile_definitions(_rubberband PRIVATE HAVE_VDSP=1 PYTIMESTRETCH_RB_FFT="vdsp")
  find_library(ACCELERATE_FRAMEWORK Accelerate REQUIRED)
  target_link_libraries(_rubberband PRIVATE ${ACCELERATE_FRAMEWORK})
elseif(WIN32)
  target_compile_definitions(
    _rubberband
    PRIVATE
    USE_BUILTIN_FFT=1
    PYTIMESTRETCH_RB_FFT="builtin"
    _USE_MATH_DEFINES
    NOMINMAX
  )
else()
  target_compile_definitions(_rubberband PRIVATE USE_BUILTIN_FFT=1 PYTIMESTRETCH_RB_FFT="builtin")
endif()

install(TARGETS _rubberband LIBRARY DESTINATION pytimestretch)

# Signalsmith Stretch + Signalsmith Linear: header-only, vendored as git
# submodules. Declared as an INTERFACE library that owns their include
# paths for the _signalsmith module below.
add_library(signalsmith-stretch-headers INTERFACE)
target_include_directories(
  signalsmith-stretch-headers
  INTERFACE
  extern/signalsmith-stretch/include
  extern/signalsmith-linear/include
)

# Pinned upstream revisions for both signalsmith submodules, recorded into
# engine_info() the same way as Rubber Band's above. Falls back to the
# plan's pinned commit/tag when .git is unavailable (sdist build).
set(PYTIMESTRETCH_SS_REVISION "main@57b93f4")
set(PYTIMESTRETCH_SS_LINEAR_REVISION "0.3.1")
if(Git_FOUND)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/signalsmith-stretch/.git")
    execute_process(
      COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/extern/signalsmith-stretch" rev-parse HEAD
      OUTPUT_STRIP_TRAILING_WHITESPACE
      OUTPUT_VARIABLE PYTIMESTRETCH_SS_REVISION_GIT
      RESULT_VARIABLE PYTIMESTRETCH_SS_GIT_RESULT
    )
    if(PYTIMESTRETCH_SS_GIT_RESULT EQUAL 0 AND PYTIMESTRETCH_SS_REVISION_GIT)
      set(PYTIMESTRETCH_SS_REVISION "${PYTIMESTRETCH_SS_REVISION_GIT}")
    endif()
  endif()
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/signalsmith-linear/.git")
    execute_process(
      COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/extern/signalsmith-linear" rev-parse HEAD
      OUTPUT_STRIP_TRAILING_WHITESPACE
      OUTPUT_VARIABLE PYTIMESTRETCH_SS_LINEAR_REVISION_GIT
      RESULT_VARIABLE PYTIMESTRETCH_SS_LINEAR_GIT_RESULT
    )
    if(PYTIMESTRETCH_SS_LINEAR_GIT_RESULT EQUAL 0 AND PYTIMESTRETCH_SS_LINEAR_REVISION_GIT)
      set(PYTIMESTRETCH_SS_LINEAR_REVISION "${PYTIMESTRETCH_SS_LINEAR_REVISION_GIT}")
    endif()
  endif()
endif()

nanobind_add_module(
  _signalsmith
  NB_STATIC
  native/signalsmith_module.cpp
)

target_link_libraries(_signalsmith PRIVATE signalsmith-stretch-headers)

target_compile_definitions(
  _signalsmith
  PRIVATE
  PYTIMESTRETCH_SS_SOURCE_REVISION="${PYTIMESTRETCH_SS_REVISION}"
  PYTIMESTRETCH_SS_LINEAR_REVISION="${PYTIMESTRETCH_SS_LINEAR_REVISION}"
)

# signalsmith-linear's own CMakeLists (extern/signalsmith-linear/CMakeLists.txt)
# defaults SIGNALSMITH_USE_ACCELERATE to ON on Apple; we are not
# add_subdirectory-ing that file (its target isn't used — see the
# INTERFACE library above), so mirror that default explicitly here rather
# than silently losing it. Linux/Windows keep signalsmith-linear's built-in
# FFT (no flag needed).
if(APPLE)
  target_compile_definitions(_signalsmith PRIVATE SIGNALSMITH_USE_ACCELERATE ACCELERATE_NEW_LAPACK PYTIMESTRETCH_SS_FFT="accelerate")
  find_library(ACCELERATE_FRAMEWORK Accelerate REQUIRED)
  target_link_libraries(_signalsmith PRIVATE ${ACCELERATE_FRAMEWORK})
else()
  target_compile_definitions(_signalsmith PRIVATE PYTIMESTRETCH_SS_FFT="builtin")
endif()

install(TARGETS _signalsmith LIBRARY DESTINATION pytimestretch)
