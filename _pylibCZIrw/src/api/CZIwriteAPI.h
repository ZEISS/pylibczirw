#pragma once

#include "PImage.h"
#include "inc_libCzi.h"
#include <iostream>
#include <optional>

/// This enum specifies the "tinting-mode" - how the channel is false-colored.
/// \remark
/// Plan is to add a property "GetTintingMode", currently we only implement
/// "Color" and "None", so this information is conveniently contained in the
/// method "TryGetTintingColorRgb8".
enum class TintingModeEnum : std::uint8_t {
  None = 0, ///< None - which gives the "original color", ie. in case of RGB the
            ///< RGB-value is directly used, in case of grayscale we get a gray
            ///< pixel.
  Color = 1, ///< The pixel value is multiplied with the tinting-color.
  LookUpTableExplicit = 2, ///< (NOT YET IMPLEMENTED) There is an explicit
                           ///< look-up-table specified.
  LookUpTableWellKnown =
      3 ///< (NOT YET IMPLEMENTED) We are using a "well-known" look-up-table,
        ///< and it is identified by its name (which is a string).
};

/// This POD ("plain-old-data") structure is intended to capture all information
/// found inside an IChannelDisplaySetting-object. It allows for easy
/// modification of the information.
struct ChannelDisplaySettingsStruct {
  /// A boolean indicating whether the corresponding channel is 'active' in the
  /// multi-channel-composition.
  bool isEnabled;

  /// The tinting mode.
  TintingModeEnum tintingMode;

  /// The tinting color (only valid if tinting mode == Color).
  libCZI::Rgb8Color tintingColor;

  /// The (normalized) black point value.
  float blackPoint;

  /// The (normalized) white point value.
  float whitePoint;

  /// Sets the structure to a defined standard value - not enabled, no tinting,
  /// linear gradation-curve and black-point to zero and white-point to one.
  LIBCZI_API void Clear() {
    this->isEnabled = false;
    this->tintingMode = TintingModeEnum::None;
    this->blackPoint = 0;
    this->whitePoint = 1;
  }
};

/// Class used to represent a CZI writer object in pylibCZIrw.
/// It gathers the libCZI features for writing needed in the pylibCZI project.
/// CZIrwAPI will be exposed to python via pybind11 as a czi class.
class CZIwriteAPI {

private:
  std::shared_ptr<libCZI::ICziWriter>
      spWriter_; ///< The pointer to the spWriter.
  libCZI::Utils::CompressionOption defaultCompressionOptions_;

public:
  /// Constructor which constructs a CZIwriteAPI object from the given wstring.
  /// Creates a spWriter for the czi document pointed by the given filepath.
  /// This constructor will use default options for compression, which is "no
  /// compression, uncompressed".
  ///
  /// \param  fileName    Filename of the CZI-file to be created.
  CZIwriteAPI(const std::wstring &fileName);

  /// Constructor creating a CZI-writer object for the specified filename. The
  /// 'compressionOptions' argument gives a string representation of the
  /// compression options to be used as default for this instance.
  ///
  /// \param  fileName            Filename of the file.
  /// \param  compressionOptions  The compression-options in string
  /// representation.
  CZIwriteAPI(const std::wstring &fileName,
              const std::string &compressionOptions);

  /// Close the Opened czi writer.
  void close() { this->spWriter_->Close(); }

  /// Writes metadata to the created czi document.
  ///
  /// \param  documentTitle       The title of the czi document.
  /// \param  scaleX              The length of a pixel in x-direction in the
  /// unit meters. If unknown/invalid, this value is
  /// numeric_limits<double>::quiet_NaN(). \param  scaleY              The
  /// length of a pixel in y-direction in the unit meters. If unknown/invalid,
  /// this value is numeric_limits<double>::quiet_NaN(). \param  scaleZ The
  /// length of a pixel in z-direction in the unit meters. If unknown/invalid,
  /// this value is numeric_limits<double>::quiet_NaN(). \param  channelNames A
  /// dictionary of channels, where key is the channel index and value is the
  /// corresponding channel name. \param  customAttributes    A dictionary of
  /// custom attributes, where the key is the name of the attribute and value is
  /// the corresponding custom attribute value. \param  displaySettings     A
  /// dictionary of display settings, where key is channel number and value is
  /// the corresponding display setting.
  void WriteMetadata(
      const std::wstring &documentTitle, std::optional<double> scaleX,
      std::optional<double> scaleY, std::optional<double> scaleZ,
      const std::map<int, std::string> &channelNames,
      const std::map<std::string, const libCZI::CustomValueVariant>
          &customAttributes,
      const std::map<int, const ChannelDisplaySettingsStruct> &displaySettings);

  /// Add the specified bitmap plane to the czi document at the specified
  /// coordinates.
  ///
  /// \param  coordinateString    The coordinate in string representation.
  /// \param  plane               The bitmap to add.
  /// \param  x                   The x pixel coordinate.
  /// \param  y                   The y pixel coordinate.
  /// \param  m                   The m index.
  ///
  /// \returns    True if it succeeds, false if it fails.
  bool AddTile(const std::string &coordinateString, const PImage *plane, int x,
               int y, int m, const std::string &retiling_id);

  /// Add the specified bitmap plane to the czi document at the specified
  /// coordinates. This method allows to override the compression-options. If
  /// the string 'compressionOptions' is empty, then the default
  /// compression-options are used.
  ///
  /// \param  coordinateString    The coordinate in string representation.
  /// \param  plane               The bitmap to add.
  /// \param  x                   The x pixel coordinate.
  /// \param  y                   The y pixel coordinate.
  /// \param  m                   The m index.
  /// \param  compressionOptions  The compression-options in string
  /// representation.
  ///
  /// \returns    True if it succeeds, false if it fails.
  bool AddTileEx(const std::string &coordinateString, const PImage *plane,
                 int x, int y, int m, const std::string &compressionOptions,
                 const std::string &retiling_id);

private:
  static std::string CreateSubBlockMetadataXml(const std::string &retiling_id);

  static void
  AddSubBlock(const libCZI::CDimCoordinate &coord, const PImage *subblock,
              const libCZI::Utils::CompressionOption &compressionOptions,
              libCZI::ICziWriter *writer, int x, int y, int m,
              const std::string &sbmetadata);
};