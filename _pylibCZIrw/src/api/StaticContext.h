#pragma once

#include "inc_libCzi.h"
#include <string>

/// This class is intended to provide global and static context information for
/// the python-side of pylibCZIrw.
class StaticContext {
private:
  std::string override_curl_ca_info_filename_;

protected:
  /// Initializes this object. This method must only be called once, and before
  /// any calls to other methods of the class.
  void Initialize();

  friend void OneTimeSiteInitialization();

public:
  /// Gets stream class name (as used with libCZI) for the reader class "curl"
  /// (as used with the python side).
  ///
  /// \returns    The libczi-stream-class-name for the python reader class
  /// "curl".
  const std::string &GetStreamClassNameForCurlReader() const;

  /// Sets default properties for the libCZI-reader initialization. This method
  /// will inspect the field 'class_name' of the create_info parameter and set
  /// the default properties for the reader class identified by this field.
  ///
  /// \param [in,out] create_info The options object for creating a
  /// libczi-stream-class.
  void SetDefaultPropertiesForReader(
      libCZI::StreamsFactory::CreateStreamInfo &create_info) const;

private:
  void TryFigureOutCurlCaInfoPath();
};

extern StaticContext kStaticContext;
