"""Tests for exact-byte fixture verification and the pytest startup gate."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ..conftest import verify_fixture_manifest


@pytest.fixture
def sample_manifest(tmp_path: Path) -> tuple[Path, Path]:
    payload = b"fixture\x00bytes\r\n"
    (tmp_path / "sample.bin").write_bytes(payload)
    (tmp_path / "alias.bin").write_bytes(payload)
    manifest_path = tmp_path / "fixture_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "assets": [
                    {
                        "id": "sample",
                        "path": "sample.bin",
                        "aliases": ["alias.bin"],
                        "size_bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest().upper(),
                    }
                ],
                "inventory_scope": {
                    "unique_assets": 1,
                    "paths_including_aliases": 2,
                    "bytes_including_aliases": 2 * len(payload),
                },
            }
        ),
        encoding="utf-8",
    )
    return tmp_path, manifest_path


def test_verify_fixture_manifest(sample_manifest: tuple[Path, Path]) -> None:
    verify_fixture_manifest(*sample_manifest)


@pytest.mark.parametrize("filename", ["sample.bin", "alias.bin"])
def test_reject_changed_bytes(sample_manifest: tuple[Path, Path], filename: str) -> None:
    root, manifest_path = sample_manifest
    filepath = root / filename
    filepath.write_bytes(filepath.read_bytes().replace(b"fixture", b"changed"))
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_missing_fixture(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    (root / "sample.bin").unlink()
    with pytest.raises(ValueError, match="Cannot read fixture"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_size_change(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    (root / "sample.bin").write_bytes(b"short")
    with pytest.raises(ValueError, match="size mismatch"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_newline_conversion(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    filepath = root / "sample.bin"
    filepath.write_bytes(filepath.read_bytes().replace(b"\r\n", b"\n"))
    with pytest.raises(ValueError, match="size mismatch"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_invalid_json(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    manifest_path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read fixture manifest"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_unknown_schema(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported fixture manifest schema"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_path_escape(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["path"] = "../outside.bin"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid fixture path"):
        verify_fixture_manifest(root, manifest_path)


def test_reject_inconsistent_inventory(sample_manifest: tuple[Path, Path]) -> None:
    root, manifest_path = sample_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inventory_scope"]["bytes_including_aliases"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory counts"):
        verify_fixture_manifest(root, manifest_path)


@pytest.mark.parametrize("discovery", ["file", "root"])
def test_session_rejects_corruption_before_collection(sample_manifest: tuple[Path, Path], discovery: str) -> None:
    root, manifest_path = sample_manifest
    test_dir = root / "pylibCZIrw" / "tests"
    data_dir = test_dir / "integration" / "test_data"
    data_dir.mkdir(parents=True)
    shutil.copyfile(manifest_path, data_dir / "fixture_manifest.json")
    shutil.copyfile(Path(__file__).resolve().parents[1] / "conftest.py", test_dir / "conftest.py")
    test_path = test_dir / "test_never_collected.py"
    test_path.write_text('raise RuntimeError("TEST COLLECTION REACHED")\n', encoding="utf-8")
    (root / "sample.bin").unlink()
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "--import-mode=importlib",
            "-q",
            str(test_path if discovery == "file" else root),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (pytest.ExitCode.USAGE_ERROR, pytest.ExitCode.INTERRUPTED)
    assert "Fixture integrity check failed" in result.stdout + result.stderr
    assert "TEST COLLECTION REACHED" not in result.stdout + result.stderr


@pytest.fixture(scope="module")
def assignment_records() -> tuple[dict, dict]:
    root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (root / "pylibCZIrw/tests/integration/test_data/fixture_manifest.json").read_text(encoding="utf-8")
    )
    evidence = next(record for record in manifest["reference_audits"] if record["id"] == "fixture-refresh-20261015")
    content = (root / evidence["path"]).read_bytes()
    assert len(content) == evidence["size_bytes"]
    assert hashlib.sha256(content).hexdigest().upper() == evidence["sha256"]
    report = json.loads(content)
    for source in report["source_review"]["sources"]:
        content = source["source_utf8"].encode("utf-8")
        assert len(content) == source["size_bytes"]
        assert hashlib.sha256(content).hexdigest().upper() == source["sha256"]
    return manifest, report


@pytest.mark.parametrize("case_id", ["C01", "C02", "C03", "C04", "C05", "C06", "C07"])
def test_case_assignments_have_references_not_implementation_passes(
    assignment_records: tuple[dict, dict], case_id: str
) -> None:
    manifest, report = assignment_records
    assets = {asset["id"]: asset for asset in manifest["assets"]}
    group = next(group for group in manifest["required_case_groups"] if group["id"] == case_id)
    assignment = report["case_assignments"][case_id]
    assert group["assignment_state"] == assignment["assignment_state"] == "complete"
    if case_id == "C07":
        assert assignment["reference_state"] == "blocked"
        assert group["state"] == "reference-verified"
        assert group["reference_scope_decision"] == manifest["corpus_policy"]["id"]
    else:
        assert group["state"] == assignment["reference_state"]
    expected_runs = [report["id"]]
    if case_id == "C07":
        expected_runs.append("legacy-reference-review-20261015")
    assert group["reference_runs"] == expected_runs
    assert group["implementation_runs"] == assignment["implementation_runs"] == []
    assert assignment["implementation_state"] == "not-evaluated"
    assert group["expected_results"]["pointer"] == f"/case_assignments/{case_id}"
    expected_assets = {asset_id for variant in assignment["variants"] for asset_id in variant["asset_ids"]}
    assert set(group["asset_ids"]) == expected_assets
    assert len({variant["id"] for variant in assignment["variants"]}) == len(assignment["variants"])
    for asset_id in expected_assets:
        assert assets[asset_id]["admission"] == "admitted"
        assert case_id in assets[asset_id]["case_ids"]
    for variant in assignment["variants"]:
        assert variant["asset_ids"] and variant["expected"]
        assert variant["implementation_state"] == "not-evaluated"


def test_raw_coordinate_and_compression_references(assignment_records: tuple[dict, dict]) -> None:
    manifest, report = assignment_records
    generated = {asset["id"]: asset for asset in report["generated_assets"]}
    assert generated["asset-044"]["subblocks"][0]["compression"] == 42
    assert generated["asset-056"]["subblocks"][0]["coordinates"] == {
        "X": -8,
        "Y": -4,
        "M": 37,
        "S": 2,
        "T": 3,
        "C": 5,
        "Z": 7,
    }
    assert [attachment["name"] for attachment in generated["asset-050"]["attachments"]] == [
        "Label",
        "SlidePreview",
        "SlidePreview",
        "Unknown",
        "Corrupt",
    ]
    assert report["case_assignments"]["C07"]["reference_state"] == "blocked"
    approval = next(
        record for record in manifest["privacy_decisions"] if record["id"] == "existing-fixture-reuse-20261015"
    )
    assert not set(approval["asset_ids"]) & generated.keys()
    for asset in manifest["assets"]:
        if asset["id"] in generated:
            assert asset["privacy"]["state"] == "reference-verified"


def test_historical_review_does_not_promote_unknown_history_or_formatting(
    assignment_records: tuple[dict, dict],
) -> None:
    manifest, _ = assignment_records
    root = Path(__file__).resolve().parents[3]
    evidence = next(
        record for record in manifest["reference_audits"] if record["id"] == "legacy-reference-review-20261015"
    )
    content = (root / evidence["path"]).read_bytes()
    assert len(content) == evidence["size_bytes"]
    assert hashlib.sha256(content).hexdigest().upper() == evidence["sha256"]
    report = json.loads(content)
    for source in report["sources"]:
        content = source["source_utf8"].encode("utf-8")
        assert len(content) == source["size_bytes"]
        assert hashlib.sha256(content).hexdigest().upper() == source["sha256"]
    cases = report["independent_results"]["cases"]
    pixels = [case for case in cases if case["id"].startswith("legacy-pixels-")]
    xml = [case for case in cases if case["id"].startswith("legacy-XML-")]
    assert len(pixels) == 3 and len(xml) == 6
    assert all(case["state"] == "reference-verified" for case in cases)
    assert all(case["expected_sha256"] == case["actual_sha256"] for case in pixels)
    assert all(case["semantic_match"] and not case["exact_bytes"] for case in xml)
    assert all(case["exact_native_text_oracle"] == "unverified" for case in xml)
    assert report["public_projection"]["not_original_record"]
    assert not report["public_projection"]["embedded_helpers_reexecuted"]
    assert manifest["public_projection"]["not_original_record"]
    assert not manifest["public_projection"]["fixture_bytes_changed"]
    assert not manifest["public_projection"]["reference_states_promoted"]
    policy = manifest["corpus_policy"]
    assert policy["existing_history_not_reconstructed"]
    assert not policy["release_or_distribution_approval"]
    assert manifest["asset_defaults"]["origin"]["original_source"] is None
    assert manifest["asset_defaults"]["origin"]["creation_recipe"] is None
    assert manifest["status"] == "public-regression-corpus"
    assert "provenance_scope_decision" not in manifest
    assert "completion" not in manifest
    assert all(group["state"] == "reference-verified" for group in manifest["required_case_groups"])
    assert all(group["implementation_runs"] == [] for group in manifest["required_case_groups"])
    assert manifest["network_evidence"]["remote_fixture_identity_and_rights"].startswith("unverified")
    assert manifest["network_evidence"]["invalid_certificate_rejection"] == "unverified"
    assert manifest["public_projection"]["internal_approval_records_omitted"]
