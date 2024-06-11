"""Module implementing unit tests for the CziWriter class"""

import re
import tempfile
from os.path import join
from typing import Dict, Optional
from unittest import mock
from unittest.mock import call, patch

import _pylibCZIrw
import numpy as np
import pytest
from pylibCZIrw.czi import CziReader, CziWriter, create_czi

# testing static functions


@pytest.mark.parametrize(
    "plane, expected",
    [
        ({"C": 0, "T": 0, "Z": 8}, "C0 T0 Z8"),
        ({"Z": 100, "T": 8}, "Z100 T8"),
        ({"C": 0, "T": 0, "Z": 8}, "C0 T0 Z8"),
        ({"C": 0}, "C0"),
    ],
)
def test_format_plane(plane: Dict[str, int], expected: str) -> None:
    """Unit tests for format_plane function"""
    formatted_plane = CziWriter._format_plane(plane)
    assert formatted_plane == expected


@pytest.mark.parametrize(
    "plane, scene, expected",
    [
        ({"C": 0, "T": 0, "Z": 8}, 0, {"T": 0, "Z": 8, "C": 0, "S": 0}),
        ({"R": 0, "Z": 100, "T": 8}, 3, {"T": 8, "Z": 100, "C": 0, "S": 3}),
        (
            {"C": 0, "T": 0, "Z": 8, "H": 200, "B": 3, "R": -1},
            5,
            {"T": 0, "Z": 8, "C": 0, "S": 5},
        ),
    ],
)
def test_create_plane(plane: Dict[str, int], scene: int, expected: Dict[str, int]) -> None:
    """Unit tests for create_plane function"""
    created_plane = CziWriter._create_plane(plane, scene)
    assert created_plane == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            np.array(
                [
                    [0, 18, 20, 20, 18, 50],
                    [15, 24, 25, 251, 45, 12],
                    [200, 10, 56, 20, 145, 14],
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
def test_format_gray_data(data: np.ndarray, expected: np.ndarray) -> None:
    """Unit tests for format_gray_data function"""
    formatted_data = CziWriter._format_gray_data(data)
    np.testing.assert_array_equal(formatted_data, expected)


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            np.array(
                [
                    [[0], [18], [20], [20], [18], [50]],
                    [[15], [24], [25], [251], [45], [12]],
                    [[200], [10], [56], [20], [145], [14]],
                ]
            ),
            False,
        ),
        (
            np.array(
                [
                    [0, 18, 20, 20, 18, 50],
                    [15, 24, 25, 251, 45, 12],
                    [200, 10, 56, 20, 145, 14],
                ]
            ),
            False,
        ),
        (
            np.array(
                [
                    [[0, 18, 20], [20, 18, 50]],
                    [[15, 24, 25], [251, 45, 12]],
                    [[200, 10, 56], [20, 145, 14]],
                ]
            ),
            True,
        ),
    ],
)
def test_is_rgb(data: np.ndarray, expected: bool) -> None:
    """Unit tests for _is_rgb function"""
    is_rgb = CziWriter._is_rgb(data)
    assert expected == is_rgb


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            np.array(
                [
                    [[0], [18], [20], [20], [18], [50]],
                    [[15], [24], [25], [251], [45], [12]],
                    [[200], [10], [56], [20], [145], [14]],
                ]
            ),
            True,
        ),
        (
            np.array(
                [
                    [[0, 18, 20], [20, 18, 50]],
                    [[15, 24, 25], [251, 45, 12]],
                    [[200, 10, 56], [20, 145, 14]],
                ]
            ),
            False,
        ),
        (
            np.array(
                [
                    [0, 18, 20, 20, 18, 50],
                    [15, 24, 25, 251, 45, 12],
                    [200, 10, 56, 20, 145, 14],
                ]
            ),
            True,
        ),
    ],
)
def test_is_gray(data: np.ndarray, expected: bool) -> None:
    """Unit tests for _is_rgb function"""
    is_gray = CziWriter._is_gray(data)
    assert expected == is_gray


def test_shape_input() -> None:
    """Unit tests for checking the shape of the input pixel_data for rgb"""
    data: np.ndarray = np.array(
        [
            [0, 18, 20, 20, 18, 50],
            [15, 24, 25, 251, 45, 12],
            [200, 10, 56, 20, 145, 14],
        ],
        dtype="uint8",
    )
    with pytest.raises(
        ValueError,
        match=re.escape("The data provided should have a shape of at least length 3 (e.g. (m,n,3) or (m,n,1))"),
    ):
        _ = CziWriter._get_channel_dim(data)


# Testing Class method


@pytest.mark.parametrize(
    "data",
    [
        np.array(
            [
                [[0], [18], [20], [20], [18], [50]],
                [[15], [24], [25], [251], [45], [12]],
                [[200], [10], [56], [20], [145], [14]],
            ],
            dtype="uint8",
        ),
        np.array(
            [[0, 18, 20, 21, 18, 34], [15, 24, 25, 22, 11, 90]],
            dtype="uint8",
        ),
    ],
)
def test_format_data_gray(data: np.ndarray) -> None:
    """Unit tests for format_data function with gray array"""
    expected = _pylibCZIrw.PImage(data.reshape((data.shape[0], data.shape[1], 1)), _pylibCZIrw.PixelType.Gray8)
    data_libczi = CziWriter._format_data(data)
    np.testing.assert_array_equal(np.array(data_libczi), np.array(expected))


def test_format_data_rgb() -> None:
    """Unit tests for format_data function with rgb array"""
    data: np.ndarray = np.array(
        [
            [[0, 18, 20], [20, 18, 50]],
            [[15, 24, 25], [251, 45, 12]],
            [[200, 10, 56], [20, 145, 14]],
        ],
        dtype="uint8",
    )
    expected = _pylibCZIrw.PImage(
        data.reshape((data.shape[0], data.shape[1], data.shape[2])),
        _pylibCZIrw.PixelType.Bgr24,
    )
    data_libczi = CziWriter._format_data(data)
    np.testing.assert_array_equal(np.array(data_libczi), np.array(expected))


def test_channel_dimension() -> None:
    """Unit tests for checking the channel dimension of the input pixel_data"""
    data: np.ndarray = np.array(
        [
            [[0, 18, 20, 21], [20, 18, 50, 21]],
            [[15, 24, 25, 21], [251, 45, 12, 21]],
            [[200, 10, 56, 21], [20, 145, 14, 21]],
        ],
        dtype="uint8",
    )
    with pytest.raises(ValueError, match="Incorrect Channel dimension!"):
        _ = _pylibCZIrw.PImage(
            data.reshape((data.shape[0], data.shape[1], data.shape[2])),
            _pylibCZIrw.PixelType.Bgr24,
        )
        _ = CziWriter._format_data(data)


@mock.patch("pylibCZIrw.czi.CziWriter.write_metadata")
def test_metadata_written_on_close(write_metadata_mock: mock.Mock) -> None:
    """Tests that metadata is not overwritten when closing the file."""
    with tempfile.TemporaryDirectory() as td:
        writer = CziWriter(join(td, "test"))
        writer._metadata_writen = True
        writer.close()

    write_metadata_mock.assert_not_called()


@mock.patch("pylibCZIrw.czi.CziWriter.write_metadata")
def test_metadata_not_written_if_already_written(
    write_metadata_mock: mock.Mock,
) -> None:
    """Tests that metadata is written when closing the file, if no metadata was yet written."""
    with tempfile.TemporaryDirectory() as td:
        writer = CziWriter(join(td, "test"))
        writer.close()

    write_metadata_mock.assert_called_once()


@mock.patch("pylibCZIrw.czi._pylibCZIrw.czi_writer")
def test_czi_writer_splits_to_correct_locations(czi_writer_mock: mock.Mock) -> None:
    """Tests that split sub-images are written to the correct location."""
    mock_writer = mock.MagicMock()
    mock_writer.AddTile = mock.MagicMock(return_value=True)
    czi_writer_mock.return_value = mock_writer
    writer = CziWriter("Some Path")
    writer.write(np.ones((2048, 2048, 3), dtype=np.uint8), location=(200, 400))
    writer.close()

    expected_calls = [
        mock.call(mock.ANY, mock.ANY, 200, 400, mock.ANY, mock.ANY),
        mock.call(mock.ANY, mock.ANY, 1224, 400, mock.ANY, mock.ANY),
        mock.call(mock.ANY, mock.ANY, 200, 1424, mock.ANY, mock.ANY),
        mock.call(mock.ANY, mock.ANY, 1224, 1424, mock.ANY, mock.ANY),
    ]
    mock_writer.AddTile.assert_has_calls(expected_calls)


@pytest.mark.parametrize(
    "compression_options",
    [
        "uncompressed:",
        "zstd0:",
        "zstd1:",
        "zstd0:ExplicitLevel=2",
        "zstd1:ExplicitLevel=0",
    ],
)
def test_write_czi_check_file_compression_none(compression_options: str) -> None:
    """Write a subblock to a newly created CZI-file, read the CZI-file and compare the pixeldata - while
    using different compression_options when creating the writer-object.
    """
    data: np.ndarray = np.array(
        [
            [[0, 18, 20], [20, 18, 50]],
            [[15, 24, 25], [251, 45, 12]],
            [[200, 10, 56], [20, 145, 14]],
        ],
        dtype="uint8",
    )

    with tempfile.TemporaryDirectory() as td:
        czi_filename = join(td, "test")
        writer = CziWriter(czi_filename, compression_options)
        writer.write(data, (0, 0), {"C": 0, "T": 0, "Z": 0}, None, 0)
        writer.write_metadata()
        writer.close()

        test_czi = CziReader(czi_filename)
        bounding_box = test_czi.total_bounding_box
        pixeldata = test_czi.read((0, 0, 2, 3), {"C": 0, "T": 0, "Z": 0}, None, 1, None)
        test_czi.close()
        np.testing.assert_array_equal(pixeldata, data)
        assert bounding_box["X"] == (0, 2) and bounding_box["Y"] == (0, 3)
        assert bounding_box["C"] == (0, 1) and bounding_box["T"] == (0, 1) and bounding_box["Z"] == (0, 1)


def test_write_czi_check_file_compression_invalid() -> None:
    """Testing if the invalid name of commpression is handled properly"""
    data: np.ndarray = np.array(
        [
            [[0, 18, 20], [20, 18, 50]],
            [[15, 24, 25], [251, 45, 12]],
            [[200, 10, 56], [20, 145, 14]],
        ],
        dtype="uint8",
    )

    with pytest.raises(RuntimeError, match="The specified string could not be processed."):
        with tempfile.TemporaryDirectory() as td:
            czi_filename = join(td, "test")
            writer = CziWriter(czi_filename, "hello")
            writer.write(data, (0, 0), {"C": 0, "T": 0, "Z": 0}, "hello", 0)


@pytest.mark.parametrize(
    "compression_options",
    [
        "uncompressed:",
        "zstd0:",
        "zstd1:",
        "zstd0:ExplicitLevel=-100",
        "zstd1:ExplicitLevel=0",
    ],
)
def test_write_czi_with_write_specific_compressionoptions_check_file(
    compression_options: str,
) -> None:
    """Write a subblock to a newly created CZI-file, read the CZI-file and compare the pixeldata - while
    using different compression_options with the write-call.
    """
    data: np.ndarray = np.array(
        [
            [[0, 18, 20], [20, 18, 50]],
            [[15, 24, 25], [251, 45, 12]],
            [[200, 10, 56], [20, 145, 14]],
        ],
        dtype="uint8",
    )

    with tempfile.TemporaryDirectory() as td:
        czi_filename = join(td, "test")
        writer = CziWriter(czi_filename)
        writer.write(data, (0, 0), {"C": 0, "T": 0, "Z": 0}, compression_options, 0)
        writer.write_metadata()
        writer.close()

        test_czi = CziReader(czi_filename)
        bounding_box = test_czi.total_bounding_box
        pixeldata = test_czi.read((0, 0, 2, 3), {"C": 0, "T": 0, "Z": 0}, None, 1, None)
        test_czi.close()
        np.testing.assert_array_equal(pixeldata, data)
        assert bounding_box["X"] == (0, 2) and bounding_box["Y"] == (0, 3)
        assert bounding_box["C"] == (0, 1) and bounding_box["T"] == (0, 1) and bounding_box["Z"] == (0, 1)


@pytest.mark.parametrize(
    "compression_options_global, compression_options_overwrite ",
    [(None, "zstd0:ExplicitLevel=-1"), (None, "zstd1:ExplicitLevel=0")],
)
@patch("pylibCZIrw.czi.CziWriter.write")
def test_overwrite_compression(
    write_mock: mock.Mock,
    compression_options_global: Optional[str],
    compression_options_overwrite: Optional[str],
) -> None:
    """Write a subblock to a newly created CZI-file, while overwriting the compression_option in write function.
    Check if the compression_options are overwritten successfully.
    """
    data: np.ndarray = np.array(
        [
            [[0, 18, 20], [20, 18, 50]],
            [[15, 24, 25], [251, 45, 12]],
            [[200, 10, 56], [20, 145, 14]],
        ],
        dtype="uint8",
    )
    calls = [call(data, (0, 0), {"C": 0, "T": 0, "Z": 0}, compression_options_overwrite, 0)]

    with tempfile.TemporaryDirectory() as td:
        with create_czi(
            filepath=join(td, "test.czi"),
            compression_options=compression_options_global,
        ) as test_czi:
            test_czi.write(data, (0, 0), {"C": 0, "T": 0, "Z": 0}, compression_options_overwrite, 0)
            test_czi.write_metadata()

    write_mock.assert_has_calls(calls=calls, any_order=False)
