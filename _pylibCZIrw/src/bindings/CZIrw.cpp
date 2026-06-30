#include "../api/CZIeditAPI.h"
#include "../api/CZIreadAPI.h"
#include "../api/CZIwriteAPI.h"
#include "../api/PImage.h"
#include "../api/ReaderOptions.h"
#include "../api/SubBlockCache.h"
#include "../api/site.h"
#include "PbHelper.h"

#include <exception>
#include <functional>
#include <optional>

#include <pybind11/chrono.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/options.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

namespace {
std::function<bool(int, const libCZI::SubBlockInfo &)> StopOnCallbackException(
    const std::function<bool(int, const libCZI::SubBlockInfo &)> &func,
    std::exception_ptr &callbackException) {
  return
      [&func, &callbackException](int index, const libCZI::SubBlockInfo &info) {
        if (callbackException) {
          return false;
        }

        try {
          return func(index, info);
        } catch (...) {
          callbackException = std::current_exception();
          return false;
        }
      };
}
} // namespace

PYBIND11_MODULE(_pylibCZIrw, m) {
  py::class_<CZIreadAPI>(m, "czi_reader", py::module_local())
      .def(py::init([](const std::wstring &fileName) {
        return new CZIreadAPI(fileName);
      }))
      .def(py::init([](const std::string &stream_class_name,
                       const std::wstring &fileName) {
        return new CZIreadAPI(stream_class_name, fileName);
      }))
      .def(py::init([](const std::wstring &fileName,
                       const SubBlockCacheOptions &subBlockCacheOptions) {
        return new CZIreadAPI(fileName, subBlockCacheOptions);
      }))
      .def(py::init([](const std::string &stream_class_name,
                       const std::wstring &fileName,
                       const SubBlockCacheOptions &subBlockCacheOptions) {
        return new CZIreadAPI(stream_class_name, fileName,
                              subBlockCacheOptions);
      }))
      .def(py::init([](const std::string &stream_class_name,
                       const std::wstring &fileName,
                       const SubBlockCacheOptions &subBlockCacheOptions,
                       const ReaderOptions &readerOptions) {
        return new CZIreadAPI(stream_class_name, fileName, subBlockCacheOptions,
                              readerOptions);
      }))
      .def("close", &CZIreadAPI::close)
      .def("GetXmlMetadata", &CZIreadAPI::GetXmlMetadata)
      .def("GetSubBlockStats", &CZIreadAPI::GetSubBlockStats)
      .def("GetDimensionSize", &CZIreadAPI::GetDimensionSize)
      .def("GetChannelPixelType", &CZIreadAPI::GetChannelPixelType)
      .def("GetSingleChannelScalingTileAccessorData",
           [](CZIreadAPI &self, libCZI::PixelType pixeltype,
              libCZI::IntRect roi, libCZI::RgbFloatColor bgColor, float zoom,
              const std::string &coordinateString,
              const std::wstring &SceneIndexes) {
             // We release the GIL to make data access parallelizable via python
             // threads. Note: Whenever the executed C++ code tries to access
             // python objects,
             //       the GIL must be re-acquired using py::gil_scoped_acquire
             //       and released again to make the rest of the code
             //       parallelizable again.
             // For more details see:
             // https://pybind11.readthedocs.io/en/stable/advanced/misc.html#global-interpreter-lock-gil
             py::gil_scoped_release release;
             auto result = self.GetSingleChannelScalingTileAccessorData(
                 pixeltype, roi, bgColor, zoom, coordinateString, SceneIndexes);
             return result;
           })
      .def("GetCacheInfo", &CZIreadAPI::GetCacheInfo)
      .def(
          "EnumerateSubBlocks",
          [](CZIreadAPI &self,
             const std::function<bool(int, const libCZI::SubBlockInfo &)>
                 &func) {
            std::exception_ptr callbackException;
            auto callback = StopOnCallbackException(func, callbackException);
            self.EnumerateSubBlocks(callback);
            if (callbackException) {
              std::rethrow_exception(callbackException);
            }
          },
          py::arg("func"),
          "Enumerate all subblocks and call the provided function for each")
      .def(
          "EnumerateSubset",
          [](CZIreadAPI &self, py::object planeCoordinate, py::object roi,
             bool onlyLayer0,
             const std::function<bool(int, const libCZI::SubBlockInfo &)>
                 &func) {
            const libCZI::IDimCoordinate *pCoord = nullptr;
            const libCZI::IntRect *pRoi = nullptr;

            std::unique_ptr<libCZI::CDimCoordinate> coordHolder;
            std::unique_ptr<libCZI::IntRect> roiHolder;

            if (!planeCoordinate.is_none()) {
              if (py::isinstance<std::string>(planeCoordinate)) {
                std::string coordStr = py::cast<std::string>(planeCoordinate);
                coordHolder = std::make_unique<libCZI::CDimCoordinate>(
                    libCZI::CDimCoordinate::Parse(coordStr.c_str()));
                pCoord = coordHolder.get();
              } else if (py::isinstance<py::dict>(planeCoordinate)) {
                py::dict coordDict = py::cast<py::dict>(planeCoordinate);
                coordHolder = std::make_unique<libCZI::CDimCoordinate>();
                for (auto item : coordDict) {
                  std::string dim_str = py::str(item.first);
                  if (dim_str.length() == 1) {
                    libCZI::DimensionIndex dim =
                        libCZI::Utils::CharToDimension(dim_str[0]);
                    if (dim != libCZI::DimensionIndex::invalid) {
                      int value = py::cast<int>(item.second);
                      coordHolder->Set(dim, value);
                    }
                  }
                }
                pCoord = coordHolder.get();
              } else if (py::isinstance<libCZI::CDimCoordinate>(
                             planeCoordinate)) {
                pCoord =
                    &py::cast<const libCZI::CDimCoordinate &>(planeCoordinate);
              }
            }

            if (!roi.is_none()) {
              roiHolder = std::make_unique<libCZI::IntRect>(
                  py::cast<libCZI::IntRect>(roi));
              pRoi = roiHolder.get();
            }

            std::exception_ptr callbackException;
            auto callback = StopOnCallbackException(func, callbackException);
            self.EnumerateSubset(pCoord, pRoi, onlyLayer0, callback);
            if (callbackException) {
              std::rethrow_exception(callbackException);
            }
          },
          py::arg("plane_coordinate") = py::none(), py::arg("roi") = py::none(),
          py::arg("only_layer0") = false, py::arg("func"),
          "Enumerate a filtered subset of subblocks. Plane coordinate can be a "
          "string (e.g., 'C0Z5'), "
          "a dict (e.g., {'C': 0, 'Z': 5}), or a DimCoordinate object.");

  py::class_<CZIwriteAPI>(m, "czi_writer", py::module_local())
      .def(py::init<const std::wstring &, const std::string &>())
      .def(py::init<const std::wstring &>())
      .def("close", &CZIwriteAPI::close)
      .def("WriteMetadata", &CZIwriteAPI::WriteMetadata)
      .def("AddTile", &CZIwriteAPI::AddTile)
      .def("AddTileEx", &CZIwriteAPI::AddTileEx);

  py::class_<PImage>(m, "PImage", py::buffer_protocol(), py::module_local())
      .def(py::init([](py::buffer b, libCZI::PixelType pixel_type) {
        /* Request a buffer descriptor from Python */
        const py::buffer_info info = b.request();

        /* Some sanity checks ... */
        if (info.ndim != 3) {
          throw std::runtime_error("Incompatible buffer dimension!");
        }

        /* Convert Python Buffer to BitmapData */
        const auto BitmapPtr = PbHelper::BufferToBitmap(b, pixel_type);

        std::unique_ptr<PImage> BitmapUptr(new PImage(BitmapPtr));
        return BitmapUptr;
      }))
      .def_buffer([](PImage &m) -> py::buffer_info {
        return py::buffer_info(
            m.get_data(),     // Pointer to buffer
            m.get_itemsize(), // Size of one scalar
            PbHelper::get_format(
                m.get_pixelType()), // Python struct-style format descriptor
            m.get_ndim(),           // Number of dimensions
            m.get_shape(),          // Buffer dimensions
            {                       // Strides (in bytes) for each index
             m.get_stride(), m.get_shape()[m.get_ndim() - 1] * m.get_itemsize(),
             m.get_itemsize()});
      });

  py::class_<libCZI::SubBlockStatistics>(m, "SubBlockStatistics",
                                         py::module_local())
      .def(py::init<>())
      .def_readonly("subBlockCount", &libCZI::SubBlockStatistics::subBlockCount)
      .def_readonly("minMindex", &libCZI::SubBlockStatistics::minMindex)
      .def_readonly("maxMindex", &libCZI::SubBlockStatistics::maxMindex)
      .def_readonly("boundingBox", &libCZI::SubBlockStatistics::boundingBox)
      .def_readonly("boundingBoxLayer0Only",
                    &libCZI::SubBlockStatistics::boundingBoxLayer0Only)
      //.def_readonly("dimBounds", &libCZI::SubBlockStatistics::dimBounds)
      .def_readonly("sceneBoundingBoxes",
                    &libCZI::SubBlockStatistics::sceneBoundingBoxes);

  py::class_<libCZI::BoundingBoxes>(m, "BoundingBoxes", py::module_local())
      .def(py::init<>())
      .def_readwrite("boundingBox", &libCZI::BoundingBoxes::boundingBox)
      .def_readwrite("boundingBoxLayer0",
                     &libCZI::BoundingBoxes::boundingBoxLayer0);

  py::class_<libCZI::RgbFloatColor>(m, "RgbFloatColor", py::module_local())
      .def(py::init<>())
      .def_readwrite("b", &libCZI::RgbFloatColor::b)
      .def_readwrite("g", &libCZI::RgbFloatColor::g)
      .def_readwrite("r", &libCZI::RgbFloatColor::r);

  py::class_<libCZI::IntRect>(m, "IntRect", py::module_local())
      .def(py::init<>())
      .def_readwrite("x", &libCZI::IntRect::x)
      .def_readwrite("y", &libCZI::IntRect::y)
      .def_readwrite("w", &libCZI::IntRect::w)
      .def_readwrite("h", &libCZI::IntRect::h);

  py::class_<libCZI::IntSize>(m, "IntSize", py::module_local())
      .def(py::init<>())
      .def_readwrite("w", &libCZI::IntSize::w)
      .def_readwrite("h", &libCZI::IntSize::h);

  py::class_<libCZI::CDimCoordinate>(m, "DimCoordinate", py::module_local())
      .def(py::init<>())
      .def(py::init([](const std::string &coordinate_string) {
             return libCZI::CDimCoordinate::Parse(coordinate_string.c_str());
           }),
           py::arg("coordinate_string"),
           "Create a DimCoordinate from a coordinate string (e.g., 'C0Z5T2')")
      .def(py::init([](const py::dict &coord_dict) {
             libCZI::CDimCoordinate coord;
             for (auto item : coord_dict) {
               std::string dim_str = py::str(item.first);
               if (dim_str.length() == 1) {
                 libCZI::DimensionIndex dim =
                     libCZI::Utils::CharToDimension(dim_str[0]);
                 if (dim != libCZI::DimensionIndex::invalid) {
                   int value = py::cast<int>(item.second);
                   coord.Set(dim, value);
                 }
               }
             }
             return coord;
           }),
           py::arg("coordinate_dict"),
           "Create a DimCoordinate from a dictionary (e.g., {'C': 0, 'Z': 5, "
           "'T': 2})")
      .def("set", &libCZI::CDimCoordinate::Set, py::arg("dimension"),
           py::arg("value"), "Set the value for a specific dimension")
      .def("clear",
           py::overload_cast<libCZI::DimensionIndex>(
               &libCZI::CDimCoordinate::Clear),
           py::arg("dimension"), "Clear a specific dimension")
      .def("clear_all", py::overload_cast<>(&libCZI::CDimCoordinate::Clear),
           "Clear all dimensions")
      .def(
          "try_get_position",
          [](const libCZI::CDimCoordinate &self,
             libCZI::DimensionIndex dim) -> py::object {
            int value;
            if (self.TryGetPosition(dim, &value)) {
              return py::cast(value);
            }
            return py::none();
          },
          py::arg("dimension"),
          "Try to get the position for a dimension. Returns the value or None "
          "if not set.")
      .def(
          "to_dict",
          [](const libCZI::CDimCoordinate &self) -> py::dict {
            py::dict result;
            for (auto i = static_cast<
                     std::underlying_type<libCZI::DimensionIndex>::type>(
                     libCZI::DimensionIndex::MinDim);
                 i <= static_cast<
                          std::underlying_type<libCZI::DimensionIndex>::type>(
                          libCZI::DimensionIndex::MaxDim);
                 ++i) {
              int value;
              libCZI::DimensionIndex dim =
                  static_cast<libCZI::DimensionIndex>(i);
              if (self.TryGetPosition(dim, &value)) {
                char dim_char = libCZI::Utils::DimensionToChar(dim);
                std::string key(1, dim_char);
                result[py::str(key)] = value;
              }
            }
            return result;
          },
          "Convert coordinate to a Python dictionary");

  py::enum_<libCZI::CompressionMode>(m, "CompressionMode", py::module_local())
      .value("Invalid", libCZI::CompressionMode::Invalid)
      .value("UnCompressed", libCZI::CompressionMode::UnCompressed)
      .value("Jpg", libCZI::CompressionMode::Jpg)
      .value("JpgXr", libCZI::CompressionMode::JpgXr)
      .value("Zstd0", libCZI::CompressionMode::Zstd0)
      .value("Zstd1", libCZI::CompressionMode::Zstd1)
      .export_values();

  py::class_<libCZI::SubBlockInfo>(m, "SubBlockInfo", py::module_local())
      .def(py::init<>())
      .def_readonly("compressionModeRaw",
                    &libCZI::SubBlockInfo::compressionModeRaw)
      .def_readonly("pixelType", &libCZI::SubBlockInfo::pixelType)
      .def_readonly("coordinate", &libCZI::SubBlockInfo::coordinate)
      .def_readonly("logicalRect", &libCZI::SubBlockInfo::logicalRect)
      .def_readonly("physicalSize", &libCZI::SubBlockInfo::physicalSize)
      .def_readonly("mIndex", &libCZI::SubBlockInfo::mIndex)
      .def("get_compression_mode", &libCZI::SubBlockInfo::GetCompressionMode,
           "Get the compression mode as an enum")
      .def("get_zoom", &libCZI::SubBlockInfo::GetZoom,
           "Calculate zoom factor from physical and logical size")
      .def("is_mindex_valid", &libCZI::SubBlockInfo::IsMindexValid,
           "Check if M-index is valid");

  py::enum_<libCZI::DimensionIndex>(m, "DimensionIndex", py::module_local())
      .value("Z", libCZI::DimensionIndex::Z)
      .value("C", libCZI::DimensionIndex::C)
      .value("T", libCZI::DimensionIndex::T)
      .value("R", libCZI::DimensionIndex::R)
      .value("S", libCZI::DimensionIndex::S)
      .value("I", libCZI::DimensionIndex::I)
      .value("H", libCZI::DimensionIndex::H)
      .value("V", libCZI::DimensionIndex::V)
      .value("B", libCZI::DimensionIndex::B)
      .export_values();

  py::enum_<libCZI::PixelType>(m, "PixelType", py::module_local())
      .value("Gray8", libCZI::PixelType::Gray8)
      .value("Gray16", libCZI::PixelType::Gray16)
      .value("Gray32", libCZI::PixelType::Gray32)
      .value("Bgr24", libCZI::PixelType::Bgr24)
      .value("Bgr48", libCZI::PixelType::Bgr48)
      .value("Gray32Float", libCZI::PixelType::Gray32Float)
      .value("Bgr96Float", libCZI::PixelType::Bgr96Float)
      .value("Invalid", libCZI::PixelType::Invalid)
      .export_values();

  py::class_<libCZI::CustomValueVariant>(m, "CustomValueVariant",
                                         py::module_local())
      .def(py::init<>())
      .def_property("int32Value",
                    &libCZI::CustomValueVariant::GetAsInt32OrThrow,
                    &libCZI::CustomValueVariant::SetInt32)
      .def_property("floatValue",
                    &libCZI::CustomValueVariant::GetAsFloatOrThrow,
                    &libCZI::CustomValueVariant::SetFloat)
      .def_property("doubleValue",
                    &libCZI::CustomValueVariant::GetAsDoubleOrThrow,
                    &libCZI::CustomValueVariant::SetDouble)
      .def_property("boolValue", &libCZI::CustomValueVariant::GetAsBoolOrThrow,
                    &libCZI::CustomValueVariant::SetBool)
      .def_property("stringValue",
                    &libCZI::CustomValueVariant::GetAsStringOrThrow,
                    &libCZI::CustomValueVariant::SetString);

  py::enum_<TintingModeEnum>(m, "TintingModeEnum", py::module_local())
      .value("None", TintingModeEnum::None)
      .value("Color", TintingModeEnum::Color)
      .value("LookUpTableExplicit", TintingModeEnum::LookUpTableExplicit)
      .value("LookUpTableWellKnown", TintingModeEnum::LookUpTableWellKnown)
      .export_values();

  py::class_<libCZI::Rgb8Color>(m, "Rgb8Color", py::module_local())
      .def(py::init<>())
      .def_readwrite("r", &libCZI::Rgb8Color::r)
      .def_readwrite("g", &libCZI::Rgb8Color::g)
      .def_readwrite("b", &libCZI::Rgb8Color::b);

  py::class_<ChannelDisplaySettingsStruct>(m, "ChannelDisplaySettingsStruct",
                                           py::module_local())
      .def(py::init<>())
      .def_readwrite("isEnabled", &ChannelDisplaySettingsStruct::isEnabled)
      .def_readwrite("tintingMode", &ChannelDisplaySettingsStruct::tintingMode)
      .def_readwrite("tintingColor",
                     &ChannelDisplaySettingsStruct::tintingColor)
      .def_readwrite("blackPoint", &ChannelDisplaySettingsStruct::blackPoint)
      .def_readwrite("whitePoint", &ChannelDisplaySettingsStruct::whitePoint)
      .def("Clear", &ChannelDisplaySettingsStruct::Clear);

  py::enum_<CacheType>(m, "CacheType", py::module_local())
      .value("None", CacheType::None)
      .value("Standard", CacheType::Standard)
      .export_values();

  py::class_<libCZI::ISubBlockCache::PruneOptions>(m, "PruneOptions",
                                                   py::module_local())
      .def(py::init<>())
      .def_readwrite("maxMemoryUsage",
                     &libCZI::ISubBlockCache::PruneOptions::maxMemoryUsage)
      .def_readwrite("maxSubBlockCount",
                     &libCZI::ISubBlockCache::PruneOptions::maxSubBlockCount);

  py::class_<SubBlockCacheOptions>(m, "SubBlockCacheOptions",
                                   py::module_local())
      .def(py::init<>())
      .def_readwrite("cacheOnlyCompressed",
                     &SubBlockCacheOptions::cacheOnlyCompressed)
      .def_readwrite("cacheType", &SubBlockCacheOptions::cacheType)
      .def_readwrite("pruneOptions", &SubBlockCacheOptions::pruneOptions)
      .def("Clear", &SubBlockCacheOptions::Clear);

  py::class_<SubBlockCacheInfo>(m, "SubBlockCacheInfo", py::module_local())
      .def(py::init<>())
      .def_readwrite("elements_count", &SubBlockCacheInfo::elementsCount)
      .def_readwrite("memory_usage", &SubBlockCacheInfo::memoryUsage);

  py::class_<ReaderOptions>(m, "ReaderOptions", py::module_local())
      .def(py::init<>())
      .def_readwrite("enableMaskAwareness", &ReaderOptions::enableMaskAwareness)
      .def_readwrite("enableVisibilityCheckOptimization",
                     &ReaderOptions::enableVisibilityCheckOptimization)
      .def_readwrite("laxSubblockCoordinateChecks",
                     &ReaderOptions::laxSubblockCoordinateChecks)
      .def_readwrite("ignoreSizeMForPyramidSubblocks",
                     &ReaderOptions::ignoreSizeMForPyramidSubblocks)
      .def("Clear", &ReaderOptions::Clear);

  // PyCZIMetadataBuilder bindings (Python-facing wrapper)
  py::class_<PyCZIMetadataBuilder, std::shared_ptr<PyCZIMetadataBuilder>>(
      m, "CziMetadataBuilder", py::module_local())
      .def("get_xml", &PyCZIMetadataBuilder::GetXml,
           py::arg("prettify") = false,
           "Get the current XML representation of the metadata")
      .def("set_xml", &PyCZIMetadataBuilder::SetXml, py::arg("xml_string"),
           "Replace the entire metadata XML content")
      .def(
          "set_general_document_info",
          [](PyCZIMetadataBuilder &self,
             const std::optional<std::wstring> &name,
             const std::optional<std::wstring> &title,
             const std::optional<std::wstring> &userName,
             const std::optional<std::wstring> &description,
             const std::optional<std::wstring> &comment,
             const std::optional<std::wstring> &keywords,
             const std::optional<double> &rating) {
            libCZI::GeneralDocumentInfo info;
            if (name)
              info.SetName(*name);
            if (title)
              info.SetTitle(*title);
            if (userName)
              info.SetUserName(*userName);
            if (description)
              info.SetDescription(*description);
            if (comment)
              info.SetComment(*comment);
            if (keywords)
              info.SetKeywords(*keywords);
            if (rating)
              info.SetRating(*rating);
            self.SetGeneralDocumentInfo(info);
          },
          py::arg("name") = py::none(), py::arg("title") = py::none(),
          py::arg("user_name") = py::none(),
          py::arg("description") = py::none(), py::arg("comment") = py::none(),
          py::arg("keywords") = py::none(), py::arg("rating") = py::none(),
          "Set general document information fields")
      .def(
          "set_scaling_info",
          [](PyCZIMetadataBuilder &self, const std::optional<double> &scale_x,
             const std::optional<double> &scale_y,
             const std::optional<double> &scale_z) {
            libCZI::ScalingInfo info;
            if (scale_x)
              info.scaleX = *scale_x;
            if (scale_y)
              info.scaleY = *scale_y;
            if (scale_z)
              info.scaleZ = *scale_z;
            self.SetScalingInfo(info);
          },
          py::arg("scale_x") = py::none(), py::arg("scale_y") = py::none(),
          py::arg("scale_z") = py::none(), "Set scaling information")
      .def("set_custom_key_value", &PyCZIMetadataBuilder::SetCustomKeyValue,
           py::arg("key"), py::arg("value"),
           "Set or add a custom key-value pair")
      .def("set_display_settings", &PyCZIMetadataBuilder::SetDisplaySettings,
           py::arg("display_settings"),
           "Set display settings for specified channels.\n"
           "The mapping key is the channel index (e.g. 0, 1, ...).\n"
           "For each ChannelDisplaySettingsStructWithNameAndDescription:\n"
           "  - description is written to <Description>.\n"
           "  - name is written to <Name>.\n"
           "  - isEnabled controls <IsSelected> if that element exists for "
           "the channel:\n"
           "      isEnabled=True  -> <IsSelected>true</IsSelected>\n"
           "      isEnabled=False -> <IsSelected>false</IsSelected>\n"
           "    If <IsSelected> is not present in the original metadata, it "
           "is left absent.")
      .def("can_commit", &PyCZIMetadataBuilder::CanCommit,
           "Check if the builder can commit changes to the file")
      .def("commit", &PyCZIMetadataBuilder::Commit,
           "Commit all pending changes to the CZI file");

  // ChannelDisplaySettingsStructWithDescription bindings
  py::class_<ChannelDisplaySettingsStructWithNameAndDescription>(
      m, "ChannelDisplaySettingsStructWithNameAndDescription",
      py::module_local())
      .def(py::init<>())
      .def_readwrite(
          "isEnabled",
          &ChannelDisplaySettingsStructWithNameAndDescription::isEnabled)
      .def_readwrite(
          "tintingMode",
          &ChannelDisplaySettingsStructWithNameAndDescription::tintingMode)
      .def_readwrite(
          "tintingColor",
          &ChannelDisplaySettingsStructWithNameAndDescription::tintingColor)
      .def_readwrite(
          "blackPoint",
          &ChannelDisplaySettingsStructWithNameAndDescription::blackPoint)
      .def_readwrite(
          "whitePoint",
          &ChannelDisplaySettingsStructWithNameAndDescription::whitePoint)
      .def_readwrite(
          "description",
          &ChannelDisplaySettingsStructWithNameAndDescription::description)
      .def_readwrite("name",
                     &ChannelDisplaySettingsStructWithNameAndDescription::name)
      .def("Clear", &ChannelDisplaySettingsStructWithNameAndDescription::Clear);

  // CZIeditAPI bindings
  py::class_<CZIeditAPI>(m, "czi_editor", py::module_local())
      .def(py::init<const std::wstring &>(), py::arg("file_name"),
           "Open an existing CZI file for in-place metadata editing")
      .def("close", &CZIeditAPI::Close, "Close the opened CZI file")
      .def("is_open", &CZIeditAPI::IsOpen, "Check if the file is open")
      .def("read_metadata_xml", &CZIeditAPI::ReadMetadataXml,
           "Read the current metadata XML from the file")
      .def(
          "read_general_document_info",
          [](const CZIeditAPI &self) -> py::dict {
            auto info = self.ReadGeneralDocumentInfo();
            py::dict result;
            if (info.name_valid)
              result["name"] = info.name;
            if (info.title_valid)
              result["title"] = info.title;
            if (info.userName_valid)
              result["user_name"] = info.userName;
            if (info.description_valid)
              result["description"] = info.description;
            if (info.comment_valid)
              result["comment"] = info.comment;
            if (info.keywords_valid)
              result["keywords"] = info.keywords;
            if (info.rating_valid)
              result["rating"] = info.rating;
            if (info.creationDateTime_valid)
              result["creation_date_time"] = info.creationDateTime;
            return result;
          },
          "Read current general document info as a dictionary")
      .def(
          "read_scaling_info",
          [](const CZIeditAPI &self) -> py::dict {
            const auto si = self.ReadScalingInfo();
            py::dict result;
            result["scale_x"] = si.scaleX;
            result["scale_y"] = si.scaleY;
            result["scale_z"] = si.scaleZ;
            return result;
          },
          "Read current scaling information")
      .def("read_display_settings", &CZIeditAPI::ReadDisplaySettings,
           "Read current display settings for all channels as a dictionary "
           "mapping channel index to settings")
      .def("read_custom_key_value", &CZIeditAPI::ReadCustomKeyValue,
           py::arg("key"),
           "Read a custom key-value by key. Returns a CustomValueVariant.")
      .def("create_metadata_builder", &CZIeditAPI::CreateMetadataBuilder,
           "Create a metadata builder initialized from the file's current "
           "metadata");

  // perform one-time-initialization of libCZI
  OneTimeSiteInitialization();
}
