# API Specification
**Table of Contents**
- [API Specification](#api-specification)
  - [Opening a CZI (read-only)](#opening-a-czi-read-only)
    - [Using a subblock cache](#using-a-subblock-cache)
    - [Specifying additional reader-options](#specifying-additional-reader-options)
  - [Reading a CZI](#reading-a-czi)
    - [Reading dimension information](#reading-dimension-information)
    - [Reading raw metadata](#reading-raw-metadata)
    - [Reading metadata](#reading-metadata)
    - [Reading custom attributes](#reading-custom-attributes)
    - [Reading pixel type](#reading-pixel-type)
    - [Reading pixel data](#reading-pixel-data)
      - [`read(**kwargs)`](#readkwargs)
      - [roi](#roi)
      - [plane](#plane)
      - [scene](#scene)
      - [zoom](#zoom)
      - [pixel\_type](#pixel_type)
      - [background\_pixel](#background_pixel)
    - [Enumerating subblocks](#enumerating-subblocks)
      - [`enumerate_subblocks(func)`](#enumerate_subblocksfunc)
      - [`enumerate_subblocks_subset(func, **kwargs)`](#enumerate_subblocks_subsetfunc-kwargs)
  - [Creating a CZI](#creating-a-czi)
  - [Writing a CZI](#writing-a-czi)
    - [Writing pixel data](#writing-pixel-data)
      - [`write(data, **kwargs)`](#writedata-kwargs)
      - [data](#data)
      - [location](#location)
      - [plane](#plane-1)
      - [compression\_options](#compression_options)
      - [scene](#scene-1)
    - [Writing metadata](#writing-metadata)
      - [document\_name](#document_name)
      - [channel\_names](#channel_names)
      - [scale\_x](#scale_x)
      - [scale\_y](#scale_y)
      - [scale\_z](#scale_z)
      - [custom\_attributes](#custom_attributes)
      - [display\_settings](#display_settings)
      - [Writing Example](#writing-example)
  - [Advanced Topics](#advanced-topics)
    - [Pixel Types](#pixel-types)
      - [Discovery](#discovery)
      - [Handling and Conversion](#handling-and-conversion)
        - [Reading](#reading)
        - [Writing](#writing)
    - [Masks](#masks)
    - [Scenes](#scenes)
      - [Images with no scenes](#images-with-no-scenes)
      - [Images with non-uniform scenes](#images-with-non-uniform-scenes)
      - [Images with uniform scenes](#images-with-uniform-scenes)
    - [Handling Planes of Different Sizes](#handling-planes-of-different-sizes)
  - [Editing metadata in-place (CziEditor)](#editing-metadata-in-place-czieditor)
    - [Opening a CZI for editing](#opening-a-czi-for-editing)
    - [Starting an edit session](#starting-an-edit-session)
    - [Builder operations](#builder-operations)
    - [Example: update document info and scaling](#example-update-document-info-and-scaling)
    - [Example: update display settings for an existing channel](#example-update-display-settings-for-an-existing-channel)

## Opening a CZI (read-only)

A CZI file can be opened in a context manager using a [path-like-object](https://docs.python.org/3/library/os.html#os.PathLike) (in this case, file_path).

`with czi.open_czi(file_path) as czi:`

Or directly using a [stream](https://docs.python.org/3/library/io.html).

**This will open the CZI in read-only mode.**

**Note**: Internally, the library works with streams. Like done in [aicspylibczi](https://github.com/AllenCellModeling/aicspylibczi/blob/f00b6eb4042246cd28a527c5964f3e946ed84c7e/aicspylibczi/CziFile.py#L48) If this is correctly implemented, otherwise, lets start using file path only.

### Using a subblock cache
The `open_czi` method additionally accepts cache options that define the subblock caching behavior of the reader document. _Per default, not cache is used._ 

A `CacheOptions` object allows defining a cache type and upper limits for memory usage and the number of subblocks to be cached:
```python
cache_options = CacheOptions(
  type = CacheType.Standard,
  max_memory_usage = 500 * 1024**2 # 500 Megabytes
  max_sub_block_count = 100,
)
with czi.open_czi(file_path, cache_options=cache_options) as czi:
    ...
```

### Specifying additional reader-options
The `open_czi` method accepts a `ReaderOptions` structure where additional configurations
can be given controlling the operations. The following options are available:
- `enable_mask_awareness` - whether the tile-composition uses mask-information. This is by default `false`.
- `enable_visibility_check_optimization` - in the tile-composition, do a visibility-check before reading sub-blocks, potentially reducing the amount of data that must be loaded. This is by default `true`.
- `lax_subblock_coordinate_checks` - whether to use lax parameter validation when parsing subblock dimension entries. The default (`true`) is lenient for compatibility with older files. Set to `false` for strict validation. Users are encouraged to disable this for new code.
- `ignore_sizem_for_pyramid_subblocks` - whether to ignore the size-M attribute of pyramid subblocks. Only relevant when `lax_subblock_coordinate_checks` is `false`. Useful for CZI files with bogus SizeM values. This is by default `false`.

The `ReaderOptions` can be passed to `open_czi` like in this example:

```python
cache_options = CacheOptions(
  type = CacheType.Standard,
  max_memory_usage = 500 * 1024**2 # 500 Megabytes
  max_sub_block_count = 100,
)
reader_options = ReaderOptions(
  enable_mask_awareness = True,
  lax_subblock_coordinate_checks = False,
  ignore_sizem_for_pyramid_subblocks = True,
)
with czi.open_czi(file_path, cache_options=cache_options, reader_options=reader_options) as czi:
    ...
```


## Reading a CZI

The following calls all relate to reading information from the CZI. And, whenever they're called, the file's last write date will be evaluated and cached. **If the file was changed while opened, all file caches will be invalidated.**

### Reading dimension information
The czi object will have some methods to extract specific information from the CZI.

The plane dimensions (i.e. C, T, Z, H, B, etc) are constant across scenes.
We will treat scenes differently at this level for the sake of consistency. The following three calls mimic the concept of [SubBlockStatistics](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#a10b6e7fb9312e93b1e9785daed56e44e) in libCZI.

**`total_bounding_box`**

*Returns:* Dictionary with the existing plane dimensions and their range. Example: `{'C': (0, 3), 'Z': (0, 4), 'T': (0,7), 'X': (0, 975), 'Y': (0, 825)}`.

**The plane dimensions are constant across scenes.**

*Default:* X, Y, C, Z, and T will always be returned even if there's no such information, in which case their default value will be (0, 1). Other dimensions (e.g. H, B, etc.) will **not** be returned if not present.

**Note**: It is possible, though rarely, that the minimum index of a plane is less than zero.

**`scenes_bounding_rectangle`**

*Returns:* Dictionary where the keys are the scenes and the value their bounding rectangles. [Same as in libCIZ](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#ab02ae7bcd25f34008ec9d5afa8a4efec). Example:  `{ 0: (0, 0, 475, 325), 1: (500, 500, 900, 800) }`

**Important:** If there are no scenes, we return empty.

**`scenes_bounding_rectangle_no_pyramid`**

*Returns:* Dictionary where the keys are the scenes and the value their bounding rectangles only taking into account layer 0 of the image pyramid. [Same as in libCIZ](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#ab02ae7bcd25f34008ec9d5afa8a4efec). Example:  `{ 0: (0, 0, 475, 325), 1: (500, 500, 900, 800) }`

**Important:** If there are no scenes, we return empty.

**`total_bounding_rectangle`**

*Returns:* The bounding rectangle of the whole CZI. Same as [boundingBox](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#a924c2adf7f3e132470dfeb06ea1e958c).

**Note**: The total bounding rectangle can also be inferred from the X and Y values returned by the `total_bounding_box` call.

### Reading raw metadata

**`raw_metadata`**

*Returns:* The raw xml metadata of the czi as a string.

### Reading metadata

**`metadata`**

*Returns:* The raw metadata of the czi parsed into a dictionary.

### Reading custom attributes

**`custom_attributes_metadata`**

*Returns:* The custom attributes list in a dictionary.

### Reading pixel type

**`get_channel_pixel_type(channel_index)`**

*Returns:* The pixel type of the channel with the specified index, e.g. 'gray8'. 
*Default:* Defaults to the minimum channel index. As mentioned above, if there is no C index in the CZI (uncommon and pathological case), the C index still defaults to 0.

**`pixel_types`**

*Returns:* Dictionary whose keys are the channel indices, and the values the channel's pixel types, e.g.  {0: 'gray8', 1: 'bgr24'}

LibCZI's strategy for finding a channel's pixel type is by checking the pixel type of the first subblock. This is further discussed in [**Discovery**](#discovery).

### Reading pixel data

LibCZI offers different ways of reading the pixel data:

![image info](doc/images/libczi_access_types.png)  

We will use the [Single Channel Scaling Accessor](https://zeiss.github.io/libczi/classlib_c_z_i_1_1_i_single_channel_scaling_tile_accessor.html). And, to start simple, the python api should resemble what the [libCZI exposes](https://zeiss.github.io/libczi/classlib_c_z_i_1_1_i_single_channel_scaling_tile_accessor.html).

<span style="color: #FF2C00">Important</span> considerations regarding the Single Channel Scaling Accessor:

- Subblocks of different scenes CANNOT overlap. When they do, we get undefined behaviour. This assumption allows for no ambiguity about the returned data when the roi spans across multiple scenes.
- Images might have overlapping tiles/subblocks, this is particularly the case for non-stitched images. When getting pixel data from regions with overlapping subblocks (within the same scene), the subblock with the highest M-index wins.
If tile-wise processing or any other processing that accounts for subblock arrangement is needed, new methods must be provided that bind to [libCZI's subblock accessor](https://zeiss.github.io/libczi/classlib_c_z_i_1_1_i_sub_block_repository.html).

#### `read(**kwargs)`

*Returns:* The pixel data as a **numpy array**, the shape of the returned array and its data type will depend on the specified `pixel_type`.
- BGR pixel type -> [y, x, 3]
- Gray pixel type -> [y, x, 1]

This is further explained in the [pixel type parameter description](#pixel_type)

#### roi
**Optional**  
The **roi is a tuple** defined as a (axis-aligned) rectangle in (x, y, w, h) form, with:
- x: x coordinate of upper-left point
- y: y coordinate of upper-left point
- w: rectangle width
- h: rectangle height

**The maximum roi size is the total bounding rectangle.**

*Default:* The roi default depends on the scene parameter:
- No scene parameter: The roi defaults to the total bounding rectangle (`total_bounding_rectangle`)
- Scene parameter specified: The roi defaults to the bounding box of the specified scene.

**Important:** For CZIs with scenes of different shapes, not specifying the roi will return different shapes of data for each scene.

**Please check the section on [scenes](#scenes) section for examples on how to handle CZIs with different scene arrangements.**

#### plane
**Optional**  
The plane variable is a set of indices representing the coordinate of the planes to access. It is as dictionary whose keys are the dimension and the values are the coordinate value.
Example: dict {'C': 0, 'T': 1, 'Z': 4}

*Default:* Defaults to the minimum value for all plane coordinates, which can be known using `total_bounding_box`.

*Errors:* If any plane coordinate falls outside the existing bounds, an error is raised.

**Note:** There might be indices with negative indices, and there is no logic to deal with this case. It is up to the caller to deal with such scenarios.

#### scene
**Optional**  
The index of the scene to be considered. If set, only subblocks of the specified scene can contribute to the resulting bitmap.

*Default:* All scenes will be considered.

**Note:** Scenes are not orthogonal to the other dimensions and must therefore be handled differently. For more information please check the section on [scenes](#scenes) section.

#### zoom
**Optional**  
A float between 0 (excluded) and 1 that specifies the zoom factor.

The purpose of the zoom factor (like the ROI) is to facilitate the handling of large data that does not fit into the available memory. Using a zoom factor smaller than one will return less data. 

*Default:* The zoom defaults to 1, in which case, the returned array will have the same X,Y shape of the used ROI. Smaller zoom factors will return an array whose X,Y shape are smaller (in the proportion of the zoom factor) than the used ROI. For zoom levels different than 1, allocating the output bitmap needs to be done in 2 calls.

*Errors:* Zoom levels will throw at small enough levels.

#### pixel_type
**Optional**  
The pixel type of the returned data.

*Default:* Defaults to the pixel type of the channel being read.

Since a pixel type is always used internally, there will always be an implicit pixel conversion done by libCZI which will take care of the issue of having subblocks with different pixel types in the same channel.

Reading pixel types is further explained in the section on [reading pixel data](#reading-pixel-data) section.


#### background_pixel
**Optional**  
Specified the colour of the background pixels (pixels with no data).
This parameter naturally needs to be consistent with the returned pixel type:
|pixel_type | background_pixel type | Default value  | 
--- | --- | ---
|BGR|3-value tuple |(0, 0, 0)|
|Gray|Scalar value bounded by the gray scale|0|
|BGRA (If ever supported by libCZI)|4-value tuple|(0, 0, 0, 0)|

*Errors:* An exception will be raised if the wrong type is provided.

**Note:** In the future we hope to support masks to univocally identify invalid data.

### Enumerating subblocks

Subblock enumeration provides direct access to subblock header information without loading pixel data. This is useful for analyzing CZI structure, querying subblock metadata, and understanding how data is organized within the file.

#### `enumerate_subblocks(func)`

Enumerates all subblocks in the CZI document, calling the provided function for each subblock.

**Parameters:**
- `func`: A callable that takes two arguments: `index` (int) and `info` (SubBlockInfo). The function should return `True` to continue enumeration or `False` to stop.

**SubBlockInfo attributes:**
- `logicalRect`: Rectangle defining the subblock's position in logical coordinate space (x, y, width, height)
- `physicalSize`: Actual bitmap dimensions (width, height) - may differ from logical size for pyramid layers
- `pixelType`: Pixel type enumeration (e.g., Gray8, Gray16, Bgr24)
- `coordinate`: DimCoordinate object containing the subblock's dimensional coordinates (C, Z, T, etc.)
- `mIndex`: M-index for mosaic/scene organization (if available)
- `get_compression_mode()`: Returns the compression mode (UnCompressed, JpgXr, Zstd0, etc.)
- `get_zoom()`: Calculates zoom factor from physical and logical sizes
- `is_mindex_valid()`: Checks if M-index is valid

**Example:**
```python
with czi.open_czi(file_path) as czi_doc:
    def print_subblock_info(index, info):
        rect = info.logicalRect
        print(f"Subblock {index}:")
        print(f"  Position: ({rect.x}, {rect.y})")
        print(f"  Size: {rect.w} x {rect.h}")
        print(f"  Pixel type: {info.pixelType.name}")
        print(f"  Compression: {info.get_compression_mode().name}")
        print(f"  Coordinates: {info.coordinate.to_dict()}")
        return True  # Continue enumeration

    czi_doc.enumerate_subblocks(print_subblock_info)
```

#### `enumerate_subblocks_subset(func, **kwargs)`

Enumerates a filtered subset of subblocks based on optional criteria.

**Parameters:**
- `func`: Callback function (same as `enumerate_subblocks`)
- `plane` (optional): Coordinate filter specifying which dimensional plane to enumerate
  - Can be a string (e.g., `"C0Z5T2"`)
  - Can be a dictionary (e.g., `{"C": 0, "Z": 5, "T": 2}`)
  - Default: `None` (no coordinate filtering)
- `roi` (optional): Region of interest filter as tuple `(x, y, width, height)` or Rectangle
  - Only subblocks intersecting this ROI are enumerated
  - Default: `None` (no ROI filtering)
- `only_layer0` (optional): If `True`, enumerate only pyramid layer 0 subblocks
  - Layer 0 subblocks have `physicalSize == logicalRect size`
  - Default: `False`

**Examples:**

Enumerate layer 0 subblocks only:
```python
with czi.open_czi(file_path) as czi_doc:
    def process_layer0(index, info):
        # Process full-resolution subblocks
        return True

    czi_doc.enumerate_subblocks_subset(
        process_layer0,
        only_layer0=True
    )
```

Filter by coordinate using string notation:
```python
with czi.open_czi(file_path) as czi_doc:
    def process_specific_plane(index, info):
        # Process only subblocks at C=0, Z=5
        return True

    csi_doc.enumerate_subblocks_subset(
        process_specific_plane,
        plane="C0Z5",
        only_layer0=True
    )
```

Filter by coordinate using dictionary notation:
```python
with czi.open_czi(file_path) as czi_doc:
    subblock_bounds = []

    def collect_bounds(index, info):
        rect = info.logicalRect
        subblock_bounds.append({
            'x': rect.x,
            'y': rect.y,
            'width': rect.w,
            'height': rect.h
        })
        return True

    czi_doc.enumerate_subblocks_subset(
        collect_bounds,
        plane={"C": 0, "Z": 5, "T": 2},
        only_layer0=True
    )
```

Filter by region of interest:
```python
with czi.open_czi(file_path) as czi_doc:
    # Enumerate subblocks intersecting upper-left quadrant
    roi = (0, 0, 512, 512)

    def process_roi_subblocks(index, info):
        return True

    czi_doc.enumerate_subblocks_subset(
        process_roi_subblocks,
        roi=roi,
        only_layer0=True
    )
```

Combine multiple filters:
```python
with czi.open_czi(file_path) as czi_doc:
    def analyze_subblock(index, info):
        # Analyze specific subblocks
        coord = info.coordinate.to_dict()
        compression = info.get_compression_mode().name
        print(f"Subblock {index}: {coord}, {compression}")
        return True

    czi_doc.enumerate_subblocks_subset(
        analyze_subblock,
        plane={"C": 0, "Z": 3},
        roi=(100, 100, 500, 500),
        only_layer0=True
    )
```

**Early termination:**
```python
with czi.open_czi(file_path) as czi_doc:
    # Collect first 10 subblocks
    collected = []

    def collect_limited(index, info):
        collected.append(info)
        return len(collected) < 10  # Stop after 10

    czi_doc.enumerate_subblocks(collect_limited)
```

## Creating a CZI

Like with opening, creating a new empty CZI can be done in a context manager using a [path-like-object](https://docs.python.org/3/library/os.html#os.PathLike) (in this case, file_path).

`with czi.create_czi(file_path) as czi:`

This creates a new czi file at the provided path and **opens it in write mode.**  
**Note:** Any intermediate-level directories needed to contain the leaf directory are generated if necessary.  
**Note:** Per default, a [FileExistsError](https://docs.python.org/3/library/exceptions.html#FileExistsError) is raised in case `file_path` already exists. The error can be ignored by calling  
`with czi.create_czi(file_path, exist_ok = True) as czi:`

The compression option is an optional parameter for czi.creat_czi function and can be overwritten with each individual call to the write function. The compression option can be defined by calling
`with czi.create_czi(file_path, exist_ok = True, compression_options = zstd0:) as czi:`

## Writing a CZI

### Writing pixel data

For the sake of consistency, we want to write data similarly to how we read it.

#### `write(data, **kwargs)`

Writes data as **a single subblock** in the CZI at a specific location.

#### data
**Required**  

The data (numpy array) to be written.

Writing 2D single non-BGR channel is done by providing a [1, y, x] array.
Writing a 2D single BGR channel is done by providing a [3, y, x] array.

The pixel type in which to write the data will be inferred from the numpy array data type following the rules described in [**Writing Pixel Data**](#writing-pixel-data).

**Note:** Data is expected in BGR. If the original data is in BGR format, rotation can be done simply by `bgr = rgb[...,::-1]`.

*Errors:* If the data is larger than 10MB, this call will throw. In order to write larger data, it needs to be broken down into chunks smaller than 10MB.

#### location
**Optional**  

The pixel coordinates of the upper-left pixel. This allows writing data in different regions in the selected 2D plane.

*Default:* Default value is (0, 0).

*Errors:* If there is already data at the specified position, the write call will raise an exception  (i.e. we cannot write overlapping subblocks).

#### plane
**Optional**  

Same concept of the read method. A dictionary specifying the plane coordinates of the data to be written.
Example: dict {'C': 0, 'T': 1, 'Z': 4}

An M index is cached per plane so that every new subblock written to the plane gets the next M-index (this is hidden from the user).

*Default:* All planes will default to 0, meaning that the size of each plane coordinate is at least 1.

*Errors:* If there is data with a different pixel type in the specified plane, the write call will raise an exception.

#### compression_options
**Optional**

String representation of compression options.

*Default:* If no compression_options is specified, the writer's default is used.

#### scene
**Optional**  

An integer specifying the scene index.

*Default:* If no scene index is specified the result document will have a single scene with index 0.

### Writing metadata

Metadata can be explicitly written with

**`write_metadata(document_name, channel_names, scalex_x, scale_y, scale_z, custom_attrbutes, display_settings)`**

If not explicitly written, metadata will be automatically written when closing the file.


libCZI allows writing metadata through the [IMetadataSegment](https://github.com/ZEISS/libczi/blob/7b425bdec760af8f1728c51a0290e44f97ed9fef/Src/libCZI/libCZI_ReadWrite.h#L86) exposed in the ICziReaderWriter.
The IMetadataSegment is the root of a specialized object tree that provides access to specific metadata. We will start by exposing a single call to write channel information which will manipulate the [IDimensionChannelInfo](https://github.com/ZEISS/libczi/blob/7b425bdec760af8f1728c51a0290e44f97ed9fef/Src/libCZI/libCZI_Metadata2.h#L170).

#### document_name
**Optional**  

The document name is an optional string parameter that sets the value of the Document.Title metadata node.

#### channel_names
**Optional**  

The channel names parameter is a dictionary whose keys are the channels' indices, and the values being a dictionary representing the channels' names.

**For now, we will only support changing the channel name**. So the only valid format is: ``{ 0: "C1", 1: "C2" }``

Future requirements like setting a channel's color will only require implementation at the C++ layer, with the python API having no change whatsoever. It simply will not break when setting the channel color anymore. 

Future things to implement:
- writing spatial relationship data instead of stage coordinates at subblocks.
- Add colour persistence to channel.

#### scale_x
**Optional**  

scale_x is an optional float parameter that indicates the extent of a pixel in x-direction (in units of m) in the document.

#### scale_y
**Optional**  

scale_y is an optional float parameter that indicates the extent of a pixel in y-direction (in units of m) in the document.

#### scale_z
**Optional**  

scale_z is an optional float parameter that indicates the extent of a pixel in z-direction (in units of m) in the document.

#### custom_attributes
**Optional**  

custom_attributes is an optional dictionary parameter that contains customized key-value pairs.

#### display_settings
**Optional**  

display_settings is an optional dictionary of display settings, where key is channel number and value is the corresponding display setting.

*Errors:* If the type of value is not boolean, integer, float or string.

#### Writing Example

The following code illustrates how one can write a czi in a machine learning context.

```python

data = inference_service.run() # [2, y, x] array with 2 being the number of classes.

with czi.open_czi(path, 'w'):

    class_nuclei = data[0,:,:]
    channel_0 = { 'C': 0 }

    czi.write(data=class_nuclei, location=(0,0), plane=channel_0, compression_options = "zstd0:ExplicitLevel=0" )

    class_background = data[1,:,:]
    channel_1 = { 'C': 1 }

    czi.write(data=class_background, location=(0,0), plane=channel_1, compression_options = "zstd1:ExplicitLevel=2" )

    # If we stopped here, we'd have a valid CZI. But we want to name the channels after the classes.

    channel_names = { 0: "C1", 1: "C2" }
    custom_attributes = {"key1": "value1", "key2": "value2"}

    czi.write_metadata(channel_names=channel_names, scale_x=0.1 `* 1e-6, scale_y=0.1 * 1e-6, custom_attributes=custom_attributes)

    # If we want to specify specific colors for specific channels, we write as follows:
    # In this case we are specifying c1 as blue and c2 as green.
    
    display_setting_dict: Dict[int, ChannelDisplaySettingsDataClass] = {}
    tint_color_c1 = Rgb8Color(np.uint8(0x00), np.uint8(0xFF), np.uint8(0x00))
    channel_setting_c1 = ChannelDisplaySettingsDataClass(True, TintingMode.Color, tint_color_c1)
    display_setting_dict[0] = channel_setting_c1
    tint_color_c2 = Rgb8Color(np.uint8(0x00), np.uint8(0x00), np.uint8(0xFF))
    channel_setting_c2 = ChannelDisplaySettingsDataClass(True, TintingMode.Color, tint_color_c2)
    display_setting_dict[1] = channel_setting_c2

    czi.write_metadata(display_settings=display_setting_dict)

    # Similarly, if we want to specify specific colors and black/white levels for specific channels, we write as follows:
    # In this case we are specifying c1 as blue and c2 as green.
    # Additionally we specify c1 with black point as 0.2 and white point as 0.8 and c2 with black point as 0.3 and white point as 0.75.

    display_setting_dict: Dict[int, ChannelDisplaySettingsDataClass] = {}
    tint_color_c1 = Rgb8Color(np.uint8(0x00), np.uint8(0xFF), np.uint8(0x00))
    channel_setting_c1 = ChannelDisplaySettingsDataClass(True, TintingMode.Color, tint_color_c1, 0.2, 0.8)
    display_setting_dict[0] = channel_setting_c1
    tint_color_c2 = Rgb8Color(np.uint8(0x00), np.uint8(0x00), np.uint8(0xFF))
    channel_setting_c2 = ChannelDisplaySettingsDataClass(True, TintingMode.Color, tint_color_c2, 0.3, 0.75)
    display_setting_dict[1] = channel_setting_c2

    czi.write_metadata(display_settings=display_setting_dict)

    # Note: writing display setting for a channel overwrites any existing display setting as we do not fetch the current display setting.
    # Note: There is no 1:1 relationship enforced. A user may decide to add display settings to each channel or only to some channels.
    #       Similarly, it is not verified if the user sends more display settings than channels present.
    #       Display setting that are not written will be set as 'empty' regardless of if the initially existed for that channel.
```
## Advanced Topics
### Pixel Types

#### Discovery

Pixel type is a tricky topic. The following situations are possible:
- metadata has the correct pixel type
- metadata has an incorrect pixel type
- metadata does not have information about the pixel type
- pixel type is the same for all channels
- pixel type is different for different channels
- pixel type is different for different subblocks in the same channel

We will get the pixel type by looking at the first subblock (using libCZI).

#### Handling and Conversion

Data can be read and written in different pixel types, with BGR having some peculiarities.

##### Reading

**<span style="color:	#FF2C00">TO DO: pixel type to numpy data type conversion</span>**
read



write
[1, y, x]
uint8 -> gray8
uint16 -> gray16
float32 -> gray32 float
[3, y, x]
uint8 -> BGR24 (colour rotation, )
uint16 -> BGR48
float32 -> BGR96float (check if libCZI)



When reading, one can specify a destination pixel type. When the requested pixel type is different than the source's, libCZI converts it. The conversion is done as documented in the [libCZI documentation](https://zeiss.github.io/libczi/accessors.html):

![pixel type conversion](doc/images/pixel_type_conversion.png)

**Important: The shape of the last data dimension will always be expanded from 1 to 3 if the [destination pixel type](#pixel_type) is BGR (BGR24 or BGR48).**

This is similar to what is done in [aicspylibczi](https://github.com/AllenCellModeling/aicspylibczi/blob/575c440c6bf6a0a481dabd0b4ae4eb67f89dda26/aicspylibczi/CziFile.py#L342).


##### Writing

There is no pixel type conversion in place when writing. We must therefore add the necessary logic to the subblock creation process.

In both the low and high-level read APIs, if the pixel_type is set to BGR, the subblock creation will have to merge the channels found in the data array following the same conversion rules defined above.
**Important: The data must of therefore be consistent with the pixel type being written. Otherwise an error will be thrown**


### Masks
Regions with no data will be filled by libCZI with the background color. There is therefore no way to tell between a pixel having the color of the background or being really background/invalid.

*A hacky way of figuring it out is to request the same data twice with different background colors.*

The real solution to this problem is by leveraging the mask data that exists in the CZI. Masks indicate regions with invalid or no data. There are two cases:                
- simple case: there is no subblock at aspecific location
- advanced case: there is a subblock with mask data, indicating that there are parts with invalid pixels

However, there is no support (yet) for masks in libCZI. If we come to need it, it has to be implemented.

### Scenes
Scenes are not orthogonal to the other dimensions, they can be though of as "tags". Thus, handling them as other dimensions will cause more problems than it would help.

In a nutshell:
**The scene-index is not part of a plane-coordinate**

The arrangement below is possible:

![image info](doc/images/scenes.png)

Getting the dimensions of this CZI would show these scenes having the following bounding boxes:

**S0:** X=0, Y=0, W=100, H=100
**S1:** X=80, Y=80, W=100, H=100

For orthogonal dimensions, one can loop through them using the same ROI and not run into troubles. (<span style="color:	#FF8C00">Or am I missing something?</span>)
However, in the situation above, looping through scenes with the same ROI would produce bogus data:

![image info](doc/images/read_scenes.png)

So to avoid confusion we treat scenes differently. By having to deal with scenes separately, users will know that they're not just another dimension.

#### Images with no scenes

Let's say we have a single-channel CZI time series with no scenes:

![simple czi](doc/scenes/no_scenes.png)

**Get dimensions information:**

```python
total_bounding_box = get_total_bounding_box()
scene_bounding_rectangle = czi.get_scene_bounding_rectangle()
total_bounding_rectangle = czi.get_total_bounding_rectangle()

print(total_bounding_box)
# {'C': 0, 'T': (0, 5), 'X': (0, 400), 'Y': (0, 600)}
print(scene_bounding_rectangle)
# ''
print(total_bounding_rectangle)
# '(0, 0, 400, 600)'
```
**Default read (no ROI)**

```python
for t in t_enumerable:
    data = czi.read(plane = { 'T': t })
```
Returns:

![default read](doc/scenes/no_scenes.png)

**Specifying ROI:**

```python
for t in t_enumerable:
    roi = (0, 0, 200, 200)
    data = czi.read(roi=roi, plane = { 'T': t })
```
Returns:

![read at roi](doc/scenes/no_scenes_result_roi.png)


#### Images with non-uniform scenes

Let's say we have a single-channel time series and z-stack CZI with scenes:

![multi-scene czi](doc/scenes/scenes_image.png)


**Get dimensions information:**

```python
print(total_bounding_box)
# {'C': 0, 'T': (0, 5), 'Z': (0, 2), 'X': (0, 2000), 'Y': (0, 1400)}
```

In this case, scenes have different sizes/bounding boxes:

![bounding boxes](doc/scenes/bounding_boxes.png)

```python
print(scene_bounding_rectangle)
# { 0: (800, 0, 1200, 500), 1: (0, 200, 1000, 1200), 2: (900, 600, 1100, 800)}
print(total_bounding_rectangle)
# { 0: (0, 0, 2000, 1400)}
```

**Default read (no ROI)**

If no scene is specified the call:

```python
data_all_scenes = czi.read()
```

Will have the following defaults:
- ROI = total_bounding_rectangle = (0, 0, 2000, 1400)
- Planes = { 'C': 0, 'T': 0, 'Z': 0 }

And return the following data:

![read no roi](doc/scenes/read_all_scenes.png)

If a scene is specified the call:

```python
data = czi.read(scene=1)
```

Will have the following defaults:
- ROI = scene_bounding_rectangle[1] = (0, 200, 1000, 1200)
- Planes = { 'C': 0, 'T': 0, 'Z': 0 }

And return the following data:

![read no roi](doc/scenes/read_s1.png)

**Specifying ROI:**

Getting data from a specific ROI works exactly as specified above. The user needs to keep in mind that the ROI can span across different scenes.

![roi](doc/scenes/roi.png)

```python
roi = (500, 0, 500, 700)

data_all_scenes = czi.read(roi=roi)
data_s1 = czi.read(roi=roi, scene=1)
```

Returns:

![read at roi](doc/scenes/read_roi.png)


#### Images with uniform scenes

Let's consider an image with scenes of consistent shape, like a multi-well where each scene corresponds to a well.

![multi-well](doc/scenes/multi_well.png)

The logic above is unaltered, but we will most likely not want to read data at ROIs spanning across multiple scenes. Instead, we would like to iterate over the scenes and get the scene/well data.

This can be done as follows:

```python
total_bounding_box = get_total_bounding_box()
scene_bounding_rectangle = czi.get_scene_bounding_rectangle()
total_bounding_rectangle = czi.get_total_bounding_rectangle()

print(total_bounding_box)
# {'X': (0, 1000), 'Y': (0, 1000)}
print(scene_bounding_rectangle)
# { 0: (0, 0, 400, 400), 1: (500, 0, 1000, 400), 2: (0, 500, 400, 1000), 3: (500, 500, 1000, 1000)}
print(total_bounding_rectangle)
# '(0, 0, 1000, 1000)'
```

```python

for s in scene_bounding_boxes.keys():
    roi = scene_bounding_boxes[s]
    data = czi.read(roi=roi)
```

This iteration returns the pixel data for each scene. There is no need to specify the scene_filter because the ROI is the scene bounding box and there are no overlapping scenes.


![iteration results](doc/scenes/iteration_results.png)

### Handling Planes of Different Sizes

There are some CZIs where the size of the planes varies. Z-stacks acquired in the FiB-SEM are an example of this:

![image info](doc/images/fib_stack.png)

This means that it's possible to get zones with invalid data in different planes.

The user can nevertheless access the data normally, but the assumption that the planes are correctly stacked is not guaranteed.

**All planes live in a common pixel-coordinate system. And this pixel-coordinate-system gives the spatial position. Everything else is a matter of interpretation.**

The standard way of defining ROIs to cover a plane will lead to situations like the one below, where accessing Z=4 starting with a ROI (0,0, w, h) produces a bitmap with invalid data.

![image info](doc/images/fib_stack_roi.png)

## Editing metadata in-place (CziEditor)

The edit API allows reading metadata and performing in-place metadata changes on an existing CZI without rewriting pixel data. It uses a context manager to open the file and provides a builder for staged edits that are committed once.

### Opening a CZI for editing

Open an existing file and obtain an editor:

```python
from pylibCZIrw.czi import edit_czi
with edit_czi(file_path) as editor: assert editor.is_open xml = editor.read_metadata_xml()
```

- The editor exposes read helpers:
  - `read_metadata_xml()` -> returns the current metadata XML as a string.
  - `read_general_document_info()` -> returns available document info as a dict; keys may include `name`, `title`, `user_name`, `description`, `comment`, `keywords`, `rating`, `creation_date_time`. Missing keys were not present in the file.
  - `read_scaling_info()` -> returns a DTO with optional `scale_x`, `scale_y`, `scale_z` (None when not present).
  - `read_display_settings()` -> returns a dict mapping channel index to per-channel display settings (may be empty if the file has no display settings).
  - `read_custom_key_value(key)` -> returns the value for a custom attribute as a native Python type (bool, int, float, str) or None if not found.

### Starting an edit session

Edits are made via a metadata builder returned by the editor. The builder accumulates changes and writes them back on `commit()`.

```python
with edit_czi(file_path) as editor: builder = editor.create_metadata_builder() # or use auto-commit on success: with editor.edit_session() as builder: ...
```

- `create_metadata_builder()` initializes the builder from the current file state.
- `begin_edit()` is an alias for creating a builder.
- `edit_session()` yields a builder and auto-commits once on successful exit if `can_commit()` returns True.

### Builder operations

The builder provides high-level setters. Fields left as None are ignored; only specified values are applied.

- `get_xml(prettify: bool = False)` -> returns the current builder XML.
- `set_xml(xml_string)` -> replaces the builder content with the given XML string (must be valid CZI metadata XML).
- `set_general_document_info(...)` -> updates document info fields. Accepts a DTO and/or keyword arguments:
  - `name`, `title`, `user_name`, `description`, `comment`, `keywords`, `rating`
  - Unspecified fields remain unchanged.
- `set_scaling_info(...)` -> updates pixel size in the existing unit (typically μm). Accepts a DTO and/or keyword args:
  - `scale_x`, `scale_y`, `scale_z`
  - Unspecified axes remain unchanged.
- `set_custom_key_value(key, value)` -> sets or adds a custom attribute. `value` must be bool, int, float, or str.
- `set_display_settings({channel_index: settings_dto})` -> updates per-channel display settings for provided channels only.
  - Settings include `is_enabled`, `tinting_mode` (`TintingMode.none` or `TintingMode.Color`), `tinting_color` (`Rgb8Color`), `black_point`, `white_point`.
  - Optional `name` and `description` can be provided in `ChannelDisplaySettingsDataClassWithNameAndDescription`.
  - Nonexistent channels are not created by this call.
- `can_commit()` -> returns True if the builder can commit to the file.
- `commit()` -> writes all pending changes back to the CZI file.

### Example: update document info and scaling

```python
from pylibCZIrw.czi import edit_czi, ScalingInfoDto, GeneralDocumentInfoDto
with edit_czi(file_path) as editor: builder = editor.create_metadata_builder()
builder.set_general_document_info(
    info=GeneralDocumentInfoDto(title="New Title"),
    user_name="EditorUser",
    comment="Edited by API",
)

builder.set_scaling_info(scale_x=0.25, scale_y=0.25)  # leave Z unchanged

if builder.can_commit():
    builder.commit()

# Verify
info = editor.read_general_document_info()
scaling = editor.read_scaling_info()
```


### Example: update display settings for an existing channel

```python
from pylibCZIrw.czi import edit_czi, Rgb8Color, TintingMode, ChannelDisplaySettingsDataClassWithNameAndDescription
with edit_czi(file_path) as editor: builder = editor.create_metadata_builder()
ds = ChannelDisplaySettingsDataClassWithNameAndDescription(
    is_enabled=True,
    tinting_mode=TintingMode.Color,
    tinting_color=Rgb8Color(r=255, g=0, b=0),
    black_point=0.05,
    white_point=0.95,
    description="Edited by API",
)

builder.set_display_settings({0: ds})  # update channel 0 if it exists

if builder.can_commit():
    builder.commit()

```

Notes
- Builder setters merge DTO values with explicit keyword arguments; keywords override DTO fields when provided.
- Unspecified fields are not written, preserving existing metadata.
- `read_display_settings()` may return an empty map for files without display settings.
- `read_custom_key_value(key)` returns the current value as a native type when present.