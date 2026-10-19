"""Attachment descriptors, raw bytes and explicit embedded-CZI image reads."""

from pathlib import Path
from dataclasses import FrozenInstanceError, fields
import struct
from uuid import UUID

import numpy as np
import pytest
import _pylibCZIrw as native

from pylibCZIrw.czi import AttachmentInfo, CziReader, create_czi, open_czi

DATA = Path(__file__).resolve().parent.parent / "test_data"
ATTACHMENTS = DATA / "synthetic/literal_slidepreview_cases.czi"


def test_attachment_directory_and_selected_raw_bytes():
    with open_czi(str(ATTACHMENTS)) as reader:
        infos = reader.list_attachments()
        assert infos
        payload = reader.read_attachment(infos[0].index)
    assert isinstance(payload, bytes)
    assert payload
    assert infos[0].name


def test_optional_images_are_none_only_when_absent():
    with open_czi(str(DATA / "synthetic/literal_gray16_raw.czi")) as reader:
        assert reader.list_attachments() == []
        assert reader.read_label() is None
        assert reader.read_preview() is None


def test_owned_descriptor_fields_guid_byte_order_and_defaults():
    with open_czi(str(ATTACHMENTS)) as reader:
        infos = reader.list_attachments()
    assert [info.name for info in infos] == ["Label", "SlidePreview", "SlidePreview", "Unknown", "Corrupt"]
    assert [info.index for info in infos] == [0, 1, 2, 3, 4]
    assert infos[0].content_guid == UUID("11111111-2222-3343-8444-555555555555")
    assert infos[1].content_guid == UUID("11111111-2222-3343-8444-555555555556")
    assert all(info.size_bytes is None for info in infos)
    assert [item.name for item in fields(AttachmentInfo)] == [
        "index",
        "name",
        "content_file_type",
        "content_guid",
        "size_bytes",
    ]
    assert AttachmentInfo(0, "Unknown", "OTHER", infos[0].content_guid).size_bytes is None
    assert AttachmentInfo(0, "Unknown", "OTHER", infos[0].content_guid, 0).size_bytes == 0
    with pytest.raises(TypeError):
        AttachmentInfo()
    with pytest.raises(FrozenInstanceError):
        infos[0].name = "Changed"


@pytest.mark.parametrize("index", [0, 1, 2])
def test_embedded_image_pixels_and_lifetime(index):
    with open_czi(str(ATTACHMENTS)) as reader:
        pixels = reader.read_attachment_image(index=np.int64(index))
        raw = reader.read_attachment(index)
    expected = (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)
    assert pixels.dtype == np.uint16
    np.testing.assert_array_equal(pixels, expected)
    assert raw == (DATA / "synthetic/literal_gray16_raw.czi").read_bytes()


def test_helpers_disambiguate_without_fallback():
    with open_czi(str(ATTACHMENTS)) as reader:
        np.testing.assert_array_equal(reader.read_label(), reader.read_attachment_image(0))
        np.testing.assert_array_equal(reader.read_label(index=None), reader.read_attachment_image(0))
        with pytest.raises(ValueError, match="matched 2"):
            reader.read_preview()
        with pytest.raises(ValueError, match="matched 2"):
            reader.read_preview(index=None)
        np.testing.assert_array_equal(reader.read_preview(index=2), reader.read_attachment_image(2))
        np.testing.assert_array_equal(reader.read_label(index=1), reader.read_attachment_image(1))
        for index in (3, 4):
            assert isinstance(reader.read_attachment(index), bytes)
            with pytest.raises(ValueError):
                reader.read_attachment_image(index)
            with pytest.raises(ValueError):
                reader.read_preview(index=index)
        with pytest.raises(TypeError):
            reader.read_label(0)
        with pytest.raises(TypeError):
            reader.read_preview(1)


@pytest.mark.parametrize("method", ["read_attachment", "read_attachment_image", "read_label", "read_preview"])
@pytest.mark.parametrize(
    "index,error",
    [
        (True, TypeError),
        (np.bool_(True), TypeError),
        (1.5, TypeError),
        ("0", TypeError),
        (-1, IndexError),
        (2**100, IndexError),
        (99, IndexError),
    ],
)
def test_indices_are_checked_for_every_read(method, index, error):
    with open_czi(str(ATTACHMENTS)) as reader:
        with pytest.raises(error):
            getattr(reader, method)(index=index)


@pytest.mark.parametrize(
    "method", ["list_attachments", "read_attachment", "read_attachment_image", "read_label", "read_preview"]
)
def test_closed_reader_rejects_new_access(method):
    with open_czi(str(ATTACHMENTS)) as reader:
        pass
    with pytest.raises(RuntimeError, match="closed"):
        getattr(reader, method)(**({"index": 0} if method != "list_attachments" else {}))


def test_listing_does_not_fetch_payloads_and_io_failures_keep_cause():
    data = ATTACHMENTS.read_bytes()
    reads = []
    injected = OSError("injected attachment read failure")
    state = {"fail": False}

    def read_at(offset, size):
        reads.append((offset, size))
        if state["fail"]:
            raise injected
        return data[offset : offset + size]

    reader = CziReader.__new__(CziReader)
    reader._czi_reader = native.czi_reader._from_stream(read_at)
    reader._subblock_closed = False
    reader._subblock_catalog = None
    try:
        reads.clear()
        assert len(reader.list_attachments()) == 5
        assert reads == []
        reader.read_attachment(0)
        assert reads
        state["fail"] = True
        with pytest.raises(OSError) as caught:
            reader.read_attachment(1)
        assert caught.value.__cause__ is injected
    finally:
        reader.close()


@pytest.mark.parametrize(
    "dtype,components", [("uint8", 1), ("uint16", 1), ("float32", 1), ("uint8", 3), ("uint16", 3), ("float32", 3)]
)
def test_embedded_native_layouts_with_literal_pixels(tmp_path, dtype, components):
    expected = np.arange(5 * 7 * components).reshape(5, 7, components).astype(dtype)
    if dtype == "float32":
        expected /= 8
        expected[0, 0, 0] = np.nan
    filepath = tmp_path / "embedded.czi"
    with create_czi(str(filepath)) as writer:
        writer.write(expected, plane={"C": 0})
    embedded = filepath.read_bytes()
    original = (DATA / "synthetic/literal_gray16_raw.czi").read_bytes()
    assert len(embedded) <= len(original)
    data = bytearray(ATTACHMENTS.read_bytes())
    start = data.index(original)
    data[start : start + len(original)] = embedded.ljust(len(original), b"\0")
    reader = CziReader.__new__(CziReader)
    reader._czi_reader = native.czi_reader._from_stream(lambda offset, size: bytes(data[offset : offset + size]))
    reader._subblock_closed = False
    reader._subblock_catalog = None
    try:
        pixels = reader.read_label()
    finally:
        reader.close()
    assert pixels.dtype == expected.dtype
    np.testing.assert_array_equal(pixels, expected[..., 0] if components == 1 else expected)


def test_duplicate_label_names_are_not_collapsed():
    data = ATTACHMENTS.read_bytes().replace(b"SlidePreview\0", b"Label\0" + b"\0" * 7)
    reader = CziReader.__new__(CziReader)
    reader._czi_reader = native.czi_reader._from_stream(lambda offset, size: data[offset : offset + size])
    reader._subblock_closed = False
    reader._subblock_catalog = None
    try:
        with pytest.raises(ValueError, match="matched 3"):
            reader.read_label()
        assert reader.read_preview() is None
        assert reader.read_label(index=2).shape == (32, 48)
    finally:
        reader.close()


@pytest.mark.parametrize("size", [-1, -(2**63)])
@pytest.mark.parametrize("method", ["read_attachment", "read_attachment_image"])
def test_unrepresentable_attachment_lengths_do_not_allocate_huge_buffers(size, method):
    data = bytearray(ATTACHMENTS.read_bytes())
    start = data.index(b"ZISRAWATTACH")
    struct.pack_into("<q", data, start + 32, size)
    reader = CziReader.__new__(CziReader)
    reader._czi_reader = native.czi_reader._from_stream(lambda offset, count: bytes(data[offset : offset + count]))
    reader._subblock_closed = False
    reader._subblock_catalog = None
    try:
        with pytest.raises(OverflowError, match="buffer range"):
            getattr(reader, method)(0)
    finally:
        reader.close()
