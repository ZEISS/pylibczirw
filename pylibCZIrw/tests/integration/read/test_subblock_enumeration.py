"""Module implementing integration tests for subblock enumeration functionality"""

# pylint: disable=no-self-use  # Test methods don't need to use self

import os
import struct
from dataclasses import FrozenInstanceError, fields
from types import SimpleNamespace

import numpy as np
import pytest

import _pylibCZIrw as native
from pylibCZIrw.czi import CziReader, ReaderOptions, StoredLevelInfo, SubblockInfo, create_czi, open_czi

working_dir = os.path.dirname(os.path.abspath(__file__))

CZI_SIMPLE = os.path.join(working_dir, "../test_data", "c1_gray8.czi")
CZI_MULTI_CHANNEL = os.path.join(working_dir, "../test_data", "c2_gray8_gray16.czi")
CZI_MULTI_DIM = os.path.join(working_dir, "../test_data", "c2_gray8_t3_z5_s2.czi")
CZI_MULTI_SCENE = os.path.join(working_dir, "../test_data", "c1_gray8_s2_overlapping_bounding_boxes.czi")


class TestIndexedNativeAccess:
    """Test native indexed access independently of composed-plane reads."""

    def test_directory_snapshot_uses_no_stream_reads(self) -> None:
        with open(os.path.join(working_dir, "../test_data/synthetic/stored_sparse_coordinates.czi"), "rb") as source:
            data = source.read()
        reads = []

        def read_at(offset: int, size: int) -> bytes:
            reads.append((offset, size))
            return data[offset : offset + size]

        reader = native.czi_reader._from_stream(read_at)
        try:
            reads.clear()
            directory = reader.GetSubBlockDirectory()
            assert [index for index, _info in directory] == [0, 1]
            assert reader.GetSubBlockInfo(1).mIndex == 37
            assert reads == []
        finally:
            reader.close()
        assert directory[0][1].coordinate.to_dict() == {"S": 2, "T": 3, "C": 5, "Z": 7}

    @staticmethod
    def stream_data(filename="stored_sparse_coordinates.czi"):
        with open(os.path.join(working_dir, "../test_data/synthetic", filename), "rb") as source:
            return bytearray(source.read())

    @staticmethod
    def directory_entry(data, index=0):
        directory = struct.unpack_from("<q", data, 84)[0]
        assert data[directory : directory + 16].startswith(b"ZISRAWDIRECTORY")
        entry = directory + 32 + 128
        for _entry_index in range(index):
            entry += 32 + 20 * struct.unpack_from("<i", data, entry + 28)[0]
        assert data[entry : entry + 2] == b"DV"
        return entry

    @pytest.mark.parametrize(
        "filename",
        [
            "stored_sparse_coordinates.czi",
            "stored_levels_same_m37.czi",
            "stored_levels_negative_m7.czi",
            "stored_levels_irregular.czi",
            "literal_gray16_unsupported42_v2.czi",
            "literal_gray16_invalid_utf8.czi",
        ],
    )
    def test_public_snapshot_and_filters_are_stream_free(self, filename):
        data = self.stream_data(filename)
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        native_reader = native.czi_reader._from_stream(read_at)
        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native_reader
        try:
            reads.clear()
            infos = reader.list_subblocks()
            assert infos
            assert reader.count_subblocks() == len(infos)
            assert sum(reader.count_subblocks_by_scene().values()) == len(infos)
            for info in infos:
                plane = {key: value for key, value in info.coordinates.items() if key != "S"}
                filters = dict(plane=plane, scene=info.coordinates.get("S"), m_index=info.m_index, level=info.level_id)
                selected = reader.list_subblocks(**filters)
                assert info in selected
                assert reader.count_subblocks(**filters) == len(selected)
                assert sum(reader.count_subblocks_by_scene(**filters).values()) == len(selected)
            assert reader.list_subblocks(level=2**100) == []
            assert reads == []
        finally:
            reader.close()
        assert infos[0].stored_shape[0] > 0

    def test_selection_reads_only_chosen_stored_segment(self):
        data = self.stream_data()
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            reads.clear()
            infos = reader.list_subblocks(m_index=37)
            assert len(infos) == 2
            selected = reader.list_subblocks(scene=8, plane={"T": 9, "C": 11, "Z": 13}, level=infos[1].level_id)
            assert [info.index for info in selected] == [1]
            assert reads == []
            pixels = np.asarray(reader._czi_reader.ReadSubBlock(selected[0].index))
            entry = self.directory_entry(data, selected[0].index)
            start = struct.unpack_from("<q", data, entry + 6)[0]
            end = start + 32 + struct.unpack_from("<q", data, start + 16)[0]
            assert reads
            assert all(start <= offset and offset + size <= end for offset, size in reads)
            expected = (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
            np.testing.assert_array_equal(pixels[..., 0], expected)
        finally:
            reader.close()

    @pytest.mark.parametrize("failure", ["io", "truncated", "codec"])
    def test_payload_failures_are_typed_and_chained(self, failure):
        data = self.stream_data("literal_gray16_zstd0.czi")
        injected = OSError("injected stream failure")
        state = {"fail": False}

        def read_at(offset, size):
            if state["fail"]:
                raise injected
            return bytes(data[offset : offset + size])

        reader = native.czi_reader._from_stream(read_at)
        try:
            if failure == "io":
                state["fail"] = True
            elif failure == "truncated":
                data.clear()
            else:
                offset = data.index(b"\x28\xb5\x2f\xfd")
                data[offset : offset + 4] = b"\0\0\0\0"
            with pytest.raises(OSError if failure == "io" else ValueError) as caught:
                reader.ReadSubBlock(0)
            assert caught.value.__cause__ is not None
            if failure == "io":
                assert caught.value.__cause__ is injected
        finally:
            reader.close()

    @pytest.mark.parametrize(
        "change,error",
        [
            ("row_overflow", OverflowError),
            ("decoded_overflow", OverflowError),
            ("zero_size", ValueError),
            ("layout", ValueError),
            ("compression", ValueError),
        ],
    )
    def test_directory_validation_rejects_before_payload_or_allocation(self, change, error):
        data = self.stream_data("literal_gray16_raw.czi")
        entry = self.directory_entry(data)
        if change == "layout":
            struct.pack_into("<i", data, entry + 2, int(native.PixelType.Gray32))
        elif change == "compression":
            struct.pack_into("<i", data, entry + 18, 42)
        else:
            for dimension in range(struct.unpack_from("<i", data, entry + 28)[0]):
                offset = entry + 32 + 20 * dimension
                name = bytes(data[offset : offset + 4]).rstrip(b"\0")
                if name == b"X":
                    struct.pack_into("<i", data, offset + 16, 0 if change == "zero_size" else 2**31 - 1)
                if name == b"Y" and change == "decoded_overflow":
                    struct.pack_into("<i", data, offset + 16, 2**31 - 1)
            if change == "decoded_overflow":
                struct.pack_into("<i", data, entry + 2, int(native.PixelType.Bgr96Float))
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = native.czi_reader._from_stream(read_at)
        try:
            reads.clear()
            with pytest.raises(error):
                reader.ReadSubBlock(0)
            assert reads == []
        finally:
            reader.close()

    @pytest.fixture
    def indexed_reader(self):
        reader = native.czi_reader(os.path.join(working_dir, "../test_data/synthetic/stored_sparse_coordinates.czi"))
        try:
            yield reader
        finally:
            reader.close()

    def test_directory_descriptor_preserves_sparse_coordinates(self) -> None:
        reader = native.czi_reader(os.path.join(working_dir, "../test_data/synthetic/stored_sparse_coordinates.czi"))
        try:
            info = reader.GetSubBlockInfo(0)
            assert info.coordinate.to_dict() == {"S": 2, "T": 3, "C": 5, "Z": 7}
            assert info.mIndex == 37
            assert (info.logicalRect.x, info.logicalRect.y) == (-8, -4)
            assert (info.physicalSize.h, info.physicalSize.w) == (32, 48)
        finally:
            reader.close()
        assert info.coordinate.to_dict() == {"S": 2, "T": 3, "C": 5, "Z": 7}

    @pytest.mark.parametrize(
        "filename",
        ["literal_gray16_raw.czi", "literal_gray16_zstd0.czi", "literal_gray16_zstd1.czi", "literal_gray16_jpegxr.czi"],
    )
    def test_indexed_bitmap_owns_literal_pixels_after_close(self, filename: str) -> None:
        reader = native.czi_reader(os.path.join(working_dir, "../test_data/synthetic", filename))
        try:
            pixels = np.asarray(reader.ReadSubBlock(0))
        finally:
            reader.close()
        del reader
        expected = (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)
        assert pixels.dtype == np.dtype("uint16")
        assert pixels.shape == (32, 48, 1)
        np.testing.assert_array_equal(pixels[..., 0], expected)

    @pytest.mark.parametrize(
        "dtype,components",
        [
            ("uint8", 1),
            ("uint16", 1),
            ("float32", 1),
            ("uint8", 3),
            ("uint16", 3),
            ("float32", 3),
        ],
    )
    def test_all_supported_layouts_have_owned_native_dtype(self, tmp_path, dtype, components):
        expected = np.arange(6 * 8 * components).reshape(6, 8, components).astype(dtype)
        if dtype == "float32":
            expected /= 8
            expected[0, 0, 0] = np.nan
        filepath = str(tmp_path / "indexed_layout.czi")
        with create_czi(filepath) as writer:
            writer.write(data=expected, plane={"C": 0})
        reader = native.czi_reader(filepath)
        try:
            pixels = np.asarray(reader.ReadSubBlock(0))
        finally:
            reader.close()
        del reader
        assert pixels.dtype == expected.dtype
        assert pixels.shape == expected.shape
        np.testing.assert_array_equal(pixels, expected)

    def test_repeated_m_selects_stored_index_not_m_or_full_resolution(self, indexed_reader) -> None:
        info = indexed_reader.GetSubBlockInfo(index=np.int64(1))
        assert info.mIndex == 37
        assert info.coordinate.to_dict() == {"S": 8, "T": 9, "C": 11, "Z": 13}
        assert (info.physicalSize.h, info.physicalSize.w) == (16, 24)
        pixels = np.asarray(indexed_reader.ReadSubBlock(index=1))
        expected = (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
        assert pixels.shape == (16, 24, 1)
        np.testing.assert_array_equal(pixels[..., 0], expected)

    @pytest.mark.parametrize("method", ["GetSubBlockInfo", "ReadSubBlock"])
    @pytest.mark.parametrize("index", [True, False, 1.5, "0", None])
    def test_rejects_non_integer_indices(self, indexed_reader, method: str, index) -> None:
        with pytest.raises(TypeError):
            getattr(indexed_reader, method)(index)

    @pytest.mark.parametrize("method", ["GetSubBlockInfo", "ReadSubBlock"])
    @pytest.mark.parametrize("index", [-1, 2, 37, 2**31, 2**100, -(2**100)])
    def test_rejects_missing_indices_without_wrapping(self, indexed_reader, method: str, index: int) -> None:
        with pytest.raises(IndexError):
            getattr(indexed_reader, method)(index)

    @pytest.mark.parametrize("method", ["GetSubBlockInfo", "ReadSubBlock"])
    def test_closed_reader_rejects_new_operations(self, indexed_reader, method: str) -> None:
        indexed_reader.close()
        with pytest.raises(RuntimeError, match="closed"):
            getattr(indexed_reader, method)(0)

    @pytest.mark.parametrize("filename", ["literal_gray16_unsupported42_v2.czi", "literal_gray16_invalid_utf8.czi"])
    def test_descriptor_does_not_decode_pixels_or_xml(self, filename: str) -> None:
        reader = native.czi_reader(os.path.join(working_dir, "../test_data/synthetic", filename))
        try:
            info = reader.GetSubBlockInfo(0)
            assert (info.physicalSize.h, info.physicalSize.w) == (32, 48)
            if "unsupported42" in filename:
                assert info.compressionModeRaw == 42
                with pytest.raises(ValueError, match="compression"):
                    reader.ReadSubBlock(0)
        finally:
            reader.close()

    @pytest.mark.parametrize("filename", ["c1_bgr24", "c1_bgr48"])
    def test_native_color_order_and_owned_nonempty_buffer(self, filename: str) -> None:
        reader = native.czi_reader(os.path.join(working_dir, "../test_data", filename + ".czi"))
        try:
            pixels = np.asarray(reader.ReadSubBlock(0))
        finally:
            reader.close()
        with np.load(
            os.path.join(working_dir, "../test_data", filename + "_plane.npz"), allow_pickle=False
        ) as reference:
            expected = reference["arr"]
            assert pixels.dtype == expected.dtype
            assert pixels.shape == expected.shape
            np.testing.assert_array_equal(pixels, expected)


class TestPublicSubblockReads:
    @pytest.fixture
    def public_reader(self):
        data = TestIndexedNativeAccess.stream_data()
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        reads.clear()
        try:
            yield reader, reads, data
        finally:
            reader.close()

    def test_indexed_public_pixels_use_stored_yx_geometry(self, public_reader):
        reader, reads, data = public_reader
        pixels = reader.read_subblock(index=np.int64(1))
        expected = (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
        assert pixels.shape == (16, 24)
        assert pixels.dtype == expected.dtype
        np.testing.assert_array_equal(pixels, expected)
        entry = TestIndexedNativeAccess.directory_entry(data, 1)
        start = struct.unpack_from("<q", data, entry + 6)[0]
        end = start + 32 + struct.unpack_from("<q", data, start + 16)[0]
        assert reads
        assert all(start <= offset and offset + size <= end for offset, size in reads)

    def test_unique_m_helper_reads_the_filtered_block(self, public_reader):
        reader, reads, data = public_reader
        assert reader.list_subblocks()[0].logical_rect == (-8, -4, 48, 32)
        reads.clear()
        pixels = reader.read_subblock_by_m(m_index=37, plane={"T": 9, "C": 11, "Z": 13}, scene=8)
        expected = (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
        np.testing.assert_array_equal(pixels, expected)
        entry = TestIndexedNativeAccess.directory_entry(data, 1)
        start = struct.unpack_from("<q", data, entry + 6)[0]
        end = start + 32 + struct.unpack_from("<q", data, start + 16)[0]
        assert reads
        assert all(start <= offset and offset + size <= end for offset, size in reads)

    @pytest.mark.parametrize("m_index,count", [(0, 0), (37, 2)])
    def test_nonunique_m_helper_fails_without_payload_reads(self, public_reader, m_index, count):
        reader, reads, _data = public_reader
        with pytest.raises(ValueError) as caught:
            reader.read_subblock_by_m(m_index, plane={}, scene=None, level=None)
        assert f"m_index={m_index}" in str(caught.value)
        assert str(count) in str(caught.value)
        assert "plane=" in str(caught.value)
        assert "scene=" in str(caught.value)
        assert "level=" in str(caught.value)
        assert reads == []

    @pytest.mark.parametrize(
        "dtype,components",
        [
            ("uint8", 1),
            ("uint16", 1),
            ("float32", 1),
            ("uint8", 3),
            ("uint16", 3),
            ("float32", 3),
        ],
    )
    def test_public_layouts_survive_close_and_reader_deletion(self, tmp_path, dtype, components):
        expected = np.arange(5 * 7 * components).reshape(5, 7, components).astype(dtype)
        if dtype == "float32":
            expected /= 8
            expected[0, 0, 0] = np.nan
        filepath = str(tmp_path / "public_layout.czi")
        with create_czi(filepath) as writer:
            writer.write(data=expected, plane={"C": 0})
        with open_czi(filepath) as reader:
            pixels = reader.read_subblock(0)
        del reader
        assert pixels.dtype == expected.dtype
        assert pixels.shape == ((5, 7) if components == 1 else (5, 7, 3))
        np.testing.assert_array_equal(pixels, expected[..., 0] if components == 1 else expected)

    @pytest.mark.parametrize(
        "filename",
        [
            "literal_gray16_raw.czi",
            "literal_gray16_zstd0.czi",
            "literal_gray16_zstd1.czi",
            "literal_gray16_jpegxr.czi",
            "literal_gray16_invalid_utf8.czi",
        ],
    )
    def test_public_compression_pixels_match_literal_reference(self, filename):
        with open_czi(os.path.join(working_dir, "../test_data/synthetic", filename)) as reader:
            pixels = reader.read_subblock(0)
        expected = (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)
        np.testing.assert_array_equal(pixels, expected)
        assert pixels[0, 0] == 0

    @pytest.mark.parametrize("filename", ["c1_bgr24", "c1_bgr48"])
    def test_public_color_order_matches_independent_reference(self, filename):
        with open_czi(os.path.join(working_dir, "../test_data", filename + ".czi")) as reader:
            pixels = reader.read_subblock(0)
        with np.load(
            os.path.join(working_dir, "../test_data", filename + "_plane.npz"), allow_pickle=False
        ) as reference:
            np.testing.assert_array_equal(pixels, reference["arr"])

    @pytest.mark.parametrize("mask_aware", [False, True])
    @pytest.mark.parametrize("filename", ["literal_valid_mask_v2.czi", "literal_corrupt_mask_v2.czi"])
    def test_direct_pixels_do_not_apply_or_decode_masks(self, filename, mask_aware):
        with open_czi(
            os.path.join(working_dir, "../test_data/synthetic", filename),
            reader_options=ReaderOptions(enable_mask_awareness=mask_aware),
        ) as reader:
            pixels = reader.read_subblock_by_m(0)
            expected = (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)
            np.testing.assert_array_equal(pixels, expected)
            if filename == "literal_valid_mask_v2.czi":
                composed = reader.read(plane={"C": 0, "T": 0, "Z": 0}, scene=0)[..., 0]
                if mask_aware:
                    assert np.any(composed != pixels)
                else:
                    np.testing.assert_array_equal(composed, pixels)

    def test_repeated_m_across_levels_requires_explicit_selection(self):
        data = TestIndexedNativeAccess.stream_data("stored_levels_same_m37.czi")
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            infos = reader.list_subblocks(m_index=37, plane={"C": 0}, scene=0)
            lower = next(info for info in infos if info.stored_shape == (16, 24))
            reads.clear()
            with pytest.raises(ValueError, match="matched 2"):
                reader.read_subblock_by_m(37, plane={"C": 0}, scene=0)
            with pytest.raises(ValueError, match="matched 0"):
                reader.read_subblock_by_m(37, level=2**100)
            assert reads == []
            pixels = reader.read_subblock_by_m(37, plane={"C": 0}, scene=0, level=lower.level_id)
            expected = (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
            np.testing.assert_array_equal(pixels, expected)
            entry = TestIndexedNativeAccess.directory_entry(data, lower.index)
            start = struct.unpack_from("<q", data, entry + 6)[0]
            end = start + 32 + struct.unpack_from("<q", data, start + 16)[0]
            assert reads
            assert all(start <= offset and offset + size <= end for offset, size in reads)
        finally:
            reader.close()

    def test_valid_negative_m_and_numpy_selectors(self):
        with open_czi(os.path.join(working_dir, "../test_data/synthetic/stored_levels_negative_m7.czi")) as reader:
            pixels = reader.read_subblock_by_m(np.int64(-7), plane={"C": np.int64(0)}, scene=np.int64(0))
        expected = (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)
        np.testing.assert_array_equal(pixels, expected)

    def test_sparse_indices_missing_coordinates_and_unclassified_geometry(self):
        reader = TestSubblockCatalog.reader(
            [
                TestSubblockCatalog.descriptor(3, {}, -(2**31)),
                TestSubblockCatalog.descriptor(9, {"C": 0}, 0),
                TestSubblockCatalog.descriptor(12, {"C": -2}, -7, logical=(0, 32)),
            ]
        )
        decoded = []

        def read_subblock(index):
            decoded.append(index)
            return np.full((2, 3, 1), index, dtype=np.uint16)

        reader._czi_reader.ReadSubBlock = read_subblock
        np.testing.assert_array_equal(reader.read_subblock_by_m(0, plane={"C": 0}), np.full((2, 3), 9))
        np.testing.assert_array_equal(reader.read_subblock_by_m(-7, plane={"C": -2}), np.full((2, 3), 12))
        np.testing.assert_array_equal(reader.read_subblock(3), np.full((2, 3), 3))
        assert decoded == [9, 12, 3]
        assert reader.list_subblocks(m_index=-7)[0].level_id is None
        with pytest.raises(ValueError, match="matched 0"):
            reader.read_subblock_by_m(0, plane={"C": -2})
        assert decoded == [9, 12, 3]

    @pytest.mark.parametrize(
        "index,error",
        [
            *[(value, TypeError) for value in [True, False, np.bool_(True), 1.5, "0", None]],
            *[(value, IndexError) for value in [-1, 2, 37, 2**31, 2**100, -(2**100)]],
        ],
    )
    def test_public_index_validation_precedes_payload(self, public_reader, index, error):
        reader, reads, _data = public_reader
        with pytest.raises(error):
            reader.read_subblock(index)
        assert reads == []

    @pytest.mark.parametrize(
        "m_index,filters,error",
        [
            *[(value, {}, TypeError) for value in [True, False, np.bool_(True), 1.5, "37", None]],
            (-(2**31), {}, ValueError),
            (2**31 - 1, {}, ValueError),
            (2**100, {}, OverflowError),
            (-(2**31) - 1, {}, OverflowError),
            (37, {"plane": "C0"}, TypeError),
            *[(37, {"plane": {key: 0}}, ValueError) for key in ["S", "M", "X", "Y", "A", "c", 1]],
            (37, {"plane": {"C": True}}, TypeError),
            (37, {"plane": {"C": 2**31}}, OverflowError),
            (37, {"scene": True}, TypeError),
            (37, {"scene": 2**31}, OverflowError),
            (37, {"level": True}, TypeError),
            (37, {"level": -1}, ValueError),
        ],
    )
    def test_m_selector_validation_precedes_payload(self, public_reader, m_index, filters, error):
        reader, reads, _data = public_reader
        with pytest.raises(error):
            reader.read_subblock_by_m(m_index, **filters)
        assert reads == []
        assert reader._subblock_catalog is None

    @pytest.mark.parametrize("method", ["read_subblock", "read_subblock_by_m"])
    def test_public_signatures_reject_extra_selectors_and_closed_reads(self, public_reader, method):
        reader, reads, _data = public_reader
        with pytest.raises(TypeError):
            getattr(reader, method)(0, {})
        with pytest.raises(TypeError):
            getattr(reader, method)(0, zoom=0.5)
        reader.list_subblocks()
        reader.close()
        reader.close()
        with pytest.raises(RuntimeError, match="closed"):
            getattr(reader, method)(0)
        assert reads == []

    @pytest.mark.parametrize("failure", ["io", "truncated", "codec"])
    def test_public_payload_errors_retain_original_causes(self, failure):
        data = TestIndexedNativeAccess.stream_data("literal_gray16_zstd0.czi")
        injected = OSError("injected public read failure")
        state = {"fail": False}

        def read_at(offset, size):
            if state["fail"]:
                raise injected
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            if failure == "io":
                state["fail"] = True
            elif failure == "truncated":
                data.clear()
            else:
                offset = data.index(b"\x28\xb5\x2f\xfd")
                data[offset : offset + 4] = b"\0\0\0\0"
            with pytest.raises(OSError if failure == "io" else ValueError) as caught:
                reader.read_subblock(0)
            assert caught.value.__cause__ is not None
            if failure == "io":
                assert caught.value.__cause__ is injected
        finally:
            reader.close()

    def test_public_unknown_compression_is_explicit(self):
        with open_czi(
            os.path.join(working_dir, "../test_data/synthetic/literal_gray16_unsupported42_v2.czi")
        ) as reader:
            assert reader.list_subblocks()[0].compression_mode == 42
            with pytest.raises(ValueError, match="compression"):
                reader.read_subblock(0)


class TestStoredLevelReads:
    @staticmethod
    def literal(lower=False):
        if lower:
            return (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
        return (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)

    def test_discovery_and_exact_reduced_level_pixels(self):
        filepath = os.path.join(working_dir, "../test_data/synthetic/stored_levels_same_m37.czi")
        with open_czi(filepath) as reader:
            levels = reader.list_stored_levels(scene=0, plane={"C": 0})
            assert len(levels) == 2
            selected = next(level for level in levels if level.output_shape == (16, 24))
            assert selected.coordinates == {"S": 0, "T": 0, "C": 0, "Z": 0}
            pixels = reader.read_stored_level(selected.level_id, scene=0, plane={"C": 0})
        expected = (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
        np.testing.assert_array_equal(pixels, expected)
        assert selected.subblocks[0].stored_shape == pixels.shape

    def test_present_level_with_uncovered_roi_is_black(self):
        filepath = os.path.join(working_dir, "../test_data/synthetic/stored_levels_same_m37.czi")
        with open_czi(filepath) as reader:
            selected = next(level for level in reader.list_stored_levels() if level.output_shape == (16, 24))
            pixels = reader.read_stored_level(selected.level_id, roi=(1000, -1000, 17, 9))
            assert pixels.shape == (4, 8)
            assert pixels.dtype == np.uint16
            assert not pixels.any()

    def test_frozen_descriptor_required_fields_and_owned_coordinates(self):
        coordinates = {"S": 8}
        info = StoredLevelInfo(1, coordinates, (-8, -4, 48, 32), (), None, None)
        coordinates["S"] = 2
        assert info.coordinates == {"S": 8}
        assert [item.name for item in fields(info)] == [
            "level_id",
            "coordinates",
            "logical_rect",
            "subblocks",
            "downsample",
            "output_shape",
        ]
        with pytest.raises(TypeError):
            StoredLevelInfo()
        with pytest.raises(FrozenInstanceError):
            info.level_id = 2
        with pytest.raises(TypeError):
            info.coordinates["S"] = 2

    @pytest.mark.parametrize("scenario", ["factor_three", "mixed_types", "absent_m"])
    def test_directory_geometry_and_ordering_contracts(self, scenario):
        filename = "stored_levels_same_m37.czi" if scenario == "factor_three" else "literal_overlapping_tiles.czi"
        data = TestIndexedNativeAccess.stream_data(filename)
        entry = TestIndexedNativeAccess.directory_entry(data, 1 if scenario != "absent_m" else 0)
        subblock = struct.unpack_from("<q", data, entry + 6)[0] + 48
        assert data[subblock : subblock + 2] == b"DV"
        for base in (entry, subblock):
            if scenario == "mixed_types":
                struct.pack_into("<i", data, base + 2, int(native.PixelType.Gray8))
                continue
            count = struct.unpack_from("<i", data, base + 28)[0]
            for dimension in range(count):
                offset = base + 32 + 20 * dimension
                name = data[offset : offset + 4].rstrip(b"\0")
                if scenario == "factor_three" and name in (b"X", b"Y"):
                    stored = struct.unpack_from("<i", data, offset + 16)[0]
                    struct.pack_into("<i", data, offset + 8, stored * 3)
                if scenario == "absent_m" and name == b"M":
                    struct.pack_into("<i", data, offset + 4, 2**31 - 1)
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            reads.clear()
            levels = reader.list_stored_levels()
            if scenario == "mixed_types":
                with pytest.raises(ValueError, match="Mixed"):
                    reader.read_stored_level(levels[0].level_id, roi=(30, 20, 8, 8))
                assert reads == []
            elif scenario == "factor_three":
                selected = next(level for level in levels if level.downsample == (3, 3))
                np.testing.assert_array_equal(reader.read_stored_level(selected.level_id), self.literal(lower=True))
            else:
                expected = self.literal()
                expected[:16, :24] = self.literal(lower=True)
                np.testing.assert_array_equal(reader.read_stored_level(levels[0].level_id), expected)
        finally:
            reader.close()

    @pytest.mark.parametrize("filename", ["literal_tiles_with_gap.czi", "literal_overlapping_tiles.czi"])
    def test_gap_and_ascending_m_overlap_pixels(self, filename):
        with open_czi(os.path.join(working_dir, "../test_data/synthetic", filename)) as reader:
            levels = reader.list_stored_levels()
            assert len(levels) == 1
            pixels = reader.read_stored_level(levels[0].level_id)
        if "gap" in filename:
            expected = np.zeros((32, 96), dtype=np.uint16)
            expected[:, :48] = self.literal()
            expected[:16, 72:] = self.literal(lower=True)
        else:
            expected = self.literal()
            expected[:16, :24] = self.literal(lower=True)
        np.testing.assert_array_equal(pixels, expected)

    @pytest.mark.parametrize("origin", [-1, 1, 3])
    def test_roi_offsets_truncate_toward_zero(self, origin):
        filepath = os.path.join(working_dir, "../test_data/synthetic/stored_levels_same_m37.czi")
        with open_czi(filepath) as reader:
            lower = next(level for level in reader.list_stored_levels() if level.output_shape == (16, 24))
            pixels = reader.read_stored_level(lower.level_id, roi=(origin, origin, 48, 32))
        expected = self.literal(lower=True)
        if origin == 3:
            expected = np.zeros((16, 24), dtype=np.uint16)
            expected[:-1, :-1] = self.literal(lower=True)[1:, 1:]
        np.testing.assert_array_equal(pixels, expected)

    @pytest.mark.parametrize("enabled", [False, True])
    @pytest.mark.parametrize("corrupt", [False, True])
    def test_mask_awareness_is_strict_and_does_not_rewrite_direct_pixels(self, enabled, corrupt):
        filename = "literal_corrupt_mask_v2.czi" if corrupt else "literal_valid_mask_v2.czi"
        with open_czi(
            os.path.join(working_dir, "../test_data/synthetic", filename),
            reader_options=ReaderOptions(enable_mask_awareness=enabled),
        ) as reader:
            level = reader.list_stored_levels()[0]
            if enabled and corrupt:
                with pytest.raises(ValueError, match="mask"):
                    reader.read_stored_level(level.level_id)
            else:
                pixels = reader.read_stored_level(level.level_id)
                expected = self.literal()
                if enabled:
                    rows, columns = np.indices(expected.shape)
                    expected[(rows + columns) % 3 == 0] = 0
                np.testing.assert_array_equal(pixels, expected)
            np.testing.assert_array_equal(reader.read_subblock(0), self.literal())

    def test_discovery_and_selected_level_io_are_exact(self):
        data = TestIndexedNativeAccess.stream_data("stored_levels_same_m37.czi")
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            reads.clear()
            levels = reader.list_stored_levels()
            lower = next(level for level in levels if level.output_shape == (16, 24))
            with pytest.raises(ValueError, match="matched 0"):
                reader.read_stored_level(2**100)
            assert reader.list_stored_levels(scene=99) == []
            assert reads == []
            pixels = reader.read_stored_level(lower.level_id)
            entry = TestIndexedNativeAccess.directory_entry(data, lower.subblocks[0].index)
            start = struct.unpack_from("<q", data, entry + 6)[0]
            end = start + 32 + struct.unpack_from("<q", data, start + 16)[0]
            assert reads
            assert all(start <= offset and offset + size <= end for offset, size in reads)
            np.testing.assert_array_equal(pixels, self.literal(lower=True))
            reads.clear()
            reader.read_stored_level(lower.level_id, roi=(1000, 1000, 8, 8))
            assert reads == []
        finally:
            reader.close()
        assert lower.subblocks
        with pytest.raises(RuntimeError, match="closed"):
            reader.list_stored_levels()
        with pytest.raises(RuntimeError, match="closed"):
            reader.read_stored_level(lower.level_id)

    def test_multiple_plane_groups_require_explicit_selection(self):
        with open_czi(CZI_MULTI_DIM) as reader:
            levels = reader.list_stored_levels()
            assert len(levels) > 1
            with pytest.raises(ValueError, match="scene/plane groups"):
                reader.read_stored_level(levels[0].level_id)

    def test_unsupported_and_unclassified_geometry_remain_discoverable(self):
        reader = TestSubblockCatalog.reader(
            [
                TestSubblockCatalog.descriptor(0, {"S": 2}, stored=(23, 16)),
                TestSubblockCatalog.descriptor(1, {"S": 8}, logical=(0, 32)),
            ]
        )
        levels = reader.list_stored_levels()
        assert len(levels) == 1
        assert levels[0].output_shape is None
        assert reader.list_subblocks(scene=8)[0].level_id is None
        with pytest.raises(ValueError, match="unsupported stored geometry"):
            reader.read_stored_level(levels[0].level_id)

    @pytest.mark.parametrize(
        "dtype,components", [("uint8", 1), ("uint16", 1), ("float32", 1), ("uint8", 3), ("uint16", 3), ("float32", 3)]
    )
    def test_native_layouts_and_post_close_lifetime(self, tmp_path, dtype, components):
        expected = np.arange(5 * 7 * components).reshape(5, 7, components).astype(dtype)
        if dtype == "float32":
            expected /= 8
            expected[0, 0, 0] = np.nan
        filepath = str(tmp_path / "stored_level.czi")
        with create_czi(filepath) as writer:
            writer.write(expected, plane={"C": 0})
        with open_czi(filepath) as reader:
            level = reader.list_stored_levels()[0]
            pixels = reader.read_stored_level(level.level_id)
        assert pixels.dtype == expected.dtype
        np.testing.assert_array_equal(pixels, expected[..., 0] if components == 1 else expected)

    @pytest.mark.parametrize(
        "kwargs,error",
        [
            ({"level": True}, TypeError),
            ({"level": None}, TypeError),
            ({"level": -1}, ValueError),
            ({"level": 2**100}, ValueError),
            ({"roi": [0, 0, 8, 8]}, TypeError),
            ({"roi": (0, 0, True, 8)}, TypeError),
            ({"roi": (0, 0, 0, 8)}, ValueError),
            ({"roi": (0, 0, 8, -1)}, ValueError),
            ({"roi": (0, 0, 8)}, ValueError),
            ({"roi": (2**31 - 1, 0, 8, 8)}, OverflowError),
            ({"roi": (0, 0, 2**31 - 1, 8)}, OverflowError),
        ],
    )
    def test_invalid_read_arguments(self, kwargs, error):
        with open_czi(os.path.join(working_dir, "../test_data/synthetic/stored_levels_same_m37.czi")) as reader:
            filters = {"level": reader.list_stored_levels()[0].level_id}
            filters.update(kwargs)
            with pytest.raises(error):
                reader.read_stored_level(**filters)


class TestSelectiveSubblockReads:
    def test_raw_xml_is_separate_from_pixels(self):
        filepath = os.path.join(working_dir, "../test_data/synthetic/literal_gray16_raw.czi")
        with open_czi(filepath) as reader:
            xml = reader.read_subblock_metadata_xml(0)
        assert isinstance(xml, str)
        assert xml

    def test_stored_mask_is_boolean_and_survives_close(self):
        filepath = os.path.join(working_dir, "../test_data/synthetic/literal_valid_mask_v2.czi")
        with open_czi(filepath) as reader:
            mask = reader.read_subblock_mask(0)
        assert mask.shape == (32, 48)
        assert mask.dtype == np.bool_
        rows, columns = np.indices((32, 48))
        np.testing.assert_array_equal(mask, (rows + columns) % 3 != 0)

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("literal_xml_absent.czi", None),
            ("literal_xml_malformed_xml.czi", "<METADATA><UnknownProbe>literal"),
            (
                "literal_xml_unknown_element.czi",
                "<?xml version='1.0' encoding='utf8'?>\n"
                '<METADATA><UnknownProbe token="alpha">literal</UnknownProbe></METADATA>',
            ),
        ],
    )
    def test_xml_preserves_absence_and_original_text(self, filename, expected):
        with open_czi(os.path.join(working_dir, "../test_data/synthetic", filename)) as reader:
            assert reader.read_subblock_metadata_xml(0) == expected

    def test_xml_errors_are_not_absence(self):
        filepath = os.path.join(working_dir, "../test_data/synthetic/literal_gray16_invalid_utf8.czi")
        with open_czi(filepath) as reader:
            with pytest.raises(UnicodeDecodeError):
                reader.read_subblock_metadata_xml(0)

    def test_unicode_xml_and_io_errors_are_preserved(self):
        data = TestIndexedNativeAccess.stream_data("literal_xml_unknown_element.czi")
        original = b'<UnknownProbe token="alpha">literal</UnknownProbe>'
        replacement = b'<UnknownProbe token="alpha">caf\xc3\xa9  </UnknownProbe>'
        assert len(original) == len(replacement)
        assert original in data
        data = data.replace(original, replacement)
        injected = OSError("injected metadata read failure")
        state = {"fail": False}

        def read_at(offset, size):
            if state["fail"]:
                raise injected
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            xml = reader.read_subblock_metadata_xml(0)
            assert xml == (
                "<?xml version='1.0' encoding='utf8'?>\n"
                '<METADATA><UnknownProbe token="alpha">caf\u00e9  </UnknownProbe></METADATA>'
            )
            state["fail"] = True
            with pytest.raises(OSError) as caught:
                reader.read_subblock_metadata_xml(0)
            assert caught.value.__cause__ is injected
        finally:
            reader.close()

    def test_metadata_does_not_require_supported_pixel_decoder(self):
        filepath = os.path.join(working_dir, "../test_data/synthetic/literal_gray16_unsupported42_v2.czi")
        with open_czi(filepath) as reader:
            assert reader.read_subblock_metadata_xml(0)
            assert reader.read_subblock_mask(0) is None
            with pytest.raises(ValueError):
                reader.read_subblock(0)

    def test_absent_and_corrupt_masks_are_distinct(self):
        with open_czi(CZI_SIMPLE) as reader:
            assert reader.read_subblock_mask(0) is None
        filepath = os.path.join(working_dir, "../test_data/synthetic/literal_corrupt_mask_v2.czi")
        with open_czi(filepath) as reader:
            with pytest.raises(ValueError, match="mask"):
                reader.read_subblock_mask(0)

    @pytest.mark.parametrize("method", ["read_subblock_metadata_xml", "read_subblock_mask"])
    @pytest.mark.parametrize(
        "index,error",
        [
            (True, TypeError),
            (np.bool_(True), TypeError),
            (1.5, TypeError),
            (None, TypeError),
            (-1, IndexError),
            (2**100, IndexError),
            (99, IndexError),
        ],
    )
    def test_checked_indices_and_close(self, method, index, error):
        with open_czi(CZI_SIMPLE) as reader:
            with pytest.raises(error):
                getattr(reader, method)(index)
        with pytest.raises(RuntimeError, match="closed"):
            getattr(reader, method)(0)

    def test_selected_metadata_reads_only_the_selected_segment(self):
        data = TestIndexedNativeAccess.stream_data()
        reads = []

        def read_at(offset, size):
            reads.append((offset, size))
            return bytes(data[offset : offset + size])

        reader = TestSubblockCatalog.reader([])
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        try:
            reads.clear()
            assert reader.read_subblock_metadata_xml(1)
            entry = TestIndexedNativeAccess.directory_entry(data, 1)
            start = struct.unpack_from("<q", data, entry + 6)[0]
            end = start + 32 + struct.unpack_from("<q", data, start + 16)[0]
            assert reads
            assert all(start <= offset and offset + size <= end for offset, size in reads)
        finally:
            reader.close()


class TestSubblockCatalog:
    @staticmethod
    def descriptor(index=0, coordinates=None, m_index=37, logical=(48, 32), stored=(48, 32)):
        return index, SimpleNamespace(
            coordinate=SimpleNamespace(to_dict=lambda: dict(coordinates or {})),
            mIndex=m_index,
            is_mindex_valid=lambda: m_index not in {-(2**31), 2**31 - 1},
            logicalRect=SimpleNamespace(x=-8, y=-4, w=logical[0], h=logical[1]),
            physicalSize=SimpleNamespace(w=stored[0], h=stored[1]),
            pixelType=native.PixelType.Gray16,
            compressionModeRaw=42,
        )

    @staticmethod
    def reader(directory):
        class DirectoryOnly:
            calls = 0

            def GetSubBlockDirectory(self):
                self.calls += 1
                return directory

            def close(self):
                pass

        reader = CziReader.__new__(CziReader)
        reader._czi_reader = DirectoryOnly()
        reader._subblock_catalog = None
        reader._subblock_closed = False
        return reader

    def test_counts_preserve_sparse_scenes_and_count_repeated_m(self):
        reader = self.reader(
            [
                self.descriptor(12, {"S": 2, "C": 5}),
                self.descriptor(3, {"S": 8, "C": 5}),
                self.descriptor(9, {"S": 2, "C": 7}),
                self.descriptor(21, {}, -(2**31)),
                self.descriptor(30, {"S": 0, "C": 0}, 0),
            ]
        )
        assert reader.count_subblocks() == 5
        assert reader.count_subblocks_by_scene() == {8: 1, 2: 2, None: 1, 0: 1}
        assert reader.count_subblocks(m_index=37) == 3
        assert reader.count_subblocks_by_scene(m_index=37) == {8: 1, 2: 2}
        assert reader.count_subblocks(plane={"C": np.int64(5)}, scene=2, m_index=37) == 1
        assert reader.count_subblocks_by_scene(plane={"C": 5}, scene=2, m_index=37) == {2: 1}
        assert reader.count_subblocks(scene=0) == 1
        assert reader.count_subblocks_by_scene(scene=0) == {0: 1}
        assert reader.count_subblocks(scene=99) == 0
        assert reader.count_subblocks_by_scene(scene=99) == {}
        counts = reader.count_subblocks_by_scene()
        counts.clear()
        assert reader.count_subblocks_by_scene(plane={}) == {8: 1, 2: 2, None: 1, 0: 1}
        assert reader._czi_reader.calls == 1

    def test_counts_filter_levels_and_retain_unclassified_entries(self):
        reader = self.reader(
            [
                self.descriptor(0, {"S": 2}, stored=(24, 16)),
                self.descriptor(1, {"S": 2}),
                self.descriptor(2, {"S": 8}, logical=(0, 32)),
                self.descriptor(9, {"S": 2, "T": 3}, stored=(24, 16)),
            ]
        )
        assert reader.count_subblocks() == 4
        assert reader.count_subblocks_by_scene() == {2: 3, 8: 1}
        assert reader.count_subblocks(level=0) == 2
        assert reader.count_subblocks_by_scene(level=0) == {2: 2}
        assert reader.count_subblocks(level=1) == 1
        assert reader.count_subblocks_by_scene(level=1) == {2: 1}
        assert reader.count_subblocks(plane={"T": 3}, scene=2, m_index=37, level=0) == 1
        assert reader.count_subblocks_by_scene(plane={"T": 3}, scene=2, m_index=37, level=0) == {2: 1}
        assert reader.count_subblocks(level=2**100) == 0
        assert reader.count_subblocks_by_scene(level=2**100) == {}

    @pytest.mark.parametrize("method", ["count_subblocks", "count_subblocks_by_scene"])
    def test_count_signatures_and_closed_reader(self, method):
        reader = self.reader([])
        with pytest.raises(TypeError):
            getattr(reader, method)({"C": 0})
        reader.close()
        with pytest.raises(RuntimeError, match="closed"):
            getattr(reader, method)()
        assert reader._czi_reader.calls == 0

    def test_owned_frozen_descriptor_required_fields(self):
        coordinates = {"S": 2, "C": 5}
        info = SubblockInfo(7, coordinates, None, (-8, -4, 48, 32), (32, 48), 1, 42, None)
        coordinates["S"] = 9
        assert info.coordinates == {"S": 2, "C": 5}
        assert [item.name for item in fields(info)] == [
            "index",
            "coordinates",
            "m_index",
            "logical_rect",
            "stored_shape",
            "pixel_type",
            "compression_mode",
            "level_id",
        ]
        with pytest.raises(FrozenInstanceError):
            info.index = 3
        with pytest.raises(TypeError):
            info.coordinates["S"] = 9
        with pytest.raises(TypeError):
            SubblockInfo()

    def test_sparse_indices_missing_zero_and_intersecting_filters(self):
        reader = self.reader(
            [
                self.descriptor(12, {"S": 2, "C": 5, "Z": -3}, -7),
                self.descriptor(3, {"C": 0}, -(2**31)),
                self.descriptor(9, {}, 0),
            ]
        )
        assert [info.index for info in reader.list_subblocks()] == [3, 9, 12]
        assert [info.index for info in reader.list_subblocks(plane={"C": 0})] == [3]
        assert [info.index for info in reader.list_subblocks(m_index=0)] == [9]
        assert [info.index for info in reader.list_subblocks(plane={"Z": -3}, scene=2, m_index=-7)] == [12]
        assert reader.list_subblocks(scene=0) == []
        assert reader.list_subblocks(plane={}) == reader.list_subblocks()
        assert reader.list_subblocks()[0].m_index is None
        assert reader._czi_reader.calls == 1

    def test_exact_levels_are_stable_not_ordinals_and_keep_unclassified(self):
        reader = self.reader(
            [
                self.descriptor(0, {"S": 2}, stored=(24, 16)),
                self.descriptor(1, {"S": 8}),
                self.descriptor(2, {"S": 2}, stored=(24, 16)),
                self.descriptor(3, stored=(23, 16)),
                self.descriptor(4, logical=(0, 32)),
                self.descriptor(5, stored=(32, 16)),
            ]
        )
        infos = reader.list_subblocks()
        assert [info.level_id for info in infos] == [0, 1, 0, 2, None, 3]
        assert [info.index for info in reader.list_subblocks(level=0)] == [0, 2]
        assert reader.list_subblocks(scene=8, level=0) == []
        assert reader.list_subblocks(level=2**100) == []
        reader.list_subblocks().clear()
        assert len(reader.list_subblocks()) == 6
        reader.close()
        assert infos[0].stored_shape == (16, 24)
        with pytest.raises(RuntimeError, match="closed"):
            reader.list_subblocks()

    @pytest.mark.parametrize("method", ["list_subblocks", "count_subblocks", "count_subblocks_by_scene"])
    @pytest.mark.parametrize(
        "filters,error",
        [
            ({"plane": "C0"}, TypeError),
            ({"plane": []}, TypeError),
            *[({"plane": {dimension: 0}}, ValueError) for dimension in ["S", "M", "X", "Y", "A", "c", "unknown", 1]],
            *[
                ({name: value}, TypeError)
                for name in ["scene", "m_index", "level"]
                for value in [True, False, np.bool_(True), 1.5, "0"]
            ],
            ({"plane": {"C": True}}, TypeError),
            ({"plane": {"C": 1.5}}, TypeError),
            ({"plane": {"C": 2**31}}, OverflowError),
            ({"scene": -(2**31) - 1}, OverflowError),
            ({"m_index": 2**100}, OverflowError),
            ({"m_index": -(2**31)}, ValueError),
            ({"m_index": 2**31 - 1}, ValueError),
            ({"level": -1}, ValueError),
        ],
    )
    def test_selector_validation_precedes_directory_access(self, method, filters, error):
        reader = self.reader([])
        with pytest.raises(error):
            getattr(reader, method)(**filters)
        assert reader._czi_reader.calls == 0

    def test_empty_directory_and_numpy_integer_selectors(self):
        assert self.reader([]).list_subblocks() == []
        assert self.reader([]).count_subblocks() == 0
        assert self.reader([]).count_subblocks_by_scene() == {}
        reader = self.reader([self.descriptor(5, {"C": -2}, -7)])
        assert reader.list_subblocks(plane={"C": np.int64(-2)}, m_index=np.int64(-7))[0].index == 5
        with pytest.raises(TypeError):
            reader.list_subblocks({"C": -2})


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
