"""Bindings from colony scarcity to the service's real Linux resources."""

from __future__ import annotations

import os
import time
from pathlib import Path

from .world import World, WorldConfig


CGROUP_ROOT = Path("/sys/fs/cgroup")


def _self_cgroup() -> Path:
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            return CGROUP_ROOT / fields[2].lstrip("/")
    return CGROUP_ROOT


def _read_int(path: Path) -> int | None:
    try:
        raw = path.read_text().strip()
        return None if raw == "max" else int(raw)
    except (OSError, ValueError):
        return None


def cpu_temperature_c() -> float:
    """Read the AMD package control temperature, failing closed if absent."""
    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            if (hwmon / "name").read_text().strip() != "k10temp":
                continue
        except OSError:
            continue
        for source in hwmon.glob("temp*_input"):
            label = source.with_name(source.name.replace("_input", "_label"))
            try:
                if label.exists() and label.read_text().strip() != "Tctl":
                    continue
                return int(source.read_text()) / 1000.0
            except (OSError, ValueError):
                continue
    raise RuntimeError("AMD k10temp/Tctl sensor is unavailable")


class SubstrateWorld(World):
    """World whose pressure signals and allocations are physical, not counters.

    Genome reservations commit and touch real anonymous pages. Linux cgroup v2
    supplies the memory limit/current RSS and CPU usage. Thermal pressure comes
    from the AMD Tctl sensor.
    """

    bytes_per_word = 2 * 1024
    service_headroom_bytes = 32 * 1024 * 1024
    thermal_threshold_c = 72.0
    thermal_penalty = 0.08

    # -- Odin as the climate -----------------------------------------------
    # The simulated quadrant carousel is gone. Storms now fire on this
    # machine's real thermal load, and the quadrant they burn is chosen by
    # the machine's own state, so the colony's weather is whatever Odin is
    # actually doing. Baseline is a slow EMA rather than a fixed threshold:
    # idle Tctl already sits above thermal_threshold_c, so only a *rise*
    # above the recent trailing average counts as an event.
    machine_alpha = 0.002          # EMA rate; ~500 ticks of thermal memory
    machine_warning_delta = 0.30   # degrees over baseline that raise a warning
    machine_trigger_delta = 0.80   # degrees over baseline that fire a storm
    machine_memory_band = 0.50     # cgroup pressure that flips the memory bit
    storm_refractory = 1000        # ticks a storm may not re-fire within

    # -- Odin's spare capacity is the colony's income ----------------------
    # Tile regeneration is not a pasture. It is whatever scheduler time this
    # machine is not already spending on something else, so running a model is
    # a famine and an idle night is a harvest. Measured system-wide from
    # /proc/stat: a cgroup cannot distinguish "I was not scheduled" from "I did
    # not ask", but the box's idle fraction is unambiguous.
    #
    # Scaled against a slow trailing baseline rather than an absolute, because
    # 32 cores idle at ~0.99 spare and no fixed threshold would ever fire. What
    # matters is the DEVIATION: income tracks (spare / usual spare) squared.
    # There is deliberately no floor. If Odin is busy for long enough the
    # colony starves, and extinction is a legitimate outcome.
    cpu_alpha = 0.002              # EMA rate for the spare-capacity baseline
    cpu_sample_interval = 0.5      # seconds between /proc/stat reads
    regen_exponent = 2.0           # how sharply income follows spare capacity
    regen_ceiling = 1.5            # an unusually quiet box pays a bounded bonus

    def __init__(self, config: WorldConfig | None = None):
        super().__init__(config)
        self._pages: list[bytearray] = []
        self._cgroup = _self_cgroup()
        self._temp_cache = (0.0, cpu_temperature_c())

    @classmethod
    def from_world(cls, old: World) -> "SubstrateWorld":
        new = cls(old.config)
        new.energy = old.energy
        new.scrap = getattr(old, "scrap", new.scrap)
        new.bus = getattr(old, "bus", new.bus)
        new.memory_used = old.memory_used
        new.instructions_this_tick = old.instructions_this_tick
        new.tick = old.tick
        new.rng.setstate(old.rng.getstate())
        if new.memory_used:
            new._commit_pages(new.memory_used)
        return new

    def _commit_pages(self, words: int) -> None:
        for _ in range(words):
            block = bytearray(self.bytes_per_word)
            # Touch every OS page so this is RSS, not optimistic virtual RAM.
            for offset in range(0, len(block), os.sysconf("SC_PAGE_SIZE")):
                block[offset] = 1
            self._pages.append(block)

    @property
    def cgroup_memory_current(self) -> int:
        return _read_int(self._cgroup / "memory.current") or 0

    @property
    def cgroup_memory_max(self) -> int:
        value = _read_int(self._cgroup / "memory.max")
        if value is None:
            raise RuntimeError("thegrid service has no finite cgroup memory.max")
        return value

    @property
    def cpu_usage_usec(self) -> int:
        try:
            for line in (self._cgroup / "cpu.stat").read_text().splitlines():
                key, value = line.split()
                if key == "usage_usec":
                    return int(value)
        except (OSError, ValueError):
            pass
        return 0

    def request_memory(self, words: int) -> bool:
        needed = words * self.bytes_per_word
        # Leave resident room for the observer, checkpointing, and Python GC.
        # The cgroup remains the authority; this reserve prevents UI starvation.
        usable_limit = self.cgroup_memory_max - self.service_headroom_bytes
        if self.cgroup_memory_current + needed >= usable_limit:
            return False
        try:
            self._commit_pages(words)
        except MemoryError:
            return False
        self.memory_used += words
        return True

    def release_memory(self, words: int) -> None:
        for _ in range(min(words, len(self._pages))):
            self._pages.pop()
        self.memory_used = max(0, self.memory_used - words)

    @property
    def memory_pressure(self) -> float:
        return self.cgroup_memory_current / self.cgroup_memory_max

    @property
    def heat(self) -> float:
        now = time.monotonic()
        sampled_at, value = getattr(self, "_temp_cache", (0.0, 0.0))
        if now - sampled_at >= 0.5:
            value = cpu_temperature_c()
            self._temp_cache = (now, value)
        return value

    @heat.setter
    def heat(self, _value: float) -> None:
        # Compatibility with World.__init__; thermal state is sensor-owned.
        pass

    @staticmethod
    def _cpu_totals() -> tuple[int, int]:
        """(idle+iowait, total) jiffies for the whole machine."""
        fields = [int(v) for v in
                  open("/proc/stat").readline().split()[1:]]
        return fields[3] + fields[4], sum(fields)

    def _sample_cpu(self) -> None:
        """Refresh the machine's spare-capacity reading, at most every 0.5s."""
        now = time.monotonic()
        if now - getattr(self, "_cpu_sampled_at", 0.0) < self.cpu_sample_interval:
            return
        try:
            idle, total = self._cpu_totals()
        except (OSError, ValueError, IndexError):
            return
        previous = getattr(self, "_cpu_prev", None)
        self._cpu_prev = (idle, total)
        self._cpu_sampled_at = now
        if previous is None:
            return
        idle_delta, total_delta = idle - previous[0], total - previous[1]
        if total_delta <= 0:
            return
        spare = max(0.0, min(1.0, idle_delta / total_delta))
        baseline = getattr(self, "machine_spare_baseline", None)
        if baseline is None:
            baseline = spare
        self.machine_spare_baseline = baseline + (spare - baseline) * self.cpu_alpha
        self.machine_spare = spare

    @property
    def regen_multiplier(self) -> float:
        """Income as a share of what this machine usually has going spare."""
        baseline = getattr(self, "machine_spare_baseline", 0.0)
        if baseline <= 0.0:
            return 1.0
        ratio = getattr(self, "machine_spare", baseline) / baseline
        return min(self.regen_ceiling, max(0.0, ratio) ** self.regen_exponent)

    def _sample_machine(self) -> None:
        """Take one reading of Odin per tick; everything else reuses it."""
        if getattr(self, "_machine_tick", None) == self.tick:
            return
        self._machine_tick = self.tick
        self._sample_cpu()
        heat = self.heat
        baseline = getattr(self, "machine_baseline", None)
        if baseline is None:
            baseline = heat
        self.machine_baseline = baseline + (heat - baseline) * self.machine_alpha
        self.machine_excess = heat - self.machine_baseline
        try:
            self.machine_memory = self.memory_pressure
        except (OSError, RuntimeError, ZeroDivisionError):
            self.machine_memory = 0.0

    @property
    def machine_band(self) -> int:
        """Odin's live state, quantised onto the four quadrants."""
        self._sample_machine()
        hot = getattr(self, "machine_excess", 0.0) >= self.machine_warning_delta
        tight = getattr(self, "machine_memory", 0.0) >= self.machine_memory_band
        return int(hot) + 2 * int(tight)

    def storm_regions(self, tick: int | None = None) -> tuple[int, int]:
        """Which quadrant burns is Odin's state, not a clock cycle."""
        drought = self.machine_band
        return drought, (drought + 2) % 4

    def apply_resource_storm(self) -> bool:
        """Fire when the machine actually heats up, not on a fixed interval."""
        self._sample_machine()
        last = getattr(self, "last_storm_tick", -1)
        if self.tick - last < self.storm_refractory:
            return False
        if getattr(self, "machine_excess", 0.0) < self.machine_trigger_delta:
            return False
        drought, bloom = self.storm_regions()
        return self._apply_storm(drought, bloom)

    @property
    def next_storm_tick(self) -> int:
        """Earliest tick a storm could fire; the machine decides whether it does."""
        return max(self.tick,
                   getattr(self, "last_storm_tick", -1) + self.storm_refractory)

    def weather_cue(self, x: int, y: int) -> int | None:
        """The information biome feels Odin warming; nowhere else can.

        A thermal rise precedes the storm it will trigger, so an organism in
        the SE information niche can read which quadrant is about to burn
        before it burns. The reading is worthless where it is taken -- the
        sensor sits in biome 3, the drought lands in whichever quadrant the
        band names -- so profiting from it means moving, or telling someone.
        This is the first thing in the world that `scan` cannot derive locally.
        """
        self._sample_machine()
        # No upper bound: a sharp thermal ramp crosses the trigger between two
        # samples, so a narrow warning band is unobservable in practice. The
        # cue is live for as long as the machine is running hot, and the band
        # it names is the quadrant the next storm will burn.
        if getattr(self, "machine_excess", 0.0) < self.machine_warning_delta:
            return None
        if self.biome(x, y) != 3:
            return None
        return self.machine_band

    @property
    def cost_multiplier(self) -> float:
        over = self.heat - self.thermal_threshold_c
        return 1.0 + self.thermal_penalty * over if over > 0 else 1.0

    def step(self) -> None:
        # Tile chemistry remains part of the habitat, but memory, scheduler
        # time, and thermal pressure are taken directly from Linux/hardware.
        c = self.config
        self.apply_resource_storm()
        # The favoured biome tracks the machine, not a 2000-tick carousel.
        phase = self.machine_band
        # Income is Odin's spare capacity. No floor: a busy enough box is a
        # famine, and a long enough famine is an extinction.
        regen = self.regen_multiplier
        for y, row in enumerate(self.energy):
            for x in range(c.width):
                if row[x] < c.tile_capacity:
                    biome = self.biome(x, y)
                    climate = 1.8 if biome == phase else 0.55
                    base = (1.25, 0.65, 0.40, 0.75)[biome]
                    construction = self.structures[y][x] * 0.003 * (4.0 if biome == 2 else 0.6)
                    row[x] = min(c.tile_capacity,
                                 row[x] + c.tile_regen * climate * base * regen
                                 + construction)
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
        self.instructions_this_tick = 0
        self.tick += 1

    def __getstate__(self):
        state = dict(self.__dict__)
        state.pop("_pages", None)
        state.pop("_cgroup", None)
        state.pop("_temp_cache", None)
        state.pop("_machine_tick", None)
        state.pop("_cpu_prev", None)
        state.pop("_cpu_sampled_at", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._pages = []
        self._cgroup = _self_cgroup()
        self._temp_cache = (0.0, cpu_temperature_c())
        if self.memory_used:
            self._commit_pages(self.memory_used)
