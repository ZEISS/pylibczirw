"""Create, edit and reopen one CZI with the bounded document facade."""

from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib.pyplot as plt
import numpy as np

from pylibCZIrw.czi import CziDocument


def main() -> None:
    """Create, edit and reopen one CZI with the bounded document facade."""
    rows, columns = np.indices((128, 192))
    expected = ((211 * rows + 37 * columns) % 65536).astype(np.uint16)

    with TemporaryDirectory(prefix="czirw-document-") as directory:
        filepath = Path(directory) / "workflow.czi"
        with CziDocument.create(filepath, compression_options="zstd1:ExplicitLevel=1") as document:
            document.write(expected[..., None])
            document.write_metadata(document_name="Facade example", scale_x=0.25, scale_y=0.25)

        with CziDocument.edit(filepath) as document:
            with document.edit_session() as builder:
                builder.set_general_document_info(name="Edited facade example")
            if "Edited facade example" not in document.read_metadata_xml():
                raise AssertionError()

        with CziDocument.open(filepath) as document:
            info = document.list_subblocks()[0]
            pixels = document.read_subblock(info.index)
        if not document.closed:
            raise AssertionError()

    np.testing.assert_array_equal(pixels, expected)
    print("Retained pixels:", pixels.shape, pixels.dtype, "placement:", info.logical_rect)
    figure, axis = plt.subplots(figsize=(7, 4.5))
    image = axis.imshow(pixels, cmap="gray", interpolation="nearest")
    # Standalone examples intentionally repeat plot labels and presentation.
    # pylint: disable=duplicate-code
    axis.set_title("CziDocument: compressed round trip after metadata edit")
    axis.set_xlabel("Image X (pixels)")
    axis.set_ylabel("Image Y (pixels)")
    figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()
    # pylint: enable=duplicate-code


if __name__ == "__main__":
    main()
