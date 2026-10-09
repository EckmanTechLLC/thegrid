"""Grid 2 — the real-work world. State, ledger, fossil record.

Organisms are real processes. The only income in the universe is verified
real work and voluntary trade. Nothing here defines fitness; the kernel
charges for CPU and memory, the broker pays for work that verifies, and
everything else is evolution's problem.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

STATE = Path("/state")
ORGS = STATE / "organisms"
JOBS = STATE / "jobs"
MORGUE = STATE / "morgue"

# -- economy constants (cycles; 1 cycle = 1 CPU millisecond) ----------------
ROUND_OVERHEAD = 5          # existing costs something, but not much
RSS_FREE_MB = 64            # memory under this is rent-free
RSS_CYCLES_PER_MB = 2       # above it, per round
GOOD_RENT_PER_10KB = 1      # published goods pay storage rent per round
ANCESTOR_GRANT = 20_000
MIN_SPAWN_GRANT = 2_000
BIRTH_TAX = 0.10            # burned on every spawn
STILLBORN_REFUND = 0.50
MAX_POP = 192
MAX_ACTIONS_PER_ROUND = 40
MAX_SOURCE_BYTES = 65_536
MAX_GOOD_BYTES = 262_144
CPU_LIMIT_S = 2             # hard rlimit per round
WALL_LIMIT_S = 3
AS_LIMIT_MB = 512
FSIZE_LIMIT_MB = 64


@dataclass
class Organism:
    oid: int
    parent: int
    gen: int
    born_round: int
    balance: int
    src_hash: str
    jobs_won: int = 0
    trades_sold: int = 0
    author: str = "genesis"   # which engine wrote this source: genesis/ast/hgt/llm/copy
    root: int = 0             # founding ancestor oid, for lineage identity
    last_income_round: int = 0
    goods: dict = field(default_factory=dict)   # name -> {path,price,size}

    @property
    def home(self) -> Path:
        return ORGS / str(self.oid)


class DB:
    def __init__(self, path: Path):
        self.con = sqlite3.connect(path)
        self.con.execute("pragma journal_mode=wal")
        self.con.executescript("""
        create table if not exists organisms(
            oid integer primary key, parent integer, gen integer,
            born_round integer, died_round integer, cause text,
            src_hash text, jobs_won integer default 0,
            trades_sold integer default 0, final_balance integer);
        create table if not exists sources(
            hash text primary key, body text, first_round integer,
            authored_by text default 'ast');
        create table if not exists ledger(
            round integer, oid integer, delta integer, reason text);
        create table if not exists jobs(
            jid integer primary key, type text, kb real, reward integer,
            winner integer, posted_round integer, won_round integer,
            source_file text);
        create table if not exists trades(
            round integer, buyer integer, seller integer, name text,
            fee integer);
        create table if not exists rounds(
            round integer primary key, ts real, pop integer, births integer,
            deaths integer, paid_out integer, burned integer,
            jobs_open integer, jobs_won integer, trades integer,
            llm_muts integer, cpu_ms integer);
        create table if not exists events(round integer, ts real, text text);
        create table if not exists org_snapshots(
            round integer, oid integer, balance integer,
            jobs_won integer, sold integer, goods integer);
        """)
        self.con.commit()

    def event(self, rnd: int, text: str) -> None:
        self.con.execute("insert into events values(?,?,?)",
                         (rnd, time.time(), text))

    def save_source(self, body: str, rnd: int, author: str) -> str:
        h = hashlib.sha256(body.encode()).hexdigest()[:16]
        self.con.execute(
            "insert or ignore into sources values(?,?,?,?)",
            (h, body, rnd, author))
        return h

    def get_source(self, h: str) -> str | None:
        row = self.con.execute(
            "select body from sources where hash=?", (h,)).fetchone()
        return row[0] if row else None


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)
