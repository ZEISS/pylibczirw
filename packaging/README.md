# Packaging Candidate

The production backend remains the repository's existing setup script and
release workflows. The configuration in this directory is an opt-in
scikit-build-core candidate with a CMake wrapper around the same native targets.
It does not replace the Python API, native implementation or production build.

The candidate configuration defines its build requirements, intended interpreter
selectors and platform dependency choices. Configuration is not support
certification. Dependencies, native source identities, wheel repair, notices,
versioning and clean-runtime behavior require validation before adoption.

## Local Evaluation

Use a separate environment and a new directory outside the checkout. The staging
helper copies tracked sources and initialized submodules, then activates the
candidate configuration only in that external copy. It does not provision
native dependencies. Windows requires a vcpkg toolchain with curl SSL support
and Eigen; POSIX requires the corresponding compiler and dependency packages.

```powershell
$work = Join-Path $env:TEMP "pylibczirw-build-check"
$toolchain = Join-Path $env:VCPKG_ROOT "scripts/buildsystems/vcpkg.cmake"
python -I packaging/spike.py $work --toolchain $toolchain --triplet x64-windows-static
```

Do not run installation or editable checks in an environment whose existing
package must be preserved. Use a disposable environment and retain the exact
wheel, source/toolchain identities, command output and module origins.

## Installed Examples

With the matching wheel installed in a separate environment:

```powershell
python -m pip install matplotlib==3.11.2 markdown-it-py==4.2.0
$evidence = Join-Path $env:TEMP "pylibczirw-example-check"
python -I packaging/example_checks.py $evidence
```

The example checker stages inputs outside the checkout, requires non-editable
installed imports, and runs fresh child processes. It saves Agg-rendered figures
and checks the displayed arrays and nonblank canvases. This is not interactive
GUI certification. Add local-data examples only when their user-supplied input
files are available. See the [demo guide](../demo_scripts/README.md).

## Distribution Boundary

License/notice collection is not legal clearance. Exact corresponding sources,
relinking or replacement arrangements, dependency license compatibility and any
source-delivery obligations require distributor review. The unchanged production
setup script and the candidate configuration do not necessarily package the
same notice set. Inspect the actual wheel before redistribution.

The source-capture helper can build an internal source/review archive and verify
its inventory. An inventory is not a public source offer, retention commitment
or approval. Do not activate this candidate at the root or replace the release
workflows as part of an API-only review.