#include "CZIwriteAPI.h"
#include "../pylibCZIrw_Config.h"
#include <algorithm>
#include <optional>

using namespace libCZI;
using namespace std;

CZIwriteAPI::CZIwriteAPI(const std::wstring &fileName)
    : CZIwriteAPI(fileName, "") {}

CZIwriteAPI::CZIwriteAPI(const std::wstring &fileName,
                         const std::string &compressionOptions) {
  if (!compressionOptions.empty()) {
    this->defaultCompressionOptions_ =
        Utils::ParseCompressionOptions(compressionOptions);
  } else {
    this->defaultCompressionOptions_.first = CompressionMode::UnCompressed;
  }

  const auto stream = libCZI::CreateOutputStreamForFile(fileName.c_str(), true);
  const auto spWriter = libCZI::CreateCZIWriter();

  // initialize the "CZI-writer-object" with the "output-stream-object"
  // notes: (1) not sure if we should/have to provide a "bounds" at
  // initialization
  //        (2) the bounds provided here _could_ be used to create a suitable
  //        sized subblk-directory at the
  //             beginning of the file AND for checking the validity of the
  //             subblocks added later on
  //        (3) ...both things are not really necessary from a technical point
  //        of view, however... consistency-
  //             checking I'd consider an important feature

  const auto spWriterInfo =
      make_shared<CCziWriterInfo>(GUID{0, 0, 0, {0, 0, 0, 0, 0, 0, 0, 0}});
  spWriter->Create(stream, spWriterInfo);

  this->spWriter_ = spWriter;
}

bool CZIwriteAPI::AddTile(const std::string &coordinateString,
                          const PImage *plane, int x, int y, int m,
                          const std::string &retiling_id) {

  return this->AddTileEx(coordinateString, plane, x, y, m, "", retiling_id);
}

bool CZIwriteAPI::AddTileEx(const std::string &coordinateString,
                            const PImage *plane, int x, int y, int m,
                            const std::string &compressionOptions,
                            const std::string &retiling_id) {
  libCZI::Utils::CompressionOption actualCompressionOptions;
  if (!compressionOptions.empty()) {
    actualCompressionOptions =
        Utils::ParseCompressionOptions(compressionOptions);
  } else {
    actualCompressionOptions = this->defaultCompressionOptions_;
  }

  libCZI::CDimCoordinate coords;
  (void)Utils::StringToDimCoordinate(coordinateString.c_str(), &coords);

  // Get per-channel pixel type
  int cIndex = 0;
  if (coords.TryGetPosition(libCZI::DimensionIndex::C, &cIndex)) {
    channelPixelTypes_[cIndex] = plane->get_pixelType();
  }

  auto sbmetadata = CZIwriteAPI::CreateSubBlockMetadataXml(retiling_id);
  CZIwriteAPI::AddSubBlock(coords, plane, actualCompressionOptions,
                           this->spWriter_.get(), x, y, m, sbmetadata);

  return true;
}

void CZIwriteAPI::WriteMetadata(
    const std::wstring &documentTitle, const std::optional<double> scaleX,
    const std::optional<double> scaleY, const std::optional<double> scaleZ,
    const std::map<int, std::string> &channelNames,
    const std::map<std::string, const libCZI::CustomValueVariant>
        &customAttributes,
    const std::map<int, const ChannelDisplaySettingsStruct> &displaySettings) {
  // get "partially filled out" metadata - the metadata contains information
  // which was derived from the
  //  subblocks added, in particular we "pre-fill" the Size-information, and the
  //  Pixeltype-information
  PrepareMetadataInfo prepareInfo;
  prepareInfo.funcGenerateIdAndNameForChannel =
      [&channelNames](int channelIndex) -> tuple<string, tuple<bool, string>> {
    stringstream ssId, ssName;
    ssId << "Channel:" << channelIndex;
    auto channelNameIterator = channelNames.find(channelIndex);
    bool nameIsValid;
    if (channelNameIterator != channelNames.end()) {
      ssName << channelNameIterator->second;
      nameIsValid = true;
    } else {
      ssName << "";
      nameIsValid = false;
    }
    return make_tuple(ssId.str(), make_tuple(nameIsValid, ssName.str()));
  };

  auto mdBldr = this->spWriter_->GetPreparedMetadata(prepareInfo);

  // now we could add additional information
  GeneralDocumentInfo docInfo;
  docInfo.SetTitle(documentTitle);
  docInfo.SetComment(L"pylibCZIrw generated");
  MetadataUtils::WriteGeneralDocumentInfo(mdBldr.get(), docInfo);

  // Add scaleinfo
  ScalingInfo scaleInfo;
  if (scaleX.has_value()) {
    scaleInfo.scaleX = scaleX.value();
  }

  if (scaleY.has_value()) {
    scaleInfo.scaleY = scaleY.value();
  }

  if (scaleZ.has_value()) {
    scaleInfo.scaleZ = scaleZ.value();
  }

  MetadataUtils::WriteScalingInfo(mdBldr.get(), scaleInfo);

  // Add DisplaySettings
  // see test_DisplaySettings.cpp -> TEST(DisplaySettings,
  // WriteDisplaySettingsToDocumentAndReadFromThereAndCompare) for an
  // explanation on this process)
  if (displaySettings.size()) {
    DisplaySettingsPOD display_settings;
    ChannelDisplaySettingsPOD channel_display_setting;
    for (const auto &entry : displaySettings) {
      channel_display_setting.Clear();
      channel_display_setting.isEnabled = entry.second.isEnabled;
      channel_display_setting.tintingColor = entry.second.tintingColor;
      channel_display_setting.blackPoint = entry.second.blackPoint;
      channel_display_setting.whitePoint = entry.second.whitePoint;
      switch (entry.second.tintingMode) {
      case TintingModeEnum::Color:
        channel_display_setting.tintingMode =
            libCZI::IDisplaySettings::TintingMode::Color;
        break;
      case TintingModeEnum::LookUpTableExplicit:
        channel_display_setting.tintingMode =
            libCZI::IDisplaySettings::TintingMode::LookUpTableExplicit;
        break;
      case TintingModeEnum::LookUpTableWellKnown:
        channel_display_setting.tintingMode =
            libCZI::IDisplaySettings::TintingMode::LookUpTableWellKnown;
        break;
      default:
        channel_display_setting.tintingMode =
            libCZI::IDisplaySettings::TintingMode::None;
        break;
      }
      display_settings.channelDisplaySettings[entry.first] =
          (channel_display_setting);
    }

    MetadataUtils::WriteDisplaySettings(
        mdBldr.get(),
        DisplaySettingsPOD::CreateIDisplaySettingSp(display_settings).get());
  }

  // Add custom attributes
  for (const auto &it : customAttributes) {
    const auto &key = it.first;
    const auto &value = it.second;
    MetadataUtils::SetOrAddCustomKeyValuePair(mdBldr.get(), key, value);
  }

  
  // Infer ComponentBitCount
  int imageBits = 0;
  if (!channelPixelTypes_.empty()) {
    bool allEqual = true;
    int firstBits = BitsPerComponent(channelPixelTypes_.begin()->second);
    int maxBits = firstBits;
    for (const auto& kv : channelPixelTypes_) {
      const int b = BitsPerComponent(kv.second);
      if (b != firstBits) allEqual = false;
      if (b > maxBits)  maxBits = b;
    }
    imageBits = allEqual ? firstBits : maxBits;
  }
  if (imageBits > 0) {
    const bool integerPixels =
      (imageBits == 8 || imageBits == 16 || imageBits == 32) &&
      // treat float32 types specially:
      (std::none_of(channelPixelTypes_.begin(), channelPixelTypes_.end(),
        [](auto& kv){ return kv.second == libCZI::PixelType::Gray32Float 
            || kv.second == libCZI::PixelType::Bgr96Float; }));
    mdBldr->GetRootNode()
      ->GetOrCreateChildNode("Metadata/Information/Image/ComponentBitCount")
      ->SetValue(imageBits);
    if (integerPixels) {
      const auto highVal = (imageBits >= 31) ? 0x7FFFFFFFu : ((1u << imageBits) - 1u);
      mdBldr->GetRootNode()
        ->GetOrCreateChildNode("Metadata/Information/Image/ComponentHighValue")
        ->SetValue(highVal);
    }
  }

  // Per-channel bitcount
  auto channelsNode = mdBldr->GetRootNode()
    ->GetOrCreateChildNode("Metadata/Information/Image/Dimensions/Channels");
    
  for (const auto& kv : channelPixelTypes_) {
    const int c    = kv.first;
    const int bits = BitsPerComponent(kv.second);
    if (bits <= 0) continue;

    // Find existing <Channel Id="Channel:c"> or create a new one
    std::shared_ptr<libCZI::IMetadataNode> channelNode;
    for (int i = 0;; ++i) {
      auto child = channelsNode->GetChildNode("Channel", i);
      if (!child) break;
      auto idAttr = child->GetAttribute("Id");
      if (idAttr.has_value() && idAttr.value() == ("Channel:" + std::to_string(c))) {
        channelNode = child;
          break;
        }
    }
    if (!channelNode) {
        channelNode = channelsNode->CreateChildNode("Channel");
        channelNode->SetAttribute("Id", ("Channel:" + std::to_string(c)).c_str());
    }

    channelNode->GetOrCreateChildNode("ComponentBitCount")->SetValue(bits);
  }

  mdBldr->GetRootNode()
      ->GetOrCreateChildNode("Metadata/Information/Application/Name")
      ->SetValue("pylibCZIrw");
  mdBldr->GetRootNode()
      ->GetOrCreateChildNode("Metadata/Information/Application/Version")
      ->SetValue(PROJECT_VERSION);

  // the resulting metadata-information is written to the CZI here
  auto xml = mdBldr->GetXml();
  WriteMetadataInfo writerMdInfo;
  writerMdInfo.Clear();
  writerMdInfo.szMetadata = xml.c_str();
  writerMdInfo.szMetadataSize = xml.size();
  this->spWriter_->SyncWriteMetadata(writerMdInfo);
}

/*static*/ std::string
CZIwriteAPI::CreateSubBlockMetadataXml(const std::string &retiling_id) {
  if (retiling_id.empty()) {
    return retiling_id;
  } else {
    stringstream ss;
    ss << "<METADATA><Tags><RetilingId>" << retiling_id
       << "</RetilingId></Tags></METADATA>";
    return ss.str();
  }
}

/*static*/ void CZIwriteAPI::AddSubBlock(
    const libCZI::CDimCoordinate &coord, const PImage *subblock,
    const libCZI::Utils::CompressionOption &compressionOptions,
    libCZI::ICziWriter *writer, int x, int y, int m,
    const std::string &sbmetadata) {
  if (compressionOptions.first == CompressionMode::UnCompressed) {
    AddSubBlockInfoStridedBitmap addInfo;
    addInfo.Clear();
    addInfo.coordinate = coord;
    addInfo.mIndexValid = true;
    addInfo.mIndex = m;
    addInfo.x = x;
    addInfo.y = y;
    addInfo.logicalWidth = static_cast<int>(subblock->get_width());
    addInfo.logicalHeight = static_cast<int>(subblock->get_height());
    addInfo.physicalWidth = static_cast<int>(subblock->get_width());
    addInfo.physicalHeight = static_cast<int>(subblock->get_height());
    addInfo.PixelType = subblock->get_pixelType();
    addInfo.ptrBitmap = subblock->get_data();
    addInfo.strideBitmap = static_cast<uint32_t>(subblock->get_stride());
    addInfo.SetCompressionMode(libCZI::CompressionMode::UnCompressed);
    addInfo.ptrSbBlkMetadata = sbmetadata.c_str();
    addInfo.sbBlkMetadataSize = static_cast<uint32_t>(sbmetadata.size());

    writer->SyncAddSubBlock(addInfo);
  } else if (compressionOptions.first == CompressionMode::Zstd1 ||
             compressionOptions.first == CompressionMode::Zstd0) {
    AddSubBlockInfoMemPtr addInfo;
    addInfo.Clear();
    addInfo.coordinate = coord;
    addInfo.mIndexValid = true;
    addInfo.mIndex = m;
    addInfo.x = x;
    addInfo.y = y;
    addInfo.logicalWidth = static_cast<int>(subblock->get_width());
    addInfo.logicalHeight = static_cast<int>(subblock->get_height());
    addInfo.physicalWidth = static_cast<int>(subblock->get_width());
    addInfo.physicalHeight = static_cast<int>(subblock->get_height());
    addInfo.PixelType = subblock->get_pixelType();
    addInfo.ptrSbBlkMetadata = sbmetadata.c_str();
    addInfo.sbBlkMetadataSize = static_cast<uint32_t>(sbmetadata.size());

    addInfo.SetCompressionMode(compressionOptions.first);

    std::shared_ptr<IMemoryBlock> memblk;
    if (compressionOptions.first == CompressionMode::Zstd1) {
      memblk = ZstdCompress::CompressZStd1Alloc(
          addInfo.physicalWidth, addInfo.physicalHeight,
          static_cast<uint32_t>(subblock->get_stride()), addInfo.PixelType,
          subblock->get_data(), compressionOptions.second.get());
    } else {
      memblk = ZstdCompress::CompressZStd0Alloc(
          addInfo.physicalWidth, addInfo.physicalHeight,
          static_cast<uint32_t>(subblock->get_stride()), addInfo.PixelType,
          subblock->get_data(), compressionOptions.second.get());
    }

    addInfo.ptrData = memblk->GetPtr();
    addInfo.dataSize = static_cast<uint32_t>(memblk->GetSizeOfData());

    writer->SyncAddSubBlock(addInfo);
  } else {
    throw invalid_argument("An unsupported compression mode was specified.");
  }
}
