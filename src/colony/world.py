"""The substrate organisms live in.

Three scarce things, all global and all real to the organisms:

  energy  — per-tile, regenerating, depletable. The only source of metabolism.
  memory  — a hard colony-wide cap. Allocation fails when it is exhausted,
            which is what actually bounds population size.
  heat    — rises with total instructions executed, decays passively. Above a
            threshold every organism's costs are multiplied. Nobody can escape
            it alone: it is a commons problem, not an individual one.

In the deployed version, energy is a CPU-time budget, memory is real RSS under
a cgroup, and heat is read from thermal sensors. Here they are accounted in
software so the dynamics can be tested before they are wired to the metal.
The interfaces are the same either way.
"""

from dataclasses import dataclass, field
import random


@dataclass
class WorldConfig:
    width: int = 32
    height: int = 32
    tile_capacity: float = 90.0
    # Tuned so the colony consumes energy faster than the world makes it.
    # At higher values the map saturates, starvation stops happening, and
    # memory becomes the only binding constraint — which hollows out the
    # whole premise. Verified by sweep: at 0.06 starvation dominates deaths.
    tile_regen: float = 0.06         # energy per tile per tick
    harvest_rate: float = 6.0        # max energy drawn by one harvest
    memory_cap: int = 6000           # total genome-words the colony may hold
    heat_per_instruction: float = 0.02
    heat_decay: float = 0.90         # fraction retained per tick
    # Tuned against the retuned regen: at 40 the colony never gets hot enough
    # to throttle and the commons problem never bites; at 22 it engages in
    # bursts and self-regulates (hot -> costs rise -> deaths -> cools).
    heat_threshold: float = 22.0     # below this, no throttling
    heat_penalty: float = 0.04       # cost multiplier added per degree over
    storm_interval: int = 1000       # Colony Two resource-weather cadence
    storm_warning: int = 100         # input cue lead time
    drought_fraction: float = 0.08   # energy retained in the drought quadrant
    bloom_fraction: float = 0.75     # minimum capacity after a bloom
    signal_radius: int = 3
    signal_duration: int = 24
    signal_attenuation: int = 5
    seed: int = 1337


class World:
    def __init__(self, config: WorldConfig | None = None):
        self.config = config or WorldConfig()
        c = self.config
        self.rng = random.Random(c.seed)

        # Energy is not uniform. Patchiness is what makes movement and sensing
        # worth evolving — a flat world rewards sitting still.
        self.energy: list[list[float]] = [
            [self._initial_energy() for _ in range(c.width)]
            for _ in range(c.height)
        ]
        self.signals = [[0] * c.width for _ in range(c.height)]
        self.signal_strength = [[0] * c.width for _ in range(c.height)]
        self.structures = [[0] * c.width for _ in range(c.height)]

        self.memory_used: int = 0
        self.heat: float = 0.0
        self.instructions_this_tick: int = 0
        self.tick: int = 0
        self.storm_count: int = 0
        self.last_storm_tick: int = -1
        self.last_drought_quadrant: int | None = None
        self.last_bloom_quadrant: int | None = None

    def _initial_energy(self) -> float:
        c = self.config
        # Roughly a third of tiles are rich, the rest are lean.
        return c.tile_capacity if self.rng.random() < 0.35 else c.tile_capacity * 0.15

    # ── energy ────────────────────────────────────────────────────────────

    def tile_energy(self, x: int, y: int) -> float:
        return self.energy[y % self.config.height][x % self.config.width]

    def harvest(self, x: int, y: int) -> float:
        """Draw energy from a tile. Returns what was actually available."""
        c = self.config
        y, x = y % c.height, x % c.width
        taken = min(c.harvest_rate, self.energy[y][x])
        self.energy[y][x] -= taken
        return taken

    def wrap(self, x: int, y: int) -> tuple[int, int]:
        return x % self.config.width, y % self.config.height

    def signal(self, x: int, y: int, value: int) -> None:
        radius = getattr(self.config, "signal_radius", 3)
        duration = getattr(self.config, "signal_duration", 24)
        attenuation = getattr(self.config, "signal_attenuation", 5)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                distance = abs(dx) + abs(dy)
                if distance > radius:
                    continue
                sx, sy = self.wrap(x + dx, y + dy)
                strength = max(1, duration - distance * attenuation)
                if strength >= self.signal_strength[sy][sx]:
                    self.signals[sy][sx] = value & 0xFF
                    self.signal_strength[sy][sx] = strength

    def listen(self, x: int, y: int) -> int:
        cells = [self.wrap(x, y), self.wrap(x, y - 1), self.wrap(x + 1, y),
                 self.wrap(x, y + 1), self.wrap(x - 1, y)]
        sx, sy = max(cells, key=lambda p: self.signal_strength[p[1]][p[0]])
        return self.signals[sy][sx] if self.signal_strength[sy][sx] else 0

    def listen_strength(self, x: int, y: int) -> int:
        cells = [self.wrap(x, y), self.wrap(x, y - 1), self.wrap(x + 1, y),
                 self.wrap(x, y + 1), self.wrap(x - 1, y)]
        return max(self.signal_strength[sy][sx] for sx, sy in cells)

    def build(self, x: int, y: int) -> None:
        x, y = self.wrap(x, y)
        self.structures[y][x] = min(20, self.structures[y][x] + 1)

    # ── memory ────────────────────────────────────────────────────────────

    def request_memory(self, words: int) -> bool:
        """Claim RAM for a child buffer. Fails when the colony is full.

        This failure is the population control. There is no max_population
        constant anywhere — organisms stop being able to reproduce because
        the machine is out of room, exactly as it would be in deployment.
        """
        if self.memory_used + words > self.config.memory_cap:
            return False
        self.memory_used += words
        return True

    def release_memory(self, words: int) -> None:
        self.memory_used = max(0, self.memory_used - words)

    @property
    def memory_pressure(self) -> float:
        return self.memory_used / self.config.memory_cap

    # ── heat ──────────────────────────────────────────────────────────────

    def charge_instruction(self) -> None:
        self.instructions_this_tick += 1

    @property
    def cost_multiplier(self) -> float:
        """What every instruction currently costs, relative to its base price."""
        c = self.config
        over = self.heat - c.heat_threshold
        return 1.0 + c.heat_penalty * over if over > 0 else 1.0

    # ── tick ──────────────────────────────────────────────────────────────

    def storm_regions(self, tick: int | None = None) -> tuple[int, int]:
        interval = getattr(self.config, "storm_interval", 1000)
        cycle = (self.tick if tick is None else tick) // interval
        drought = cycle % 4
        return drought, (drought + 2) % 4

    def apply_resource_storm(self) -> bool:
        """Apply Colony Two's periodic spatial drought/bloom disturbance."""
        c = self.config
        interval = getattr(c, "storm_interval", 1000)
        if not interval or not self.tick or self.tick % interval:
            return False
        drought, bloom = self.storm_regions()
        drought_fraction = getattr(c, "drought_fraction", 0.08)
        bloom_floor = c.tile_capacity * getattr(c, "bloom_fraction", 0.75)
        for y, row in enumerate(self.energy):
            for x in range(c.width):
                quadrant = (x >= c.width // 2) + 2 * (y >= c.height // 2)
                if quadrant == drought:
                    row[x] *= drought_fraction
                    self.structures[y][x] //= 2
                elif quadrant == bloom:
                    row[x] = max(row[x], bloom_floor)
        self.storm_count = getattr(self, "storm_count", 0) + 1
        self.last_storm_tick = self.tick
        self.last_drought_quadrant = drought
        self.last_bloom_quadrant = bloom
        return True

    @property
    def next_storm_tick(self) -> int:
        interval = getattr(self.config, "storm_interval", 1000)
        return ((self.tick // interval) + 1) * interval

    def step(self) -> None:
        c = self.config
        self.apply_resource_storm()
        phase = (self.tick // 2000) % 4
        for y, row in enumerate(self.energy):
            for x in range(c.width):
                if row[x] < c.tile_capacity:
                    quadrant = (x >= c.width // 2) + 2 * (y >= c.height // 2)
                    climate = 1.8 if quadrant == phase else 0.55
                    construction = self.structures[y][x] * 0.003
                    row[x] = min(c.tile_capacity, row[x] + c.tile_regen * climate + construction)
                if self.signal_strength[y][x] > 0:
                    self.signal_strength[y][x] -= 1
                    if self.signal_strength[y][x] == 0:
                        self.signals[y][x] = 0
                if self.tick and self.tick % 500 == 0 and self.structures[y][x] > 0:
                    self.structures[y][x] -= 1

        self.heat = self.heat * c.heat_decay + self.instructions_this_tick * c.heat_per_instruction
        self.instructions_this_tick = 0
        self.tick += 1

    def total_energy(self) -> float:
        return sum(sum(row) for row in self.energy)
