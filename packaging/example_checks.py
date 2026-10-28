"""Run fixture-backed documentation examples against installed artifacts."""

import argparse
import hashlib
import inspect
import json
import os
import runpy
import shutil
import subprocess  # nosec B404 - Intentional subprocesses; see call-specific reviews.
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTABLE = ("01", "03", "04", "05", "06", "07", "08", "10")
LOCAL = ("02", "09")
PLOT_VALUES = {
    "02": ("pixels_by_m", "pixels"),
    "03": ("pixels",),
    "04": ("pixels",),
    "06": ("pixels", "mask", "masked"),
    "07": ("pixels", "roi_pixels", "composed"),
    "08": ("label", "preview"),
    "09": ("pixels",),
    "10": ("pixels",),
}


def require(condition: object, *details: object) -> None:
    """Keep validation active under optimization and preserve error arguments."""
    if not condition:
        raise AssertionError(*details)


def fingerprint(path: Path) -> dict:
    """Return the file size and SHA256 used by evidence records."""
    return {"size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def installed() -> dict:
    """Verify non-editable installed module origins and record artifact provenance."""
    # Package-owned private/native API intentionally exercised.
    # pylint: disable-next=import-outside-toplevel,import-private-name
    import _pylibCZIrw as native

    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    from pylibCZIrw import czi

    site = Path(sysconfig.get_path("platlib")).resolve()
    if not Path(czi.__file__).resolve().is_relative_to(site):
        raise AssertionError(czi.__file__)
    if not Path(native.__file__).resolve().is_relative_to(site):
        raise AssertionError(native.__file__)
    distribution = metadata.distribution("pylibczirw")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    require(not direct_url.get("dir_info", {}).get("editable", False))
    return {
        "python": sys.executable,
        "version": distribution.version,
        "direct_url": direct_url,
        "imports": {"python": czi.__file__, "native": native.__file__},
        "module_hashes": {"python": fingerprint(Path(czi.__file__)), "native": fingerprint(Path(native.__file__))},
    }


def documentation_example(staged: Path, work: Path) -> None:
    """Execute the unchanged Python fence and verify its returned image."""
    # Optional Markdown parser is needed only for documentation validation.
    # pylint: disable-next=import-outside-toplevel
    from markdown_it import MarkdownIt

    blocks = [
        token.content
        for token in MarkdownIt().parse((staged / "INFO.md").read_text(encoding="utf8"))
        if token.type == "fence" and token.info.strip() == "python"
    ]
    require(len(blocks) == 1)
    os.chdir(staged)
    extracted = work / "INFO-python-example.py"
    extracted.write_text(blocks[0], encoding="utf8")
    namespace = runpy.run_path(str(extracted), run_name="__documentation_example__")
    require(namespace["image2d"].shape == (100, 50, 1))
    require(namespace["total_bounding_box"] and namespace["scenes_bounding_rectangle"])


def child(work: Path, case: str) -> None:
    """Execute one installed example and verify its displayed arrays and rendering."""
    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    import matplotlib

    matplotlib.use("Agg", force=True)
    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    import matplotlib.pyplot as plt

    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    import numpy as np

    # Validation-only dependencies are intentionally deferred.
    # pylint: disable-next=import-outside-toplevel
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    provenance = installed()
    staged = work / "example-source"
    figures = []
    number = case[:2]

    def save(*_args: object, **_kwargs: object) -> None:
        """Check displayed arrays and retain a nonblank Agg-rendered figure."""
        frame = inspect.currentframe()
        if frame is None or frame.f_back is None:
            raise RuntimeError("Figure validation requires the calling Python frame.")
        values = frame.f_back.f_locals
        del frame
        opened = [plt.figure(identifier) for identifier in plt.get_fignums()]
        require(len(opened) == 1, case)
        (figure,) = opened
        images = [image for axis in figure.axes for image in axis.get_images()]
        expected = PLOT_VALUES[number]
        require(len(images) == len(expected), (case, len(images)))
        arrays = []
        for image, name in zip(images, expected):
            actual = np.asarray(image.get_array())
            np.testing.assert_array_equal(actual, values[name])
            arrays.append(
                {
                    "name": name,
                    "shape": list(actual.shape),
                    "dtype": str(actual.dtype),
                    "sha256": hashlib.sha256(actual.tobytes()).hexdigest(),
                }
            )
        if number == "02":
            np.testing.assert_array_equal(values["pixels_by_m"], values["pixels"])
        elif number == "06":
            np.testing.assert_array_equal(values["masked"], np.where(values["mask"], values["pixels"], 0))
        elif number == "09":
            require(values["output_path"].read_bytes() == values["raw"])
        renderer = figure.canvas
        if not isinstance(renderer, FigureCanvasAgg):
            raise RuntimeError("Figure validation requires the Agg canvas backend.")
        renderer.draw()
        canvas = np.asarray(renderer.buffer_rgba())
        require(canvas.shape[0] > 0 and canvas.shape[1] > 0 and canvas[..., :3].std() > 0)
        image_path = work / "plots" / f"{Path(case).stem}.png"
        image_path.parent.mkdir(exist_ok=True)
        figure.savefig(image_path, dpi=120)
        figures.append({"path": str(image_path), **fingerprint(image_path), "arrays": arrays, "nonblank_canvas": True})
        plt.close(figure)

    plt.show = save
    if case == "INFO":
        documentation_example(staged, work)
    else:
        script = staged / "demo_scripts" / case
        sys.argv = [str(script)]
        if number == "09":
            sys.argv.extend(["--output-dir", str(work / "extracted")])
        runpy.run_path(str(script), run_name="__main__")
        require(bool(figures) == (number in PLOT_VALUES), case)
    record = {"case": case, "status": "passed", "installed": provenance, "figures": figures}
    (work / f"{Path(case).stem}-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")


def run(work: Path, source: Path, include_local: bool, only: str | None) -> None:
    """Stage admitted inputs and execute the selected installed examples."""
    require(not work.is_relative_to(source), "Example evidence must live outside the source checkout.")
    work.mkdir(parents=True, exist_ok=False)
    provenance = installed()
    staged = work / "example-source"
    (staged / "demo_scripts").mkdir(parents=True)
    cases = PORTABLE + LOCAL if include_local else PORTABLE
    if only:
        require(only in cases, only)
        cases = (only,)
    scripts = []
    inputs = []
    for number in cases:
        (script,) = (source / "demo_scripts").glob(f"{number}_*.py")
        shutil.copy2(script, staged / "demo_scripts" / script.name)
        scripts.append(script.name)
        inputs.append({"path": str(script), **fingerprint(script)})
    fixture_directory = "pylibCZIrw/tests/integration/test_data"
    relatives = [
        f"{fixture_directory}/synthetic/{name}.czi"
        for name in (
            "stored_sparse_coordinates",
            "stored_levels_same_m37",
            "literal_valid_mask_v2",
            "literal_tiles_with_gap",
            "literal_slidepreview_cases",
        )
    ]
    if include_local:
        relatives.extend(["test_data/Brain_CH=3_M=25.czi", "test_data/well96-A4-6_B16-18_CH=2.czi"])
    for relative in relatives:
        original = source / relative
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        inputs.append({"path": str(original), **fingerprint(original)})
    if not only:
        shutil.copy2(source / "INFO.md", staged / "INFO.md")
        shutil.copy2(source / fixture_directory / "c2_gray8_t3_z5_s2.czi", staged / "myimagefile.czi")
        scripts.append("INFO")
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["MPLBACKEND"] = "Agg"
    records = []
    for case in scripts:
        log = work / f"{Path(case).stem}.log"
        command = [sys.executable, "-I", str(Path(__file__).resolve()), str(work), "--case", case]
        with log.open("x", encoding="utf8") as stream:
            result = subprocess.run(  # nosec B603 - Reviewed argv; shell=False.
                command, cwd=work, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=False
            )
        print(case, "exit", result.returncode, flush=True)
        if result.returncode != 0:
            raise AssertionError(log.read_text(encoding="utf8")[-4000:])
        record = json.loads((work / f"{Path(case).stem}-record.json").read_text(encoding="utf8"))
        record["command"] = command
        record["log"] = {"path": str(log), **fingerprint(log)}
        records.append(record)
    record = {
        "status": "passed",
        "installed": provenance,
        "cases": records,
        "inputs": inputs,
        "local_only_demos_included": include_local,
        "not_run": (
            []
            if include_local
            else [
                "02_read_subblock.py (local acquisition file)",
                "09_extract_attachment_image.py (local acquisition file)",
            ]
        ),
        "plot_validation": (
            "Agg rasterization, nonblank canvas, exact displayed-array comparison; "
            "interactive GUI behavior is not certified."
        ),
    }
    (work / "examples-record.json").write_text(json.dumps(record, indent=2), encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--include-local", action="store_true")
    parser.add_argument("--only")
    parser.add_argument("--case")
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    if arguments.case:
        child(directory, arguments.case)
    else:
        run(directory, arguments.source.resolve(), arguments.include_local, arguments.only)
