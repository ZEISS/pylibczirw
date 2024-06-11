"""Holds all relevant information for packaging and publishing to PyPI."""

import os
import platform
import re
import subprocess
import sys
from distutils.version import LooseVersion
from pathlib import Path
from typing import List

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

# DO NOT CHANGE
# THIS IS UPDATED AUTOMATICALLY THROUGH PYTHON-SEMANTIC-RELEASE
VERSION = "0.0.0"

with open("INFO.md") as info_file:
    info = info_file.read()

with open("CHANGELOG.md") as changelog_file:
    changelog = changelog_file.read()

# List any runtime requirements here
requirements = ["numpy", "cmake", "xmltodict", "validators"]


class CMakeExtension(Extension):
    def __init__(self, name: str, sourcedir: str = ""):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    def run(self) -> None:
        try:
            out = subprocess.check_output(["cmake", "--version"])
        except OSError:
            raise RuntimeError(
                "CMake must be installed and available at PATH ({0}) to build the following extensions: {1}".format(
                    os.environ.get("PATH"), ", ".join(e.name for e in self.extensions)
                )
            )
        cmake_version = LooseVersion(
            re.search(r"version\s*([\d.]+)", out.decode()).group(1)  # type: ignore[union-attr]
        )
        if platform.system() == "Windows":
            cmake_version = LooseVersion(
                re.search(r"version\s*([\d.]+)", out.decode()).group(1)  # type: ignore[union-attr]
            )
            if cmake_version < "3.1.0":
                raise RuntimeError("CMake >= 3.1.0 is required on Windows")

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):  # type: ignore[no-untyped-def]
        path_var = os.environ["PATH"]
        path_var = str(Path(sys.executable).parent) + ":" + path_var
        env = dict(os.environ.copy(), PATH=path_var)
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        cmake_args = [
            "-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=" + extdir,
            "-DPYTHON_EXECUTABLE=" + sys.executable,  # used for pybind11
        ]

        cfg = "Debug" if self.debug else "Release"
        build_args = ["--config", cfg]

        cmake_args += ["-DLIBCZI_BUILD_DYNLIB=OFF"]  # we don't need the dynamic library
        cmake_args += ["-DLIBCZI_BUILD_UNITTESTS=OFF"]  # also, we don't need the unit tests
        cmake_args += ["-DLIBCZI_BUILD_CURL_BASED_STREAM=ON"]  # and we want a version which is "libcurl-enabled"

        cmake_args += ["-DPYLIBCZIRW_VERSION=" + VERSION]  # Have the same version as the Python package

        if platform.system() == "Windows":
            cmake_args += ["-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}".format(cfg.upper(), extdir)]
            cmake_args += ["-DVCPKG_TARGET_TRIPLET=x64-windows-static"]
            vcpkg_installation_root = os.environ.get("VCPKG_INSTALLATION_ROOT", "C:\\vcpkg")
            if os.path.exists(vcpkg_installation_root):
                check_and_install_packages(
                    packages=["curl[ssl]", "eigen3"],
                    triplet="x64-windows-static",
                    vcpkg_root=vcpkg_installation_root,
                )
                cmake_args += [
                    "-DLIBCZI_BUILD_PREFER_EXTERNALPACKAGE_LIBCURL=ON"
                ]  # instruct to use the package-manager provided libcurl
                cmake_args += [
                    "-DLIBCZI_BUILD_PREFER_EXTERNALPACKAGE_EIGEN3=ON"
                ]  # instruct to use the package-manager provided eigen3
                cmake_args += [
                    "-DCMAKE_TOOLCHAIN_FILE="
                    + os.path.join(
                        vcpkg_installation_root,
                        "scripts",
                        "buildsystems",
                        "vcpkg.cmake",
                    )
                ]
            else:
                raise RuntimeError("vcpkg installation not found, please define your VCPKG_INSTALLATION_ROOT path")

            build_args += ["--", "/m"]
        else:  # Linux
            # Get the value of the environment variable
            manylinux_env_variable = os.environ.get("AUDITWHEEL_PLAT", "").lower()
            if "manylinux" in manylinux_env_variable:
                # When running in manylinux-container, we want to build openssl ourselves and link it statically.
                # On the CI/CD-server, we set the variable "BUILDWHEEL_STATIC_OPENSSL" in order to instruct running a
                # local build of openSSL (and instruct the libCZI-build to use it)
                print("Building static openssl and zlib dependencies locally.")
                subprocess.run(
                    "cd /tmp && "
                    "git clone --branch v1.3 https://github.com/madler/zlib.git && "
                    "cd zlib && "
                    "CFLAGS=-fPIC ./configure --static && "
                    "make -j2 && "
                    "make install",
                    shell=True,
                )
                subprocess.run(
                    "cd /tmp && "
                    "git clone --branch openssl-3.2.0 https://github.com/openssl/openssl.git && "
                    "cd openssl && "
                    "mkdir build && "
                    "./config no-shared -static zlib -fPIC -L/usr/lib no-docs no-tests && "
                    "make -j2",
                    shell=True,
                )
                cmake_args += [
                    "-DOPENSSL_USE_STATIC_LIBS=TRUE"
                ]  # instruct to use the static version of libssl and libcrypto
                cmake_args += ["-DOPENSSL_ROOT_DIR=/tmp/openssl"]
                cmake_args += ["-DZLIB_USE_STATIC_LIBS=TRUE"]

            # Test install curl using vcpkg on linux
            print("env root is: " + os.environ.get("VCPKG_INSTALLATION_ROOT", ""))
            vcpkg_installation_root = os.environ.get("VCPKG_INSTALLATION_ROOT", r"/usr/local/share/vcpkg")
            print("set env root is: " + vcpkg_installation_root)
            test = os.path.exists(vcpkg_installation_root)
            print(f"path exists is: {test} ")
            if os.path.exists(vcpkg_installation_root):
                check_and_install_packages(
                    packages=["curl[ssl]"],
                    triplet="x64-linux",
                    vcpkg_root=vcpkg_installation_root,
                )
                cmake_args += [
                    "-DCMAKE_TOOLCHAIN_FILE="
                    + os.path.join(
                        vcpkg_installation_root,
                        "scripts",
                        "buildsystems",
                        "vcpkg.cmake",
                    )
                ]
                cmake_args += [
                    "-DLIBCZI_BUILD_PREFER_EXTERNALPACKAGE_LIBCURL=ON"
                ]  # if curl is available via vcpkg, then instruct to use the package-manager provided libcurl
            else:
                print("Pacakge manager missing, attempting to build libcurl dependency locally.")
                cmake_args += [
                    "-DLIBCZI_BUILD_PREFER_EXTERNALPACKAGE_LIBCURL=OFF"
                ]  # otherwise, we try to build libcurl ourselves (note: probably requires libssl-dev to be installed)

            cmake_args += ["-DCMAKE_BUILD_TYPE=" + cfg]
            build_args += ["--", "-j2"]

        env["CXXFLAGS"] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get("CXXFLAGS", ""), self.distribution.get_version())
        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)
        if self.debug:
            print("cmake build path: " + self.build_temp)
            print("cmake compile: " + " ".join(["cmake", ext.sourcedir, cmake_args]))
        subprocess.check_call(["cmake", ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)
        if self.debug:
            print(" ".join(["cmake build:", "cmake", "--build", ".", "--target", "_pylibCZIrw", build_args]))
        subprocess.check_call(
            ["cmake", "--build", ".", "--target", "_pylibCZIrw"] + build_args,
            cwd=self.build_temp,
            env=env,
        )


def check_and_install_packages(packages: List[str], triplet: str, vcpkg_root: str) -> None:
    for package in packages:
        vcpkg_executable = os.path.join(vcpkg_root, "vcpkg")
        result = subprocess.run(
            [
                vcpkg_executable,
                "list",
                package,
                f"--triplet={triplet}",
                f"--vcpkg-root={vcpkg_root}",
            ],
            capture_output=True,
            text=True,
        )
        if package in result.stdout:
            print(f"{package} is already installed.")
        else:
            print(f"Installing {package}")
            subprocess.run(
                [
                    vcpkg_executable,
                    "install",
                    package,
                    f"--triplet={triplet}",
                    f"--vcpkg-root={vcpkg_root}",
                ]
            )
    print("Installations complete")


setup(
    name="pylibCZIrw",
    version=VERSION,
    author="Sebastian Soyer",
    author_email="sebastian.soyer@zeiss.com",
    description="A python wrapper around the libCZI C++ library with reading and writing functionality.",
    long_description="\n".join([info, changelog]),
    long_description_content_type="text/markdown",
    # See https://setuptools.pypa.io/en/latest/userguide/datafiles.html
    include_package_data=True,
    keywords="czi, imaging",
    ext_modules=[CMakeExtension("_pylibCZIrw")],
    packages=["pylibCZIrw"],
    cmdclass=dict(build_ext=CMakeBuild),
    install_requires=requirements,
    # we require at least python version 3.7
    python_requires=">=3.7,<3.12",
    license_files=["COPYING", "COPYING.LESSER", "NOTICE"],
    # Classifiers help users find your project by categorizing it.
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Scientific/Engineering :: Image Processing",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: Unix",
    ],
    zip_safe=False,
)
