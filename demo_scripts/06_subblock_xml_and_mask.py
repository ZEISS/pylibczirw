"""Read raw XML and an explicit validity mask without changing direct pixels."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pylibCZIrw import czi


def main() -> None:
    filepath = (
        Path(__file__).resolve().parents[1]
        / "pylibCZIrw/tests/integration/test_data/synthetic/literal_valid_mask_v2.czi"
    )
    with czi.open_czi(str(filepath)) as reader:
        block = reader.list_subblocks()[0]
        xml = reader.read_subblock_metadata_xml(block.index)
        mask = reader.read_subblock_mask(block.index)
        pixels = reader.read_subblock(block.index)

    print("Raw subblock XML:", xml)
    print("Stored mask:", mask.shape, mask.dtype, "valid pixels:", np.count_nonzero(mask))
    # Applying a mask here is an explicit choice; read_subblock returns raw pixels.
    masked = np.where(mask, pixels, 0)
    figure, axes = plt.subplots(1, 3, figsize=(12, 4))
    for axis, values, title in zip(
        axes, (pixels, mask, masked), ("Raw stored pixels", "Stored validity mask", "Explicitly masked pixels")
    ):
        image = axis.imshow(values, cmap="gray", interpolation="nearest")
        axis.set_title(title)
        axis.set_xlabel("Stored X (pixels)")
        axis.set_ylabel("Stored Y (pixels)")
        figure.colorbar(image, ax=axis, label="Valid" if values is mask else "Intensity")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
