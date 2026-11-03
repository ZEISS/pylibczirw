"""Check installed B01 native, HTTPS and provenance behavior in the Conda environment."""

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import ssl
import subprocess  # nosec B404 - Intentional subprocesses; see call-specific reviews.
import sys
import sysconfig
import traceback
from pathlib import Path
from typing import Iterator


def execute(label: str, command: list[str], work_dir: Path, environment: dict[str, str]) -> dict:
    """Run a validation command and retain its exclusive log and exit status."""
    log = work_dir / f"{label}.log"
    with log.open("x", encoding="utf8") as stream:
        result = subprocess.run(  # nosec B603 - Reviewed argv; shell=False.
            command, cwd=work_dir, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    record = {"command": command, "exit_code": result.returncode, "cwd": str(work_dir), "log": str(log)}
    (work_dir / f"{label}-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    print(log.read_text(encoding="utf8")[-2000:])
    result.check_returncode()
    return record


def serve(cert: Path, key: Path) -> None:
    """Run the ephemeral local TLS endpoint used by certificate checks."""
    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    from http.server import BaseHTTPRequestHandler, HTTPServer

    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(server.server_port, flush=True)
    server.serve_forever()


@contextlib.contextmanager
def tls_server(command: list[str], work_dir: Path) -> Iterator[subprocess.Popen[str]]:
    """Own the TLS child, output streams and bounded termination together."""
    with (work_dir / "tls-server.log").open("x", encoding="utf8") as errors:
        with subprocess.Popen(  # nosec B603 - Reviewed local interpreter argv; shell=False.
            command, stdout=subprocess.PIPE, stderr=errors, text=True, cwd=work_dir
        ) as server:
            try:
                yield server
            finally:
                server.terminate()
                server.wait(timeout=10)


def reject_untrusted_https(port: int) -> None:
    """Fail explicitly if the untrusted endpoint is accepted."""
    # Keep installed-package access deferred to the HTTPS validation operation.
    # pylint: disable-next=import-outside-toplevel
    from pylibCZIrw import czi

    with czi.open_czi(f"https://127.0.0.1:{port}/image.czi", file_input_type=czi.ReaderFileInputTypes.Curl):
        raise AssertionError("An untrusted certificate was accepted.")


def tls(work_dir: Path) -> None:
    """Verify exact trusted HTTPS pixels and rejection of an untrusted certificate."""
    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    import numpy as np

    # Package-owned private/native API intentionally exercised.
    # pylint: disable-next=import-outside-toplevel,import-private-name
    import _pylibCZIrw as native

    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    from pylibCZIrw import czi

    site_packages = Path(sysconfig.get_path("platlib"))
    if not Path(czi.__file__).is_relative_to(site_packages):
        raise AssertionError()
    if not Path(native.__file__).is_relative_to(site_packages):
        raise AssertionError()
    url = "https://cadevelop.blob.core.windows.net/public/pylibCZIrwTestFiles/c1_bgr24.czi"
    fixture = work_dir / "source/pylibCZIrw/tests/integration/test_data/c1_bgr24.czi"
    with czi.open_czi(str(fixture)) as local, czi.open_czi(
        url, file_input_type=czi.ReaderFileInputTypes.Curl
    ) as remote:
        expected = local.read(plane={"T": 0, "C": 0, "Z": 0})
        actual = remote.read(plane={"T": 0, "C": 0, "Z": 0})
        np.testing.assert_array_equal(actual, expected)
    with czi.CziDocument.open(url, file_input_type=czi.ReaderFileInputTypes.Curl) as remote:
        np.testing.assert_array_equal(remote.read(plane={"T": 0, "C": 0, "Z": 0}), expected)
    openssl = shutil.which("openssl")
    if not openssl:
        raise AssertionError("OpenSSL executable is needed only to generate an untrusted local test certificate.")
    cert, key = work_dir / "untrusted-test-cert.pem", work_dir / "untrusted-test-key.pem"
    execute(
        "create-untrusted-certificate",
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-config",
            str(Path(__file__).with_name("tls-test.cnf")),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        work_dir,
        os.environ.copy(),
    )
    command = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        str(work_dir),
        "--serve",
        "--cert",
        str(cert),
        "--key",
        str(key),
    ]
    rejection = None
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(key.unlink, missing_ok=True)
        server = cleanup.enter_context(tls_server(command, work_dir))
        if server.stdout is None:
            raise RuntimeError("The TLS test server did not provide its port output stream.")
        port = int(server.stdout.readline().strip())
        try:
            reject_untrusted_https(port)
        except RuntimeError as error:
            rejection = "".join(traceback.format_exception(error))
            if "error code 60" not in rejection:
                raise AssertionError(rejection) from error
    record = {
        "python": sys.executable,
        "imports": {"python": czi.__file__, "native": native.__file__},
        "trusted_https_url": url,
        "trusted_https_exact_local_pixels": True,
        "legacy_and_document_reads": True,
        "shape": list(expected.shape),
        "dtype": str(expected.dtype),
        "pixel_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
        "untrusted_local_certificate_rejected": True,
        "rejection": rejection,
        "trust_store_modified": False,
        "verification_disabled": False,
    }
    (work_dir / "tls-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    print(json.dumps(record, indent=2))


def main(arguments: argparse.Namespace) -> None:
    """Check installed B01 native, HTTPS and provenance behavior in the Conda environment."""
    work_dir = arguments.work_dir.resolve()
    if arguments.serve:
        serve(arguments.cert, arguments.key)
        return
    os.chdir(work_dir)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    if arguments.tls:
        tls(work_dir)
        return
    source = work_dir / "source"
    wheel = next((work_dir / "sdist-wheels").glob("*.whl"))
    if not arguments.restore_wheel.is_file():
        raise AssertionError()
    build = work_dir / "native-build"
    # Standalone Windows toolchain environment mirrors the independent build CLI.
    # pylint: disable=duplicate-code
    environment["PATH"] = (
        f"{Path(sys.executable).parent};{Path(sys.executable).parent / 'Scripts'};"
        f"{os.environ['SystemRoot']}/System32/WindowsPowerShell/v1.0;"
        f"{os.environ['SystemRoot']}/System32;{environment['PATH']}"
    )
    # pylint: enable=duplicate-code
    environment["CMAKE_GENERATOR"] = "Visual Studio 17 2022"
    # Standalone shell-free pip recipe; keep each CLI independently executable.
    # pylint: disable=duplicate-code
    execute(
        "native-target-wheel",
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
            str(work_dir / "native-target-wheels"),
            str(source),
            f"--config-settings=build-dir={build}",
            "--config-settings=build.targets=_pylibCZIrw;cziedit_tests",
            f"--config-settings=cmake.define.CMAKE_TOOLCHAIN_FILE={arguments.toolchain.resolve()}",
            "--config-settings=cmake.define.VCPKG_TARGET_TRIPLET=x64-windows-static",
        ],
        work_dir,
        environment,
    )
    # pylint: enable=duplicate-code
    native_fixture = work_dir / "native-editor-input.czi"
    shutil.copy2(source / "pylibCZIrw/tests/integration/test_data/c1_bgr24.czi", native_fixture)
    temporary = work_dir / "native-editor-temporary"
    temporary.mkdir()
    native_environment = environment | {"TMP": str(temporary), "TEMP": str(temporary)}
    execute(
        "native-editor",
        [str(next(build.rglob("cziedit_tests.exe"))), str(native_fixture)],
        work_dir,
        native_environment,
    )
    with contextlib.ExitStack() as cleanup:
        # Standalone shell-free pip recipe; keep each CLI independently executable.
        # pylint: disable=duplicate-code
        cleanup.callback(
            execute,
            "parity-restore-baseline",
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
        # pylint: enable=duplicate-code
        # Standalone shell-free pip recipe; keep each CLI independently executable.
        # pylint: disable=duplicate-code
        execute(
            "parity-install",
            [sys.executable, "-I", "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel)],
            work_dir,
            environment,
        )
        # pylint: enable=duplicate-code
        execute(
            "https",
            [sys.executable, "-I", str(Path(__file__).resolve()), str(work_dir), "--tls"],
            work_dir,
            environment,
        )
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("Git is required to record native provenance.")
    provenance = {
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "pins": {
            name: subprocess.check_output(  # nosec B603 - Reviewed argv; shell=False.
                [str(Path(git).resolve()), "-C", str(arguments.checkout / name), "rev-parse", "HEAD"], text=True
            ).strip()
            for name in (".", "libs/libCZIrw", "libs/pybind11")
        },
        "vcpkg_revision": subprocess.check_output(  # nosec B603 - Reviewed argv; shell=False.
            [str(Path(git).resolve()), "-C", str(arguments.toolchain.resolve().parents[2]), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "build_dependencies": {
            item.metadata["Name"]: item.version
            for item in importlib.metadata.distributions(path=[str(work_dir / "sdist-build-dependencies")])
        },
        "native_build_cache": str(build / "CMakeCache.txt"),
    }
    (work_dir / "provenance-record.json").write_text(json.dumps(provenance, indent=2), encoding="utf8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--restore-wheel", type=Path)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    main(parser.parse_args())
