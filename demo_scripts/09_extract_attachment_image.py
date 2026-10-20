"""Extract and display the SlidePreview attachment from the well-plate CZI."""

from argparse import ArgumentParser
from pathlib import Path

import matplotlib.pyplot as plt

from pylibCZIrw import czi


def main() -> None:
    """Extract and display the SlidePreview attachment from the well-plate CZI."""
    basedir = Path(__file__).resolve().parents[1]
    filepath = basedir / "test_data/well96-A4-6_B16-18_CH=2.czi"
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=basedir / "output/attachments",
        help="Directory for the extracted embedded CZI (default: output/attachments).",
    )
    args = parser.parse_args()

    with czi.open_czi(str(filepath)) as reader:
        attachments = reader.list_attachments()
        for attachment in attachments:
            print(attachment)
        previews = [attachment for attachment in attachments if attachment.name == "SlidePreview"]
        if len(previews) != 1:
            raise ValueError(f"Expected one SlidePreview attachment, found {len(previews)}.")
        preview = previews[0]
        raw = reader.read_attachment(preview.index)
        pixels = reader.read_attachment_image(preview.index)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{filepath.stem}_SlidePreview.czi"
    output_path.write_bytes(raw)
    print("Extracted embedded CZI:", output_path)
    print("Payload bytes:", len(raw))
    print("Preview shape / dtype:", pixels.shape, pixels.dtype)

    figure, axis = plt.subplots(figsize=(10, 7))
    image = axis.imshow(pixels, cmap="gray", interpolation="nearest", vmin=0, vmax=255)
    axis.set_title(f"{filepath.name}\n{preview.name}")
    axis.set_xlabel("Image X (pixels)")
    axis.set_ylabel("Image Y (pixels)")
    figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
