cmake_minimum_required(VERSION 3.11)

cmake_policy(SET CMP0091 NEW) # enable new "MSVC runtime library selection" (https://cmake.org/cmake/help/latest/variable/CMAKE_MSVC_RUNTIME_LIBRARY.html)

project(_pylibCZIrw VERSION ${PYLIBCZIRW_VERSION})

# Set library version in the code
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/_pylibCZIrw/src/pylibCZIrw_Config.h.in ${CMAKE_CURRENT_SOURCE_DIR}/_pylibCZIrw/src/pylibCZIrw_Config.h @ONLY)

 # Instruct to use the static-version of the runtime library (on Windows) -> c.f. https://cmake.org/cmake/help/latest/variable/CMAKE_MSVC_RUNTIME_LIBRARY.html
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# bring in libczi (which is a git-submodule of this repository)
# we turn off some unnecessary things 
set(LIBCZI_BUILD_UNITTESTS OFF CACHE  BOOL "" FORCE)
set(LIBCZI_BUILD_DYNLIB OFF CACHE  BOOL "" FORCE)
set(LIBCZI_BUILD_CZICMD OFF CACHE  BOOL "" FORCE)
set(LIBCZI_DO_NOT_SET_MSVC_RUNTIME_LIBRARY ON CACHE  BOOL "" FORCE) # instruct to NOT set the runtime library (we do this ourselves above)

# this will instruct to build a static library for CPR (in case we download and build it ourselves within libCZI)
# TODO(JBL): - not sure whether it is a good idea to fiddle with this "general" variable here, is there are way to have it more specific to the CPR-build
#               (and maybe this should better be handled in libCZI)
#            - same applies to enabling PIC (position independent code) below - is there a way to do this more specific to the CPR-build?
#            - should we do this only for Linux - and maybe only if we build CPR ourselves?
set(BUILD_SHARED_LIBS FALSE CACHE  BOOL "" FORCE)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

add_subdirectory(libs/libCZIrw)

# bring in pybind11 (which is a git-submodule of this repository)
add_subdirectory(libs/pybind11)

# this is a static library containing the C-API which we want to expose to Python
add_subdirectory(_pylibCZIrw/src/api)

# this is the Python-module which we want to build, exposing the C-API (from above) to Python
add_subdirectory(_pylibCZIrw/src/bindings)

# bring in the tests specific to pylibCZIrw
add_subdirectory(_pylibCZIrw/tests)