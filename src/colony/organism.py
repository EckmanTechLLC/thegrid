"""Organism VM. One instruction is one metabolic scheduling slice."""

from __future__ import annotations

from dataclasses import dataclass, field

from .isa import ISA, NUM_OPS, Op


@dataclass
class Organism:
    id: int
    genome: list[int]
    x: int
    y: int
    lineage: int
    generation: int = 0
    energy: float = 32.0
    age: int = 0
    ip: int = 0
    a: int = 0
    b: int = 0
    c: int = 1
    child: list[int] | None = None
    copy_index: int = 0
    child_mutations: list[str] = field(default_factory=list)
    tasks_solved: dict[str, int] = field(default_factory=dict)
    births: int = 0
    harvested: float = 0.0
    last_inputs: tuple[int, int] = (0, 0)
    input_index: int = 0
    signals_sent: int = 0
    bus_writes: int = 0
    bus_reads: int = 0
    signals_heard: int = 0
    signal_guided_moves: int = 0
    post_signal_harvested: float = 0.0
    structures_built: int = 0
    neighbor_reads: int = 0
    foreign_copies: int = 0
    moves: int = 0
    scans: int = 0
    guided_moves: int = 0
    post_move_harvested: float = 0.0
    task_inputs_seen: int = 0
    pending: list[int] = field(default_factory=list)  # spliced routine ops
    call_slot: int = -1              # slot currently being executed
    call_energy: float = 0.0         # caller energy when the routine started
    scan_pending: bool = False
    listen_pending: bool = False
    awaiting_post_move_harvest: bool = False
    awaiting_signal_harvest: bool = False
    scratch: list[int] = field(default_factory=lambda: [0] * 8)
    last_load_slot: int | None = None
    last_load_tick: int = -1
    forecast_target: int | None = None
    forecast_due_tick: int = -1
    forecast_expires_tick: int = -1
    forecast_stored_mask: int = 0
    forecast_attempts: int = 0
    forecasts_solved: int = 0
    weather_cues_seen: int = 0
    weather_cue_signals: int = 0
    weather_cue_value: int | None = None
    experimental_ops: dict[str, int] = field(default_factory=dict)
    salvaged: float = 0.0

    def telemetry(self) -> dict:
        return {
            "age": self.age, "energy": round(self.energy, 2),
            "generation": self.generation, "births": self.births,
            "harvested": round(self.harvested, 2),
            "tasks_solved": dict(self.tasks_solved), "genome_length": len(self.genome),
            "signals_sent": getattr(self, "signals_sent", 0),
            "signals_heard": getattr(self, "signals_heard", 0),
            "signal_guided_moves": getattr(self, "signal_guided_moves", 0),
            "post_signal_harvested": round(getattr(self, "post_signal_harvested", 0.0), 2),
            "structures_built": getattr(self, "structures_built", 0),
            "neighbor_reads": getattr(self, "neighbor_reads", 0),
            "foreign_copies": getattr(self, "foreign_copies", 0),
            "moves": getattr(self, "moves", 0),
            "scans": getattr(self, "scans", 0),
            "guided_moves": getattr(self, "guided_moves", 0),
            "post_move_harvested": round(getattr(self, "post_move_harvested", 0.0), 2),
            "scratch_nonzero": sum(value != 0 for value in getattr(self, "scratch", [])),
            "forecast_attempts": getattr(self, "forecast_attempts", 0),
            "forecasts_solved": getattr(self, "forecasts_solved", 0),
            "weather_cues_seen": getattr(self, "weather_cues_seen", 0),
            "weather_cue_signals": getattr(self, "weather_cue_signals", 0),
            "experimental_ops": dict(getattr(self, "experimental_ops", {})),
            "salvaged": round(getattr(self, "salvaged", 0.0), 2),
        }

    def execute(self, colony) -> None:
        if not self.genome:
            self.energy = 0
            return
        # A called routine's instructions execute inline without occupying the
        # genome — that is the whole point: reference, don't copy.
        if self.pending:
            word = self.pending.pop(0)
            from_routine = True
        else:
            word = self.genome[self.ip % len(self.genome)]
            from_routine = False
        op = Op(word) if 0 <= word < NUM_OPS else Op.NOP
        if op in (Op.ADD, Op.SUB, Op.XOR, Op.LOAD, Op.STORE, Op.JMPR,
                  Op.POST, Op.FETCH, Op.LOCATE):
            name = ISA[op].name
            self.experimental_ops[name] = self.experimental_ops.get(name, 0) + 1
            colony.experimental_ops[name] += 1
        self.energy -= ISA[op].cost * colony.world.instruction_cost_multiplier(
            op, self.x, self.y)
        colony.world.charge_instruction()
        self.age += 1
        next_ip = self.ip if from_routine else (self.ip + 1) % len(self.genome)

        if op == Op.HARVEST:
            gained = colony.world.harvest(self.x, self.y)
            self.energy += gained
            self.harvested += gained
            if getattr(self, "awaiting_post_move_harvest", False):
                self.post_move_harvested = getattr(self, "post_move_harvested", 0.0) + gained
                self.awaiting_post_move_harvest = False
            if getattr(self, "awaiting_signal_harvest", False):
                self.post_signal_harvested = getattr(self, "post_signal_harvested", 0.0) + gained
                self.awaiting_signal_harvest = False
        elif op == Op.SCAN:
            options = [(0, -1), (1, 0), (0, 1), (-1, 0)]
            self.a = max(range(4), key=lambda i: colony.world.tile_energy(self.x + options[i][0], self.y + options[i][1]))
            self.scans = getattr(self, "scans", 0) + 1
            self.scan_pending = True
            self.listen_pending = False
        elif op == Op.MOVE:
            dx, dy = [(0, -1), (1, 0), (0, 1), (-1, 0)][self.a % 4]
            self.x, self.y = colony.world.move(self.x, self.y, dx, dy)
            self.moves = getattr(self, "moves", 0) + 1
            if getattr(self, "scan_pending", False):
                self.guided_moves = getattr(self, "guided_moves", 0) + 1
            if getattr(self, "listen_pending", False):
                self.signal_guided_moves = getattr(self, "signal_guided_moves", 0) + 1
                self.awaiting_signal_harvest = True
            self.scan_pending = False
            self.listen_pending = False
            self.awaiting_post_move_harvest = True
        elif op == Op.ALLOC and self.child is None:
            if colony.world.request_memory(len(self.genome)):
                self.child, self.copy_index, self.child_mutations = [], 0, []
        elif op == Op.COPY and self.child is not None and self.copy_index < len(self.genome):
            source = self.genome[self.copy_index]
            copied = colony.mutator.copy_error(source, colony.rng)
            self.child.append(copied)
            if copied != source:
                self.child_mutations.append("point_substitution")
            self.copy_index += 1
        elif op == Op.IFNOTDONE and (self.child is None or self.copy_index >= len(self.genome)):
            next_ip = (self.ip + 2) % len(self.genome)
        elif op == Op.JMPB:
            next_ip = (self.ip - ((self.c % 8) + 1)) % len(self.genome)
        elif op == Op.FORK:
            colony.fork(self)
        elif op == Op.FREE:
            self.free_child(colony.world)
        elif op == Op.INC:
            self.a = (self.a + 1) & 0xFF
        elif op == Op.DEC:
            self.a = (self.a - 1) & 0xFF
        elif op == Op.SWAP:
            self.a, self.b = self.b, self.a
        elif op == Op.INPUT:
            if self.input_index == 0:
                # A temporal challenge keeps replaying its cue pair until it is
                # solved or expires, so a looping genome can recompute and
                # recover the same forecast instead of being handed a moving
                # target every circuit.
                if self.forecast_target is None or colony.world.tick > self.forecast_expires_tick:
                    cue = colony.world.weather_cue(self.x, self.y)
                    self.last_inputs = colony.tasks.inputs(
                        colony.world.tick, self.id, weather_cue=cue)
                    self.weather_cue_value = cue
                    if cue is not None:
                        self.weather_cues_seen = getattr(self, "weather_cues_seen", 0) + 1
                        colony.weather_cues_seen += 1
                self.task_inputs_seen = 0
            self.a = self.last_inputs[self.input_index % 2]
            self.input_index = (self.input_index + 1) % 2
            self.task_inputs_seen = getattr(self, "task_inputs_seen", 0) + 1
            if (self.input_index == 0
                    and hasattr(colony.tasks, "forecast_target")
                    and (self.forecast_target is None
                         or colony.world.tick > self.forecast_expires_tick)):
                self.forecast_target = colony.tasks.forecast_target(self.last_inputs)
                self.forecast_due_tick = colony.world.tick + colony.tasks.forecast_delay
                self.forecast_expires_tick = self.forecast_due_tick + colony.tasks.forecast_window
                self.forecast_stored_mask = 0
        elif op == Op.NAND:
            self.a = (~(self.a & self.b)) & 0xFF
        elif op == Op.OUTPUT:
            # A task challenge is valid only after both fresh inputs have been
            # read, and every challenge can be submitted at most once.
            name, reward = None, 0.0
            tick = colony.world.tick
            if self.forecast_target is not None and tick >= self.forecast_due_tick:
                self.forecast_attempts += 1
                colony.forecast_attempts += 1
                recovered_after_due = (
                    self.last_load_tick >= self.forecast_due_tick
                    and self.last_load_slot is not None
                    and self.forecast_stored_mask & (1 << self.last_load_slot)
                    and tick - self.last_load_tick <= max(2, len(self.genome))
                )
                if tick <= self.forecast_expires_tick and recovered_after_due:
                    name, reward = colony.tasks.evaluate_forecast(
                        self.a, self.forecast_target)
                if name == "forecast" or tick > self.forecast_expires_tick:
                    self.forecast_target = None
                    self.forecast_due_tick = -1
                    self.forecast_expires_tick = -1
                    self.forecast_stored_mask = 0
                if name == "forecast":
                    self.forecasts_solved += 1
                    colony.forecasts_solved += 1
            if name is None and getattr(self, "task_inputs_seen", 0) >= 2:
                name, reward = colony.tasks.evaluate(self.a, self.last_inputs)
                self.task_inputs_seen = 0
            if name:
                self.energy += reward * colony.world.task_reward_multiplier(self.x, self.y)
                self.tasks_solved[name] = self.tasks_solved.get(name, 0) + 1
                colony.note_task(name)
        elif op == Op.IFZERO and self.a != 0:
            next_ip = (self.ip + 2) % len(self.genome)
        elif op == Op.PUSH:
            self.c = self.a
        elif op == Op.SIGNAL:
            colony.world.signal(self.x, self.y, self.a)
            self.signals_sent = getattr(self, "signals_sent", 0) + 1
            if (getattr(self, "weather_cue_value", None) is not None
                    and self.a == self.weather_cue_value):
                self.weather_cue_signals = getattr(self, "weather_cue_signals", 0) + 1
                colony.weather_cue_signals += 1
        elif op == Op.LISTEN:
            strength = colony.world.listen_strength(self.x, self.y)
            self.a = colony.world.listen(self.x, self.y)
            self.listen_pending = strength > 0
            self.scan_pending = False
            if strength > 0:
                self.signals_heard = getattr(self, "signals_heard", 0) + 1
        elif op == Op.BUILD:
            build_cost = colony.world.build_cost(self.x, self.y)
            if self.energy >= build_cost:
                self.energy -= build_cost
                colony.world.build(self.x, self.y)
                self.structures_built = getattr(self, "structures_built", 0) + 1
        elif op == Op.PEEK:
            other = colony.neighbor(self)
            if other and other.genome:
                self.a = other.genome[self.b % len(other.genome)]
                self.neighbor_reads = getattr(self, "neighbor_reads", 0) + 1
                colony.neighbor_reads += 1
        elif op == Op.COPYN and self.child is not None and self.copy_index < len(self.genome):
            # Horizontal transfer of a contiguous SEGMENT, not a single word.
            # Single-word transfer is functionally inert: acquiring a neighbour's
            # capability (e.g. an input/nand/output block) would need several
            # consecutive COPYN hits at exactly the right indices. Biology moves
            # functional units — a whole gene arrives in one event — which is why
            # HGT is an evolutionary force at all. Segment length is small and
            # random so this is transfer, not wholesale genome theft. Nothing here
            # chooses WHAT is copied or rewards any outcome; it only makes the
            # combination of separately-evolved capabilities physically possible.
            other = colony.neighbor(self)
            if other and other.genome:
                span = colony.rng.randint(2, 6)
                start = self.copy_index % len(other.genome)
                for offset in range(span):
                    if self.copy_index >= len(self.genome):
                        break
                    word = other.genome[(start + offset) % len(other.genome)]
                    copied = colony.mutator.copy_error(word, colony.rng)
                    self.child.append(copied)
                    if copied != word:
                        self.child_mutations.append("point_substitution")
                    self.copy_index += 1
                    self.foreign_copies = getattr(self, "foreign_copies", 0) + 1
                    colony.foreign_copies += 1
                self.child_mutations.append("segment_transfer")
        elif op == Op.ADD:
            self.a = (self.a + self.b) & 0xFF
        elif op == Op.SUB:
            self.a = (self.a - self.b) & 0xFF
        elif op == Op.XOR:
            self.a = (self.a ^ self.b) & 0xFF
        elif op == Op.LOAD:
            scratch = getattr(self, "scratch", [0] * 8)
            slot = self.b % len(scratch)
            self.a = scratch[slot]
            self.last_load_slot = slot
            self.last_load_tick = colony.world.tick
        elif op == Op.STORE:
            scratch = getattr(self, "scratch", None)
            if scratch is None:
                self.scratch = scratch = [0] * 8
            slot = self.b % len(scratch)
            scratch[slot] = self.a & 0xFF
            if (self.forecast_target is not None
                    and colony.world.tick < self.forecast_due_tick
                    and scratch[slot] == self.forecast_target):
                self.forecast_stored_mask |= 1 << slot
        elif op == Op.POST:
            colony.world.bus_post(self.b, self.a, writer=self.id)
            self.bus_writes = getattr(self, "bus_writes", 0) + 1
            colony.bus_writes = getattr(colony, "bus_writes", 0) + 1
        elif op == Op.LOCATE:
            self.a = colony.world.biome(self.x, self.y)
        elif op == Op.FETCH:
            self.a = colony.world.bus_fetch(self.b)
            self.bus_reads = getattr(self, "bus_reads", 0) + 1
            colony.bus_reads = getattr(colony, "bus_reads", 0) + 1
        elif op == Op.JMPR:
            next_ip = (self.ip + (self.c % 15) - 7) % len(self.genome)
        elif op == Op.SALVAGE:
            gained = colony.world.salvage(self.x, self.y)
            self.energy += gained
            self.salvaged = getattr(self, "salvaged", 0.0) + gained
            colony.salvaged += gained
        elif op == Op.PUBLISH:
            if self.genome and self.energy > 3.0:
                start = self.b % len(self.genome)
                seg = [self.genome[(start + k) % len(self.genome)] for k in range(8)]
                if colony.world.publish_routine(self.a, seg, owner=self.id):
                    self.published = getattr(self, "published", 0) + 1
                    colony.published = getattr(colony, "published", 0) + 1
                else:
                    # The address is held by a routine somebody still calls.
                    # The energy is spent either way; the claim is refused.
                    colony.publish_refused = getattr(colony, "publish_refused", 0) + 1
        elif op == Op.CALL:
            routine = colony.world.get_routine(self.a)
            # depth guard: a routine that calls itself cannot run away
            if routine and len(self.pending) < 24:
                if self.call_slot < 0:
                    self.call_slot = self.a % len(colony.world.code_slots)
                    self.call_energy = self.energy
                self.pending.extend(routine)
                self.calls = getattr(self, "calls", 0) + 1
                colony.calls = getattr(colony, "calls", 0) + 1
        elif op == Op.WRITE:
            if self.genome:
                pos = self.b % len(self.genome)
                self.genome[pos] = self.a % NUM_OPS
                self.self_writes = getattr(self, "self_writes", 0) + 1
                colony.self_writes = getattr(colony, "self_writes", 0) + 1
        # ── royalty settlement ────────────────────────────────────────────
        # A routine is USEFUL if running it left the caller better off. The
        # publisher takes a cut OF THAT GAIN — a transfer, never newly minted —
        # so the commons cannot inflate the way the task faucet did. Useless
        # code earns its author nothing, and you cannot farm your own routine.
        if from_routine and not self.pending and self.call_slot >= 0:
            gain = self.energy - self.call_energy
            if gain > 0:
                owner_id = colony.world.slot_owner[self.call_slot]
                if owner_id >= 0 and owner_id != self.id:
                    owner = colony.organism_by_id(owner_id)
                    if owner is not None:
                        cut = gain * 0.15
                        self.energy -= cut
                        owner.energy += cut
                        owner.royalties = getattr(owner, "royalties", 0.0) + cut
                        colony.royalties = getattr(colony, "royalties", 0.0) + cut
                        colony.royalty_events = getattr(colony, "royalty_events", 0) + 1
            self.call_slot = -1
        self.ip = next_ip

    def free_child(self, world) -> None:
        if self.child is not None:
            world.release_memory(len(self.genome))
            self.child, self.copy_index, self.child_mutations = None, 0, []
