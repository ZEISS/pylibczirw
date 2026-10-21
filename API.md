# API Specification

This document describes the implemented API, including the bounded
`CziDocument` facade. Methods added here require a build containing these
interfaces; older published wheels may not provide them.

## Table of Contents

- [API Specification](#api-specification)
  - [Document facade](#document-facade)
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
      - [plane (read)](#plane-read)
      - [scene (read)](#scene-read)
      - [zoom](#zoom)
      - [pixel_type](#pixel_type)
      - [background_pixel](#background_pixel)
    - [Enumerating subblocks](#enumerating-subblocks)
      - [`enumerate_subblocks(func)`](#enumerate_subblocksfunc)
      - [`enumerate_subblocks_subset(func, **kwargs)`](#enumerate_subblocks_subsetfunc-kwargs)
    - [Listing subblock snapshots](#listing-subblock-snapshots)
    - [Reading stored subblock pixels](#reading-stored-subblock-pixels)
    - [Reading selected XML and masks](#reading-selected-xml-and-masks)
    - [Reading exact stored levels](#reading-exact-stored-levels)
    - [Reading attachments](#reading-attachments)
  - [Creating a CZI](#creating-a-czi)
  - [Writing a CZI](#writing-a-czi)
    - [Writing pixel data](#writing-pixel-data)
      - [`write(data, **kwargs)`](#writedata-kwargs)
      - [data](#data)
      - [location](#location)
      - [plane (write)](#plane-write)
      - [compression_options](#compression_options)
      - [scene (write)](#scene-write)
    - [Writing metadata](#writing-metadata)
      - [document_name](#document_name)
      - [channel_names](#channel_names)
      - [scale_x](#scale_x)
      - [scale_y](#scale_y)
      - [scale_z](#scale_z)
      - [custom_attributes](#custom_attributes)
      - [display_settings](#display_settings)
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

## Document facade

Import `CziDocument` from `pylibCZIrw.czi`. Its three factories acquire a resource
immediately, before context entry:

```python
from os import PathLike
from pylibCZIrw.czi import CziDocument, ReaderFileInputTypes, CacheOptions, ReaderOptions

class CziDocument:
  @classmethod
  def open(
    cls, filepath: str | PathLike[str], *,
    file_input_type: ReaderFileInputTypes = ReaderFileInputTypes.Standard,
    cache_options: CacheOptions | None = None,
    reader_options: ReaderOptions | None = None,
  ) -> "CziDocument": ...

  @classmethod
  def create(
    cls, filepath: str | PathLike[str], *,
    exist_ok: bool = False, compression_options: str | None = None,
  ) -> "CziDocument": ...

  @classmethod
  def edit(cls, filepath: str | PathLike[str]) -> "CziDocument": ...
```

These signatures specify the factories, not an example implementation.
Each returns an already-open document. Use a `with` block or call `close()`
explicitly. There is no public resource-opening constructor or generic `mode=`
argument. Local paths accept text `PathLike` objects; byte paths are rejected.
URL strings require explicit `ReaderFileInputTypes.Curl`, preserve the URL
unchanged, and use the existing reader's range-request behavior. Create and edit
accept local paths only. Create refuses existing files unless `exist_ok=True`.

| Read-Only `mode` | Delegated Operations                                                                                                                                                                                                                                         |
|------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `"r"`            | `read`, `list_subblocks`, `read_subblock`, `read_subblock_by_m`, `read_subblock_metadata_xml`, `read_subblock_mask`, `list_stored_levels`, `read_stored_level`, `list_attachments`, `read_attachment`, `read_attachment_image`, `read_label`, `read_preview` |
| `"w"`            | `write`, `write_metadata`                                                                                                                                                                                                                                    |
| `"edit"`         | `read_metadata_xml`, `edit_session`                                                                                                                                                                                                                          |

Delegates retain the existing method signatures, defaults, results and domain
errors documented below. The facade owns one existing reader, writer or editor,
including its stream and cache, for its whole lifetime. It does not reopen per
operation, expose raw owners or forward unknown attributes. Count helpers and
other APIs outside this table remain available on the existing classes only.
Legacy `read` still returns YXA; direct grayscale reads return YX, color returns
YXA in native BGR order. M coordinates, directory indices and opaque stored-level
tokens remain distinct. XML/mask and attachment reads retain their documented
selected-payload RAM/I/O costs; the facade adds no streaming guarantee.

```python
from pathlib import Path
from pylibCZIrw.czi import CziDocument

with CziDocument.open(Path("image.czi")) as document:
  info = document.list_subblocks()[0]
  pixels = document.read_subblock(info.index)
assert document.closed
# Returned pixels and immutable descriptors remain usable here.
```

`mode` and `closed` are read-only. `close()` finalizes and releases the owner at
most once; repeated close is harmless. Even failed finalization leaves the
document terminal. Operations on a closed document raise `RuntimeError`; a
wrong-mode operation on an open document raises `ValueError`. Nested/repeated
context entry is rejected. A context never suppresses a body exception. If body
and cleanup both fail, the body exception stays primary and the cleanup error is
its explicit cause. Acquisition failures propagate immediately; partially
acquired reader state is closed if statistics initialization fails.

`edit_session()` borrows the existing `CziMetadataBuilder`. Failed sessions do
not commit, and a session exiting after document close cannot automatically
commit. A context retained until after close cannot be entered. The builder is
supported only within its open document/session; retaining it is not an
independent lifetime or a general read/write API. Existing `open_czi`,
`create_czi`, `edit_czi`, `CziReader`, `CziWriter` and `CziEditor` remain supported.
See [the runnable workflow](demo_scripts/10_document_workflow.py) for create,
metadata edit and post-close pixel display.

## Opening a CZI (read-only)

A CZI file can be opened in a context manager using a [path-like-object](https://docs.python.org/3/library/os.html#os.PathLike) (in this case, file_path).

`with czi.open_czi(file_path) as czi:`

**This will open the CZI in read-only mode.**

The public API accepts paths, not arbitrary Python file objects. Internally it
uses libCZI streams. HTTP(S) input requires explicit curl selection and a server
supporting byte-range requests:

```python
from pylibCZIrw import czi

with czi.open_czi(url, file_input_type=czi.ReaderFileInputTypes.Curl) as reader:
  data = reader.read(plane={"C": 0})
```

### Using a subblock cache

The `open_czi` method accepts cache options defining subblock caching.
_By default, no cache is used._

A `CacheOptions` object allows defining a cache type and upper limits for memory usage and the number of subblocks to be cached:

```python
cache_options = CacheOptions(
  type = CacheType.Standard,
  max_memory_usage = 500 * 1024**2, # 500 MiB
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
  max_memory_usage = 500 * 1024**2, # 500 MiB
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

Statistics are captured when the reader opens. No public contract automatically
rechecks file modification dates or invalidates all caches after an external
edit. Close and reopen the reader after changes; do not mutate its source during
reads or deferred computation.

### Reading dimension information

The czi object will have some methods to extract specific information from the CZI.

The returned non-spatial sizes are document-wide, not proof that each scene has
the same coordinates or complete plane coverage.
We will treat scenes differently at this level for the sake of consistency. The following three calls mimic the concept of [SubBlockStatistics](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#a10b6e7fb9312e93b1e9785daed56e44e) in libCZI.

**`total_bounding_box`**

_Returns:_ Dictionary with the existing plane dimensions and their range. Example: `{'C': (0, 3), 'Z': (0, 4), 'T': (0,7), 'X': (0, 975), 'Y': (0, 825)}`.

X/Y tuples are half-open `(start, stop)` ranges, not `(start, size)`;
width/height are `stop - start`. The current wrapper builds non-spatial ranges
as `(0, GetDimensionSize(...))`, so these are not a reliable representation of
negative/nonzero starts or sparse coordinates. Use subblock enumeration for
exact stored coordinates. S is exposed through scene bounds, and M through
subblock headers, not through this dict.

_Default:_ C/Z/T are synthesized as `(0, 1)` when absent. X/Y come from the
bounding rectangle. Other dimensions are included only when present.

**Note**: It is possible, though rarely, that the minimum index of a plane is less than zero.

**`scenes_bounding_rectangle`**

_Returns:_ Dictionary where the keys are the scenes and the value their bounding rectangles. [Same as in libCIZ](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#ab02ae7bcd25f34008ec9d5afa8a4efec). Example: `{ 0: (0, 0, 475, 325), 1: (500, 500, 900, 800) }`

**Important:** If there are no scenes, we return empty.

**`scenes_bounding_rectangle_no_pyramid`**

_Returns:_ Dictionary where the keys are the scenes and the value their bounding rectangles only taking into account layer 0 of the image pyramid. [Same as in libCIZ](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#ab02ae7bcd25f34008ec9d5afa8a4efec). Example: `{ 0: (0, 0, 475, 325), 1: (500, 500, 900, 800) }`

**Important:** If there are no scenes, we return empty.

**`total_bounding_rectangle`**

_Returns:_ The bounding rectangle of the whole CZI. Same as [boundingBox](https://zeiss.github.io/libczi/structlib_c_z_i_1_1_sub_block_statistics.html#a924c2adf7f3e132470dfeb06ea1e958c).

**Note**: The total bounding rectangle can also be inferred from the X and Y values returned by the `total_bounding_box` call.

### Reading raw metadata

**`raw_metadata`**

_Returns:_ The raw xml metadata of the czi as a string.

### Reading metadata

**`metadata`**

_Returns:_ The raw metadata of the czi parsed into a dictionary.

### Reading custom attributes

**`custom_attributes_metadata`**

_Returns:_ The custom attributes list in a dictionary.

### Reading pixel type

**`get_channel_pixel_type(channel_index)`**

_Returns:_ The pixel type name for the required channel index, e.g. `"Gray8"`,
or `"Invalid"` for a nonexistent channel. There is no default argument.

**`pixel_types`**

_Returns:_ Dictionary of channel indices and pixel type names, e.g.
`{0: "Gray8", 1: "Bgr24"}`. The wrapper currently iterates zero-based channel
indices; use enumeration to inspect unusual/sparse channel coordinates.

LibCZI's strategy for finding a channel's pixel type is by checking the pixel type of the first subblock. This is further discussed in [**Discovery**](#discovery).

### Reading pixel data

LibCZI offers different ways of reading the pixel data:

![image info](doc/images/libczi_access_types.png)

We will use the [Single Channel Scaling Accessor](https://zeiss.github.io/libczi/classlib_c_z_i_1_1_i_single_channel_scaling_tile_accessor.html). And, to start simple, the python api should resemble what the [libCZI exposes](https://zeiss.github.io/libczi/classlib_c_z_i_1_1_i_single_channel_scaling_tile_accessor.html).

**Important** considerations regarding the Single Channel Scaling Accessor:

- Subblocks of different scenes CANNOT overlap. When they do, we get undefined behaviour. This assumption allows for no ambiguity about the returned data when the roi spans across multiple scenes.
- Images might have overlapping tiles/subblocks, this is particularly the case for non-stitched images. When getting pixel data from regions with overlapping subblocks (within the same scene), the subblock with the highest M-index wins.
  If tile-wise processing or any other processing that accounts for subblock arrangement is needed, new methods must be provided that bind to [libCZI's subblock accessor](https://zeiss.github.io/libczi/classlib_c_z_i_1_1_i_sub_block_repository.html).

#### `read(**kwargs)`

_Returns:_ The pixel data as a **numpy array**, the shape of the returned array and its data type will depend on the specified `pixel_type`.

- BGR pixel type -> [y, x, 3]
- Gray pixel type -> [y, x, 1]

This is further explained in the [pixel type parameter description](#pixel_type)

#### roi

**Optional.**
The **roi is a tuple** defined as a (axis-aligned) rectangle in (x, y, w, h) form, with:

- x: x coordinate of upper-left point
- y: y coordinate of upper-left point
- w: rectangle width
- h: rectangle height

The ROI is expressed in logical pixel coordinates, including negative origins
where present. Reads outside available coverage use the background color.

_Default:_ The roi default depends on the scene parameter:

- No scene parameter: The roi defaults to the total bounding rectangle (`total_bounding_rectangle`)
- Scene parameter specified: The roi defaults to the bounding box of the specified scene.

**Important:** For CZIs with scenes of different shapes, not specifying the roi will return different shapes of data for each scene.

**Please check the section on [scenes](#scenes) section for examples on how to handle CZIs with different scene arrangements.**

#### plane (read)

**Optional**  
The plane variable is a set of indices representing the coordinate of the planes to access. It is as dictionary whose keys are the dimension and the values are the coordinate value.
Example: dict {'C': 0, 'T': 1, 'Z': 4}

_Default:_ Omitted coordinates are derived from the wrapper's bounding ranges.
These start at zero for non-spatial axes in the current implementation. Do not
rely on this default for nonzero/negative-start or sparse acquisitions.

_Errors:_ If any plane coordinate falls outside the existing bounds, an error is raised.

**Note:** There might be indices with negative indices, and there is no logic to deal with this case. It is up to the caller to deal with such scenarios.

#### scene (read)

**Optional**  
The index of the scene to be considered. If set, only subblocks of the specified scene can contribute to the resulting bitmap.

_Default:_ All scenes will be considered.

**Note:** Scenes are not orthogonal to the other dimensions and must therefore be handled differently. For more information please check the section on [scenes](#scenes) section.

#### zoom

**Optional**  
A float between 0 (excluded) and 1 that specifies the zoom factor.

The purpose of the zoom factor (like the ROI) is to facilitate the handling of large data that does not fit into the available memory. Using a zoom factor smaller than one will return less data.

_Default:_ The zoom defaults to 1, in which case, the returned array will have the same X,Y shape of the used ROI. Smaller zoom factors will return an array whose X,Y shape are smaller (in the proportion of the zoom factor) than the used ROI. For zoom levels different than 1, allocating the output bitmap needs to be done in 2 calls.

_Errors:_ Zoom levels will throw at small enough levels.

#### pixel_type

**Optional.**
The pixel type of the returned data.

_Default:_ Defaults to the pixel type of the channel being read.

Since a pixel type is always used internally, there will always be an implicit pixel conversion done by libCZI which will take care of the issue of having subblocks with different pixel types in the same channel.

Reading pixel types is further explained in the section on [reading pixel data](#reading-pixel-data) section.

#### background_pixel

**Optional.**
The public wrapper accepts a three-value normalized color tuple or `Color`
for both grayscale and BGR output; default `(0, 0, 0)`. Components are floats
in `[0, 1]`, not raw uint16 intensities. `Color` fields are named `b`, `g`, `r`.
Use named fields for colored backgrounds. A scalar is not this API's contract.

Mask-aware composition is available through `ReaderOptions`, but `read()` does
not return a separate validity mask.

### Enumerating subblocks

Subblock enumeration provides header information without loading pixel data.
Header fields are not the per-subblock XML segment: public `CziReader` does not
expose direct tile decoding, subblock XML reads, or attachment reads.

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

    czi_doc.enumerate_subblocks_subset(
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

### Listing Subblock Snapshots

Older installed wheels may not contain this method. It returns immutable
snapshots of the stored directory entries without reading pixel payloads.

```python
from pylibCZIrw import czi

with czi.open_czi(file_path) as reader:
  blocks = reader.list_subblocks(plane={"C": 0}, scene=2, m_index=37)
  for block in blocks:
    print(block.index, block.coordinates, block.logical_rect, block.stored_shape)
```

`list_subblocks(*, plane=None, scene=None, m_index=None, level=None)` returns
`list[SubblockInfo]` in ascending file-local directory-index order. It reads
directory information only, not pixel, XML or mask payloads. The catalog is
materialized lazily; no constant-time or constant-memory guarantee is made.
The filters intersect; no matches gives `[]` and an empty plane mapping adds
no constraint. Unspecified coordinates remain unconstrained, not zero.

`plane` accepts a mapping with native `T`, `C`, `Z`, `R`, `I`, `H`, `V` and `B`
keys. Use `scene` for native S and `m_index` for native M. M can repeat across
planes/scenes/levels; listing retains every match. `level` is an opaque
nonnegative token from the returned descriptors, not a resolution ordinal or
zoom. Discover tokens rather than assuming zero means full resolution. Missing
tokens give `[]`, with no resampling/fallback. Classification uses exact logical
and stored geometry, retaining unclassified entries when no level is selected.

`SubblockInfo` is imported from `pylibCZIrw.czi`. Its eight required constructor
fields are `index`, `coordinates`, `m_index`, `logical_rect`, `stored_shape`,
`pixel_type`, `compression_mode` and `level_id`. It is a frozen dataclass with
an owned read-only coordinate mapping. The raw rectangle is `(x, y, width,
height)`; stored shape is `(height, width)`, without a component axis. M/level
absence is `None`; unknown raw compression identifiers are preserved. Directory
indices, M values and level tokens are distinct identities. Snapshots remain
usable after close; new listings through the closed reader raise `RuntimeError`.

Invalid selector types, including booleans as integers, raise `TypeError`;
invalid dimensions, absent-M sentinel selectors and negative level tokens raise
`ValueError`. Out-of-native-range scene/plane/M integers raise `OverflowError`.

### Counting Stored Subblocks

`count_subblocks(*, plane=None, scene=None, m_index=None, level=None)` returns
the number of matching stored directory entries. `count_subblocks_by_scene()`
accepts the same keyword-only filters and returns a dictionary of native scene
IDs to counts. Both use the listing filters and validation without reading
pixel, XML or mask payloads.

```python
with czi.open_czi(file_path) as reader:
  total = reader.count_subblocks()
  per_scene = reader.count_subblocks_by_scene()
  scene_total = reader.count_subblocks(scene=2)
  plane_total = reader.count_subblocks(scene=2, plane={"T": 3, "C": 5, "Z": 7})
```

Each stored subblock counts once, even when its M value repeats. Unfiltered
counts include all scenes, acquisition planes, stored levels and unclassified
entries; these are not counts of unique spatial positions. Filter `plane` and
use a discovered `level` token when counting tiles in one plane at one level.
Sparse scene IDs are preserved, and entries without S are grouped under the
`None` key, not scene zero. No matches returns `0` or `{}` respectively; the
per-scene result contains only scenes with matches. New calls after close raise
`RuntimeError`.

Bounding boxes describe spatial extent, not tile counts. Use
`total_bounding_box` for overall bounds and `scenes_bounding_rectangle` for
per-scene rectangles, or their `_no_pyramid` variants for layer-0 bounds. The
existing per-scene rectangle validation can reject sparse scene IDs; the new
counting methods use stored S coordinates and do not depend on that validation.

### Reading Stored Subblock Pixels

The F01 development build adds `read_subblock(index)` and
`read_subblock_by_m(m_index, *, plane=None, scene=None, level=None)` to
`CziReader`. These methods decode one stored subblock, without composition,
cropping, resampling, stacking or stitching. Directory indices are not M values
or positions in a filtered listing.

The following selectors use the admitted
[sparse-coordinate fixture](pylibCZIrw/tests/integration/test_data/synthetic/stored_sparse_coordinates.czi)
as `file_path`; inspect your file's listing for its actual selectors.

```python
from pylibCZIrw import czi

with czi.open_czi(file_path) as reader:
  plane = {"T": 3, "C": 5, "Z": 7}
  blocks = reader.list_subblocks(m_index=37, scene=2, plane=plane)
  for block in blocks:
    pixels = reader.read_subblock(block.index)
    print(block.logical_rect, pixels.shape)

  pixels = reader.read_subblock_by_m(37, scene=2, plane=plane)
```

`read_subblock` accepts its index positionally or by keyword; it has no scene,
plane, zoom or output-type selectors. It returns the stored shape: YX for
grayscale, YXA for color. Supported native layouts are Gray8, Gray16,
Gray32Float, Bgr24, Bgr48 and Bgr96Float. Dtype and native BGR component order
are preserved, without RGB conversion. Returned arrays retain their bitmap
owner after reader close/deletion; no mandatory copy or zero-copy promise is
made. Placement remains in the descriptor's raw `logical_rect`, not the array.

`read_subblock_by_m` applies exactly the listing filters and reads pixels only
if **one** directory entry matches. Zero or multiple matches raise `ValueError`
with selectors and match count **before payload reads**. M can repeat across
scenes, planes and levels. Omitting `scene` means `scene=None`: all scenes remain
eligible, not an implicit scene zero. Supply `scene=0` to restrict to scene zero.
Omitting `level` tests uniqueness across all levels;
it does not mean full resolution. Use a token from `list_subblocks()` to select
a stored level; an unmatched token never triggers fallback. To read multiple
matches, iterate the descriptors and read their indices as above.

M remains an explicit required `m_index` argument for this M-specific helper;
`plane` is not a general coordinate dictionary and does not accept `M` or `S`.
The same selector convention applies to `list_subblocks()`, where M is optional.
A general `selection`/`coordinates` dictionary API is not currently provided.

These methods return original decoded pixels, including zero intensities;
they do not apply or decode validity masks, even with mask-aware composed reads
enabled. Stored XML and masks are retrieved explicitly below. Existing `read()`
and callback enumeration retain their existing behavior.

Wrong types (including Boolean integers) raise `TypeError`; negative or missing
directory indices, including unrepresentable indices, raise `IndexError`.
Selector validation follows `list_subblocks()`; M is required and cannot be
`None`. Unsupported pixel layout/codec or corrupt pixel payloads raise
`ValueError`, genuine stream failures raise `OSError`, and unrepresentable
decoded sizes raise `OverflowError`. Native failure causes are preserved.
New calls after close raise `RuntimeError`; previously returned arrays remain
usable.

### Reading selected XML and masks

```python
reader.read_subblock_metadata_xml(index: int) -> str | None
reader.read_subblock_mask(index: int) -> np.ndarray | None
```

These select one actual subblock directory index, not its M value. XML is the
original strict UTF-8 text, with unknown elements and whitespace preserved.
Absent XML returns `None`; malformed but UTF-8-decodable XML remains retrievable.
Parsing is a separate caller operation. Invalid UTF-8 raises `UnicodeDecodeError`;
I/O errors raise `OSError`, not `None`. Global metadata remains separate.

Masks are owned YX Boolean arrays at the stored bitmap's resolution. `True`
means valid; absence returns `None`, while corrupt or unsupported stored masks
raise `ValueError`. No composite-coverage mask is synthesized. A mask does not
rewrite a direct subblock read. To apply it explicitly:

```python
with czi.open_czi(filepath) as reader:
  block = reader.list_subblocks()[0]
  xml = reader.read_subblock_metadata_xml(block.index)
  mask = reader.read_subblock_mask(block.index)
  pixels = reader.read_subblock(block.index)
  masked = pixels if mask is None else np.where(
      mask if pixels.ndim == 2 else mask[..., None], pixels, 0)
```

Both operations avoid pixel decoding, but the native selected-subblock read
loads its stored pixel payload and optional attachment as well as XML. This is
**not XML-only I/O**. Unselected subblocks are not loaded. Returned values remain
valid after close; new calls after close raise `RuntimeError`. Index validation
and native error mappings match `read_subblock()`.

See [the XML/mask display demo](demo_scripts/06_subblock_xml_and_mask.py).

### Reading exact stored levels

```python
reader.list_stored_levels(*, plane=None, scene=None) -> list[StoredLevelInfo]
reader.read_stored_level(level, *, plane=None, scene=None, roi=None) -> np.ndarray
```

Discovery is directory-only. Each frozen `StoredLevelInfo` contains the required
fields `level_id`, read-only `coordinates`, raw logical XYWH `logical_rect`,
exact member `subblocks`, exact Y/X `Fraction` pair `downsample`, and YX
`output_shape`. A descriptor describes one native scene/plane group. Tokens
are the same file-local opaque tokens used by `list_subblocks()`, not ordered
resolution numbers or M values. Do not assume identical inventories across
scenes/planes. Unclassified nonpositive geometry remains visible in
`list_subblocks()` but does not create a stored-level group.

Reads require exactly one matching scene/plane group before considering ROI.
Missing or ambiguous groups raise contextual `ValueError`; they never fall back
to another level, scene, or plane. Current composition supports exact positive
isotropic integer reductions, including non-powers of two. Other discovered
ratios have `output_shape=None` and raise `ValueError` on read rather than being
approximated. All selected members must share a supported native pixel layout.

ROI is a tuple or `Rectangle` of signed-native-integer `(x, y, width, height)`
in raw level-0 coordinates, preserving negative origins. It defaults to the
descriptor's logical union. For reduction `p`, output YX is
`(height // p, width // p)`; remainders are dropped. Relative signed tile offsets
truncate toward zero. Nonpositive/zero-output extents and unsafe conversions
are rejected. No scaling accessor, resampling, or `zoom` fallback is involved.

Uncovered pixels are initialized to zero after level availability is confirmed.
This is not validity information. Overlaps follow ascending valid M, highest M
on top; absent M sorts first. Equal/absent-M ties have no portable winner promise.
`ReaderOptions(enable_mask_awareness=True)` applies valid stored masks during
composition and raises on corrupt masks. The default is mask-unaware. The
current mask-aware path reads each intersecting selected subblock again to
obtain its mask; do not infer single-read or zero-copy behavior.

Output is YX grayscale or native-BGR YXA, with the same six layouts as direct
reads. Returned arrays/descriptors survive close. Existing `read()` and `zoom`
behavior is unchanged. See [the composition/ROI demo](demo_scripts/07_compose_stored_level.py).

### Reading attachments

```python
reader.list_attachments() -> list[AttachmentInfo]
reader.read_attachment(index: int) -> bytes
reader.read_attachment_image(index: int) -> np.ndarray
reader.read_label(*, index: int | None = None) -> np.ndarray | None
reader.read_preview(*, index: int | None = None) -> np.ndarray | None
```

Frozen `AttachmentInfo` requires `index`, `name`, `content_file_type` and
`content_guid` (`uuid.UUID`); `size_bytes` defaults to `None`. Listing reads the
native directory without fetching payloads or decoding images. Indices are
file-local identities; duplicate names remain separate entries. Native directory
sizes are unavailable, so `None` means unknown, not zero.

Raw reads return the exact selected bytes, even for unknown or corrupt image
formats. Explicit image reads support embedded `CZI` attachments containing one
full-resolution native scene/plane with a supported layout. libCZI opens an
attachment-backed memory stream; no disk roundtrip or second parser is used.
Multiple full-resolution planes or unsupported geometry/layouts are rejected,
not silently flattened or resampled. Output is YX grayscale or native-BGR YXA
with uint8, uint16 or float32 dtype; BGR is not automatically converted to RGB.

`read_label()` matches `Label`; `read_preview()` matches `SlidePreview`.
No match returns `None`. Duplicate names raise `ValueError` unless a keyword
`index` explicitly selects an attachment. That index selects exactly its payload,
even if its name differs. Invalid indices, unsupported formats and corrupt
images raise errors without substitution or conversion to `None`. Wrong index
types/Boolean integers raise `TypeError`; negative, missing or unrepresentable
indices raise `IndexError`. Native parse/decode failures raise `ValueError`,
stream failures `OSError`, and unsafe size conversions `OverflowError`.

Raw and image reads materialize the selected payload in memory. Raw access also
creates native string/Python-byte copies; image access additionally retains
decoded input/output bitmaps. Size arithmetic is checked, with no arbitrary
payload cap, streaming, fixed-memory-bound or zero-copy guarantee. Unrelated
attachment payloads are not loaded. Memory use depends on the selected payload
and decoded image size; small-fixture checks do not establish a large-file bound.

Descriptors, bytes and image arrays remain valid after parent/embedded readers
close. New calls after close raise `RuntimeError`. Attachment editing and
recursive/universal image decoding are outside this API.
See [the label/preview display demo](demo_scripts/08_attachment_images.py).

## Creating a CZI

Like with opening, creating a new empty CZI can be done in a context manager using a [path-like-object](https://docs.python.org/3/library/os.html#os.PathLike) (in this case, file_path).

`with czi.create_czi(file_path) as czi:`

This creates a new czi file at the provided path and **opens it in write mode.**  
**Note:** Any intermediate-level directories needed to contain the leaf directory are generated if necessary.  
**Note:** Per default, a [FileExistsError](https://docs.python.org/3/library/exceptions.html#FileExistsError) is raised in case `file_path` already exists. The error can be ignored by calling  
`with czi.create_czi(file_path, exist_ok = True) as czi:`

The default compression can be overridden per write:
`with czi.create_czi(file_path, exist_ok=True, compression_options="zstd0:") as writer:`
`exist_ok=True` permits overwriting; it is not append or modify mode.

## Writing a CZI

### Writing pixel data

For the sake of consistency, we want to write data similarly to how we read it.

#### `write(data, **kwargs)`

Writes a 2D plane or tile at a location, splitting large input into subblocks.
Returns `bool` indicating success.

#### data

**Required.**

The data (numpy array) to be written.

Grayscale input has shape `[Y, X]` or `[Y, X, 1]`.
BGR input has shape `[Y, X, 3]`. Supported dtypes are `uint8`, `uint16`, and
`float32`; the last axis is a color component, not the C acquisition dimension.

The pixel type in which to write the data will be inferred from the numpy array data type following the rules described in [**Writing Pixel Data**](#writing-pixel-data).

**Note:** Color input is BGR. Convert RGB input using
`bgr = np.ascontiguousarray(rgb[..., ::-1])`.

Inputs larger than 10,000,000 bytes trigger automatic tiling. The current
splitter uses fixed spatial extents, not a strict per-subblock byte budget.

#### location

**Optional.**

The pixel coordinates of the upper-left pixel. This allows writing data in different regions in the selected 2D plane.

_Default:_ Default value is (0, 0).

The wrapper assigns a new M-index to each tile. Do not treat overlapping writes
as replacement or as a transaction; use the intended tile-composition semantics.

#### plane (write)

**Optional.**

Same concept of the read method. A dictionary specifying the plane coordinates of the data to be written.
Example: dict {'C': 0, 'T': 1, 'Z': 4}

The current writer retains only T/C/Z/S entries; other keys are discarded by
`_create_plane()`. Set the scene through `scene=`. Full R/I/H/V/B dimension
writing is a proposed extension, not current public behavior.

An M index is cached per plane so that every new subblock written to the plane gets the next M-index (this is hidden from the user).

_Default:_ All planes will default to 0, meaning that the size of each plane coordinate is at least 1.

_Errors:_ If there is data with a different pixel type in the specified plane, the write call will raise an exception.

#### compression_options

**Optional.**

String representation of compression options.

_Default:_ If no compression_options is specified, the writer's default is used.

#### scene (write)

**Optional.**

An integer specifying the scene index.

_Default:_ If no scene index is specified the result document will have a single scene with index 0.

### Writing metadata

Metadata can be explicitly written with

**`write_metadata(document_name, channel_names, scale_x, scale_y, scale_z, custom_attributes, display_settings)`**

If not explicitly written, metadata will be automatically written when closing the file.

The writer prepares XML through libCZI metadata helpers. This public call updates
document information, channels, scaling, custom attributes, and display settings;
it is not a general raw-XML or per-subblock-metadata write interface.

#### document_name

**Optional.**

The document name is an optional string parameter that sets the value of the Document.Title metadata node.

#### channel_names

**Optional.**

The channel names parameter maps channel indices to name strings.

**For now, we will only support changing the channel name**. So the only valid format is: `{ 0: "C1", 1: "C2" }`

Channel names are strings. Channel tint/color is handled separately through
`display_settings`, not through an arbitrary nested channel-name dictionary.

#### scale_x

**Optional.**

scale_x is an optional float parameter that indicates the extent of a pixel in x-direction (in units of m) in the document.

#### scale_y

**Optional.**

scale_y is an optional float parameter that indicates the extent of a pixel in y-direction (in units of m) in the document.

#### scale_z

**Optional.**

scale_z is an optional float parameter that indicates the extent of a pixel in z-direction (in units of m) in the document.

#### custom_attributes

**Optional.**

custom_attributes is an optional dictionary parameter that contains customized key-value pairs.

#### display_settings

**Optional.**

display_settings is an optional dictionary of display settings, where key is channel number and value is the corresponding display setting.

Values are `ChannelDisplaySettingsDataClass` instances; the restriction to
bool/int/float/str applies to `custom_attributes`, not display settings.

#### Writing Example

The following code illustrates how one can write a czi in a machine learning context.

```python
import numpy as np
from pylibCZIrw import czi

data = inference_service.run()  # shape [2, Y, X], supported dtype
settings = {
  0: czi.ChannelDisplaySettingsDataClass(
    True, czi.TintingMode.Color,
    czi.Rgb8Color(np.uint8(0), np.uint8(0), np.uint8(255)), 0.2, 0.8,
  ),
  1: czi.ChannelDisplaySettingsDataClass(
    True, czi.TintingMode.Color,
    czi.Rgb8Color(np.uint8(0), np.uint8(255), np.uint8(0)), 0.3, 0.75,
  ),
}
with czi.create_czi(path, compression_options="zstd1:ExplicitLevel=2") as writer:
  writer.write(data[0], plane={"C": 0}, location=(0, 0))
  writer.write(data[1], plane={"C": 1}, location=(0, 0))
  writer.write_metadata(
    channel_names={0: "Nuclei", 1: "Background"},
    scale_x=0.1e-6, scale_y=0.1e-6,
    custom_attributes={"key1": "value1", "key2": "value2"},
    display_settings=settings,
  )
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

| Pixel type  | NumPy dtype | Read shape |
|-------------|-------------|------------|
| Gray8       | uint8       | Y, X, 1    |
| Gray16      | uint16      | Y, X, 1    |
| Gray32Float | float32     | Y, X, 1    |
| Bgr24       | uint8       | Y, X, 3    |
| Bgr48       | uint16      | Y, X, 3    |
| Bgr96Float  | float32     | Y, X, 3    |

When reading, one can specify a destination pixel type. When the requested pixel type is different than the source's, libCZI converts it. The conversion is done as documented in the [libCZI documentation](https://zeiss.github.io/libczi/accessors.html):

![pixel type conversion](doc/images/pixel_type_conversion.png)

**Important:** The trailing component dimension is 3 for BGR output, including
Bgr96Float, and 1 for grayscale output.

This is similar to what is done in [aicspylibczi](https://github.com/AllenCellModeling/aicspylibczi/blob/575c440c6bf6a0a481dabd0b4ae4eb67f89dda26/aicspylibczi/CziFile.py#L342).

##### Writing

The writer infers pixel type from dtype and the trailing component axis using
the same table. It does not convert dtype or RGB to BGR and has no `pixel_type=`
argument. Supply a supported dtype/shape explicitly.

### Masks

Regions with no data will be filled by libCZI with the background color. There is therefore no way to tell between a pixel having the color of the background or being really background/invalid.

_A hacky way of figuring it out is to request the same data twice with different background colors._

The real solution to this problem is by leveraging the mask data that exists in the CZI. Masks indicate regions with invalid or no data. There are two cases:

- simple case: there is no subblock at aspecific location
- advanced case: there is a subblock with mask data, indicating that there are parts with invalid pixels

libCZI now exposes subblock masks and supports mask-aware composition.
Set `ReaderOptions(enable_mask_awareness=True)` to use them during composition.
The public reader still returns only the image, not a validity-mask array.

### Scenes

Scenes are not orthogonal to the other dimensions, they can be though of as "tags". Thus, handling them as other dimensions will cause more problems than it would help.

In a nutshell:
**The scene-index is not part of a plane-coordinate**

The arrangement below is possible:

![image info](doc/images/scenes.png)

Getting the dimensions of this CZI would show these scenes having the following bounding boxes:

**S0:** X=0, Y=0, W=100, H=100
**S1:** X=80, Y=80, W=100, H=100

For non-spatial dimensions, a fixed ROI can be reused, but coverage and available
coordinates may vary by scene or plane.
However, in the situation above, looping through scenes with the same ROI would produce bogus data:

![image info](doc/images/read_scenes.png)

So to avoid confusion we treat scenes differently. By having to deal with scenes separately, users will know that they're not just another dimension.

#### Images with no scenes

The scene-guide fragments below assume an active `CziReader` named `reader`
inside `with czi.open_czi(file_path) as reader:`. Reported rectangles are
illustrative `(x, y, width, height)` values, not captured runtime output.

Let's say we have a single-channel CZI time series with no scenes:

![simple czi](doc/scenes/no_scenes.png)

**Get dimensions information:**

```python
total_bounding_box = reader.total_bounding_box
scene_bounding_rectangle = reader.scenes_bounding_rectangle
total_bounding_rectangle = reader.total_bounding_rectangle

print(total_bounding_box)
# {'C': (0, 1), 'T': (0, 5), 'Z': (0, 1), 'X': (0, 400), 'Y': (0, 600)}
print(scene_bounding_rectangle)
# {}
print(total_bounding_rectangle)
# '(0, 0, 400, 600)'
```

**Default read (no ROI).**

```python
for t in t_enumerable:
    data = reader.read(plane={"T": t})
```

Returns:

![default read](doc/scenes/no_scenes.png)

**Specifying ROI:**

```python
for t in t_enumerable:
    roi = (0, 0, 200, 200)
    data = reader.read(roi=roi, plane={"T": t})
```

Returns:

![read at roi](doc/scenes/no_scenes_result_roi.png)

#### Images with non-uniform scenes

Let's say we have a single-channel time series and z-stack CZI with scenes:

![multi-scene czi](doc/scenes/scenes_image.png)

**Get dimensions information:**

```python
print(total_bounding_box)
# {'C': (0, 1), 'T': (0, 5), 'Z': (0, 2), 'X': (0, 2000), 'Y': (0, 1400)}
```

In this case, scenes have different sizes/bounding boxes:

![bounding boxes](doc/scenes/bounding_boxes.png)

```python
print(scene_bounding_rectangle)
# { 0: (800, 0, 1200, 500), 1: (0, 200, 1000, 1200), 2: (900, 600, 1100, 800)}
print(total_bounding_rectangle)
# Rectangle(x=0, y=0, w=2000, h=1400)
```

**Default read (no ROI).**

If no scene is specified the call:

```python
data_all_scenes = reader.read()
```

Will have the following defaults:

- ROI = total_bounding_rectangle = (0, 0, 2000, 1400)
- Planes = { 'C': 0, 'T': 0, 'Z': 0 }

And return the following data:

![read no roi](doc/scenes/read_all_scenes.png)

If a scene is specified the call:

```python
data = reader.read(scene=1)
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

data_all_scenes = reader.read(roi=roi)
data_s1 = reader.read(roi=roi, scene=1)
```

Returns:

![read at roi](doc/scenes/read_roi.png)

#### Images with uniform scenes

Let's consider an image with scenes of consistent shape, like a multi-well where each scene corresponds to a well.

![multi-well](doc/scenes/multi_well.png)

The logic above is unaltered, but we will most likely not want to read data at ROIs spanning across multiple scenes. Instead, we would like to iterate over the scenes and get the scene/well data.

This can be done as follows:

```python
total_bounding_box = reader.total_bounding_box
scene_bounding_rectangle = reader.scenes_bounding_rectangle
total_bounding_rectangle = reader.total_bounding_rectangle

print(total_bounding_box)
# Includes C/Z/T defaults and X/Y half-open bounds.
print(scene_bounding_rectangle)
# Rectangles have x/y/w/h, not x/y/right/bottom.
print(total_bounding_rectangle)
# '(0, 0, 1000, 1000)'
```

```python

for scene_index, roi in scene_bounding_rectangle.items():
  data = reader.read(roi=roi, scene=scene_index)
```

Specify the scene even when using its ROI: scenes can overlap, and an ROI alone
does not filter contributions from another scene. A CZI scene is not necessarily
a biological well; HCS plate/well/field semantics come from metadata.

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
with edit_czi(file_path) as editor:
  assert editor.is_open
  xml = editor.read_metadata_xml()
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
with edit_czi(file_path) as editor:
  with editor.edit_session() as builder:
    builder.set_general_document_info(title="Processed")
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
with edit_czi(file_path) as editor:
  builder = editor.create_metadata_builder()
  builder.set_general_document_info(
    info=GeneralDocumentInfoDto(title="New Title"),
    user_name="EditorUser",
    comment="Edited by API",
  )
  builder.set_scaling_info(scale_x=0.25, scale_y=0.25)
  if builder.can_commit():
    builder.commit()
  info = editor.read_general_document_info()
  scaling = editor.read_scaling_info()
```

### Example: update display settings for an existing channel

```python
from pylibCZIrw.czi import edit_czi, Rgb8Color, TintingMode, ChannelDisplaySettingsDataClassWithNameAndDescription
import numpy as np

with edit_czi(file_path) as editor:
  ds = ChannelDisplaySettingsDataClassWithNameAndDescription(
    is_enabled=True,
    tinting_mode=TintingMode.Color,
    tinting_color=Rgb8Color(r=np.uint8(255), g=np.uint8(0), b=np.uint8(0)),
    black_point=0.05,
    white_point=0.95,
    description="Edited by API",
  )
  with editor.edit_session() as builder:
    builder.set_display_settings({0: ds})

```

Notes

- Builder setters merge DTO values with explicit keyword arguments; keywords override DTO fields when provided.
- Unspecified fields are not written, preserving existing metadata.
- `read_display_settings()` may return an empty map for files without display settings.
- `read_custom_key_value(key)` returns the current value as a native type when present.
- `write_metadata(scale_x/y/z=...)` uses meters. The editor's scaling DTO/setter
  uses the document's existing default unit (typically microns); do not pass the
  same numbers between these APIs without checking units.
- Staging builder edits is not an atomic filesystem transaction or rollback
  guarantee. `CziEditor` only exposes metadata operations, not pixel replacement.
