from src.colony.colony import Colony
from src.colony.isa import build_ancestor
from src.colony.mutation import RandomMutator, parse_genome
from src.colony.world import World, WorldConfig
from src.colony.live import Habitat
from src.colony.odin_operator import OdinMutator
from src.colony.organism import Organism
import json
import random


def test_ancestor_reproduces_and_memory_accounts():
    world = World(WorldConfig(width=8, height=8, tile_regen=0.5, memory_cap=500, seed=7))
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0), seed=7, founders=1)
    for _ in range(100):
        colony.step()
    assert colony.births > 0
    assert world.memory_used == sum(len(o.genome) + (len(o.genome) if o.child is not None else 0) for o in colony.organisms)


def test_seed_is_deterministic():
    def run():
        colony = Colony(World(WorldConfig(width=8, height=8, seed=11)), seed=11, founders=2)
        for _ in range(80):
            colony.step()
        return len(colony.organisms), colony.births, colony.deaths, colony.world.memory_used
    assert run() == run()


def test_parse_genome_rejects_unknown_ops():
    assert parse_genome('["harvest", "alloc"]') is not None
    assert parse_genome('["become_god"]') is None


def test_ancestor_is_valid():
    assert build_ancestor()
    assert all(isinstance(word, int) for word in build_ancestor())


def test_live_habitat_restores_checkpoint(tmp_path):
    state = tmp_path / "colony.pkl"
    habitat = Habitat(state, seed=9, founders=2, physical=False)
    for _ in range(25):
        habitat.step()
    habitat.save()

    restored = Habitat(state, physical=False)
    assert restored.colony.world.tick == 25
    assert restored.snapshot()["population"] == len(restored.colony.organisms)


def test_odin_operator_queues_and_consumes_authored_variant(tmp_path):
    mutator = OdinMutator(tmp_path, rate=1.0, energy_cost=1.0)
    mutator.base.point_rate = 0
    mutator.base.indel_rate = 0
    parent = Organism(1, build_ancestor(), 0, 0, 0, energy=100)
    original = list(parent.genome)
    mutator.offer(parent)
    assert mutator.mutate_at_birth(list(original), random.Random(1)) == original
    assert (tmp_path / "request.json").exists()

    names = ["harvest", "alloc", "copy", "ifnotdone", "jmpb", "fork"]
    (tmp_path / "proposal.json").write_text(json.dumps({"genome": names}))
    mutator.offer(parent)
    proposal = mutator.mutate_at_birth(list(original), random.Random(1))
    assert proposal != original
    assert mutator.accepted == 1
    assert not (tmp_path / "proposal.json").exists()
