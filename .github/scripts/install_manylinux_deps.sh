#!/usr/bin/env bash
set -euo pipefail

yum install -y glibc-static perl-IPC-Cmd curl ca-certificates

if yum list available eigen3-devel >/dev/null 2>&1; then
	yum install -y eigen3-devel
	exit 0
fi

echo "eigen3-devel is unavailable; installing pinned Eigen headers."

eigen_version="3.4.0"
eigen_commit="3147391d946bb4b6c68edd901f2add6ac1f31f8c"
eigen_prefix="/opt/eigen3"
eigen_workdir="/tmp/eigen3-install"
eigen_archive="${eigen_workdir}/eigen.tar.gz"

rm -rf "${eigen_workdir}"
mkdir -p "${eigen_workdir}" "${eigen_prefix}/include/eigen3" "${eigen_prefix}/share/eigen3/cmake"

downloaded_eigen=0
for eigen_url in \
	"https://github.com/eigen-mirror/eigen/archive/refs/tags/${eigen_version}.tar.gz" \
	"https://gitlab.com/libeigen/eigen/-/archive/${eigen_commit}/eigen-${eigen_commit}.tar.gz"; do
	rm -f "${eigen_archive}"
	if curl --fail --location --retry 5 --retry-delay 5 --connect-timeout 30 \
		"${eigen_url}" --output "${eigen_archive}"; then
		downloaded_eigen=1
		break
	fi
done

if [[ "${downloaded_eigen}" != "1" || ! -s "${eigen_archive}" ]]; then
	echo "Failed to download Eigen ${eigen_version}." >&2
	exit 1
fi

tar -xzf "${eigen_archive}" -C "${eigen_workdir}" --strip-components=1
cp -R "${eigen_workdir}/Eigen" "${eigen_prefix}/include/eigen3/"
cp -R "${eigen_workdir}/unsupported" "${eigen_prefix}/include/eigen3/"

cat >"${eigen_prefix}/share/eigen3/cmake/Eigen3Config.cmake" <<'EOF'
get_filename_component(_eigen3_config_dir "${CMAKE_CURRENT_LIST_FILE}" PATH)
get_filename_component(_eigen3_prefix "${_eigen3_config_dir}/../../.." ABSOLUTE)
set(EIGEN3_INCLUDE_DIR "${_eigen3_prefix}/include/eigen3")

if(NOT TARGET Eigen3::Eigen)
  add_library(Eigen3::Eigen INTERFACE IMPORTED)
  set_target_properties(Eigen3::Eigen PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${EIGEN3_INCLUDE_DIR}")
endif()

set(Eigen3_FOUND TRUE)
EOF

cat >"${eigen_prefix}/share/eigen3/cmake/Eigen3ConfigVersion.cmake" <<EOF
set(PACKAGE_VERSION "${eigen_version}")

if(PACKAGE_FIND_VERSION VERSION_GREATER PACKAGE_VERSION)
  set(PACKAGE_VERSION_COMPATIBLE FALSE)
else()
  set(PACKAGE_VERSION_COMPATIBLE TRUE)
  if(PACKAGE_FIND_VERSION STREQUAL PACKAGE_VERSION)
    set(PACKAGE_VERSION_EXACT TRUE)
  endif()
endif()
EOF
