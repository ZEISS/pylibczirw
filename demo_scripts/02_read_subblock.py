"""Read one stored bitmap by M and directory index, then display both results."""

from pathlib import Path

import matplotlib.pyplot as plt

from pylibCZIrw import czi


def main() -> None:
    filepath = Path(__file__).resolve().parents[1] / "test_data/Brain_CH=3_M=25.czi"

    # define the desired M-Tile index and channel
    m: int = 12
    c: int = 0

    with czi.open_czi(str(filepath)) as reader:
        # Read by M directly, without first requesting a descriptor.
        pixels_by_m = reader.read_subblock_by_m(m_index=m, scene=0, plane={"C": c})

        block = reader.list_subblocks(scene=0, m_index=m, plane={"C": c})[0]

        # Use the file-local directory index, NOT M or the filtered list position.
        pixels = reader.read_subblock(index=block.index)

    # Grayscale is YX; color is YXA in native BGR order, without dtype conversion.
    # Pixels are not stitched, resampled or validity-masked; placement is separate.
    print("Directory index / M:", block.index, block.m_index)
    print("Logical placement (x, y, width, height):", block.logical_rect)
    print("Stored shape / dtype:", pixels.shape, pixels.dtype)
    print("Direct M shape / dtype:", pixels_by_m.shape, pixels_by_m.dtype)

    # Both arrays retain their bitmap owners and stay valid after reader close.
    print("First five pixels:", pixels[0, :5])
    print("First five direct:", pixels_by_m[0, :5])

    # This fixture is grayscale; imshow scales its native uint16 values for display.
    # Axes use stored pixel coordinates, not the separate logical placement above.
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), sharex=True, sharey=True)
    minimum, maximum = pixels.min(), pixels.max()
    for axis, values, title in zip(
        axes,
        (pixels_by_m, pixels),
        (f"Direct M={block.m_index}", f"Directory index {block.index}"),
    ):
        image = axis.imshow(values, cmap="gray", interpolation="nearest", vmin=minimum, vmax=maximum)
        axis.set_title(title)
        axis.set_xlabel("Stored X (pixels)")
        axis.set_ylabel("Stored Y (pixels)")
        figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
