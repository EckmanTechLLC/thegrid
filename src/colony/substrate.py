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

    def __init__(self, config: WorldConfig | None = None):
        super().__init__(config)
        self._pages: list[bytearray] = []
        self._cgroup = _self_cgroup()
        self._temp_cache = (0.0, cpu_temperature_c())

    @classmethod
    def from_world(cls, old: World) -> "SubstrateWorld":
        new = cls(old.config)
        new.energy = old.energy
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

    @property
    def cost_multiplier(self) -> float:
        over = self.heat - self.thermal_threshold_c
        return 1.0 + self.thermal_penalty * over if over > 0 else 1.0

    def step(self) -> None:
        # Tile chemistry remains part of the habitat, but memory, scheduler
        # time, and thermal pressure are taken directly from Linux/hardware.
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
        self.instructions_this_tick = 0
        self.tick += 1

    def __getstate__(self):
        state = dict(self.__dict__)
        state.pop("_pages", None)
        state.pop("_cgroup", None)
        state.pop("_temp_cache", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._pages = []
        self._cgroup = _self_cgroup()
        self._temp_cache = (0.0, cpu_temperature_c())
        if self.memory_used:
            self._commit_pages(self.memory_used)
