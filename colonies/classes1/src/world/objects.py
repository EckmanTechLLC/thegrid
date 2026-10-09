import random
from dataclasses import dataclass, field

from src.world.map import WorldMap

OBJECT_DEFINITIONS = [
    {"type": "rock", "count": 5, "interactable": False},
    {"type": "tree", "count": 5, "interactable": False},
    {"type": "chest", "count": 3, "interactable": True},
]


CHEST_CONTENTS = ["gold coin", "old key", "book", "trash", "bones"]
CHEST_REWARDS = {"gold coin", "old key", "book"}
CHEST_DIRT = {"trash", "bones"}


@dataclass
class WorldObject:
    object_id: str
    type: str
    x: int
    y: int
    interactable: bool
    contents: str = ""


def place_objects(world_map: WorldMap, seed: int) -> list[WorldObject]:
    rng = random.Random(seed + 1)  # offset to avoid duplicate sequence from map gen

    valid_tiles = [
        (x, y)
        for (x, y), tile in world_map.tiles.items()
        if tile.passable
        and x > 0
        and x < world_map.width - 1
        and y > 0
        and y < world_map.height - 1
    ]

    occupied: set[tuple[int, int]] = set()
    objects: list[WorldObject] = []
    counters: dict[str, int] = {}

    for definition in OBJECT_DEFINITIONS:
        obj_type = definition["type"]
        interactable = definition["interactable"]
        counters[obj_type] = 0

        for _ in range(definition["count"]):
            available = [t for t in valid_tiles if t not in occupied]
            if not available:
                break
            tile = rng.choice(available)
            occupied.add(tile)
            counters[obj_type] += 1
            object_id = f"{obj_type}-{counters[obj_type]}"
            contents = rng.choice(CHEST_CONTENTS) if obj_type == "chest" else ""
            objects.append(
                WorldObject(
                    object_id=object_id,
                    type=obj_type,
                    x=tile[0],
                    y=tile[1],
                    interactable=interactable,
                    contents=contents,
                )
            )

    return objects
