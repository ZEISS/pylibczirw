#include "CZIreadAPI.h"
#include "StaticContext.h"
#include "libCZI_Site.h"

#include <algorithm>
#include <codecvt>
#include <cstddef>
#include <cstring>
#include <limits>
#include <locale>
#include <map>
#include <sstream>
#include <stdexcept>

using namespace libCZI;
using namespace std;

CZIreadAPI::CZIreadAPI(const std::wstring &fileName)
    : CZIreadAPI("", fileName, SubBlockCacheOptions()) {}

CZIreadAPI::CZIreadAPI(const std::wstring &fileName,
                       const SubBlockCacheOptions &subBlockCacheOptions)
    : CZIreadAPI("", fileName, subBlockCacheOptions) {}

CZIreadAPI::CZIreadAPI(const std::string &stream_class_name,
                       const std::wstring &fileName)
    : CZIreadAPI(stream_class_name, fileName, SubBlockCacheOptions()) {}

CZIreadAPI::CZIreadAPI(const std::string &stream_class_name,
                       const std::wstring &fileName,
                       const SubBlockCacheOptions &subBlockCacheOptions)
    : CZIreadAPI(stream_class_name, fileName, subBlockCacheOptions,
                 ReaderOptions()) {}

CZIreadAPI::CZIreadAPI(const std::string &stream_class_name,
                       const std::wstring &fileName,
                       const SubBlockCacheOptions &subBlockCacheOptions,
                       const ReaderOptions &readerOptions) {
  shared_ptr<IStream> stream;
  if (stream_class_name.empty() || stream_class_name == "standard") {
    stream = StreamsFactory::CreateDefaultStreamForFile(fileName.c_str());
  } else if (stream_class_name == "curl") {
    StreamsFactory::CreateStreamInfo create_info;
    create_info.class_name = kStaticContext.GetStreamClassNameForCurlReader();

    kStaticContext.SetDefaultPropertiesForReader(
        create_info); // and have the default-properties set for this class

    stream = StreamsFactory::CreateStream(create_info, fileName);
    if (!stream) {
      wstring_convert<codecvt_utf8<wchar_t>> utf8_conv;
      string filename_utf8 = utf8_conv.to_bytes(fileName);
      stringstream string_stream;
      string_stream << "Failed to create stream for stream class: "
                    << stream_class_name << " and filename: " << filename_utf8
                    << '.';
      throw std::runtime_error(string_stream.str());
    }
  }

  this->Open(stream, subBlockCacheOptions, readerOptions);
}

CZIreadAPI::CZIreadAPI(std::shared_ptr<libCZI::IStream> stream) {
  this->Open(std::move(stream), SubBlockCacheOptions(), ReaderOptions());
}

void CZIreadAPI::Open(std::shared_ptr<libCZI::IStream> stream,
                      const SubBlockCacheOptions &subBlockCacheOptions,
                      const ReaderOptions &readerOptions) {
  const auto reader = libCZI::CreateCZIReader();
  ICZIReader::OpenOptions openOptions;
  openOptions.SetDefault();
  openOptions.lax_subblock_coordinate_checks =
      readerOptions.laxSubblockCoordinateChecks;
  openOptions.ignore_sizem_for_pyramid_subblocks =
      readerOptions.ignoreSizeMForPyramidSubblocks;
  reader->Open(stream, &openOptions);
  this->spAccessor = reader->CreateSingleChannelScalingTileAccessor();
  this->spReader = reader;
  this->subBlockCacheOptions = subBlockCacheOptions;
  this->readerOptions = readerOptions;
  if (subBlockCacheOptions.cacheType == CacheType::Standard) {
    this->spSubBlockCache = libCZI::CreateSubBlockCache();
  } else if (subBlockCacheOptions.cacheType != CacheType::None) {
    stringstream string_stream;
    string_stream << "The specified type of cache is not supported: "
                  << static_cast<underlying_type_t<CacheType>>(
                         subBlockCacheOptions.cacheType)
                  << '.';
    throw std::invalid_argument(string_stream.str());
  }
}

void CZIreadAPI::EnsureOpen() const {
  if (this->isClosed) {
    throw std::logic_error("The CZI reader is closed.");
  }
}

void CZIreadAPI::close() {
  if (!this->isClosed) {
    this->spReader->Close();
    this->isClosed = true;
  }
}

libCZI::SubBlockInfo CZIreadAPI::GetSubBlockInfo(int index) const {
  this->EnsureOpen();
  libCZI::SubBlockInfo info;
  if (index < 0 || !this->spReader->TryGetSubBlockInfo(index, &info)) {
    throw std::out_of_range("No subblock exists at the supplied directory index.");
  }
  return info;
}

std::vector<std::pair<int, libCZI::SubBlockInfo>>
CZIreadAPI::GetSubBlockDirectory() const {
  this->EnsureOpen();
  std::vector<std::pair<int, libCZI::SubBlockInfo>> directory;
  this->spReader->EnumerateSubBlocks(
      [&directory](int index, const libCZI::SubBlockInfo &info) {
        directory.emplace_back(index, info);
        return true;
      });
  return directory;
}

std::unique_ptr<PImage> CZIreadAPI::ReadSubBlock(int index) {
  const auto info = this->GetSubBlockInfo(index);
  if (info.physicalSize.w <= 0 || info.physicalSize.h <= 0) {
    throw std::invalid_argument("Stored subblock dimensions must be positive.");
  }
  switch (info.pixelType) {
  case libCZI::PixelType::Gray8:
  case libCZI::PixelType::Gray16:
  case libCZI::PixelType::Gray32Float:
  case libCZI::PixelType::Bgr24:
  case libCZI::PixelType::Bgr48:
  case libCZI::PixelType::Bgr96Float:
    break;
  default:
    throw std::invalid_argument("Unsupported stored subblock pixel layout.");
  }
  if (info.GetCompressionMode() == libCZI::CompressionMode::Invalid) {
    throw std::invalid_argument("Unsupported stored subblock compression mode.");
  }
  const auto width = static_cast<size_t>(info.physicalSize.w);
  const auto height = static_cast<size_t>(info.physicalSize.h);
  const auto bytesPerPixel = libCZI::Utils::GetBytesPerPixel(info.pixelType);
  if (width > (std::numeric_limits<uint32_t>::max() - 3u) / bytesPerPixel) {
    throw std::overflow_error("Decoded subblock stride exceeds the native range.");
  }
  const auto stride = ((width * bytesPerPixel + 3) / 4) * 4;
  if (height > static_cast<size_t>(std::numeric_limits<std::ptrdiff_t>::max()) / stride) {
    throw std::overflow_error("Decoded subblock size exceeds the buffer range.");
  }
  const auto subblock = this->spReader->ReadSubBlock(index);
  if (!subblock) {
    throw std::out_of_range("No subblock exists at the supplied directory index.");
  }
  try {
    return std::make_unique<PImage>(subblock->CreateBitmap());
  } catch (const std::overflow_error &) {
    throw;
  } catch (const std::runtime_error &error) {
    throw SubBlockDecodeError(error.what());
  }
}

std::string CZIreadAPI::ReadSubBlockMetadata(int index) {
  this->GetSubBlockInfo(index);
  const auto subblock = this->spReader->ReadSubBlock(index);
  size_t size = 0;
  const auto data = subblock->GetRawData(libCZI::ISubBlock::Metadata, &size);
  if (size > static_cast<size_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
    throw std::overflow_error("Subblock metadata exceeds the buffer range.");
  }
  return size ? std::string(static_cast<const char *>(data.get()), size) : std::string();
}

std::optional<StoredMaskData> CZIreadAPI::ReadSubBlockMask(int index) {
  const auto info = this->GetSubBlockInfo(index);
  const auto subblock = this->spReader->ReadSubBlock(index);
  size_t size = 0;
  const auto data = subblock->GetRawData(libCZI::ISubBlock::Attachment, &size);
  if (!size) {
    return std::nullopt;
  }
  const auto metadata = libCZI::CreateSubBlockMetadataFromSubBlock(subblock.get());
  if (!metadata->IsXmlValid()) {
    throw std::invalid_argument("Invalid subblock metadata for stored mask.");
  }
  const auto accessor = libCZI::CreateSubBlockAttachmentAccessor(subblock, metadata);
  if (!accessor->HasChunkContainer()) {
    return std::nullopt;
  }
  const auto bytes = static_cast<const unsigned char *>(data.get());
  const unsigned char maskGuid[] = {0x67, 0xea, 0xe3, 0xcb, 0xfc, 0x5b, 0x2b, 0x49,
                                  0xa1, 0x6a, 0xec, 0xe3, 0x78, 0x03, 0x14, 0x48};
  const auto read32 = [](const unsigned char *value) -> uint32_t {
    return uint32_t(value[0]) | (uint32_t(value[1]) << 8) |
           (uint32_t(value[2]) << 16) | (uint32_t(value[3]) << 24);
  };
  std::optional<StoredMaskData> result;
  for (size_t offset = 0; offset < size;) {
    if (size - offset < 20) {
      throw std::invalid_argument("Corrupt stored mask chunk header.");
    }
    const auto length = read32(bytes + offset + 16);
    if (length > size - offset - 20) {
      throw std::invalid_argument("Corrupt stored mask chunk length.");
    }
    if (std::memcmp(bytes + offset, maskGuid, 16) == 0) {
      if (result || length < 16) {
        throw std::invalid_argument("Corrupt or duplicate stored mask chunk.");
      }
      const auto payload = bytes + offset + 20;
      const auto width = read32(payload);
      const auto height = read32(payload + 4);
      const auto representation = read32(payload + 8);
      const auto stride = read32(payload + 12);
      const auto rowBytes = (uint64_t(width) + 7) / 8;
      if (!width || !height || width != static_cast<uint32_t>(info.physicalSize.w) ||
          height != static_cast<uint32_t>(info.physicalSize.h) || representation != 0 ||
          stride < rowBytes || uint64_t(height - 1) * stride + rowBytes > length - 16) {
        throw std::invalid_argument("Corrupt or unsupported stored mask geometry/representation.");
      }
      if (rowBytes * height > static_cast<uint64_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
        throw std::overflow_error("Stored mask exceeds the buffer range.");
      }
      StoredMaskData mask{info.physicalSize.w, info.physicalSize.h,
                          std::string(static_cast<size_t>(rowBytes * height), '\0')};
      for (uint32_t row = 0; row < height; ++row) {
        std::memcpy(mask.bits.data() + row * rowBytes, payload + 16 + uint64_t(row) * stride,
                    static_cast<size_t>(rowBytes));
      }
      result = std::move(mask);
    }
    offset += 20 + static_cast<size_t>(length);
  }
  return result;
}

std::unique_ptr<PImage> CZIreadAPI::ReadStoredLevel(
    const std::vector<int> &indices, libCZI::IntRect roi, int factor) {
  this->EnsureOpen();
  if (indices.empty() || factor <= 0 || roi.w <= 0 || roi.h <= 0 ||
      roi.w / factor <= 0 || roi.h / factor <= 0) {
    throw std::invalid_argument("Invalid stored level members, ROI or integer factor.");
  }
  std::vector<std::pair<int, libCZI::SubBlockInfo>> members;
  for (const auto index : indices) {
    members.emplace_back(index, this->GetSubBlockInfo(index));
  }
  const auto pixelType = members.front().second.pixelType;
  switch (pixelType) {
  case libCZI::PixelType::Gray8:
  case libCZI::PixelType::Gray16:
  case libCZI::PixelType::Gray32Float:
  case libCZI::PixelType::Bgr24:
  case libCZI::PixelType::Bgr48:
  case libCZI::PixelType::Bgr96Float:
    break;
  default:
    throw std::invalid_argument("Unsupported stored level pixel type.");
  }
  for (const auto &member : members) {
    const auto &info = member.second;
    if (info.pixelType != pixelType) {
      throw std::invalid_argument("Mixed stored level pixel types.");
    }
    if (info.logicalRect.w <= 0 || info.logicalRect.h <= 0 ||
        !info.physicalSize.w || !info.physicalSize.h ||
        int64_t(info.physicalSize.w) * factor != info.logicalRect.w ||
        int64_t(info.physicalSize.h) * factor != info.logicalRect.h) {
      throw std::invalid_argument("Unsupported stored level member geometry.");
    }
  }
  const auto width = static_cast<uint32_t>(roi.w / factor);
  const auto height = static_cast<uint32_t>(roi.h / factor);
  const auto bytesPerPixel = libCZI::Utils::GetBytesPerPixel(pixelType);
  if (width > (std::numeric_limits<uint32_t>::max() - 3u) / bytesPerPixel) {
    throw std::overflow_error("Stored level output stride exceeds the native range.");
  }
  const auto stride = (uint64_t(width) * bytesPerPixel + 3) / 4 * 4;
  if (height > static_cast<size_t>(std::numeric_limits<std::ptrdiff_t>::max()) / stride) {
    throw std::overflow_error("Stored level output exceeds the buffer range.");
  }
  auto output = std::make_unique<PImage>(
      libCZI::GetDefaultSiteObject(libCZI::SiteObjectType::Default)->CreateBitmap(pixelType, width, height));
  std::memset(output->get_data(), 0, output->get_stride() * height);
  std::stable_sort(members.begin(), members.end(), [](const auto &left, const auto &right) {
    const auto leftM = libCZI::Utils::IsValidMindex(left.second.mIndex)
        ? left.second.mIndex : std::numeric_limits<int>::min();
    const auto rightM = libCZI::Utils::IsValidMindex(right.second.mIndex)
        ? right.second.mIndex : std::numeric_limits<int>::min();
    return leftM < rightM;
  });
  for (const auto &member : members) {
    const auto &rect = member.second.logicalRect;
    if (int64_t(rect.x) + rect.w <= roi.x || int64_t(rect.y) + rect.h <= roi.y ||
        int64_t(roi.x) + roi.w <= rect.x || int64_t(roi.y) + roi.h <= rect.y) {
      continue;
    }
    const auto offsetX = (int64_t(rect.x) - roi.x) / factor;
    const auto offsetY = (int64_t(rect.y) - roi.y) / factor;
    const auto sourceX = std::max<int64_t>(0, -offsetX);
    const auto sourceY = std::max<int64_t>(0, -offsetY);
    const auto targetX = std::max<int64_t>(0, offsetX);
    const auto targetY = std::max<int64_t>(0, offsetY);
    const auto copyWidth = std::min<int64_t>(member.second.physicalSize.w - sourceX, width - targetX);
    const auto copyHeight = std::min<int64_t>(member.second.physicalSize.h - sourceY, height - targetY);
    if (copyWidth <= 0 || copyHeight <= 0) {
      continue;
    }
    const auto pixels = this->ReadSubBlock(member.first);
    const auto mask = this->readerOptions.enableMaskAwareness
        ? this->ReadSubBlockMask(member.first) : std::optional<StoredMaskData>();
    for (int64_t row = 0; row < copyHeight; ++row) {
      const auto source = static_cast<const unsigned char *>(pixels->get_data()) +
          (sourceY + row) * pixels->get_stride() + sourceX * bytesPerPixel;
      const auto target = static_cast<unsigned char *>(output->get_data()) +
          (targetY + row) * output->get_stride() + targetX * bytesPerPixel;
      if (!mask) {
        std::memcpy(target, source, static_cast<size_t>(copyWidth) * bytesPerPixel);
      } else {
        const auto maskStride = (uint64_t(mask->width) + 7) / 8;
        for (int64_t column = 0; column < copyWidth; ++column) {
          const auto maskX = sourceX + column;
          const auto value = static_cast<unsigned char>(mask->bits[(sourceY + row) * maskStride + maskX / 8]);
          if (value & (0x80 >> (maskX % 8))) {
            std::memcpy(target + column * bytesPerPixel, source + column * bytesPerPixel, bytesPerPixel);
          }
        }
      }
    }
  }
  return output;
}

libCZI::AttachmentInfo CZIreadAPI::GetAttachmentInfo(int index) const {
  this->EnsureOpen();
  libCZI::AttachmentInfo info;
  if (index < 0 || !this->spReader->TryGetAttachmentInfo(index, &info)) {
    throw std::out_of_range("No attachment exists at the supplied directory index.");
  }
  return info;
}

std::vector<std::pair<int, libCZI::AttachmentInfo>> CZIreadAPI::GetAttachmentDirectory() {
  this->EnsureOpen();
  std::vector<std::pair<int, libCZI::AttachmentInfo>> directory;
  this->spReader->EnumerateAttachments([&](int index, const libCZI::AttachmentInfo &info) {
    directory.emplace_back(index, info);
    return true;
  });
  return directory;
}

std::string CZIreadAPI::ReadAttachment(int index) {
  this->GetAttachmentInfo(index);
  const auto attachment = this->spReader->ReadAttachment(index);
  size_t size = 0;
  const auto data = attachment->GetRawData(&size);
  if (size > static_cast<size_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
    throw std::overflow_error("Attachment payload exceeds the buffer range.");
  }
  return size ? std::string(static_cast<const char *>(data.get()), size) : std::string();
}

std::unique_ptr<PImage> CZIreadAPI::ReadAttachmentImage(int index) {
  const auto info = this->GetAttachmentInfo(index);
  if (std::string(info.contentFileType) != "CZI") {
    throw std::invalid_argument("Unsupported attachment image format; expected embedded CZI.");
  }
  const auto attachment = this->spReader->ReadAttachment(index);
  size_t size = 0;
  attachment->GetRawData(&size);
  if (size > static_cast<size_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
    throw std::overflow_error("Attachment image payload exceeds the buffer range.");
  }
  CZIreadAPI embedded(libCZI::CreateStreamFromMemory(attachment.get()));
  const auto directory = embedded.GetSubBlockDirectory();
  std::vector<int> indices;
  std::map<libCZI::DimensionIndex, int> selectedCoordinates;
  int64_t left = std::numeric_limits<int64_t>::max();
  int64_t top = left;
  int64_t right = std::numeric_limits<int64_t>::min();
  int64_t bottom = right;
  for (const auto &entry : directory) {
    const auto &block = entry.second;
    if (block.logicalRect.w <= 0 || block.logicalRect.h <= 0 ||
        uint64_t(block.logicalRect.w) != block.physicalSize.w ||
        uint64_t(block.logicalRect.h) != block.physicalSize.h) {
      continue;
    }
    std::map<libCZI::DimensionIndex, int> coordinates;
    block.coordinate.EnumValidDimensions([&](libCZI::DimensionIndex dimension, int value) {
      coordinates[dimension] = value;
      return true;
    });
    if (!indices.empty() && coordinates != selectedCoordinates) {
      throw std::invalid_argument("Embedded CZI attachment contains multiple image planes.");
    }
    selectedCoordinates = std::move(coordinates);
    indices.push_back(entry.first);
    left = std::min<int64_t>(left, block.logicalRect.x);
    top = std::min<int64_t>(top, block.logicalRect.y);
    right = std::max<int64_t>(right, int64_t(block.logicalRect.x) + block.logicalRect.w);
    bottom = std::max<int64_t>(bottom, int64_t(block.logicalRect.y) + block.logicalRect.h);
  }
  if (indices.empty()) {
    throw std::invalid_argument("Embedded CZI attachment has no supported full-resolution image plane.");
  }
  if (right > std::numeric_limits<int>::max() || bottom > std::numeric_limits<int>::max() ||
      right - left > std::numeric_limits<int>::max() || bottom - top > std::numeric_limits<int>::max()) {
    throw std::overflow_error("Embedded CZI image bounds exceed the native range.");
  }
  const libCZI::IntRect roi{static_cast<int>(left), static_cast<int>(top),
                            static_cast<int>(right - left), static_cast<int>(bottom - top)};
  auto pixels = embedded.ReadStoredLevel(indices, roi, 1);
  embedded.close();
  return pixels;
}

std::string CZIreadAPI::GetXmlMetadata() {

  const auto mds = this->spReader->ReadMetadataSegment();
  const auto md = mds->CreateMetaFromMetadataSegment();

  return md->GetXml();
}

size_t CZIreadAPI::GetDimensionSize(libCZI::DimensionIndex DimIndex) {

  const auto stats = this->spReader->GetStatistics();
  int size;

  // Should replace nullptr with reference to handle CZI with index not starting
  // at 0, legal ?
  const bool dim_exist =
      stats.dimBounds.TryGetInterval(DimIndex, nullptr, &size);

  if (dim_exist) {
    return size;
  }

  return 0;
}

libCZI::PixelType CZIreadAPI::GetChannelPixelType(int chanelIdx) {

  libCZI::SubBlockInfo sbBlkInfo;
  const bool b = this->spReader->TryGetSubBlockInfoOfArbitrarySubBlockInChannel(
      chanelIdx, sbBlkInfo);
  if (!b) {
    // TODO more precise error handling
    return libCZI::PixelType::Invalid;
  }

  return sbBlkInfo.pixelType;
}

libCZI::SubBlockStatistics CZIreadAPI::GetSubBlockStats() {

  return this->spReader->GetStatistics();
}

std::unique_ptr<PImage> CZIreadAPI::GetSingleChannelScalingTileAccessorData(
    libCZI::PixelType pixeltype, libCZI::IntRect roi,
    libCZI::RgbFloatColor bgColor, float zoom,
    const std::string &coordinateString, const std::wstring &SceneIndexes) {
  libCZI::CDimCoordinate planeCoordinate;
  try {
    planeCoordinate = CDimCoordinate::Parse(coordinateString.c_str());
  } catch (libCZI::LibCZIStringParseException &parseExcp) {
    // TODO Error handling
  }

  libCZI::ISingleChannelScalingTileAccessor::Options scstaOptions;
  scstaOptions.Clear();
  // set the flag "visibility check optimization" as configured by the user
  scstaOptions.useVisibilityCheckOptimization =
      this->readerOptions.enableVisibilityCheckOptimization;
  // set the flag "mask awareness" as configured by the user
  scstaOptions.maskAware = this->readerOptions.enableMaskAwareness;
  scstaOptions.backGroundColor = bgColor;
  if (this->spSubBlockCache) {
    scstaOptions.subBlockCache = this->spSubBlockCache;
    scstaOptions.onlyUseSubBlockCacheForCompressedData =
        this->subBlockCacheOptions.cacheOnlyCompressed;
  }

  if (!SceneIndexes.empty()) {
    scstaOptions.sceneFilter = libCZI::Utils::IndexSetFromString(SceneIndexes);
  }

  std::shared_ptr<libCZI::IBitmapData> Data = this->spAccessor->Get(
      pixeltype, roi, &planeCoordinate, zoom, &scstaOptions);

  if (this->spSubBlockCache) {
    this->spSubBlockCache->Prune(this->subBlockCacheOptions.pruneOptions);
  }

  std::unique_ptr<PImage> ptr_Bitmap(new PImage(Data));
  return ptr_Bitmap;
}

/// Returns an info struct on the subblock cache
SubBlockCacheInfo CZIreadAPI::GetCacheInfo() {
  auto cacheInfo = SubBlockCacheInfo();
  if (this->spSubBlockCache) {
    // Note: We need to use one call (to retrieve the values) in order to ensure
    // that they are consistent.
    const auto cacheStatistics = this->spSubBlockCache->GetStatistics(
        libCZI::ISubBlockCacheStatistics::kElementsCount |
        libCZI::ISubBlockCacheStatistics::kMemoryUsage);
    cacheInfo.elementsCount = cacheStatistics.elementsCount;
    cacheInfo.memoryUsage = cacheStatistics.memoryUsage;
  }

  return cacheInfo;
}

void CZIreadAPI::EnumerateSubBlocks(
    const std::function<bool(int index, const libCZI::SubBlockInfo &info)>
        &func) {
  this->spReader->EnumerateSubBlocks(func);
}

void CZIreadAPI::EnumerateSubset(
    const libCZI::IDimCoordinate *planeCoordinate, const libCZI::IntRect *roi,
    bool onlyLayer0,
    const std::function<bool(int index, const libCZI::SubBlockInfo &info)>
        &func) {
  this->spReader->EnumSubset(planeCoordinate, roi, onlyLayer0, func);
}
