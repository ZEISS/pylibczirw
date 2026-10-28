# New Reader API Demos

Short examples for the descriptor, stored-pixel, metadata, attachment and
document APIs.
They use synthetic fixtures or local files in `test_data/` and resolve paths relative
to the scripts rather than the working directory. The pixel display demos
require Matplotlib; the other demos need no plotting packages or fixture downloads.

- [01_list_subblocks.py](01_list_subblocks.py): inspect immutable descriptors,
  count stored subblocks overall and per scene, and filter native scene/plane/M
  coordinates without loading pixels.
- [02_read_subblock.py](02_read_subblock.py): read one directory entry and use its
  array and placement after closing the reader, then display its grayscale
  pixels with an intensity colorbar.
- [03_read_by_m.py](03_read_by_m.py): observe an ambiguous M selection, then narrow
  it to exactly one stored bitmap and display its pixels.
- [04_select_stored_level.py](04_select_stored_level.py): discover a token in the
  subblock listing and display that stored bitmap without fallback or resampling.
- [05_count_subblocks.py](05_count_subblocks.py): count stored entries overall,
  per native scene and with plane/M/level filters; show repeated M values and
  empty-match results without reading pixels.
- [06_subblock_xml_and_mask.py](06_subblock_xml_and_mask.py): retrieve raw XML,
  display raw pixels and the stored mask, then explicitly apply that mask.
- [07_compose_stored_level.py](07_compose_stored_level.py): discover actual stored
  geometry, read a reduced level and logical ROI, and display composed tile gaps.
- [08_attachment_images.py](08_attachment_images.py): list attachment identities,
  extract raw bytes, and display the label and an explicitly selected preview.
- [09_extract_attachment_image.py](09_extract_attachment_image.py): extract the
  `SlidePreview` from `test_data/well96-A4-6_B16-18_CH=2.czi` as a standalone CZI
  in `output/attachments/` and display its grayscale pixels. This demo writes an
  output file; use `--output-dir PATH` to choose another directory.
- [10_document_workflow.py](10_document_workflow.py): create a compressed CZI in
  a temporary directory, edit metadata, reopen through `CziDocument` and display
  retained pixels after close. It does not modify fixture files.

## Installed-Wheel Setup

Use a separate environment with a wheel containing these interfaces. In the
commands below, `$python` names its interpreter and `$wheel` names that wheel.
Install the wheel and plotting dependency before running the examples below:

```powershell
& $python -I -m pip install --only-binary=:all: $wheel matplotlib
```

Demos 02 and 09 require their named local acquisition files. See the
[fixture policy](../doc/fixture_policy.md) for the synthetic test inputs.

## Interactive Runs

Demo 10 requires a wheel providing `CziDocument`. Use a separate environment
instead of replacing an installation that must be preserved. From the
repository root, with that environment's interpreter as `$python`:

```powershell
& $python -m pip install matplotlib
& $python demo_scripts/01_list_subblocks.py
& $python demo_scripts/02_read_subblock.py
& $python demo_scripts/03_read_by_m.py
& $python demo_scripts/04_select_stored_level.py
& $python demo_scripts/05_count_subblocks.py
& $python demo_scripts/06_subblock_xml_and_mask.py
& $python demo_scripts/07_compose_stored_level.py
& $python demo_scripts/08_attachment_images.py
& $python demo_scripts/09_extract_attachment_image.py
& $python demo_scripts/10_document_workflow.py
```

Demos 02, 03, 04, 06, 07, 08, 09 and 10 open plot windows; close them to finish.

For your own CZI, change `filepath` and the fixture-specific selectors in each
script. Inspect its descriptors first: M is not a directory index, omitted
coordinates are wildcards, and level tokens are not resolution ordinals.

Counts include every matching stored directory entry, including repeated M
values across planes and levels. They are not counts of unique tile positions.
Use plane and level filters to narrow the count; an absent S coordinate is
grouped under `None` rather than scene zero.

Pixels retain their native dtype and BGR order. Grayscale arrays are YX, color
arrays are YXA. Convert BGR to RGB explicitly when displaying a color image.
Raw direct reads do not apply validity masks. XML/mask reads fetch the selected
stored payload without decoding pixels; they are not XML-only I/O. Attachment
raw/image reads materialize the selected payload in RAM, with additional memory
for bytes, decoded pixels and copies. They are not streaming or zero-copy reads.
Only embedded CZI attachments with one supported full-resolution image plane
are decoded. Unknown formats remain available as raw bytes.
