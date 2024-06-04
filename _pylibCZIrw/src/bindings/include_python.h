#pragma once

// on Windows, there are problems with a debug-build and linking to the Python library
// (c.f. https://stackoverflow.com/questions/59126760/building-a-python-c-extension-on-windows-with-a-debug-python-installation).
// We use the following workaround:
// - we undefine the preprocessor macro _DEBUG before including Python.h
// - and afterwards, we restore its initial value

#if defined(_WIN32) && defined(_DEBUG)
#define _DEBUG_WAS_DEFINED_BEFORE_INCLUDING_PYTHON
#undef _DEBUG
#endif

#include <Python.h>

#if defined(_DEBUG_WAS_DEFINED_BEFORE_INCLUDING_PYTHON)
#define _DEBUG
#undef _DEBUG_WAS_DEFINED_BEFORE_INCLUDING_PYTHON
#endif
