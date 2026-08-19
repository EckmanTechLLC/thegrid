from src.colony.colony import Colony
from src.colony.isa import Op, build_ancestor
from src.colony.mutation import RandomMutator, parse_genome
from src.colony.world import World, WorldConfig
from src.colony.live import Habitat
from src.colony.odin_operator import OdinMutator
from src.colony.organism import Organism
from src.colony.history import LineageHistory
import json
import random
from types import SimpleNamespace


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
    habitat.save()
    assert state.with_suffix(".previous.pkl").exists()

    restored = Habitat(state, physical=False)
    assert restored.colony.world.tick == 25
    assert restored.snapshot()["population"] == len(restored.colony.organisms)
    assert len(restored.snapshot()["signalField"]) == 32 * 32
    assert len(restored.snapshot()["structureField"]) == 32 * 32


def test_extinction_releases_old_colony_and_seeds_one_new_epoch(tmp_path):
    habitat = Habitat(tmp_path / "extinction.pkl", founders=2, physical=False)
    habitat.colony.organisms.clear()
    habitat.step()
    assert habitat.epoch == 2
    assert len(habitat.colony.organisms) == 2


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


def test_ecology_instructions_enable_communication_construction_and_parasitism():
    world = World(WorldConfig(width=4, height=4, memory_cap=500, seed=3))
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    seed=3, founders=2)
    sender, receiver = colony.organisms
    sender.x = receiver.x = 1
    sender.y = receiver.y = 1

    sender.genome, sender.a = [Op.SIGNAL], 73
    sender.execute(colony)
    receiver.genome = [Op.LISTEN]
    receiver.execute(colony)
    assert receiver.a == 73

    sender.genome, sender.energy = [Op.BUILD], 20
    sender.execute(colony)
    assert world.structures[1][1] == 1

    sender.genome, sender.b = [Op.PEEK], 0
    receiver.genome = [Op.NAND, Op.OUTPUT]
    sender.execute(colony)
    assert sender.a == Op.NAND

    sender.genome = [Op.COPYN]
    sender.child, sender.copy_index = [], 0
    sender.execute(colony)
    assert sender.child == [Op.NAND]
    assert colony.foreign_copies == 1


def test_task_reward_requires_two_fresh_inputs_and_is_single_use():
    colony = Colony(World(WorldConfig(width=4, height=4, memory_cap=100, seed=5)),
                    RandomMutator(point_rate=0, indel_rate=0), seed=5, founders=1)
    organism = colony.organisms[0]
    organism.genome = [Op.OUTPUT]
    before = organism.energy
    organism.execute(colony)
    assert organism.energy < before
    assert organism.tasks_solved == {}

    organism.genome = [Op.INPUT]
    organism.execute(colony)
    organism.execute(colony)
    organism.a = organism.last_inputs[0] & organism.last_inputs[1]
    organism.genome = [Op.OUTPUT]
    before = organism.energy
    organism.execute(colony)
    rewarded = organism.energy
    assert rewarded > before
    assert organism.tasks_solved == {"and": 1}
    organism.execute(colony)
    assert organism.energy < rewarded
    assert organism.tasks_solved == {"and": 1}


def test_movement_telemetry_distinguishes_guided_and_unguided_moves():
    colony = Colony(World(WorldConfig(width=4, height=4, memory_cap=100, seed=6)),
                    RandomMutator(point_rate=0, indel_rate=0), seed=6, founders=1)
    organism = colony.organisms[0]
    organism.genome = [Op.MOVE]
    organism.execute(colony)
    assert organism.moves == 1
    assert organism.guided_moves == 0

    organism.genome = [Op.SCAN]
    organism.execute(colony)
    organism.genome = [Op.MOVE]
    organism.execute(colony)
    organism.genome = [Op.HARVEST]
    organism.execute(colony)
    assert organism.moves == 2
    assert organism.scans == 1
    assert organism.guided_moves == 1
    assert organism.post_move_harvested > 0


def test_lineage_history_aggregates_genomes_transitions_and_epoch(tmp_path):
    colony = Colony(World(WorldConfig(width=4, height=4, memory_cap=300, seed=8)),
                    RandomMutator(point_rate=0, indel_rate=0), seed=8, founders=1)
    history = LineageHistory(tmp_path / "history.sqlite3")
    history.start_epoch(3, 8, 100.0)
    history.record(3, colony.lifecycle_events)
    colony.lifecycle_events.clear()
    for _ in range(30):
        colony.step()
        history.record(3, colony.lifecycle_events)
        colony.lifecycle_events.clear()
    summary = history.summary(3)
    assert summary["totals"]["genomes"] == 1
    assert summary["totals"]["births"] > 1
    assert summary["genomes"][0]["source"].startswith("harvest · harvest")
    history.finish_epoch(3, colony)
    assert history.summary(3)["epochs"][0]["ended_tick"] == colony.world.tick
    history.close()


def test_lineage_history_ranks_mutation_establishment(tmp_path):
    history = LineageHistory(tmp_path / "success.sqlite3")
    history.start_epoch(1, 1, 100.0)
    ancestor = SimpleNamespace(genome=[Op.HARVEST])
    for index, generation in enumerate((5, 7, 9, 12, 15)):
        organism = SimpleNamespace(genome=[Op.MOVE], generation=generation)
        parent = ancestor if index == 0 else SimpleNamespace(genome=[Op.MOVE])
        history.record(1, [{"kind": "birth", "tick": 10 + index,
                            "organism": organism, "parent": parent}])
    success = history.summary(1)["mutationSuccess"][0]
    assert success["births"] == 5
    assert success["observed_generations"] == 10
    assert success["age_ticks"] == 4
    assert success["tier"] == "growing"
    history.close()


def test_lineage_history_compacts_ecology_into_tick_buckets(tmp_path):
    history = LineageHistory(tmp_path / "ecology.sqlite3")
    history.start_epoch(1, 1, 100.0)
    metrics = dict(diversity=3, dominance=0.5, genome_length=11.0,
                   resources=2.5, built=1, signals=2)
    history.record_ecology(1, 10, population=10, **metrics)
    history.record_ecology(1, 20, population=20, **metrics)
    history.record_ecology(1, 20, population=20, **metrics)
    history.record_ecology(1, 510, population=30, **metrics)
    ecology = history.summary(1)["ecology"]
    assert len(ecology) == 2
    assert ecology[0]["samples"] == 2
    assert ecology[0]["population_avg"] == 15
    assert ecology[0]["population_min"] == 10
    assert ecology[0]["population_max"] == 20
    assert ecology[1]["population_avg"] == 30
    history.close()


def test_live_inspector_tracks_current_organism_and_recent_death(tmp_path):
    habitat = Habitat(tmp_path / "inspect.pkl", seed=14, founders=1, physical=False)
    organism = habitat.colony.organisms[0]
    detail = habitat.organism_latest[(habitat.epoch, organism.id)]
    assert detail["status"] == "alive"
    assert detail["currentInstruction"] == "harvest"
    assert detail["genome"][0:2] == ["harvest", "harvest"]
    assert len(detail["genomeId"]) == 16
    assert detail["genomeGlyph"] == detail["genomeId"][0]
    assert len(habitat.latest["genomeGlyphs"]) == habitat.latest["population"]
    organism.energy = -1_000_000
    habitat.step()
    dead = habitat.recent_deaths[-1]
    assert dead["id"] == organism.id
    assert dead["status"] == "dead"
    assert dead["cause"] == "starvation"
    habitat.history.close()
