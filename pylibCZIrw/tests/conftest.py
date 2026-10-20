"""Verify the versioned fixture inventory before collecting tests."""

import hashlib
import json
import re
from pathlib import Path

import pytest


def verify_fixture_manifest(root: Path, manifest_path: Path) -> None:
    """Reject missing, changed or malformed active fixture records."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read fixture manifest {manifest_path}: {exc}") from exc

    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported fixture manifest schema")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("Fixture manifest has no active assets")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    total_bytes = 0
    root = root.resolve()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Invalid fixture asset record")
        asset_id = asset.get("id")
        aliases = asset.get("aliases")
        expected_size = asset.get("size_bytes")
        expected_hash = asset.get("sha256")
        if not isinstance(asset_id, str) or not asset_id or asset_id in seen_ids:
            raise ValueError(f"Invalid or duplicate fixture ID: {asset_id}")
        seen_ids.add(asset_id)
        if not isinstance(aliases, list):
            raise ValueError(f"Invalid fixture aliases: {asset_id}")
        if type(expected_size) is not int or expected_size < 0:
            raise ValueError(f"Invalid fixture size: {asset_id}")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
            raise ValueError(f"Invalid fixture SHA256: {asset_id}")

        for relative in [asset.get("path"), *aliases]:
            if not isinstance(relative, str) or not relative or "\\" in relative:
                raise ValueError(f"Invalid fixture path: {relative}")
            filepath = (root / relative).resolve()
            if Path(relative).is_absolute() or ".." in Path(relative).parts or not filepath.is_relative_to(root):
                raise ValueError(f"Invalid fixture path: {relative}")
            if relative in seen_paths:
                raise ValueError(f"Duplicate fixture path: {relative}")
            seen_paths.add(relative)
            try:
                size = filepath.stat().st_size
                if size != expected_size:
                    raise ValueError(f"Fixture size mismatch: {relative}; expected {expected_size}, got {size}")
                digest = hashlib.sha256()
                with filepath.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
            except OSError as exc:
                raise ValueError(f"Cannot read fixture {relative}: {exc}") from exc
            if digest.hexdigest().upper() != expected_hash.upper():
                raise ValueError(f"Fixture SHA256 mismatch: {relative}")
            total_bytes += size

    expected_inventory = {
        "unique_assets": len(seen_ids),
        "paths_including_aliases": len(seen_paths),
        "bytes_including_aliases": total_bytes,
    }
    inventory = manifest.get("inventory_scope")
    if not isinstance(inventory, dict) or any(inventory.get(key) != value for key, value in expected_inventory.items()):
        raise ValueError("Fixture inventory counts do not match active assets")


def pytest_configure() -> None:
    """Fail before collection rather than running against unverified bytes."""
    test_dir = Path(__file__).resolve().parent
    try:
        verify_fixture_manifest(test_dir.parents[1], test_dir / "integration" / "test_data" / "fixture_manifest.json")
    except ValueError as exc:
        raise pytest.UsageError(f"Fixture integrity check failed: {exc}") from exc
