"""Inspect stored subblocks without decoding their pixel payloads."""

from pathlib import Path

from pylibCZIrw import czi


def main() -> None:
    """Inspect stored subblocks without decoding their pixel payloads."""
    filepath = (
        Path(__file__).resolve().parents[1]
        / "pylibCZIrw/tests/integration/test_data/synthetic/stored_sparse_coordinates.czi"
    )

    with czi.open_czi(str(filepath)) as reader:
        # The directory index, native M value and level token are different IDs.
        blocks = reader.list_subblocks()

        print("Total stored subblocks:", reader.count_subblocks())
        print("Stored subblocks by native scene:", reader.count_subblocks_by_scene())
        print("Stored subblocks in scene 8:", reader.count_subblocks(scene=8))

        # Filters intersect; omitted coordinates are wildcards, not zero.
        selected = reader.list_subblocks(m_index=37, scene=8, plane={"C": 11})

    # These immutable snapshots remain usable after the reader closes.
    for block in blocks:
        print(f"Index={block.index}, M={block.m_index}, coordinates={dict(block.coordinates)}")
        print(f"  logical XYWH={block.logical_rect}, stored YX={block.stored_shape}")
        print(f"  level token={block.level_id}, pixel type={block.pixel_type}, codec={block.compression_mode}")
    print("Filtered directory indices:", [block.index for block in selected])


if __name__ == "__main__":
    main()
