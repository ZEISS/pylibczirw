#include "CZIreadAPI.h"
#include "StaticContext.h"

#include <codecvt>
#include <locale>
#include <sstream>

using namespace libCZI;
using namespace std;

CZIreadAPI::CZIreadAPI(const std::wstring& fileName)
    : CZIreadAPI("", fileName, SubBlockCacheOptions())
{
}

CZIreadAPI::CZIreadAPI(const std::wstring& fileName, const SubBlockCacheOptions& subBlockCacheOptions)
: CZIreadAPI("", fileName, subBlockCacheOptions)
{
}

CZIreadAPI::CZIreadAPI(const std::string& stream_class_name, const std::wstring& fileName)
: CZIreadAPI(stream_class_name, fileName, SubBlockCacheOptions())
{
}

CZIreadAPI::CZIreadAPI(const std::string& stream_class_name, const std::wstring& fileName, const SubBlockCacheOptions& subBlockCacheOptions)
{
    shared_ptr<IStream> stream;
    if (stream_class_name.empty() || stream_class_name == "standard")
    {
        stream = StreamsFactory::CreateDefaultStreamForFile(fileName.c_str());
    }
    else if (stream_class_name == "curl")
    {
        StreamsFactory::CreateStreamInfo create_info;
        create_info.class_name = kStaticContext.GetStreamClassNameForCurlReader();  // set the libczi-stream-class-name for the python reader class "curl"
        kStaticContext.SetDefaultPropertiesForReader(create_info);                  // and have the default-properties set for this class

        stream = StreamsFactory::CreateStream(create_info, fileName);
        if (!stream)
        {
            wstring_convert<codecvt_utf8<wchar_t>> utf8_conv;
            string filename_utf8 = utf8_conv.to_bytes(fileName);
            stringstream string_stream;
            string_stream << "Failed to create stream for stream class: " << stream_class_name << " and filename: " << filename_utf8 << '.';
            throw std::runtime_error(string_stream.str());
        }
    }

    const auto reader = libCZI::CreateCZIReader();
    reader->Open(stream);
    this->spAccessor = reader->CreateSingleChannelScalingTileAccessor();
    this->spReader = reader;
    this->subBlockCacheOptions = subBlockCacheOptions;
    if (subBlockCacheOptions.cacheType == CacheType::Standard)
    {
        this->spSubBlockCache = libCZI::CreateSubBlockCache();
    } 
    else if (subBlockCacheOptions.cacheType != CacheType::None)
    {
        stringstream string_stream;
        string_stream << "The specified type of cache is not supported: " << static_cast<underlying_type_t<CacheType>>(subBlockCacheOptions.cacheType) << '.';
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

    // Should replace nullptr with reference to handle CZI with index not starting at 0, legal ?
    const bool dim_exist = stats.dimBounds.TryGetInterval(DimIndex, nullptr, &size);

    if (dim_exist)
    {
        return size;
    }

    return 0;
}

libCZI::PixelType CZIreadAPI::GetChannelPixelType(int chanelIdx) {

    libCZI::SubBlockInfo sbBlkInfo;
    const bool b = this->spReader->TryGetSubBlockInfoOfArbitrarySubBlockInChannel(chanelIdx, sbBlkInfo);
    if (!b)
    {
        // TODO more precise error handling
        return libCZI::PixelType::Invalid;
    }

    return sbBlkInfo.pixelType;
}


libCZI::SubBlockStatistics CZIreadAPI::GetSubBlockStats() {

    return this->spReader->GetStatistics();
}

std::unique_ptr<PImage> CZIreadAPI::GetSingleChannelScalingTileAccessorData(libCZI::PixelType pixeltype, libCZI::IntRect roi, libCZI::RgbFloatColor bgColor, float zoom, const std::string& coordinateString, const std::wstring& SceneIndexes) 
{
    libCZI::CDimCoordinate planeCoordinate;
    try
    {
        planeCoordinate = CDimCoordinate::Parse(coordinateString.c_str());
    }
    catch (libCZI::LibCZIStringParseException& parseExcp)
    {
        //TODO Error handling
    }

    libCZI::ISingleChannelScalingTileAccessor::Options scstaOptions; 
    scstaOptions.Clear();
    scstaOptions.useVisibilityCheckOptimization = true; // enable the "visibility check optimization"
    scstaOptions.backGroundColor = bgColor;
    if (this->spSubBlockCache) 
    {
        scstaOptions.subBlockCache = this->spSubBlockCache;
        scstaOptions.onlyUseSubBlockCacheForCompressedData = this->subBlockCacheOptions.cacheOnlyCompressed;
    }

    if (!SceneIndexes.empty())
    {
        scstaOptions.sceneFilter = libCZI::Utils::IndexSetFromString(SceneIndexes);
    }

    std::shared_ptr<libCZI::IBitmapData> Data = this->spAccessor->Get(pixeltype, roi, &planeCoordinate, zoom, &scstaOptions);

    if (this->spSubBlockCache) 
    {
        this->spSubBlockCache->Prune(this->subBlockCacheOptions.pruneOptions);
    }

    std::unique_ptr<PImage> ptr_Bitmap(new PImage(Data));
    return ptr_Bitmap;
}

/// Returns an info struct on the subblock cache
SubBlockCacheInfo CZIreadAPI::GetCacheInfo() 
{
    auto cacheInfo = SubBlockCacheInfo();
    if (this->spSubBlockCache) 
    {
        // Note: We need to use one call (to retrieve the values) in order to ensure that they are consistent.
        const auto cacheStatistics = this->spSubBlockCache->GetStatistics(libCZI::ISubBlockCacheStatistics::kElementsCount | libCZI::ISubBlockCacheStatistics::kMemoryUsage);
        cacheInfo.elementsCount = cacheStatistics.elementsCount;
        cacheInfo.memoryUsage = cacheStatistics.memoryUsage;
    }

    return cacheInfo;
}
