#include "CZIreadAPI.h"
#include "StaticContext.h"
#include "libCZI_Site.h"

#include <algorithm>
#include <array>
#include <codecvt>
#include <cstddef>
#include <cstring>
#include <limits>
#include <locale>
#include <map>
#include <numeric>
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

void CZIreadAPI::VisitSubBlocks(
    const std::map<std::string, int> &plane, std::optional<int> scene,
    std::optional<int> mIndex, std::optional<int> level, bool classify,
    const std::function<void(int, const libCZI::SubBlockInfo &, std::optional<int>)> &visitor) const {
  this->EnsureOpen();
  std::map<libCZI::DimensionIndex, int> coordinates;
  for (const auto &entry : plane) {
    if (entry.first.size() != 1 || std::string("TCZRIHVB").find(entry.first) == std::string::npos) {
      throw std::invalid_argument("Invalid subblock plane dimension.");
    }
    const auto parsed = libCZI::CDimCoordinate::Parse((entry.first + std::to_string(entry.second)).c_str());
    parsed.EnumValidDimensions([&](libCZI::DimensionIndex dimension, int value) {
      coordinates[dimension] = value;
      return true;
    });
  }
  if (scene) {
    coordinates[libCZI::DimensionIndex::S] = *scene;
  }
  std::map<std::array<int, 4>, int> levels;
  this->spReader->EnumerateSubBlocks([&](int index, const libCZI::SubBlockInfo &info) {
    std::optional<int> token;
    if ((classify || level) && info.logicalRect.w > 0 && info.logicalRect.h > 0 &&
        info.physicalSize.w > 0 && info.physicalSize.h > 0) {
      const auto horizontal = std::gcd(info.logicalRect.w, static_cast<int>(info.physicalSize.w));
      const auto vertical = std::gcd(info.logicalRect.h, static_cast<int>(info.physicalSize.h));
      const std::array<int, 4> key{info.logicalRect.h / vertical,
          static_cast<int>(info.physicalSize.h) / vertical,
          info.logicalRect.w / horizontal, static_cast<int>(info.physicalSize.w) / horizontal};
      token = levels.emplace(key, static_cast<int>(levels.size())).first->second;
    }
    for (const auto &coordinate : coordinates) {
      int value;
      if (!info.coordinate.TryGetPosition(coordinate.first, &value) || value != coordinate.second) {
        return true;
      }
    }
    if ((mIndex && (!libCZI::Utils::IsValidMindex(info.mIndex) || info.mIndex != *mIndex)) ||
        (level && token != level)) {
      return true;
    }
    visitor(index, info, token);
    return true;
  });
}

std::vector<std::tuple<int, libCZI::SubBlockInfo, std::optional<int>>>
CZIreadAPI::QuerySubBlocks(const std::map<std::string, int> &plane, std::optional<int> scene,
                          std::optional<int> mIndex, std::optional<int> level) const {
  std::vector<std::tuple<int, libCZI::SubBlockInfo, std::optional<int>>> result;
  this->VisitSubBlocks(plane, scene, mIndex, level, true,
      [&](int index, const libCZI::SubBlockInfo &info, std::optional<int> token) {
        result.emplace_back(index, info, token);
      });
  return result;
}

uint64_t CZIreadAPI::CountSubBlocks(const std::map<std::string, int> &plane, std::optional<int> scene,
                                  std::optional<int> mIndex, std::optional<int> level) const {
  uint64_t count = 0;
  this->VisitSubBlocks(plane, scene, mIndex, level, false,
      [&](int, const libCZI::SubBlockInfo &, std::optional<int>) { ++count; });
  return count;
}

std::map<std::optional<int>, uint64_t> CZIreadAPI::CountSubBlocksByScene(
    const std::map<std::string, int> &plane, std::optional<int> scene,
    std::optional<int> mIndex, std::optional<int> level) const {
  std::map<std::optional<int>, uint64_t> counts;
  this->VisitSubBlocks(plane, scene, mIndex, level, false,
      [&](int, const libCZI::SubBlockInfo &info, std::optional<int>) {
        int value;
        const auto key = info.coordinate.TryGetPosition(libCZI::DimensionIndex::S, &value)
            ? std::optional<int>(value) : std::nullopt;
        ++counts[key];
      });
  return counts;
}

std::unique_ptr<PImage> CZIreadAPI::ReadSubBlock(int index) {
  this->EnsureOpen();
  return std::make_unique<PImage>(DecodeSubBlock(this->spReader, index));
}

std::shared_ptr<libCZI::IBitmapData> CZIreadAPI::DecodeSubBlock(
    const std::shared_ptr<libCZI::ISubBlockRepository> &repository, int index) {
  libCZI::SubBlockInfo info;
  if (index < 0 || !repository->TryGetSubBlockInfo(index, &info)) {
    throw std::out_of_range("No subblock exists at the supplied directory index.");
  }
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
  const auto subblock = repository->ReadSubBlock(index);
  if (!subblock) {
    throw std::out_of_range("No subblock exists at the supplied directory index.");
  }
  try {
    libCZI::CreateBitmapOptions options;
    options.handle_uncompressed_data_size_mismatch = false;
    options.handle_jpgxr_bitmap_mismatch = false;
    options.handle_zstd_data_size_mismatch = false;
    options.handle_chunked_compression_data_size_mismatch = false;
    return subblock->CreateBitmap(&options);
  } catch (const std::overflow_error &) {
    throw;
  } catch (const std::logic_error &error) {
    throw SubBlockDecodeError("Stored subblock compression mode " +
        std::to_string(info.compressionModeRaw) + ": " + error.what());
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
  this->GetSubBlockInfo(index);
  const auto subblock = this->spReader->ReadSubBlock(index);
  const auto bitmap = ReadMaskBitmap(subblock);
  if (!bitmap) {
    return std::nullopt;
  }
  const auto width = bitmap->GetWidth();
  const auto height = bitmap->GetHeight();
  const auto rowBytes = (uint64_t(width) + 7) / 8;
  if (rowBytes * height > static_cast<uint64_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
    throw std::overflow_error("Stored mask exceeds the buffer range.");
  }
  const libCZI::ScopedBitonalBitmapLockerP locked(bitmap.get());
  StoredMaskData result{width, height,
      std::string(static_cast<size_t>(rowBytes * height), '\0')};
  for (uint32_t row = 0; row < height; ++row) {
    std::memcpy(result.bits.data() + row * rowBytes,
        static_cast<const unsigned char *>(locked.ptrData) + uint64_t(row) * locked.stride,
        static_cast<size_t>(rowBytes));
  }
  return result;
}

std::shared_ptr<libCZI::IBitonalBitmapData> CZIreadAPI::ReadMaskBitmap(
    const std::shared_ptr<libCZI::ISubBlock> &subblock) {
  const auto info = subblock->GetSubBlockInfo();
  size_t size = 0;
  subblock->GetRawData(libCZI::ISubBlock::Attachment, &size);
  if (!size) {
    return {};
  }
  const auto metadata = libCZI::CreateSubBlockMetadataFromSubBlock(subblock.get());
  if (!metadata->IsXmlValid()) {
    throw std::invalid_argument("Invalid subblock metadata for stored mask.");
  }
  const auto accessor = libCZI::CreateSubBlockAttachmentAccessor(subblock, metadata);
  if (!accessor->HasChunkContainer()) {
    return {};
  }
  try {
    const libCZI::GUID maskGuid{0xcbe3ea67, 0x5bfc, 0x492b,
        {0xa1, 0x6a, 0xec, 0xe3, 0x78, 0x03, 0x14, 0x48}};
    int maskCount = 0;
    accessor->EnumerateChunksInChunkContainer(
        [&](int, const libCZI::ISubBlockAttachmentAccessor::ChunkInfo &chunk) {
          if (chunk.guid == maskGuid) {
            if (++maskCount > 1 || chunk.size < 16) {
              throw std::invalid_argument("Corrupt or duplicate stored mask chunk.");
            }
          }
          return true;
        });
    if (!maskCount) {
      return {};
    }
    const auto mask = accessor->GetValidPixelMaskAsUncompressedBitonalBitmap();
    const auto bitmap = accessor->CreateBitonalBitmapFromMaskInfo();
    if (mask.width != info.physicalSize.w || mask.height != info.physicalSize.h) {
      throw std::invalid_argument("Stored mask dimensions do not match the subblock.");
    }
    return bitmap;
  } catch (const libCZI::LibCZIException &error) {
    throw std::invalid_argument(std::string("Invalid stored mask: ") + error.what());
  }
}

std::unique_ptr<PImage> CZIreadAPI::ReadStoredLevel(
    const std::vector<int> &indices, libCZI::IntRect roi, int factor) {
  this->EnsureOpen();
  return ComposeStoredLevel(this->spReader, indices, roi, factor,
                            this->readerOptions.enableMaskAwareness);
}

std::unique_ptr<PImage> CZIreadAPI::ComposeStoredLevel(
    const std::shared_ptr<libCZI::ISubBlockRepository> &repository,
    const std::vector<int> &indices, libCZI::IntRect roi, int factor, bool maskAware) {
  if (indices.empty() || factor <= 0 || roi.w <= 0 || roi.h <= 0 ||
      roi.w / factor <= 0 || roi.h / factor <= 0) {
    throw std::invalid_argument("Invalid stored level members, ROI or integer factor.");
  }
  std::vector<std::pair<int, libCZI::SubBlockInfo>> members;
  for (const auto index : indices) {
    libCZI::SubBlockInfo info;
    if (index < 0 || !repository->TryGetSubBlockInfo(index, &info)) {
      throw std::out_of_range("No subblock exists at the supplied directory index.");
    }
    members.emplace_back(index, info);
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
    if (roi.w % factor || roi.h % factor ||
        (int64_t(info.logicalRect.x) - roi.x) % factor ||
        (int64_t(info.logicalRect.y) - roi.y) % factor) {
      throw std::invalid_argument("Stored level ROI and tiles must align to the sampling grid.");
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
  const auto bitmap = libCZI::GetDefaultSiteObject(libCZI::SiteObjectType::Default)
      ->CreateBitmap(pixelType, width, height);
  auto output = std::make_unique<PImage>(bitmap);
  std::memset(output->get_data(), 0, output->get_stride() * height);
  members.erase(std::remove_if(members.begin(), members.end(), [&](const auto &member) {
    const auto &rect = member.second.logicalRect;
    return int64_t(rect.x) + rect.w <= roi.x || int64_t(rect.y) + rect.h <= roi.y ||
        int64_t(roi.x) + roi.w <= rect.x || int64_t(roi.y) + roi.h <= rect.y;
  }), members.end());
  std::stable_sort(members.begin(), members.end(), [](const auto &left, const auto &right) {
    const auto leftM = libCZI::Utils::IsValidMindex(left.second.mIndex)
        ? left.second.mIndex : std::numeric_limits<int>::min();
    const auto rightM = libCZI::Utils::IsValidMindex(right.second.mIndex)
        ? right.second.mIndex : std::numeric_limits<int>::min();
    return leftM < rightM || (leftM == rightM && left.first < right.first);
  });
  libCZI::Compositors::ComposeSingleChannelTilesMaskAware(
      [&](int position, std::shared_ptr<libCZI::IBitmapData> &pixels,
          std::shared_ptr<libCZI::IBitonalBitmapData> &maskBitmap, int &offsetX, int &offsetY) {
    if (static_cast<size_t>(position) >= members.size()) {
      return false;
    }
    const auto &member = members[position];
    const auto &rect = member.second.logicalRect;
    offsetX = static_cast<int>((int64_t(rect.x) - roi.x) / factor);
    offsetY = static_cast<int>((int64_t(rect.y) - roi.y) / factor);
    pixels = DecodeSubBlock(repository, member.first);
    if (maskAware) {
      maskBitmap = ReadMaskBitmap(repository->ReadSubBlock(member.first));
    }
    return true;
  }, bitmap.get(), 0, 0, nullptr);
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

std::vector<libCZI::AttachmentInfo> CZIreadAPI::GetAttachmentDirectory() {
  this->EnsureOpen();
  std::vector<libCZI::AttachmentInfo> directory;
  this->spReader->EnumerateAttachments([&](int, const libCZI::AttachmentInfo &info) {
    directory.push_back(info);
    return true;
  });
  return directory;
}

std::vector<uint8_t> CZIreadAPI::ReadAttachment(int index) {
  this->GetAttachmentInfo(index);
  const auto attachment = this->spReader->ReadAttachment(index);
  size_t size = 0;
  const auto data = attachment->GetRawData(&size);
  if (size > static_cast<size_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
    throw std::overflow_error("Attachment payload exceeds the buffer range.");
  }
  const auto bytes = static_cast<const uint8_t *>(data.get());
  return size ? std::vector<uint8_t>(bytes, bytes + size) : std::vector<uint8_t>();
}

std::unique_ptr<PImage> CZIreadAPI::ReadEmbeddedCziImage(int index) {
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
  const auto embedded = libCZI::CreateCZIReader();
  embedded->Open(libCZI::CreateStreamFromMemory(attachment.get()));
  std::vector<int> indices;
  std::map<libCZI::DimensionIndex, int> selectedCoordinates;
  int64_t left = std::numeric_limits<int64_t>::max();
  int64_t top = left;
  int64_t right = std::numeric_limits<int64_t>::min();
  int64_t bottom = right;
  embedded->EnumerateSubBlocks([&](int index, const libCZI::SubBlockInfo &block) {
    if (block.logicalRect.w <= 0 || block.logicalRect.h <= 0 ||
        uint64_t(block.logicalRect.w) != block.physicalSize.w ||
        uint64_t(block.logicalRect.h) != block.physicalSize.h) {
      return true;
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
    indices.push_back(index);
    left = std::min<int64_t>(left, block.logicalRect.x);
    top = std::min<int64_t>(top, block.logicalRect.y);
    right = std::max<int64_t>(right, int64_t(block.logicalRect.x) + block.logicalRect.w);
    bottom = std::max<int64_t>(bottom, int64_t(block.logicalRect.y) + block.logicalRect.h);
    return true;
  });
  if (indices.empty()) {
    throw std::invalid_argument("Embedded CZI attachment has no supported full-resolution image plane.");
  }
  if (right > std::numeric_limits<int>::max() || bottom > std::numeric_limits<int>::max() ||
      right - left > std::numeric_limits<int>::max() || bottom - top > std::numeric_limits<int>::max()) {
    throw std::overflow_error("Embedded CZI image bounds exceed the native range.");
  }
  const libCZI::IntRect roi{static_cast<int>(left), static_cast<int>(top),
                            static_cast<int>(right - left), static_cast<int>(bottom - top)};
  auto pixels = ComposeStoredLevel(embedded, indices, roi, 1,
                                    this->readerOptions.enableMaskAwareness);
  embedded->Close();
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
