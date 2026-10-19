Native third-party license and attribution texts

The files in this directory preserve upstream or distributor-supplied text.
Different platform wheels incorporate different components; inclusion here
does not imply that every listed component is linked into every wheel.

Common native components:
  libCZI-and-vendored-components-COPYING.txt: libCZI and its modified
    pugixml and JPEG XR components, including LGPL, MIT and BSD notices.
  pybind11-LICENSE.txt: the pinned pybind11 binding headers.
  Eigen-5.0.1-vcpkg-copyright.txt: Eigen 5.0.1 notices for Windows/macOS.
  Linux-eigen3-devel-*.txt: Eigen 3.3.4 notices from its exact Linux RPM.
  zstd-1.5.7-LICENSE.txt: the BSD license option for Zstandard 1.5.7.
  zstd-1.5.7-xxhash-source-notice.txt: the unmodified xxHash header and notice
    from the Zstandard source used by the build.

Windows adds curl 8.18.0 and zlib 1.3.1, with the vcpkg-supplied notices.
Linux adds curl 8.9.1 and the RPM-supplied OpenSSL 1.1.1k, libpsl 0.20.2,
libidn2 2.2.0 and libunistring 0.9.9 notices and attribution/Unicode texts.
Linux-libidn2-AUTHORS.txt and Linux-libunistring-AUTHORS.txt retain the
AUTHORS files from their authenticated distributor source RPMs.
Linux-publicsuffix-list-MPL-2.0.txt and
Linux-publicsuffix-list-data-notice.txt cover the dated 20180723 public-suffix
data input selected by the Linux libpsl build, separately from libpsl's MIT
library license. Its source package and generator are in the review handoff.
macOS adds curl 8.21.0, OpenSSL 3.6.3, Brotli 1.2.0, nghttp2 1.70.0,
nghttp3 1.18.0, ngtcp2 1.25.0, libssh2 1.11.1, libpsl 0.23.3 and zstd 1.5.7.

The COPYING and attribution files describe the applicable alternatives and
exceptions; do not infer a single license for every file of a component.
Source availability, relinking/replacement, modifications and any required
source-distribution arrangements must also be addressed for release. This
directory is not a substitute for those obligations or a compliance sign-off.