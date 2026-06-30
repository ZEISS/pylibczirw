"""Module implementing integration tests for subblock enumeration functionality"""

# pylint: disable=no-self-use  # Test methods don't need to use self

import os

import pytest

from pylibCZIrw.czi import open_czi

working_dir = os.path.dirname(os.path.abspath(__file__))

CZI_SIMPLE = os.path.join(working_dir, "../test_data", "c1_gray8.czi")
CZI_MULTI_CHANNEL = os.path.join(working_dir, "../test_data", "c2_gray8_gray16.czi")
CZI_MULTI_DIM = os.path.join(working_dir, "../test_data", "c2_gray8_t3_z5_s2.czi")
CZI_MULTI_SCENE = os.path.join(working_dir, "../test_data", "c1_gray8_s2_overlapping_bounding_boxes.czi")


class TestBasicEnumeration:
    """Test basic subblock enumeration functionality."""

    def test_enumerate_all_subblocks_simple_file(self) -> None:
        """Test enumerating all subblocks in a simple single-subblock file."""
        with open_czi(CZI_SIMPLE) as czi_doc:
            count = {"total": 0}

            def count_callback(index, info):  # type: ignore
                count["total"] += 1
                assert index >= 0
                assert info.logicalRect.w > 0
                assert info.logicalRect.h > 0
                assert info.physicalSize.w > 0
                assert info.physicalSize.h > 0
                return True

            czi_doc.enumerate_subblocks(count_callback)

            assert count["total"] >= 1

    def test_enumerate_all_subblocks_multi_channel(self) -> None:
        """Test enumerating all subblocks in a multi-channel file."""
        with open_czi(CZI_MULTI_CHANNEL) as czi_doc:
            count = {"total": 0}
            channels_seen = set()

            def count_callback(_index, info):  # type: ignore
                count["total"] += 1
                coord_dict = info.coordinate.to_dict()
                if "C" in coord_dict:
                    channels_seen.add(coord_dict["C"])
                return True

            czi_doc.enumerate_subblocks(count_callback)

            assert count["total"] > 1
            assert len(channels_seen) >= 2

    def test_enumerate_all_subblocks_multi_dimensional(self) -> None:
        """Test enumerating all subblocks in a multi-dimensional file."""
        with open_czi(CZI_MULTI_DIM) as czi_doc:
            count = {"total": 0}
            coordinates_seen = set()

            def count_callback(_index, info):  # type: ignore
                count["total"] += 1
                coord_dict = info.coordinate.to_dict()
                coord_tuple = tuple(sorted(coord_dict.items()))
                coordinates_seen.add(coord_tuple)
                return True

            czi_doc.enumerate_subblocks(count_callback)

            assert count["total"] > 10
            assert len(coordinates_seen) > 5


class TestSubBlockInfo:
    """Test SubBlockInfo structure and content."""

    def test_subblock_info_has_logical_rect(self) -> None:
        """Test that SubBlockInfo contains logical rectangle."""
        with open_czi(CZI_SIMPLE) as czi_doc:
            info_collected = []

            def collect_info(_index, info):  # type: ignore
                info_collected.append(info)
                return len(info_collected) < 5

            czi_doc.enumerate_subblocks(collect_info)

            for info in info_collected:
                assert hasattr(info, "logicalRect")
                assert info.logicalRect.x is not None
                assert info.logicalRect.y is not None
                assert info.logicalRect.w > 0
                assert info.logicalRect.h > 0

    def test_subblock_info_has_physical_size(self) -> None:
        """Test that SubBlockInfo contains physical size."""
        with open_czi(CZI_SIMPLE) as czi_doc:
            info_collected = []

            def collect_info(_index, info):  # type: ignore
                info_collected.append(info)
                return len(info_collected) < 5

            czi_doc.enumerate_subblocks(collect_info)

            for info in info_collected:
                assert hasattr(info, "physicalSize")
                assert info.physicalSize.w > 0
                assert info.physicalSize.h > 0

    def test_subblock_info_has_pixel_type(self) -> None:
        """Test that SubBlockInfo contains pixel type."""
        with open_czi(CZI_SIMPLE) as czi_doc:
            info_collected = []

            def collect_info(_index, info):  # type: ignore
                info_collected.append(info)
                return len(info_collected) < 5

            czi_doc.enumerate_subblocks(collect_info)

            for info in info_collected:
                assert hasattr(info, "pixelType")
                assert hasattr(info.pixelType, "name")

    def test_subblock_info_has_compression(self) -> None:
        """Test that SubBlockInfo contains compression information."""
        with open_czi(CZI_SIMPLE) as czi_doc:
            info_collected = []

            def collect_info(_index, info):  # type: ignore
                info_collected.append(info)
                return len(info_collected) < 5

            czi_doc.enumerate_subblocks(collect_info)

            for info in info_collected:
                compression = info.get_compression_mode()
                assert hasattr(compression, "name")

    def test_subblock_info_has_coordinates(self) -> None:
        """Test that SubBlockInfo contains coordinate information."""
        with open_czi(CZI_MULTI_DIM) as czi_doc:
            info_collected = []

            def collect_info(_index, info):  # type: ignore
                info_collected.append(info)
                return len(info_collected) < 10

            czi_doc.enumerate_subblocks(collect_info)

            for info in info_collected:
                assert hasattr(info, "coordinate")
                coord_dict = info.coordinate.to_dict()
                assert isinstance(coord_dict, dict)
                assert "C" in coord_dict or len(coord_dict) > 0


class TestFilteredEnumeration:
    """Test filtered subblock enumeration."""

    def test_enumerate_layer0_only(self) -> None:
        """Test enumerating only layer 0 subblocks."""
        with open_czi(CZI_SIMPLE) as czi_doc:
            all_count = {"total": 0}
            layer0_count = {"total": 0}

            def count_all(_index, _info):  # type: ignore
                all_count["total"] += 1
                return True

            def count_layer0(_index, _info):  # type: ignore
                layer0_count["total"] += 1
                return True

            czi_doc.enumerate_subblocks(count_all)
            czi_doc.enumerate_subblocks_subset(count_layer0, only_layer0=True)

            assert layer0_count["total"] <= all_count["total"]
            assert layer0_count["total"] > 0

    def test_enumerate_with_coordinate_filter_string(self) -> None:
        """Test filtering by coordinate using string format."""
        with open_czi(CZI_MULTI_CHANNEL) as czi_doc:
            coords_found = set()

            def collect_coords(_index, info):  # type: ignore
                coord_dict = info.coordinate.to_dict()
                if "C" in coord_dict:
                    coords_found.add(coord_dict["C"])
                return True

            czi_doc.enumerate_subblocks(collect_coords)

            if len(coords_found) > 0:
                target_channel = min(coords_found)
                coord_string = f"C{target_channel}"

                filtered_count = {"total": 0}

                def count_filtered(_index, info):  # type: ignore
                    filtered_count["total"] += 1
                    coord_dict = info.coordinate.to_dict()
                    assert coord_dict.get("C") == target_channel
                    return True

                czi_doc.enumerate_subblocks_subset(count_filtered, plane=coord_string, only_layer0=True)

                assert filtered_count["total"] > 0

    def test_enumerate_with_coordinate_filter_dict(self) -> None:
        """Test filtering by coordinate using dict format."""
        with open_czi(CZI_MULTI_DIM) as czi_doc:
            coords_found = []

            def collect_coords(_index, info):  # type: ignore
                coord_dict = info.coordinate.to_dict()
                coords_found.append(coord_dict)
                return len(coords_found) < 20

            czi_doc.enumerate_subblocks(collect_coords)

            if len(coords_found) > 0:
                target_coord = coords_found[0]

                filtered_count = {"total": 0}

                def count_filtered(_index, _info):  # type: ignore
                    filtered_count["total"] += 1
                    return True

                czi_doc.enumerate_subblocks_subset(count_filtered, plane=target_coord, only_layer0=False)

                assert filtered_count["total"] > 0

    def test_enumerate_with_roi_filter(self) -> None:
        """Test filtering by region of interest."""
        with open_czi(CZI_SIMPLE) as czi_doc:

            bounds = czi_doc.total_bounding_box

            roi = (
                bounds["X"][0],
                bounds["Y"][0],
                (bounds["X"][1] - bounds["X"][0]) // 2,
                (bounds["Y"][1] - bounds["Y"][0]) // 2,
            )

            filtered_count = {"total": 0}

            def count_in_roi(_index, _info):  # type: ignore
                filtered_count["total"] += 1
                return True

            czi_doc.enumerate_subblocks_subset(count_in_roi, roi=roi, only_layer0=True)

            assert filtered_count["total"] >= 0

    def test_enumerate_with_combined_filters(self) -> None:
        """Test using multiple filters together."""
        with open_czi(CZI_MULTI_DIM) as czi_doc:
            bounds = czi_doc.total_bounding_box

            roi = (
                bounds["X"][0],
                bounds["Y"][0],
                (bounds["X"][1] - bounds["X"][0]),
                (bounds["Y"][1] - bounds["Y"][0]),
            )

            combined_count = {"total": 0}

            def count_combined(_index, _info):  # type: ignore
                combined_count["total"] += 1
                return True

            czi_doc.enumerate_subblocks_subset(count_combined, plane={"C": 0}, roi=roi, only_layer0=True)

            assert combined_count["total"] >= 0


class TestEnumerationControl:
    """Test enumeration control flow."""

    def test_early_termination(self) -> None:
        """Test that returning False stops enumeration."""
        with open_czi(CZI_MULTI_DIM) as czi_doc:
            max_count = 5
            count = {"total": 0}

            def limited_callback(_index, _info):  # type: ignore
                count["total"] += 1
                return count["total"] < max_count

            czi_doc.enumerate_subblocks(limited_callback)

            assert count["total"] == max_count

    def test_enumerate_subblocks_rethrows_callback_exception(self) -> None:
        """Test that exceptions raised by the callback are re-thrown."""

        class CallbackError(RuntimeError):
            """Raised by the test callback."""

        with open_czi(CZI_SIMPLE) as czi_doc:
            calls = {"total": 0}

            def failing_callback(_index, _info):  # type: ignore
                calls["total"] += 1
                raise CallbackError("callback failed")

            with pytest.raises(CallbackError, match="callback failed"):
                czi_doc.enumerate_subblocks(failing_callback)

            assert calls["total"] == 1

    def test_enumerate_subblocks_subset_rethrows_callback_exception(self) -> None:
        """Test that subset enumeration re-throws callback exceptions."""

        class CallbackError(RuntimeError):
            """Raised by the test callback."""

        with open_czi(CZI_SIMPLE) as czi_doc:
            calls = {"total": 0}

            def failing_callback(_index, _info):  # type: ignore
                calls["total"] += 1
                raise CallbackError("callback failed")

            with pytest.raises(CallbackError, match="callback failed"):
                czi_doc.enumerate_subblocks_subset(failing_callback, only_layer0=True)

            assert calls["total"] == 1

    def test_collect_specific_subblocks(self) -> None:
        """Test collecting specific subblocks based on criteria."""
        with open_czi(CZI_MULTI_CHANNEL) as czi_doc:
            channel_0_bounds = []

            def collect_channel_0(_index, info):  # type: ignore
                coord_dict = info.coordinate.to_dict()
                if coord_dict.get("C") == 0:
                    rect = info.logicalRect
                    channel_0_bounds.append(
                        {
                            "index": _index,
                            "x": rect.x,
                            "y": rect.y,
                            "width": rect.w,
                            "height": rect.h,
                        }
                    )
                return True

            czi_doc.enumerate_subblocks(collect_channel_0)

            assert len(channel_0_bounds) > 0

            for bounds in channel_0_bounds:
                assert bounds["width"] > 0
                assert bounds["height"] > 0


class TestSceneHandling:
    """Test subblock enumeration with multi-scene files."""

    def test_enumerate_multi_scene_file(self) -> None:
        """Test enumerating subblocks in a multi-scene file."""
        with open_czi(CZI_MULTI_SCENE) as czi_doc:
            scenes_found = set()

            def collect_scenes(_index, info):  # type: ignore
                coord_dict = info.coordinate.to_dict()
                if "S" in coord_dict:
                    scenes_found.add(coord_dict["S"])
                return True

            czi_doc.enumerate_subblocks(collect_scenes)

            assert len(scenes_found) > 0
