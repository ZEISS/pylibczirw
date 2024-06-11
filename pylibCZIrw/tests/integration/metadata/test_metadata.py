"""Module implementing integration tests for the properties of the CziReader class"""

import os
import tempfile
from typing import Any, Dict, Optional, Tuple
from unittest.mock import PropertyMock, patch

import numpy as np
import pytest
import xmltodict
from pylibCZIrw.czi import CziReader, Rectangle, create_czi, open_czi

working_dir = os.path.dirname(os.path.abspath(__file__))

CZI_DOCUMENT_TEST1 = os.path.join(working_dir, "test_data", "c1_bgr24_t1_z1_h1.czi")
EXPECTED_METADATA_TEST1 = os.path.join(working_dir, "test_data", "c1_bgr24_t1_z1_h1_metadata.txt")

CZI_DOCUMENT_TEST2 = os.path.join(
    working_dir,
    "test_data",
    "c1_gray8_t1_z1_h1_s2_overlapping_subblocks_accross_scenes.czi",
)

EXPECTED_METADATA_TEST2 = os.path.join(
    working_dir,
    "test_data",
    "c1_gray8_t1_z1_h1_s2_overlapping_subblocks_accross_scenes_metadata.txt",
)

CZI_DOCUMENT_TEST3 = os.path.join(working_dir, "test_data", "c1_bgr24.czi")
EXPECTED_METADATA_TEST3 = os.path.join(working_dir, "test_data", "c1_bgr24_metadata.txt")

CZI_DOCUMENT_TEST4 = os.path.join(working_dir, "test_data", "c2_gray8_gray16_t1_z1_h1.czi")
EXPECTED_METADATA_TEST4 = os.path.join(working_dir, "test_data", "c2_gray8_gray16_t1_z1_h1_metadata.txt")

CZI_DOCUMENT_TEST5 = os.path.join(working_dir, "test_data", "c2_gray8_t3_z5_h1_s2.czi")
EXPECTED_METADATA_TEST5 = os.path.join(working_dir, "test_data", "c2_gray8_t3_z5_h1_s2_metadata.txt")

CZI_DOCUMENT_TEST6 = os.path.join(working_dir, "test_data", "test_additional_metadata.czi")
EXPECTED_METADATA_TEST6 = os.path.join(working_dir, "test_data", "test_additional_metadata_metadata.txt")


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, EXPECTED_METADATA_TEST1),
        (CZI_DOCUMENT_TEST2, EXPECTED_METADATA_TEST2),
        (CZI_DOCUMENT_TEST3, EXPECTED_METADATA_TEST3),
        (CZI_DOCUMENT_TEST4, EXPECTED_METADATA_TEST4),
        (CZI_DOCUMENT_TEST5, EXPECTED_METADATA_TEST5),
    ],
)
def test_raw_metadata(czi_path: str, expected: str) -> None:
    """Integration tests for the raw_metadata function"""
    with open_czi(czi_path) as czi_document:
        metadata = czi_document.raw_metadata
    with open(expected, "r", encoding="utf-8") as content:
        expected_metadata = content.read()
    assert metadata == expected_metadata


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (
            CZI_DOCUMENT_TEST1,
            {
                "C": (0, 1),
                "H": (0, 1),
                "T": (0, 1),
                "X": (0, 256),
                "Y": (0, 256),
                "Z": (0, 1),
            },
        ),
        (
            CZI_DOCUMENT_TEST2,
            {
                "C": (0, 1),
                "H": (0, 1),
                "T": (0, 1),
                "X": (0, 615),
                "Y": (0, 600),
                "Z": (0, 1),
            },
        ),
        (
            CZI_DOCUMENT_TEST3,
            {"T": (0, 1), "Z": (0, 1), "C": (0, 1), "X": (0, 1200), "Y": (0, 1000)},
        ),
        (
            CZI_DOCUMENT_TEST4,
            {
                "C": (0, 2),
                "H": (0, 1),
                "T": (0, 1),
                "X": (0, 256),
                "Y": (0, 256),
                "Z": (0, 1),
            },
        ),
        (
            CZI_DOCUMENT_TEST5,
            {
                "C": (0, 2),
                "H": (0, 1),
                "T": (0, 3),
                "X": (-1405, -230),
                "Y": (-414, 666),
                "Z": (0, 5),
            },
        ),
    ],
)
def test_total_bounding_box(czi_path: str, expected: Dict[str, Tuple[int, int]]) -> None:
    """Integration tests for the total_bounding_box function"""
    with open_czi(czi_path) as czi_document:
        assert czi_document.total_bounding_box == expected
        assert czi_document.total_bounding_box_no_pyramid == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, {}),
        (
            CZI_DOCUMENT_TEST2,
            {
                0: Rectangle(x=0, y=0, w=486, h=486),
                1: Rectangle(x=129, y=114, w=486, h=486),
            },
        ),
        (CZI_DOCUMENT_TEST3, {}),
        (CZI_DOCUMENT_TEST4, {}),
        (
            CZI_DOCUMENT_TEST5,
            {
                0: Rectangle(x=-1405, y=-414, w=512, h=512),
                1: Rectangle(x=-742, y=154, w=512, h=512),
            },
        ),
    ],
)
def test_scenes_bounding_rectangle(czi_path: str, expected: Dict[int, Rectangle]) -> None:
    """Integration tests for the scenes_bounding_rectangle function"""
    with open_czi(czi_path) as czi_document:
        assert czi_document.scenes_bounding_rectangle == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, Rectangle(x=0, y=0, w=256, h=256)),
        (CZI_DOCUMENT_TEST2, Rectangle(x=0, y=0, w=615, h=600)),
        (CZI_DOCUMENT_TEST3, Rectangle(x=0, y=0, w=1200, h=1000)),
        (CZI_DOCUMENT_TEST4, Rectangle(x=0, y=0, w=256, h=256)),
        (CZI_DOCUMENT_TEST5, Rectangle(x=-1405, y=-414, w=1175, h=1080)),
    ],
)
def test_total_bounding_rectangle(czi_path: str, expected: Rectangle) -> None:
    """Integration tests for the total_bounding_rectangle function"""
    with open_czi(czi_path) as czi_document:
        assert czi_document.total_bounding_rectangle == expected
        assert czi_document.total_bounding_rectangle_no_pyramid == expected


@pytest.mark.parametrize(
    "czi_path, channel_index, expected",
    [
        (CZI_DOCUMENT_TEST1, 0, "Bgr24"),
        (CZI_DOCUMENT_TEST2, 0, "Gray8"),
        (CZI_DOCUMENT_TEST3, 0, "Bgr24"),
        (CZI_DOCUMENT_TEST4, 0, "Gray8"),
        (CZI_DOCUMENT_TEST4, 1, "Gray16"),
        (CZI_DOCUMENT_TEST5, 0, "Gray8"),
        (CZI_DOCUMENT_TEST5, 1, "Gray8"),
    ],
)
def test_get_channel_pixel_type(czi_path: str, channel_index: int, expected: str) -> None:
    """Integration tests for the get_channel_pixel_type function"""
    with open_czi(czi_path) as czi_document:
        assert czi_document.get_channel_pixel_type(channel_index) == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, {0: "Bgr24"}),
        (CZI_DOCUMENT_TEST2, {0: "Gray8"}),
        (CZI_DOCUMENT_TEST3, {0: "Bgr24"}),
        (CZI_DOCUMENT_TEST4, {0: "Gray8", 1: "Gray16"}),
        (CZI_DOCUMENT_TEST5, {0: "Gray8", 1: "Gray8"}),
    ],
)
def test_pixel_types(czi_path: str, expected: Dict[int, str]) -> None:
    """Integration tests for the pixel_types function"""
    with open_czi(czi_path) as czi_document:
        assert czi_document.pixel_types == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [(CZI_DOCUMENT_TEST6, EXPECTED_METADATA_TEST6)],
)
def test_additional(czi_path: str, expected: str) -> None:
    """Integration tests for receiving all metadata"""
    with open(expected, "r", encoding="utf-8") as content:
        expected_metadata = xmltodict.parse(content.read())
    with open_czi(czi_path) as czi_document:
        actual_metadata = czi_document.metadata

    assert actual_metadata == expected_metadata


@pytest.mark.parametrize(
    "scale_x, scale_y, scale_z",
    [
        (1.0, 2.0, 3.0),
        (None, 1.0, 2.0),
        (1.0, None, 2.0),
        (1.0, 2.0, None),
        (1.0, None, None),
        (None, None, 1.0),
        (None, 1.0, None),
        (None, None, None),
    ],
)
def test_none_scaling_values(scale_x: Optional[float], scale_y: Optional[float], scale_z: Optional[float]) -> None:
    """Test if write metadata accepts None values for scaling"""
    with tempfile.TemporaryDirectory() as temp_directory:
        with create_czi(os.path.join(temp_directory, "./test.czi")) as test_czi:
            test_czi.write_metadata(scale_x=scale_x, scale_y=scale_y, scale_z=scale_z)


@pytest.mark.parametrize(
    "custom_attributes",
    [
        None,
        {"key1": "123", "key2": "456"},
        {"key1": 123, "key2": 456},
        {"key1": True, "key2": False},
        {"key1": 22.5, "key2": 11.5},
    ],
)
def test_custom_attributes(custom_attributes: Optional[Dict[str, Any]]) -> None:
    """Test if write metadata accepts the custom attributes and writing and reading it in XML metadata correctly"""
    with tempfile.TemporaryDirectory() as temp_directory:
        with create_czi(os.path.join(temp_directory, "./test.czi")) as test_czi:
            test_czi.write_metadata(custom_attributes=custom_attributes)
        with open_czi(os.path.join(temp_directory, "./test.czi")) as czi_document:
            actual_data = czi_document.custom_attributes_metadata
        assert actual_data == custom_attributes


@pytest.mark.parametrize(
    "custom_attributes",
    [
        {"key1": [1, 2]},
        {"key1": (1, 2)},
    ],
)
def test_custom_attributes_write_error(custom_attributes: Optional[Dict[str, Any]]) -> None:
    """Test if throws errors when the type of custom attributes is not accepted while writing"""
    with tempfile.TemporaryDirectory() as temp_directory:
        with create_czi(os.path.join(temp_directory, "./test.czi")) as test_czi:
            with pytest.raises(ValueError):
                test_czi.write_metadata(custom_attributes=custom_attributes)


@pytest.mark.parametrize(
    "custom_attributes",
    [
        {"key1": {"@Type": "SomeType", "#text": 123}},
    ],
)
@patch("pylibCZIrw.czi.CziReader.metadata", new_callable=PropertyMock)
def test_custom_attributes_read_error(
    metadata_patch: PropertyMock, custom_attributes: Optional[Dict[str, Any]]
) -> None:
    """Test if throws errors when the type of custom attributes is not accepted while reading"""
    metadata_patch.return_value = {
        "ImageDocument": {"Metadata": {"Information": {"CustomAttributes": {"KeyValue": custom_attributes}}}}
    }
    with patch.object(CziReader, "__init__", lambda x, y: None):
        czi_reader = CziReader("some dummy string")
        with pytest.raises(ValueError):
            _ = czi_reader.custom_attributes_metadata


def test_zoom() -> None:
    """Testing the zoom while reading the image."""
    with tempfile.TemporaryDirectory() as temp_directory:
        with create_czi(os.path.join(temp_directory, "./test.czi")) as test_czi:
            test_czi.write(np.zeros((128, 163, 3), dtype=np.uint8))
            test_czi.write_metadata()
        with open_czi(os.path.join(temp_directory, "./test.czi")) as czi_document:
            czi_document.read(zoom=0.25)


@pytest.mark.parametrize(
    "shape",
    [
        (163, 163, 3),
        (159, 163, 3),
        (258, 258, 3),
    ],
)
def test_write_read_if_same(shape: Tuple[int, int, int]) -> None:
    """Tests the data loaded by reader is equal to the data written to writer."""
    original_data = (np.random.random(shape) * 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as temp_directory:
        with create_czi(os.path.join(temp_directory, "./test.czi"), exist_ok=True) as write_czi:
            write_czi.write(original_data)
            write_czi.write_metadata()
        with open_czi(os.path.join(temp_directory, "./test.czi")) as read_czi:
            data_loaded = read_czi.read(zoom=1)
            np.testing.assert_array_equal(original_data, data_loaded)
