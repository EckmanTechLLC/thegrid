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
                 seed: int = 42, founders: int = 6, max_age: int = 2400,
                 founder_genomes: list[list[int]] | None = None,
                 founder_copies: int = 1, features: set | None = None):
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
        self.weather_cues_seen = 0
        self.weather_cue_signals = 0
        self.mutation_mechanisms: Counter = Counter()
        self.scrap_deposited = 0.0
        self.salvaged = 0.0
        self.published = 0      # routines written to the shared code commons
        self.calls = 0          # routine invocations (referenced, not copied)
        self.self_writes = 0    # in-life genome edits (Lamarckian: COPY reads genome)
        self.royalties = 0.0    # energy transferred to publishers of useful routines
        self.royalty_events = 0
        # Which frontier mechanics this colony has. A disabled op executes as
        # a nop rather than being absent, so opcode indices and glyphs stay
        # identical across every arm and genomes remain comparable.
        self.features = set(features or ())
        self.burns = 0
        self.bounties_offered = 0
        self.macros_defined = 0
        self.macro_runs = 0
        self.next_group = 1
        self.links = 0          # successful bindings
        self.group_births = 0   # members copied by a groupmate's replication
        self.lifecycle_events = deque()
        genomes = founder_genomes or [build_ancestor() for _ in range(founders)]
        if len(genomes) < founders:
            raise ValueError("founder_genomes must contain at least one genome per founder")
        # Seed distinct, viable niches. Random placement on a patchy field can
        # erase most founder diversity before evolution even begins.
        positions = [(x, y) for y in range(self.world.config.height)
                     for x in range(self.world.config.width)]
        self.rng.shuffle(positions)
        positions.sort(key=lambda p: self.world.tile_energy(*p), reverse=True)
        if founder_copies < 1:
            raise ValueError("founder_copies must be positive")
        position_index = 0
        for lineage in range(founders):
            genome = list(genomes[lineage])
            if not genome:
                raise ValueError("founder genomes cannot be empty")
            for _ in range(founder_copies):
                if not self.world.request_memory(len(genome)):
                    return
                x, y = positions[position_index]
                position_index += 1
                founder = Organism(
                    id=self._id(), genome=list(genome), x=x, y=y,
                    lineage=lineage, energy=48.0,
                )
                self.organisms.append(founder)
                self.lifecycle_events.append({"kind": "birth", "tick": self.world.tick,
                                              "organism": founder, "parent": None})

    def _id(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value

    def step(self) -> None:
        # Unworked tasks drift back up in price each tick (scarcity pricing).
        self.tasks.decay_rates()
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
                self.scrap_deposited += self.world.deposit_scrap(
                    organism.x, organism.y, len(organism.genome), organism.energy)
                self.lifecycle_events.append({"kind": "death", "tick": self.world.tick,
                                              "organism": organism, "cause": cause})
                organism.free_child(self.world)
                self.world.release_memory(len(organism.genome))
                self.deaths += 1
                self.deaths_by_cause[cause] += 1
            else:
                survivors.append(organism)
        self.organisms = survivors
        if "bounty" in self.features:
            self.expire_bounties()
        self.world.step()
        if "burn" in self.features:
            # Real cycles, spent after the tick's bookkeeping so the cost lands
            # on this machine rather than on the colony's own accounting.
            self.world.spend_cycles()

    def expire_bounties(self) -> None:
        """Refund escrow nobody claimed. An offerer who died forfeits it."""
        world = self.world
        for address, bounty in enumerate(world.bounties):
            if bounty is None or world.tick - bounty["tick"] < world.bounty_ttl:
                continue
            world.bounties[address] = None
            world.bounty_expired += 1
            owner = self.organism_by_id(bounty["owner"])
            if owner is not None:
                owner.energy += bounty["escrow"]

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
        if parent.energy <= self.CHILD_ENERGY:
            self.world.release_memory(len(proposal))
            return
        child = Organism(self._id(), proposal, x, y, parent.lineage,
                           generation=parent.generation + 1,
                           energy=self.CHILD_ENERGY)
        parent.energy -= self.CHILD_ENERGY
        parent.births += 1
        self.births += 1
        self.mutation_mechanisms.update(mutation_events)
        self.organisms.append(child)
        self.lifecycle_events.append({"kind": "birth", "tick": self.world.tick,
                                      "organism": child, "parent": parent,
                                      "mutations": mutation_events})
        # The group is the unit that reproduces. Every other bound member is
        # copied alongside, into the child's new group - so a member carrying no
        # replication machinery of its own is still inherited.
        if parent.group >= 0:
            others = [o for o in self.members(parent.group) if o is not parent]
            if others:
                child.group = offspring_group = self.next_group
                self.next_group += 1
                for member in others:
                    self._copy_member(member, child, offspring_group)

    MAX_GROUP = 8   # a bound unit cannot exceed this; a bound on cost, not a design

    # Reproduction is paid for, not subsidised. A child used to appear holding
    # 16.0 while the parent was charged only 8.0 - eight units created from
    # nothing on every birth, flat, regardless of genome length. Over one epoch
    # colony seven minted 15.7 MILLION units that way, against 1,545 sitting on
    # its entire map, and evolved a one-word genome to farm it: the shorter the
    # program, the larger the subsidy relative to its cost. That faucet was far
    # larger than the pasture, the task budget and salvage combined, so every
    # scarcity result in this project was measured against a world that printed
    # money. The child's energy now comes out of the parent, and a parent that
    # cannot cover it does not reproduce.
    CHILD_ENERGY = 16.0

    def members(self, group: int) -> list:
        return [o for o in self.organisms if o.group == group] if group >= 0 else []

    def _dissolve_if_alone(self, organism) -> None:
        """A unit of one is not a unit. Without this, an organism whose
        groupmates have died stays flagged as bound, and since two grouped
        organisms are never merged, every survivor eventually ends up in a
        dead singleton and linking stops working altogether."""
        if organism.group >= 0 and len(self.members(organism.group)) < 2:
            organism.group = -1

    def link(self, initiator, other) -> bool:
        """Bind two programs into one unit. Unilateral: consent is not required."""
        self._dissolve_if_alone(initiator)
        self._dissolve_if_alone(other)
        a, b = initiator.group, other.group
        if a >= 0 and a == b:
            return False
        if a >= 0 and b >= 0:
            return False                      # merging two groups is not offered
        if b >= 0:                            # attach to the neighbour's group
            if len(self.members(b)) >= self.MAX_GROUP:
                return False
            initiator.group = b
        elif a >= 0:                          # pull the neighbour into mine
            if len(self.members(a)) >= self.MAX_GROUP:
                return False
            other.group = a
        else:
            initiator.group = other.group = self.next_group
            self.next_group += 1
        self.links += 1
        return True

    def _copy_member(self, member, anchor, group: int) -> None:
        """Reproduce one bound member off a groupmate's replication event.

        The member pays for its own copy, which is what keeps binding neutral
        rather than subsidised: a group of identical programs costs exactly
        what the same programs cost unbound.
        """
        if member.energy <= self.CHILD_ENERGY:
            return
        genome = list(member.genome)
        if not self.world.request_memory(len(genome)):
            return
        proposal = self.mutator.mutate_at_birth(genome, self.rng)
        delta = len(proposal) - len(genome)
        if delta > 0 and not self.world.request_memory(delta):
            self.world.release_memory(len(genome))
            return
        if delta < 0:
            self.world.release_memory(-delta)
        if not proposal:
            self.world.release_memory(len(proposal))
            return
        dx, dy = self.rng.choice([(0, -1), (1, 0), (0, 1), (-1, 0)])
        x, y = self.world.wrap(anchor.x + dx, anchor.y + dy)
        child = Organism(self._id(), proposal, x, y, member.lineage,
                         generation=member.generation + 1,
                         energy=self.CHILD_ENERGY)
        child.group = group
        member.energy -= self.CHILD_ENERGY
        member.births += 1
        self.births += 1
        self.group_births += 1
        self.organisms.append(child)
        self.lifecycle_events.append({"kind": "birth", "tick": self.world.tick,
                                      "organism": child, "parent": member})

    def organism_by_id(self, oid: int):
        for organism in self.organisms:
            if organism.id == oid:
                return organism
        return None

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
