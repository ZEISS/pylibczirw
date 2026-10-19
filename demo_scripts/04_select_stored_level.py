"""Read a stored lower-resolution subblock without composing or resampling."""

from pathlib import Path

import matplotlib.pyplot as plt

from pylibCZIrw import czi


def main() -> None:
    filepath = (
        Path(__file__).resolve().parents[1]
        / "pylibCZIrw/tests/integration/test_data/synthetic/stored_levels_same_m37.czi"
    )

    with czi.open_czi(str(filepath)) as reader:
        # M, scene and plane are identical in both stored levels of this fixture.
        blocks = reader.list_subblocks(m_index=37, scene=0, plane={"C": 0})
        for block in blocks:
            print("Level token / stored YX shape:", block.level_id, block.stored_shape)

        # Choose by stored geometry, not token order: level IDs are opaque.
        # Reuse tokens only within this reader session; None means unclassified.
        selected = min(blocks, key=lambda block: block.stored_shape[0] * block.stored_shape[1])
        pixels = reader.read_subblock_by_m(37, scene=0, plane={"C": 0}, level=selected.level_id)

    # These are the lower level's original pixels, not a resampled level-zero image.
    print("Selected stored bitmap:", pixels.shape, pixels.dtype)
    print("First stored value:", pixels[0, 0])

    # Display the stored grayscale pixels; ownership survives reader close.
    figure, axis = plt.subplots()
    image = axis.imshow(pixels, cmap="gray", interpolation="nearest")
    axis.set_title(f"Stored level {selected.level_id}, M={selected.m_index}")
    axis.set_xlabel("Stored X (pixels)")
    axis.set_ylabel("Stored Y (pixels)")
    figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
