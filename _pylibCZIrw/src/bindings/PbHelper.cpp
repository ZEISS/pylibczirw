#include "PbHelper.h"

std::string PbHelper::get_format(libCZI::PixelType pixelType) {
  switch (pixelType) {
  case libCZI::PixelType::Gray8:
    return py::format_descriptor<uint8_t>::format();
  case libCZI::PixelType::Gray16:
    return py::format_descriptor<uint16_t>::format();
  case libCZI::PixelType::Gray32Float:
    return py::format_descriptor<float>::format();
  case libCZI::PixelType::Bgr24:
    return py::format_descriptor<uint8_t>::format();
  case libCZI::PixelType::Bgr48:
    return py::format_descriptor<uint16_t>::format();
  case libCZI::PixelType::Bgr96Float:
    return py::format_descriptor<float>::format();
  default:
    throw std::invalid_argument("illegal pixeltype");
  }
}

std::shared_ptr<libCZI::IBitmapData>
PbHelper::BufferToBitmap(const py::buffer &buffer,
                         libCZI::PixelType pixelType) {

  py::buffer_info info = buffer.request();

  uint32_t width = info.shape[1];
  uint32_t height = info.shape[0];
  uint32_t stride = info.strides[0];

  auto bm =
      std::make_shared<CMemBitmapWrapper>(pixelType, width, height, stride);

  libCZI::ScopedBitmapLockerSP lckBm{bm};

  // This is no valid long term solution, should investigate other ways to
  // handle this without copying.
  memcpy(lckBm.ptrDataRoi, info.ptr, (size_t)(lckBm.size));

  return bm;
}
