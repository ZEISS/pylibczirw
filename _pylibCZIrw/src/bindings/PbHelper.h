#include "../api/CZIreadAPI.h"
#include "include_python.h"
#include <atomic>
#include <pybind11/chrono.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

/// This namespace is dedicated to helper functions
/// for pybind11 usage.
namespace PbHelper {

class CMemBitmapWrapper : public libCZI::IBitmapData {
private:
  void *ptrData;
  libCZI::PixelType pixeltype;
  std::uint32_t width;
  std::uint32_t height;
  std::uint32_t stride;
  std::atomic<int> lock_count = ATOMIC_VAR_INIT(0);

public:
  CMemBitmapWrapper(libCZI::PixelType pixeltype, std::uint32_t width,
                    std::uint32_t height, std::uint32_t stride)
      : pixeltype(pixeltype), width(width), height(height), stride(stride) {
    size_t s = this->stride * static_cast<size_t>(height);
    this->ptrData = malloc(s);
  }

  virtual ~CMemBitmapWrapper() { free(this->ptrData); }

  virtual libCZI::PixelType GetPixelType() const { return this->pixeltype; }

  virtual libCZI::IntSize GetSize() const {
    return libCZI::IntSize{this->width, this->height};
  }

  virtual libCZI::BitmapLockInfo Lock() {
    libCZI::BitmapLockInfo bitmapLockInfo;
    bitmapLockInfo.ptrData = this->ptrData;
    bitmapLockInfo.ptrDataRoi = this->ptrData;
    bitmapLockInfo.stride = this->stride;
    bitmapLockInfo.size = this->stride * static_cast<size_t>(this->height);
    std::atomic_fetch_add(&this->lock_count, 1);
    return bitmapLockInfo;
  }

  virtual void Unlock() { std::atomic_fetch_sub(&this->lock_count, 1); }

  virtual int GetLockCount() const {
    return std::atomic_load(&this->lock_count);
  }
};

/// Returns format descriptor corresponding to each libCZI::PixelType.
/// This is used for pybind11 buffer_protocol.
std::string get_format(libCZI::PixelType pixelType);

std::shared_ptr<libCZI::IBitmapData>
BufferToBitmap(const py::buffer &buffer, libCZI::PixelType pixelType);

} // namespace PbHelper
