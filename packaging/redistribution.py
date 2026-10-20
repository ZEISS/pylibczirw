"""Assemble and verify an internal native source/review handoff, not legal clearance."""

import argparse
import hashlib
import json
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path: Path) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"size_bytes": path.stat().st_size, "sha256": digest}


def safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts or ":" in name:
        raise ValueError(f"Unsafe archive path: {name!r}")


def verify(archive_path: Path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError("Duplicate or case-colliding archive members.")
        for name in names:
            safe_name(name)
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["redistribution_cleared"] is not False or manifest["g1_approved"] is not False:
            raise ValueError("This tool cannot grant redistribution or G1 approval.")
        expected = manifest["files"]
        if set(names) != set(expected) | {"manifest.json"}:
            raise ValueError("Archive members differ from the manifest.")
        for name, record in expected.items():
            with archive.open(name) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != record["sha256"] or archive.getinfo(name).file_size != record["size_bytes"]:
                raise ValueError(f"Archive bytes differ: {name}")
    print(f"Verified {len(expected)} files; redistribution and G1 remain unapproved.")
    return manifest


def prepare(specification: Path, destination: Path) -> Path:
    destination = destination.resolve()
    if destination.is_relative_to(ROOT):
        raise ValueError("Source handoff evidence must live outside the checkout.")
    spec = json.loads(specification.read_text(encoding="utf8"))
    identifiers = [item["id"] for item in spec["inputs"]]
    if len(identifiers) != len(set(identifier.casefold() for identifier in identifiers)):
        raise ValueError("Duplicate input identifiers.")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identifier) for identifier in identifiers):
        raise ValueError("Input identifiers must be simple path components.")
    destination.mkdir(parents=True, exist_ok=False)
    payload = destination / "payload"
    payload.mkdir()
    inputs = []
    for item in spec["inputs"]:
        record = dict(item)
        target = payload / item["id"]
        target.mkdir()
        if item["kind"] == "https":
            url = urllib.parse.urlsplit(item["source"])
            if url.scheme != "https" or url.username or url.password:
                raise ValueError("Downloads require credential-free HTTPS URLs.")
            filename = item.get("filename", PurePosixPath(url.path).name)
            if not filename or filename != Path(filename).name:
                raise ValueError("Download filenames must be simple path components.")
            downloaded = target / filename
            with urllib.request.urlopen(item["source"], timeout=90) as response:
                if urllib.parse.urlsplit(response.url).scheme != "https":
                    raise ValueError("HTTPS download redirected to an insecure transport.")
                record["resolved_url"] = response.url
                with downloaded.open("xb") as stream:
                    shutil.copyfileobj(response, stream)
            original = downloaded
        else:
            original = Path(item["source"])
            if original.is_symlink():
                raise ValueError(f"Source symlinks require explicit archival handling: {original}")
            if item["kind"] == "file":
                shutil.copy2(original, target / original.name)
            elif item["kind"] == "tree":
                if not original.is_dir():
                    raise FileNotFoundError(original)
                for path in sorted(original.rglob("*")):
                    relative = path.relative_to(original)
                    if ".git" in relative.parts or "__pycache__" in relative.parts:
                        continue
                    if path.is_symlink():
                        raise ValueError(f"Source symlinks require explicit archival handling: {path}")
                    if path.is_file():
                        copied = target / relative
                        copied.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, copied)
                if not any(path.is_file() for path in target.rglob("*")):
                    raise ValueError(f"Source tree contains no retained files: {original}")
            else:
                raise ValueError(f"Unknown input kind: {item['kind']}")
        if item.get("expected_sha256"):
            if not original.is_file() or fingerprint(original)["sha256"] != item["expected_sha256"]:
                raise ValueError(f"Input differs from its recorded hash: {item['id']}")
        record["payload_directory"] = f"payload/{item['id']}"
        inputs.append(record)
        print("Retained", item["id"], flush=True)
    inventory = {
        path.relative_to(destination).as_posix(): fingerprint(path)
        for path in sorted(payload.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "schema_version": 1,
        "purpose": "Internal R01/R02 source and review preparation; not a public source offer.",
        "redistribution_cleared": False,
        "g1_approved": False,
        "inputs": inputs,
        "review": spec["review"],
        "files": inventory,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    archive_path = destination / "native-redistribution-review.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(manifest_path, "manifest.json")
        for name in inventory:
            safe_name(name)
            archive.write(destination / name, name)
    verify(archive_path)
    record = {"archive": str(archive_path), **fingerprint(archive_path), "manifest": fingerprint(manifest_path)}
    (destination / "bundle-record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    print(json.dumps(record, indent=2))
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assemble = commands.add_parser("prepare")
    assemble.add_argument("specification", type=Path)
    assemble.add_argument("destination", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        prepare(arguments.specification, arguments.destination)
    else:
        verify(arguments.archive)
