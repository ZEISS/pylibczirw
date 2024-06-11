#include "StaticContext.h"
#include <filesystem>

#include "inc_libCzi.h"

using namespace std;
using namespace libCZI;

StaticContext kStaticContext;

const std::string &StaticContext::GetStreamClassNameForCurlReader() const {
  static const string kStreamClassNameForCurlReader = "curl_http_inputstream";
  return kStreamClassNameForCurlReader;
}

void StaticContext::Initialize() {
  for (int i = 0; i < StreamsFactory::GetStreamClassesCount(); i++) {
    StreamsFactory::StreamClassInfo stream_info;
    if (StreamsFactory::GetStreamInfoForClass(i, stream_info) &&
        stream_info.class_name == this->GetStreamClassNameForCurlReader()) {
      // what we attempt to do here is something like:
      // * If libcurl is using openSSL, then for establishing a secure
      // connection, it needs to know where the CA info is located.
      // * "Common practice" seems to be that the location of this file is a
      // build-time configuration for libcurl or openSSL.
      // * However, when using a static build of libcurl/openSSL, this location
      // might be unknown at build-time (or - when building
      //    on another system than where the library will be used - the location
      //    might be wrong).
      // * If this is the case, we will try to figure out the location of the CA
      // info file at run-time, and set the location
      //    (with the property kStreamClassInfoProperty_CurlHttp_CaInfo) before
      //    creating the stream.
      if (stream_info.get_property) {
        // here we query the curl-based stream class for their default value for
        // the CA info file
        auto property = stream_info.get_property(
            StreamsFactory::kStreamClassInfoProperty_CurlHttp_CaInfo);
        if (property.GetType() == StreamsFactory::Property::Type::String) {
          // This property will not be available if openSSL is not used by
          // libcurl, or if libcurl is not built with https-support. So, we only
          // want to check whether the file exists if the property is available
          // (and not empty). Otherwise, we assume that "nothing needs to be
          // done".
          const auto ca_info = property.GetAsStringOrThrow();
          if (!ca_info.empty()) {
            try {
              const filesystem::path path(ca_info);

              // Check if file exists and is not a directory
              if (!(filesystem::exists(path) &&
                    filesystem::is_regular_file(path))) {
                // ok, if the file libcurl reported it would use as CA info file
                // does not exist, we will try to figure out
                //  where the CA info file is located on the system (at
                //  run-time), and set the location accordingly.
                this->TryFigureOutCurlCaInfoPath();
              }
            } catch (...) {
              // ignore any exceptions here, we will just assume that the file
              // does not exist
            }
          }

          break;
        }
      }
    }
  }
}

void StaticContext::SetDefaultPropertiesForReader(
    libCZI::StreamsFactory::CreateStreamInfo &create_info) const {
  if (create_info.class_name == this->GetStreamClassNameForCurlReader()) {
    // if we figured out that we need to override the default location of the CA
    // info file, we will set the property here accordingly
    if (!this->override_curl_ca_info_filename_.empty()) {
      create_info
          .property_bag[StreamsFactory::StreamProperties::kCurlHttp_CaInfo] =
          StreamsFactory::Property(this->override_curl_ca_info_filename_);
    }

    create_info.property_bag
        [StreamsFactory::StreamProperties::kCurlHttp_FollowLocation] =
        StreamsFactory::Property(true);
  }
}

void StaticContext::TryFigureOutCurlCaInfoPath() {
  // Check common location for Unix-based systems
  static const char *kCandidate_Paths[] = {
      "/etc/ssl/certs/ca-certificates.crt",     //( Ubuntu, Debian, Arch Linux)
      "/etc/pki/tls/certs/ca-bundle.crt",       // (Fedora, RHEL, CentOS)
      "/usr/local/share/certs/ca-root-nss.crt", // (FreeBSD)
      "/etc/ssl/cert.pem"                       // (macOS)
  };

  // let's check those paths in order, and use the first one that exists and is
  // a regular file
  for (const char *candidate_path : kCandidate_Paths) {
    try {
      if (filesystem::exists(candidate_path) &&
          filesystem::is_regular_file(candidate_path)) {
        this->override_curl_ca_info_filename_ = candidate_path;
        break;
      }
    } catch (...) {
      // ignore any exceptions here, we will just assume that the file does not
      // exist
    }
  }

  // TODO(JBL):
  // * we might want to check the environment variable CURL_CAINFO here, it
  // seems that this variable can
  //    be used to override the default location of the CA info file with curl
  //    (not libcurl!) itself
  // * should necessity arise, I reckon we would have the option to set
  // CURLOPT_CAINFO_BLOB (via kCurlHttp_CaInfoBlob),
  //    i.e. set the CA info as a blob of data instead of directing to a file.
  //    We would then have to embed the PEM-encoded data in the pylibCZIrw
  //    binary (e.g. downloaded from here https://curl.se/docs/caextract.html).
}