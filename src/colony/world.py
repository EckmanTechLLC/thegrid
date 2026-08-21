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

from .isa import Op


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
    storm_scout_depth: int = 4       # bloom-side boundary strip that senses it
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
        self.scrap = [[0.0] * c.width for _ in range(c.height)]

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
        # The forage biome rewards a short harvesting specialist; elsewhere
        # harvesting is weaker enough that mobility, building, or information
        # processing can repay their extra instructions.
        rate = c.harvest_rate * (1.35 if self.biome(x, y) == 0 else 0.78)
        taken = min(rate, self.energy[y][x])
        self.energy[y][x] -= taken
        return taken

    def wrap(self, x: int, y: int) -> tuple[int, int]:
        return x % self.config.width, y % self.config.height

    def biome(self, x: int, y: int) -> int:
        """Persistent NW forage, NE nomad, SW engineer, SE information niche."""
        c = self.config
        x, y = self.wrap(x, y)
        return (x >= c.width // 2) + 2 * (y >= c.height // 2)

    def move(self, x: int, y: int, dx: int, dy: int) -> tuple[int, int]:
        """Move within a biome, crossing boundaries only through narrow gates."""
        destination = self.wrap(x + dx, y + dy)
        if self.biome(x, y) == self.biome(*destination):
            return destination
        # Two three-tile migration corridors cross each boundary. This also
        # gates the toroidal outer seam, preventing instant global mixing.
        perpendicular = y if dx else x
        extent = self.config.height if dx else self.config.width
        gates = (extent // 4, 3 * extent // 4)
        return destination if any(abs(perpendicular - gate) <= 1 for gate in gates) else (x, y)

    def instruction_cost_multiplier(self, op: Op, x: int, y: int) -> float:
        """Local energetic tradeoffs; replication remains the neutral yardstick."""
        biome = self.biome(x, y)
        local = 1.0
        if biome == 0:  # forage: cheap harvesting, expensive infrastructure
            if op == Op.HARVEST:
                local = 0.65
            elif op in (Op.BUILD, Op.SIGNAL, Op.LISTEN):
                local = 1.4
        elif biome == 1:  # nomad: cheap sensing/motion, poor stationary yield
            if op in (Op.SCAN, Op.MOVE):
                local = 0.55
            elif op in (Op.HARVEST, Op.BUILD):
                local = 1.3
        elif biome == 2:  # engineer: construction pays, motion/foraging do not
            if op in (Op.BUILD, Op.SALVAGE):
                local = 0.45
            elif op in (Op.HARVEST, Op.MOVE):
                local = 1.3
        else:  # information: communication, memory, and computation are cheap
            if op in (Op.SIGNAL, Op.LISTEN, Op.INPUT, Op.OUTPUT, Op.ADD, Op.SUB,
                      Op.XOR, Op.LOAD, Op.STORE, Op.NAND, Op.PEEK, Op.COPYN):
                local = 0.55
            elif op in (Op.HARVEST, Op.BUILD):
                local = 1.35
        return self.cost_multiplier * local

    def build_cost(self, x: int, y: int) -> float:
        return 1.5 if self.biome(x, y) == 2 else 4.0

    def task_reward_multiplier(self, x: int, y: int) -> float:
        return 1.75 if self.biome(x, y) == 3 else 0.75

    def signal(self, x: int, y: int, value: int) -> None:
        radius = getattr(self.config, "signal_radius", 3)
        duration = getattr(self.config, "signal_duration", 24)
        if self.biome(x, y) == 3:
            duration = int(duration * 1.75)
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

    def deposit_scrap(self, x: int, y: int, genome_words: int,
                      remaining_energy: float) -> float:
        """Leave bounded embodied hardware behind without refunding birth cost."""
        x, y = self.wrap(x, y)
        amount = min(12.0, genome_words * 0.45 + max(0.0, remaining_energy) * 0.20)
        self.scrap[y][x] = min(31.0, self.scrap[y][x] + amount)
        return amount

    def salvage(self, x: int, y: int) -> float:
        x, y = self.wrap(x, y)
        taken = min(5.0, self.scrap[y][x])
        self.scrap[y][x] -= taken
        return taken * (1.25 if self.biome(x, y) == 2 else 1.0)

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

    def weather_cue(self, x: int, y: int) -> int | None:
        """Give bloom-front scouts a direction; everyone else must listen."""
        c = self.config
        interval = getattr(c, "storm_interval", 1000)
        warning = getattr(c, "storm_warning", 100)
        if not interval or self.tick % interval < interval - warning:
            return None
        next_tick = ((self.tick // interval) + 1) * interval
        _, bloom = self.storm_regions(next_tick)
        x, y = self.wrap(x, y)
        if self.biome(x, y) != bloom:
            return None
        mid_x, mid_y = c.width // 2, c.height // 2
        depth = max(1, getattr(c, "storm_scout_depth", 4))
        near_vertical_front = (bloom % 2 == 0 and mid_x - depth <= x < mid_x) or (
            bloom % 2 == 1 and mid_x <= x < mid_x + depth)
        near_horizontal_front = (bloom < 2 and mid_y - depth <= y < mid_y) or (
            bloom >= 2 and mid_y <= y < mid_y + depth)
        if not (near_vertical_front or near_horizontal_front):
            return None

        target_x = c.width // 4 if bloom % 2 == 0 else 3 * c.width // 4
        target_y = c.height // 4 if bloom < 2 else 3 * c.height // 4
        dx, dy = target_x - x, target_y - y
        if abs(dx) >= abs(dy) and dx:
            return 1 if dx > 0 else 3
        return 2 if dy > 0 else 0

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
                    biome = self.biome(x, y)
                    climate = 1.8 if biome == phase else 0.55
                    base = (1.25, 0.65, 0.40, 0.75)[biome]
                    construction = self.structures[y][x] * 0.003 * (4.0 if biome == 2 else 0.6)
                    row[x] = min(c.tile_capacity, row[x] + c.tile_regen * climate * base + construction)
                if self.signal_strength[y][x] > 0:
                    self.signal_strength[y][x] -= 1
                    if self.signal_strength[y][x] == 0:
                        self.signals[y][x] = 0
                if self.tick and self.tick % 500 == 0 and self.structures[y][x] > 0:
                    self.structures[y][x] -= 1
                if self.scrap[y][x] > 0:
                    self.scrap[y][x] *= 0.997
                    if self.scrap[y][x] < 0.05:
                        self.scrap[y][x] = 0.0

        self.heat = self.heat * c.heat_decay + self.instructions_this_tick * c.heat_per_instruction
        self.instructions_this_tick = 0
        self.tick += 1

    def total_energy(self) -> float:
        return sum(sum(row) for row in self.energy)
