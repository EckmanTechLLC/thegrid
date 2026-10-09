"""Compact durable history of genome evolution in the persistent habitat."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from .isa import ISA, isa_version
from .record import encode_genome


def genome_id(genome: list[int]) -> str:
    return hashlib.sha256(bytes(genome)).hexdigest()[:16]


class LineageHistory:
    """Aggregate ancestry without retaining an unbounded row per organism."""

    ECOLOGY_BUCKET_TICKS = 500
    EXPORT_PAGE = 100
    EXPORT_PAGE_MAX = 500

    def __init__(self, path: Path, features=(), mutator: str | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # Stamped onto each genome at first sighting. Features and the mutator
        # are unit-file flags and the ISA is whatever tree is checked out, so
        # none of them is a property of the fossil record - and all three
        # changed this September. A row that says which table its glyphs mean
        # something against, and which opcodes could act when it was born, is
        # checkable later; a join against the running process is a guess.
        self.provenance = (isa_version(), ",".join(sorted(features)), mutator)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS genomes (
                genome_id TEXT PRIMARY KEY,
                encoded TEXT NOT NULL,
                source TEXT NOT NULL,
                first_epoch INTEGER NOT NULL,
                first_tick INTEGER NOT NULL,
                parent_genome_id TEXT
            );
            CREATE TABLE IF NOT EXISTS genome_stats (
                epoch INTEGER NOT NULL,
                genome_id TEXT NOT NULL,
                births INTEGER NOT NULL DEFAULT 0,
                starvation_deaths INTEGER NOT NULL DEFAULT 0,
                senescence_deaths INTEGER NOT NULL DEFAULT 0,
                first_generation INTEGER,
                max_generation INTEGER NOT NULL DEFAULT 0,
                first_tick INTEGER NOT NULL,
                last_tick INTEGER NOT NULL,
                PRIMARY KEY (epoch, genome_id)
            );
            CREATE TABLE IF NOT EXISTS transitions (
                epoch INTEGER NOT NULL,
                parent_genome_id TEXT NOT NULL,
                child_genome_id TEXT NOT NULL,
                births INTEGER NOT NULL DEFAULT 0,
                first_tick INTEGER NOT NULL,
                last_tick INTEGER NOT NULL,
                PRIMARY KEY (epoch, parent_genome_id, child_genome_id)
            );
            CREATE TABLE IF NOT EXISTS mutation_origins (
                epoch INTEGER NOT NULL,
                child_genome_id TEXT NOT NULL,
                mutation_type TEXT NOT NULL,
                origin_births INTEGER NOT NULL DEFAULT 0,
                occurrences INTEGER NOT NULL DEFAULT 0,
                births_at_first_origin INTEGER NOT NULL DEFAULT 0,
                first_generation INTEGER NOT NULL DEFAULT 0,
                first_tick INTEGER NOT NULL,
                last_tick INTEGER NOT NULL,
                PRIMARY KEY (epoch, child_genome_id, mutation_type)
            );
            CREATE TABLE IF NOT EXISTS epochs (
                epoch INTEGER PRIMARY KEY,
                seed INTEGER NOT NULL,
                started_at REAL NOT NULL,
                ended_at REAL,
                ended_tick INTEGER,
                births INTEGER,
                deaths INTEGER,
                max_generation INTEGER,
                extinct INTEGER NOT NULL DEFAULT 0,
                partial INTEGER NOT NULL DEFAULT 0,
                end_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS ecology_buckets (
                epoch INTEGER NOT NULL,
                bucket INTEGER NOT NULL,
                start_tick INTEGER NOT NULL,
                end_tick INTEGER NOT NULL,
                samples INTEGER NOT NULL,
                population_sum INTEGER NOT NULL,
                population_min INTEGER NOT NULL,
                population_max INTEGER NOT NULL,
                diversity_sum INTEGER NOT NULL,
                dominance_sum REAL NOT NULL,
                genome_length_sum REAL NOT NULL,
                resource_sum REAL NOT NULL,
                built_sum INTEGER NOT NULL,
                signals_sum INTEGER NOT NULL,
                PRIMARY KEY (epoch, bucket)
            );
            CREATE INDEX IF NOT EXISTS genomes_first_seen
                ON genomes(first_epoch DESC, first_tick DESC);
            CREATE INDEX IF NOT EXISTS transitions_recent
                ON transitions(epoch DESC, last_tick DESC);
        """)
        # The mechanics added in epochs 28-29 - the bus, the reclaim pool,
        # commons heat, and the machine's own thermal and CPU state - existed
        # only in the live snapshot, so nothing about them survived the tick
        # they happened in. Averages for instantaneous quantities, last-value
        # for cumulative counters, so deltas can be taken between buckets.
        ecology_columns = {row[1] for row in
                           self._db.execute("PRAGMA table_info(ecology_buckets)")}
        for _name in ('cost_sum',
                      'thermal_excess_sum',
                      'machine_spare_sum',
                      'regen_sum',
                      'reclaim_pool_sum',
                      'slots_held_sum',
                      'bus_writes_end',
                      'bus_reads_end',
                      'published_end',
                      'calls_end',
                      'publish_refused_end',
                      'salvaged_end',
                      # Founder lineages alive, and the share held by the
                      # largest. Nothing recorded this, so whether founder
                      # diversity survives could only be guessed at from a
                      # single live reading - which is exactly how I got it
                      # wrong. lineages counts distinct founder indices among
                      # the living; lineage_top is the largest one's fraction.
                      'lineages_sum',
                      'lineage_top_sum',
                      # The two mechanisms added in September had no fossil
                      # record at all. bit rot and eviction were both visible
                      # only in /api/state, which is ephemeral and resets on
                      # reseed - a full day of running would have produced
                      # nothing analysable for either of them.
                      'bit_flips_end',
                      'evicted_end',
                      'useful_sum',
                      'royalties_end',
                      'tasks_solved_end'):
            if _name not in ecology_columns:
                self._db.execute(
                    f"ALTER TABLE ecology_buckets ADD COLUMN {_name} REAL NOT NULL DEFAULT 0")

        genome_columns = {row[1] for row in self._db.execute("PRAGMA table_info(genomes)")}
        for _name in ("isa_version", "features", "mutator"):
            if _name not in genome_columns:
                self._db.execute(f"ALTER TABLE genomes ADD COLUMN {_name} TEXT")
        # Rows from before these columns existed stay NULL: "not recorded" is
        # an answer, backfilling from today's flags would be a claim.
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS genomes_export
                ON genomes(first_epoch, first_tick, genome_id)
        """)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(genome_stats)")}
        if "first_generation" not in columns:
            self._db.execute("ALTER TABLE genome_stats ADD COLUMN first_generation INTEGER")
            # Existing rows become conservative lower bounds measured from deployment.
            self._db.execute("UPDATE genome_stats SET first_generation=max_generation")
        epoch_columns = {row[1] for row in self._db.execute("PRAGMA table_info(epochs)")}
        if "end_reason" not in epoch_columns:
            self._db.execute("ALTER TABLE epochs ADD COLUMN end_reason TEXT")
        origin_columns = {row[1] for row in self._db.execute("PRAGMA table_info(mutation_origins)")}
        if "births_at_first_origin" not in origin_columns:
            self._db.execute(
                "ALTER TABLE mutation_origins ADD COLUMN births_at_first_origin INTEGER NOT NULL DEFAULT 0")
        if "first_generation" not in origin_columns:
            self._db.execute(
                "ALTER TABLE mutation_origins ADD COLUMN first_generation INTEGER NOT NULL DEFAULT 0")
        # Rows created before these baselines existed start measuring now rather
        # than receiving credit for reproduction predating the mutation origin.
        self._db.execute("""
            UPDATE mutation_origins
            SET births_at_first_origin=(
                    SELECT births FROM genome_stats s
                    WHERE s.epoch=mutation_origins.epoch
                      AND s.genome_id=mutation_origins.child_genome_id),
                first_generation=(
                    SELECT max_generation FROM genome_stats s
                    WHERE s.epoch=mutation_origins.epoch
                      AND s.genome_id=mutation_origins.child_genome_id)
            WHERE births_at_first_origin=0
        """)
        self._db.commit()
        self._last_commit = time.monotonic()
        self._last_ecology_tick: dict[int, int] = {}

    def start_epoch(self, epoch: int, seed: int, started_at: float,
                    organisms=(), partial: bool = False, observed_tick: int = 0) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO epochs(epoch,seed,started_at,partial) VALUES(?,?,?,?)",
                (epoch, seed, started_at, int(partial)),
            )
            for organism in organisms:
                self._observe_genome(epoch, observed_tick, organism.genome, None,
                                     organism.generation)
            self._db.commit()

    def record(self, epoch: int, events) -> None:
        with self._lock:
            for event in events:
                organism = event["organism"]
                tick = int(event["tick"])
                child_id = self._observe_genome(
                    epoch, tick, organism.genome,
                    event.get("parent").genome if event.get("parent") else None,
                    organism.generation,
                )
                if event["kind"] == "birth":
                    self._db.execute("""
                        UPDATE genome_stats SET births=births+1,
                            max_generation=max(max_generation,?), last_tick=?
                        WHERE epoch=? AND genome_id=?
                    """, (organism.generation, tick, epoch, child_id))
                    parent = event.get("parent")
                    if parent is not None:
                        parent_id = genome_id(parent.genome)
                        self._db.execute("""
                            INSERT INTO transitions(epoch,parent_genome_id,child_genome_id,
                                                    births,first_tick,last_tick)
                            VALUES(?,?,?,?,?,?)
                            ON CONFLICT(epoch,parent_genome_id,child_genome_id) DO UPDATE SET
                                births=births+1,last_tick=excluded.last_tick
                        """, (epoch, parent_id, child_id, 1, tick, tick))
                    mutation_counts: dict[str, int] = {}
                    for mutation_type in event.get("mutations", []):
                        mutation_counts[mutation_type] = mutation_counts.get(mutation_type, 0) + 1
                    for mutation_type, occurrences in mutation_counts.items():
                        births_now = self._db.execute(
                            "SELECT births FROM genome_stats WHERE epoch=? AND genome_id=?",
                            (epoch, child_id),
                        ).fetchone()[0]
                        self._db.execute("""
                            INSERT INTO mutation_origins(
                                epoch,child_genome_id,mutation_type,origin_births,
                                occurrences,births_at_first_origin,first_generation,
                                first_tick,last_tick)
                            VALUES(?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(epoch,child_genome_id,mutation_type) DO UPDATE SET
                                origin_births=origin_births+1,
                                occurrences=occurrences+excluded.occurrences,
                                last_tick=excluded.last_tick
                        """, (epoch, child_id, mutation_type, 1, occurrences,
                              births_now, organism.generation, tick, tick))
                else:
                    column = "starvation_deaths" if event["cause"] == "starvation" else "senescence_deaths"
                    self._db.execute(
                        f"UPDATE genome_stats SET {column}={column}+1,last_tick=? "
                        "WHERE epoch=? AND genome_id=?", (tick, epoch, child_id),
                    )
            if time.monotonic() - self._last_commit >= 1.0:
                self._db.commit()
                self._last_commit = time.monotonic()

    def _observe_genome(self, epoch: int, tick: int, genome: list[int],
                        parent_genome: list[int] | None, generation: int) -> str:
        identity = genome_id(genome)
        parent_id = genome_id(parent_genome) if parent_genome is not None else None
        source = " · ".join(ISA[word].name if 0 <= word < len(ISA) else f"?{word}"
                            for word in genome)
        self._db.execute("""
            INSERT OR IGNORE INTO genomes(genome_id,encoded,source,first_epoch,first_tick,
                                          parent_genome_id,isa_version,features,mutator)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (identity, encode_genome(genome), source, epoch, tick, parent_id,
              *self.provenance))
        self._db.execute("""
            INSERT INTO genome_stats(epoch,genome_id,first_generation,max_generation,first_tick,last_tick)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(epoch,genome_id) DO UPDATE SET
                first_generation=min(first_generation,excluded.first_generation),
                max_generation=max(max_generation,excluded.max_generation),
                last_tick=max(last_tick,excluded.last_tick)
        """, (epoch, identity, generation, generation, tick, tick))
        return identity

    def finish_epoch(self, epoch: int, colony, extinct: bool = True,
                     reason: str | None = None) -> None:
        with self._lock:
            maximum = self._db.execute(
                "SELECT coalesce(max(max_generation),0) FROM genome_stats WHERE epoch=?",
                (epoch,),
            ).fetchone()[0]
            self._db.execute("""
                UPDATE epochs SET ended_at=?,ended_tick=?,births=?,deaths=?,
                    max_generation=?,extinct=?,end_reason=? WHERE epoch=?
            """, (time.time(), colony.world.tick, colony.births, colony.deaths,
                  maximum, int(extinct), reason or ("extinction" if extinct else None), epoch))
            self._db.commit()

    def record_ecology(self, epoch: int, tick: int, *, population: int,
                       diversity: int, dominance: float, genome_length: float,
                       resources: float, built: int, signals: int,
                       cost: float = 1.0, thermal_excess: float = 0.0,
                       machine_spare: float = 1.0, regen: float = 1.0,
                       reclaim_pool: float = 0.0, slots_held: int = 0,
                       bus_writes: int = 0, bus_reads: int = 0,
                       published: int = 0, calls: int = 0,
                       publish_refused: int = 0, salvaged: float = 0.0,
                       lineages: int = 0, lineage_top: float = 0.0,
                       bit_flips: int = 0, evicted: int = 0, useful: int = 0,
                       royalties: float = 0.0, tasks_solved: int = 0) -> None:
        """Store bounded per-500-tick ecology aggregates, never per-frame rows."""
        with self._lock:
            if epoch not in self._last_ecology_tick:
                row = self._db.execute(
                    "SELECT coalesce(max(end_tick),-1) FROM ecology_buckets WHERE epoch=?",
                    (epoch,),
                ).fetchone()
                self._last_ecology_tick[epoch] = int(row[0])
            if tick <= self._last_ecology_tick[epoch]:
                return
            bucket = tick // self.ECOLOGY_BUCKET_TICKS
            self._db.execute("""
                INSERT INTO ecology_buckets(
                    epoch,bucket,start_tick,end_tick,samples,population_sum,
                    population_min,population_max,diversity_sum,dominance_sum,
                    genome_length_sum,resource_sum,built_sum,signals_sum,
                    cost_sum,thermal_excess_sum,machine_spare_sum,regen_sum,reclaim_pool_sum,slots_held_sum,bus_writes_end,bus_reads_end,published_end,calls_end,publish_refused_end,salvaged_end,
                    lineages_sum,lineage_top_sum,
                    bit_flips_end,evicted_end,useful_sum,royalties_end,tasks_solved_end)
                VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(epoch,bucket) DO UPDATE SET
                    end_tick=excluded.end_tick,
                    samples=samples+1,
                    population_sum=population_sum+excluded.population_sum,
                    population_min=min(population_min,excluded.population_min),
                    population_max=max(population_max,excluded.population_max),
                    diversity_sum=diversity_sum+excluded.diversity_sum,
                    dominance_sum=dominance_sum+excluded.dominance_sum,
                    genome_length_sum=genome_length_sum+excluded.genome_length_sum,
                    resource_sum=resource_sum+excluded.resource_sum,
                    built_sum=built_sum+excluded.built_sum,
                    signals_sum=signals_sum+excluded.signals_sum,
                    cost_sum=cost_sum+excluded.cost_sum,
                    thermal_excess_sum=thermal_excess_sum+excluded.thermal_excess_sum,
                    machine_spare_sum=machine_spare_sum+excluded.machine_spare_sum,
                    regen_sum=regen_sum+excluded.regen_sum,
                    reclaim_pool_sum=reclaim_pool_sum+excluded.reclaim_pool_sum,
                    slots_held_sum=slots_held_sum+excluded.slots_held_sum,
                    bus_writes_end=excluded.bus_writes_end,
                    bus_reads_end=excluded.bus_reads_end,
                    published_end=excluded.published_end,
                    calls_end=excluded.calls_end,
                    publish_refused_end=excluded.publish_refused_end,
                    salvaged_end=excluded.salvaged_end,
                    lineages_sum=lineages_sum+excluded.lineages_sum,
                    lineage_top_sum=lineage_top_sum+excluded.lineage_top_sum,
                    bit_flips_end=excluded.bit_flips_end,
                    evicted_end=excluded.evicted_end,
                    useful_sum=useful_sum+excluded.useful_sum,
                    royalties_end=excluded.royalties_end,
                    tasks_solved_end=excluded.tasks_solved_end
            """, (epoch, bucket, tick, tick, population, population, population,
                  diversity, dominance, genome_length, resources, built, signals,
                  cost, thermal_excess, machine_spare, regen, reclaim_pool,
                  slots_held, bus_writes, bus_reads, published, calls,
                  publish_refused, salvaged, lineages, lineage_top,
                  bit_flips, evicted, useful, royalties, tasks_solved))
            self._last_ecology_tick[epoch] = tick

    def flush(self) -> None:
        with self._lock:
            self._db.commit()
            self._last_commit = time.monotonic()

    def summary(self, current_epoch: int, limit: int = 12) -> dict:
        with self._lock:
            self._db.commit()
            totals = self._db.execute("""
                SELECT (SELECT count(*) FROM genomes) AS genomes,
                       (SELECT coalesce(sum(births),0) FROM genome_stats) AS births,
                       (SELECT count(*) FROM epochs) AS epochs
            """).fetchone()
            genomes = self._db.execute("""
                SELECT g.genome_id,g.source,g.first_epoch,g.first_tick,g.parent_genome_id,
                       coalesce(sum(s.births),0) AS births,
                       coalesce(max(s.max_generation),0) AS max_generation
                FROM genomes g LEFT JOIN genome_stats s USING(genome_id)
                GROUP BY g.genome_id
                ORDER BY g.first_epoch DESC,g.first_tick DESC LIMIT ?
            """, (limit,)).fetchall()
            transitions = self._db.execute("""
                SELECT t.epoch,t.last_tick,t.births,t.parent_genome_id,t.child_genome_id,
                       p.source AS parent_source,c.source AS child_source
                FROM transitions t JOIN genomes p ON p.genome_id=t.parent_genome_id
                JOIN genomes c ON c.genome_id=t.child_genome_id
                WHERE t.parent_genome_id != t.child_genome_id
                ORDER BY t.epoch DESC,t.last_tick DESC LIMIT ?
            """, (limit,)).fetchall()
            success_rows = self._db.execute("""
                SELECT g.genome_id,g.source,g.parent_genome_id,s.births,
                       s.first_tick,s.last_tick,s.first_generation,s.max_generation
                FROM genome_stats s JOIN genomes g USING(genome_id)
                WHERE s.epoch=? AND g.parent_genome_id IS NOT NULL
                ORDER BY (s.max_generation-s.first_generation) DESC,
                         s.births DESC,s.last_tick DESC LIMIT 100
            """, (current_epoch,)).fetchall()
            epochs = self._db.execute("""
                SELECT * FROM epochs ORDER BY epoch DESC LIMIT 8
            """).fetchall()
            ecology_rows = self._db.execute("""
                SELECT * FROM ecology_buckets WHERE epoch=?
                ORDER BY bucket DESC LIMIT 24
            """, (current_epoch,)).fetchall()
            mechanism_rows = self._db.execute("""
                SELECT o.mutation_type,
                       sum(o.origin_births) AS origin_births,
                       sum(o.occurrences) AS occurrences,
                       count(*) AS genomes,
                       max(s.max_generation-o.first_generation) AS max_generation_span,
                       sum(max(0,s.births-o.births_at_first_origin)) AS later_reproductions
                FROM mutation_origins o
                JOIN genome_stats s ON s.epoch=o.epoch AND s.genome_id=o.child_genome_id
                WHERE o.epoch=?
                GROUP BY o.mutation_type
                ORDER BY later_reproductions DESC,occurrences DESC
            """, (current_epoch,)).fetchall()
            communication_rows = self._db.execute("""
                SELECT g.genome_id,g.source,s.births,s.first_tick,s.last_tick,
                       s.max_generation-s.first_generation AS observed_generations,
                       CASE
                           WHEN g.source LIKE '%signal%' AND g.source LIKE '%listen%'
                               THEN 'signal+listen'
                           WHEN g.source LIKE '%listen%' THEN 'listen'
                           ELSE 'signal'
                       END AS role
                FROM genome_stats s JOIN genomes g USING(genome_id)
                WHERE s.epoch=? AND (g.source LIKE '%signal%' OR g.source LIKE '%listen%')
                ORDER BY observed_generations DESC,s.births DESC,s.last_tick DESC
                LIMIT ?
            """, (current_epoch, limit)).fetchall()
        successes = []
        for source_row in success_rows:
            row = dict(source_row)
            generations = row["max_generation"] - row["first_generation"]
            births = row["births"]
            if generations >= 100 and births >= 100:
                tier = "established"
            elif generations >= 50 and births >= 25:
                tier = "enduring"
            elif generations >= 10 and births >= 5:
                tier = "growing"
            elif births >= 2:
                tier = "reproduced"
            else:
                tier = "new"
            row.update({"observed_generations": generations,
                        "age_ticks": row["last_tick"] - row["first_tick"],
                        "tier": tier})
            successes.append(row)
        ecology = []
        for source_row in reversed(ecology_rows):
            row = dict(source_row)
            samples = row.pop("samples")
            row.update({
                "samples": samples,
                "population_avg": round(row.pop("population_sum") / samples, 2),
                "diversity_avg": round(row.pop("diversity_sum") / samples, 2),
                "dominance_avg": round(row.pop("dominance_sum") / samples, 4),
                "genome_length_avg": round(row.pop("genome_length_sum") / samples, 2),
                "resources_avg": round(row.pop("resource_sum") / samples, 2),
                "built_avg": round(row.pop("built_sum") / samples, 2),
                "signals_avg": round(row.pop("signals_sum") / samples, 2),
                "cost_avg": round(row.pop("cost_sum", 0.0) / samples, 4),
                "thermal_excess_avg": round(row.pop("thermal_excess_sum", 0.0) / samples, 4),
                "machine_spare_avg": round(row.pop("machine_spare_sum", 0.0) / samples, 4),
                "regen_avg": round(row.pop("regen_sum", 0.0) / samples, 4),
                "reclaim_pool_avg": round(row.pop("reclaim_pool_sum", 0.0) / samples, 4),
                "slots_held_avg": round(row.pop("slots_held_sum", 0.0) / samples, 4),
                "lineages_avg": round(row.pop("lineages_sum", 0.0) / samples, 2),
                "lineage_top_avg": round(row.pop("lineage_top_sum", 0.0) / samples, 4),
            })
            ecology.append(row)
        return {
            "currentEpoch": current_epoch,
            "totals": dict(totals),
            "genomes": [dict(row) for row in genomes],
            "transitions": [dict(row) for row in transitions],
            "mutationSuccess": successes[:limit],
            "ecology": ecology,
            "mutationMechanisms": [dict(row) for row in mechanism_rows],
            "communicationLineages": [dict(row) for row in communication_rows],
            "epochs": [dict(row) for row in epochs],
        }

    def genome_record(self, identity: str) -> dict | None:
        """One genome at its stable id, or None. Never ranks; see _export."""
        with self._lock:
            self._db.commit()
            row = self._db.execute(
                "SELECT * FROM genomes WHERE genome_id=?", (identity,)).fetchone()
            return self._export(row) if row is not None else None

    def genome_records(self, since_epoch: int = 0, after: str | None = None,
                       limit: int = EXPORT_PAGE) -> tuple[list[dict], str | None]:
        """A page of genomes in first-sighting order, oldest first.

        `after` is the cursor returned with the previous page - the last row's
        (first_epoch, first_tick, genome_id) - so a reader can walk the whole
        record forward without offsets drifting as new genomes are appended.
        """
        limit = max(1, min(self.EXPORT_PAGE_MAX, int(limit)))
        epoch, tick, identity = -1, -1, ""
        if after:
            parts = after.split(":")
            if len(parts) != 3:
                raise ValueError("cursor is epoch:tick:genome_id")
            epoch, tick, identity = int(parts[0]), int(parts[1]), parts[2]
        with self._lock:
            self._db.commit()
            rows = self._db.execute("""
                SELECT * FROM genomes
                WHERE first_epoch >= ?
                  AND (first_epoch, first_tick, genome_id) > (?, ?, ?)
                ORDER BY first_epoch, first_tick, genome_id LIMIT ?
            """, (int(since_epoch), epoch, tick, identity, limit)).fetchall()
            records = [self._export(row) for row in rows]
        cursor = None
        if len(records) == limit:
            last = records[-1]
            cursor = f"{last['first_epoch']}:{last['first_tick']}:{last['genome_id']}"
        return records, cursor

    def _export(self, row) -> dict:
        """The published shape of one genome. Facts only, no field a reader
        could mistake for a verdict: no births, no ages, no tiers. What
        selection did with a sequence is downstream's rule to apply, not ours
        to summarise - see EckmanTechLLC/thegrid#5."""
        record = dict(row)
        generation = self._db.execute(
            "SELECT first_generation FROM genome_stats WHERE epoch=? AND genome_id=?",
            (record["first_epoch"], record["genome_id"])).fetchone()
        # The mechanisms on the FIRST birth of this sequence here, not every
        # birth that later re-derived it by some other route.
        mechanisms = [r[0] for r in self._db.execute("""
            SELECT mutation_type FROM mutation_origins
            WHERE epoch=? AND child_genome_id=? AND first_tick=?
            ORDER BY mutation_type
        """, (record["first_epoch"], record["genome_id"], record["first_tick"]))]
        features = record.get("features")
        mutator = record.get("mutator")
        return {
            "genome_id": record["genome_id"],
            "encoded": record["encoded"],
            "instructions": record["source"].split(" · "),
            "first_epoch": record["first_epoch"],
            "first_tick": record["first_tick"],
            "first_generation": generation[0] if generation else None,
            "parent_genome_id": record["parent_genome_id"],
            "mechanisms": mechanisms,
            # Proposed by a model and kept by selection, or blind. Unknown for
            # rows older than the mutator column: the tag did not exist yet.
            "model_proposed": (None if mutator is None
                               else "model_proposal" in mechanisms),
            "isa_version": record.get("isa_version"),
            "features": (None if features is None
                         else [f for f in features.split(",") if f]),
            "mutator": mutator,
        }

    def close(self) -> None:
        with self._lock:
            self._db.commit()
            self._db.close()
