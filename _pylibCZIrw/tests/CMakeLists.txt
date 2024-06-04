# Lines below are for building the main script which can help debugging c++ execution and add sanity check.
set(TARGET_MEMTEST mem_check)
add_executable(${TARGET_MEMTEST} "main.cpp")
target_include_directories(${TARGET_MEMTEST} PRIVATE ${libCZI_SOURCE_DIR})
target_link_libraries(${TARGET_MEMTEST} PRIVATE libCZIStatic JxrDecodeStatic _pylibCZIrw_API)