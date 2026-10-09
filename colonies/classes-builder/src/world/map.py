import random
from dataclasses import dataclass, field

TERRAIN_PASSABLE = {
    "floor": True,
    "wall": False,
    "water": False,
    "forest": True,
}

INTERIOR_WEIGHTS = ["floor"] * 60 + ["wall"] * 15 + ["water"] * 10 + ["forest"] * 15


@dataclass
class TileData:
    terrain_type: str
    passable: bool
    x: int
    y: int


@dataclass
class WorldMap:
    width: int
    height: int
    seed: int
    tiles: dict = field(default_factory=dict)  # (x, y) -> TileData


def generate_map(width: int = 20, height: int = 20, seed: int = None) -> WorldMap:
    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    rng = random.Random(seed)
    tiles = {}

    for x in range(width):
        for y in range(height):
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                terrain = "wall"
            else:
                terrain = rng.choice(INTERIOR_WEIGHTS)

            tiles[(x, y)] = TileData(
                terrain_type=terrain,
                passable=TERRAIN_PASSABLE[terrain],
                x=x,
                y=y,
            )

    return WorldMap(width=width, height=height, seed=seed, tiles=tiles)


def find_spawn_point(world_map: WorldMap, clear_radius: int = 2) -> tuple[int, int]:
    cx = world_map.width // 2
    cy = world_map.height // 2

    # All interior passable tiles sorted by Manhattan distance from center
    candidates = [
        (abs(x - cx) + abs(y - cy), x, y)
        for (x, y), tile in world_map.tiles.items()
        if tile.passable
        and x > 0 and x < world_map.width - 1
        and y > 0 and y < world_map.height - 1
    ]
    candidates.sort()

    # Find first tile where all tiles within clear_radius are also passable
    for _, x, y in candidates:
        clear = all(
            world_map.tiles.get((nx, ny), TileData("", False, nx, ny)).passable
            for nx in range(x - clear_radius, x + clear_radius + 1)
            for ny in range(y - clear_radius, y + clear_radius + 1)
            if abs(nx - x) + abs(ny - y) <= clear_radius
        )
        if clear:
            return (x, y)

    # Fallback: any passable interior tile closest to center
    if candidates:
        return (candidates[0][1], candidates[0][2])

    # Last resort
    return (cx, cy)
