#include <cstdio>
#include <cstdlib>
#include <locale>
#include <codecvt>
#include <string>
#include <chrono>

#include "../src/api/CZIreadAPI.h"

void mem_test_read(std::wstring filepath, std::string coordinates, std::wstring scenefilter) {

    CZIreadAPI czi(filepath.c_str());

    std::cout << "Metadata: " << czi.GetXmlMetadata() << std::endl;

    auto pixeltype = libCZI::PixelType::Gray8;
    auto roi = libCZI::IntRect{ 0, 0, 100, 100 };
    auto bgColor = libCZI::RgbFloatColor{ 0,0,0 };

    auto start = std::chrono::high_resolution_clock::now();

    auto bitmap = czi.GetSingleChannelScalingTileAccessorData(pixeltype, roi, bgColor, 1.0, coordinates, scenefilter);

    auto done = std::chrono::high_resolution_clock::now();

    std::cout << "Duration(milliseconds): " << std::chrono::duration_cast<std::chrono::milliseconds>(done - start).count() << std::endl;

}



int main(int argc, char* argv[]) {
    if (argc != 4) {
        std::cout << "Example Usage: mem_check image.czi T0Z0C0 1" << std::endl;
        std::cerr << "Program called with insufficient or excess arguments!" << std::endl;
        exit(0);
    }

    std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> converter;
    std::wstring filepath = converter.from_bytes(argv[1]);
    std::string coordinates = argv[2];
    std::wstring scenefilter = converter.from_bytes(argv[3]);

    mem_test_read(filepath, argv[2], scenefilter);
    
    return 0;
}
