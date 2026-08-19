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
    tasks_solved: dict[str, int] = field(default_factory=dict)
    births: int = 0
    harvested: float = 0.0
    last_inputs: tuple[int, int] = (0, 0)
    input_index: int = 0
    signals_sent: int = 0
    structures_built: int = 0
    neighbor_reads: int = 0
    foreign_copies: int = 0
    moves: int = 0
    scans: int = 0
    guided_moves: int = 0
    post_move_harvested: float = 0.0
    task_inputs_seen: int = 0
    scan_pending: bool = False
    awaiting_post_move_harvest: bool = False

    def telemetry(self) -> dict:
        return {
            "age": self.age, "energy": round(self.energy, 2),
            "generation": self.generation, "births": self.births,
            "harvested": round(self.harvested, 2),
            "tasks_solved": dict(self.tasks_solved), "genome_length": len(self.genome),
            "signals_sent": getattr(self, "signals_sent", 0),
            "structures_built": getattr(self, "structures_built", 0),
            "neighbor_reads": getattr(self, "neighbor_reads", 0),
            "foreign_copies": getattr(self, "foreign_copies", 0),
            "moves": getattr(self, "moves", 0),
            "scans": getattr(self, "scans", 0),
            "guided_moves": getattr(self, "guided_moves", 0),
            "post_move_harvested": round(getattr(self, "post_move_harvested", 0.0), 2),
        }

    def execute(self, colony) -> None:
        if not self.genome:
            self.energy = 0
            return
        word = self.genome[self.ip % len(self.genome)]
        op = Op(word) if 0 <= word < NUM_OPS else Op.NOP
        self.energy -= ISA[op].cost * colony.world.cost_multiplier
        colony.world.charge_instruction()
        self.age += 1
        next_ip = (self.ip + 1) % len(self.genome)

        if op == Op.HARVEST:
            gained = colony.world.harvest(self.x, self.y)
            self.energy += gained
            self.harvested += gained
            if getattr(self, "awaiting_post_move_harvest", False):
                self.post_move_harvested = getattr(self, "post_move_harvested", 0.0) + gained
                self.awaiting_post_move_harvest = False
        elif op == Op.SCAN:
            options = [(0, -1), (1, 0), (0, 1), (-1, 0)]
            self.a = max(range(4), key=lambda i: colony.world.tile_energy(self.x + options[i][0], self.y + options[i][1]))
            self.scans = getattr(self, "scans", 0) + 1
            self.scan_pending = True
        elif op == Op.MOVE:
            dx, dy = [(0, -1), (1, 0), (0, 1), (-1, 0)][self.a % 4]
            self.x, self.y = colony.world.wrap(self.x + dx, self.y + dy)
            self.moves = getattr(self, "moves", 0) + 1
            if getattr(self, "scan_pending", False):
                self.guided_moves = getattr(self, "guided_moves", 0) + 1
            self.scan_pending = False
            self.awaiting_post_move_harvest = True
        elif op == Op.ALLOC and self.child is None:
            if colony.world.request_memory(len(self.genome)):
                self.child, self.copy_index = [], 0
        elif op == Op.COPY and self.child is not None and self.copy_index < len(self.genome):
            self.child.append(colony.mutator.copy_error(self.genome[self.copy_index], colony.rng))
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
                self.last_inputs = colony.tasks.inputs(colony.world.tick, self.id)
                self.task_inputs_seen = 0
            self.a = self.last_inputs[self.input_index % 2]
            self.input_index = (self.input_index + 1) % 2
            self.task_inputs_seen = getattr(self, "task_inputs_seen", 0) + 1
        elif op == Op.NAND:
            self.a = (~(self.a & self.b)) & 0xFF
        elif op == Op.OUTPUT:
            # A task challenge is valid only after both fresh inputs have been
            # read, and every challenge can be submitted at most once.
            if getattr(self, "task_inputs_seen", 0) < 2:
                name, reward = None, 0.0
            else:
                name, reward = colony.tasks.evaluate(self.a, self.last_inputs)
                self.task_inputs_seen = 0
            if name:
                self.energy += reward
                self.tasks_solved[name] = self.tasks_solved.get(name, 0) + 1
                colony.note_task(name)
        elif op == Op.IFZERO and self.a != 0:
            next_ip = (self.ip + 2) % len(self.genome)
        elif op == Op.PUSH:
            self.c = self.a
        elif op == Op.SIGNAL:
            colony.world.signal(self.x, self.y, self.a)
            self.signals_sent = getattr(self, "signals_sent", 0) + 1
        elif op == Op.LISTEN:
            self.a = colony.world.listen(self.x, self.y)
        elif op == Op.BUILD:
            if self.energy >= 4.0:
                self.energy -= 4.0
                colony.world.build(self.x, self.y)
                self.structures_built = getattr(self, "structures_built", 0) + 1
        elif op == Op.PEEK:
            other = colony.neighbor(self)
            if other and other.genome:
                self.a = other.genome[self.b % len(other.genome)]
                self.neighbor_reads = getattr(self, "neighbor_reads", 0) + 1
                colony.neighbor_reads += 1
        elif op == Op.COPYN and self.child is not None and self.copy_index < len(self.genome):
            other = colony.neighbor(self)
            if other and other.genome:
                word = other.genome[self.copy_index % len(other.genome)]
                self.child.append(colony.mutator.copy_error(word, colony.rng))
                self.copy_index += 1
                self.foreign_copies = getattr(self, "foreign_copies", 0) + 1
                colony.foreign_copies += 1
        self.ip = next_ip

    def free_child(self, world) -> None:
        if self.child is not None:
            world.release_memory(len(self.genome))
            self.child, self.copy_index = None, 0
