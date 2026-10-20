#include "CZIeditAPI.h"
#include "CZIwriteAPI.h"
#include <filesystem>

using namespace libCZI;
using namespace std;

CZIeditAPI::CZIeditAPI(const std::wstring &fileName) {
  const auto filenameUtf8 = Utils::ConvertToUtf8(fileName);
  if (!std::filesystem::is_regular_file(
          std::filesystem::u8path(filenameUtf8))) {
    throw std::runtime_error("Cannot edit CZI file \"" + filenameUtf8 +
                             "\": an existing regular file is required.");
  }
  auto stream = CreateInputOutputStreamForFile(fileName.c_str());
  auto rw = CreateCZIReaderWriter();
  rw->Create(stream);
  if (!rw) {
    throw std::logic_error("Failed to create CZI ReaderWriter.");
  }
  this->spReaderWriter_ = rw;
}

void CZIeditAPI::Close() {
  if (this->spReaderWriter_) {
    this->spReaderWriter_->Close();
    this->spReaderWriter_.reset();
  }
}

std::string CZIeditAPI::ReadMetadataXml() const {
  if (auto mdSeg = this->spReaderWriter_->ReadMetadataSegment()) {
    auto meta = CreateMetaFromMetadataSegment(mdSeg.get());
    return meta->GetXml();
  }
  return std::string();
}

libCZI::GeneralDocumentInfo CZIeditAPI::ReadGeneralDocumentInfo() const {
  GeneralDocumentInfo result;
  if (auto mdSeg = this->spReaderWriter_->ReadMetadataSegment()) {
    auto meta = CreateMetaFromMetadataSegment(mdSeg.get());
    auto docInfo = meta->GetDocumentInfo();
    if (docInfo) {
      return docInfo->GetGeneralDocumentInfo();
    }
  }
  return result;
}

libCZI::ScalingInfo CZIeditAPI::ReadScalingInfo() const {
  ScalingInfo result{};
  if (auto mdSeg = this->spReaderWriter_->ReadMetadataSegment()) {
    auto meta = CreateMetaFromMetadataSegment(mdSeg.get());
    auto documentInfo = meta->GetDocumentInfo();
    if (!documentInfo) {
      throw std::logic_error(
          "Unable to get document information from metadata.");
    }

    result = documentInfo->GetScalingInfo();
  }

  return result;
}

libCZI::CustomValueVariant
CZIeditAPI::ReadCustomKeyValue(const std::string &key) const {
  libCZI::CustomValueVariant result;
  auto mdSeg = this->spReaderWriter_->ReadMetadataSegment();
  if (!mdSeg) {
    throw std::logic_error("Unable to read the metadata segment.");
  }

  auto meta = CreateMetaFromMetadataSegment(mdSeg.get());
  std::string path =
      "ImageDocument/Metadata/Information/CustomAttributes/KeyValue/";
  path += key;

  auto kvNode = meta->GetChildNodeReadonly(path.c_str());
  if (!kvNode) {
    return result; // not found
  }

  std::wstring typeAttrW;
  const bool hasType = kvNode->TryGetAttribute(L"Type", &typeAttrW);

  if (!hasType) {
    std::wstring wval;
    if (kvNode->TryGetValue(&wval)) {
      result.SetString(Utils::ConvertToUtf8(wval));
    }
    return result;
  }

  if (typeAttrW == L"Boolean") {
    bool b;
    if (kvNode->TryGetValueAsBool(&b)) {
      result.SetBool(b);
    }
    return result;
  }
  if (typeAttrW == L"Int32") {
    std::int32_t i;
    if (kvNode->TryGetValueAsInt32(&i)) {
      result.SetInt32(i);
    }
    return result;
  }
  if (typeAttrW == L"Double") {
    double d;
    if (kvNode->TryGetValueAsDouble(&d)) {
      result.SetDouble(d);
    }
    return result;
  }
  if (typeAttrW == L"Float") {
    float f;
    if (kvNode->TryGetValueAsFloat(&f)) {
      result.SetFloat(f);
    }
    return result;
  }
  if (typeAttrW == L"String") {
    std::wstring wval;
    if (kvNode->TryGetValue(&wval)) {
      result.SetString(Utils::ConvertToUtf8(wval));
    }
    return result;
  }

  std::wstring wval;
  if (kvNode->TryGetValue(&wval)) {
    result.SetString(Utils::ConvertToUtf8(wval));
  }
  return result;
}

static std::shared_ptr<IXmlNodeRw> GetChannelsNode(IXmlNodeRw *root) {
  auto displayNode = root->GetChildNode("Metadata/DisplaySetting");
  if (!displayNode) {
    throw std::logic_error("DisplaySetting node is not available.");
  }
  return displayNode->GetChildNode("Channels");
}

std::map<int, const ChannelDisplaySettingsStructWithNameAndDescription>
CZIeditAPI::ReadDisplaySettings() const {
  std::map<int, const ChannelDisplaySettingsStructWithNameAndDescription>
      result;

  auto mdSeg = this->spReaderWriter_->ReadMetadataSegment();
  if (!mdSeg) {
    throw std::logic_error("Unable to read the metadata segment.");
  }

  auto meta = CreateMetaFromMetadataSegment(mdSeg.get());

  auto channelsNode = meta->GetChildNodeReadonly(
      "ImageDocument/Metadata/DisplaySetting/Channels");
  if (!channelsNode) {
    throw std::logic_error("Unable to find the channels node.");
  }

  int chanIdxEnum = -1;
  // EnumChildren should be giving us the elements in order so our map index
  // ought to remain consistent.
  channelsNode->EnumChildren([&](std::shared_ptr<IXmlNodeRead> child) -> bool {
    // We should be protected from child being null by the XmlNodeWrapper, but
    // I'm adding it as a guard regardless.
    if (!child) {
      throw std::logic_error("Unable to enumerate channels.");
    }
    ++chanIdxEnum;

    ChannelDisplaySettingsStructWithNameAndDescription
        channelDisplaySettingsStruct;
    channelDisplaySettingsStruct.Clear();

    // For now I'm sticking with specified attributes only. We can consider
    // modifying things like TintingMode, white/black points, etc separately.
    std::wstring nameAttr;
    if (child->TryGetAttribute(L"Name", &nameAttr)) {
      channelDisplaySettingsStruct.name = nameAttr;
    }

    auto descNode = child->GetChildNodeReadonly("Description");
    if (descNode) {
      std::wstring descVal;
      if (descNode->TryGetValue(&descVal)) {
        channelDisplaySettingsStruct.description = descVal;
      }
    }

    auto isSelNode = child->GetChildNodeReadonly("IsSelected");
    if (isSelNode) {
      std::wstring selVal;
      if (isSelNode->TryGetValue(&selVal)) {
        channelDisplaySettingsStruct.isEnabled =
            (selVal == L"true" || selVal == L"True" || selVal == L"1");
      }
    }

    auto tintingModeNode = child->GetChildNodeReadonly("TintingMode");

    result.emplace(chanIdxEnum, channelDisplaySettingsStruct);

    return true;
  });

  return result;
}

std::shared_ptr<PyCZIMetadataBuilder> CZIeditAPI::CreateMetadataBuilder() {
  if (!this->spReaderWriter_) {
    throw std::logic_error("CZIeditAPI is not open.");
  }

  std::shared_ptr<ICziMetadataBuilder> libCziBuilder;

  if (auto mdSegExisting = this->spReaderWriter_->ReadMetadataSegment()) {
    auto metaExisting = CreateMetaFromMetadataSegment(mdSegExisting.get());
    libCziBuilder = CreateMetadataBuilderFromXml(metaExisting->GetXml());
  } else {
    libCziBuilder = libCZI::CreateMetadataBuilder();
  }

  return std::shared_ptr<PyCZIMetadataBuilder>(
      new PyCZIMetadataBuilder(libCziBuilder, this->spReaderWriter_));
}

PyCZIMetadataBuilder::PyCZIMetadataBuilder(
    std::shared_ptr<ICziMetadataBuilder> builder,
    std::shared_ptr<ICziReaderWriter> readerWriter)
    : spBuilder_(std::move(builder)), wpReaderWriter_(readerWriter) {}

std::string PyCZIMetadataBuilder::GetXml(bool prettify) const {
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }
  return this->spBuilder_->GetXml(prettify);
}

void PyCZIMetadataBuilder::SetXml(const std::string &xmlString) {
  this->spBuilder_ = CreateMetadataBuilderFromXml(xmlString);
}

std::shared_ptr<IXmlNodeRw> PyCZIMetadataBuilder::GetRootNode() {
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }
  return this->spBuilder_->GetRootNode();
}

void PyCZIMetadataBuilder::SetGeneralDocumentInfo(
    const GeneralDocumentInfo &docInfo) {
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }
  MetadataUtils::WriteGeneralDocumentInfo(this->spBuilder_.get(), docInfo);
}

void PyCZIMetadataBuilder::SetScalingInfo(
    const libCZI::ScalingInfo &scalingInfo) {
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }
  MetadataUtils::WriteScalingInfo(this->spBuilder_.get(), scalingInfo);
}

void PyCZIMetadataBuilder::SetCustomKeyValue(
    const std::string &key, const libCZI::CustomValueVariant &value) {
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }
  MetadataUtils::SetOrAddCustomKeyValuePair(this->spBuilder_.get(), key, value);
}

void PyCZIMetadataBuilder::SetDisplaySettings(
    const std::map<int,
                   const ChannelDisplaySettingsStructWithNameAndDescription>
        &displaySettings) {
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }
  PyCZIMetadataBuilder::ApplyDisplaySettings(this->spBuilder_.get(),
                                             displaySettings);
}

bool PyCZIMetadataBuilder::CanCommit() const {
  return !this->wpReaderWriter_.expired() && this->spBuilder_ != nullptr;
}

void PyCZIMetadataBuilder::Commit() {
  auto spReaderWriter = this->wpReaderWriter_.lock();
  if (!spReaderWriter) {
    throw std::logic_error("Parent CZI file is no longer available.");
  }
  if (!this->spBuilder_) {
    throw std::logic_error("Builder is not initialized.");
  }

  const auto xmlOut = this->spBuilder_->GetXml(true);
  WriteMetadataInfo wmi;
  wmi.Clear();
  wmi.szMetadata = xmlOut.c_str();
  wmi.szMetadataSize = xmlOut.size();
  wmi.ptrAttachment = nullptr;
  wmi.attachmentSize = 0;
  spReaderWriter->SyncWriteMetadata(wmi);
}

/*static*/ void PyCZIMetadataBuilder::ApplyDisplaySettings(
    ICziMetadataBuilder *builder,
    const std::map<int,
                   const ChannelDisplaySettingsStructWithNameAndDescription>
        &displaySettings) {
  if (displaySettings.empty()) {
    return;
  }

  auto root = builder->GetRootNode();

  auto displayNode = root->GetChildNode("Metadata/DisplaySetting");
  if (!displayNode) {
    throw std::logic_error("DisplaySetting node is not available.");
  }
  auto channelsNode = displayNode->GetChildNode("Channels");
  if (!channelsNode) {
    throw std::logic_error("Channels node is not available.");
  }

  for (const auto &entry : displaySettings) {
    const int chIndex = entry.first;
    const auto &ds = entry.second;

    // This is a positional index query!
    std::string path = "Channel[" + std::to_string(chIndex) + "]";
    auto chRw = channelsNode->GetChildNode(path.c_str());
    if (!chRw) {
      throw std::logic_error("Channel node for index " +
                             std::to_string(chIndex) + " is not available.");
    }

    if (!ds.name.empty()) {
      chRw->SetAttribute(L"Name", ds.name.c_str());
    }

    if (!ds.description.empty()) {
      auto descNode = chRw->GetOrCreateChildNode("Description");
      descNode->SetValue(ds.description.c_str());
    }

    {
      auto isSelectedNode = chRw->GetOrCreateChildNode("IsSelected");
      if (isSelectedNode) {
        isSelectedNode->SetValue(ds.isEnabled ? L"true" : L"false");
      }
    }
  }
}
