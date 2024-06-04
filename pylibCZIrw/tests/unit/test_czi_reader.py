"""Module implementing unit tests for the CziReader class"""

from unittest import mock
from typing import NamedTuple, Dict, Tuple, Optional
import pytest
import numpy as np

# pylint: disable=no-name-in-module
from _pylibCZIrw import IntRect, DimensionIndex, RgbFloatColor, PixelType
from pylibCZIrw.czi import CziReader, Rectangle, Color

# testing static functions


def create_rectangle(x: int, y: int, w: int, h: int) -> IntRect:
    """Creates a IntRect object."""
    rectangle = IntRect()
    rectangle.x = x
    rectangle.y = y
    rectangle.w = w
    rectangle.h = h

    return rectangle


def compare_rectangle(rec1: IntRect, rec2: IntRect) -> bool:
    """Compare 2 IntRect objects"""
    return (rec1.x, rec1.y, rec1.w, rec1.h) == (rec2.x, rec2.y, rec2.w, rec2.h)


def create_color(b: float, g: float, r: float) -> RgbFloatColor:
    """Creates a RgbFloatColor object."""
    color = RgbFloatColor()
    color.b = b
    color.g = g
    color.r = r

    return color


def compare_color(color1: RgbFloatColor, color2: RgbFloatColor) -> bool:
    """Compare 2 RgbFloatColor objects"""
    return (color1.r, color1.g, color1.b) == (color2.r, color2.g, color2.b)


@pytest.mark.parametrize(
    "rectangle, expected",
    [
        (create_rectangle(0, 0, 100, 100), {"X": (0, 100), "Y": (0, 100)}),
        (create_rectangle(10, 20, 10, 50), {"X": (10, 20), "Y": (20, 70)}),
        (create_rectangle(0, -10, 400, 20), {"X": (0, 400), "Y": (-10, 10)}),
    ],
)
def test_compute_index_ranges(rectangle: IntRect, expected: Dict[str, Tuple[int, int]]) -> None:
    """Unit tests for compute_index_ranges function"""
    rectangle = CziReader._compute_index_ranges(rectangle)
    assert rectangle == expected


@pytest.mark.parametrize(
    "color, expected",
    [
        ("Bgr24", True),
        ("Bgr96Float", True),
        ("Bgr48", True),
        ("Gray8", False),
        ("Gray16", False),
        ("Gray32Float", False),
    ],
)
def test_is_rgb(color: str, expected: bool) -> None:
    """Unit tests for is_rgb function"""
    is_rgb = CziReader._is_rgb(color)
    assert is_rgb == expected


@pytest.mark.parametrize(
    "roi, expected",
    [
        (Rectangle(0, 0, 10, 10), create_rectangle(0, 0, 10, 10)),
        (Rectangle(0, 0, 100, -10), create_rectangle(0, 0, 100, -10)),
        (Rectangle(20, 30, 50, 10), create_rectangle(20, 30, 50, 10)),
    ],
)
def test_format_roi(roi: Rectangle, expected: IntRect) -> None:
    """Unit tests for format_roi function"""
    formatted_roi = CziReader._format_roi(roi)
    assert compare_rectangle(formatted_roi, expected)


@pytest.mark.parametrize(
    "plane, expected",
    [
        ({"C": 0, "T": 0, "Z": 8}, "C0 T0 Z8"),
        ({"R": 0, "Z": 100, "T": 8}, "R0 Z100 T8"),
        ({"C": 0, "T": 0, "Z": 8, "H": 200, "B": 3, "R": -1}, "C0 T0 Z8 H200 B3 R-1"),
        ({"C": 0}, "C0"),
    ],
)
def test_format_plane(plane: Dict[str, int], expected: str) -> None:
    """Unit tests for format_plane function"""
    formatted_plane = CziReader._format_plane(plane)
    assert formatted_plane == expected


@pytest.mark.parametrize(
    "color, expected",
    [
        (Color(0, 0, 0), create_color(0, 0, 0)),
        (Color(0.5, 0.8, 0), create_color(0.5, 0.8, 0)),
        (Color(0.3, -0.1, 0.2), create_color(0.3, -0.1, 0.2)),
    ],
)
def test_format_background_pixel(color: Color, expected: RgbFloatColor) -> None:
    """Unit tests for format_background_pixel function"""
    formatted_color = CziReader._format_background_pixel(color)
    assert compare_color(formatted_color, expected)


@pytest.mark.parametrize(
    "pixel_type, expected",
    [
        ("Bgr24", PixelType.Bgr24),
        ("Bgr96Float", PixelType.Bgr96Float),
        ("Bgr48", PixelType.Bgr48),
        ("Gray8", PixelType.Gray8),
        ("Gray16", PixelType.Gray16),
        ("Gray32Float", PixelType.Gray32Float),
    ],
)
def test_format_pixel_type(pixel_type: str, expected: PixelType) -> None:
    """Unit tests for format_pixel_type function"""
    formatted_pixel_type = CziReader._format_pixel_type(pixel_type)
    assert formatted_pixel_type == expected


def test_format_pixel_type_raises_error_on_incorrect_type() -> None:
    """Unit tests for format_pixel_type error message"""
    expected_error_message = (
        r"The pixel type provided does not mach any supported pixel types, possible values are: "
        r"Gray8, Gray16, Gray32Float, Bgr24, Bgr48, Bgr96Float"
    )
    with pytest.raises(ValueError, match=expected_error_message):
        CziReader._format_pixel_type("gray")


# testing properties and class functions

dimension_sizes_test1 = {
    DimensionIndex.Z: 0,
    DimensionIndex.C: 1,
    DimensionIndex.T: 0,
    DimensionIndex.R: 0,
    DimensionIndex.I: 0,
    DimensionIndex.H: 0,
    DimensionIndex.V: 0,
    DimensionIndex.B: 0,
    DimensionIndex.S: 2,
}

dimension_sizes_test2 = {
    DimensionIndex.Z: 0,
    DimensionIndex.C: 6,
    DimensionIndex.T: 0,
    DimensionIndex.R: 3,
    DimensionIndex.I: 1,
    DimensionIndex.H: 0,
    DimensionIndex.V: 10,
    DimensionIndex.B: 0,
    DimensionIndex.S: 1,
}

dimension_sizes_test3 = {
    DimensionIndex.Z: 3,
    DimensionIndex.C: 100,
    DimensionIndex.T: 2,
    DimensionIndex.R: 10,
    DimensionIndex.I: 4,
    DimensionIndex.H: 1,
    DimensionIndex.V: 12,
    DimensionIndex.B: 6,
    DimensionIndex.S: 5,
}


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "GetDimensionSize, boundingBox, expected_total_bounding_box",
    [
        (
            lambda x: 0,
            create_rectangle(0, 0, 10, 10),
            {"C": (0, 1), "T": (0, 1), "X": (0, 10), "Y": (0, 10), "Z": (0, 1)},
        ),
        (
            dimension_sizes_test1.get,
            create_rectangle(0, 0, 10, 10),
            {"C": (0, 1), "T": (0, 1), "X": (0, 10), "Y": (0, 10), "Z": (0, 1)},
        ),
        (
            dimension_sizes_test2.get,
            create_rectangle(10, 5, 200, 20),
            {
                "C": (0, 6),
                "I": (0, 1),
                "R": (0, 3),
                "T": (0, 1),
                "V": (0, 10),
                "X": (10, 210),
                "Y": (5, 25),
                "Z": (0, 1),
            },
        ),
        (
            dimension_sizes_test3.get,
            create_rectangle(-10, 10, 10, 10),
            {
                "X": (-10, 0),
                "Y": (10, 20),
                "C": (0, 100),
                "Z": (0, 3),
                "T": (0, 2),
                "R": (0, 10),
                "I": (0, 4),
                "H": (0, 1),
                "V": (0, 12),
                "B": (0, 6),
            },
        ),
    ],
)
def test_total_bounding_box(
    GetDimensionSize: Dict[DimensionIndex, int],
    boundingBox: IntRect,
    expected_total_bounding_box: Dict[str, Tuple[int, int]],
) -> None:
    """Unit tests for total_bounding_box function"""
    test_czi = CziReader("filepath")
    test_czi._stats.boundingBox = boundingBox
    test_czi._czi_reader.GetDimensionSize = GetDimensionSize
    assert test_czi.total_bounding_box == expected_total_bounding_box


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "scene_bounding_boxes, expected_scenes_bounding_rectangles",
    [
        ({0: create_rectangle(0, 0, 10, 10)}, {0: Rectangle(0, 0, 10, 10)}),
        ({16: create_rectangle(0, 0, 10, 10)}, {16: Rectangle(0, 0, 10, 10)}),
        (
            {0: create_rectangle(0, 0, 10, 10), 1: create_rectangle(123, 233, 231, 111)},
            {0: Rectangle(0, 0, 10, 10), 1: Rectangle(123, 233, 231, 111)},
        ),
        (
            {0: create_rectangle(0, 0, 10, 10), 24: create_rectangle(123, 233, 231, 111)},
            {0: Rectangle(0, 0, 10, 10), 24: Rectangle(123, 233, 231, 111)},
        ),
        (
            {1: create_rectangle(0, 0, 10, 10), 24: create_rectangle(123, 233, 231, 111)},
            {1: Rectangle(0, 0, 10, 10), 24: Rectangle(123, 233, 231, 111)},
        ),
    ],
)
def test_extract_scenes_bounding_box(
    scene_bounding_boxes: Dict[int, IntRect],
    expected_scenes_bounding_rectangles: Dict[int, Tuple[int, int, int, int]],
) -> None:
    """Unit tests for total_bounding_box function"""
    test_czi = CziReader("filepath")
    test_czi._stats.sceneBoundingBoxes = scene_bounding_boxes
    test_czi._czi_reader.GetDimensionSize = mock.Mock(return_value=len(scene_bounding_boxes))
    assert test_czi._extract_scenes_bounding_rectangles(lambda x: x) == expected_scenes_bounding_rectangles


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "scene_bounding_boxes, dimension_size",
    [
        ({0: create_rectangle(0, 0, 10, 10)}, 0),
        ({0: create_rectangle(0, 0, 10, 10), 1: create_rectangle(123, 233, 231, 111)}, 1),
        ({0: create_rectangle(0, 0, 10, 10), 24: create_rectangle(123, 233, 231, 111)}, 3),
        ({1: create_rectangle(0, 0, 10, 10), 24: create_rectangle(123, 233, 231, 111)}, -1),
    ],
)
def test_extract_scenes_bounding_box_raises_error(
    scene_bounding_boxes: Dict[int, IntRect],
    dimension_size: int,
) -> None:
    """Unit tests for total_bounding_box function"""
    test_czi = CziReader("filepath")
    test_czi._stats.sceneBoundingBoxes = scene_bounding_boxes
    test_czi._czi_reader.GetDimensionSize = mock.Mock(return_value=dimension_size)
    with pytest.raises(ValueError) as error:
        test_czi._extract_scenes_bounding_rectangles(lambda x: x)
    assert (
        str(error.value) == f"The number of scenes in the meta data ({dimension_size}) "
        f"does not match the number of available scene "
        f"bounding boxes ({len(scene_bounding_boxes)})."
    )


BoundingBoxes = NamedTuple("BoundingBoxes", [("boundingBox", IntRect)])

sceneBoundingBoxesTest1 = {
    0: BoundingBoxes(create_rectangle(0, 0, 100, 100)),
    1: BoundingBoxes(create_rectangle(10, 10, 20, 20)),
}

sceneBoundingBoxesTest2 = {
    0: BoundingBoxes(create_rectangle(0, 0, 1200, 1200)),
}

sceneBoundingBoxesTest3 = {
    0: BoundingBoxes(create_rectangle(0, 0, 100, 100)),
    1: BoundingBoxes(create_rectangle(10, 10, 10, 10)),
    2: BoundingBoxes(create_rectangle(0, 5, 100, 20)),
    3: BoundingBoxes(create_rectangle(5, 0, 20, 100)),
    4: BoundingBoxes(create_rectangle(100, 100, 100, 100)),
}


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "GetDimensionSize, sceneBoundingBoxes, expected_scenes_bounding_rectangle",
    [
        (lambda x: 0, {}, {}),
        (
            dimension_sizes_test1.get,
            sceneBoundingBoxesTest1,
            {0: Rectangle(0, 0, 100, 100), 1: Rectangle(10, 10, 20, 20)},
        ),
        (
            dimension_sizes_test2.get,
            sceneBoundingBoxesTest2,
            {0: Rectangle(0, 0, 1200, 1200)},
        ),
        (
            dimension_sizes_test3.get,
            sceneBoundingBoxesTest3,
            {
                0: Rectangle(0, 0, 100, 100),
                1: Rectangle(10, 10, 10, 10),
                2: Rectangle(0, 5, 100, 20),
                3: Rectangle(5, 0, 20, 100),
                4: Rectangle(100, 100, 100, 100),
            },
        ),
    ],
)
def test_scenes_bounding_rectangle(
    GetDimensionSize: Dict[DimensionIndex, int],
    sceneBoundingBoxes: Dict[int, IntRect],
    expected_scenes_bounding_rectangle: Dict[int, Rectangle],
) -> None:
    """Unit tests for scenes_bounding_rectangle function"""
    test_czi = CziReader("filepath")
    test_czi._stats.sceneBoundingBoxes = sceneBoundingBoxes
    test_czi._czi_reader.GetDimensionSize = GetDimensionSize
    assert test_czi.scenes_bounding_rectangle == expected_scenes_bounding_rectangle


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "GetSubBlockStats, expected_total_bounding_rectangle",
    [
        (BoundingBoxes(create_rectangle(0, 0, 10, 10)), Rectangle(0, 0, 10, 10)),
        (BoundingBoxes(create_rectangle(10, 20, 100, 10)), Rectangle(10, 20, 100, 10)),
    ],
)
def test_total_bounding_rectangle(
    GetSubBlockStats: BoundingBoxes, expected_total_bounding_rectangle: Rectangle
) -> None:
    """Unit tests for total_bounding_rectangle function"""
    test_czi = CziReader("filepath")
    test_czi._stats = GetSubBlockStats
    assert test_czi.total_bounding_rectangle == expected_total_bounding_rectangle


GetSubBlockStatsTest = NamedTuple("GetSubBlockStatsTest", [("boundingBox", IntRect), ("sceneBoundingBoxes", Dict)])


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "roi, scene, expected",
    [
        (None, None, Rectangle(0, 0, 1000, 1000)),
        (None, None, Rectangle(0, 0, 1000, 1000)),
        (None, 2, Rectangle(0, 5, 100, 20)),
        (None, 2, Rectangle(0, 5, 100, 20)),
        (Rectangle(0, 0, 100, 100), None, Rectangle(0, 0, 100, 100)),
        (Rectangle(0, 0, 100, 100), None, Rectangle(0, 0, 100, 100)),
        (Rectangle(0, 10, 100, 200), 2, Rectangle(0, 10, 100, 200)),
        (Rectangle(0, 10, 100, 200), 2, Rectangle(0, 10, 100, 200)),
    ],
)
def test_create_roi(roi: Optional[Rectangle], scene: Optional[int], expected: Rectangle) -> None:
    """Unit tests for _create_roi function"""
    test_czi = CziReader("filepath")
    test_czi._stats = GetSubBlockStatsTest(create_rectangle(0, 0, 1000, 1000), sceneBoundingBoxesTest3)
    test_czi._czi_reader.GetDimensionSize = dimension_sizes_test3.get
    assert test_czi._create_roi(roi, scene) == expected


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
def test_create_roi_raises_error_on_incorrect_scene() -> None:
    """Unit tests for _create_roi error messages"""
    expected_error_message = "The scene index provided does not mach existing scenes in the czi document"
    with pytest.raises(ValueError, match=expected_error_message):
        test_czi = CziReader("filepath")
        test_czi._stats = GetSubBlockStatsTest(create_rectangle(0, 0, 1000, 1000), sceneBoundingBoxesTest3)
        test_czi._czi_reader.GetDimensionSize = dimension_sizes_test3.get
        test_czi._create_roi(None, 10)


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "GetDimensionSize, expected",
    [
        (dimension_sizes_test1, {"C": 0}),
        (
            dimension_sizes_test2,
            {"C": 0, "I": 0, "R": 0, "V": 0},
        ),
        (
            dimension_sizes_test3,
            {"Z": 0, "C": 0, "T": 0, "R": 0, "I": 0, "H": 0, "V": 0, "B": 0},
        ),
    ],
)
def test_create_default_plane_coords(
    GetDimensionSize: Dict[DimensionIndex, int],
    expected: Dict[str, int],
) -> None:
    """Unit tests for _create_default_plane_coords function"""
    test_czi = CziReader("filepath")
    test_czi._czi_reader.GetDimensionSize = GetDimensionSize.get
    assert test_czi._create_default_plane_coords() == expected


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "plane, GetDimensionSize, expected",
    [
        (None, dimension_sizes_test1, {"C": 0}),
        ({"C": 1, "Z": 3, "T": 4}, dimension_sizes_test1, {"C": 1}),
        (
            {"C": 5, "Z": 3, "T": 4, "B": 12},
            dimension_sizes_test2,
            {"C": 5, "I": 0, "R": 0, "V": 0},
        ),
        (
            None,
            dimension_sizes_test3,
            {"Z": 0, "C": 0, "T": 0, "R": 0, "I": 0, "H": 0, "V": 0, "B": 0},
        ),
    ],
)
def test_create_plane_coords(
    plane: Optional[Dict[str, int]],
    GetDimensionSize: Dict[DimensionIndex, int],
    expected: Dict[str, int],
) -> None:
    """Unit tests for _create_plane_coords function"""
    test_czi = CziReader("filepath")
    test_czi._stats = GetSubBlockStatsTest(create_rectangle(0, 0, 1000, 1000), {})
    test_czi._czi_reader.GetDimensionSize = GetDimensionSize.get
    assert test_czi._create_plane_coords(plane) == expected


channel_pixel_types_test = {
    0: PixelType.Gray8,
    1: PixelType.Bgr48,
    2: PixelType.Bgr96Float,
    3: PixelType.Gray16,
}


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader", mock.Mock())
@pytest.mark.parametrize(
    "pixel_type, plane, expected",
    [
        (None, {"C": 0, "T": 4, "Z": 10}, "Gray8"),
        (None, {"B": 8, "C": 1, "T": 4, "Z": 10}, "Bgr48"),
        ("Gray16", {"B": 8, "C": 1, "T": 4, "Z": 10}, "Gray16"),
        ("Bgr96Float", {"B": 8, "C": 1, "T": 4, "Z": 10}, "Bgr96Float"),
    ],
)
def test_get_pixel_type(pixel_type: Optional[str], plane: Dict[str, int], expected: str) -> None:
    """Unit tests for _get_pixel_type function"""
    test_czi = CziReader("filepath")
    test_czi._czi_reader.GetChannelPixelType = channel_pixel_types_test.get
    assert test_czi._get_pixel_type(pixel_type, plane) == expected


@pytest.mark.parametrize(
    "pixel_data, expected",
    [
        (np.array([[[0], [0], [0]]]), np.array([[[0], [0], [0]]])),
        (np.array([[[0, 0, 0]]]), np.array([[[0, 0, 0]]])),
        (
            np.array(
                [
                    [[0, 18, 20], [20, 18, 50]],
                    [[15, 24, 25], [251, 45, 12]],
                    [[200, 10, 56], [20, 145, 14]],
                ]
            ),
            np.array(
                [
                    [[0, 18, 20], [20, 18, 50]],
                    [[15, 24, 25], [251, 45, 12]],
                    [[200, 10, 56], [20, 145, 14]],
                ]
            ),
        ),
        (
            np.array(
                [
                    [[0], [18], [20], [20], [18], [50]],
                    [[15], [24], [25], [251], [45], [12]],
                    [[200], [10], [56], [20], [145], [14]],
                ]
            ),
            np.array(
                [
                    [[0], [18], [20], [20], [18], [50]],
                    [[15], [24], [25], [251], [45], [12]],
                    [[200], [10], [56], [20], [145], [14]],
                ]
            ),
        ),
    ],
)
def test_get_array_from_bitmap(pixel_data: np.ndarray, expected: np.ndarray) -> None:
    """Unit tests for get_array_from_bitmap function"""
    generated_array = CziReader._get_array_from_bitmap(pixel_data)
    np.testing.assert_array_equal(generated_array, expected)


def test_array_shape() -> None:
    """Unit tests for checking the shape of the input pixel_data"""
    with pytest.raises(ValueError, match="Incorrect shape"):
        CziReader._get_array_from_bitmap(np.array([[0], [0], [0]]))
