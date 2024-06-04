"""Module implementing minimal integration tests for CziReader using URI"""

from typing import Dict, Tuple, Optional
import tempfile
import os
import pytest

from pylibCZIrw.czi import create_czi, open_czi, Rectangle, ReaderFileInputTypes

working_dir = os.path.dirname(os.path.abspath(__file__))

# Note: This file is not part of the repo and so is untracked. If tests fail, make sure that this have not been deleted.
CZI_DOCUMENT_TEST1 = "https://cadevelop.blob.core.windows.net/public/pylibCZIrwTestFiles/c1_bgr24_t1_z1_h1.czi"
EXPECTED_METADATA_TEST1 = os.path.join(working_dir, "test_data", "c1_bgr24_t1_z1_h1_metadata.txt")


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, EXPECTED_METADATA_TEST1),
    ],
)
def test_raw_metadata(czi_path: str, expected: str) -> None:
    """Integration tests for the raw_metadata function"""
    with open_czi(czi_path, file_input_type=ReaderFileInputTypes.Curl) as czi_document:
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
    ],
)
def test_total_bounding_box(czi_path: str, expected: Dict[str, Tuple[int, int]]) -> None:
    """Integration tests for the total_bounding_box function"""
    with open_czi(czi_path, file_input_type=ReaderFileInputTypes.Curl) as czi_document:
        assert czi_document.total_bounding_box == expected
        assert czi_document.total_bounding_box_no_pyramid == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, {}),
    ],
)
def test_scenes_bounding_rectangle(czi_path: str, expected: Dict[int, Rectangle]) -> None:
    """Integration tests for the scenes_bounding_rectangle function"""
    with open_czi(czi_path, file_input_type=ReaderFileInputTypes.Curl) as czi_document:
        assert czi_document.scenes_bounding_rectangle == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, Rectangle(x=0, y=0, w=256, h=256)),
    ],
)
def test_total_bounding_rectangle(czi_path: str, expected: Rectangle) -> None:
    """Integration tests for the total_bounding_rectangle function"""
    with open_czi(czi_path, file_input_type=ReaderFileInputTypes.Curl) as czi_document:
        assert czi_document.total_bounding_rectangle == expected
        assert czi_document.total_bounding_rectangle_no_pyramid == expected


@pytest.mark.parametrize(
    "czi_path, channel_index, expected",
    [
        (CZI_DOCUMENT_TEST1, 0, "Bgr24"),
    ],
)
def test_get_channel_pixel_type(czi_path: str, channel_index: int, expected: str) -> None:
    """Integration tests for the get_channel_pixel_type function"""
    with open_czi(czi_path, file_input_type=ReaderFileInputTypes.Curl) as czi_document:
        assert czi_document.get_channel_pixel_type(channel_index) == expected


@pytest.mark.parametrize(
    "czi_path, expected",
    [
        (CZI_DOCUMENT_TEST1, {0: "Bgr24"}),
    ],
)
def test_pixel_types(czi_path: str, expected: Dict[int, str]) -> None:
    """Integration tests for the pixel_types function"""
    with open_czi(czi_path, file_input_type=ReaderFileInputTypes.Curl) as czi_document:
        assert czi_document.pixel_types == expected


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
