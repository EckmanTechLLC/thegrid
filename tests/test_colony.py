from src.colony.colony import Colony
from src.colony.isa import ISA, Op, build_ancestor, build_founder_palette, isa_version
from src.colony.record import encode_genome, encode_positions
from src.colony.mutation import ExperimentalMutator, RandomMutator, parse_genome
from src.colony.world import World, WorldConfig
from src.colony.live import Habitat
from src.colony.odin_operator import OdinMutator
from src.colony.organism import Organism
from src.colony.history import LineageHistory, genome_id
from src.colony.tasks import TemporalTaskEnvironment
import asyncio
import hashlib
import json
import random
import sqlite3
import pytest

from collections import Counter
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
    assert len(palette) == len({tuple(genome) for genome in palette})
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
                    founders=len(palette), founder_genomes=palette)
    colony.organisms[0].x, colony.organisms[0].y = 47, 47
    encoded = encode_positions(colony, 48)
    assert len(encoded) == 4 * len(colony.organisms)
    assert encoded[:3] == "27v"  # base-32 encoding of tile 2303


def test_diverse_epoch_seeds_every_lineage_on_a_rich_distinct_patch():
    world = World(WorldConfig(width=48, height=48, seed=42))
    palette = build_founder_palette()
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    seed=42, founders=len(palette),
                    founder_genomes=palette)
    positions = {(o.x, o.y) for o in colony.organisms}
    assert len(positions) == len(palette)
    assert all(world.tile_energy(o.x, o.y) == world.config.tile_capacity
               for o in colony.organisms)
    assert all(o.energy == 48.0 for o in colony.organisms)


def test_epoch_can_inoculate_four_organisms_per_lineage():
    palette = build_founder_palette()
    expected = len(palette) * 4
    colony = Colony(World(WorldConfig(width=48, height=48, seed=42)),
                    seed=42, founders=len(palette),
                    founder_genomes=palette, founder_copies=4)
    counts = Counter(o.lineage for o in colony.organisms)
    assert len(colony.organisms) == expected
    assert counts == Counter({lineage: 4 for lineage in range(len(palette))})
    assert len({(o.x, o.y) for o in colony.organisms}) == expected


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
    assert len(restored.snapshot()["biomeField"]) == 48 * 48
    assert len(restored.snapshot()["biomePopulations"]) == 4


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


def test_odin_birth_that_consumed_a_proposal_is_its_own_mechanism(tmp_path):
    mutator = OdinMutator(tmp_path, rate=1.0, energy_cost=1.0)
    mutator.base.point_rate = 0
    mutator.base.indel_rate = 0
    mutator.base.burst_rate = 1.0          # every blind birth leaves an event
    parent = Organism(1, build_ancestor(), 0, 0, 0, energy=100)
    mutator.offer(parent)
    mutator.mutate_at_birth(list(parent.genome), random.Random(1))
    assert mutator.last_events == ["random_burst"]

    names = ["harvest", "alloc", "copy", "ifnotdone", "jmpb", "fork"]
    (tmp_path / "proposal.json").write_text(json.dumps({"genome": names}))
    mutator.offer(parent)
    mutator.mutate_at_birth(list(parent.genome), random.Random(1))
    # The base never ran for this birth; its stale burst must not be blamed
    # on the model's genome.
    assert mutator.last_events == ["model_proposal"]

    mutator.offer(parent)
    mutator.mutate_at_birth(list(parent.genome), random.Random(2))
    assert mutator.last_events == ["random_burst"]


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

    # Task pools start empty and refill once per tick. These tests drive
    # execute() directly rather than stepping, so without this the solve is
    # priced at min(want, empty pool) and correctly pays nothing.
    colony.tasks.decay_rates()
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

    # Task pools start empty and refill once per tick. These tests drive
    # execute() directly rather than stepping, so without this the solve is
    # priced at min(want, empty pool) and correctly pays nothing.
    colony.tasks.decay_rates()
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


def test_history_exports_genomes_at_stable_ids_without_ranking_them(tmp_path):
    history = LineageHistory(tmp_path / "export.sqlite3",
                             features={"predation", "lease"}, mutator="odin")
    ancestor = SimpleNamespace(genome=[Op.HARVEST], generation=0)
    mutant = SimpleNamespace(genome=[Op.HARVEST, Op.MOVE], generation=7)
    history.start_epoch(4, 1, 100.0, organisms=[ancestor])
    history.record(4, [{"kind": "birth", "tick": 10, "organism": mutant,
                        "parent": ancestor,
                        "mutations": ["point_substitution", "model_proposal"]}])
    # A later birth re-deriving the same sequence by another route does not
    # rewrite what the first one was made by.
    history.record(4, [{"kind": "birth", "tick": 30, "organism": mutant,
                        "parent": ancestor, "mutations": ["segment_transfer"]}])
    identity = genome_id(mutant.genome)
    record = history.genome_record(identity)
    assert record == {
        "genome_id": identity,
        "encoded": encode_genome(mutant.genome),
        "instructions": ["harvest", "move"],
        "first_epoch": 4, "first_tick": 10, "first_generation": 7,
        "parent_genome_id": genome_id(ancestor.genome),
        "mechanisms": ["model_proposal", "point_substitution"],
        "model_proposed": True,
        "isa_version": isa_version(),
        "features": ["lease", "predation"],
        "mutator": "odin",
    }
    assert hashlib.sha256(bytes(mutant.genome)).hexdigest()[:16] == identity
    assert not any(key in record for key in ("births", "tier", "age_ticks"))
    assert history.genome_record("0000000000000000") is None

    first, cursor = history.genome_records(limit=1)
    assert [r["genome_id"] for r in first] == [genome_id(ancestor.genome)]
    assert first[0]["model_proposed"] is False
    assert first[0]["parent_genome_id"] is None
    rest, done = history.genome_records(after=cursor, limit=1)
    assert [r["genome_id"] for r in rest] == [identity]
    assert history.genome_records(after=done)[0] == []
    assert history.genome_records(since_epoch=5)[0] == []
    with pytest.raises(ValueError):
        history.genome_records(after="not-a-cursor")
    history.close()

    # A record written before the provenance columns existed answers "not
    # recorded", never today's flags.
    old = sqlite3.connect(tmp_path / "export.sqlite3")
    old.execute("UPDATE genomes SET isa_version=NULL, features=NULL, mutator=NULL")
    old.commit()
    old.close()
    reopened = LineageHistory(tmp_path / "export.sqlite3", mutator="random")
    aged = reopened.genome_record(identity)
    assert (aged["isa_version"], aged["features"], aged["mutator"]) == (None, None, None)
    assert aged["model_proposed"] is None
    reopened.close()


def test_genome_export_routes_serve_the_record_and_its_table(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    from src.colony.live import create_app

    habitat = Habitat(tmp_path / "export.pkl", seed=3, founders=2, physical=False,
                      mutator_kind="random", name="Colony Test",
                      deployment="test-bench")
    for _ in range(40):
        habitat.step()
    assert habitat.latest["deployment"] == "test-bench"

    async def exercise() -> None:
        app = await create_app(habitat, ticks_per_second=10)
        async with TestClient(TestServer(app)) as client:
            page = await (await client.get("/api/genomes")).json()
            assert page["colony"] == "Colony Test"
            assert page["deployment"] == "test-bench"
            assert page["live"] == {"isaVersion": isa_version(), "features": [],
                                    "mutator": "random"}
            assert page["genomes"] and page["next"] is None
            first = page["genomes"][0]
            assert first["first_epoch"] == 1 and first["mutator"] == "random"

            table = await (await client.get("/api/genomes/isa")).json()
            body = json.dumps([[o["name"], o["cost"]] for o in table["opcodes"]],
                              separators=(",", ":"))
            recomputed = hashlib.sha256(
                f"{table['encoding']}|{body}".encode()).hexdigest()[:12]
            assert table["isaVersion"] == recomputed == first["isa_version"]
            names = [o["name"] for o in table["opcodes"]]
            ops = [names.index(n) for n in first["instructions"]]
            assert hashlib.sha256(bytes(ops)).hexdigest()[:16] == first["genome_id"]

            one = await client.get(f"/api/genomes/{first['genome_id']}")
            assert one.status == 200
            assert (await one.json())["genome"] == first
            assert (await client.get("/api/genomes/0000000000000000")).status == 404
            assert (await client.get("/api/genomes?since_epoch=x")).status == 400
            assert (await client.get("/api/genomes?after=bad")).status == 400

    asyncio.run(exercise())


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


def test_storm_warning_is_local_and_directional():
    tasks = TemporalTaskEnvironment(storm_interval=1000, storm_warning=100)
    world = World(WorldConfig(width=48, height=48, storm_interval=1000,
                              storm_warning=100, storm_scout_depth=4))
    world.tick = 899
    assert world.weather_cue(24, 24) is None
    world.tick = 900  # next bloom is SE; only its inward boundary can sense it
    assert world.weather_cue(24, 24) in (1, 2)
    assert world.weather_cue(40, 40) is None
    assert world.weather_cue(23, 24) is None
    cue = world.weather_cue(24, 24)
    assert tasks.inputs(900, 7, weather_cue=cue) == (cue, cue)
    assert tasks.inputs(900, 7) != (cue, cue)
    world.tick = 1000
    assert world.weather_cue(24, 24) is None


def test_local_weather_cue_can_flow_through_signal_listen_move():
    world = World(WorldConfig(width=48, height=48, storm_interval=1000,
                              storm_warning=100, storm_scout_depth=4))
    tasks = TemporalTaskEnvironment(storm_interval=1000, storm_warning=100)
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    tasks=tasks, seed=41, founders=2)
    scout, listener = colony.organisms
    world.tick = 900
    scout.x, scout.y = 24, 24
    listener.x, listener.y = 27, 24
    scout.genome = [Op.INPUT, Op.SIGNAL]
    listener.genome = [Op.LISTEN, Op.MOVE, Op.HARVEST]

    scout.execute(colony)
    cue = scout.a
    before_signal = scout.energy
    scout.execute(colony)
    assert scout.weather_cues_seen == 1
    assert scout.weather_cue_signals == 1
    assert scout.energy < before_signal  # signaling itself has no reward

    listener.execute(colony)
    assert listener.a == cue
    listener.execute(colony)
    assert listener.signal_guided_moves == 1
    listener.execute(colony)
    assert listener.post_signal_harvested > 0


def test_biomes_create_real_instruction_and_resource_tradeoffs():
    world = World(WorldConfig(width=8, height=8, seed=30))
    # NW forage, NE nomad, SW engineer, SE information.
    assert world.instruction_cost_multiplier(Op.HARVEST, 1, 1) < 1
    assert world.instruction_cost_multiplier(Op.BUILD, 1, 1) > 1
    assert world.instruction_cost_multiplier(Op.MOVE, 6, 1) < 1
    assert world.build_cost(1, 6) < world.build_cost(1, 1)
    assert world.instruction_cost_multiplier(Op.SIGNAL, 6, 6) < 1
    assert world.task_reward_multiplier(6, 6) > 1
    world.energy[1][1] = world.energy[1][6] = 90
    assert world.harvest(1, 1) > world.harvest(6, 1)


def test_biome_boundaries_have_narrow_migration_corridors():
    world = World(WorldConfig(width=8, height=8, seed=31))
    assert world.move(3, 0, 1, 0) == (3, 0)  # blocked boundary
    assert world.move(3, 2, 1, 0) == (4, 2)  # quarter-map gate
    assert world.move(1, 1, 1, 0) == (2, 1)  # free within a biome


def test_death_funds_the_reclaim_pool_and_salvage_only_ever_drains_it():
    world = World(WorldConfig(width=8, height=8, memory_cap=100, seed=32))
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    seed=32, founders=1)
    organism = colony.organisms[0]
    x, y = organism.x, organism.y
    # nop costs nothing, so a nop-only genome cannot starve however small its
    # energy is - that is exactly why the lease exists. Empty the tank instead.
    organism.genome = [Op.NOP] * 20
    organism.energy = 0.0
    colony.step()

    deposited = world.reclaim_pool
    assert deposited > 0
    assert colony.scrap_deposited > 0

    # Salvage is a transfer. Whatever it hands out must leave the pool, in
    # every quadrant: a multiplier here once minted 25% on top and a colony
    # promptly evolved a no-harvest salvage loop to farm it.
    for corner in ((1, 1), (6, 1), (1, 6), (6, 6)):
        before = world.reclaim_pool
        gained = world.salvage(*corner)
        assert gained == pytest.approx(before - world.reclaim_pool)
        assert world.reclaim_pool >= 0

    # And an empty pool pays nothing rather than going negative.
    world.reclaim_pool = 0.0
    assert world.salvage(x, y) == 0.0
    assert world.reclaim_pool == 0.0


def test_salvage_instruction_is_a_costly_contextual_advantage():
    world = World(WorldConfig(width=8, height=8, memory_cap=100, seed=33))
    colony = Colony(world, RandomMutator(point_rate=0, indel_rate=0),
                    seed=33, founders=1, founder_genomes=[[Op.SALVAGE]])
    organism = colony.organisms[0]
    world.reclaim_pool = 5.0
    before = organism.energy
    colony.step()
    assert organism.salvaged > 0
    assert colony.salvaged == organism.salvaged
    assert organism.energy > before
