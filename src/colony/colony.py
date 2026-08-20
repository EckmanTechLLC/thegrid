"""Scheduler, selection, lineage tracking, and colony telemetry."""

from __future__ import annotations

from collections import Counter, deque
import random

from .isa import build_ancestor
from .mutation import RandomMutator
from .organism import Organism
from .tasks import TaskEnvironment
from .world import World


class Colony:
    def __init__(self, world: World | None = None, mutator=None, tasks=None,
                 seed: int = 42, founders: int = 6, max_age: int = 2400):
        self.world = world or World()
        self.mutator = mutator or RandomMutator()
        self.tasks = tasks or TaskEnvironment()
        self.rng = random.Random(seed)
        self.max_age = max_age
        self.organisms: list[Organism] = []
        self.next_id = 1
        self.births = 0
        self.deaths = 0
        self.deaths_by_cause: Counter = Counter()
        self.task_firsts: dict[str, int] = {}
        self.neighbor_reads = 0
        self.foreign_copies = 0
        self.experimental_ops: Counter = Counter()
        self.forecast_attempts = 0
        self.forecasts_solved = 0
        self.mutation_mechanisms: Counter = Counter()
        self.lifecycle_events = deque()
        ancestor = build_ancestor()
        for lineage in range(founders):
            if not self.world.request_memory(len(ancestor)):
                break
            founder = Organism(
                id=self._id(), genome=list(ancestor),
                x=self.rng.randrange(self.world.config.width),
                y=self.rng.randrange(self.world.config.height), lineage=lineage,
            )
            self.organisms.append(founder)
            self.lifecycle_events.append({"kind": "birth", "tick": self.world.tick,
                                          "organism": founder, "parent": None})

    def _id(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value

    def step(self) -> None:
        # Rotate the first execution slot so birth order does not permanently
        # decide who harvests a contested tile first. Unlike shuffling, this
        # does not consume the evolutionary RNG stream.
        current = list(self.organisms)
        offset = self.world.tick % len(current) if current else 0
        for organism in current[offset:] + current[:offset]:
            organism.execute(self)
        survivors = []
        for organism in self.organisms:
            cause = "starvation" if organism.energy <= 0 else ("senescence" if organism.age >= self.max_age else None)
            if cause:
                self.lifecycle_events.append({"kind": "death", "tick": self.world.tick,
                                              "organism": organism, "cause": cause})
                organism.free_child(self.world)
                self.world.release_memory(len(organism.genome))
                self.deaths += 1
                self.deaths_by_cause[cause] += 1
            else:
                survivors.append(organism)
        self.organisms = survivors
        self.world.step()

    def fork(self, parent: Organism) -> None:
        if parent.child is None or parent.copy_index != len(parent.genome):
            return
        reserved = len(parent.genome)
        proposal = list(parent.child)
        mutation_events = list(getattr(parent, "child_mutations", []))
        if hasattr(self.mutator, "offer"):
            self.mutator.offer(parent)
        proposal = self.mutator.mutate_at_birth(proposal, self.rng)
        mutation_events.extend(getattr(self.mutator, "last_events", []))
        delta = len(proposal) - reserved
        if delta > 0 and not self.world.request_memory(delta):
            parent.free_child(self.world)
            return
        if delta < 0:
            self.world.release_memory(-delta)
        parent.child, parent.copy_index, parent.child_mutations = None, 0, []
        if not proposal:
            self.world.release_memory(len(proposal))
            return
        dx, dy = self.rng.choice([(0, -1), (1, 0), (0, 1), (-1, 0)])
        x, y = self.world.wrap(parent.x + dx, parent.y + dy)
        child = Organism(self._id(), proposal, x, y, parent.lineage,
                           generation=parent.generation + 1, energy=16.0)
        parent.energy -= 8.0
        parent.births += 1
        self.births += 1
        self.mutation_mechanisms.update(mutation_events)
        self.organisms.append(child)
        self.lifecycle_events.append({"kind": "birth", "tick": self.world.tick,
                                      "organism": child, "parent": parent,
                                      "mutations": mutation_events})

    def note_task(self, name: str) -> None:
        self.task_firsts.setdefault(name, self.world.tick)

    def neighbor(self, organism: Organism) -> Organism | None:
        width, height = self.world.config.width, self.world.config.height
        for other in self.organisms:
            if other is organism:
                continue
            dx = min((other.x - organism.x) % width, (organism.x - other.x) % width)
            dy = min((other.y - organism.y) % height, (organism.y - other.y) % height)
            if dx + dy <= 1:
                return other
        return None

    def dominant_genome(self) -> tuple[list[int], int]:
        if not self.organisms:
            return [], 0
        counts = Counter(tuple(o.genome) for o in self.organisms)
        genome, carriers = counts.most_common(1)[0]
        return list(genome), carriers
