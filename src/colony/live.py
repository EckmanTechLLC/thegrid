"""Persistent colony process with a small LAN observer."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import signal
import time
from collections import Counter, deque
from pathlib import Path

from aiohttp import web

from .colony import Colony
from .isa import ISA, build_ancestor
from .mutation import RandomMutator
from .record import encode_energy, encode_genome, encode_positions
from .tasks import TaskEnvironment
from .world import World, WorldConfig


class Habitat:
    def __init__(self, state_path: Path, seed: int = 42, founders: int = 6):
        self.state_path = state_path
        self.seed = seed
        self.founders = founders
        self.epoch = 1
        self.started_at = time.time()
        self.events: deque[dict] = deque(maxlen=40)
        self.colony = self._load_or_create()
        self.running = True
        self._last_tasks = set(self.colony.task_firsts)

    def _new_colony(self) -> Colony:
        world = World(WorldConfig(seed=self.seed))
        return Colony(world, RandomMutator(), TaskEnvironment(),
                      seed=self.seed, founders=self.founders)

    def _load_or_create(self) -> Colony:
        try:
            with self.state_path.open("rb") as handle:
                saved = pickle.load(handle)
            self.epoch = int(saved.get("epoch", 1))
            self.started_at = float(saved.get("started_at", time.time()))
            self.events.extend(saved.get("events", []))
            return saved["colony"]
        except FileNotFoundError:
            return self._new_colony()
        except Exception as exc:
            damaged = self.state_path.with_suffix(f".damaged-{int(time.time())}.pkl")
            self.state_path.replace(damaged)
            self.events.append({"tick": 0, "text": f"damaged checkpoint archived: {exc}"})
            return self._new_colony()

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        with temporary.open("wb") as handle:
            pickle.dump({"colony": self.colony, "epoch": self.epoch,
                         "started_at": self.started_at,
                         "events": list(self.events)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.state_path)

    def step(self) -> None:
        if not self.colony.organisms:
            last_tick = self.colony.world.tick
            self.events.append({"tick": last_tick, "text": "colony became extinct; new epoch seeded"})
            self.epoch += 1
            self.seed += 1
            self.colony = self._new_colony()
            self._last_tasks.clear()
        self.colony.step()
        for name, tick in self.colony.task_firsts.items():
            if name not in self._last_tasks:
                self.events.append({"tick": tick, "text": f"{name} solved"})
                self._last_tasks.add(name)

    def snapshot(self) -> dict:
        colony, world = self.colony, self.colony.world
        genome, carriers = colony.dominant_genome()
        strains = Counter(o.lineage for o in colony.organisms)
        return {
            "epoch": self.epoch, "startedAt": self.started_at,
            "width": world.config.width, "height": world.config.height,
            "tick": world.tick, "population": len(colony.organisms),
            "generation": max((o.generation for o in colony.organisms), default=0),
            "births": colony.births, "deaths": colony.deaths,
            "memory": round(world.memory_pressure, 4), "heat": round(world.heat, 2),
            "cost": round(world.cost_multiplier, 2),
            "energy": encode_energy(world),
            "organisms": encode_positions(colony, world.config.width),
            "strains": [strains.get(i, 0) for i in range(self.founders)],
            "dominant": encode_genome(genome), "carriers": carriers,
            "isa": [item.name for item in ISA],
            "ancestor": encode_genome(build_ancestor()),
            "tasks": colony.task_firsts,
            "events": list(self.events),
        }


async def run_habitat(habitat: Habitat, ticks_per_second: int) -> None:
    interval = 0.1
    batch = max(1, ticks_per_second // 10)
    saves = 0
    while habitat.running:
        before = time.monotonic()
        for _ in range(batch):
            habitat.step()
        saves += batch
        if saves >= 1000:
            habitat.save()
            saves = 0
        delay = interval - (time.monotonic() - before)
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0)


async def create_app(habitat: Habitat, ticks_per_second: int) -> web.Application:
    app = web.Application()
    app.router.add_get("/", lambda _: web.FileResponse(Path(__file__).with_name("live_viewer.html")))
    app.router.add_get("/api/state", lambda _: web.json_response(habitat.snapshot(),
                                                                  dumps=lambda x: json.dumps(x, separators=(",", ":"))))

    async def start(app: web.Application) -> None:
        app["runner"] = asyncio.create_task(run_habitat(habitat, ticks_per_second))

    async def stop(app: web.Application) -> None:
        habitat.running = False
        await app["runner"]
        habitat.save()

    app.on_startup.append(start)
    app.on_cleanup.append(stop)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistent live colony.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--ticks-per-second", type=int, default=100)
    parser.add_argument("--state", type=Path,
                        default=Path.home() / ".local/state/thegrid/colony.pkl")
    args = parser.parse_args()
    habitat = Habitat(args.state)
    web.run_app(create_app(habitat, args.ticks_per_second), host=args.host,
                port=args.port, print=None)


if __name__ == "__main__":
    main()
