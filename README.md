# pylibCZIrw
[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![REUSE status](https://api.reuse.software/badge/github.com/ZEISS/pylibczirw)](https://api.reuse.software/info/github.com/ZEISS/pylibczirw)
[![Build](https://github.com/ZEISS/pylibczirw/actions/workflows/build.yml/badge.svg?branch=main&event=push)](https://github.com/ZEISS/pylibczirw/actions/workflows/build.yml)
[![codecov](https://codecov.io/gh/ZEISS/pylibczirw/graph/badge.svg?token=JX6cZGEJ0a)](https://codecov.io/gh/ZEISS/pylibczirw)
[![GitHub Pages](https://github.com/ZEISS/pylibczirw/actions/workflows/pages.yml/badge.svg?branch=main&event=push)](https://github.com/ZEISS/pylibczirw/actions/workflows/pages.yml)
[![PyPI version](https://badge.fury.io/py/pylibCZIrw.svg)](https://badge.fury.io/py/pylibCZIrw)  

# Contribute
test
If you intend to **use** this repo, clone the repository on your machine with ``` git clone --recurse-submodules ```.  
If you intend to also **contribute** to this repo, you are requested to copy ALL files in the hooks directory into your .git/hooks directory right after you cloned this repo!  
In addition, be sure to ideally always keep your remotes up-to-date with ``` git pull --recurse-submodules ```. Even better, you can set the configuration option _submodule.recurse_ to _true_ locally (this works for git pull since Git 2.15) with ``` git config --local submodule.recurse true ```.  This option will make Git use the _--recurse-submodules_ flag for all commands that support it (except clone). See https://git-scm.com/book/en/v2/Git-Tools-Submodules for more information.
Note: if you forget to link the submodules when cloning, you can use ``` git submodule update --init ```.  

You should ideally have [PyCharm Professional](https://www.jetbrains.com/pycharm/) and [conda](https://docs.conda.io/en/latest/miniconda.html) installed locally. You should also configure your Project interpreter as a conda environment to have all required packages installed, i.e.  
1. Create a fresh conda environment via `conda create -p <some-path\PyPI\pylibCZIrw> python` and activate it with `conda activate <environment_name>`  
   Note: Alternatively, when opening the project the first time, in the prompt to create a venv, select the python location from one of the existing conda venvs. 
2. Navigate to the repository from inside the environment.
3. Install necessary packages for building from the activated environment via `pip install .`
4. Install necessary packages for code quality analysis and testing from the activated environment via `pip install -r requirements_test.txt`  

You may then [configure all relevant 3rd party tools](https://www.jetbrains.com/help/pycharm/configuring-third-party-tools.html#), e.g. pytest, mypy, flake8 or bandit. You may want to check with the corresponding pipeline (template) for which analysis tools are run and their command line.  

This repo follows [GitFlow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow). PR/Build validation is executed on develop and main. Self-approval is allowed on develop. No policy is applied on release/ to allow for PR changes on release/ before merging to main or back to develop. See [Packaging](#packaging) and [Versioning](#versioning) for more information.  

For more information, refer to [CONTRIBUTING.md](./CONTRIBUTING.md).

# Introduction 

czi is a python wrapper around the [libCZI C++ library](https://github.com/ZEISS/libczi).

Similar endeavours have been made to wrap libCZI in python, namely:
- [pylibCZI](https://github.com/elhuhdron/pylibczi)
- [aicspylibCZI](https://github.com/AllenCellModeling/aicspylibczi)

This python package has a slightly different API with some improvements to reading but, more importantly, the addition of writing functionality.

There are also libCZI wrappers for other languages:
- [Mathematica / Wolfram Language](https://github.com/ptahmose/WolframLibraryLink_libCZI)
- [Matlab/Octave via MEXFile](https://github.com/ptahmose/MEXlibCZI)

# Building
***pylibCZIrw*** is a python library using bindings from:  
* [libCZI](https://github.com/ZEISS/libczi) and  
* pybind11  
  - a very modern and maintained project (Supports c++11/c++14 features)  
  - Bindings are done in a very few lines of code, interface with numpy array is easy.
  - No need to "learn" and code in an intermediate language (Cython).
  - Already used internally at Zeiss and very good feedbacks.

To contribute to the development (C++ or python side), you will have to compile the C++ bindings.  
This documentation provides a step-by-step guide to help you to do so.

## Requirements

- 64 bits OS and 64 bits Python (with [cmake pre-installed](https://cmake-python-distributions.readthedocs.io/en/latest/installation.html)). 
- ***python 3.XX***
- C++ compiler (***clang/gcc*** for linux, ***VS Studio*** on ***Windows***).

## Getting started

- Make sure that the libs folder contains ***libCZIrw*** and ***pybind11*** submodules (i.e. those subfolders are not empty).

## Building on Windows

Before building, install [vcpkg](https://vcpkg.io/en/getting-started.html) 
Once this is done, add the environment variable VCPKG_INSTALLATION_ROOT to be the root of the installation (repo).

### Using PyCharm (or plain Python console)
1. ``` pip install .``` from the root of the repo.  
Note: For pip 21.2 and below, use in-tree-build ``` pip install --use-feature=in-tree-build .``` from the root of the repo, or it will fail.
2. You can import this library in python and start using the bindings.  
```from pylibCZIrw import czi ```
3. Updating to a libczi version on a different fork can be done via navigating to the lib folder in the fork `cd <RepositoryDirectory>/pylibczirw/libs/libCZIrw` 
   Then adding the fork branch ``git remote add fork https://github.com/<my fork>.git``  
   Fetching the branches in the fork ``git fetch fork``  
   And finally checking out the required branch ``git checkout write_colormode_to_displaysettingsxml``
4. To test this on another project that uses pylibczi, navigate to the pylibczirw folder in python terminal of the pylibCZIrw project, and then create a wheel file using
   ```python setup.py bdist_wheel```.  
    Note: Make sure you didn't run ``pip install .`` as this will delete the wheel file after installing it.
    Then install the package in the project using ```pip install <RepositoryDirectory>\pylibczirw\dist\pylibCZIrw-3.4.0-cp310-cp310-win_amd64.whl```  
    Note: this required the python versions in both projects (and venvs) to be the same.
    Note: If this fails on cmake, the cmake inputs can be copied from the console output, and run separately for faster debugging.
5. Alternatively, in the python terminal of the project that uses pylibCZIrw, navigate to the build folder of pylibCZIrw and run ```pip install . -e```.  
   This will build and install the latest pylibCZIrw whenever it changes.  
   Note: This is slow and takes around 5 min to build. To run a faster option that doesn't auto update, run ```pip install .```. This will however need to be rerun on every change to pylibczirw.
6. Finally run ``` pip install .``` from the root of the repo CziConverter repo to install all the new dependencies.
### Using Visual Studio > 2015
1. Create an environment variable PYTHON_EXECUTABLE that contains the full path to python.exe (needed for pybind11)
2. Launch ***Visual Studio***. 
Click Open a local folder and select pylibczirw.  
It will automatically load the ***Cmake*** project.

3. To build the project right-click on the **CmakeList.txt** at the root of the repo and select Build.  
If it fails with the linking error **LNK1104 cannot open file 'python3X_d.lib'**, try to select the **"x64-Release"** config instead of **"x64-Debug"**  
(some ***Windows*** installation of python are missing the debug .dll version (dynamic libraries)).

4. If the Build was successful it should have generated a python library file **_pylibCZIrw.cp<python-version>-win_amd64.pyd** in the corresponding build folder.

5. Copy this file to the root of the repo and rename it to _pylibCZIrw.pyd

6. You can import this library in python and start using the bindings.  
```from _pylibCZIrw import czi ```

## Building on Linux

Not done yet. Only in CI/CD pipeline.

# Versioning
This [package](#packaging) follows [Semantic Versioning](https://semver.org/).  
Version bumps are carried out automatically using [Python Semantic Release](https://python-semantic-release.readthedocs.io/en/latest/index.html).  
Note: When updating major version, this must be synchronised with a [Colab template update](doc/jupyter_notebooks). 

# Packaging

A package installable through pip is generated as part of a [build](https://github.com/ZEISS/pylibczirw/actions/workflows/build.yml) and pushed to [PyPI](https://pypi.org/project/pylibczirw/).  

# Release Process
  1. Once changes have been merged to develop, a PR with updated version (see: [Versioning](#versioning)) should be created to develop.  
     The following files need to have their version updated: CZIwriteAPI.cpp, CMakeLists.txt, setup.py, INFO.md
  2. Make sure both the [API](#api)s have been updated.
  3. Next create a release branch based on develop, with naming `release/v_version (ex: release/v_3_4_0)`
  4. Create a PR to merge this into main.  
     **WARNING** Do not merge until package is tested.  
     To create a TestPyPI package, run a manual build of [TC-PyPI-pylibCZIrw](https://dev.azure.com/ZEISSgroup/RMS-DEV/_build?definitionId=5108) with the `Upload` stage selected.  
     This, when complete will produce a URI to the test package (ex: https://test.pypi.org/project/pylibCZIrw/3.4.0/).
  5. Once this test package is ready, it can be installed using the following command replacing the version with the one specified previously  
     ``` pip install -i https://test.pypi.org/simple/ pylibCZIrw==3.4.0 ```.
  6. After testing this package, merge the release branch into main, and then back into develop, if any bugfixes have been made.

# Installation
Binary wheels for all python versions that this package is considered to be compatible against (see python_requires in setup.py) as well as a source distribution are [packaged](#packaging). Installing from the source distribution requires __cmake__ to be available on PATH. 

1. ``` python -m pip install --upgrade --requirement requirements.txt``` (essentially needed for keyring and artifacts-keyring to be available)
2. ``` python -m pip install pylibCZIrw --index-url https://pkgs.dev.azure.com/ZEISSgroup/RMS-DEV/_packaging/RMS-PyPI/pypi/simple ```
3. Complete authentication (varies based on the concrete method)

# API
See [API Specification](https://zeiss.github.io/pylibczirw/)  

# Troubleshooting
See [Troubleshooting](/TROUBLESHOOTING.md)
