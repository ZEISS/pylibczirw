"""Module implementing integration tests for the write function of the CziWriter class"""
import os
from os.path import join, abspath, dirname
from collections import OrderedDict
import tempfile
from typing import List, Tuple, Optional, Union, Iterator, Dict
from unittest.mock import patch, MagicMock
import pytest
import numpy as np

from pylibCZIrw.czi import create_czi, ChannelDisplaySettingsDataClass, Rgb8Color, TintingMode
from pylibCZIrw.czi import open_czi

working_dir = dirname(abspath(__file__))

CZI_DOCUMENT_TEST_WRITE1 = join(working_dir, "../test_data", "c1_bgr24.czi")
EXPECTED_PLANE_TEST1 = np.load(join(working_dir, "../test_data", "c1_bgr24_plane.npz"))["arr"]

CZI_DOCUMENT_TEST_WRITE2 = join(working_dir, "../test_data", "c1_bgr48.czi")
EXPECTED_PLANE_TEST2 = np.load(join(working_dir, "../test_data", "c1_bgr48_plane.npz"))["arr"]

CZI_DOCUMENT_TEST_WRITE3 = join(working_dir, "../test_data", "c1_gray8.czi")
EXPECTED_PLANE_TEST3 = np.load(join(working_dir, "../test_data", "c1_gray8_plane.npz"))["arr"]


def get_plane(path: str, roi: Optional[Tuple[int, int, int, int]]) -> np.ndarray:
    """Open the czi and returns the plane"""
    with open_czi(path) as czi_document:
        return czi_document.read(roi=roi)


@pytest.mark.parametrize(
    "plane, location, roi, expected",
    [
        (CZI_DOCUMENT_TEST_WRITE1, (0, 0), None, EXPECTED_PLANE_TEST1),
        (
            CZI_DOCUMENT_TEST_WRITE1,
            (0, 0),
            (0, 0, 100, 100),
            EXPECTED_PLANE_TEST1[
                0:100,
                0:100,
            ],
        ),
        (CZI_DOCUMENT_TEST_WRITE2, (0, 0), None, EXPECTED_PLANE_TEST2),
        (
            CZI_DOCUMENT_TEST_WRITE2,
            (50, 20),
            (50, 20, 10, 10),
            EXPECTED_PLANE_TEST2[
                20:30,
                50:60,
            ],
        ),
        (CZI_DOCUMENT_TEST_WRITE3, (0, 0), None, EXPECTED_PLANE_TEST3),
    ],
)
def test_write_roi_pixeltypes(
    plane: str, location: Tuple[int, int], roi: Optional[Tuple[int, int, int, int]], expected: np.ndarray
) -> None:
    """Integration tests for the basic features of the write function"""
    with tempfile.TemporaryDirectory() as temp_directory:
        original_plane = get_plane(plane, roi)
        with create_czi(join(temp_directory, "test.czi")) as test_czi:
            test_czi.write(original_plane, location=location)
            test_czi.write_metadata()
        plane_written = get_plane(join(temp_directory, "test.czi"), roi)

        np.testing.assert_array_equal(plane_written, expected)


def test_write_existing_file_gets_overwritten_when_exist_ok_is_true() -> None:
    """Tests that an existing file gets silently overwritten if exist_ok is set to True."""

    def _write_czi() -> None:
        with create_czi(join(td, "test.czi"), exist_ok=True) as test_czi:
            test_czi.write(original_plane, location=(0, 0))
            test_czi.write_metadata()

    original_plane = get_plane(CZI_DOCUMENT_TEST_WRITE1, None)
    with tempfile.TemporaryDirectory() as td:
        _write_czi()
        _write_czi()


def test_write_throw_if_file_exists_and_exist_ok_is_false() -> None:
    """Tests that an error is thrown if a file exists and exist_ok is set to False."""

    def _write_czi() -> None:
        with create_czi(join(td, "test.czi"), exist_ok=False) as test_czi:
            test_czi.write(original_plane, location=(0, 0))
            test_czi.write_metadata()

    original_plane = get_plane(CZI_DOCUMENT_TEST_WRITE1, None)
    with tempfile.TemporaryDirectory() as td:
        _write_czi()
        with pytest.raises(FileExistsError):
            _write_czi()


def test_write_throw_if_file_exists_and_exist_ok_is_not_specified() -> None:
    """Tests that an error is thrown if a file exists and exist_ok is not explicitly specified."""

    def _write_czi() -> None:
        with create_czi(join(td, "test.czi")) as test_czi:
            test_czi.write(original_plane, location=(0, 0))
            test_czi.write_metadata()

    original_plane = get_plane(CZI_DOCUMENT_TEST_WRITE1, None)
    with tempfile.TemporaryDirectory() as td:
        _write_czi()
        with pytest.raises(FileExistsError):
            _write_czi()


@pytest.mark.parametrize(
    "exist_ok, path",
    [
        pytest.param(False, "", id="exist_ok_False_No_Intermediate"),
        pytest.param(False, "intermediate", id="exist_ok_False_Intermediate"),
        pytest.param(True, "", id="exist_ok_True_No_Intermediate"),
        pytest.param(True, "intermediate", id="exist_ok_True_Intermediate"),
    ],
)
def test_write_succeeds_if_file_does_not_exist(exist_ok: bool, path: str) -> None:
    """Tests that file is written if it does not exist (independent of exist_ok or missing path segments).

    Parameters
    ----------
    path : str
        File path.
    exist_ok: bool
        Whether to throw if the file already exists (i.e. if exist_ok = False)
    """
    original_plane = get_plane(CZI_DOCUMENT_TEST_WRITE1, None)
    with tempfile.TemporaryDirectory() as td:
        with create_czi(join(td, path, "test.czi"), exist_ok=exist_ok) as test_czi:
            test_czi.write(original_plane, location=(0, 0))
            test_czi.write_metadata()


def test_write_metadata_application_version_matches_package_version() -> None:
    """Tests that Metadata/Information/Application/Version matches the package version as specified in setup.py"""
    # Arrange
    # retrieve version as generated through setup.py (locally) or env set through python-semantic-release in pipeline
    setup_version = os.getenv("PYTHON_SEMANTIC_RELEASE_VERSION")
    if setup_version is None:
        root = join(abspath(dirname(dirname(dirname(dirname(dirname(__file__)))))))
        with open(join(root, "setup.py"), encoding="utf-8") as f:
            readme = f.readlines()
            for line in readme:
                if "VERSION" in line:
                    setup_version = line.split('"')[1]
                    break

    assert setup_version is not None

    original_plane = get_plane(CZI_DOCUMENT_TEST_WRITE1, None)
    with tempfile.TemporaryDirectory() as td:
        # Act
        with create_czi(join(td, "test.czi")) as test_czi:
            test_czi.write(original_plane, location=(0, 0))
            test_czi.write_metadata()
        # Assert
        with open_czi(join(td, "test.czi")) as czi_document:
            actual_metadata = czi_document.metadata
        assert actual_metadata["ImageDocument"]["Metadata"]["Information"]["Application"]["Version"] == setup_version


@pytest.mark.parametrize(
    "channel_names, display_settings, expected",
    [
        (
            {0: "TestCh0", 1: "TestCh1"},
            {
                0: ChannelDisplaySettingsDataClass(
                    True, TintingMode.Color, Rgb8Color(np.uint8(0x01), np.uint8(0x02), np.uint8(0x03)), 0.2, 0.8
                ),
                1: ChannelDisplaySettingsDataClass(
                    True, TintingMode.Color, Rgb8Color(np.uint8(0xFF), np.uint8(0xFE), np.uint8(0xFD)), 0.3, 0.7
                ),
            },
            [
                {"IsSelected": "true", "Color": "#FF010203", "ColorMode": "Color", "Low": "0.2", "High": "0.8"},
                {"IsSelected": "true", "Color": "#FFFFFEFD", "ColorMode": "Color", "Low": "0.3", "High": "0.7"},
            ],
        ),
        (None, None, None),
    ],
)
def test_write_sample_metadata_and_compare(
    channel_names: Dict[int, str],
    display_settings: Optional[Dict[int, ChannelDisplaySettingsDataClass]],
    expected: List[Dict[str, str]],
) -> None:
    """Tests that Metadata matches the given metatadata"""

    def __flatten(setting: Union[List[OrderedDict], OrderedDict]) -> Iterator[OrderedDict]:
        """Flattens the list of display settings independent of whether
        there are multiple settings present for the same key.
        """
        if isinstance(setting, list):
            for curr_setting in setting:
                yield from __flatten(curr_setting)
        else:
            yield setting

    # Act
    with tempfile.TemporaryDirectory() as td:
        # Act
        with create_czi(join(td, "test.czi")) as test_czi:
            test_czi.write_metadata(
                document_name="TestWriteMetadata",
                scale_x=1.0,
                scale_y=2.0,
                scale_z=3.0,
                channel_names=channel_names,
                display_settings=display_settings,
            )
        # Assert
        with open_czi(join(td, "test.czi")) as czi_document:
            actual_metadata = czi_document.metadata
        actual_display_settings = actual_metadata["ImageDocument"]["Metadata"].get("DisplaySetting", None)
        if actual_display_settings:
            channels_parsed = list(__flatten(list(actual_display_settings["Channels"].values())))
        else:
            channels_parsed = None
        assert channels_parsed == expected  # Do not rely on name of channels but rather the order


@pytest.mark.parametrize(
    "shape",
    [(3600, 3600, 3), (3601, 3601, 3), (20, 400000, 3), (3601, 3601, 1), (480, 640), (3008, 4096)],
)
@patch("_pylibCZIrw.czi_writer.AddTile")
def test_different_image_shapes(_divide_image_patch: MagicMock, shape: Tuple[int, int, int]) -> None:
    """Tests that image data is divided correctly based on its size.

    Parameters
    ----------
    shape : Tuple[int, int, int]
        Shape of the test array
    """

    def _compute_num_parts(original_extent: int, max_extent: int) -> int:
        if original_extent < max_extent:
            return 1
        return (original_extent + max_extent - 1) // max_extent

    # Arrange
    data = (np.zeros(shape)).astype(np.uint8)
    width, length = data.shape[:2]
    channel = 1
    if len(data.shape) > 2:
        channel = data.shape[-1]
    if channel == 1:
        max_extent = 3100
    else:
        max_extent = 1800
    num_cols = _compute_num_parts(width, max_extent)
    num_rows = _compute_num_parts(length, max_extent)
    num_subblocks = num_cols * num_rows
    # Act
    with tempfile.TemporaryDirectory() as td:
        with create_czi(join(td, "./test.czi"), exist_ok=True) as test_czi:
            test_czi.write(data)
    # Assert
    assert _divide_image_patch.call_count == num_subblocks


def test_write_incontiguous() -> None:
    """Tests that incontiguous image data is written correctly to czi."""
    # Arrange
    input_path = join(dirname(working_dir), "test_data", "rgb-image.npy")  # Color channels first
    expected_path = join(dirname(working_dir), "test_data", "rgb-image.czi")
    data = np.load(input_path)
    data = np.moveaxis(data, 0, -1)
    with tempfile.TemporaryDirectory() as td:
        target_path = join(td, "test.czi")
        # Act
        with create_czi(target_path, exist_ok=True) as test_czi:
            test_czi.write(data)
        # Assert
        with open_czi(expected_path) as czi_document:
            expected = czi_document.read()
        with open_czi(target_path) as czi_document:
            actual = czi_document.read()

        np.testing.assert_array_equal(expected, actual)
