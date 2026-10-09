from src.flux.client import FluxClient
from src.perception.models import AgentState, PerceptionResult

PERCEPTION_RADIUS = 5

# Maps facing direction to (dx, dy) for "ahead"
_FACING_VECTOR = {
    "north": (0, -1),
    "south": (0, 1),
    "east":  (1, 0),
    "west":  (-1, 0),
}

# Maps (dx_sign, dy_sign) to cardinal label — dominant axis wins
_CARDINAL_LABELS = {
    (0,  -1): "north",
    (0,   1): "south",
    (1,   0): "east",
    (-1,  0): "west",
}


def _manhattan_distance(ax: int, ay: int, tx: int, ty: int) -> int:
    return abs(tx - ax) + abs(ty - ay)


def _cardinal_direction(ax: int, ay: int, tx: int, ty: int) -> str:
    """Return dominant cardinal direction from (ax, ay) to (tx, ty)."""
    dx = tx - ax
    dy = ty - ay
    if abs(dx) >= abs(dy):
        return "east" if dx >= 0 else "west"
    else:
        return "north" if dy < 0 else "south"


def _relative_direction(agent: AgentState, tx: int, ty: int) -> str:
    """Return relative direction (ahead/behind/left/right) from agent to (tx, ty)."""
    cardinal = _cardinal_direction(agent.x, agent.y, tx, ty)
    facing = agent.facing

    if cardinal == facing:
        return "ahead"

    opposites = {"north": "south", "south": "north", "east": "west", "west": "east"}
    if cardinal == opposites[facing]:
        return "behind"

    # Clockwise order: north -> east -> south -> west -> north
    clockwise = ["north", "east", "south", "west"]
    fi = clockwise.index(facing)
    ci = clockwise.index(cardinal)
    diff = (ci - fi) % 4
    return "right" if diff == 1 else "left"


def _tile_distance_label(dist: int) -> str:
    return "1 tile" if dist == 1 else f"{dist} tiles"


GRID_RADIUS = 5  # 11x11 grid


def _build_surroundings_grid(
    agent: AgentState,
    tile_map: dict[tuple[int, int], dict],
    all_objects: list[dict],
) -> list[str]:
    # Build object lookup by (x, y) — exclude water objects (shown via terrain)
    obj_map: dict[tuple[int, int], str] = {}
    for entity in all_objects:
        props = entity.get("properties", {})
        ex = props.get("x")
        ey = props.get("y")
        obj_type = props.get("type", "")
        if ex is not None and ey is not None and obj_type != "water":
            obj_map[(ex, ey)] = obj_type

    rows = []
    for dy in range(-GRID_RADIUS, GRID_RADIUS + 1):  # north to south
        row = []
        for dx in range(-GRID_RADIUS, GRID_RADIUS + 1):  # west to east
            wx, wy = agent.x + dx, agent.y + dy
            if dx == 0 and dy == 0:
                row.append("@")
            elif (wx, wy) not in tile_map:
                row.append("?")
            else:
                props = tile_map[(wx, wy)]
                terrain = props.get("terrain_type", "floor")
                if (wx, wy) in obj_map:
                    ot = obj_map[(wx, wy)]
                    if ot == "chest":
                        row.append("C")
                    elif ot == "rock":
                        row.append("R")
                    elif ot == "tree":
                        row.append("T")
                    else:
                        row.append(".")
                elif terrain == "wall":
                    row.append("#")
                elif terrain == "water":
                    row.append("~")
                else:
                    row.append(".")
        rows.append(" ".join(row))
    return rows


async def build_perception(agent: AgentState, flux: FluxClient) -> PerceptionResult:
    # --- Fetch all tiles and objects in one call each ---
    all_tiles = await flux.get_all_entities(prefix="world/tile")
    all_objects = await flux.get_all_entities(prefix="world/object")

    # --- Build tile lookup by (x, y) ---
    tile_map: dict[tuple[int, int], dict] = {}
    current_terrain = None

    for entity in all_tiles:
        props = entity.get("properties", {})
        ex = props.get("x")
        ey = props.get("y")
        if ex is None or ey is None:
            continue
        tile_map[(ex, ey)] = props
        if ex == agent.x and ey == agent.y:
            current_terrain = props.get("terrain_type", "unknown")

    # --- Nearby objects ---
    nearby_objects: list[tuple[int, str, str, str, bool]] = []  # (dist, direction, obj_id, type, interactable)

    for entity in all_objects:
        props = entity.get("properties", {})
        ex = props.get("x")
        ey = props.get("y")
        if ex is None or ey is None:
            continue
        dist = _manhattan_distance(agent.x, agent.y, ex, ey)
        if dist <= PERCEPTION_RADIUS:
            obj_type = props.get("type", "object")
            if obj_type == "water" and dist > 1:
                continue
            direction = _cardinal_direction(agent.x, agent.y, ex, ey)
            full_id = entity.get("id", "unknown")
            obj_id = full_id.split("/")[-1] if "/" in full_id else full_id
            interactable = props.get("interactable", False)
            nearby_objects.append((dist, direction, obj_id, obj_type, interactable))

    nearby_objects.sort(key=lambda x: x[0])

    # --- Build description ---
    lines = []

    lines.append(f"You are facing {agent.facing}.")
    lines.append(f"You are standing on {current_terrain or 'unknown terrain'}.")
    lines.append("")

    # Objects section
    lines.append("Nearby objects:")
    if nearby_objects:
        for dist, direction, obj_id, obj_type, interactable in nearby_objects:
            label = _tile_distance_label(dist)
            suffix = f" (interactable, id: {obj_id})" if interactable else " (not interactable)"
            lines.append(f"- A {obj_type} {label} {direction}{suffix}")
    else:
        lines.append("No objects nearby.")
    lines.append("")

    # Agent state section
    lines.append("Your state:")
    lines.append(f"- Feeling: {agent.internal_state or 'neutral'}")
    if agent.last_action:
        lines.append(f"- Last action: {agent.last_action}")
    if agent.last_feedback:
        lines.append(f"- Result: {agent.last_feedback}")
    lines.append("")

    # Available actions (hardcoded for now)
    lines.append("Available actions:")
    lines.append("- move [north|south|east|west]")
    lines.append("- turn [north|south|east|west]")
    lines.append("- interact [object_id] — interact with an adjacent object or water tile")
    lines.append("- wait")

    description = "\n".join(lines)

    raw = {
        "current_terrain": current_terrain,
        "nearby_objects": [(d, dr, oid, ot, ia) for d, dr, oid, ot, ia in nearby_objects],
    }

    return PerceptionResult(agent_id=agent.agent_id, description=description, raw=raw)
