"""Module implementing the czi interface

The open method will create a czi document.
This czi document can be used to read and write czi.
"""

import contextlib
import uuid
from dataclasses import dataclass
from enum import Enum
from os import makedirs
from os.path import abspath, dirname, isfile
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterator,
    NamedTuple,
    Optional,
    Tuple,
    Union,
)

import numpy as np
import validators
import xmltodict

import _pylibCZIrw

Rectangle = NamedTuple("Rectangle", [("x", int), ("y", int), ("w", int), ("h", int)])
Location = NamedTuple("Location", [("x", int), ("y", int)])
Color = NamedTuple("Color", [("b", float), ("g", float), ("r", float)])


class TintingMode(Enum):
    """TintingMode enum.

    This enum specifies the "tinting-mode" - how the channel is false-colored.
    """

    # Gives the "original color", ie. in case of RGB the RGB-value is directly used,
    # in case of grayscale we get a gray pixel.
    none = 0
    # The pixel value is multiplied with the tinting-color.
    Color = 1


class ReaderFileInputTypes(Enum):
    """ReaderFileInputTypes enum.

    This enum specifies the "file input types for the czi reader" - if the file is local or a url.
    """

    # The file is present on the local storage.
    Standard = "standard"
    # The file is present on a curl accessible url.
    Curl = "curl"


class CacheType(Enum):
    """CacheType enum.

    Specifies the supported types of subblock caches..
    """

    Standard = 1  # Currently only one standard type of cache is supported


@dataclass
class CacheOptions:
    """Cache options data structure.

    Data structure to represent the configuration of the cache.
    """

    type: CacheType = CacheType.Standard
    max_memory_usage: Optional[int] = None
    max_sub_block_count: Optional[int] = None


@dataclass
class ReaderOptions:
    """Reader options data structure.

    Configuration options for CZI reader.
    """

    enable_mask_awareness: bool = False
    """Whether the accessor will use the valid-pixel-mask for the tile-composition."""

    enable_visibility_check_optimization: bool = True
    """Whether the accessor will use the visibility-check-optimization for the tile-composition."""

    lax_subblock_coordinate_checks: bool = True
    """Whether to use lax parameter validation when parsing subblock dimension entries.
    The default (True) is lenient for compatibility with older files. Set to False for strict validation."""

    ignore_sizem_for_pyramid_subblocks: bool = False
    """Whether to ignore the size-M attribute of pyramid subblocks.
    Only relevant when lax_subblock_coordinate_checks is False.
    Useful for CZI files with bogus SizeM values."""


@dataclass
class Rgb8Color:
    """Rgb8Color class.

    A structure representing an R-G-B-color triple (as bytes).
    """

    r: np.uint8  # The red component.
    g: np.uint8  # The green component.
    b: np.uint8  # The blue component.


@dataclass
class ChannelDisplaySettingsDataClass:
    """ChannelDisplaySettingsDataClass class.

    This dataclass is intended to capture all information found inside an IChannelDisplaySetting-object.
    It allows for easy modification of the information.
    """

    # A bool indicating whether the corresponding channel is 'active' in the multi-channel-composition.
    # Default value should be 'false'.
    is_enabled: bool
    # The tinting mode.
    # Default value should be 'TintingMode.none'.
    tinting_mode: "TintingMode"
    # The tinting color (only valid if tinting mode == Color).
    tinting_color: "Rgb8Color"
    # The (normalized) black point value.
    # Default value should be '0'.
    black_point: float
    # The (normalized) white point value.
    # Default value should be '1'.
    white_point: float


class CziReader:
    """CziReader class.

    _czi_reader : object
        c++ bonded object, corresponding to an instance of the CZIreadAPI class.
    _stats : object
         c++ bonded object, corresponding to an instance of the libCZI::SubBlockStatistics class.
    CZI_DIMS : Dict[str, int]
        Dictionary matching a dimension with the c++ libCZI::DimensionIndex enum value.
        The Scene dimension was excluded on purpose to avoid confusion to the users of pylibCZIrw.
        In fact S is a filter and SHOULD NOT be considered as a plane dimension.
    PIXEL_TYPES : Dict[str, int]
        Dictionary matching a pixel type with the c++ libCZI::PixelType enum value.
    """

    BLACK_COLOR = Color(0, 0, 0)

    PIXEL_TYPES: Dict[str, int] = {
        "Gray8": 0,  # Grayscale 8-bit unsigned.
        "Gray16": 1,  # Grayscale 16-bit unsigned.
        "Gray32Float": 2,  # Grayscale 4 byte float.
        "Bgr24": 3,  # BGR-color 8-bytes triples (memory order B, G, R).
        "Bgr48": 4,  # BGR-color 16-bytes triples (memory order B, G, R).
        "Bgr96Float": 8,  # BGR-color 4 byte float triples (memory order B, G, R).
    }

    CZI_DIMS: Dict[str, int] = {
        "Z": 1,  # The Z-dimension.
        "C": 2,  # The C-dimension ("channel").
        "T": 3,  # The T-dimension ("time").
        "R": 4,  # The R-dimension ("rotation").
        "I": 6,  # The I-dimension ("illumination").
        "H": 7,  # The H-dimension ("phase").
        "V": 8,  # The V-dimension ("view").
        "B": 9,  # The B-dimension ("block") - its use is deprecated.
    }

    CACHE_TYPE_LUT = {
        CacheType.Standard: _pylibCZIrw.CacheType.Standard,
    }

    def __init__(
        self,
        filepath: str,
        file_input_type: ReaderFileInputTypes = ReaderFileInputTypes.Standard,
        cache_options: Optional[CacheOptions] = None,
        reader_options: Optional[ReaderOptions] = None,
    ) -> None:
        """Creates a czi reader object, should only be called through the open_czi() function.

        Parameters
        ----------
        filepath : str
            File path.
        file_input_type : ReaderFileInputTypes
            This is used to set if the filepath is to a local path or url. Defaults to local path.
        cache_options:
            The configuration of a subblock cache to be used.
        """
        libczi_cache_options = self._create_default_cache_options(cache_options=cache_options)
        libczi_reader_options = self._create_reader_options(reader_options=reader_options)

        if file_input_type is ReaderFileInputTypes.Curl:
            if validators.url(filepath):
                # When reading from CURL stream we assume that the connection is slow
                # And therefore also cache uncompressed subblocks.
                libczi_cache_options.cacheOnlyCompressed = False
                self._czi_reader = _pylibCZIrw.czi_reader(
                    ReaderFileInputTypes.Curl.value,
                    filepath,
                    libczi_cache_options,
                    libczi_reader_options,
                )
            else:
                raise FileNotFoundError(f"{filepath} is not a valid URL.")
        else:
            # When reading from disk we only cache compressed subblocks.
            libczi_cache_options.cacheOnlyCompressed = True
            # use the "standard reader class name" for local files
            self._czi_reader = _pylibCZIrw.czi_reader(
                ReaderFileInputTypes.Standard.value,
                filepath,
                libczi_cache_options,
                libczi_reader_options,
            )
        self._stats = self._czi_reader.GetSubBlockStats()

    @classmethod
    def _create_default_cache_options(cls, cache_options: Optional[CacheOptions]) -> _pylibCZIrw.SubBlockCacheOptions:
        sub_block_cache_options = _pylibCZIrw.SubBlockCacheOptions()
        sub_block_cache_options.Clear()
        if cache_options:
            native_cache_type = None
            native_enum = getattr(_pylibCZIrw, "CacheType", None)
            if native_enum is not None:
                native_cache_type = getattr(native_enum, cache_options.type.name, None)
            if native_cache_type is None:
                native_cache_type = cls.CACHE_TYPE_LUT.get(cache_options.type)
            if native_cache_type is not None:
                sub_block_cache_options.cacheType = native_cache_type
            if cache_options.max_memory_usage is not None:
                sub_block_cache_options.pruneOptions.maxMemoryUsage = cache_options.max_memory_usage
            if cache_options.max_sub_block_count is not None:
                sub_block_cache_options.pruneOptions.maxSubBlockCount = cache_options.max_sub_block_count
        return sub_block_cache_options

    def close(self) -> None:
        """Close the document and finalize the reading"""
        self._czi_reader.close()

    @staticmethod
    def _create_reader_options(
        reader_options: Optional[ReaderOptions],
    ) -> _pylibCZIrw.ReaderOptions:
        """Creates a ReaderOptions object from the ReaderOptions dataclass.

        Parameters
        ----------
        reader_options : ReaderOptions
            Reader options dataclass

        Returns
        -------
        : _pylibCZIrw.ReaderOptions
            Reader options object.
        """
        libczi_reader_options = _pylibCZIrw.ReaderOptions()
        libczi_reader_options.Clear()
        if reader_options:
            libczi_reader_options.enableMaskAwareness = reader_options.enable_mask_awareness
            libczi_reader_options.enableVisibilityCheckOptimization = (
                reader_options.enable_visibility_check_optimization
            )
            libczi_reader_options.laxSubblockCoordinateChecks = reader_options.lax_subblock_coordinate_checks
            libczi_reader_options.ignoreSizeMForPyramidSubblocks = reader_options.ignore_sizem_for_pyramid_subblocks
        return libczi_reader_options

    @staticmethod
    def _compute_index_ranges(
        rectangle: _pylibCZIrw.IntRect,
    ) -> Dict[str, Tuple[int, int]]:
        """From a bounding rectangle (_pylibCZIrw.IntRect object, which is a struct with (x, y, h, w),
        returns the X Y index ranges.

        Parameters
        ----------
        rectangle : _pylibCZIrw.IntRect
            C++ struct representing a bounding rectangle
        Returns
        ----------
        : Dict[str, Tuple[int, int]]
            Dictionary containing the range of X and Y dimensions in the czi document
            for example: {'X': (0, 975), 'Y': (0, 825)}
        """
        return {
            "X": (rectangle.x, rectangle.x + rectangle.w),
            "Y": (rectangle.y, rectangle.y + rectangle.h),
        }

    @property
    def total_bounding_box(self) -> Dict[str, Tuple[int, int]]:
        """Returns the total bounding box of the czi document.

        The bounding box consists
        of the range of all dimension that exists in the document. The dimension that can be stored
        in the czi are the one present in the CZI_DIMS dictionary.
        If the dimension does not exist in the czi document it won't be specified in the returned
        dictionary.
        Additionally, we add the X and Y ranges of the total bounding rectangle of the czi.

        Returns
        ----------
        total_bounding_box : Dict
            Dictionary containing the range of each dimensions in the czi document
            for example: {'C': (0, 3), 'Z': (0, 4), 'T': (0,7), 'X': (0, 975), 'Y': (0, 825)}
        """
        total_bounding_box = {
            "T": (0, 1),
            "Z": (0, 1),
            "C": (0, 1),
        }  # T Z and C dimension should always be of size
        # 1 even if not present in the CziReader document

        # Getting CZI_DIMS size
        for dim, dim_index in self.CZI_DIMS.items():
            dimension_size = self._czi_reader.GetDimensionSize(_pylibCZIrw.DimensionIndex(dim_index))
            if dimension_size > 0:
                total_bounding_box[dim] = (0, dimension_size)

        # Getting X Y
        total_bounding_box.update(self._compute_index_ranges(self._stats.boundingBox))

        return total_bounding_box

    @property
    def total_bounding_box_no_pyramid(self) -> Dict[str, Tuple[int, int]]:
        """Returns the total bounding box of the czi document for layer0 only.
        Pyramid sometimes leads to have more pixels in later layers.
        We can get the original no. of pixels from layer 0 only.

        The bounding box consists
        of the range of all dimension that exists in the document. The dimension that can be stored
        in the czi are the one present in the CZI_DIMS dictionary.
        If the dimension does not exist in the czi document it won't be specified in the returned
        dictionary.
        Additionally, we add the X and Y ranges of the total bounding rectangle of the czi.

        Returns
        ----------
        total_bounding_box : Dict
            Dictionary containing the range of each dimensions in the czi document
            for example: {'C': (0, 3), 'Z': (0, 4), 'T': (0,7), 'X': (0, 975), 'Y': (0, 825)}
        """
        total_bounding_box_layer0 = {
            "T": (0, 1),
            "Z": (0, 1),
            "C": (0, 1),
        }

        # Getting CZI_DIMS size
        for dim, dim_index in self.CZI_DIMS.items():
            dimension_size = self._czi_reader.GetDimensionSize(_pylibCZIrw.DimensionIndex(dim_index))
            if dimension_size > 0:
                total_bounding_box_layer0[dim] = (0, dimension_size)
        # Getting X Y
        total_bounding_box_layer0.update(self._compute_index_ranges(self._stats.boundingBoxLayer0Only))

        return total_bounding_box_layer0

    def _extract_scenes_bounding_rectangles(
        self,
        extract_scene_bounding_box: Callable[[_pylibCZIrw.BoundingBoxes], Rectangle],
    ) -> Dict[int, Rectangle]:
        """Get the bounding rectangle of all scenes in the document and returns it
        in a dictionary where scene indexes are the keys and the bounding rectangles the values.
        bounding rectangle are tuples following (x, y, h, w) with:

        x y - coordinates of the top left corner
        h - height of the rectangle
        w - width of the rectangle

        Arguments:
            extract_scene_bounding_box: A function that extracts a rectangle from the
            bounding boxes in the subblock statistics.

        Returns
        ----------
        scenes_bounding_rectangle : Dict[int, Rectangle]
            dictionary containing all scenes bounding rectangle
            for example: { 0: (0, 0, 475, 325) }, { 1: (500, 500, 900, 800) }
        """
        scenes_bounding_rectangle = {}

        n_scenes_metadata = self._czi_reader.GetDimensionSize(_pylibCZIrw.DimensionIndex.S)
        n_scene_bounding_boxes = len(self._stats.sceneBoundingBoxes)
        if n_scenes_metadata != n_scene_bounding_boxes:
            raise ValueError(
                f"The number of scenes in the meta data ({n_scenes_metadata}) "
                f"does not match the number of available scene bounding boxes ({n_scene_bounding_boxes})."
            )

        for scene_id, scene_bounding_box in self._stats.sceneBoundingBoxes.items():
            scene_bounding_box_extracted = extract_scene_bounding_box(scene_bounding_box)
            scenes_bounding_rectangle[scene_id] = Rectangle(
                scene_bounding_box_extracted.x,
                scene_bounding_box_extracted.y,
                scene_bounding_box_extracted.w,
                scene_bounding_box_extracted.h,
            )

        return scenes_bounding_rectangle

    @property
    def scenes_bounding_rectangle(self) -> Dict[int, Rectangle]:
        """Get the bounding rectangle of all scenes in the document and returns it
        in a dictionary where scene indexes are the keys and the bounding rectangles the values.
        bounding rectangle are tuples following (x, y, h, w) with:

        x y - coordinates of the top left corner
        h - height of the rectangle
        w - width of the rectangle

        Returns
        ----------
        scenes_bounding_rectangle : Dict[int, Rectangle]
            dictionary containing all scenes bounding rectangle
            for example: { 0: (0, 0, 475, 325) }, { 1: (500, 500, 900, 800) }
        """
        return self._extract_scenes_bounding_rectangles(lambda x: x.boundingBox)

    @property
    def scenes_bounding_rectangle_no_pyramid(self) -> Dict[int, Rectangle]:
        """Get the bounding rectangle only of layer 0 of all scenes in the document and returns it
        in a dictionary where scene indexes are the keys and the bounding rectangles the values.
        bounding rectangle are tuples following (x, y, h, w) with:

        x y - coordinates of the top left corner
        h - height of the rectangle
        w - width of the rectangle

        Returns
        ----------
        scenes_bounding_rectangle_no_pyramids : Dict[int, Rectangle]
            dictionary containing all scenes bounding rectangle only taking layer 0 into account
            for example: { 0: (0, 0, 475, 325) }, { 1: (500, 500, 900, 800) }
        """
        return self._extract_scenes_bounding_rectangles(lambda x: x.boundingBoxLayer0)

    @property
    def total_bounding_rectangle(self) -> Rectangle:
        """Get the bounding rectangle of the whole czi document:

        Returns
        ----------
        total_bounding_rectangle : Rectangle
            Tuple containing the bounding rectangle properties.
            for example: (0, 0, 1200, 1000)
        """
        total_bounding_rectangle = Rectangle(
            self._stats.boundingBox.x,
            self._stats.boundingBox.y,
            self._stats.boundingBox.w,
            self._stats.boundingBox.h,
        )

        return total_bounding_rectangle

    @property
    def total_bounding_rectangle_no_pyramid(self) -> Rectangle:
        """Get the bounding rectangle of the whole czi document of layer 0 only:
        Pyramid sometimes leads to have more pixels in later layers.
        We can get the original no. of pixels from layer 0 only.

        Returns
        ----------
        total_bounding_rectangle : Rectangle
            Tuple containing the bounding rectangle properties.
            for example: (0, 0, 1200, 1000)
        """
        total_bounding_rectangle_layer0 = Rectangle(
            self._stats.boundingBoxLayer0Only.x,
            self._stats.boundingBoxLayer0Only.y,
            self._stats.boundingBoxLayer0Only.w,
            self._stats.boundingBoxLayer0Only.h,
        )

        return total_bounding_rectangle_layer0

    @property
    def raw_metadata(self) -> str:
        """Get the raw xml metadata of the czi document and returns it as a string

        Returns
        ----------
        : str
            XMl Metadata stored as a string
        """
        return self._czi_reader.GetXmlMetadata()

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get the raw metadata parsed in a dictionary

        Returns
        ----------
        :
            All available metadata in a dict
        """
        return xmltodict.parse(self.raw_metadata)

    @property
    def custom_attributes_metadata(self) -> Optional[Dict[str, Any]]:
        """Get the custom attribute list in a dictionary

        Returns
        ---------
        :
            Custom Attributes in a dict

        : raises ValueError: If the type of value is not supported, raises an error.
        """
        custom_attribute = None
        if "CustomAttributes" in self.metadata["ImageDocument"]["Metadata"]["Information"]:
            custom_attribute_metadata = self.metadata["ImageDocument"]["Metadata"]["Information"]["CustomAttributes"][
                "KeyValue"
            ]
            custom_attribute = {}
            for key, value in custom_attribute_metadata.items():
                if value["@Type"] == "Int32":
                    custom_attribute[key] = int(value["#text"])
                elif value["@Type"] == "Boolean":
                    if value["#text"] == "true":
                        custom_attribute[key] = True
                    else:
                        custom_attribute[key] = False
                elif value["@Type"] == "Double":
                    custom_attribute[key] = float(value["#text"])  # type: ignore
                elif value["@Type"] == "String":
                    custom_attribute[key] = str(value["#text"])  # type: ignore
                else:
                    raise ValueError("The type of the value is not supported!")

        return custom_attribute

    def get_channel_pixel_type(self, channel_index: int) -> str:
        """Get the pixel type of the specified color channel.
        If the channel_index doesn't exist in the czi document, "Invalid" is returned.

        PixelType object is an enum class with the corresponding match:

        * name : Gray8,         value: 0
        * name : Gray16,        value: 1
        * name : Gray32Float,   value: 2
        * name : Bgr24,         value: 3
        * name : Bgr48,         value: 4
        * name : Bgr96Float,    value: 8
        * name : Invalid,       value: 0xff

        thus, it only returns the name of the PixelType object (as a string).

        Parameters
        ----------
        channel_index : int
            index of the color channel to get the pixeltype.

        Returns
        ----------
        : str
            Name of the pixel type corresponding to the specified channel
        """
        return self._czi_reader.GetChannelPixelType(channel_index).name

    @property
    def pixel_types(self) -> Dict[int, str]:
        """Get the pixel types of all color channels present in the czi document

        Returns
        ----------
        pixel_types : Dict
            Dictionary containing channel indexes as keys and corresponding pixel types as values
            For example: {0: 'Gray8'}
        """
        pixel_types = {
            channel_index: self.get_channel_pixel_type(channel_index)
            for channel_index in range(self.total_bounding_box["C"][1])
        }

        return pixel_types

    @staticmethod
    def _is_rgb(pixel_type: str) -> bool:
        """Test if the pixel_type is rgb

        Parameters
        ----------
        pixel_type : str
            Pixel type
        Returns
        ----------
        : bool
            True if rgb False otherwise.
        """
        return "Bgr" in pixel_type

    @staticmethod
    def _format_roi(roi: Rectangle) -> _pylibCZIrw.IntRect:
        """Formats roi tuple as an IntRect object.

        Parameters
        ----------
        roi : Tuple[int, int, int, int]
            Region of Interest
        Returns
        ----------
        : _pylibCZIrw.IntRect
            the roi as an IntRect object.
        """
        roi_libczi = _pylibCZIrw.IntRect()

        roi_libczi.x = roi.x
        roi_libczi.y = roi.y
        roi_libczi.w = roi.w
        roi_libczi.h = roi.h

        return roi_libczi

    @staticmethod
    def _format_plane(plane: Dict[str, int]) -> str:
        """Formats plane Dict as a string.

        Parameters
        ----------
        plane : Dict[str, int]
            Plane coordinates
        Returns
        ----------
        : str
            Plane coordinates as a string.
        """
        return " ".join(f"{key}{value}" for key, value in plane.items())

    @staticmethod
    def _format_background_pixel(background_pixel: Color) -> _pylibCZIrw.RgbFloatColor:
        """Formats background_pixel Color Tuple as a RgbFloatColor object.

        Parameters
        ----------
        background_pixel : Color
            background pixel color
        Returns
        ----------
        : _pylibCZIrw.RgbFloatColor
           background pixel color as a RgbFloatColor object.
        """
        background_pixel_libczi = _pylibCZIrw.RgbFloatColor()

        background_pixel_libczi.r = background_pixel.r
        background_pixel_libczi.g = background_pixel.g
        background_pixel_libczi.b = background_pixel.b

        return background_pixel_libczi

    @classmethod
    def _format_pixel_type(cls, pixel_type: str) -> _pylibCZIrw.PixelType:
        """Formats pixel_type as a libCZI::PixelType object.

        Parameters
        ----------
        pixel_type : str
            Pixel type.

        Returns
        ----------
        : _pylibCZIrw.PixelType
           pixel type as a PixelType object.
        :raises ValueError: if pixel type is not a key of the PIXEL_TYPE dictionnary
        """
        try:
            pixel_id = cls.PIXEL_TYPES[pixel_type]
        except KeyError:
            raise ValueError(
                f"The pixel type provided does not mach any supported pixel types, possible values are: "
                f"{', '.join(list(cls.PIXEL_TYPES.keys()))}"
            ) from KeyError
        return _pylibCZIrw.PixelType(pixel_id)

    def _create_roi(
        self,
        roi: Optional[Rectangle],
        scene: Optional[int],
    ) -> Rectangle:
        """Generates roi or adapt it if needed and returns it.

        roi will be generated if None was provided. In this case if scene is specified, roi will be the bounding
        rectangle of the scene. Otherwise roi will be the total bounding rectangle of the czi.

        If roi is not None, it will just be converted to an IntRect object.

        Parameters
        ----------
        roi : Rectangle
            Region of Interest
        scene : int
            Scene index
        Returns
        ----------
        : Rectangle
            the formatted roi
        :raises ValueError: if scene index doesnt not exist in the czi document
        """
        if roi is None:
            if scene is None:
                roi = self.total_bounding_rectangle
            else:
                try:
                    roi = self.scenes_bounding_rectangle[scene]
                except KeyError:
                    raise ValueError(
                        "The scene index provided does not mach existing scenes in the czi document"
                    ) from KeyError
        roi = Rectangle(roi.x, roi.y, roi.w, roi.h)
        return roi

    def _create_default_plane_coords(self) -> Dict[str, int]:
        """Generates a default plane coordinates dictionary with all indexes to 0.
        This default plane coordinate contains all dimensions reported being used by
        the CZI-document, but includes only dimensions for which the size is >1.

        Returns
        -------
        : Dict [str, int]
            Example: If the czi contains T,Z,H will return {"T":0,"H":0,"Z":0}
        """
        return {
            dim: 0
            for dim, dim_index in self.CZI_DIMS.items()
            if self._czi_reader.GetDimensionSize(_pylibCZIrw.DimensionIndex(dim_index)) > 1
        }

    def _create_plane_coords(
        self,
        plane: Optional[Dict[str, int]],
    ) -> Dict[str, int]:
        """Generates valid plane coordinates from the one specified. if plane is None, plane coordinates will be
        generated with all first indexes of each dimension. Otherwise, will keep the valid coordinates specified in
        plane and add the potential coordinates missing set to 0.

        For instance if T is specified in plane but does not exist in the czi it will be filtered out here.
        And if T is not specified but is present in the document it will be added with T=0.

        Parameters
        ----------
        plane : Dict[str, int]
            Plane coordinates
        Returns
        ----------
        : Dict[str, int]
            Plane coordinates.
            Example: {"T":0, "Z":1, "C":0}.
        """
        default_plane = self._create_default_plane_coords()
        if plane:
            default_plane.update((k, v) for k, v in plane.items() if k in default_plane)

        return default_plane

    def _get_pixel_type(
        self,
        pixel_type: Optional[str],
        plane: Dict[str, int],
    ) -> str:
        """Get pixel_type of the specified plane if needed, otherwise returns the pixel_type provided by the user.

        Parameters
        ----------
        pixel_type: str
            Pixel type
        plane : Dict[str, int]
            Plane coordinate
        Returns
        ----------
        pixel_type: str
            Pixel type
        """
        if not pixel_type:
            pixel_type = self.get_channel_pixel_type(
                plane["C"] if "C" in plane else 0
            )  # In the case where there is no color channel in the czi, 0 index indicates the pixel type of the
            # document
        return pixel_type

    @classmethod
    def _get_array_from_bitmap(
        cls,
        pixel_data: _pylibCZIrw.PImage,
    ) -> np.ndarray:
        """Converts the bitmap stored in pixel_data to a np.array and creates a color channel.
        In the buffer pointed by pixel_data, the values are not regrouped in a specific color channel, that's why we
        need to perform a reshape: (m,n,1) if grayscale / (m,n,3) if rgb

        Parameters
        ----------
        pixel_data : _pylibCZIrw.PImage
            bitmap object containing pixel data
        Returns
        ----------
        :raises ValueError: Array should be 3-d
        : np.ndarray
            The bitmap converted to a numpy array and reshaped by splitting the color channel
        """
        if len(np.array(pixel_data).shape) == 2:
            raise ValueError("Incorrect shape")
        return np.array(pixel_data, copy=False)

    def get_cache_info(self) -> _pylibCZIrw.SubBlockCacheInfo:
        """Provide information on the subblock cache

        ----------
        : _pylibczirw.SubBlockCacheInfo
            A SubBlockCacheInfo object representing the cache information
        """
        return self._czi_reader.GetCacheInfo()

    def enumerate_subblocks(self, func: Callable[[int, _pylibCZIrw.SubBlockInfo], bool]) -> None:
        """Enumerate all subblocks in the CZI document.

        This method provides access to subblock header information without loading pixel data.
        For each subblock, the provided function is called with the subblock index and its
        SubBlockInfo containing metadata like coordinates, bounds, pixel type, and compression.

        Parameters
        ----------
        func : Callable[[int, _pylibCZIrw.SubBlockInfo], bool]
            A function that will be called for each subblock. It receives:
            - index (int): The subblock index
            - info (_pylibCZIrw.SubBlockInfo): Subblock header information
            Returns True to continue enumeration, False to stop.

        Examples
        --------
        >>> def print_subblock(index, info):
        ...     print(f"Subblock {index}: {info.logicalRect}")
        ...     return True  # continue enumeration
        >>> czi_doc.enumerate_subblocks(print_subblock)
        """
        self._czi_reader.EnumerateSubBlocks(func)

    def enumerate_subblocks_subset(
        self,
        func: Callable[[int, _pylibCZIrw.SubBlockInfo], bool],
        plane: Optional[Union[str, Dict[str, int]]] = None,
        roi: Optional[Union[Tuple[int, int, int, int], Rectangle]] = None,
        only_layer0: bool = False,
    ) -> None:
        """Enumerate a filtered subset of subblocks.

        This method allows filtering subblocks by plane coordinates, region of interest,
        and/or pyramid layer. Only subblock header information is accessed, not pixel data.

        Parameters
        ----------
        func : Callable[[int, _pylibCZIrw.SubBlockInfo], bool]
            A function called for each matching subblock. It receives:
            - index (int): The subblock index
            - info (_pylibCZIrw.SubBlockInfo): Subblock header information
            Returns True to continue enumeration, False to stop.
        plane : Optional[Union[str, Dict[str, int]]]
            Optional plane coordinate filter. Can be:
            - A coordinate string like "C0Z5T2"
            - A dictionary like {"C": 0, "Z": 5, "T": 2}
            - None for no coordinate filtering
        roi : Optional[Union[Tuple[int, int, int, int], Rectangle]]
            Optional region of interest. Only subblocks intersecting this ROI are enumerated.
            Specified as (x, y, width, height) tuple or Rectangle.
        only_layer0 : bool
            If True, only pyramid layer 0 subblocks are enumerated (default: False).

        Examples
        --------
        >>> # Enumerate all layer0 subblocks in channel 0, Z-slice 5
        >>> def print_bounds(index, info):
        ...     rect = info.logicalRect
        ...     print(f"Subblock {index}: ({rect.x}, {rect.y}, {rect.w}, {rect.h})")
        ...     return True
        >>> czi_doc.enumerate_subblocks_subset(
        ...     print_bounds,
        ...     plane={"C": 0, "Z": 5},
        ...     only_layer0=True
        ... )

        >>> # Enumerate using coordinate string
        >>> czi_doc.enumerate_subblocks_subset(
        ...     print_bounds,
        ...     plane="C0Z5T0"
        ... )
        """
        plane_coord = None
        if plane is not None:
            if isinstance(plane, str):
                plane_coord = _pylibCZIrw.DimCoordinate(plane)
            elif isinstance(plane, dict):
                plane_coord = _pylibCZIrw.DimCoordinate(plane)

        roi_rect = None
        if roi is not None:
            if not isinstance(roi, Rectangle):
                roi = Rectangle(*roi)
            roi_rect = self._format_roi(roi)

        self._czi_reader.EnumerateSubset(plane_coord, roi_rect, only_layer0, func)

    def read(
        self,
        roi: Optional[Union[Tuple[int, int, int, int], Rectangle]] = None,
        plane: Optional[Dict[str, int]] = None,
        scene: Optional[int] = None,
        zoom: Optional[float] = None,
        pixel_type: Optional[str] = None,
        background_pixel: Union[Tuple[float, float, float], Color] = BLACK_COLOR,
    ) -> np.ndarray:
        """Access Pixel data of the CziReader document and returns it as a np.ndarray

        Parameters
        ----------
        roi : Optional[Union[Tuple[int, int, int, int], Rectangle]]
            Region of Interest
        plane : Optional[Dict[str, int]]
            Plane coordinates
        scene : Optional[int]
            Scene index
        zoom : float
            A float between 0 (excluded) and 1 that specifies the zoom factor
        pixel_type : Optional[str]
            The pixel type of the returned data.
        background_pixel : Union[Tuple[float, float, float], Color]
            Specifies the color of the background pixels (pixels with no data)
            This value should always be an rgb float (range 0-1) and will be automatically converted to the bitmap data
            type.

        Returns
        ----------
        pixel_data : np.ndarray
            The pixel data as a numpy array.
        """
        # Casting possible tuples to namedtuple
        if roi:
            roi = Rectangle(*roi)
        if not isinstance(background_pixel, Color):
            background_pixel = Color(*background_pixel)

        # Generating possibly non specified values
        plane = self._create_plane_coords(plane)
        pixel_type = self._get_pixel_type(pixel_type, plane)
        roi = self._create_roi(roi, scene)

        # Formatting parameters for the low level call
        roi_libczi = self._format_roi(roi)
        background_pixel_libczi = self._format_background_pixel(background_pixel)
        plane_libczi = self._format_plane(plane)
        pixel_type_libczi = self._format_pixel_type(pixel_type)
        scene_libczi = "" if scene is None else str(scene)
        zoom_libczi = 1.0 if zoom is None else float(zoom)

        # Getting the bitmap
        pixel_data = self._czi_reader.GetSingleChannelScalingTileAccessorData(
            pixel_type_libczi,
            roi_libczi,
            background_pixel_libczi,
            zoom_libczi,
            plane_libczi,
            scene_libczi,
        )
        # Converting to numpy array
        np_pixel_data = self._get_array_from_bitmap(pixel_data)

        return np_pixel_data


class CziWriter:
    """CziWriter class.

    _czi_writer : object
        c++ bonded object, corresponding to an instance of the CZIwriteAPI class.
    _m_dict : Dict[str, int]
        Dictionary matching a plane with the greatest m_index of subblocks already written in this Plane.
    GRAY_MAPPING : Dict[str, int]
        Dictionary matching a np.dtype with the corresponding libCZI PixelType for gray-level images.
    RGN_MAPPING : Dict[str, int]
        Dictionary matching a np.dtype with the corresponding libCZI PixelType for rgb-level images.
    """

    GRAY_MAPPING: Dict[np.dtype, _pylibCZIrw.PixelType] = {
        np.dtype("uint8"): _pylibCZIrw.PixelType(0),
        np.dtype("uint16"): _pylibCZIrw.PixelType(1),
        np.dtype("float32"): _pylibCZIrw.PixelType(2),
    }

    RGB_MAPPING: Dict[np.dtype, _pylibCZIrw.PixelType] = {
        np.dtype("uint8"): _pylibCZIrw.PixelType(3),
        np.dtype("uint16"): _pylibCZIrw.PixelType(4),
        np.dtype("float32"): _pylibCZIrw.PixelType(8),
    }

    def __init__(self, filepath: str, compression_options: Optional[str] = None) -> None:
        """Creates a czi writer object, should only be call through the create_czi() function.

        Parameters
        ----------
        filepath : str
            File path.
        compression_options : Optional[str]
            String representation of compression options to be used as default (for this instance). If
            not specified, uncompressed is used.
        """
        czi_writer = (
            _pylibCZIrw.czi_writer(filepath)
            if compression_options is None
            else _pylibCZIrw.czi_writer(filepath, compression_options)
        )

        self._czi_writer: _pylibCZIrw.czi_writer = czi_writer
        self._m_dict: Dict[str, int] = {}
        self._metadata_writen = False

    def close(self) -> None:
        """Close the document and finalize the writing"""
        try:  # pylint: disable=too-many-try-statements
            if not self._metadata_writen:
                self.write_metadata()
        finally:
            self._czi_writer.close()

    def _get_m_index(self, plane_libczi: str) -> int:
        """Compute next available m_index in the specified plane.

        Parameters
        ----------
        plane_libczi : str
            Plane coordinates formatted as a string, ex: "T0 Z0 C0 S1"
        Returns
        ----------
        : int
           the m_index corresponding to the given plane
        """
        if plane_libczi in self._m_dict:
            self._m_dict[plane_libczi] = self._m_dict[plane_libczi] + 1
        else:
            self._m_dict[plane_libczi] = 0
        return self._m_dict[plane_libczi]

    @staticmethod
    def _format_plane(plane: Dict[str, int]) -> str:
        """Formats plane Dict as a string.

        Parameters
        ----------
        plane : Dict[str, int]
            Plane coordinates
        Returns
        ----------
        : str
            Plane coordinates as a string.
        """
        return " ".join(f"{key}{value}" for key, value in plane.items())

    @staticmethod
    def _create_plane(plane: Optional[Dict[str, int]], scene: int) -> Dict[str, int]:
        """Generates valid plane coordinates from the one specified. if plane is None, plane coordinates will be
        generated with all first indexes of each dimension. Otherwise, will keep the valid coordinates specified in
        plane and add the potential coordinates missing set to 0.
        For the writing we also take scene_index into account and always specify it in the plane coordinates.
        If the user doesnt specify a scene we wil per default write to scene of index 0.

        Parameters
        ----------
        plane : Dict[str, int]
            Plane coordinates
        scene : int
             Scene index
        Returns
        ----------
        : Dict[str, int]
            Plane coordinates.
            Example: {"T":0, "Z":1, "C":0, "S": 0}.
        """
        default_plane = {"T": 0, "Z": 0, "C": 0, "S": scene}
        if plane:
            default_plane.update((k, v) for k, v in plane.items() if k in default_plane)
        return default_plane

    @staticmethod
    def _format_gray_data(data: np.ndarray) -> np.ndarray:
        """Reshape 3D grayscale array to 2D array.

        Parameters
        ----------
        data : np.ndarray
            data to be reshaped
        Returns
        ----------
        : np.ndarray
            reshaped data.
        """
        return data.reshape((data.shape[0], data.shape[1], 1))

    @staticmethod
    def _get_channel_dim(data: np.ndarray) -> int:
        """Get the channel dimension of the input data

        Parameters
        ----------
        data : np.ndarray
            image data
        Returns
        ----------
        : int
            no. of channel dimension
        :raises ValueError: If data has less than two dimensions.
        """
        try:
            return data.shape[2]
        except IndexError:
            raise ValueError(
                "The data provided should have a shape of at least length 3 (e.g. (m,n,3) or (m,n,1))"
            ) from IndexError

    @staticmethod
    def _is_rgb(data: np.ndarray) -> bool:
        """Check if the given image data is rgb or not.

        Parameters
        ----------
        data : np.ndarray
            image data
        Returns
        ----------
        : bool
            True if RGB False otherwise.
        """
        return CziWriter._get_channel_dim(data) == 3 if len(data.shape) == 3 else False

    @staticmethod
    def _is_gray(data: np.ndarray) -> bool:
        """Check if the given image data is gray or not.

        Parameters
        ----------
        data : np.ndarray
            image data
        Returns
        ----------
        : bool
            True if Gray False otherwise.
        """
        if len(data.shape) == 3:
            return CziWriter._get_channel_dim(data) == 1
        return len(data.shape) == 2

    @classmethod
    def _format_data(cls, data: np.ndarray) -> _pylibCZIrw.PImage:
        """Converts the data np.array to a c++ PImage object that will be sent to the writer.
        In order to convert the np.array to a PImage we have to reshape to 2D array and flatten the color dimension.
        PixelType will be deducted from the shape and the dtype of the array.

        Parameters
        ----------
        data : np.ndarray
            Plane coordinates
        Returns
        ----------
        : _pylibCZIrw.PImage
            PImage bitmap object
        :raises ValueError: if  channel dimension is not correct
        """
        if len(data.shape) == 2:
            data = data[..., np.newaxis]

        if cls._is_rgb(data):
            return _pylibCZIrw.PImage(data, cls.RGB_MAPPING[data.dtype])
        if cls._is_gray(data):
            return _pylibCZIrw.PImage(cls._format_gray_data(data), cls.GRAY_MAPPING[data.dtype])
        raise ValueError("Incorrect Channel dimension!")

    @classmethod
    def _choose_max_extent(cls, data: np.ndarray) -> int:
        """Choose the maximum extent based on the number of channels

        Parameters
        ----------
        data : np.ndarray
            image data
        Returns
        ----------
        : int
            max length / width
        """
        max_extent = 1800 if cls._is_rgb(data) else 3100

        return max_extent

    @staticmethod
    def _compute_num_parts(original_extent: int, max_extent: int) -> int:
        """Compute the number of sub parts

        Parameters
        ----------
        original_extent : int
            original length / width
        max_extent : int
            max length / width
        Returns
        ----------
        : int
            number of sub parts
        """
        if original_extent < max_extent:
            return 1
        return (original_extent + max_extent - 1) // max_extent

    def _divide_data(self, data: np.ndarray) -> Generator:
        """Divide the image data into sub arrays

        Parameters
        ----------
        data : np.ndarray
            image data
        Returns
        ----------
        : Generator
            divided sub image data.
        """
        width, length = data.shape[:2]
        max_extent = self._choose_max_extent(data)
        num_cols = self._compute_num_parts(width, max_extent)
        num_rows = self._compute_num_parts(length, max_extent)
        for i in range(num_cols):
            for j in range(num_rows):
                right = None if i == num_cols - 1 else (width // num_cols) * (i + 1)
                bottom = None if j == num_rows - 1 else (length // num_rows) * (j + 1)
                subdata = data[(width // num_cols) * i : right, (length // num_rows) * j : bottom]
                yield subdata

    def write(
        self,
        data: np.ndarray,
        location: Tuple[int, int] = (0, 0),
        plane: Optional[Dict[str, int]] = None,
        compression_options: Optional[str] = None,
        scene: int = 0,
    ) -> bool:
        """Write Pixel data to the CziWriter document.

        Parameters
        ----------
        data : np.ndarray
            2D tile data to write, expected of shape (m,n,1) or (m,n,3) for rgb planes.
        location : Optional[Tuple[int, int]]
            Coordinates of top-left corner where to write the tile.
        plane: Optional[Dict[str, int]]
            Plane coordinates
        compression_options : Optional[str]
            String representation of compression options; if not specified, the writer's default is used.
        scene : Optional[int]
            Scene index
        Returns
        ----------
        : bool
            true if everything went fine, false otherwise.
        """
        plane = self._create_plane(plane, scene)
        plane_libczi = self._format_plane(plane)
        curr_x, curr_y = location
        data_size = data.nbytes / 1000000
        retiling_id = str(uuid.uuid4())

        subdata_generator = self._divide_data(data) if data_size > 10.0 else (item for item in [data])

        for subarray in subdata_generator:
            m_index = self._get_m_index(plane_libczi)
            data_libczi = self._format_data(np.ascontiguousarray(subarray))
            location_libczi = Location(curr_x, curr_y)
            if compression_options is None:
                if not self._czi_writer.AddTile(
                    plane_libczi,
                    data_libczi,
                    location_libczi.x,
                    location_libczi.y,
                    m_index,
                    retiling_id,
                ):
                    return False
            else:
                if not self._czi_writer.AddTileEx(  # pylint: disable=confusing-consecutive-elif, else-if-used
                    plane_libczi,
                    data_libczi,
                    location_libczi.x,
                    location_libczi.y,
                    m_index,
                    compression_options,
                    retiling_id,
                ):
                    return False
            curr_x += subarray.shape[1]
            if curr_x == data.shape[1] + location[0]:
                curr_x = location[0]
                curr_y += subarray.shape[0]
        return True

    @staticmethod
    def _create_customvalue(
        value: Union[int, float, bool, str],
    ) -> _pylibCZIrw.CustomValueVariant:
        """Convert the custom attribute value into a CustomValueVariant object

        Parameters
        ----------
        value: Union[int, float, bool, str]
            value of the custom attribute pair

        Returns
        ----------
         : customvalue
            converted custom attribute value as a CustomValueVariant object

        : raises ValueError: The type of value could only be boolean, integer, float or string.
        """
        customvalue = _pylibCZIrw.CustomValueVariant()
        if isinstance(value, bool):
            customvalue.boolValue = value
        elif isinstance(value, int):
            customvalue.int32Value = value
        elif isinstance(value, float):
            customvalue.doubleValue = value
        elif isinstance(value, str):
            customvalue.stringValue = value
        else:
            raise ValueError("The type of value could only be boolean, integer, float or string.")
        return customvalue

    @staticmethod
    def _create_display_setting(
        value: ChannelDisplaySettingsDataClass,
    ) -> _pylibCZIrw.ChannelDisplaySettingsStruct:
        """Convert the ChannelDisplaySettingsDataClass value into a ChannelDisplaySettingsPOD object

        Parameters
        ----------
        value: ChannelDisplaySettingsDataClass
            value of the channel display setting

        Returns
        ----------
         : channel_display_setting
            converted ChannelDisplaySettingsDataClass value as a ChannelDisplaySettingsPOD object

        : raises ValueError: The type of value could only be boolean, integer, float or string.
        """
        channel_display_setting = _pylibCZIrw.ChannelDisplaySettingsStruct()
        channel_display_setting.Clear()
        channel_display_setting.isEnabled = value.is_enabled
        channel_display_setting.blackPoint = value.black_point
        channel_display_setting.whitePoint = value.white_point

        channel_display_setting.tintingColor.r = value.tinting_color.r
        channel_display_setting.tintingColor.g = value.tinting_color.g
        channel_display_setting.tintingColor.b = value.tinting_color.b

        if value.tinting_mode == TintingMode.Color:
            channel_display_setting.tintingMode = _pylibCZIrw.TintingModeEnum.Color

        return channel_display_setting

    def write_metadata(
        self,
        document_name: Optional[str] = "CZI",
        channel_names: Optional[Dict[int, str]] = None,
        scale_x: Optional[float] = 0.0,
        scale_y: Optional[float] = 0.0,
        scale_z: Optional[float] = 0.0,
        custom_attributes: Optional[Dict[str, Union[int, float, bool, str]]] = None,
        display_settings: Optional[Dict[int, ChannelDisplaySettingsDataClass]] = None,
    ) -> None:
        """Generates and write metadata according to all data writen so far in the CZI document.
        Channels names can be specified optionally.

        Parameters
        ----------
        document_name: str
            name of the document
        channel_names : Optional[Dict[int, str]]
            name of color channels, each channel without a specified name will be marked as "C:channel_id"
        scale_x:
            The extent of a pixel in x-direction in units of µm
        scale_y:
            The extent of a pixel in y-direction in units of µm
        scale_z:
            The extent of a pixel in z-direction in units of µm
        custom_attributes: Optional[Dict[str, _pylibCZIrw.CustomValueVariant]]
            custom attribute key name and its corresponding values
        display_settings:
            This dataclass is intended to capture all information found inside a ChannelDisplaySetting-object.
            It allows for easy modification of the information.
            There should be one dictionary entry per channel.
            Note: There is no 1:1 relationship enforced.
            A user may decide to add display settings to each channel or only to some channels.
            Similarly, it is not verified if the user sends more display settings than channels present.
            Display settings that are not written will be set as 'empty', regardless of if they
            initially existed for that channel.
        """

        channel_names = channel_names or {}
        display_settings_dict = {}
        if display_settings:
            for (
                display_settings_key,
                display_settings_value,
            ) in display_settings.items():
                display_settings_dict[display_settings_key] = self._create_display_setting(display_settings_value)
        custom_attributes_dict = {}
        if custom_attributes:
            for (
                custom_attributes_key,
                custom_attributes_value,
            ) in custom_attributes.items():
                custom_attributes_dict[custom_attributes_key] = self._create_customvalue(custom_attributes_value)
        self._czi_writer.WriteMetadata(
            document_name,
            scale_x,
            scale_y,
            scale_z,
            channel_names,
            custom_attributes_dict,
            display_settings_dict,
        )
        self._metadata_writen = True


@dataclass
class ScalingInfoDto:
    """ScalingInfoDto.

    Represents pixel size (scaling) in the existing unit (by default micrometers) for X, Y, Z axes.
    - A field left as None indicates “unspecified/no change”.
    - When editing, only provided values are applied.

    Attributes
    ----------
    scale_x : Optional[float]
        Pixel size along X.
    scale_y : Optional[float]
        Pixel size along Y.
    scale_z : Optional[float]
        Pixel size along Z.
    """

    scale_x: Optional[float] = None
    scale_y: Optional[float] = None
    scale_z: Optional[float] = None


@dataclass
class ChannelDisplaySettingsDataClassWithNameAndDescription(ChannelDisplaySettingsDataClass):
    """ChannelDisplaySettingsDataClassWithNameAndDescription.

    Extends channel display settings with optional `name` and `description`.

    Notes
    -----
    - `is_enabled`, contrast points (`black_point`, `white_point`) and `tinting_*`
      behave as in `ChannelDisplaySettingsDataClass`.
    - `name` and `description` are optional; omit or set None to leave unchanged on edit.
    """

    name: Optional[str] = None
    description: Optional[str] = None


@dataclass
class GeneralDocumentInfoDto:
    """DTO for general document information fields."""

    name: Optional[str] = None
    title: Optional[str] = None
    user_name: Optional[str] = None
    description: Optional[str] = None
    comment: Optional[str] = None
    keywords: Optional[str] = None
    rating: Optional[float] = None
    creation_date_time: Optional[str] = None


class CziMetadataBuilder:
    """CziMetadataBuilder.

    High-level helper to edit metadata. Create via `CziEditor.begin_edit()` or `CziEditor.create_metadata_builder()`.

    General behavior
    ----------------
    - Setters accept DTOs and/or keyword arguments.
    - Fields not provided (None) are ignored; only specified fields are applied.
    - Call `commit()` to persist changes. Use `can_commit()` to verify the builder is valid.
    """

    def __init__(self, native: "_pylibCZIrw.CziMetadataBuilder") -> None:
        self._native = native

    # Helper method to filter function inputs
    @staticmethod
    def _filter_none(d: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in d.items() if v is not None}

    def get_xml(self, prettify: bool = False) -> str:
        """Get the current metadata XML.

        Parameters
        ----------
        prettify : bool, optional
            If True, return pretty-printed XML where supported by the native implementation.
        """
        return self._native.get_xml(prettify)

    def set_xml(self, xml_string: str) -> None:
        """Replace the entire metadata XML content.

        Parameters
        ----------
        xml_string : str
            The new XML content to set.
        """
        self._native.set_xml(xml_string)

    def set_general_document_info(
        self,
        info: Optional[GeneralDocumentInfoDto] = None,
        *,
        name: Optional[str] = None,
        title: Optional[str] = None,
        user_name: Optional[str] = None,
        description: Optional[str] = None,
        comment: Optional[str] = None,
        keywords: Optional[str] = None,
        rating: Optional[float] = None,
    ) -> None:
        """Update general document fields.

        Parameters
        ----------
        info : Optional[GeneralDocumentInfoDto]
            DTO whose non-None fields are applied.
        name : Optional[str]
            Document name. Overrides DTO when provided.
        title : Optional[str]
            Document title. Overrides DTO when provided.
        user_name : Optional[str]
            User name. Overrides DTO when provided.
        description : Optional[str]
            Document description. Overrides DTO when provided.
        comment : Optional[str]
            Document comment. Overrides DTO when provided.
        keywords : Optional[str]
            Document keywords. Overrides DTO when provided.
        rating : Optional[float]
            Document rating. Overrides DTO when provided.

        Examples
        --------
        - Update only the name:
            builder.set_general_document_info(name="New name")
        - Merge a DTO and override one field:
            builder.set_general_document_info(info=dto, comment="Updated")

        Notes
        -----
        Unspecified fields remain unchanged in the document.
        """
        base = {
            "name": getattr(info, "name", None),
            "title": getattr(info, "title", None),
            "user_name": getattr(info, "user_name", None),
            "description": getattr(info, "description", None),
            "comment": getattr(info, "comment", None),
            "keywords": getattr(info, "keywords", None),
            "rating": getattr(info, "rating", None),
        }
        base.update(
            self._filter_none(
                {
                    "name": name,
                    "title": title,
                    "user_name": user_name,
                    "description": description,
                    "comment": comment,
                    "keywords": keywords,
                    "rating": rating,
                }
            )
        )
        args = self._filter_none(base)
        self._native.set_general_document_info(**args)

    def set_scaling_info(
        self,
        scaling: Optional[ScalingInfoDto] = None,
        *,
        scale_x: Optional[float] = None,
        scale_y: Optional[float] = None,
        scale_z: Optional[float] = None,
    ) -> None:
        """Update scaling (pixel size in the existing unit, typically µm).

        Parameters
        ----------
        scaling : Optional[ScalingInfoDto]
            DTO whose non-None fields are applied.
        scale_x : Optional[float]
            X-axis scale. Overrides DTO when provided.
        scale_y : Optional[float]
            Y-axis scale. Overrides DTO when provided.
        scale_z : Optional[float]
            Z-axis scale. Overrides DTO when provided.

        Examples
        --------
        - Update only scale_x:
            builder.set_scaling_info(scale_x=0.25)
        - Apply a DTO:
            builder.set_scaling_info(ScalingInfoDto(scale_x=0.25, scale_y=0.25))

        Notes
        -----
        Unspecified axes remain unchanged.
        """
        base = {
            "scale_x": getattr(scaling, "scale_x", None),
            "scale_y": getattr(scaling, "scale_y", None),
            "scale_z": getattr(scaling, "scale_z", None),
        }
        base.update(self._filter_none({"scale_x": scale_x, "scale_y": scale_y, "scale_z": scale_z}))
        args = self._filter_none(base)
        self._native.set_scaling_info(**args)

    def set_custom_key_value(self, key: str, value: Union[int, float, bool, str]) -> None:
        """Forward a Python-native value by constructing a CustomValueVariant."""
        cv = _pylibCZIrw.CustomValueVariant()
        if isinstance(value, bool):
            cv.boolValue = value
        elif isinstance(value, int):
            cv.int32Value = value
        elif isinstance(value, float):
            cv.doubleValue = value
        elif isinstance(value, str):
            cv.stringValue = value
        else:
            raise ValueError("Custom attribute value must be bool, int, float, or str.")
        self._native.set_custom_key_value(key, cv)

    def set_display_settings(
        self,
        display_settings: Dict[
            int,
            Union[
                ChannelDisplaySettingsDataClass,
                ChannelDisplaySettingsDataClassWithNameAndDescription,
            ],
        ],
    ) -> None:
        """Update per-channel display settings.

        Parameters
        ----------
        display_settings : Dict[int, ChannelDisplaySettingsDataClass or \
            ChannelDisplaySettingsDataClassWithNameAndDescription]
            Mapping from channel index to settings DTO.

        Notes
        -----
        - Only provided channels are updated.
        - Optional `name` and `description` are applied when present.
        - `is_enabled` updates selection for channels.
        """
        # pylint: disable=import-outside-toplevel,no-name-in-module
        from _pylibCZIrw import (
            ChannelDisplaySettingsStructWithNameAndDescription,
            TintingModeEnum,
        )

        def to_pod(
            ds_py: Union[
                ChannelDisplaySettingsDataClass,
                ChannelDisplaySettingsDataClassWithNameAndDescription,
            ],
        ) -> ChannelDisplaySettingsStructWithNameAndDescription:
            pod = ChannelDisplaySettingsStructWithNameAndDescription()
            pod.Clear()
            pod.isEnabled = ds_py.is_enabled
            pod.blackPoint = ds_py.black_point
            pod.whitePoint = ds_py.white_point
            pod.tintingColor.r = ds_py.tinting_color.r
            pod.tintingColor.g = ds_py.tinting_color.g
            pod.tintingColor.b = ds_py.tinting_color.b
            pod.tintingMode = (
                TintingModeEnum.Color if ds_py.tinting_mode == TintingMode.Color else getattr(TintingModeEnum, "None")
            )
            pod.description = getattr(ds_py, "description", None) or ""
            pod.name = getattr(ds_py, "name", None) or ""
            return pod

        mapped = {idx: to_pod(ds) for idx, ds in display_settings.items()}
        self._native.set_display_settings(mapped)

    def can_commit(self) -> bool:
        """Return True if the builder can commit changes."""
        return self._native.can_commit()

    def commit(self) -> None:
        """Commit all pending changes to the CZI file."""
        self._native.commit()


class CziEditor:
    """CziEditor.

    Opens an existing CZI for metadata edits. Reading is done via the editor; writing via a builder.

    Usage
    -----
    with edit_czi(path) as editor:
        info = editor.read_general_document_info()
        scaling = editor.read_scaling_info()
        with editor.edit_session() as builder:
            builder.set_general_document_info(name="New name")
            builder.set_scaling_info(scale_x=0.25)
            # builder.commit() is called automatically on successful exit
    """

    def __init__(self, filepath: str) -> None:
        """Open an existing CZI file for in-place metadata editing."""
        self._editor = _pylibCZIrw.czi_editor(filepath)

    def close(self) -> None:
        """Close the editor and underlying file handle."""
        self._editor.close()

    @property
    def is_open(self) -> bool:
        """Return True if the editor is open."""
        return self._editor.is_open()

    def read_metadata_xml(self) -> str:
        """Return the current metadata XML."""
        return self._editor.read_metadata_xml()

    def read_custom_key_value(self, key: str) -> Optional[Union[int, float, bool, str]]:
        """Return the custom attribute value for the given key.

        Returns the value as a native Python type (bool, int, float, str), or None if the variant is empty/unsupported.
        """
        variant = self._editor.read_custom_key_value(key)

        for accessor in (
            lambda v: v.boolValue,
            lambda v: v.int32Value,
            lambda v: v.doubleValue,
            lambda v: v.floatValue,
            lambda v: v.stringValue,
        ):
            try:
                return accessor(variant)
            except RuntimeError:
                continue
        return None

    def read_general_document_info(self) -> Dict[str, Any]:
        """Return available general document information as a dict.

        Notes
        -----
        Keys may include: 'name', 'title', 'user_name', 'description',
        'comment', 'keywords', 'rating', 'creation_date_time'.
        Missing keys indicate the information is not present in the file.
        """
        return self._editor.read_general_document_info()

    def read_scaling_info(self) -> ScalingInfoDto:
        """Return current scaling (pixel size in default unit which is typically µm) as a DTO.

        Notes
        -----
        - Unavailable axes are returned as None.
        - Use `builder.set_scaling_info(...)` to update specific axes without affecting others.
        """
        native = self._editor.read_scaling_info()
        return ScalingInfoDto(
            scale_x=native.get("scale_x"),
            scale_y=native.get("scale_y"),
            scale_z=native.get("scale_z"),
        )

    def read_display_settings(
        self,
    ) -> Dict[int, ChannelDisplaySettingsDataClassWithNameAndDescription]:
        """Return per-channel display settings as DTOs.

        Returns
        -------
        Dict[int, ChannelDisplaySettingsDataClassWithNameAndDescription]
            Mapping from channel index to settings DTO.

        Notes
        -----
        The mapping may be empty if the file does not contain display settings.
        """
        native_map = self._editor.read_display_settings()

        def to_dto(
            pod: "_pylibCZIrw.ChannelDisplaySettingsStructWithNameAndDescription",
        ) -> ChannelDisplaySettingsDataClassWithNameAndDescription:
            # map native tinting-mode enum to Python TintingMode
            tinting_enum_color = _pylibCZIrw.TintingModeEnum.Color
            tint_mode_py = TintingMode.Color if pod.tintingMode == tinting_enum_color else TintingMode.none
            return ChannelDisplaySettingsDataClassWithNameAndDescription(
                is_enabled=bool(getattr(pod, "isEnabled", False)),
                tinting_mode=tint_mode_py,
                tinting_color=Rgb8Color(
                    r=np.uint8(getattr(pod.tintingColor, "r", 0)),
                    g=np.uint8(getattr(pod.tintingColor, "g", 0)),
                    b=np.uint8(getattr(pod.tintingColor, "b", 0)),
                ),
                black_point=float(getattr(pod, "blackPoint", 0.0)),
                white_point=float(getattr(pod, "whitePoint", 1.0)),
                name=getattr(pod, "name", None) if hasattr(pod, "name") else None,
                description=(getattr(pod, "description", None) if hasattr(pod, "description") else None),
            )

        return {idx: to_dto(p) for idx, p in native_map.items()}

    def create_metadata_builder(self) -> CziMetadataBuilder:
        """Create a builder initialized with the file's current metadata.

        Notes
        -----
        - Use builder setters to change specific fields.
        - Call `commit()` to persist changes. For convenience, `edit_session()` auto-commits on success.
        """
        native_builder = self._editor.create_metadata_builder()
        return CziMetadataBuilder(native_builder)

    @staticmethod
    def make_channel_display_setting_with_description(
        is_enabled: bool,
        tinting_mode: TintingMode,
        tinting_color: Rgb8Color,
        black_point: float,
        white_point: float,
        description: str,
    ) -> "_pylibCZIrw.ChannelDisplaySettingsStructWithDescription":
        """Helper to build ChannelDisplaySettingsStructWithDescription from Python datatypes."""
        pod = _pylibCZIrw.ChannelDisplaySettingsStructWithDescription()
        pod.Clear()
        pod.isEnabled = is_enabled
        pod.blackPoint = black_point
        pod.whitePoint = white_point
        pod.tintingColor.r = tinting_color.r
        pod.tintingColor.g = tinting_color.g
        pod.tintingColor.b = tinting_color.b
        if tinting_mode == TintingMode.Color:
            pod.tintingMode = _pylibCZIrw.TintingModeEnum.Color
        else:
            pod.tintingMode = getattr(_pylibCZIrw.TintingModeEnum, "None")
        pod.description = description
        return pod

    def begin_edit(self) -> "CziMetadataBuilder":
        """Start an edit session by creating a metadata builder."""
        return self.create_metadata_builder()

    @contextlib.contextmanager
    def edit_session(self) -> Iterator["CziMetadataBuilder"]:
        """Context-managed edit session."""
        builder = self.begin_edit()
        yield builder
        if builder.can_commit():
            builder.commit()


@contextlib.contextmanager
def open_czi(
    filepath: str,
    file_input_type: ReaderFileInputTypes = ReaderFileInputTypes.Standard,
    cache_options: Optional[CacheOptions] = None,
    *,
    reader_options: Optional[ReaderOptions] = None,
) -> Generator[CziReader, None, None]:
    """Initialize a czi reader object and returns it.
    Opens the filepath and hands it over to the low-level function.

    Parameters
    ----------
    filepath : str
        File path.
    file_input_type : ReaderFileInputTypes, optional
        The type of file input, default is local file.
    cache_options : CacheOptions, optional
        The configuration of a subblock cache to be used. Per default no cache is used.
    reader_options: ReaderOptions, optional
        Additional configuration options for the reader. Note that there is a keyword-only argument
        boundary before the reader_options argument.
        Note: This parameter uses a keyword-only argument separator (*) to prevent
        accidental positional argument passing. This design choice ensures that
        reader_options must be explicitly named when called, improving code clarity
        and preventing errors when the function signature evolves. It also maintains
        backward compatibility if new optional parameters are added between
        cache_options and reader_options in the future.

    Returns
    ----------
     : czi
        CziReader document as a czi object
    """
    reader = CziReader(
        filepath,
        file_input_type,
        cache_options=cache_options,
        reader_options=reader_options,
    )
    try:
        yield reader
    finally:
        reader.close()


@contextlib.contextmanager
def create_czi(
    filepath: str, exist_ok: bool = False, compression_options: Optional[str] = None
) -> Generator[CziWriter, None, None]:
    """Initialize a czi writer object and returns it. Opens the filepath and hands it over to the low-level function.

    Any missing intermediate directories are created in case they are missing.
    From https://docs.python.org/3/library/os.html#os.makedirs:
    Changed in version 3.7: The mode argument no longer affects the file permission bits of newly-created
    intermediate-level directories. This is fine since this package requires Python>=3.7.

    Parameters
    ----------
    filepath : str
        File path.
    exist_ok: bool
        Whether to throw if the file already exists (i.e. if exist_ok = False)
    compression_options : Optional[str]
        String representation of compression options to be used as default (for this instance). If
        not specified, uncompressed is used. The compression-options set here can still be overwritten with each
        individual call to the write function.

    Returns
    ----------
     : czi
         CziWriter document as a czi object

    :raises FileExistsError: If exist_ok is False, i.e. no overwrite is allowed, and the file exists

    """
    filepath_abs = abspath(filepath)
    if not exist_ok and isfile(filepath_abs):
        raise FileExistsError(f"{filepath_abs} already exists and exist_ok is False.")
    makedirs(dirname(filepath_abs), exist_ok=True)
    writer = CziWriter(filepath_abs, compression_options)
    try:
        yield writer
    finally:
        writer.close()


@contextlib.contextmanager
def edit_czi(filepath: str) -> Generator[CziEditor, None, None]:
    """Initialize a czi editor object and returns it.

    Parameters
    ----------
    filepath : str
        File path to an existing CZI.

    Returns
    ----------
     : czi_editor
        CziEditor for in-place metadata editing.
    """
    editor = CziEditor(filepath)
    try:
        yield editor
    finally:
        editor.close()
