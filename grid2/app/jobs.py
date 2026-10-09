"""Real demand, real verification.

Jobs are cut from the actual files of the host (mounted read-only at
/corpus). Nothing synthetic: the input to every job is a real file that
exists because the machine lived. Payment happens only after the daemon
verifies the output the hard way. First verified submission wins; losers
burned their CPU for nothing, which is what a market is.
"""
from __future__ import annotations

import bz2
import gzip
import hashlib
import lzma
import random
import shutil
from collections import Counter
from pathlib import Path

from .world import JOBS

CORPUS = Path("/corpus")
MIN_KB, MAX_KB = 1, 256
TYPES = ("compress", "index", "checksum", "sort")


def _usable(p: Path) -> bool:
    try:
        return p.is_file() and MIN_KB * 1024 <= p.stat().st_size <= MAX_KB * 1024
    except OSError:
        return False


def scan_corpus(sample: int = 4000) -> list[Path]:
    out = []
    for root in CORPUS.iterdir() if CORPUS.exists() else []:
        for p in root.rglob("*"):
            if _usable(p):
                out.append(p)
            if len(out) >= sample:
                return out
    return out


class Broker:
    def __init__(self, db):
        self.db = db
        self.next_jid = (db.con.execute("select coalesce(max(jid),0) from jobs")
                         .fetchone()[0]) + 1
        self.open: dict[int, dict] = {}
        self._corpus: list[Path] = []
        self._rescan_round = -10_000

    def _reward(self, jtype: str, kb: float) -> int:
        # Scaled so one solid win funds ~50-100 rounds of metabolism and a
        # few wins fund a child; at the old scale reproduction was
        # arithmetically unreachable and the economy deflated to a standstill.
        base = {"compress": 240, "index": 200, "checksum": 100, "sort": 200}[jtype]
        per_kb = {"compress": 100, "index": 40, "checksum": 12, "sort": 32}[jtype]
        return int(base + per_kb * kb)

    def replenish(self, rnd: int, target: int) -> None:
        """Keep the posted-job pool near target, cut from real files."""
        if rnd - self._rescan_round >= 200 or not self._corpus:
            self._corpus = scan_corpus()
            self._rescan_round = rnd
        # Rotate through types when posting: winnable jobs clear instantly
        # while impossible ones linger, so pure random choice lets the pool
        # silt up with one toxic type (observed: six incompressible logs
        # blocking the entire economy at round 90).
        while len(self.open) < target and self._corpus:
            src = random.choice(self._corpus)
            jtype = TYPES[self.next_jid % len(TYPES)]
            jid = self.next_jid
            self.next_jid += 1
            jdir = JOBS / str(jid)
            jdir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(src, jdir / "input")
            except OSError:
                continue
            kb = (jdir / "input").stat().st_size / 1024
            job = {"jid": jid, "type": jtype, "kb": round(kb, 1), "fails": 0,
                   "input": str(jdir / "input"),
                   "reward": self._reward(jtype, kb), "posted": rnd}
            self.open[jid] = job
            self.db.con.execute(
                "insert into jobs(jid,type,kb,reward,posted_round,source_file)"
                " values(?,?,?,?,?,?)",
                (jid, jtype, kb, job["reward"], rnd, str(src)))

    def expire(self, rnd: int, ttl: int = 40) -> None:
        # Age out, and also cull jobs that keep failing verification - an
        # input that cannot be compressed is not a job, it is a tar pit.
        for jid in [j for j, job in self.open.items()
                    if rnd - job["posted"] > ttl or job.get("fails", 0) >= 3]:
            shutil.rmtree(JOBS / str(jid), ignore_errors=True)
            del self.open[jid]

    def listing(self, body: bool = False) -> list[dict]:
        jobs = [{k: j[k] for k in ("jid", "type", "kb", "input", "reward")}
                for j in self.open.values()]
        if body:
            # The standing bounty - listed only while the camera can verify,
            # because a blind bounty trains the colony that the door is
            # worthless: cost paid, nothing earned, discovery punished.
            jobs.append({"jid": 0, "type": "body", "kb": 0.0, "input": "",
                         "reward": 999})
        return jobs

    # -- verification: the only sacred code in the world -------------------
    def verify(self, job: dict, result: bytes) -> bool:
        try:
            original = Path(job["input"]).read_bytes()
            if job["type"] == "compress":
                if len(result) >= len(original):
                    return False
                for opener in (gzip.decompress, lzma.decompress, bz2.decompress):
                    try:
                        if opener(result) == original:
                            return True
                    except Exception:
                        continue
                return False
            if job["type"] == "checksum":
                return (result.decode("ascii", "ignore").strip().lower()
                        == hashlib.sha256(original).hexdigest())
            if job["type"] == "index":
                import json
                want = Counter(original.decode("utf-8", "replace").lower().split())
                got = json.loads(result.decode("utf-8", "replace"))
                return (isinstance(got, dict) and len(got) == len(want)
                        and all(want.get(k) == v for k, v in got.items()))
            if job["type"] == "sort":
                want = sorted(original.decode("utf-8", "replace").splitlines())
                got = result.decode("utf-8", "replace").splitlines()
                return got == want
        except Exception:
            return False
        return False

    def settle(self, jid: int, winner: int, rnd: int) -> int:
        job = self.open.pop(jid)
        self.db.con.execute(
            "update jobs set winner=?, won_round=? where jid=?",
            (winner, rnd, jid))
        shutil.rmtree(JOBS / str(jid), ignore_errors=True)
        return job["reward"]
