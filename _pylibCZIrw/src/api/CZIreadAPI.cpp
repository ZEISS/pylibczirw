#include "CZIreadAPI.h"
#include "StaticContext.h"

#include <codecvt>
#include <locale>
#include <sstream>

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
                       const SubBlockCacheOptions &subBlockCacheOptions) {
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

  const auto reader = libCZI::CreateCZIReader();
  reader->Open(stream);
  this->spAccessor = reader->CreateSingleChannelScalingTileAccessor();
  this->spReader = reader;
  this->subBlockCacheOptions = subBlockCacheOptions;
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
  scstaOptions.useVisibilityCheckOptimization =
      true; // enable the "visibility check optimization"
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

bool CZIreadAPI::NeedsPyramid(uint32_t max_extent_of_image) {
  ThresholdParameters parameters{ max_extent_of_image };

  const auto statistics = this->spReader->GetStatistics();

  // First, check the overall bounding box
  if (!CheckOverallBoundingBoxForNecessityOfPyramid(statistics, parameters)) {
    return false;
  }

    // Check per-scene bounding boxes
  const auto per_scene_result = CheckPerSceneBoundingBoxesForNecessityOfPyramid(statistics, parameters);
  if (per_scene_result.value_or(true) == false) {
    return false;
  }

  // Check if pyramid is already present
  const auto pyramid_statistics = this->spReader->GetPyramidStatistics();

  if (CheckIfPyramidIsPresent(statistics, pyramid_statistics, parameters)) {
    return false;
  }

  return true;
}

bool CZIreadAPI::CheckOverallBoundingBoxForNecessityOfPyramid(const libCZI::SubBlockStatistics& statistics, const ThresholdParameters& threshold_parameters) {
  if (IsRectangleAboveThreshold(statistics.boundingBoxLayer0Only, threshold_parameters)) {
    return true;
  }
  return false;
}

std::optional<bool> CZIreadAPI::CheckPerSceneBoundingBoxesForNecessityOfPyramid(const libCZI::SubBlockStatistics& statistics, const ThresholdParameters& threshold_parameters) {
  if (statistics.sceneBoundingBoxes.empty()) {
    return std::nullopt;
  }

  for (const auto& sceneBoundingBox : statistics.sceneBoundingBoxes) {
    if (IsRectangleAboveThreshold(sceneBoundingBox.second.boundingBoxLayer0, threshold_parameters)) {
      return true;
    }
  }

  return false;
}

bool CZIreadAPI::IsRectangleAboveThreshold(const libCZI::IntRect& rectangle, const ThresholdParameters& threshold_parameters) {
  if (static_cast<uint32_t>(rectangle.w) > threshold_parameters.max_extent_of_image || static_cast<uint32_t>(rectangle.h) > threshold_parameters.max_extent_of_image) {
    return true;
  }
  return false;
}

bool CZIreadAPI::CheckIfPyramidIsPresent(const libCZI::SubBlockStatistics& statistics, const libCZI::PyramidStatistics& pyramid_statistics, const ThresholdParameters& threshold_parameters) {
  if (statistics.sceneBoundingBoxes.empty()) {
    // No S-index used; check overall bounding box
    if (CheckOverallBoundingBoxForNecessityOfPyramid(statistics, threshold_parameters)) {
      const auto& pyramid_layer_statistics_iterator = pyramid_statistics.scenePyramidStatistics.find(std::numeric_limits<int>::max());
      if (pyramid_layer_statistics_iterator == pyramid_statistics.scenePyramidStatistics.end()) {
        // Unexpected; there should always be a pyramid-layer-0
          return false;
        }

        if (!DoesContainPyramidLayer(pyramid_layer_statistics_iterator->second)) {
          return false;
        }
      }
  } else {
    // Document contains scenes; check per-scene bounding boxes
    if (CheckPerSceneBoundingBoxesForNecessityOfPyramid(statistics, threshold_parameters)) {
      for (const auto& sceneBoundingBox : statistics.sceneBoundingBoxes) {
        if (IsRectangleAboveThreshold(sceneBoundingBox.second.boundingBoxLayer0, threshold_parameters)) {
          const auto& pyramid_layer_statistics_iterator = pyramid_statistics.scenePyramidStatistics.find(sceneBoundingBox.first);
          if (pyramid_layer_statistics_iterator == pyramid_statistics.scenePyramidStatistics.end()) {
            // Unexpected; there should always be a pyramid-layer-0
            return false;
          }

          if (!DoesContainPyramidLayer(pyramid_layer_statistics_iterator->second)) {
            return false;
          }
        }
      }
    }
  }

  return true;
}

bool CZIreadAPI::DoesContainPyramidLayer(const std::vector<libCZI::PyramidStatistics::PyramidLayerStatistics>& pyramid_layer_statistics) {
  for (const auto& layer_statistics : pyramid_layer_statistics) {
    if (!layer_statistics.layerInfo.IsLayer0() && layer_statistics.count > 0) {
      return true;
    }
  }
  return false;
}
