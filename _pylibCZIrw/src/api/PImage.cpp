#include "PImage.h"

using namespace libCZI;
using namespace std;

PImage::PImage(std::shared_ptr<libCZI::IBitmapData> bitMap) {

    this->ptrBitmapData = bitMap;
    
    auto lockData = this->ptrBitmapData->Lock();
    this->ptrData = lockData.ptrDataRoi;
    this->stride = lockData.stride;
 
}

PImage::~PImage() {
    this->ptrBitmapData->Unlock();
}

size_t PImage::get_itemsize() const {
    switch (this->get_pixelType())
    {
    case PixelType::Gray8:              return 1;
    case PixelType::Gray16:             return 2;
    case PixelType::Gray32Float:        return 4;
    case PixelType::Bgr24:              return 1;
    case PixelType::Bgr48:              return 2;
    case PixelType::Bgr96Float:         return 4;
    default:
        throw std::invalid_argument("illegal pixeltype");
    }
}

size_t PImage::GetNChannels() const {
    switch (this->get_pixelType())
    {
    case PixelType::Gray8:
    case PixelType::Gray16:
    case PixelType::Gray32Float:        return 1;
    case PixelType::Bgr24:
    case PixelType::Bgr48:
    case PixelType::Bgr96Float:         return 3;
    default:
        throw std::invalid_argument("illegal pixeltype");
    }
}

