"""Evaluate an opt-in packaging candidate without changing the production backend."""

import argparse
import contextlib
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tomllib
import zipfile
from collections.abc import Mapping, Sequence
from email.parser import BytesParser
from importlib.metadata import distribution, distributions, version
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(filepath: Path) -> dict[str, str | int]:
    """Return the file size and SHA256 used by evidence records."""
    return {
        "size_bytes": filepath.stat().st_size,
        "sha256": hashlib.sha256(filepath.read_bytes()).hexdigest(),
    }


def stage(destination: Path) -> list[str]:
    """Copy tracked sources and native submodules into a new external candidate."""
    if destination.resolve().is_relative_to(ROOT):
        raise ValueError("The spike must be staged outside the working checkout.")
    destination.mkdir(parents=True, exist_ok=False)
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--recurse-submodules"],
        text=True,
    ).splitlines()
    untracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"],
        text=True,
    ).splitlines()
    names = sorted(
        set(tracked + [name for name in untracked if not name.startswith(("output/", "test_data/", ".vscode/"))])
    )
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe source path: {name}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    if not (destination / "pyproject.toml").is_file():
        shutil.copy2(destination / "packaging/pyproject.toml", destination / "pyproject.toml")
    return names


def execute(label: str, command: list[str], work_dir: Path, environment: dict[str, str]) -> dict:
    """Run a validation command and retain its exclusive log and exit status."""
    log_path = work_dir / f"{label}.log"
    with log_path.open("x", encoding="utf8") as stream:
        result = subprocess.run(
            command, cwd=work_dir, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    print(log_path.read_text(encoding="utf8")[-2500:])
    record = {
        "command": command,
        "cwd": str(work_dir),
        "exit_code": result.returncode,
        "log": {"path": str(log_path), **fingerprint(log_path)},
    }
    (work_dir / f"{label}-command-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    result.check_returncode()
    return record


def audit_wheel(wheel: Path, source: Path) -> dict:
    """Verify wheel metadata, module bytes, selected notices and production readme parity."""
    from packaging.specifiers import SpecifierSet

    configuration = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf8"))
    project = configuration["project"]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        native = [name for name in names if name.startswith("_pylibCZIrw.") and name.endswith((".pyd", ".so"))]
        if not len(native) == 1:
            raise AssertionError(native)
        if not not any("/tests/" in name or "__pycache__" in name for name in names):
            raise AssertionError()
        if not archive.read("pylibCZIrw/czi.py") == (source / "pylibCZIrw/czi.py").read_bytes():
            raise AssertionError()
        metadata = BytesParser().parsebytes(archive.read(next(name for name in names if name.endswith("/METADATA"))))
        if not metadata["Version"] == project["version"]:
            raise AssertionError()
        if not SpecifierSet(metadata["Requires-Python"]) == SpecifierSet(">=3.12,<3.16"):
            raise AssertionError()
        expected_readme = "\n".join((source / name).read_text(encoding="utf8") for name in ("INFO.md", "CHANGELOG.md"))
        if not metadata["Description-Content-Type"] == "text/markdown":
            raise AssertionError()
        description = metadata.get_payload()
        if not isinstance(description, str):
            raise ValueError("Wheel metadata must contain one text description.")
        if not description.rstrip("\n") == expected_readme.rstrip("\n"):
            raise AssertionError()
        for license_name in ("COPYING", "COPYING.LESSER", "NOTICE.txt"):
            if not any(name.endswith(f"/licenses/{license_name}") for name in names):
                raise AssertionError(license_name)
        bundled_native_files = {}
        license_files = {}
        for name in names:
            if name.endswith((".pyd", ".dll", ".dylib", ".so")) or ".so." in Path(name).name:
                content = archive.read(name)
                bundled_native_files[name] = {"size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            elif ".dist-info/licenses/" in name and not name.endswith("/"):
                content = archive.read(name)
                license_files[name] = {"size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        for pattern in configuration["tool"]["scikit-build"]["wheel"]["license-files"]:
            for path in source.glob(pattern):
                if not path.is_file():
                    continue
                relative = path.relative_to(source).as_posix()
                matches = [name for name in license_files if name.endswith(f"/licenses/{relative}")]
                if not len(matches) == 1:
                    raise AssertionError(f"Missing or ambiguous packaged notice: {relative}")
                if not archive.read(matches[0]) == path.read_bytes():
                    raise AssertionError(f"Packaged notice bytes differ: {relative}")
        return {
            "path": str(wheel),
            **fingerprint(wheel),
            "contents": names,
            "native": native,
            "bundled_native_files": bundled_native_files,
            "license_files": license_files,
            "selected_source_notices_match": True,
            "version": metadata["Version"],
            "requires_python": metadata["Requires-Python"],
            "requires_dist": metadata.get_all("Requires-Dist"),
            "source_python_bytes_match": True,
            "readme_matches_production": True,
            "notice_scope": "Root notices checked; transitive native dependency notices require a separate audit.",
        }


def isolated_sdist(source: Path, work_dir: Path, environment: dict[str, str]) -> Path:
    """Build and inspect a Git-free sdist using an isolated dependency overlay."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from pyproject_hooks import BuildBackendHookCaller

    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf8"))
    dependencies = project["build-system"]["requires"]
    overlay = work_dir / "sdist-build-dependencies"
    execute(
        "sdist-build-dependencies",
        [
            sys.executable,
            "-I",
            "-m",
            "pip",
            "install",
            "--ignore-installed",
            "--no-compile",
            "--target",
            str(overlay),
            *dependencies,
        ],
        work_dir,
        environment,
    )

    def runner(cmd: Sequence[str], cwd: str | None = None, extra_environ: Mapping[str, str] | None = None) -> None:
        """Run the backend hook with its declared sequence/mapping contract."""
        hook_environment = environment | dict(extra_environ or {})
        hook_command = [
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).resolve()),
            "backend",
            str(overlay),
            *cmd[1:],
        ]
        subprocess.run(hook_command, cwd=cwd, env=hook_environment, check=True)

    backend = BuildBackendHookCaller(
        str(source),
        project["build-system"]["build-backend"],
        runner=runner,
        python_executable=sys.executable,
    )
    extra = backend.get_requires_for_build_sdist({})
    installed = {
        canonicalize_name(package.metadata["Name"]): package.version for package in distributions(path=[str(overlay)])
    }
    for specification in extra:
        requirement = Requirement(specification)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        installed_version = installed.get(canonicalize_name(requirement.name))
        if not not requirement.extras:
            raise AssertionError(f"Hook dependency extras require an explicit isolated install: {specification}")
        if not ((installed_version is not None and installed_version in requirement.specifier)):
            raise AssertionError(f"Hook dependency is not satisfied by the isolated build overlay: {specification}")
    destination = work_dir / "sdists"
    destination.mkdir()
    archive = destination / backend.build_sdist(str(destination), {})
    unpacked = work_dir / "unpacked-sdist"
    unpacked.mkdir()
    with tarfile.open(archive) as stream:
        members = stream.getnames()
        if not not any(".git" in Path(name).parts for name in members):
            raise AssertionError()
        stream.extractall(unpacked, filter="data")
    roots = list(unpacked.iterdir())
    if not len(roots) == 1:
        raise AssertionError()
    result = roots[0]
    for relative in (
        "libs/libCZIrw/CMakeLists.txt",
        "libs/pybind11/CMakeLists.txt",
        "libs/pybind11/include/pybind11/pybind11.h",
        "_pylibCZIrw/src/bindings/CZIrw.cpp",
        "packaging/CMakeLists.txt",
        "COPYING.LESSER",
    ):
        if not (result / relative).is_file():
            raise AssertionError(relative)
    if not not (result / ".git").exists():
        raise AssertionError()
    (work_dir / "sdist-record.json").write_text(
        json.dumps(
            {
                "path": str(archive),
                **fingerprint(archive),
                "contents": members,
                "build_dependencies": dependencies,
                "hook_build_requirements": extra,
                "hook_python": sys.executable,
                "isolation": (
                    "Conda interpreter with -I -S, explicit isolated dependency overlay, " "no ambient site-packages."
                ),
                "unpacked_source": str(result),
                "git_metadata_present": False,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    return result


class LocalOnly:
    """Select exact local test cases while reporting live-URL deselections."""

    def __init__(self) -> None:
        self.deselected: list[str] = []

    def pytest_collection_modifyitems(self, config: "pytest.Config", items: list["pytest.Item"]) -> None:
        """Keep local cases and report the exact excluded live-URL parameters."""
        local: list[pytest.Item] = []
        remote: list[pytest.Item] = []
        for item in items:
            parameters = getattr(getattr(item, "callspec", None), "params", {})
            is_remote = any(
                isinstance(value, str) and value.startswith(("https://", "http://")) for value in parameters.values()
            )
            (remote if is_remote else local).append(item)
        self.deselected = [item.nodeid for item in remote]
        config.hook.pytest_deselected(items=remote)
        items[:] = local


def regressions(source: Path, work_dir: Path) -> None:
    """Run the installed-wheel suite and retain exact results and module identities."""
    import defusedxml.ElementTree as ET
    import pytest

    import _pylibCZIrw as native
    from pylibCZIrw import czi

    site_packages = Path(sysconfig.get_path("platlib"))
    if not Path(czi.__file__).is_relative_to(site_packages):
        raise AssertionError()
    if not Path(native.__file__).is_relative_to(site_packages):
        raise AssertionError()
    if not (source / "pylibCZIrw/czi.py").read_bytes() == Path(czi.__file__).read_bytes():
        raise AssertionError()
    os.environ["PYTHON_SEMANTIC_RELEASE_VERSION"] = version("pylibczirw")
    os.environ["CZIRW_RESOURCE_EVIDENCE_DIR"] = str(work_dir / "installed-resources")
    plugin = LocalOnly()
    junit = work_dir / "installed-regressions.xml"
    arguments = ["--import-mode=importlib", "-q", "-rs", f"--junitxml={junit}", str(source / "pylibCZIrw/tests")]
    log_path = work_dir / "installed-regressions.log"
    with log_path.open("x", encoding="utf8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        result = pytest.main(arguments, plugins=[plugin])
    cases = list(ET.parse(junit, forbid_dtd=True).getroot().iter("testcase"))
    counts = {tag: sum(case.find(tag) is not None for case in cases) for tag in ("failure", "error", "skipped")}
    counts["passed"] = sum(all(case.find(tag) is None for tag in ("failure", "error", "skipped")) for case in cases)
    record = {
        "python": sys.executable,
        "cwd": str(Path.cwd()),
        "pytest_arguments": arguments,
        "exit_code": int(result),
        "counts": counts,
        "network_cases_deselected": plugin.deselected,
        "imports": {"python": czi.__file__, "native": native.__file__},
        "installed_modules": {"python": fingerprint(Path(czi.__file__)), "native": fingerprint(Path(native.__file__))},
        "log": fingerprint(log_path),
        "junit": fingerprint(junit),
        "packages": {
            name: version(name)
            for name in ("numpy", "pytest", "czifile", "imagecodecs", "xmltodict", "validators", "packaging")
        },
    }
    (work_dir / "regressions-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    print(log_path.read_text(encoding="utf8")[-4000:])
    print(json.dumps(counts, indent=2))
    if not result == 0:
        raise AssertionError()


def check(arguments: argparse.Namespace, environment: dict[str, str]) -> None:
    """Verify wheel, sdist, installed and editable parity in the disposable environment."""
    work_dir = arguments.work_dir.resolve()
    source = work_dir / "source"
    os.chdir(work_dir)
    wheel = next((work_dir / "wheels").glob("*.whl"))
    audit = audit_wheel(wheel, source)
    (work_dir / "wheel-audit.json").write_text(json.dumps(audit, indent=2), encoding="utf8")
    unpacked = isolated_sdist(source, work_dir, environment)
    config = []
    if arguments.toolchain:
        config.append(f"--config-settings=cmake.define.CMAKE_TOOLCHAIN_FILE={arguments.toolchain.resolve()}")
    if arguments.triplet:
        config.append(f"--config-settings=cmake.define.VCPKG_TARGET_TRIPLET={arguments.triplet}")
    execute(
        "sdist-wheel",
        [
            sys.executable,
            "-I",
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-cache-dir",
            "-v",
            "--wheel-dir",
            str(work_dir / "sdist-wheels"),
            str(unpacked),
            *config,
        ],
        work_dir,
        environment,
    )
    sdist_wheel = next((work_dir / "sdist-wheels").glob("*.whl"))
    (work_dir / "sdist-wheel-audit.json").write_text(
        json.dumps(audit_wheel(sdist_wheel, source), indent=2), encoding="utf8"
    )
    if not ((arguments.restore_wheel and arguments.restore_wheel.is_file())):
        raise AssertionError("Supply the baseline wheel to restore after installed checks.")
    try:
        execute(
            "install-candidate",
            [sys.executable, "-I", "-m", "pip", "install", "--no-deps", "--force-reinstall", str(sdist_wheel)],
            work_dir,
            environment,
        )
        execute(
            "regressions",
            [sys.executable, "-I", str(Path(__file__).resolve()), str(work_dir), "--regressions"],
            work_dir,
            environment,
        )
        execute(
            "install-editable",
            [
                sys.executable,
                "-I",
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--force-reinstall",
                "-v",
                "-e",
                str(source),
                *config,
            ],
            work_dir,
            environment,
        )
        execute(
            "editable-imports",
            [sys.executable, "-I", str(Path(__file__).resolve()), str(work_dir), "--editable-imports"],
            work_dir,
            environment,
        )
    finally:
        execute(
            "restore-baseline",
            [
                sys.executable,
                "-I",
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--force-reinstall",
                str(arguments.restore_wheel.resolve()),
            ],
            work_dir,
            environment,
        )


def editable_imports(source: Path, work_dir: Path) -> None:
    """Verify editable module origins and preserve their provenance record."""
    import _pylibCZIrw as native
    from pylibCZIrw import czi

    if not Path(czi.__file__).is_relative_to(source):
        raise AssertionError()
    if not Path(native.__file__).is_relative_to(Path(sysconfig.get_path("platlib"))):
        raise AssertionError()
    direct_url = distribution("pylibczirw").read_text("direct_url.json")
    if direct_url is None:
        raise RuntimeError("Editable provenance is missing direct_url.json.")
    if not json.loads(direct_url)["dir_info"]["editable"]:
        raise AssertionError()
    if not callable(getattr(czi.CziDocument, "open", None)):
        raise AssertionError()
    record = {
        "python": sys.executable,
        "cwd": str(Path.cwd()),
        "imports": {"python": czi.__file__, "native": native.__file__},
        "editable": True,
    }
    (work_dir / "editable-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    print(json.dumps(record, indent=2))


def main() -> None:
    """Evaluate an opt-in packaging candidate without changing the production backend."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--triplet")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--regressions", action="store_true")
    parser.add_argument("--editable-imports", action="store_true")
    parser.add_argument("--restore-wheel", type=Path)
    arguments = parser.parse_args()
    work_dir = arguments.work_dir.resolve()
    source = work_dir / "source"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    if os.name == "nt":
        environment["PATH"] = (
            f"{Path(sys.executable).parent};{Path(sys.executable).parent / 'Scripts'};"
            f"{os.environ['SystemRoot']}/System32/WindowsPowerShell/v1.0;"
            f"{os.environ['SystemRoot']}/System32;{environment['PATH']}"
        )
        environment["CMAKE_GENERATOR"] = "Visual Studio 17 2022"
    if arguments.check:
        check(arguments, environment)
        return
    if arguments.regressions:
        os.chdir(work_dir)
        regressions(source, work_dir)
        return
    if arguments.editable_imports:
        os.chdir(work_dir)
        editable_imports(source, work_dir)
        return
    names = stage(source)
    command = [
        sys.executable,
        "-I",
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--no-cache-dir",
        "-v",
        "--wheel-dir",
        str(work_dir / "wheels"),
        str(source),
    ]
    if arguments.toolchain:
        command.append(f"--config-settings=cmake.define.CMAKE_TOOLCHAIN_FILE={arguments.toolchain.resolve()}")
    if arguments.triplet:
        command.append(f"--config-settings=cmake.define.VCPKG_TARGET_TRIPLET={arguments.triplet}")
    log_path = work_dir / "isolated-wheel.log"
    with log_path.open("x", encoding="utf8") as stream:
        result = subprocess.run(
            command, cwd=work_dir, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    record = {
        "python": sys.executable,
        "command": command,
        "cwd": str(work_dir),
        "exit_code": result.returncode,
        "snapshot_files": len(names),
        "source_inputs": {
            name: fingerprint(source / name)
            for name in (
                "pyproject.toml",
                "packaging/CMakeLists.txt",
                "CMakeLists.txt",
                "pylibCZIrw/czi.py",
            )
        },
        "log": {"path": str(log_path), **fingerprint(log_path)},
        "wheels": [{"path": str(path), **fingerprint(path)} for path in (work_dir / "wheels").glob("*.whl")],
        "scope": (
            "Opt-in isolated candidate only; production backend and release pipeline unchanged; "
            "not support certification."
        ),
    }
    (work_dir / "isolated-wheel-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    print(log_path.read_text(encoding="utf8")[-9000:])
    result.check_returncode()
    print(json.dumps(record["wheels"], indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backend":
        sys.path.insert(0, sys.argv[2])
        sys.argv = sys.argv[3:]
        runpy.run_path(sys.argv[0], run_name="__main__")
    else:
        main()
