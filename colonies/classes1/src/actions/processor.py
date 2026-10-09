import httpx

from src.flux.client import FluxClient

DIRECTION_DELTAS = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}


async def process_action(
    action: dict, agent_id: str, x: int, y: int, facing: str, flux: FluxClient
) -> tuple[str, int, int, str, str | None]:
    """Validate and apply an agent action. Returns (feedback, new_x, new_y, new_facing, new_internal_state)."""
    try:
        action_type = action.get("action")

        if action_type == "move":
            return await _handle_move(action, agent_id, x, y, flux)

        elif action_type == "turn":
            return await _handle_turn(action, agent_id, x, y, flux)

        elif action_type == "interact":
            return await _handle_interact(action, agent_id, x, y, facing, flux)

        elif action_type == "wait":
            return "You pause and observe your surroundings.", x, y, facing, None

        else:
            return "Unknown action.", x, y, facing, None

    except Exception as e:
        print(f"[processor] Unexpected error: {e}")
        return "Something went wrong.", x, y, facing, None


async def _handle_move(
    action: dict, agent_id: str, x: int, y: int, flux: FluxClient
) -> tuple[str, int, int, str, None]:
    direction = action.get("direction", "")
    dx, dy = DIRECTION_DELTAS.get(direction, (0, 0))
    tx, ty = x + dx, y + dy

    try:
        tile = await flux.get_entity(f"world/tile/{tx}/{ty}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return "You can't move there — nothing exists in that direction.", x, y, direction, None
        raise

    props = tile.get("properties", {})
    passable = props.get("passable", False)

    if not passable:
        terrain_type = props.get("terrain_type", "obstacle")
        return f"You can't move there — {terrain_type}.", x, y, direction, None

    await flux.publish_event(
        stream="agent.state",
        source=agent_id,
        entity_id=f"agent/{agent_id}",
        properties={"x": tx, "y": ty, "facing": direction},
    )
    return f"You moved {direction}.", tx, ty, direction, None


async def _handle_turn(
    action: dict, agent_id: str, x: int, y: int, flux: FluxClient
) -> tuple[str, int, int, str, None]:
    direction = action.get("direction", "")
    await flux.publish_event(
        stream="agent.state",
        source=agent_id,
        entity_id=f"agent/{agent_id}",
        properties={"facing": direction},
    )
    return f"You turn to face {direction}.", x, y, direction, None


async def _handle_interact(
    action: dict, agent_id: str, x: int, y: int, facing: str, flux: FluxClient
) -> tuple[str, int, int, str, str | None]:
    object_id = action.get("object_id", "")

    try:
        obj = await flux.get_entity(f"world/object/{object_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"You can't interact with {object_id} — it doesn't exist.", x, y, facing, None
        raise

    props = obj.get("properties", {})

    if not props.get("interactable", False):
        return "You can't interact with that.", x, y, facing, None

    obj_x = props.get("x", 0)
    obj_y = props.get("y", 0)
    distance = abs(x - obj_x) + abs(y - obj_y)

    object_type = props.get("type", object_id)

    # Water interaction
    if object_type == "water":
        if distance > 1:
            return "You are too far away to reach the water.", x, y, facing, None
        return "You reach down and touch the cool water. It is still and clear.", x, y, facing, "refreshed"

    if distance > 1:
        return f"You are too far away to interact with {object_id}.", x, y, facing, None

    if props.get("opened", False):
        return f"The {object_type} is already open.", x, y, facing, None

    contents = props.get("contents", "")
    if contents in ("gold coin", "old key", "book"):
        new_state = "excited"
        feedback = f"You opened the {object_type} and found a {contents}!"
    elif contents in ("trash", "bones"):
        new_state = "disappointed"
        feedback = f"You opened the {object_type} and found {contents}. How disappointing."
    else:
        new_state = None
        feedback = f"You opened the {object_type}. It is empty."

    await flux.publish_event(
        stream="world",
        source=agent_id,
        entity_id=f"world/object/{object_id}",
        properties={"opened": True},
    )
    return feedback, x, y, facing, new_state
