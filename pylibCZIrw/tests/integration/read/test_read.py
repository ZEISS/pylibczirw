"""Module implementing integration tests for the read function of the CziReader class"""

import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytest
from pylibCZIrw.czi import CacheOptions, CacheType, ReaderFileInputTypes, open_czi

working_dir = os.path.dirname(os.path.abspath(__file__))

CZI_DOCUMENT_TEST1 = os.path.join(working_dir, "../test_data", "c1_bgr24.czi")
EXPECTED_PLANE_TEST1 = np.load(os.path.join(working_dir, "../test_data", "c1_bgr24_plane.npz"))["arr"]

CZI_DOCUMENT_TEST2 = os.path.join(working_dir, "../test_data", "c1_bgr48.czi")
EXPECTED_PLANE_TEST2 = np.load(os.path.join(working_dir, "../test_data", "c1_bgr48_plane.npz"))["arr"]

CZI_DOCUMENT_TEST3 = os.path.join(working_dir, "../test_data", "c1_gray8.czi")
EXPECTED_PLANE_TEST3 = np.load(os.path.join(working_dir, "../test_data", "c1_gray8_plane.npz"))["arr"]
EXPECTED_PLANE_ZOOM07_TEST3 = np.load(os.path.join(working_dir, "../test_data", "c1_gray8_plane_zoom07.npz"))["arr"]

CZI_DOCUMENT_TEST4 = os.path.join(working_dir, "../test_data", "c1_gray8_s2_non_overlapping_bounding_boxes.czi")
EXPECTED_PLANE_S0_ZOOM05_TEST4 = np.load(
    os.path.join(
        working_dir,
        "../test_data",
        "c1_gray8_s2_non_overlapping_bounding_boxes_plane_s0_zoom05.npz",
    )
)["arr"]
EXPECTED_PLANE_S1_TEST4 = np.load(
    os.path.join(
        working_dir,
        "../test_data",
        "c1_gray8_s2_non_overlapping_bounding_boxes_plane_s1.npz",
    )
)["arr"]

CZI_DOCUMENT_TEST5 = os.path.join(working_dir, "../test_data", "c1_gray8_s2_overlapping_bounding_boxes.czi")
EXPECTED_PLANE_TEST5 = np.load(
    os.path.join(working_dir, "../test_data", "c1_gray8_s2_overlapping_bounding_boxes_plane.npz")
)["arr"]

CZI_DOCUMENT_TEST6 = os.path.join(working_dir, "../test_data", "c1_gray16.czi")
EXPECTED_PLANE_Gray8_TEST6 = np.load(os.path.join(working_dir, "../test_data", "c1_gray16_plane_Gray8.npz"))["arr"]

CZI_DOCUMENT_TEST7 = os.path.join(working_dir, "../test_data", "c2_gray8_gray16.czi")
EXPECTED_PLANE_C0_ZOOM05_Gray16_TEST7 = np.load(
    os.path.join(working_dir, "../test_data", "c2_gray8_gray16_plane_c0_zoom05_Gray16.npz")
)["arr"]
EXPECTED_PLANE_C1_TEST7 = np.load(os.path.join(working_dir, "../test_data", "c2_gray8_gray16_plane_c1.npz"))["arr"]

CZI_DOCUMENT_TEST8 = os.path.join(working_dir, "../test_data", "c2_gray8_t3_z5_s2.czi")
EXPECTED_PLANE_C0_Z3_T2_TEST8 = np.load(
    os.path.join(working_dir, "../test_data", "c2_gray8_t3_z5_s2_plane_c0_z3_t2.npz")
)["arr"]
EXPECTED_PLANE_S1_C0_Z4_T1_TEST8 = np.load(
    os.path.join(working_dir, "../test_data", "c2_gray8_t3_z5_s2_plane_s1_c0_z4_t1.npz")
)["arr"]
# Note: This file is not part of the repo and so is untracked. If tests fail, make sure that this have not been deleted.
CZI_DOCUMENT_TEST9 = ("https://cadevelop.blob.core.windows.net/public/pylibCZIrwTestFiles/c1_bgr24.czi")
EXPECTED_PLANE_TEST9 = np.load(os.path.join(working_dir, "../test_data", "c1_bgr24_plane.npz"))["arr"]


@pytest.mark.parametrize(
    "czi_path, plane, scene, zoom, roi, pixel_type, reader_type, cache_options, "
    "expected_cache_elements_count, expected_result",
    [
        (
            CZI_DOCUMENT_TEST1,
            None,
            None,
            1.0,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_TEST1,
        ),
        (
            CZI_DOCUMENT_TEST1,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_TEST1[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST2,
            None,
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_TEST2,
        ),
        (
            CZI_DOCUMENT_TEST2,
            None,
            None,
            None,
            (50, 20, 10, 10),
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_TEST2[
                20:30,
                50:60,
            ],
        ),
        (
            CZI_DOCUMENT_TEST3,
            None,
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_TEST3,
        ),
        (
            CZI_DOCUMENT_TEST3,
            None,
            None,
            0.7,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_ZOOM07_TEST3,
        ),
        (
            CZI_DOCUMENT_TEST4,
            None,
            0,
            0.5,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_S0_ZOOM05_TEST4,
        ),
        (
            CZI_DOCUMENT_TEST4,
            None,
            0,
            0.5,
            (0, 0, 50, 50),
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_S0_ZOOM05_TEST4[
                0:25,
                0:25,
            ],
        ),
        (
            CZI_DOCUMENT_TEST4,
            None,
            1,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_S1_TEST4,
        ),
        (
            CZI_DOCUMENT_TEST5,
            None,
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_TEST5,
        ),
        (
            CZI_DOCUMENT_TEST6,
            None,
            None,
            None,
            None,
            "Gray8",
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_Gray8_TEST6,
        ),
        (
            CZI_DOCUMENT_TEST6,
            None,
            None,
            None,
            (10, 50, 25, 63),
            "Gray8",
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_Gray8_TEST6[
                50:113,
                10:35,
            ],
        ),
        (
            CZI_DOCUMENT_TEST7,
            {"C": 0},
            None,
            0.5,
            None,
            "Gray16",
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_C0_ZOOM05_Gray16_TEST7,
        ),
        (
            CZI_DOCUMENT_TEST7,
            {"C": 1, "Z": 0},
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_C1_TEST7,
        ),
        (
            CZI_DOCUMENT_TEST7,
            {"C": 1},
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_C1_TEST7,
        ),
        (
            CZI_DOCUMENT_TEST8,
            {"Z": 3, "T": 2},
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_C0_Z3_T2_TEST8,
        ),
        (
            CZI_DOCUMENT_TEST8,
            {"Z": 4, "T": 1},
            1,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_S1_C0_Z4_T1_TEST8,
        ),
        (
            CZI_DOCUMENT_TEST8,
            {"Z": 4, "T": 1, "C": 0},
            1,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_S1_C0_Z4_T1_TEST8,
        ),
        (
            CZI_DOCUMENT_TEST7,
            {"C": 1, "Z": 0},
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            None,
            None,
            EXPECTED_PLANE_C1_TEST7,
        ),
        (
            CZI_DOCUMENT_TEST7,
            {"C": 1, "Z": 0},
            None,
            None,
            None,
            None,
            ReaderFileInputTypes.Standard,
            CacheOptions(CacheType.Standard, None, None),
            0,
            EXPECTED_PLANE_C1_TEST7,
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            1.0,
            None,
            None,
            ReaderFileInputTypes.Curl,
            None,
            None,
            EXPECTED_PLANE_TEST9,
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            None,
            None,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            1.0,
            None,
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, None, None),
            1,
            EXPECTED_PLANE_TEST9,
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, None, None),
            1,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, None, 0),
            0,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, 0, None),
            0,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, 0, 2),
            0,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, 1000000000, 0),
            0,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
        (
            CZI_DOCUMENT_TEST9,
            None,
            None,
            None,
            (0, 0, 100, 100),
            None,
            ReaderFileInputTypes.Curl,
            CacheOptions(CacheType.Standard, 1000000000, 2),
            1,
            EXPECTED_PLANE_TEST9[
                0:100,
                0:100,
            ],
        ),
    ],
)
def test_read(
    czi_path: str,
    plane: Dict[str, int],
    scene: int,
    zoom: float,
    roi: Tuple[int, int, int, int],
    pixel_type: str,
    reader_type: ReaderFileInputTypes,
    cache_options: Optional[CacheOptions],
    expected_cache_elements_count: Optional[int],
    expected_result: np.ndarray,
) -> None:
    """Integration tests for the read function"""
    with open_czi(czi_path, reader_type, cache_options=cache_options) as czi_document:
        plane_array = czi_document.read(
            plane=plane,
            scene=scene,
            roi=roi,
            zoom=zoom,
            pixel_type=pixel_type,
        )
        np.testing.assert_array_equal(plane_array, expected_result)
    if expected_cache_elements_count is not None:
        assert (czi_document.get_cache_info().elements_count == expected_cache_elements_count)


@pytest.mark.parametrize(
    "czi_path, plane, scene, zoom, rois, pixel_type, expected",
    [
        (
            CZI_DOCUMENT_TEST1,
            None,
            None,
            1.0,
            [None] * 3,
            None,
            [EXPECTED_PLANE_TEST1] * 3,
        ),
        (
            CZI_DOCUMENT_TEST1,
            None,
            None,
            None,
            [
                (0, 0, 100, 100),
                (0, 0, 200, 200),
                (100, 100, 100, 100),
                (100, 100, 200, 200),
            ],
            None,
            [
                EXPECTED_PLANE_TEST1[:100, :100],
                EXPECTED_PLANE_TEST1[:200, :200],
                EXPECTED_PLANE_TEST1[100:200, 100:200],
                EXPECTED_PLANE_TEST1[100:300, 100:300],
            ],
        ),
    ],
)
def test_read_concurrently(
    czi_path: str,
    plane: Dict[str, int],
    scene: int,
    zoom: float,
    rois: List[Tuple[int, int, int, int]],
    pixel_type: str,
    expected: List[np.ndarray],
) -> None:
    """Integration tests for concurrently using the read function concurrently"""
    with open_czi(czi_path) as czi_document:
        with ThreadPoolExecutor() as executor:
            plane_arrays = list(
                executor.map(
                    partial(
                        czi_document.read,
                        plane=plane,
                        scene=scene,
                        zoom=zoom,
                        pixel_type=pixel_type,
                    ),
                    rois,
                )
            )

        for curr_plane_array, curr_expected in zip(plane_arrays, expected):
            np.testing.assert_array_equal(curr_plane_array, curr_expected)


CZI_DOCUMENT_TEST_ERROR1 = os.path.join(working_dir, "../test_data", "c1_bgr96float.czi")

CZI_DOCUMENT_TEST_ERROR2 = os.path.join(working_dir, "../test_data", "c1_gray32float.czi")


def test_read_raises_error_on_Bgr96Float() -> None:
    """Integration tests for the read function error message on Bgr96Float Data"""
    expected_error_message = r"Sorry, this pixeltype isn't implemented yet."
    with pytest.raises(RuntimeError, match=expected_error_message):
        with open_czi(CZI_DOCUMENT_TEST_ERROR1) as czi_document:
            czi_document.read()


@pytest.mark.skip(reason="gray32float is now handled. Test needs update")
def test_read_raises_error_on_Gray32Float() -> None:
    """Integration tests for the read function error message on Gray32Float Data"""
    expected_error_message = (
        r"Operation not implemented for source pixeltype='gray32float' and destination pixeltype='gray32float'."
    )
    with pytest.raises(RuntimeError, match=expected_error_message):
        with open_czi(CZI_DOCUMENT_TEST_ERROR2) as czi_document:
            czi_document.read()
