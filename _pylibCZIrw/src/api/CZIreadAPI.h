#pragma once

#include "PImage.h"
#include "SubBlockCache.h"
#include "inc_libCzi.h"
#include <iostream>
#include <optional>

/// Class used to represent a CZI reader object in pylibCZIrw.
/// It gathers the libCZI features needed for reading in the pylibCZIrw project.
/// CZIrwAPI will be exposed to python via pybind11 as a czi class.
class CZIreadAPI {

private:
  std::shared_ptr<libCZI::ICZIReader>
      spReader; ///< The pointer to the spReader.
  std::shared_ptr<libCZI::ISingleChannelScalingTileAccessor>
      spAccessor; ///< The pointer to the spAccessor object.
  std::shared_ptr<libCZI::ISubBlockCache>
      spSubBlockCache; ///< The pointer to the subblock cache object, may be
                       ///< null (in which case no caching is done)
  SubBlockCacheOptions
      subBlockCacheOptions; ///< Options for using the subblock cache

public:
  /// Constructor which constructs a CZIrwAPI object from the given wstring.
  /// Creates a spReader and spAccessor (SingleChannelTilingScalingAccessor) for
  /// the czi document pointed by the given filepath.
  /// \param  fileName            Filename of the file.
  CZIreadAPI(const std::wstring &fileName);

  /// Constructor which constructs a CZIrwAPI object, allowing to specify a
  /// stream class name. Possible stream class names are: "standard" for reading
  /// files in the file system, and "curl" for reading files from a web server.
  /// "curl" is mapped to the libCZI-streams class "curl_http_inputstream".
  ///
  /// \param  stream_class_name   A string identifying the stream class to be
  /// used (note that this string is *not* the same string the libCZI-streams
  ///                             factory uses. There is a mapping between the
  ///                             two strings done in the CZIrwAPI constructor.
  /// \param  fileName            Filename (or URI) of the file (the
  /// interpretation of the string is stream class specific).
  CZIreadAPI(const std::string &stream_class_name,
             const std::wstring &fileName);

  /// Constructor which constructs a CZIrwAPI object from the given wstring.
  /// Creates a spReader and spAccessor (SingleChannelTilingScalingAccessor) for
  /// the czi document pointed by the given filepath.
  /// This constructor allows defining a subblock cache to be used for
  /// performance optimization. \param  fileName                Filename of the
  /// file. \param  subBlockCacheOptions    Options for initializing the
  /// subblock cache.
  CZIreadAPI(const std::wstring &fileName,
             const SubBlockCacheOptions &subBlockCacheOptions);

  /// Constructor which constructs a CZIrwAPI object, allowing to specify a
  /// stream class name. Possible stream class names are: "standard" for reading
  /// files in the file system, and "curl" for reading files from a web server.
  /// "curl" is mapped to the libCZI-streams class "curl_http_inputstream". This
  /// constructor allows defining a subblock cache to be used for performance
  /// optimization.
  ///
  /// \param  stream_class_name       A string identifying the stream class to
  /// be used (note that this string is *not* the same string the libCZI-streams
  ///                                 factory uses. There is a mapping between
  ///                                 the two strings done in the CZIrwAPI
  ///                                 constructor.
  /// \param  fileName                Filename (or URI) of the file (the
  /// interpretation of the string is stream class specific). \param
  /// subBlockCacheOptions    Options for initializing the subblock cache.
  CZIreadAPI(const std::string &stream_class_name, const std::wstring &fileName,
             const SubBlockCacheOptions &subBlockCacheOptions);

  /// Close the Opened czi document
  void close() { this->spReader->Close(); }

  /// Returns raw xml metadata from the czi document.
  std::string GetXmlMetadata();

  /// Returns SubBlockStatistics about the czi document
  libCZI::SubBlockStatistics GetSubBlockStats();

  /// Returns Pixeltype of the specified channel index
  libCZI::PixelType GetChannelPixelType(int channelIdx);

  /// Returns the size of the given dimension in the czi document.
  size_t GetDimensionSize(libCZI::DimensionIndex DimIndex);

  /// <summary>
  /// Returns the bitmap (as a PImage object)
  /// </summary>
  /// <param name="roi">The ROI</param>
  /// <param name="bgColor">The background color</param>
  /// <param name="zoom">The zoom factor</param>
  /// <param name="coordinateString">The plane coordinate</param>
  /// <param name="SceneIndexes">String specifying </param>
  /// <returns>ptr to the the bitmap stored as a PImage object</returns>
  std::unique_ptr<PImage> GetSingleChannelScalingTileAccessorData(
      libCZI::PixelType pixeltype, libCZI::IntRect roi,
      libCZI::RgbFloatColor bgColor, float zoom,
      const std::string &coordinateString, const std::wstring &SceneIndexes);

  /// Returns information about the current state of the subblock cache. If
  /// caching is not active, the returned struct will contain zeros.
  /// <returns>A SubBlockCacheInfo struct containing the cache
  /// information.</returns>
  SubBlockCacheInfo GetCacheInfo();
};
