"""Contract and integration tests for the single-owner document facade."""

import inspect
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, NoReturn, Optional, Union
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest

# Package-owned private/native API intentionally exercised.
# pylint: disable-next=import-private-name
import _pylibCZIrw as native
from pylibCZIrw import czi

READ_METHODS = (
    "read",
    "list_subblocks",
    "read_subblock",
    "read_subblock_by_m",
    "read_subblock_metadata_xml",
    "read_subblock_mask",
    "list_stored_levels",
    "read_stored_level",
    "list_attachments",
    "read_attachment",
    "read_attachment_image",
    "read_label",
    "read_preview",
)
WRITE_METHODS = ("write", "write_metadata")
EDIT_METHODS = ("read_metadata_xml", "edit_session")
DATA = Path(__file__).resolve().parent / "test_data"
CALLS: dict[str, tuple[dict[str, object]]] = {
    "read": ({},),
    "list_subblocks": ({},),
    "read_subblock": ({"index": 3},),
    "read_subblock_by_m": ({"m_index": 7},),
    "read_subblock_metadata_xml": ({"index": 3},),
    "read_subblock_mask": ({"index": 3},),
    "list_stored_levels": ({},),
    "read_stored_level": ({"level": 4},),
    "list_attachments": ({},),
    "read_attachment": ({"index": 2},),
    "read_attachment_image": ({"index": 2},),
    "read_label": ({},),
    "read_preview": ({},),
    "write": ({"data": object()},),
    "write_metadata": ({},),
    "read_metadata_xml": ({},),
    "edit_session": ({},),
}


def assert_document_state(
    document: czi.CziDocument, *, mode: Optional[str] = None, closed: Optional[bool] = None
) -> None:
    """Check observable state without retaining narrowings across lifecycle calls."""
    if mode is not None:
        assert document.mode == mode
    if closed is not None:
        assert document.closed is closed


def owned_backend(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    backend: Optional[Mock] = None,
    cleanup_error: Optional[Exception] = None,
) -> tuple[czi.CziDocument, Mock, list[object]]:
    """Return a document with an instrumented mock owner and lifecycle events."""
    backend = backend if backend is not None else Mock()
    events: list[object] = []

    @contextmanager
    def factory(*args: object, **kwargs: object) -> Iterator[Mock]:
        """Record one acquisition and finalization of the selected mock."""
        events.append(("open", args, kwargs))
        try:
            yield backend
        finally:
            events.append("close")
            if cleanup_error is not None:
                raise cleanup_error

    factory_name = {"r": "open_czi", "w": "create_czi", "edit": "edit_czi"}[mode]
    monkeypatch.setattr(czi, factory_name, factory)
    method = {"r": "open", "w": "create", "edit": "edit"}[mode]
    return getattr(czi.CziDocument, method)("document.czi"), backend, events


def test_open_owns_one_factory_and_closes_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify open owns one factory and closes once."""
    events: list[object] = []
    backend = object()
    filepath = tmp_path / "document.czi"

    @contextmanager
    def factory(
        path: str,
        file_input_type: czi.ReaderFileInputTypes,
        cache_options: Optional[czi.CacheOptions],
        *,
        reader_options: Optional[czi.ReaderOptions],
    ) -> Iterator[object]:
        """Record the exact reader factory arguments and finalization."""
        events.append(("open", path, file_input_type, cache_options, reader_options))
        try:
            yield backend
        finally:
            events.append("close")

    monkeypatch.setattr(czi, "open_czi", factory)
    document = czi.CziDocument.open(filepath)
    assert_document_state(document, mode="r", closed=False)
    with document as entered:
        assert entered is document
        document.close()
        document.close()
    assert_document_state(document, closed=True)
    assert events == [("open", str(filepath), czi.ReaderFileInputTypes.Standard, None, None), "close"]
    with pytest.raises(RuntimeError, match="closed"):
        # Explicit entry verifies the deferred context-manager lifecycle.
        # pylint: disable-next=unnecessary-dunder-call
        document.__enter__()


@pytest.mark.parametrize(
    "backend,names", [(czi.CziReader, READ_METHODS), (czi.CziWriter, WRITE_METHODS), (czi.CziEditor, EDIT_METHODS)]
)
def test_delegate_signatures_are_exact(
    backend: Union[type[czi.CziEditor], type[czi.CziReader], type[czi.CziWriter]], names: tuple[str, ...]
) -> None:
    """Verify delegate signatures are exact."""
    for name in names:
        assert inspect.signature(getattr(czi.CziDocument, name)) == inspect.signature(getattr(backend, name))


@pytest.mark.parametrize(
    "mode,owner,names",
    [
        ("r", czi.CziReader, READ_METHODS),
        ("w", czi.CziWriter, WRITE_METHODS),
        ("edit", czi.CziEditor, ("read_metadata_xml",)),
    ],
)
def test_delegates_preserve_arguments_results_and_errors(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    owner: Union[type[czi.CziEditor], type[czi.CziReader], type[czi.CziWriter]],
    names: tuple[str, ...],
) -> None:
    """Verify delegates preserve arguments results and errors."""
    document, backend, events = owned_backend(monkeypatch, mode)
    for name in names:
        delegate = getattr(backend, name)
        result = object()
        delegate.return_value = result
        assert getattr(document, name)(**CALLS[name][0]) is result
        signature = inspect.signature(getattr(owner, name))
        expected = signature.bind(backend, **CALLS[name][0])
        actual = signature.bind(backend, *delegate.call_args.args, **delegate.call_args.kwargs)
        expected.apply_defaults()
        actual.apply_defaults()
        assert actual.arguments == expected.arguments
        failure = LookupError(name)
        delegate.side_effect = failure
        with pytest.raises(LookupError) as caught:
            getattr(document, name)(**CALLS[name][0])
        assert caught.value is failure
    assert len(events) == 1
    document.close()
    assert len(events) == 2


@pytest.mark.parametrize("mode,names", [("r", READ_METHODS), ("w", WRITE_METHODS), ("edit", EDIT_METHODS)])
def test_wrong_mode_and_closed_dispatch(monkeypatch: pytest.MonkeyPatch, mode: str, names: tuple[str, ...]) -> None:
    """Verify wrong mode and closed dispatch."""
    document, backend, events = owned_backend(monkeypatch, mode)
    for name in READ_METHODS + WRITE_METHODS + EDIT_METHODS:
        if name in names:
            continue
        with pytest.raises(ValueError, match=f"{name}.*{mode}"):
            result = getattr(document, name)(**CALLS[name][0])
            if name == "edit_session":
                # Explicit entry verifies the deferred context-manager lifecycle.
                # pylint: disable-next=unnecessary-dunder-call
                result.__enter__()
    assert backend.mock_calls == []
    document.close()
    for name in READ_METHODS + WRITE_METHODS + EDIT_METHODS:
        with pytest.raises(RuntimeError, match="closed"):
            result = getattr(document, name)(**CALLS[name][0])
            if name == "edit_session":
                # Explicit entry verifies the deferred context-manager lifecycle.
                # pylint: disable-next=unnecessary-dunder-call
                result.__enter__()
    assert len(events) == 2


@pytest.mark.parametrize("mode", ["r", "w", "edit"])
def test_context_body_and_cleanup_exceptions(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Verify context body and cleanup exceptions."""
    cleanup_error = OSError("cleanup failed")
    document, _, events = owned_backend(monkeypatch, mode, cleanup_error=cleanup_error)
    body_error = LookupError("body failed")
    with pytest.raises(LookupError) as caught:
        with document:
            raise body_error
    assert caught.value is body_error
    assert caught.value.__cause__ is cleanup_error
    assert document.closed
    document.close()
    assert len(events) == 2


def test_nested_context_and_read_only_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify nested context and read only state."""
    document, _, events = owned_backend(monkeypatch, "r")
    for name in ("mode", "closed"):
        with pytest.raises(AttributeError):
            setattr(document, name, "different")
    for name in ("reader", "writer", "editor", "unknown_operation"):
        with pytest.raises(AttributeError):
            getattr(document, name)
    with document:
        with pytest.raises(RuntimeError, match="already entered"):
            # Explicit entry verifies the deferred context-manager lifecycle.
            # pylint: disable-next=unnecessary-dunder-call
            document.__enter__()
    assert len(events) == 2


@pytest.mark.parametrize("factory", ["open", "create", "edit"])
@pytest.mark.parametrize("path", [b"image.czi", 42, None])
def test_invalid_paths_do_not_acquire(
    monkeypatch: pytest.MonkeyPatch, factory: str, path: Union[None, bytes, int]
) -> None:
    """Verify invalid paths do not acquire."""
    opener = Mock(side_effect=AssertionError("Must validate before acquiring"))
    monkeypatch.setattr(czi, "open_czi", opener)
    monkeypatch.setattr(czi, "create_czi", opener)
    monkeypatch.setattr(czi, "edit_czi", opener)
    with pytest.raises(TypeError):
        getattr(czi.CziDocument, factory)(path)
    opener.assert_not_called()


@pytest.mark.parametrize("factory", ["open", "create", "edit"])
def test_local_factories_reject_urls_before_acquiring(monkeypatch: pytest.MonkeyPatch, factory: str) -> None:
    """Verify local factories reject urls before acquiring."""
    opener = Mock(side_effect=AssertionError("Must reject a URL before acquiring"))
    monkeypatch.setattr(czi, "open_czi", opener)
    monkeypatch.setattr(czi, "create_czi", opener)
    monkeypatch.setattr(czi, "edit_czi", opener)
    with pytest.raises(ValueError, match="URL|local|Curl"):
        getattr(czi.CziDocument, factory)("https://example.org/image.czi")
    opener.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        {"file_input_type": "curl"},
        {"cache_options": {}},
        {"reader_options": {}},
    ],
)
def test_reader_option_types_are_checked_before_acquiring(
    monkeypatch: pytest.MonkeyPatch, options: dict[str, object]
) -> None:
    """Verify reader option types are checked before acquiring."""
    opener = Mock(side_effect=AssertionError("Must validate before acquiring"))
    monkeypatch.setattr(czi, "open_czi", opener)
    pytest.raises(TypeError, czi.CziDocument.open, "image.czi", **options)
    opener.assert_not_called()


@pytest.mark.parametrize("options", [{"exist_ok": 1}, {"compression_options": False}])
def test_writer_option_types_are_checked_before_acquiring(
    monkeypatch: pytest.MonkeyPatch, options: dict[str, Union[bool, int]]
) -> None:
    """Verify writer option types are checked before acquiring."""
    opener = Mock(side_effect=AssertionError("Must validate before acquiring"))
    monkeypatch.setattr(czi, "create_czi", opener)
    pytest.raises(TypeError, czi.CziDocument.create, "image.czi", **options)
    opener.assert_not_called()


def test_edit_session_cannot_commit_after_document_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify edit session cannot commit after document close."""
    backend = Mock()
    builder = object()
    commits = []

    @contextmanager
    def session() -> Iterator[object]:
        """Commit only after the borrowed session exits normally."""
        yield builder
        commits.append("commit")

    backend.edit_session = session
    document, _, _ = owned_backend(monkeypatch, "edit", backend)
    with pytest.raises(RuntimeError, match="closed"):
        with document.edit_session() as returned:
            assert returned is builder
            document.close()
    assert not commits


@pytest.mark.parametrize("mode", ["r", "w", "edit"])
def test_edit_session_checks_state_at_call_time(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Verify edit session checks state at call time."""
    document, backend, _ = owned_backend(monkeypatch, mode)
    if mode != "edit":
        with pytest.raises(ValueError, match="edit_session"):
            document.edit_session()
    document.close()
    with pytest.raises(RuntimeError, match="closed"):
        document.edit_session()
    assert backend.mock_calls == []


def test_session_created_before_close_cannot_enter_later(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify session created before close cannot enter later."""
    document, backend, _ = owned_backend(monkeypatch, "edit")
    session = document.edit_session()
    document.close()
    with pytest.raises(RuntimeError, match="closed"):
        # Explicit entry verifies the deferred context-manager lifecycle.
        # pylint: disable-next=unnecessary-dunder-call
        session.__enter__()
    assert backend.mock_calls == []


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_native_reader_initialization_failure_cleans_up(monkeypatch: pytest.MonkeyPatch, cleanup_fails: bool) -> None:
    """Verify native reader initialization failure cleans up."""
    acquisition_error = OSError("directory statistics failed")
    cleanup_error = OSError("native close failed")
    native_reader = Mock()
    native_reader.GetSubBlockStats.side_effect = acquisition_error
    if cleanup_fails:
        native_reader.close.side_effect = cleanup_error
    monkeypatch.setattr(native, "czi_reader", Mock(return_value=native_reader))
    with pytest.raises(OSError) as caught:
        czi.CziDocument.open("image.czi")
    assert caught.value is acquisition_error
    native_reader.close.assert_called_once_with()
    if cleanup_fails:
        assert caught.value.__cause__ is cleanup_error


def test_curl_and_option_identity_are_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify curl and option identity are forwarded."""
    received = []

    @contextmanager
    def factory(*args: object, **kwargs: object) -> Iterator[object]:
        """Record unchanged curl/cache/reader options."""
        received.append((args, kwargs))
        yield object()

    monkeypatch.setattr(czi, "open_czi", factory)
    cache = czi.CacheOptions(max_memory_usage=65536, max_sub_block_count=2)
    options = czi.ReaderOptions(enable_mask_awareness=True)
    url = "https://example.org/image.czi"
    with czi.CziDocument.open(
        url, file_input_type=czi.ReaderFileInputTypes.Curl, cache_options=cache, reader_options=options
    ):
        pass
    assert received == [
        ((url,), {"file_input_type": czi.ReaderFileInputTypes.Curl, "cache_options": cache, "reader_options": options})
    ]
    assert received[0][1]["cache_options"] is cache
    assert received[0][1]["reader_options"] is options


@pytest.mark.parametrize("path", ["image.czi", Path("image.czi"), "not a URL"])
def test_curl_rejects_local_paths_before_acquisition(monkeypatch: pytest.MonkeyPatch, path: Union[str, Path]) -> None:
    """Verify curl rejects local paths before acquisition."""
    opener = Mock(side_effect=AssertionError("Must reject before acquiring"))
    monkeypatch.setattr(czi, "open_czi", opener)
    with pytest.raises(ValueError, match="URL"):
        czi.CziDocument.open(path, file_input_type=czi.ReaderFileInputTypes.Curl)
    opener.assert_not_called()


@pytest.mark.parametrize("mode", ["r", "w", "edit"])
def test_cleanup_only_failure_is_terminal(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Verify cleanup only failure is terminal."""
    failure = OSError("finalization failed")
    document, _, events = owned_backend(monkeypatch, mode, cleanup_error=failure)
    with pytest.raises(OSError) as caught:
        with document:
            pass
    assert caught.value is failure
    assert document.closed
    document.close()
    assert len(events) == 2


@pytest.mark.parametrize("mode", ["r", "w", "edit"])
def test_body_exception_is_not_suppressed(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Verify body exception is not suppressed."""
    document, _, events = owned_backend(monkeypatch, mode)
    failure = LookupError("body failed")
    with pytest.raises(LookupError) as caught:
        with document:
            raise failure
    assert caught.value is failure
    assert document.closed
    assert len(events) == 2


def test_public_factory_boundaries() -> None:
    """Verify public factory boundaries."""
    assert list(inspect.signature(czi.CziDocument.open).parameters) == [
        "filepath",
        "file_input_type",
        "cache_options",
        "reader_options",
    ]
    assert list(inspect.signature(czi.CziDocument.create).parameters) == ["filepath", "exist_ok", "compression_options"]
    assert list(inspect.signature(czi.CziDocument.edit).parameters) == ["filepath"]
    for factory_name in ("open", "create", "edit"):
        factory = getattr(czi.CziDocument, factory_name)
        for name, parameter in inspect.signature(factory).parameters.items():
            assert parameter.kind is (
                inspect.Parameter.POSITIONAL_OR_KEYWORD if name == "filepath" else inspect.Parameter.KEYWORD_ONLY
            )
        pytest.raises(TypeError, factory, "image.czi", mode="r+")
    pytest.raises(TypeError, czi.CziDocument)


def test_real_create_read_edit_and_safe_overwrite(tmp_path: Path) -> None:
    """Verify real create read edit and safe overwrite."""
    filepath = tmp_path / "nested" / "workflow.czi"
    expected = (257 * np.arange(32)[:, None] + 11 * np.arange(48)[None, :]).astype(np.uint16)
    with czi.CziDocument.create(filepath) as document:
        assert_document_state(document, mode="w", closed=False)
        assert document.write(expected[..., None], location=(-10, 5)) is True
        document.write_metadata(document_name="Before edit", scale_x=0.25, scale_y=0.5)
    original = filepath.read_bytes()
    with pytest.raises(FileExistsError):
        czi.CziDocument.create(filepath)
    assert filepath.read_bytes() == original
    with czi.CziDocument.open(filepath) as document:
        info = document.list_subblocks()[0]
        retained = document.read_subblock(info.index)
        np.testing.assert_array_equal(document.read(scene=0)[..., 0], expected)
        assert info.logical_rect == (-10, 5, 48, 32)
    np.testing.assert_array_equal(retained, expected)
    with czi.CziDocument.edit(filepath) as document:
        assert_document_state(document, mode="edit", closed=False)
        assert "Before edit" in document.read_metadata_xml()
        with document.edit_session() as builder:
            assert isinstance(builder, czi.CziMetadataBuilder)
            builder.set_general_document_info(name="After edit")
    with czi.edit_czi(str(filepath)) as editor:
        assert editor.read_general_document_info()["name"] == "After edit"
        assert editor.read_scaling_info().scale_x == 0.25
    with czi.CziDocument.create(filepath, exist_ok=True) as document:
        document.write(np.zeros((2, 3, 1), dtype=np.uint8))
    with czi.open_czi(str(filepath)) as reader:
        assert reader.read().shape == (2, 3, 1)


def test_failed_edit_session_does_not_commit(tmp_path: Path) -> None:
    """Verify failed edit session does not commit."""
    filepath = tmp_path / "session.czi"
    with czi.create_czi(str(filepath)) as writer:
        writer.write(np.zeros((2, 3, 1), dtype=np.uint8))
        writer.write_metadata(document_name="Original")
    with czi.CziDocument.edit(filepath) as document:
        original_metadata = document.read_metadata_xml()
        with pytest.raises(LookupError):
            with document.edit_session() as builder:
                builder.set_general_document_info(name="Not committed")
                raise LookupError("cancel")
    with czi.edit_czi(str(filepath)) as editor:
        assert editor.read_metadata_xml() == original_metadata


def test_real_writer_finalizes_on_exception(tmp_path: Path) -> None:
    """Verify real writer finalizes on exception."""
    filepath = tmp_path / "partial.czi"
    expected = np.arange(24, dtype=np.uint8).reshape(4, 6, 1)
    with pytest.raises(LookupError):
        with czi.CziDocument.create(filepath) as document:
            document.write(expected)
            raise LookupError("body failure does not roll back")
    with czi.open_czi(str(filepath)) as reader:
        np.testing.assert_array_equal(reader.read(), expected)


@pytest.mark.parametrize("factory", ["open", "edit"])
def test_missing_files_fail_at_factory_call(tmp_path: Path, factory: str) -> None:
    """Verify missing files fail at factory call."""
    filepath = tmp_path / "missing.czi"
    legacy = getattr(czi, f"{factory}_czi")
    with pytest.raises(RuntimeError) as baseline:
        with legacy(str(filepath)):
            pass
    assert not filepath.exists()
    with pytest.raises(type(baseline.value)) as caught:
        getattr(czi.CziDocument, factory)(filepath)
    assert str(caught.value) == str(baseline.value)
    assert not filepath.exists()


def test_writer_finalization_failure_closes_native_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify failed metadata finalization closes its native writer once."""
    failure = OSError("metadata finalization failed")
    closes = []
    original_close = native.czi_writer.close

    def close(native_writer: native.czi_writer) -> None:
        """Record and perform the actual native close."""
        closes.append("close")
        return original_close(native_writer)

    def fail_metadata(writer: czi.CziWriter, *args: object, **kwargs: object) -> NoReturn:
        """Fail before metadata finalization can complete."""
        raise failure

    monkeypatch.setattr(native.czi_writer, "close", close)
    monkeypatch.setattr(czi.CziWriter, "write_metadata", fail_metadata)
    document = czi.CziDocument.create(tmp_path / "failed-finalization.czi")
    document.write(np.zeros((2, 3, 1), dtype=np.uint8))
    with pytest.raises(OSError) as caught:
        document.close()
    assert caught.value is failure
    assert document.closed
    document.close()
    assert closes == ["close"]


@pytest.mark.parametrize("failure", [FileNotFoundError("missing"), FileExistsError("exists"), OSError("I/O")])
def test_factory_domain_errors_are_not_translated(monkeypatch: pytest.MonkeyPatch, failure: OSError) -> None:
    """Verify factory domain errors are not translated."""
    factory = MagicMock()
    factory.return_value.__enter__.side_effect = failure
    monkeypatch.setattr(czi, "open_czi", factory)
    with pytest.raises(type(failure)) as caught:
        czi.CziDocument.open("image.czi")
    assert caught.value is failure
    factory.return_value.__exit__.assert_not_called()
