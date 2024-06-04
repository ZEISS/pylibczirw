# API Specification
**Table of Contents**
- [Opening a CZI (read-only)](#opening-a-czi-read-only)
- [Reading a CZI](#reading-a-czi)
  - [Reading dimension information](#reading-dimension-information)
  - [Reading metadata](#reading-metadata)
  - [Reading custom attributes](#reading-custom-attributes)
  - [Reading pixel type](#reading-pixel-type)
  - [Reading pixel data](#reading-pixel-data)
    - [Signature](#signature)
     - [`read(**kwargs)`](#readkwargs)
     - [roi (optional)](#roi)
     - [plane (optional)](#plane)
     - [scene (optional)](#scene)
     - [zoom (optional)](#zoom)
     - [pixel_type (optional)](#pixel_type)
     - [background_pixel (optional)](#background_pixel)
- [Creating a CZI](#creating-a-czi)
- [Writing a CZI](#writing-a-czi)
  - [Writing pixel data](#writing-pixel-data)
    - [Signature](#signature-1)
    - [`write(data, **kwargs)`](#writedata-kwargs)
    - [data (required)](#data)
    - [location (optional)](#location)
    - [plane (optional)](#plane)
    - [compression_options (optional)](#compression_options)
    - [scene_index (optional)](#scene_index)
  - [Writing metadata](#writing-metadata)
    - [document_name (optional)](#document_name)
    - [channel_names (optional)](#channel_names)
    - [scale_x (optional)](#scale_x)
    - [scale_y (optional)](#scale_y)
    - [scale_z (optional)](#scale_z)
    - [custom_attributes (optional)](#custom_attributes)
    - [display_settings (optional)](#display_settings)
  - [Writing Example](#writing-example)
- [Advanced Topics](#advanced-topics)

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
  max_memory_usge = 500 * 1024**2 # 500 Megabytes
  max_sub_block_count = 100,
)
with czi.open_czi(file_path, cache_options=cache_options) as czi:
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

The standard way of defining ROIs to cover a plane will lead situations like the one below, where accessing Z=4 starting with a ROI (0,0, w, h) produces a bitmap with invalid data.

![image info](doc/images/fib_stack_roi.png)