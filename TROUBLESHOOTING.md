**Here we document some of the issues we have encountered, so future development can be quicker**

**Table of Contents**
- [Visual Studio CMake Error](#visual-studio-cmake-error)
- [Libs folder empty](#libs-folder-empty)
- [Latest version of libczi isn't present](#latest-version-of-libczi-isnt-present)
- [Pip install .all sticks](#Pip-install-all-sticks)
- [Pip install or test fails with python version issue](#Pip-install-or-test-fails-with-python-version-issue)
- [Pip install succeeds but tests fail to find interface](#Pip-install-succeeds-but-tests-fail-to-find-interface)
- [Unable to add new interpreter to RMS_PyPi_pylibCZIrw](#Unable-to-add-new-interpreter-to-RMS_PyPi_pylibCZIrw)
- [Libs Submodule keeps showing a change](#Libs-Submodule-keeps-showing-a-change)

## Visual Studio CMake Error
Visual studio build shows CMAKE_C_COMPILER and CMAKE_CXX_COMPILER error.
This is because C/C++ tools for visual studio aren't installed.
Use Visual Studio installer to modify current setup.

## Libs folder empty
The library dependencies are linked using git submodules which have not been pulled.
Use ``` git pull --recurse-submodules ```

## Latest version of libczi isn't present
The libczi library is a submodules which where the latest need to be referenced.
Use ``` git submodule update --remote ``` and keep the latest hash from libczi.

## Pip install .all sticks
Pip version requires ``` --use-feature=in-tree-build ```
run ``` pip install --use-feature=in-tree-build .[all]```

## Pip install or test fails with python version issue
The virtual environment has some python version dependency, so change to that version of python using ``` conda install python==<version_number> ```

## Pip install succeeds but tests fail to find interface
If the python stub is created as expected, but python test run fails to find new interface, there is an issue with something broken in git
Open git bash on the repo and run ``` git clean -fdx ```

## Unable to add new interpreter to RMS_PyPi_pylibCZIrw
If adding python interpreter using 'Add new interpreter -> Add local interpreter' fails, create a new conda environment using a new PyCharm window.  
Then on open of the pylibCZIrw project, point the base python interpreter as the python.exe in the conda env  
Ex: `%USERPROFILE%\.conda\envs\pylibczi310\python.exe`

## Libs Submodule keeps showing a change
If the libs folder keeps show changes, this could be due to an older version of a submodule being used.
To clean this, run the commands below. The first command completely "unbinds" all submodules, the second then makes a fresh checkout of them.
git submodule deinit -f .
git submodule update --init