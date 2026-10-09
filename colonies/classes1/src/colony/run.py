"""Command-line runner for headless colony experiments."""

import argparse

from .colony import Colony
from .mutation import LLMMutator, RandomMutator, anthropic_caller, fixture_caller, ollama_caller
from .world import World, WorldConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mutator", choices=["random", "fixture", "ollama", "anthropic"], default="random")
    parser.add_argument("--model", default="qwen3.6")
    parser.add_argument("--rate", type=float, default=0.05)
    args = parser.parse_args()
    base = RandomMutator()
    callers = {"fixture": fixture_caller, "ollama": lambda: ollama_caller(args.model), "anthropic": anthropic_caller}
    mutator = base if args.mutator == "random" else LLMMutator(base, callers[args.mutator](), rate=args.rate)
    colony = Colony(World(WorldConfig(seed=args.seed)), mutator=mutator, seed=args.seed)
    for _ in range(args.ticks):
        if not colony.organisms:
            break
        colony.step()
    print({"ticks": colony.world.tick, "population": len(colony.organisms),
           "births": colony.births, "deaths": colony.deaths,
           "tasks": colony.task_firsts, "memory": colony.world.memory_used,
           "heat": round(colony.world.heat, 2)})


if __name__ == "__main__":
    main()
