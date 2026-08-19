"""Persistent colony process with a small LAN observer."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import os
import pickle
import shutil
import signal
import time
from collections import Counter, deque
from pathlib import Path

from aiohttp import web

from .colony import Colony
from .history import LineageHistory
from .isa import ISA, build_ancestor
from .odin_operator import OdinMutator
from .record import ALPHABET, encode_energy, encode_genome, encode_positions
from .tasks import TaskEnvironment
from .substrate import SubstrateWorld
from .world import WorldConfig


class Habitat:
    def __init__(self, state_path: Path, seed: int = 42, founders: int = 6,
                 physical: bool = True, mutator_kind: str = "odin"):
        self.state_path = state_path
        self.seed = seed
        self.founders = founders
        self.physical = physical
        self.mutator_kind = mutator_kind
        self.epoch = 1
        self.started_at = time.time()
        self.events: deque[dict] = deque(maxlen=40)
        self.colony = self._load_or_create()
        self.history = LineageHistory(state_path.with_name("history.sqlite3"))
        self.history.start_epoch(self.epoch, self.seed, self.started_at,
                                 self.colony.organisms, partial=True,
                                 observed_tick=self.colony.world.tick)
        self.running = True
        self._last_tasks = set(self.colony.task_firsts)
        self.latest = self.snapshot()

    def _new_colony(self) -> Colony:
        if self.physical:
            world = SubstrateWorld(WorldConfig(seed=self.seed))
            if self.mutator_kind == "odin":
                mutator = OdinMutator(self.state_path.parent / "operator")
            else:
                from .mutation import RandomMutator
                mutator = RandomMutator()
        else:  # deterministic unit-test boundary; never used by the service
            from .mutation import RandomMutator
            from .world import World
            world = World(WorldConfig(seed=self.seed))
            mutator = RandomMutator()
        return Colony(world, mutator, TaskEnvironment(),
                      seed=self.seed, founders=self.founders)

    def _load_or_create(self) -> Colony:
        try:
            with self.state_path.open("rb") as handle:
                saved = pickle.load(handle)
            self.epoch = int(saved.get("epoch", 1))
            self.seed = int(saved.get("seed", self.seed + self.epoch - 1))
            self.started_at = float(saved.get("started_at", time.time()))
            self.events.extend(saved.get("events", []))
            colony = saved["colony"]
            if self.physical and not isinstance(colony.world, SubstrateWorld):
                colony.world = SubstrateWorld.from_world(colony.world)
            if self.physical and self.mutator_kind == "odin" and not isinstance(colony.mutator, OdinMutator):
                colony.mutator = OdinMutator(self.state_path.parent / "operator")
            elif self.physical and self.mutator_kind == "random" and isinstance(colony.mutator, OdinMutator):
                from .mutation import RandomMutator
                colony.mutator = RandomMutator()
            config = colony.world.config
            for name in ("signals", "signal_strength", "structures"):
                if not hasattr(colony.world, name):
                    setattr(colony.world, name,
                            [[0] * config.width for _ in range(config.height)])
            colony.neighbor_reads = getattr(colony, "neighbor_reads", 0)
            colony.foreign_copies = getattr(colony, "foreign_copies", 0)
            colony.lifecycle_events = getattr(colony, "lifecycle_events", deque())
            for organism in colony.organisms:
                for name in ("signals_sent", "structures_built", "neighbor_reads", "foreign_copies",
                             "moves", "scans", "guided_moves", "post_move_harvested",
                             "task_inputs_seen"):
                    if not hasattr(organism, name):
                        setattr(organism, name, 0)
                for name in ("scan_pending", "awaiting_post_move_harvest"):
                    if not hasattr(organism, name):
                        setattr(organism, name, False)
                if not hasattr(organism, "scratch"):
                    organism.scratch = [0] * 8
            return colony
        except FileNotFoundError:
            return self._new_colony()
        except Exception as exc:
            damaged = self.state_path.with_suffix(f".damaged-{int(time.time())}.pkl")
            self.state_path.replace(damaged)
            self.events.append({"tick": 0, "text": f"damaged checkpoint archived: {exc}"})
            return self._new_colony()

    def save(self) -> None:
        self.history.flush()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        with temporary.open("wb") as handle:
            pickle.dump({"colony": self.colony, "epoch": self.epoch, "seed": self.seed,
                         "started_at": self.started_at,
                         "events": list(self.events)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        if self.state_path.exists():
            shutil.copy2(self.state_path, self.state_path.with_suffix(".previous.pkl"))
        temporary.replace(self.state_path)

    def step(self) -> None:
        if not self.colony.organisms:
            self.history.finish_epoch(self.epoch, self.colony)
            last_tick = self.colony.world.tick
            # Release the extinct population's real resident pages before
            # founders request memory from the same cgroup.
            self.colony = None  # type: ignore[assignment]
            gc.collect()
            # CPython may retain freed arenas, which still count against the
            # real cgroup limit. Return them before founders request RSS.
            try:
                ctypes.CDLL(None).malloc_trim(0)
            except (AttributeError, OSError):
                pass
            self.seed += 1
            replacement = self._new_colony()
            if not replacement.organisms:
                # Persist the empty boundary, then let systemd give the next
                # epoch a clean address space. This is recovery, not revival.
                self.colony = replacement
                self.save()
                os._exit(75)
            self.colony = replacement
            self.epoch += 1
            self.history.start_epoch(self.epoch, self.seed, time.time(),
                                     self.colony.organisms)
            self.events.append({"tick": last_tick, "text": "colony became extinct; new epoch seeded"})
            self._last_tasks.clear()
        self.colony.step()
        self.history.record(self.epoch, self.colony.lifecycle_events)
        self.colony.lifecycle_events.clear()
        for name, tick in self.colony.task_firsts.items():
            if name not in self._last_tasks:
                self.events.append({"tick": tick, "text": f"{name} solved"})
                self._last_tasks.add(name)

    def snapshot(self) -> dict:
        colony, world = self.colony, self.colony.world
        genome, carriers = colony.dominant_genome()
        strains = Counter(o.lineage for o in colony.organisms)
        return {
            "sampledAt": time.time(),
            "epoch": self.epoch, "startedAt": self.started_at,
            "width": world.config.width, "height": world.config.height,
            "tick": world.tick, "population": len(colony.organisms),
            "generation": max((o.generation for o in colony.organisms), default=0),
            "births": colony.births, "deaths": colony.deaths,
            "memory": round(world.memory_pressure, 4), "heat": round(world.heat, 2),
            "cost": round(world.cost_multiplier, 2),
            "memoryBytes": getattr(world, "cgroup_memory_current", 0),
            "memoryMaxBytes": getattr(world, "cgroup_memory_max", 0),
            "cpuUsageUsec": getattr(world, "cpu_usage_usec", 0),
            "substrate": "linux-cgroup-v2 + AMD k10temp" if self.physical else "test",
            "energy": encode_energy(world),
            "organisms": encode_positions(colony, world.config.width),
            "strains": [strains.get(i, 0) for i in range(self.founders)],
            "dominant": encode_genome(genome), "carriers": carriers,
            "isa": [item.name for item in ISA],
            "ancestor": encode_genome(build_ancestor()),
            "tasks": colony.task_firsts,
            "climatePhase": (world.tick // 2000) % 4,
            "activeSignals": sum(value > 0 for row in world.signal_strength for value in row),
            "builtTiles": sum(value > 0 for row in world.structures for value in row),
            "signalField": "".join("0123456789abc"[min(12, value)]
                                   for row in world.signal_strength for value in row),
            "structureField": "".join(ALPHABET[min(31, value)]
                                      for row in world.structures for value in row),
            "neighborReads": colony.neighbor_reads,
            "foreignCopies": colony.foreign_copies,
            "moves": sum(getattr(o, "moves", 0) for o in colony.organisms),
            "scans": sum(getattr(o, "scans", 0) for o in colony.organisms),
            "guidedMoves": sum(getattr(o, "guided_moves", 0) for o in colony.organisms),
            "postMoveHarvested": round(sum(getattr(o, "post_move_harvested", 0.0)
                                            for o in colony.organisms), 2),
            "deathsByCause": dict(colony.deaths_by_cause),
            "events": list(self.events),
        }


async def run_habitat(habitat: Habitat, ticks_per_second: int) -> None:
    interval = 0.1
    batch = max(1, ticks_per_second // 10)
    last_save = time.monotonic()
    while habitat.running:
        before = time.monotonic()
        def advance() -> None:
            for _ in range(batch):
                habitat.step()
        # The VM can consume its full cgroup slice without blocking HTTP.
        await asyncio.to_thread(advance)
        habitat.latest = habitat.snapshot()
        if time.monotonic() - last_save >= 60:
            await asyncio.to_thread(habitat.save)
            last_save = time.monotonic()
        temperature = habitat.colony.world.heat
        thermal_rest = 5.0 if temperature >= 95.0 else (1.0 if temperature >= 90.0 else 0.0)
        delay = interval + thermal_rest - (time.monotonic() - before)
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0)


async def create_app(habitat: Habitat, ticks_per_second: int) -> web.Application:
    app = web.Application()
    app.router.add_get("/", lambda _: web.FileResponse(Path(__file__).with_name("live_viewer.html")))
    app.router.add_get("/api/state", lambda _: web.json_response(habitat.latest,
                                                                  dumps=lambda x: json.dumps(x, separators=(",", ":"))))

    async def stream_state(request: web.Request) -> web.StreamResponse:
        """Send each completed habitat tick to the observer without interpolation."""
        response = web.StreamResponse(headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        })
        await response.prepare(request)
        last_marker = None
        last_keepalive = time.monotonic()
        try:
            while habitat.running:
                state = habitat.latest
                marker = (state["epoch"], state["tick"])
                if marker != last_marker:
                    payload = json.dumps(state, separators=(",", ":"))
                    await response.write(f"data:{payload}\n\n".encode())
                    last_marker = marker
                    last_keepalive = time.monotonic()
                elif time.monotonic() - last_keepalive >= 15:
                    await response.write(b": keepalive\n\n")
                    last_keepalive = time.monotonic()
                await asyncio.sleep(0.02)
        except (ConnectionError, RuntimeError):
            pass
        return response

    app.router.add_get("/api/stream", stream_state)
    app.router.add_get("/api/history", lambda _: web.json_response(
        habitat.history.summary(habitat.epoch),
        dumps=lambda x: json.dumps(x, separators=(",", ":"))))

    async def start(app: web.Application) -> None:
        app["runner"] = asyncio.create_task(run_habitat(habitat, ticks_per_second))
        def restart_on_failure(task: asyncio.Task) -> None:
            if habitat.running and not task.cancelled() and task.exception() is not None:
                os._exit(70)
        app["runner"].add_done_callback(restart_on_failure)

    async def stop(app: web.Application) -> None:
        habitat.running = False
        await app["runner"]
        habitat.save()
        habitat.history.close()

    app.on_startup.append(start)
    app.on_cleanup.append(stop)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistent live colony.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--ticks-per-second", type=int, default=100)
    parser.add_argument("--mutator", choices=("odin", "random"), default="odin")
    parser.add_argument("--state", type=Path,
                        default=Path.home() / ".local/state/thegrid/colony.pkl")
    args = parser.parse_args()
    habitat = Habitat(args.state, mutator_kind=args.mutator)
    web.run_app(create_app(habitat, args.ticks_per_second), host=args.host,
                port=args.port, print=None)


if __name__ == "__main__":
    main()
