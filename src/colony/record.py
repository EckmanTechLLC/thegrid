"""Record a colony run to a compact JSON file for playback.

    python -m colony.record --ticks 6000 --every 40 --out run.json

Frames are quantised hard on purpose: the point is to watch the field move,
not to reconstruct exact energies. A 32x32 world at 150 frames lands around
200KB, which a browser can hold entirely in memory and scrub through.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .colony import Colony
from .isa import ISA, build_ancestor
from .mutation import (
    LLMMutator,
    RandomMutator,
    anthropic_caller,
    fixture_caller,
    ollama_caller,
)
from .tasks import TaskEnvironment
from .world import World, WorldConfig

# 32 symbols: three digits encode maps up to 32,768 tiles.
ALPHABET = "0123456789abcdefghijklmnopqrstuv"
# Genomes get a wider alphabet than positions: the ISA has outgrown 32
# opcodes, and op % 32 rendered write/post/fetch/locate as 0/1/2/3.
GENOME_ALPHABET = ALPHABET + "wxyzABCDEFGHIJKLMNOPQRSTUVWXYZ@#"


def encode_positions(colony: Colony, width: int) -> str:
    """Four characters per organism: three for tile index, one for lineage."""
    out = []
    for organism in colony.organisms:
        index = organism.y * width + organism.x
        out.append(ALPHABET[(index >> 10) & 31] + ALPHABET[(index >> 5) & 31]
                   + ALPHABET[index & 31]
                   + ALPHABET[organism.lineage % 32])
    return "".join(out)


def encode_genome(genome: list[int]) -> str:
    """One character per instruction. Genomes are short; this stays tiny."""
    return "".join(GENOME_ALPHABET[op % len(GENOME_ALPHABET)] for op in genome)


def encode_energy(world: World) -> str:
    capacity = world.config.tile_capacity
    return "".join(
        str(min(9, int(value / capacity * 9.999)))
        for row in world.energy
        for value in row
    )


def build_mutator(kind: str, model: str, rate: float):
    base = RandomMutator()
    if kind == "random":
        return base
    if kind == "fixture":
        return LLMMutator(base, call_fn=fixture_caller(), rate=rate)
    caller = ollama_caller(model) if kind == "ollama" else anthropic_caller(model)
    return LLMMutator(base, call_fn=caller, rate=rate)


def record(ticks: int, every: int, seed: int, width: int, height: int,
           memory_cap: int, founders: int, mutator_kind: str = "random",
           model: str = "llama3.1", llm_rate: float = 0.05) -> dict:
    world = World(WorldConfig(width=width, height=height,
                              memory_cap=memory_cap, seed=seed))
    mutator = build_mutator(mutator_kind, model, llm_rate)
    colony = Colony(world=world, mutator=mutator,
                    tasks=TaskEnvironment(), seed=seed, founders=founders)

    frames = []
    events = []
    seen_tasks: set[str] = set()
    was_throttling = False

    for _ in range(ticks):
        if not colony.organisms:
            events.append({"tick": world.tick, "text": "colony extinct", "kind": "heat"})
            break
        colony.step()

        if world.tick % every:
            continue

        for name, tick in colony.task_firsts.items():
            if name not in seen_tasks:
                seen_tasks.add(name)
                events.append({"tick": tick, "text": f"{name} solved — reward claimed",
                               "kind": "task"})

        dominant, carriers = colony.dominant_genome()
        strains = Counter(o.lineage for o in colony.organisms)

        frames.append({
            "dom": encode_genome(dominant),
            "car": carriers,
            "s": [strains.get(i, 0) for i in range(founders)],
            "t": world.tick,
            "e": encode_energy(world),
            "o": encode_positions(colony, width),
            "p": len(colony.organisms),
            "m": round(world.memory_pressure, 3),
            "h": round(world.heat, 1),
            "x": round(world.cost_multiplier, 2),
            "g": max((o.generation for o in colony.organisms), default=0),
            "b": colony.births,
            "d": colony.deaths,
        })

        throttling = world.cost_multiplier > 1.0
        if throttling != was_throttling:
            events.append({
                "tick": world.tick,
                "text": "thermal throttling engaged" if throttling else "thermal load cleared",
                "kind": "heat",
            })
            was_throttling = throttling

    genome, carriers = colony.dominant_genome()
    return {
        "width": width,
        "height": height,
        "every": every,
        "founders": founders,
        "mutator": mutator_kind,
        "isa": [ins.name for ins in ISA],
        "ancestor": encode_genome(build_ancestor()),
        "llm": ({"calls": mutator.calls, "accepted": mutator.accepted,
                 "failures": mutator.failures} if isinstance(mutator, LLMMutator) else None),
        "frames": frames,
        "events": events,
        "dominant": {
            "carriers": carriers,
            "source": [ISA[op].name for op in genome if 0 <= op < len(ISA)],
        },
        "summary": {
            "births": colony.births,
            "deaths": colony.deaths,
            "causes": dict(colony.deaths_by_cause),
            "tasks": colony.task_firsts,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a colony run for playback.")
    parser.add_argument("--ticks", type=int, default=6000)
    parser.add_argument("--every", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--height", type=int, default=32)
    parser.add_argument("--memory-cap", type=int, default=4500)
    parser.add_argument("--founders", type=int, default=6)
    parser.add_argument("--mutator", choices=["random", "fixture", "ollama", "anthropic"],
                        default="random",
                        help="fixture is a deterministic test double, not a model")
    parser.add_argument("--model", default="llama3.1")
    parser.add_argument("--llm-rate", type=float, default=0.05)
    parser.add_argument("--out", default="run.html",
                        help="output path; .html writes a viewer, .json writes raw frames")
    args = parser.parse_args()

    data = record(args.ticks, args.every, args.seed, args.width, args.height,
                  args.memory_cap, args.founders, args.mutator, args.model,
                  args.llm_rate)
    payload = json.dumps(data, separators=(",", ":"))

    if args.out.endswith(".json"):
        with open(args.out, "w") as handle:
            handle.write(payload)
    else:
        template = Path(__file__).with_name("viewer_template.html")
        if not template.exists():
            raise SystemExit(f"viewer template not found at {template}")
        html = template.read_text()
        if "__DATA__" not in html:
            raise SystemExit("viewer template is missing its __DATA__ placeholder")
        # The payload sits inside a <script> block, so a literal closing tag
        # would end it early. Nothing in the data produces one today, but
        # escaping costs nothing and removes the failure mode.
        payload = payload.replace("</", "<\\/")
        with open(args.out, "w") as handle:
            handle.write(html.replace("__DATA__", payload))

    print(f"wrote {args.out}: {len(data['frames'])} frames, "
          f"{len(data['events'])} events")


if __name__ == "__main__":
    main()
