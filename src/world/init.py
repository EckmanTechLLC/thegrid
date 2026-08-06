import time

from src.flux.client import FluxClient
from src.world.map import generate_map, find_spawn_point
from src.world.objects import place_objects


async def initialize_world(flux: FluxClient, width: int = 20, height: int = 20) -> tuple[int, int]:
    # Always clean slate — delete all existing world entities before publishing
    await flux.delete_all_entities("world")

    world_map = generate_map(width=width, height=height)
    objects = place_objects(world_map, seed=world_map.seed)
    spawn_x, spawn_y = find_spawn_point(world_map)

    # Publish world metadata
    await flux.publish_event(
        stream="world",
        source="world-init",
        entity_id="world/meta",
        properties={
            "width": world_map.width,
            "height": world_map.height,
            "seed": world_map.seed,
            "generated_at": int(time.time() * 1000),
            "spawn_x": spawn_x,
            "spawn_y": spawn_y,
        },
    )

    # Publish all tiles
    for (x, y), tile in world_map.tiles.items():
        await flux.publish_event(
            stream="world",
            source="world-init",
            entity_id=f"world/tile/{x}/{y}",
            properties={
                "terrain_type": tile.terrain_type,
                "passable": tile.passable,
                "x": x,
                "y": y,
            },
        )

    # Publish all objects
    for obj in objects:
        await flux.publish_event(
            stream="world",
            source="world-init",
            entity_id=f"world/object/{obj.object_id}",
            properties={
                "type": obj.type,
                "x": obj.x,
                "y": obj.y,
                "interactable": obj.interactable,
                "contents": obj.contents,
            },
        )

    # Publish water tiles as interactable objects
    for (x, y), tile in world_map.tiles.items():
        if tile.terrain_type == "water":
            await flux.publish_event(
                stream="world",
                source="world-init",
                entity_id=f"world/object/water-{x}-{y}",
                properties={
                    "type": "water",
                    "x": x,
                    "y": y,
                    "interactable": True,
                },
            )

    tile_count = len(world_map.tiles)
    object_count = len(objects)
    print(f"World initialized: {width}x{height}, {tile_count} tiles, {object_count} objects, spawn: ({spawn_x}, {spawn_y})")
    return (spawn_x, spawn_y)
