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

    def telemetry(self) -> dict:
        return {
            "age": self.age, "energy": round(self.energy, 2),
            "generation": self.generation, "births": self.births,
            "harvested": round(self.harvested, 2),
            "tasks_solved": dict(self.tasks_solved), "genome_length": len(self.genome),
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
        elif op == Op.SCAN:
            options = [(0, -1), (1, 0), (0, 1), (-1, 0)]
            self.a = max(range(4), key=lambda i: colony.world.tile_energy(self.x + options[i][0], self.y + options[i][1]))
        elif op == Op.MOVE:
            dx, dy = [(0, -1), (1, 0), (0, 1), (-1, 0)][self.a % 4]
            self.x, self.y = colony.world.wrap(self.x + dx, self.y + dy)
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
            self.a = self.last_inputs[self.input_index % 2]
            self.input_index += 1
        elif op == Op.NAND:
            self.a = (~(self.a & self.b)) & 0xFF
        elif op == Op.OUTPUT:
            name, reward = colony.tasks.evaluate(self.a, self.last_inputs)
            if name:
                self.energy += reward
                self.tasks_solved[name] = self.tasks_solved.get(name, 0) + 1
                colony.note_task(name)
        elif op == Op.IFZERO and self.a != 0:
            next_ip = (self.ip + 2) % len(self.genome)
        elif op == Op.PUSH:
            self.c = self.a
        self.ip = next_ip

    def free_child(self, world) -> None:
        if self.child is not None:
            world.release_memory(len(self.genome))
            self.child, self.copy_index = None, 0
