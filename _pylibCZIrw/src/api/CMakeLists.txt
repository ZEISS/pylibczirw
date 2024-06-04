# the static library "_pylibCZIrw_API" containts the C-API for the python module "pylibCZIrw"

add_library(
  _pylibCZIrw_API STATIC 
  CZIreadAPI.cpp
  CZIwriteAPI.cpp
  PImage.cpp
  CZIreadAPI.h
  CZIwriteAPI.h
  PImage.h
  inc_libCzi.h
  site.h 
  site.cpp
  StaticContext.cpp
  StaticContext.h
  SubBlockCache.h)

target_include_directories(_pylibCZIrw_API PRIVATE ${libCZI_SOURCE_DIR})
target_link_libraries(_pylibCZIrw_API INTERFACE libCZIStatic JxrDecodeStatic)
target_compile_features(_pylibCZIrw_API PRIVATE cxx_std_17)
set_property(TARGET _pylibCZIrw_API PROPERTY POSITION_INDEPENDENT_CODE ON)
