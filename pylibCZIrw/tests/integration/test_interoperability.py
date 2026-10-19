"""Independent-reader, selected-I/O and released-resource evidence for T02."""

from contextlib import contextmanager
import ctypes
import gc
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tracemalloc
import weakref

import czifile
import numpy as np
import pytest
import _pylibCZIrw as native

from pylibCZIrw import czi

DATA = Path(__file__).resolve().parent / "test_data"
SYNTHETIC = DATA / "synthetic"
POSITIVE_FIXTURES = (
    "c1_gray8.czi",
    "c1_gray16.czi",
    "c1_gray32float.czi",
    "c1_bgr24.czi",
    "c1_bgr48.czi",
    "c1_bgr96float.czi",
    "rgb-image.czi",
    "synthetic/literal_gray16_raw.czi",
    "synthetic/literal_gray16_zstd0.czi",
    "synthetic/literal_gray16_zstd1.czi",
    "synthetic/literal_gray16_jpegxr.czi",
    "synthetic/stored_levels_same_m37.czi",
    "synthetic/stored_levels_negative_m7.czi",
    "synthetic/stored_sparse_coordinates.czi",
    "synthetic/stored_levels_irregular.czi",
    "synthetic/literal_tiles_with_gap.czi",
    "synthetic/literal_overlapping_tiles.czi",
    "synthetic/literal_valid_mask_v2.czi",
    "synthetic/literal_xml_unknown_element.czi",
    "synthetic/literal_xml_absent.czi",
    "synthetic/literal_slidepreview_cases.czi",
)
RESOURCE_CASES = {
    "tile": "literal_gray16_zstd1.czi",
    "xml_raw": "literal_gray16_raw.czi",
    "xml_zstd1": "literal_gray16_zstd1.czi",
    "mask": "literal_valid_mask_v2.czi",
    "level": "stored_levels_same_m37.czi",
    "attachment_raw": "literal_slidepreview_cases.czi",
    "attachment_image": "literal_slidepreview_cases.czi",
    "listing": "literal_slidepreview_cases.czi",
}


class _ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_uint32), ("faults", ctypes.c_uint32)] + [
        (name, ctypes.c_size_t)
        for name in (
            "peak_working_set",
            "working_set",
            "peak_paged_pool",
            "paged_pool",
            "peak_nonpaged_pool",
            "nonpaged_pool",
            "pagefile",
            "peak_pagefile",
            "private",
        )
    ]


def literal_pixels(reduced=False):
    if reduced:
        return (40000 + 101 * np.arange(16)[:, None] + 7 * np.arange(24)[None, :]).astype(np.uint16)
    return (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)


@pytest.mark.parametrize("filename", POSITIVE_FIXTURES)
def test_independent_pixels_xml_geometry_and_strict_native_validation(filename):
    filepath = DATA / filename
    options = czi.ReaderOptions(lax_subblock_coordinate_checks=False, ignore_sizem_for_pyramid_subblocks=True)
    with czifile.CziFile(filepath) as reference, czi.CziDocument.open(filepath, reader_options=options) as document:
        infos = document.list_subblocks()
        assert len(infos) == len(reference.subblock_directory)
        for info, entry in zip(infos, reference.subblock_directory, strict=True):
            block = entry.read_segment_data(reference)
            expected = np.squeeze(block.data())
            if entry.pixel_type.samples == 3:
                expected = expected[..., ::-1]
            actual = document.read_subblock(info.index)
            assert actual.dtype == expected.dtype
            np.testing.assert_array_equal(actual, expected)
            axes = dict(zip(entry.dims, entry.start, strict=True))
            sizes = dict(zip(entry.dims, entry.shape, strict=True))
            stored = dict(zip(entry.dims, entry.stored_shape, strict=True))
            assert info.logical_rect == (axes["X"], axes["Y"], sizes["X"], sizes["Y"])
            assert info.stored_shape == (stored["Y"], stored["X"])
            assert info.pixel_type == int(entry.pixel_type)
            assert info.compression_mode == int(entry.compression)
            assert document.read_subblock_metadata_xml(info.index) == (block.metadata(fixesc=False) or None)


def test_sparse_selection_and_reduced_pixels_are_literal_after_close():
    filepath = SYNTHETIC / "stored_sparse_coordinates.czi"
    with czi.CziDocument.open(filepath) as document:
        infos = document.list_subblocks(m_index=37)
        assert [info.coordinates["S"] for info in infos] == [2, 8]
        with pytest.raises(ValueError, match="matched 2"):
            document.read_subblock_by_m(37)
        pixels = document.read_subblock_by_m(37, scene=8, plane={"T": 9, "C": 11, "Z": 13})
        level = document.list_stored_levels(scene=8)[0]
        composed = document.read_stored_level(level.level_id, scene=8)
    np.testing.assert_array_equal(pixels, literal_pixels(reduced=True))
    np.testing.assert_array_equal(composed, pixels)
    assert level.output_shape == (16, 24)


def test_masks_and_composed_reads_keep_distinct_contracts():
    filepath = SYNTHETIC / "literal_valid_mask_v2.czi"
    rows, columns = np.indices((32, 48))
    expected_mask = (rows + columns) % 3 != 0
    with czi.CziDocument.open(filepath, reader_options=czi.ReaderOptions(enable_mask_awareness=True)) as document:
        info = document.list_subblocks()[0]
        raw = document.read_subblock(info.index)
        mask = document.read_subblock_mask(info.index)
        legacy = document.read()
        level = document.list_stored_levels()[0]
        stored = document.read_stored_level(level.level_id)
    np.testing.assert_array_equal(raw, literal_pixels())
    np.testing.assert_array_equal(mask, expected_mask)
    expected = np.where(expected_mask, literal_pixels(), 0)
    np.testing.assert_array_equal(legacy[..., 0], expected)
    np.testing.assert_array_equal(stored, expected)


def test_attachments_match_independent_raw_and_embedded_images():
    filepath = SYNTHETIC / "literal_slidepreview_cases.czi"
    with czifile.CziFile(filepath) as reference, czi.CziDocument.open(filepath) as document:
        infos = document.list_attachments()
        attachments = list(reference.attachments())
        assert [info.name for info in infos] == [item.attachment_entry.name for item in attachments]
        for info, attachment in zip(infos, attachments, strict=True):
            payload = document.read_attachment(info.index)
            assert payload == attachment.data(raw=True)
            if info.index < 3:
                with czifile.CziFile(BytesIO(payload)) as embedded:
                    independent = np.squeeze(embedded.asarray(maxworkers=1))
                np.testing.assert_array_equal(document.read_attachment_image(info.index), independent)
                np.testing.assert_array_equal(independent, literal_pixels())
        with pytest.raises(ValueError, match="matched 2"):
            document.read_preview()
        retained = document.read_label()
    np.testing.assert_array_equal(retained, literal_pixels())


@pytest.mark.parametrize("compression", [None, "zstd0:ExplicitLevel=1", "zstd1:ExplicitLevel=1"])
def test_facade_writer_splitting_and_compression_match_independent_reader(tmp_path, compression):
    filepath = tmp_path / "split.czi"
    expected = np.arange(1700 * 3200, dtype=np.uint16).reshape(1700, 3200)
    with czi.CziDocument.create(filepath, compression_options=compression) as document:
        assert document.write(expected[..., None]) is True
    with czi.CziDocument.open(filepath) as document:
        infos = document.list_subblocks()
        assert len(infos) > 1
        assert [info.m_index for info in infos] == list(range(len(infos)))
        np.testing.assert_array_equal(document.read()[..., 0], expected)
    with czifile.CziFile(filepath) as reference:
        np.testing.assert_array_equal(np.squeeze(reference.asarray(maxworkers=1)), expected)


@contextmanager
def instrumented_document(monkeypatch, filepath):
    content = filepath.read_bytes()
    reads = []
    owners = []

    def read_at(offset, size):
        reads.append((offset, size))
        return content[offset : offset + size]

    @contextmanager
    def factory(*args, **kwargs):
        reader = czi.CziReader.__new__(czi.CziReader)
        reader._czi_reader = native.czi_reader._from_stream(read_at)
        reader._subblock_closed = False
        reader._subblock_catalog = None
        owners.append(reader)
        try:
            yield reader
        finally:
            reader.close()

    monkeypatch.setattr(czi, "open_czi", factory)
    with czi.CziDocument.open(filepath) as document:
        reads.clear()
        yield document, reads, owners
    assert len(owners) == 1
    assert owners[0]._subblock_closed


def test_facade_listings_and_ambiguous_selections_read_no_payloads(monkeypatch):
    with instrumented_document(monkeypatch, SYNTHETIC / "stored_levels_same_m37.czi") as (document, reads, _):
        assert document.list_subblocks()
        assert document.list_stored_levels()
        assert document.list_attachments() == []
        assert reads == []
        for m_index in (37, 987):
            with pytest.raises(ValueError):
                document.read_subblock_by_m(m_index)
        assert reads == []


@pytest.mark.parametrize("operation", ["tile", "xml", "level", "attachment_raw", "attachment_image"])
def test_facade_reads_only_selected_native_segment(monkeypatch, operation):
    filepath = SYNTHETIC / (
        "literal_slidepreview_cases.czi" if operation.startswith("attachment") else "stored_levels_same_m37.czi"
    )
    with czifile.CziFile(filepath) as reference:
        if operation.startswith("attachment"):
            attachment = next(reference.attachments())
            start = attachment.segment.offset
            end = start + 32 + attachment.segment.allocated_size
        else:
            entry = reference.subblock_directory[1]
            block = entry.read_segment_data(reference)
            start = entry.file_position
            end = start + 32 + block.segment.allocated_size
    with instrumented_document(monkeypatch, filepath) as (document, reads, _):
        if operation == "tile":
            result = document.read_subblock(1)
        elif operation == "xml":
            result = document.read_subblock_metadata_xml(1)
        elif operation == "level":
            level = next(item for item in document.list_stored_levels() if item.output_shape == (16, 24))
            result = document.read_stored_level(level.level_id)
        elif operation == "attachment_raw":
            result = document.read_attachment(0)
        else:
            result = document.read_attachment_image(0)
        assert result is not None
        assert reads
        assert all(start <= offset and offset + size <= end for offset, size in reads)


def test_closed_document_releases_its_backend():
    document = czi.CziDocument.open(SYNTHETIC / "literal_gray16_raw.czi")
    backend = weakref.ref(document._backend)
    pixels = document.read_subblock(0)
    document.close()
    gc.collect()
    assert backend() is None
    np.testing.assert_array_equal(pixels, literal_pixels())


def process_memory():
    from ctypes import wintypes

    values = _ProcessMemory()
    values.cb = ctypes.sizeof(values)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemory), wintypes.DWORD]
    if not get_info(get_process(), ctypes.byref(values), values.cb):
        raise ctypes.WinError()
    handles = wintypes.DWORD()
    get_handles = ctypes.windll.kernel32.GetProcessHandleCount
    get_handles.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    if not get_handles(get_process(), ctypes.byref(handles)):
        raise ctypes.WinError()
    return {
        **{name: getattr(values, name) for name in ("private", "working_set", "peak_working_set", "peak_pagefile")},
        "handles": handles.value,
    }


def resource_worker(case):
    filepath = SYNTHETIC / RESOURCE_CASES[case]
    with czifile.CziFile(filepath) as reference:
        if case == "listing":
            selected_storage = None
        elif case.startswith("attachment"):
            attachment = next(reference.attachments())
            selected_storage = {"encoded_attachment_bytes": len(attachment.data(raw=True))}
        else:
            entry = reference.subblock_directory[1 if case == "level" else 0]
            block = entry.read_segment_data(reference)
            selected_storage = {
                "encoded_pixel_bytes": block.data_size,
                "stored_shape": list(entry.stored_shape),
                "native_dimensions": entry.dims,
                "pixel_type": int(entry.pixel_type),
                "compression_mode": int(entry.compression),
            }

    def cycle():
        with czi.CziDocument.open(filepath, cache_options=None) as document:
            if case == "tile":
                result = document.read_subblock(0)
            elif case.startswith("xml"):
                result = document.read_subblock_metadata_xml(0)
            elif case == "mask":
                result = document.read_subblock_mask(0)
            elif case == "level":
                level = next(item for item in document.list_stored_levels() if item.output_shape == (16, 24))
                result = document.read_stored_level(level.level_id)
            elif case == "attachment_raw":
                result = document.read_attachment(0)
            elif case == "attachment_image":
                result = document.read_attachment_image(0)
            else:
                result = (document.list_subblocks(), document.list_stored_levels(), document.list_attachments())
        document.close()
        assert document.closed
        return result

    for iteration in range(10):
        output = cycle()
        del output
    gc.collect()
    samples = [process_memory() for iteration in range(100)]
    peaks = [0] * 100
    baseline = process_memory()
    tracemalloc.start()
    for iteration in range(100):
        before = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        output = cycle()
        peaks[iteration] = tracemalloc.get_traced_memory()[1] - before
        if iteration == 0:
            payload = (
                output.tobytes()
                if isinstance(output, np.ndarray)
                else output.encode("utf8") if isinstance(output, str) else output if isinstance(output, bytes) else b""
            )
            output_info = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "shape": list(output.shape) if isinstance(output, np.ndarray) else None,
                "dtype": str(output.dtype) if isinstance(output, np.ndarray) else None,
            }
            del payload
        del output
        gc.collect()
        samples[iteration] = process_memory()
    tracemalloc.stop()
    assert samples[-1]["handles"] <= baseline["handles"]
    first = sum(item["private"] for item in samples[:20]) / 20
    last = sum(item["private"] for item in samples[-20:]) / 20
    return {
        "case": case,
        "fixture": str(filepath),
        "fixture_sha256": hashlib.sha256(filepath.read_bytes()).hexdigest(),
        "fixture_bytes": filepath.stat().st_size,
        "selected_storage": selected_storage,
        "python": sys.executable,
        "api": czi.__file__,
        "native": native.__file__,
        "cache": None,
        "warmup_cycles": 10,
        "measured_cycles": 100,
        "released_outputs": True,
        "baseline": baseline,
        "samples": samples,
        "output": output_info,
        "released_private_first20_mean": first,
        "released_private_last20_mean": last,
        "released_private_growth": last - first,
        "python_peak_increment_max": max(peaks),
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows private/peak-memory evidence; other OS certification is separate")
@pytest.mark.parametrize("case", RESOURCE_CASES)
def test_repeated_read_close_resource_protocol(case, tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(czi.__file__).resolve().parent.parent)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--resource-worker", case],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    record = json.loads(result.stdout)
    assert record["measured_cycles"] == 100
    assert Path(record["api"]).resolve() == Path(czi.__file__).resolve()
    assert Path(record["python"]).resolve() == Path(sys.executable).resolve()
    evidence_dir = os.environ.get("CZIRW_RESOURCE_EVIDENCE_DIR")
    if evidence_dir:
        destination = Path(evidence_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / f"{case}.json").write_text(json.dumps(record, indent=2), encoding="utf8")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--resource-worker":
        raise SystemExit("Expected --resource-worker CASE")
    print(json.dumps(resource_worker(sys.argv[2])))
