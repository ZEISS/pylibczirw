cmake_minimum_required(VERSION 3.15)

cmake_policy(SET CMP0091 NEW) # enable new "MSVC runtime library selection" (https://cmake.org/cmake/help/latest/variable/CMAKE_MSVC_RUNTIME_LIBRARY.html)

# Use scikit-build-core's version if available, otherwise fall back to PYLIBCZIRW_VERSION
if(DEFINED SKBUILD_PROJECT_VERSION)
  set(_VERSION ${SKBUILD_PROJECT_VERSION})
elseif(DEFINED PYLIBCZIRW_VERSION)
  set(_VERSION ${PYLIBCZIRW_VERSION})
else()
  set(_VERSION "0.0.0")
endif()

project(_pylibCZIrw VERSION ${_VERSION})

# Ensure every target uses a modern C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# On macOS we don't need extra libs for std::atomic; avoid probe issues
if(APPLE)
  set(ADDITIONAL_LIBS_REQUIRED_FOR_ATOMIC "" CACHE INTERNAL "Additional libs for std::atomic" FORCE)
endif()

# Set library version in the code
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/_pylibCZIrw/src/pylibCZIrw_Config.h.in ${CMAKE_CURRENT_SOURCE_DIR}/_pylibCZIrw/src/pylibCZIrw_Config.h @ONLY)

# Instruct to use the static-version of the runtime library (on Windows)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# bring in libczi (which is a git-submodule of this repository)
set(LIBCZI_BUILD_UNITTESTS OFF CACHE BOOL "" FORCE)
set(LIBCZI_BUILD_DYNLIB OFF CACHE BOOL "" FORCE)
set(LIBCZI_BUILD_CZICMD OFF CACHE BOOL "" FORCE)
set(LIBCZI_DO_NOT_SET_MSVC_RUNTIME_LIBRARY ON CACHE BOOL "" FORCE)

set(BUILD_SHARED_LIBS FALSE CACHE BOOL "" FORCE)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

add_subdirectory(libs/libCZIrw)

# bring in pybind11
if(DEFINED SKBUILD)
  # scikit-build-core provides pybind11 via build requirements
  find_package(pybind11 CONFIG REQUIRED)
else()
  # Fallback for standalone CMake builds (e.g., development)
  add_subdirectory(libs/pybind11)
endif()

# static library containing the C-API
add_subdirectory(_pylibCZIrw/src/api)

# Python module exposing the C-API via pybind11
add_subdirectory(_pylibCZIrw/src/bindings)

# Install the extension module into the wheel root (imported as `import _pylibCZIrw`)
install(TARGETS _pylibCZIrw LIBRARY DESTINATION .)

# tests (only when not building via scikit-build)
if(NOT DEFINED SKBUILD)
  add_subdirectory(_pylibCZIrw/tests)
endif()