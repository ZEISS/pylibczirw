"""Module implementing unit tests for subblock enumeration functionality"""

from typing import Dict
from unittest import mock

import pytest

# pylint: disable=no-name-in-module
from _pylibCZIrw import (
    CompressionMode,
    DimCoordinate,
    DimensionIndex,
    IntSize,
    SubBlockInfo,
)
from pylibCZIrw.czi import CziReader, Rectangle


def create_dim_coordinate_from_string(coord_str: str) -> DimCoordinate:
    """Creates a DimCoordinate from a coordinate string."""
    return DimCoordinate(coord_str)


def create_dim_coordinate_from_dict(coord_dict: Dict[str, int]) -> DimCoordinate:
    """Creates a DimCoordinate from a dictionary."""
    return DimCoordinate(coord_dict)


def create_int_size(w: int, h: int) -> IntSize:
    """Creates an IntSize object."""
    size = IntSize()
    size.w = w
    size.h = h
    return size


def compare_int_size(size1: IntSize, size2: IntSize) -> bool:
    """Compare two IntSize objects."""
    return (size1.w, size1.h) == (size2.w, size2.h)


@pytest.mark.parametrize(
    "coord_string, expected_dict",
    [
        ("C0", {"C": 0}),
        ("C0Z5", {"C": 0, "Z": 5}),
        ("C0Z5T2", {"C": 0, "Z": 5, "T": 2}),
        ("T10Z3C1", {"T": 10, "Z": 3, "C": 1}),
        ("C0Z5T2H1", {"C": 0, "Z": 5, "T": 2, "H": 1}),
    ],
)
def test_dim_coordinate_from_string(coord_string: str, expected_dict: Dict[str, int]) -> None:
    """Test creating DimCoordinate from coordinate string."""
    coord = create_dim_coordinate_from_string(coord_string)
    result_dict = coord.to_dict()
    assert result_dict == expected_dict


@pytest.mark.parametrize(
    "coord_dict, expected_dict",
    [
        ({"C": 0}, {"C": 0}),
        ({"C": 0, "Z": 5}, {"C": 0, "Z": 5}),
        ({"C": 0, "Z": 5, "T": 2}, {"C": 0, "Z": 5, "T": 2}),
        ({"T": 10, "Z": 3, "C": 1}, {"T": 10, "Z": 3, "C": 1}),
        ({"C": 0, "Z": 5, "T": 2, "H": 1}, {"C": 0, "Z": 5, "T": 2, "H": 1}),
    ],
)
def test_dim_coordinate_from_dict(coord_dict: Dict[str, int], expected_dict: Dict[str, int]) -> None:
    """Test creating DimCoordinate from dictionary."""
    coord = create_dim_coordinate_from_dict(coord_dict)
    result_dict = coord.to_dict()
    assert result_dict == expected_dict


@pytest.mark.parametrize(
    "coord_dict, dimension, expected_value",
    [
        ({"C": 0, "Z": 5}, DimensionIndex.C, 0),
        ({"C": 0, "Z": 5}, DimensionIndex.Z, 5),
        ({"C": 0, "Z": 5, "T": 2}, DimensionIndex.T, 2),
        ({"T": 10}, DimensionIndex.T, 10),
    ],
)
def test_dim_coordinate_try_get_position(
    coord_dict: Dict[str, int], dimension: DimensionIndex, expected_value: int
) -> None:
    """Test getting position from DimCoordinate."""
    coord = create_dim_coordinate_from_dict(coord_dict)
    value = coord.try_get_position(dimension)
    assert value == expected_value


@pytest.mark.parametrize(
    "coord_dict, dimension",
    [
        ({"C": 0}, DimensionIndex.Z),
        ({"C": 0, "Z": 5}, DimensionIndex.T),
        ({"T": 10}, DimensionIndex.C),
    ],
)
def test_dim_coordinate_try_get_position_returns_none(coord_dict: Dict[str, int], dimension: DimensionIndex) -> None:
    """Test getting position from DimCoordinate returns None for unset dimensions."""
    coord = create_dim_coordinate_from_dict(coord_dict)
    value = coord.try_get_position(dimension)
    assert value is None


@pytest.mark.parametrize(
    "width, height",
    [
        (100, 200),
        (256, 256),
        (1024, 768),
        (512, 1024),
    ],
)
def test_int_size_creation(width: int, height: int) -> None:
    """Test creating IntSize objects."""
    size = create_int_size(width, height)
    assert size.w == width
    assert size.h == height


def test_compression_mode_enum() -> None:
    """Test CompressionMode enum values."""
    assert CompressionMode.Invalid.name == "Invalid"
    assert CompressionMode.UnCompressed.name == "UnCompressed"
    assert CompressionMode.Jpg.name == "Jpg"
    assert CompressionMode.JpgXr.name == "JpgXr"
    assert CompressionMode.Zstd0.name == "Zstd0"
    assert CompressionMode.Zstd1.name == "Zstd1"


def test_subblock_info_structure() -> None:
    """Test that SubBlockInfo has expected attributes."""
    info = SubBlockInfo()

    assert hasattr(info, "compressionModeRaw")
    assert hasattr(info, "pixelType")
    assert hasattr(info, "coordinate")
    assert hasattr(info, "logicalRect")
    assert hasattr(info, "physicalSize")
    assert hasattr(info, "mIndex")

    assert hasattr(info, "get_compression_mode")
    assert hasattr(info, "get_zoom")
    assert hasattr(info, "is_mindex_valid")


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader")
def test_enumerate_subblocks_calls_underlying_method(mock_reader_class) -> None:  # type: ignore
    """Test that enumerate_subblocks calls the underlying C++ method."""

    mock_instance = mock.Mock()
    mock_reader_class.return_value = mock_instance
    mock_instance.GetSubBlockStats.return_value = mock.Mock(
        boundingBox=mock.Mock(x=0, y=0, w=100, h=100),
        boundingBoxLayer0Only=mock.Mock(x=0, y=0, w=100, h=100),
    )

    reader = CziReader("test.czi")

    callback_called = {"count": 0}

    def callback(_index, _info):  # type: ignore
        callback_called["count"] += 1
        return True

    reader.enumerate_subblocks(callback)

    mock_instance.EnumerateSubBlocks.assert_called_once()


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader")
def test_enumerate_subblocks_subset_with_string_coordinate(mock_reader_class) -> None:  # type: ignore
    """Test enumerate_subblocks_subset with string coordinate."""
    mock_instance = mock.Mock()
    mock_reader_class.return_value = mock_instance
    mock_instance.GetSubBlockStats.return_value = mock.Mock(
        boundingBox=mock.Mock(x=0, y=0, w=100, h=100),
        boundingBoxLayer0Only=mock.Mock(x=0, y=0, w=100, h=100),
    )

    reader = CziReader("test.czi")

    def callback(_index, _info):  # type: ignore
        return True

    reader.enumerate_subblocks_subset(callback, plane="C0Z5", only_layer0=True)

    mock_instance.EnumerateSubset.assert_called_once()


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader")
def test_enumerate_subblocks_subset_with_dict_coordinate(mock_reader_class) -> None:  # type: ignore
    """Test enumerate_subblocks_subset with dict coordinate."""
    mock_instance = mock.Mock()
    mock_reader_class.return_value = mock_instance
    mock_instance.GetSubBlockStats.return_value = mock.Mock(
        boundingBox=mock.Mock(x=0, y=0, w=100, h=100),
        boundingBoxLayer0Only=mock.Mock(x=0, y=0, w=100, h=100),
    )

    reader = CziReader("test.czi")

    def callback(_index, _info):  # type: ignore
        return True

    reader.enumerate_subblocks_subset(callback, plane={"C": 0, "Z": 5}, only_layer0=True)

    mock_instance.EnumerateSubset.assert_called_once()


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader")
def test_enumerate_subblocks_subset_with_roi(mock_reader_class) -> None:  # type: ignore
    """Test enumerate_subblocks_subset with ROI."""

    mock_instance = mock.Mock()
    mock_reader_class.return_value = mock_instance
    mock_instance.GetSubBlockStats.return_value = mock.Mock(
        boundingBox=mock.Mock(x=0, y=0, w=100, h=100),
        boundingBoxLayer0Only=mock.Mock(x=0, y=0, w=100, h=100),
    )

    reader = CziReader("test.czi")

    def callback(_index, _info):  # type: ignore
        return True

    reader.enumerate_subblocks_subset(callback, roi=(10, 20, 100, 100), only_layer0=False)

    mock_instance.EnumerateSubset.assert_called_once()


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_reader")
def test_enumerate_subblocks_subset_with_all_filters(mock_reader_class) -> None:  # type: ignore
    """Test enumerate_subblocks_subset with all filter options."""
    mock_instance = mock.Mock()
    mock_reader_class.return_value = mock_instance
    mock_instance.GetSubBlockStats.return_value = mock.Mock(
        boundingBox=mock.Mock(x=0, y=0, w=100, h=100),
        boundingBoxLayer0Only=mock.Mock(x=0, y=0, w=100, h=100),
    )

    reader = CziReader("test.czi")

    def callback(_index, _info):  # type: ignore
        return True

    reader.enumerate_subblocks_subset(
        callback,
        plane={"C": 0, "Z": 5, "T": 2},
        roi=Rectangle(10, 20, 100, 100),
        only_layer0=True,
    )

    mock_instance.EnumerateSubset.assert_called_once()
