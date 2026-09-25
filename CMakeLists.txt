cmake_minimum_required(VERSION 3.24)

# Version is single-sourced by scikit-build-core's regex metadata provider
# from src/pytimestretch/__about__.py; CMake's own project() version is not
# read anywhere, so it stays a fixed placeholder.
project(pytimestretch LANGUAGES C CXX)

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
# back to the pinned upstream tag when .git is unavailable (an sdist build
# ships the sources but not rubberband's own .git metadata).
set(PYTIMESTRETCH_RB_REVISION "v4.0.0")
find_package(Git QUIET)
if(Git_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/rubberband/.git")
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/extern/rubberband" rev-parse HEAD
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYTIMESTRETCH_RB_REVISION_GIT
    RESULT_VARIABLE PYTIMESTRETCH_RB_GIT_RESULT
    ERROR_QUIET
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
      ERROR_QUIET
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
      ERROR_QUIET
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

# libpaulstretch v0.3.0 has a distinct, approximate-duration creative
# contract. Build its C++20 core and bundled KissFFT without invoking its
# top-level CMake (which would also configure examples/WASM and may fetch
# PFFFT). Existing engine targets remain C++17.
set(PYTIMESTRETCH_PAULSTRETCH_REVISION "v0.3.0")
if(Git_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/libpaulstretch/.git")
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/extern/libpaulstretch" rev-parse HEAD
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYTIMESTRETCH_PAULSTRETCH_REVISION_GIT
    RESULT_VARIABLE PYTIMESTRETCH_PAULSTRETCH_GIT_RESULT
    ERROR_QUIET
  )
  if(PYTIMESTRETCH_PAULSTRETCH_GIT_RESULT EQUAL 0 AND PYTIMESTRETCH_PAULSTRETCH_REVISION_GIT)
    set(PYTIMESTRETCH_PAULSTRETCH_REVISION "${PYTIMESTRETCH_PAULSTRETCH_REVISION_GIT}")
  endif()
endif()

add_library(paulstretch-core STATIC
  extern/libpaulstretch/src/paulstretch.cpp
  extern/libpaulstretch/vendor/kissfft/kiss_fft.c
  extern/libpaulstretch/vendor/kissfft/kiss_fftr.c
)
target_compile_features(paulstretch-core PUBLIC cxx_std_20)
target_compile_definitions(paulstretch-core PRIVATE KISSFFT)
target_include_directories(paulstretch-core
  PUBLIC extern/libpaulstretch/include
  PRIVATE extern/libpaulstretch/vendor/kissfft
)

nanobind_add_module(_paulstretch NB_STATIC native/paulstretch_module.cpp)
target_compile_features(_paulstretch PRIVATE cxx_std_20)
target_link_libraries(_paulstretch PRIVATE paulstretch-core)
target_compile_definitions(_paulstretch PRIVATE
  PYTIMESTRETCH_PAULSTRETCH_SOURCE_REVISION="${PYTIMESTRETCH_PAULSTRETCH_REVISION}"
)
install(TARGETS _paulstretch LIBRARY DESTINATION pytimestretch)

# Bungee Basic v2.4.30 is a separate position-curve operation. Compile its
# pinned sources directly: upstream's top-level CMake also builds the CLI,
# asks for a newer CMake version, and would link a shared Bungee library.
# The nested Eigen/PFFFT submodules are pinned by Bungee's gitlink commits.
set(PYTIMESTRETCH_BUNGEE_REVISION "8cb6977d0c1a1b411ac320493b3c7f5182ed2d22")
if(Git_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/bungee/.git")
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/extern/bungee" rev-parse HEAD
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYTIMESTRETCH_BUNGEE_REVISION_GIT
    RESULT_VARIABLE PYTIMESTRETCH_BUNGEE_GIT_RESULT
    ERROR_QUIET
  )
  if(PYTIMESTRETCH_BUNGEE_GIT_RESULT EQUAL 0 AND PYTIMESTRETCH_BUNGEE_REVISION_GIT)
    set(PYTIMESTRETCH_BUNGEE_REVISION "${PYTIMESTRETCH_BUNGEE_REVISION_GIT}")
  endif()
endif()

add_library(bungee-pffft STATIC
  extern/bungee/submodules/pffft/pffft.c
  extern/bungee/submodules/pffft/fftpack.c
)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(bungee-pffft PRIVATE -ffast-math -fno-finite-math-only -fno-exceptions)
endif()

add_library(bungee-core STATIC
  extern/bungee/src/Assert.cpp
  extern/bungee/src/Fourier.cpp
  extern/bungee/src/Grain.cpp
  extern/bungee/src/Grains.cpp
  extern/bungee/src/Input.cpp
  extern/bungee/src/Instrumentation.cpp
  extern/bungee/src/Output.cpp
  extern/bungee/src/Partials.cpp
  extern/bungee/src/Stretch.cpp
  extern/bungee/src/Stretcher.cpp
  extern/bungee/src/Synthesis.cpp
  extern/bungee/src/Timing.cpp
  extern/bungee/src/Window.cpp
  extern/bungee/src/version.cpp
)
target_compile_features(bungee-core PUBLIC cxx_std_20)
target_include_directories(bungee-core
  PUBLIC extern/bungee
  PRIVATE extern/bungee/submodules/eigen extern/bungee/submodules
)
target_compile_definitions(bungee-core PRIVATE
  BUNGEE_VERSION="2.4.30"
  BUNGEE_SELF_TEST=0
  eigen_assert=BUNGEE_ASSERT1
  EIGEN_DONT_PARALLELIZE=1
)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(bungee-core PRIVATE -fwrapv)
endif()
target_link_libraries(bungee-core PRIVATE bungee-pffft)

nanobind_add_module(_bungee NB_STATIC native/bungee_module.cpp)
target_compile_features(_bungee PRIVATE cxx_std_20)
target_link_libraries(_bungee PRIVATE bungee-core bungee-pffft)
target_compile_definitions(_bungee PRIVATE
  PYTIMESTRETCH_BUNGEE_SOURCE_REVISION="${PYTIMESTRETCH_BUNGEE_REVISION}"
)
install(TARGETS _bungee LIBRARY DESTINATION pytimestretch)
