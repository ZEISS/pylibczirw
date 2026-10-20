"""Inspect attachment identities, extract bytes, and display explicit CZI images."""

from pathlib import Path

import matplotlib.pyplot as plt

from pylibCZIrw import czi


def main() -> None:
    """Inspect attachment identities, extract bytes, and display explicit CZI images."""
    filepath = (
        Path(__file__).resolve().parents[1]
        / "pylibCZIrw/tests/integration/test_data/synthetic/literal_slidepreview_cases.czi"
    )
    with czi.open_czi(str(filepath)) as reader:
        attachments = reader.list_attachments()
        for attachment in attachments:
            print(attachment)
        label = reader.read_label()
        previews = [info for info in attachments if info.name == "SlidePreview"]
        # This fixture has duplicate names: explicitly choose an attachment index.
        preview = reader.read_preview(index=previews[1].index)
        raw = reader.read_attachment(previews[1].index)
        unknown = next(info for info in attachments if info.content_file_type == "OTHER")
        print("Unknown-format raw bytes:", reader.read_attachment(unknown.index))

    print("Selected preview payload bytes:", len(raw))
    if label is None or preview is None:
        raise ValueError("This example requires the fixture's label and preview images.")
    print("Label / preview:", label.shape, label.dtype, preview.shape, preview.dtype)
    # Returned bytes and image buffers remain valid after the parent reader closes.
    figure, axes = plt.subplots(1, 2, figsize=(9, 4))
    for axis, values, title in zip(axes, (label, preview), ("Embedded CZI label", "Selected slide preview")):
        image = axis.imshow(values, cmap="gray", interpolation="nearest")
        axis.set_title(title)
        axis.set_xlabel("Image X (pixels)")
        axis.set_ylabel("Image Y (pixels)")
        figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
