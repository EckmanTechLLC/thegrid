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
from .history import LineageHistory, genome_id
from .isa import ISA, Op, build_ancestor, build_founder_palette
from .odin_operator import OdinMutator
from .record import ALPHABET, encode_energy, encode_genome, encode_positions
from .tasks import TemporalTaskEnvironment
from .substrate import SubstrateWorld
from .world import WorldConfig


class Habitat:
    ORDINALS = {"": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five"}

    @classmethod
    def default_name(cls, state_path: Path) -> str:
        """Name the habitat after its state directory, not the source tree."""
        stem = state_path.parent.name
        suffix = stem.split("colony")[-1] if "colony" in stem else ""
        return "Colony " + cls.ORDINALS.get(suffix, suffix or "One")

    def __init__(self, state_path: Path, seed: int = 42, founders: int = 13,
                 physical: bool = True, mutator_kind: str = "odin",
                 width: int = 48, height: int = 48, name: str | None = None):
        self.state_path = state_path
        self.name = name or self.default_name(state_path)
        self.seed = seed
        self.founders = founders
        self.width = width
        self.height = height
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
        self.recent_deaths: deque[dict] = deque(maxlen=256)
        self.organism_latest: dict[tuple[int, int], dict] = {}
        self.tile_latest: dict[tuple[int, int], list[dict]] = {}
        self.running = True
        self._last_tasks = set(self.colony.task_firsts)
        self._last_storm_count = getattr(self.colony.world, "storm_count", 0)
        self.latest = self.snapshot()

    def _new_colony(self) -> Colony:
        if self.physical:
            world = SubstrateWorld(WorldConfig(width=self.width, height=self.height,
                                               seed=self.seed))
            if self.mutator_kind == "odin":
                mutator = OdinMutator(self.state_path.parent / "operator")
            else:
                from .mutation import ExperimentalMutator
                mutator = ExperimentalMutator()
        else:  # deterministic unit-test boundary; never used by the service
            from .mutation import RandomMutator
            from .world import World
            world = World(WorldConfig(width=self.width, height=self.height,
                                      seed=self.seed))
            mutator = RandomMutator()
        return Colony(world, mutator, TemporalTaskEnvironment(),
                      seed=self.seed, founders=self.founders,
                      founder_genomes=build_founder_palette(),
                      founder_copies=4 if self.physical else 1)

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
            elif self.physical and self.mutator_kind == "random":
                from .mutation import ExperimentalMutator
                if not isinstance(colony.mutator, ExperimentalMutator):
                    colony.mutator = ExperimentalMutator()
                colony.mutator.upgrade()
            config = colony.world.config
            for name in ("signals", "signal_strength", "structures"):
                if not hasattr(colony.world, name):
                    setattr(colony.world, name,
                            [[0] * config.width for _ in range(config.height)])
            if not hasattr(colony.world, "scrap"):
                colony.world.scrap = [[0.0] * config.width for _ in range(config.height)]
            for name, value in {
                "storm_count": 0,
                "last_storm_tick": -1,
                "last_drought_quadrant": None,
                "last_bloom_quadrant": None,
            }.items():
                if not hasattr(colony.world, name):
                    setattr(colony.world, name, value)
            colony.neighbor_reads = getattr(colony, "neighbor_reads", 0)
            colony.foreign_copies = getattr(colony, "foreign_copies", 0)
            colony.experimental_ops = getattr(colony, "experimental_ops", Counter())
            colony.forecast_attempts = getattr(colony, "forecast_attempts", 0)
            colony.forecasts_solved = getattr(colony, "forecasts_solved", 0)
            colony.weather_cues_seen = getattr(colony, "weather_cues_seen", 0)
            colony.weather_cue_signals = getattr(colony, "weather_cue_signals", 0)
            colony.mutation_mechanisms = getattr(colony, "mutation_mechanisms", Counter())
            colony.scrap_deposited = getattr(colony, "scrap_deposited", 0.0)
            colony.salvaged = getattr(colony, "salvaged", 0.0)
            # backfill code-commons state onto worlds pickled before it existed
            if not hasattr(colony.world, "code_slots"):
                colony.world.code_slots = [[] for _ in range(16)]
                colony.world.slot_uses = [0] * 16
            if not hasattr(colony.world, "slot_owner"):
                colony.world.slot_owner = [-1] * 16
            if not hasattr(colony.world, "bus"):
                colony.world.bus = [0] * 16
                colony.world.bus_writes = colony.world.bus_reads = 0
                colony.world.bus_written_at = [-1] * 16
                colony.world.bus_writer = [-1] * 16
            for _c in ("published", "calls", "self_writes", "royalty_events",
                       "bus_writes", "bus_reads"):
                if not hasattr(colony, _c):
                    setattr(colony, _c, 0)
            if not hasattr(colony, "royalties"):
                colony.royalties = 0.0
            colony.tasks = TemporalTaskEnvironment()
            colony.lifecycle_events = getattr(colony, "lifecycle_events", deque())
            for organism in colony.organisms:
                if not hasattr(organism, "pending"):
                    organism.pending = []
                if not hasattr(organism, "call_slot"):
                    organism.call_slot, organism.call_energy = -1, 0.0
                for name in ("signals_sent", "structures_built", "neighbor_reads", "foreign_copies",
                             "moves", "scans", "guided_moves", "post_move_harvested",
                             "task_inputs_seen", "signals_heard", "signal_guided_moves",
                             "post_signal_harvested", "weather_cues_seen",
                             "weather_cue_signals", "bus_writes", "bus_reads"):
                    if not hasattr(organism, name):
                        setattr(organism, name, 0)
                for name in ("scan_pending", "listen_pending", "awaiting_post_move_harvest",
                             "awaiting_signal_harvest"):
                    if not hasattr(organism, name):
                        setattr(organism, name, False)
                if not hasattr(organism, "scratch"):
                    organism.scratch = [0] * 8
                if not hasattr(organism, "child_mutations"):
                    organism.child_mutations = []
                if not hasattr(organism, "salvaged"):
                    organism.salvaged = 0.0
                defaults = {
                    "last_load_slot": None,
                    "last_load_tick": -1,
                    "forecast_target": None,
                    "forecast_due_tick": -1,
                    "forecast_expires_tick": -1,
                    "forecast_stored_mask": 0,
                    "forecast_attempts": 0,
                    "forecasts_solved": 0,
                    "weather_cue_value": None,
                    "experimental_ops": {},
                }
                for name, value in defaults.items():
                    if not hasattr(organism, name):
                        setattr(organism, name, value)
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

    def retire_current_epoch(self, reason: str = "operator-directed retirement") -> None:
        """Archive the living epoch in history and seed a clean successor."""
        old_colony = self.colony
        old_tick = old_colony.world.tick
        self.history.finish_epoch(self.epoch, old_colony, extinct=False, reason=reason)
        self.colony = None  # type: ignore[assignment]
        gc.collect()
        try:
            ctypes.CDLL(None).malloc_trim(0)
        except (AttributeError, OSError):
            pass
        self.seed += 1
        self.epoch += 1
        self.started_at = time.time()
        self.colony = self._new_colony()
        if not self.colony.organisms:
            raise RuntimeError("fresh epoch could not allocate founders")
        self.history.start_epoch(self.epoch, self.seed, self.started_at,
                                 self.colony.organisms)
        self._last_storm_count = 0
        self.events.append({
            "tick": old_tick,
            "text": f"epoch intentionally retired; epoch {self.epoch} seeded",
        })
        self._last_tasks.clear()
        self.latest = self.snapshot()
        self.save()

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
            self._last_storm_count = 0
        self.colony.step()
        storm_count = getattr(self.colony.world, "storm_count", 0)
        if storm_count > self._last_storm_count:
            labels = ("NW", "NE", "SW", "SE")
            drought = self.colony.world.last_drought_quadrant
            bloom = self.colony.world.last_bloom_quadrant
            self.events.append({
                "tick": self.colony.world.last_storm_tick,
                "text": f"resource storm: {labels[drought]} drought · {labels[bloom]} bloom",
            })
            self._last_storm_count = storm_count
        for event in self.colony.lifecycle_events:
            if event["kind"] == "death":
                self.recent_deaths.append(self._organism_detail(
                    event["organism"], status="dead", cause=event["cause"],
                    tick=event["tick"],
                ))
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
        population = len(colony.organisms)
        diversity = len({tuple(o.genome) for o in colony.organisms})
        average_genome_length = (sum(len(o.genome) for o in colony.organisms) / population
                                 if population else 0.0)
        active_signals = sum(value > 0 for row in world.signal_strength for value in row)
        built_tiles = sum(value > 0 for row in world.structures for value in row)
        biome_populations = Counter(world.biome(o.x, o.y) for o in colony.organisms)
        biome_genomes = {
            biome: len({tuple(o.genome) for o in colony.organisms
                        if world.biome(o.x, o.y) == biome})
            for biome in range(4)
        }
        self.history.record_ecology(
            self.epoch, world.tick, population=population, diversity=diversity,
            dominance=carriers / population if population else 0.0,
            genome_length=average_genome_length,
            resources=world.total_energy() / (world.config.width * world.config.height),
            built=built_tiles, signals=active_signals,
            cost=world.cost_multiplier,
            thermal_excess=getattr(world, "machine_excess", 0.0),
            machine_spare=getattr(world, "machine_spare", 1.0),
            regen=getattr(world, "regen_multiplier", 1.0),
            # Colony three still keeps its reclaimable energy on the map;
            # summing it keeps the column comparable across both arms.
            reclaim_pool=(getattr(world, "reclaim_pool", None)
                          if getattr(world, "reclaim_pool", None) is not None
                          else sum(sum(r) for r in getattr(world, "scrap", []))),
            slots_held=sum(1 for v in getattr(world, "slot_heat", [])
                           if v >= getattr(world, "slot_hold_threshold", 0.5)),
            bus_writes=getattr(colony, "bus_writes", 0),
            bus_reads=getattr(colony, "bus_reads", 0),
            published=getattr(colony, "published", 0),
            calls=getattr(colony, "calls", 0),
            publish_refused=getattr(colony, "publish_refused", 0),
            salvaged=getattr(colony, "salvaged", 0.0),
        )
        details = [self._organism_detail(o, tick=world.tick) for o in colony.organisms]
        self.organism_latest = {(self.epoch, item["id"]): item for item in details}
        tiles: dict[tuple[int, int], list[dict]] = {}
        for item in details:
            tiles.setdefault((item["x"], item["y"]), []).append(item)
        self.tile_latest = tiles
        return {
            "sampledAt": time.time(),
            "epoch": self.epoch, "startedAt": self.started_at,
            "width": world.config.width, "height": world.config.height,
            "tick": world.tick, "population": population,
            "generation": max((o.generation for o in colony.organisms), default=0),
            "births": colony.births, "deaths": colony.deaths,
            "memory": round(world.memory_pressure, 4), "heat": round(world.heat, 2),
            "cost": round(world.cost_multiplier, 2),
            "memoryBytes": getattr(world, "cgroup_memory_current", 0),
            "memoryMaxBytes": getattr(world, "cgroup_memory_max", 0),
            "cpuUsageUsec": getattr(world, "cpu_usage_usec", 0),
            "substrate": "linux-cgroup-v2 + AMD k10temp" if self.physical else "test",
            "energy": encode_energy(world),
            "biomeField": "".join(str(world.biome(x, y))
                                    for y in range(world.config.height)
                                    for x in range(world.config.width)),
            "biomePopulations": [biome_populations.get(i, 0) for i in range(4)],
            "biomeGenomes": [biome_genomes[i] for i in range(4)],
            "organisms": encode_positions(colony, world.config.width),
            "genomeGlyphs": "".join(genome_id(o.genome)[0] for o in colony.organisms),
            "strains": [strains.get(i, 0) for i in range(self.founders)],
            "dominant": encode_genome(genome), "carriers": carriers,
            "isa": [item.name for item in ISA],
            "ancestor": encode_genome(build_ancestor()),
            "tasks": colony.task_firsts,
            "name": self.name,
            "climatePhase": getattr(world, "machine_band", (world.tick // 2000) % 4),
            "weather": {
                "storms": getattr(world, "storm_count", 0),
                "lastTick": getattr(world, "last_storm_tick", -1),
                "droughtQuadrant": getattr(world, "last_drought_quadrant", None),
                "bloomQuadrant": getattr(world, "last_bloom_quadrant", None),
                "nextTick": world.next_storm_tick,
                "warningTicks": getattr(world.config, "storm_warning", 100),
                # Colony Two's weather is Odin itself; these are the readings
                # the storms actually fire on.
                "source": "odin-thermal" if hasattr(world, "machine_band") else "simulated",
                "band": getattr(world, "machine_band", None),
                "baselineC": round(getattr(world, "machine_baseline", 0.0), 2),
                "heatFastC": round(getattr(world, "machine_heat_fast", 0.0), 2),
                "heatRawC": round(world.heat, 2),
                "excessC": round(getattr(world, "machine_excess", 0.0), 2),
                "warningC": getattr(world, "machine_warning_delta", None),
                "triggerC": getattr(world, "machine_trigger_delta", None),
                "warning": (getattr(world, "machine_excess", 0.0)
                            >= getattr(world, "machine_warning_delta", 1e9)),
            },
            "bus": {
                "words": list(getattr(world, "bus", [])),
                "writes": getattr(colony, "bus_writes", 0),
                "reads": getattr(colony, "bus_reads", 0),
                "writtenAt": list(getattr(world, "bus_written_at", [])),
                "writers": len({w for w in getattr(world, "bus_writer", [])
                                if w >= 0}),
                "carriers": sum(1 for o in colony.organisms
                                if any(word in (int(Op.POST), int(Op.FETCH))
                                       for word in o.genome)),
            },
            "activeSignals": active_signals,
            "signalsHeard": sum(getattr(o, "signals_heard", 0) for o in colony.organisms),
            "signalGuidedMoves": sum(getattr(o, "signal_guided_moves", 0)
                                       for o in colony.organisms),
            "postSignalHarvested": round(sum(getattr(o, "post_signal_harvested", 0.0)
                                               for o in colony.organisms), 2),
            "weatherCuesSeen": colony.weather_cues_seen,
            "weatherCueSignals": colony.weather_cue_signals,
            "builtTiles": built_tiles,
            "signalField": "".join("0123456789abc"[min(12, value)]
                                   for row in world.signal_strength for value in row),
            "structureField": "".join(ALPHABET[min(31, value)]
                                      for row in world.structures for value in row),
            "scrapField": "".join(ALPHABET[min(31, int(value))]
                                  for row in world.scrap for value in row),
            "scrapTiles": sum(value > 0 for row in world.scrap for value in row),
            "scrapAvailable": round(sum(sum(row) for row in world.scrap), 2),
            "scrapDeposited": round(colony.scrap_deposited, 2),
            "salvaged": round(colony.salvaged, 2),
            "published": getattr(colony, "published", 0),
            "calls": getattr(colony, "calls", 0),
            "selfWrites": getattr(colony, "self_writes", 0),
            "royalties": round(getattr(colony, "royalties", 0.0), 2),
            "royaltyEvents": getattr(colony, "royalty_events", 0),
            "slotOwners": list(getattr(colony.world, "slot_owner", [])),
            "codeSlotsUsed": sum(1 for r in colony.world.code_slots if r),
            "slotUses": list(colony.world.slot_uses),
            "neighborReads": colony.neighbor_reads,
            "foreignCopies": colony.foreign_copies,
            "experimentalOps": dict(colony.experimental_ops),
            "forecastAttempts": colony.forecast_attempts,
            "forecastsSolved": colony.forecasts_solved,
            "activeForecasts": sum(o.forecast_target is not None for o in colony.organisms),
            "mutationMechanisms": dict(colony.mutation_mechanisms),
            "moves": sum(getattr(o, "moves", 0) for o in colony.organisms),
            "scans": sum(getattr(o, "scans", 0) for o in colony.organisms),
            "guidedMoves": sum(getattr(o, "guided_moves", 0) for o in colony.organisms),
            "postMoveHarvested": round(sum(getattr(o, "post_move_harvested", 0.0)
                                            for o in colony.organisms), 2),
            "deathsByCause": dict(colony.deaths_by_cause),
            "events": list(self.events),
        }

    def _organism_detail(self, organism, status: str = "alive", cause=None,
                         tick: int | None = None) -> dict:
        genome = list(organism.genome)
        identity = genome_id(genome)
        current = genome[organism.ip % len(genome)] if genome else None
        return {
            "epoch": self.epoch, "tick": tick, "status": status, "cause": cause,
            "id": organism.id, "lineage": organism.lineage,
            "genomeId": identity, "genomeGlyph": identity[0],
            "x": organism.x, "y": organism.y,
            "generation": organism.generation, "age": organism.age,
            "energy": round(organism.energy, 2), "births": organism.births,
            "ip": organism.ip, "currentInstruction": (
                ISA[current].name if current is not None and 0 <= current < len(ISA) else None),
            "genome": [ISA[word].name if 0 <= word < len(ISA) else f"?{word}"
                       for word in genome],
            "registers": {"a": organism.a, "b": organism.b, "c": organism.c},
            "childProgress": (None if organism.child is None else {
                "copied": organism.copy_index, "total": len(genome)}),
            "harvested": round(organism.harvested, 2),
            "tasks": dict(organism.tasks_solved),
            "moves": getattr(organism, "moves", 0),
            "scans": getattr(organism, "scans", 0),
            "guidedMoves": getattr(organism, "guided_moves", 0),
            "signals": getattr(organism, "signals_sent", 0),
            "signalsHeard": getattr(organism, "signals_heard", 0),
            "signalGuidedMoves": getattr(organism, "signal_guided_moves", 0),
            "postSignalHarvested": round(getattr(organism, "post_signal_harvested", 0.0), 2),
            "weatherCuesSeen": getattr(organism, "weather_cues_seen", 0),
            "weatherCueSignals": getattr(organism, "weather_cue_signals", 0),
            "structures": getattr(organism, "structures_built", 0),
            "salvaged": round(getattr(organism, "salvaged", 0.0), 2),
            "scrapHere": round(self.colony.world.scrap[organism.y][organism.x], 2),
            "neighborReads": getattr(organism, "neighbor_reads", 0),
            "foreignCopies": getattr(organism, "foreign_copies", 0),
            "scratch": list(getattr(organism, "scratch", [])) or None,
            "experimentalOps": dict(getattr(organism, "experimental_ops", {})),
            "forecast": {
                "target": getattr(organism, "forecast_target", None),
                "dueTick": getattr(organism, "forecast_due_tick", -1),
                "expiresTick": getattr(organism, "forecast_expires_tick", -1),
                "attempts": getattr(organism, "forecast_attempts", 0),
                "solved": getattr(organism, "forecasts_solved", 0),
            },
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

    async def tile_organisms(request: web.Request) -> web.Response:
        try:
            x, y = int(request.query["x"]), int(request.query["y"])
        except (KeyError, ValueError):
            raise web.HTTPBadRequest(text="integer x and y are required")
        return web.json_response({"epoch": habitat.epoch, "x": x, "y": y,
                                  "organisms": habitat.tile_latest.get((x, y), [])})

    async def organism_detail(request: web.Request) -> web.Response:
        epoch, organism_id = int(request.match_info["epoch"]), int(request.match_info["organism_id"])
        detail = habitat.organism_latest.get((epoch, organism_id))
        if detail is None:
            detail = next((item for item in reversed(habitat.recent_deaths)
                           if item["epoch"] == epoch and item["id"] == organism_id), None)
        if detail is None:
            raise web.HTTPNotFound(text="organism is no longer in recent history")
        return web.json_response(detail)

    app.router.add_get("/api/organisms", tile_organisms)
    app.router.add_get("/api/organism/{epoch:\\d+}/{organism_id:\\d+}", organism_detail)

    # The aggregate queries grow with the fossil record -- at 419MB they take
    # 2-4 seconds. to_thread keeps them off the event loop, but a 5-second poll
    # against a 4-second query means the box is almost always mid-summary, and
    # every viewer that connects adds another one. Cache the result and let
    # concurrent callers share the single in-flight computation.
    history_cache: dict = {"at": 0.0, "epoch": None, "data": None}
    history_lock = asyncio.Lock()
    HISTORY_TTL = 25.0

    def _fresh_history() -> dict | None:
        if (history_cache["data"] is not None
                and history_cache["epoch"] == habitat.epoch
                and time.monotonic() - history_cache["at"] < HISTORY_TTL):
            return history_cache["data"]
        return None

    async def history_summary(request: web.Request) -> web.Response:
        summary = _fresh_history()
        if summary is None:
            async with history_lock:
                # Another caller may have refreshed it while we waited.
                summary = _fresh_history()
                if summary is None:
                    summary = await asyncio.to_thread(habitat.history.summary,
                                                      habitat.epoch)
                    history_cache.update(at=time.monotonic(),
                                         epoch=habitat.epoch, data=summary)
        return web.json_response(
            summary,
            dumps=lambda x: json.dumps(x, separators=(",", ":")),
        )

    app.router.add_get("/api/history", history_summary)

    async def start(app: web.Application) -> None:
        app["runner"] = asyncio.create_task(run_habitat(habitat, ticks_per_second))
        def restart_on_failure(task: asyncio.Task) -> None:
            if habitat.running and not task.cancelled() and task.exception() is not None:
                os._exit(70)
        app["runner"].add_done_callback(restart_on_failure)

    async def begin_shutdown(app: web.Application) -> None:
        # Stop SSE handlers before aiohttp waits for open connections to drain.
        habitat.running = False

    async def stop(app: web.Application) -> None:
        habitat.running = False
        await app["runner"]
        habitat.save()
        habitat.history.close()

    app.on_startup.append(start)
    app.on_shutdown.append(begin_shutdown)
    app.on_cleanup.append(stop)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistent live colony.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--ticks-per-second", type=int, default=100)
    parser.add_argument("--mutator", choices=("odin", "random"), default="odin")
    parser.add_argument("--retire-current-epoch", action="store_true")
    parser.add_argument("--name", default=None,
                        help="display name; defaults to the state directory")
    parser.add_argument("--state", type=Path,
                        default=Path.home() / ".local/state/thegrid/colony.pkl")
    args = parser.parse_args()
    habitat = Habitat(args.state, mutator_kind=args.mutator, name=args.name)
    if args.retire_current_epoch:
        habitat.retire_current_epoch()
        habitat.history.close()
        return
    web.run_app(create_app(habitat, args.ticks_per_second), host=args.host,
                port=args.port, print=None)


if __name__ == "__main__":
    main()
