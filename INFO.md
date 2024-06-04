# pylibCZIrw - Python wrapper for libCZI

This project provides a simple and easy-to-use Python wrapper for [libCZI](https://github.com/ZEISS/libczi) - a cross-platform C++ library intended for providing read and write access to CZI image documents.

## Important Remarks

* At the moment, **pylibCZIrw** completely abstracts away the subblock concept, both in the reading and in the writing APIs.
* The core concept of pylibCZIrw is focussing on reading and writing 2D image planes by specifying the dimension indices and its location in order to only read or write **what is really needed**.
* It allows reading data via http/https-protocol enabling cloud storage scenarios.

## Example Usage

```python
from pylibCZIrw import czi as pyczi

filepath = "myimagefile.czi"

# open the CZI document to read the
with pyczi.open_czi(filepath) as czidoc:
    # get the image dimensions as a dictionary, where the key identifies the dimension
    total_bounding_box = czidoc.total_bounding_box

    # get the total bounding box for all scenes
    total_bounding_rectangle = czidoc.total_bounding_rectangle

    # get the bounding boxes for each individual scene
    scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle

    # read a 2D image plane and optionally specify planes, zoom levels and ROIs
    image2d = czidoc.read(plane={"T": 1, "Z": 2, "C": 0}, zoom=1.0, roi=(0, 0, 50, 100))
```

The detailed usage can be inferred from this sample notebook:  

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zeiss/pylibczirw/blob/main/doc/jupyter_notebooks/pylibCZIrw_4_1_0.ipynb)  

For more detailed information (on the latest version) refer to https://zeiss.github.io/pylibczirw/ (also shipped with the source distribution of this package).  

## Installation
In case there is no wheel available for your system configuration, you can:  
- try to install from the provided source distribution  
  **For Windows**:
  - try to [keep paths short on systems with maximum path lengths](https://github.com/pypa/pip/issues/3055)
  - make [Win10 accept file paths over 260 characters](https://www.howtogeek.com/266621/how-to-make-windows-10-accept-file-paths-over-260-characters/)
- reach out to the maintainers of this project to add more wheels

## Disclaimer

The library and the notebook are free to use for everybody. Carl Zeiss Microscopy GmbH undertakes no warranty concerning the use of those tools. Use them at your own risk.

**By using any of those examples you agree to this disclaimer.**

Version: 2023.11.20

Copyright (c) 2023 Carl Zeiss AG, Germany. All Rights Reserved.

