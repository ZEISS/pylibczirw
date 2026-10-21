"""Resolve repeated M values with scene and plane filters before reading pixels."""

from pathlib import Path

import matplotlib.pyplot as plt

from pylibCZIrw import czi


def main() -> None:
    """Resolve repeated M values with scene and plane filters before reading pixels."""
    filepath = (
        Path(__file__).resolve().parents[1]
        / "pylibCZIrw/tests/integration/test_data/synthetic/stored_sparse_coordinates.czi"
    )

    with czi.open_czi(str(filepath)) as reader:
        # This fixture repeats M=37 across different scenes and T/C/Z coordinates.
        # Zero or multiple matches raise ValueError before reading any payload.
        try:
            reader.read_subblock_by_m(37)
        except ValueError as error:
            print("Expected ambiguous selection:", error)

        # Scene selects native S; plane holds native T/C/Z (not packed positions).
        pixels = reader.read_subblock_by_m(m_index=37, scene=8, plane={"T": 9, "C": 11, "Z": 13})
        print("Unique M selection:", pixels.shape, pixels.dtype)
        print("First five pixels:", pixels[0, :5])

    # Display the selected stored pixels; the array remains valid after close.
    # This fixture is grayscale, and axes refer to its stored pixel coordinates.
    figure, axis = plt.subplots()
    image = axis.imshow(pixels, cmap="gray", interpolation="nearest")
    # Standalone examples intentionally repeat plot labels and presentation.
    # pylint: disable=duplicate-code
    axis.set_title("M=37, S=8, T=9, C=11, Z=13")
    axis.set_xlabel("Stored X (pixels)")
    axis.set_ylabel("Stored Y (pixels)")
    figure.colorbar(image, ax=axis, label="Intensity")
    figure.tight_layout()
    plt.show()
    # pylint: enable=duplicate-code


if __name__ == "__main__":
    main()
