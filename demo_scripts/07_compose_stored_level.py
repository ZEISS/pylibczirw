"""Discover stored levels and compose exact members with an explicit logical ROI."""

from pathlib import Path

import matplotlib.pyplot as plt

from pylibCZIrw import czi


def stored_area(level: czi.StoredLevelInfo) -> int:
    """Return renderable stored geometry without assuming all levels are supported."""
    if level.output_shape is None:
        raise ValueError("This example requires renderable stored-level geometry.")
    return level.output_shape[0] * level.output_shape[1]


def main() -> None:
    """Discover stored levels and compose exact members with an explicit logical ROI."""
    folder = Path(__file__).resolve().parents[1] / "pylibCZIrw/tests/integration/test_data/synthetic"
    with czi.open_czi(str(folder / "stored_levels_same_m37.czi")) as reader:
        levels = reader.list_stored_levels(scene=0, plane={"T": 0, "C": 0, "Z": 0})
        for level in levels:
            print("Level / YX downsample / output shape:", level.level_id, level.downsample, level.output_shape)
        # Choose by reported geometry, never by the catalog token's numerical order.
        selected = min(levels, key=stored_area)
        pixels = reader.read_stored_level(selected.level_id, scene=0, plane={"T": 0, "C": 0, "Z": 0})
        # ROI uses raw level-0 XYWH; nondivisible extents drop their remainders.
        roi_pixels = reader.read_stored_level(selected.level_id, scene=0, plane={"C": 0}, roi=(8, 8, 33, 17))
    with czi.open_czi(str(folder / "literal_tiles_with_gap.czi")) as reader:
        level = reader.list_stored_levels()[0]
        composed = reader.read_stored_level(level.level_id)

    print("Selected / ROI / gapped composition shapes:", pixels.shape, roi_pixels.shape, composed.shape)
    figure, axes = plt.subplots(1, 3, figsize=(12, 4))
    for axis, values, title in zip(
        axes, (pixels, roi_pixels, composed), ("Exact reduced level", "Reduced-level ROI", "Tiles and black gap")
    ):
        image = axis.imshow(values, cmap="gray", interpolation="nearest")
        axis.set_title(title)
        axis.set_xlabel("Stored X (pixels)")
        axis.set_ylabel("Stored Y (pixels)")
        figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
