# _pylibCZIrw is the actual python module - it links to the _pylibCZIrw_API library (and in turn to libCZI and other dependencies)

pybind11_add_module(_pylibCZIrw MODULE 
        CZIrw.cpp 
        PbHelper.h 
        PbHelper.cpp
        include_python.h)

target_link_libraries(_pylibCZIrw PRIVATE _pylibCZIrw_API)
target_include_directories(_pylibCZIrw PRIVATE ${libCZI_SOURCE_DIR})
target_compile_features(_pylibCZIrw PRIVATE cxx_std_17)
