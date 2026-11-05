"""Count stored subblocks overall, per scene and within a selected plane/level."""

from pathlib import Path

from pylibCZIrw import czi


def main() -> None:
    """Count stored subblocks overall, per scene and within a selected plane/level."""
    filepath = (
        Path(__file__).resolve().parents[1]
        / "pylibCZIrw/tests/integration/test_data/synthetic/stored_sparse_coordinates.czi"
    )

    with czi.open_czi(str(filepath)) as reader:
        # Unfiltered counts include all stored scenes, planes and levels.
        print("Total stored subblocks:", reader.count_subblocks())

        # Scene IDs stay sparse (2 and 8 here); absent S would use the None key.
        print("Stored subblocks by scene:", reader.count_subblocks_by_scene())
        print("Stored subblocks in scene 8:", reader.count_subblocks(scene=8))

        # M=37 repeats in both scenes, so it still counts as two stored entries.
        print("M=37 across all scenes:", reader.count_subblocks(m_index=37))

        # Discover the level token rather than assuming zero is full resolution.
        plane = {"T": 9, "C": 11, "Z": 13}
        selected = reader.list_subblocks(scene=8, plane=plane)[0]
        count = reader.count_subblocks(scene=8, plane=plane, m_index=37, level=selected.level_id)
        print("Scene 8, selected plane/M/level:", count)
        print(
            "Filtered counts by scene:",
            reader.count_subblocks_by_scene(plane=plane, level=selected.level_id),
        )

        # No matches gives zero, or an empty dictionary for per-scene counts.
        print("Missing scene:", reader.count_subblocks(scene=99))
        print("Missing scene counts:", reader.count_subblocks_by_scene(scene=99))


if __name__ == "__main__":
    main()
