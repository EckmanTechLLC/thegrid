from src.colony.colony import Colony
from src.colony.isa import ISA, Op, build_ancestor, build_founder_palette
from src.colony.record import encode_positions
from src.colony.mutation import ExperimentalMutator, RandomMutator, parse_genome
from src.colony.world import World, WorldConfig
from src.colony.live import Habitat
from src.colony.odin_operator import OdinMutator
from src.colony.organism import Organism
from src.colony.history import LineageHistory
from src.colony.tasks import TemporalTaskEnvironment
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


def test_diverse_founders_are_unique_viable_and_fit_large_map_encoding():
    palette = build_founder_palette()
    assert len(palette) == len({tuple(genome) for genome in palette}) == 12
    for lineage, genome in enumerate(palette):
        world = World(WorldConfig(width=48, height=48, tile_regen=0.5,
                                  memory_cap=500, seed=100 + lineage))
        colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                        seed=100 + lineage, founders=1,
                        founder_genomes=[genome])
        for _ in range(300):
            colony.step()
        assert colony.births > 0, f"founder {lineage} did not reproduce"
    colony = Colony(World(WorldConfig(width=48, height=48, seed=5)),
                    founders=12, founder_genomes=palette)
    colony.organisms[0].x, colony.organisms[0].y = 47, 47
    encoded = encode_positions(colony, 48)
    assert len(encoded) == 4 * len(colony.organisms)
    assert encoded[:3] == "27v"  # base-32 encoding of tile 2303


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
    assert len(restored.snapshot()["signalField"]) == 48 * 48
    assert len(restored.snapshot()["structureField"]) == 48 * 48


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


def test_signals_radiate_and_can_guide_harvest_movement():
    world = World(WorldConfig(width=8, height=8, memory_cap=500, seed=23))
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    seed=23, founders=2)
    sender, receiver = colony.organisms
    sender.x, sender.y = 1, 1
    receiver.x, receiver.y = 4, 1
    sender.a, sender.genome = 73, [Op.SIGNAL]
    sender.execute(colony)
    assert world.signal_strength[1][1] == 24
    assert world.signal_strength[1][4] == 9

    receiver.genome = [Op.LISTEN]
    receiver.execute(colony)
    assert receiver.a == 73
    assert receiver.signals_heard == 1
    receiver.genome = [Op.MOVE]
    receiver.execute(colony)
    receiver.genome = [Op.HARVEST]
    receiver.execute(colony)
    assert receiver.signal_guided_moves == 1
    assert receiver.post_signal_harvested > 0


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
    assert detail["scratch"] == [0] * 8
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


def test_experimental_arithmetic_and_scratch_memory():
    colony = Colony(World(WorldConfig(width=4, height=4, memory_cap=100, seed=12)),
                    RandomMutator(point_rate=0, indel_rate=0), seed=12, founders=1)
    organism = colony.organisms[0]
    organism.a, organism.b = 250, 10
    organism.genome = [Op.ADD]
    organism.execute(colony)
    assert organism.a == 4
    organism.genome = [Op.SUB]
    organism.execute(colony)
    assert organism.a == 250
    organism.genome = [Op.XOR]
    organism.execute(colony)
    assert organism.a == (250 ^ 10)

    organism.a, organism.b = 73, 3
    organism.genome = [Op.STORE]
    organism.execute(colony)
    organism.a = 0
    organism.genome = [Op.LOAD]
    organism.execute(colony)
    assert organism.a == 73


def test_experimental_relative_jump_uses_register_c():
    colony = Colony(World(WorldConfig(width=4, height=4, memory_cap=100, seed=13)),
                    RandomMutator(point_rate=0, indel_rate=0), seed=13, founders=1)
    organism = colony.organisms[0]
    organism.genome = [Op.JMPR, Op.NOP, Op.NOP, Op.NOP]
    organism.ip, organism.c = 0, 9
    organism.execute(colony)
    assert organism.ip == 2


def test_temporal_forecast_requires_delayed_scratch_recall():
    world = World(WorldConfig(width=4, height=4, memory_cap=100, seed=15))
    tasks = TemporalTaskEnvironment(forecast_delay=8, forecast_window=8,
                                    forecast_reward=18.0)
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    tasks=tasks, seed=15, founders=1)
    organism = colony.organisms[0]

    organism.genome = [Op.INPUT]
    organism.execute(colony)
    organism.genome = [Op.SWAP]
    organism.execute(colony)
    organism.genome = [Op.INPUT]
    organism.execute(colony)
    organism.genome = [Op.ADD]
    organism.execute(colony)
    target = organism.a
    organism.genome = [Op.STORE]
    organism.execute(colony)

    # A correct answer is deliberately worthless before the environmental delay.
    organism.genome = [Op.OUTPUT]
    before = organism.energy
    organism.execute(colony)
    assert organism.forecasts_solved == 0
    assert organism.energy < before

    world.tick = organism.forecast_due_tick
    organism.genome = [Op.LOAD]
    organism.execute(colony)
    assert organism.a == target
    organism.genome = [Op.OUTPUT]
    before = organism.energy
    organism.execute(colony)
    assert organism.energy > before
    assert organism.forecasts_solved == 1
    assert colony.forecasts_solved == 1
    assert organism.tasks_solved["forecast"] == 1
    assert colony.experimental_ops["add"] == 1
    assert colony.experimental_ops["store"] == 1
    assert colony.experimental_ops["load"] == 1


def test_temporal_forecast_is_reachable_by_a_looping_replicator():
    world = World(WorldConfig(width=8, height=8, tile_regen=0.5,
                              memory_cap=500, seed=16))
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    tasks=TemporalTaskEnvironment(), seed=16, founders=1)
    organism = colony.organisms[0]
    organism.energy = 200
    organism.genome = [
        Op.HARVEST, Op.INPUT, Op.SWAP, Op.INPUT, Op.ADD, Op.STORE,
        Op.LOAD, Op.OUTPUT, Op.ALLOC, Op.COPY, Op.IFNOTDONE, Op.JMPB, Op.FORK,
    ]
    world.memory_used = len(organism.genome)
    for _ in range(100):
        colony.step()
    assert colony.forecasts_solved > 0
    assert colony.births > 0


def test_experimental_mutator_can_insert_short_instruction_bursts():
    class AlwaysBurst(random.Random):
        def random(self):
            return 0.0

    genome = [Op.HARVEST, Op.ALLOC, Op.COPY, Op.FORK]
    mutator = ExperimentalMutator(point_rate=0, indel_rate=0,
                                  burst_rate=1, burst_min=3, burst_max=3,
                                  duplication_rate=0, block_deletion_rate=0,
                                  inversion_rate=0)
    result = mutator.mutate_at_birth(list(genome), AlwaysBurst(17))
    assert len(result) == len(genome) + 3
    assert all(0 <= word < len(ISA) for word in result)


def test_gene_scale_mutations_are_bounded_and_labeled():
    genome = [Op.HARVEST, Op.ALLOC, Op.COPY, Op.IFNOTDONE, Op.JMPB, Op.FORK]
    duplicator = ExperimentalMutator(
        point_rate=0, indel_rate=0, burst_rate=0, duplication_rate=1,
        block_deletion_rate=0, inversion_rate=0, max_genome=12)
    duplicated = duplicator.mutate_at_birth(list(genome), random.Random(31))
    assert len(genome) + 2 <= len(duplicated) <= 12
    assert duplicator.last_events == ["segment_duplication"]

    deleter = ExperimentalMutator(
        point_rate=0, indel_rate=0, burst_rate=0, duplication_rate=0,
        block_deletion_rate=1, inversion_rate=0)
    deleted = deleter.mutate_at_birth(list(genome), random.Random(32))
    assert 4 <= len(deleted) <= len(genome) - 2
    assert deleter.last_events == ["block_deletion"]

    inverter = ExperimentalMutator(
        point_rate=0, indel_rate=0, burst_rate=0, duplication_rate=0,
        block_deletion_rate=0, inversion_rate=1)
    inverted = inverter.mutate_at_birth(list(genome), random.Random(33))
    assert len(inverted) == len(genome)
    assert sorted(inverted) == sorted(genome)
    assert inverter.last_events == ["segment_inversion"]


def test_history_links_mutation_mechanisms_to_later_reproduction(tmp_path):
    history = LineageHistory(tmp_path / "mechanisms.sqlite3")
    history.start_epoch(1, 1, 100.0)
    parent = SimpleNamespace(genome=[Op.HARVEST], generation=0)
    mutant = SimpleNamespace(genome=[Op.HARVEST, Op.HARVEST], generation=1)
    history.record(1, [{"kind": "birth", "tick": 10, "organism": mutant,
                        "parent": parent,
                        "mutations": ["segment_duplication"]}])
    child = SimpleNamespace(genome=list(mutant.genome), generation=2)
    history.record(1, [{"kind": "birth", "tick": 20, "organism": child,
                        "parent": mutant, "mutations": []}])
    mechanism = history.summary(1)["mutationMechanisms"][0]
    assert mechanism["mutation_type"] == "segment_duplication"
    assert mechanism["origin_births"] == 1
    assert mechanism["later_reproductions"] == 1
    assert mechanism["max_generation_span"] == 1
    history.close()


def test_operator_can_retire_living_epoch_without_calling_it_extinct(tmp_path):
    habitat = Habitat(tmp_path / "retire.pkl", seed=21, founders=2, physical=False)
    old_tick = habitat.colony.world.tick
    habitat.retire_current_epoch("playground reset")
    assert habitat.epoch == 2
    assert habitat.seed == 22
    assert habitat.colony.world.tick == 0
    assert len(habitat.colony.organisms) == 2
    epochs = habitat.history.summary(2)["epochs"]
    retired = next(row for row in epochs if row["epoch"] == 1)
    assert retired["ended_tick"] == old_tick
    assert retired["extinct"] == 0
    assert retired["end_reason"] == "playground reset"
    assert habitat.events[-1]["text"] == "epoch intentionally retired; epoch 2 seeded"
    habitat.history.close()


def test_resource_storm_drains_one_quadrant_and_blooms_the_opposite():
    config = WorldConfig(width=4, height=4, tile_capacity=100,
                         storm_interval=10, drought_fraction=0.1,
                         bloom_fraction=0.8, seed=22)
    world = World(config)
    world.energy = [[50.0] * 4 for _ in range(4)]
    world.structures = [[4] * 4 for _ in range(4)]
    world.tick = 10
    assert world.apply_resource_storm()
    assert world.storm_count == 1
    assert world.last_drought_quadrant == 1
    assert world.last_bloom_quadrant == 3
    assert world.energy[0][2] == 5.0
    assert world.structures[0][2] == 2
    assert world.energy[2][2] == 80.0
    assert world.energy[0][0] == 50.0


def test_storm_warning_replaces_inputs_only_during_warning_window():
    tasks = TemporalTaskEnvironment(storm_interval=1000, storm_warning=100)
    assert tasks.inputs(899, 7) != (1, 3)
    assert tasks.inputs(900, 7) == (1, 3)
    assert tasks.inputs(999, 7) == (1, 3)
    assert tasks.inputs(1000, 7) != (2, 0)
