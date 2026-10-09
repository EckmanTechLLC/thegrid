"""Grid 2 daemon: scheduler, settlement, lifecycle, fossil record, viewer.

Round discipline: every living organism's source runs as a real process
under rlimits; the kernel's rusage is the metabolic bill; actions are
settled only after the process has exited. The daemon never judges code -
it verifies outputs, meters resources, moves money, and keeps records.
"""
from __future__ import annotations

import json
import os
import random
import resource
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import mutate
from .jobs import Broker
from .world import (ANCESTOR_GRANT, AS_LIMIT_MB, BIRTH_TAX, CPU_LIMIT_S, DB,
                    FSIZE_LIMIT_MB, GOOD_RENT_PER_10KB, JOBS, MAX_ACTIONS_PER_ROUND,
                    MAX_GOOD_BYTES, MAX_POP, MAX_SOURCE_BYTES, MIN_SPAWN_GRANT,
                    MORGUE, ORGS, ROUND_OVERHEAD, RSS_CYCLES_PER_MB, RSS_FREE_MB,
                    STATE, STILLBORN_REFUND, WALL_LIMIT_S, Organism, read_json,
                    write_json)

APP = Path(__file__).parent
ROUND_SLEEP = float(os.environ.get("GRID2_ROUND_SLEEP", "2.0"))
WORKERS = int(os.environ.get("GRID2_WORKERS", "6"))
BODY_URL = os.environ.get("GRID2_BODY_URL", "")
BODY_RATE = int(os.environ.get("GRID2_BODY_RATE", "400"))
BODY_MIN_MOTION = float(os.environ.get("GRID2_BODY_MIN", "1.0"))
# calibrated 2026-10-08: still scene 0.27, single 90-degree swing ~2.0
BODY_MAX_PAY = 20_000


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S + 1))
    resource.setrlimit(resource.RLIMIT_AS,
                       (AS_LIMIT_MB << 20, AS_LIMIT_MB << 20))
    resource.setrlimit(resource.RLIMIT_FSIZE,
                       (FSIZE_LIMIT_MB << 20, FSIZE_LIMIT_MB << 20))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.setsid()
    os.nice(10)


class World:
    def __init__(self):
        for d in (ORGS, JOBS, MORGUE):
            d.mkdir(parents=True, exist_ok=True)
        self.db = DB(STATE / "history.sqlite3")
        self.broker = Broker(self.db)
        self.rng = random.Random()
        self.orgs: dict[int, Organism] = {}
        self.round = 0
        self.next_oid = 1
        self.pending_deliveries: list[dict] = []
        self.lock = threading.Lock()
        self.stats_cache: dict = {}
        self.llm_pool: list[str] = []   # compiled variants, authored off-thread
        self.body_queue: list[tuple[int, bytes]] = []
        self.body_payouts: list[tuple[int, int, float]] = []
        self.body_trials = 0
        self.body_paid_total = 0
        self.body_live = False   # eye verified recently; blind bounty hides
        self._load()
        if mutate.LLM_URL:
            threading.Thread(target=self._llm_nursery, daemon=True).start()
        if BODY_URL:
            threading.Thread(target=self._body_worker, daemon=True).start()

    def _llm_nursery(self):
        """The coder model writes variants on its own clock. Inline LLM calls
        blew the 45s budget on every birth (the model needs minutes, the world
        ticks in seconds) - zero llm genomes in 35k rounds. Here it works at
        leisure and stocks a small pool the spawn path draws from."""
        while True:
            time.sleep(30)
            try:
                if len(self.llm_pool) >= 3 or not self.orgs:
                    continue
                o = self.rng.choice(list(self.orgs.values()))
                src = (o.home / "source.py").read_text()
                ctx = ""
                try:
                    raw = json.loads((o.home / "io" / "context.json").read_text())
                    raw["jobs"] = raw.get("jobs", [])[:12]
                    raw["market"] = raw.get("market", [])[:8]
                    ctx = json.dumps(raw)[:4000]
                except Exception:
                    pass
                child = mutate._llm_mutate(src, timeout=600, context=ctx)
                if child:
                    compile(child, "<llm>", "exec")
                    self.llm_pool.append(child)
            except Exception:
                continue

    def _body_worker(self):
        """The one body serializes itself; trials run off the tick thread.
        An organism that submits bytes to job 0 is speaking to a serial
        port it knows nothing about. The bridge baselines the scene, says
        the bytes to the GIGA, and reports how much the physical world
        moved beyond its own restlessness. Movement is the only thing paid."""
        import urllib.request
        last_health = 0.0
        while True:
            time.sleep(0.5)
            if time.time() - last_health > 30:
                last_health = time.time()
                try:
                    with urllib.request.urlopen(BODY_URL + "/health",
                                                timeout=5) as r:
                        self.body_live = bool(json.load(r).get("camera"))
                except Exception:
                    self.body_live = False
            if not self.body_queue:
                continue
            oid, payload = self.body_queue.pop(0)
            try:
                body = json.dumps({"bytes": list(payload)}).encode()
                req = urllib.request.Request(
                    BODY_URL + "/trial", data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    res = json.load(r)
                self.body_trials += 1
                motion = float(res.get("motion", 0))
                if res.get("camera") and motion >= BODY_MIN_MOTION:
                    pay = min(BODY_MAX_PAY, int(motion * BODY_RATE))
                    self.body_payouts.append((oid, pay, motion))
            except Exception:
                continue

    # -- persistence -------------------------------------------------------
    def _load(self):
        snap = read_json(STATE / "registry.json", None)
        if snap:
            self.round = snap["round"]
            self.next_oid = snap["next_oid"]
            self.pending_deliveries = snap.get("deliveries", [])
            for row in snap["orgs"]:
                o = Organism(**row)
                if (o.home / "source.py").exists():
                    self.orgs[o.oid] = o
        for o in self.orgs.values():   # registries from before lineage tracking
            if not o.root:
                o.root = o.oid if not o.parent else (
                    self.orgs[o.parent].root if o.parent in self.orgs else o.oid)
        if not self.orgs:
            self._genesis()

    def _save(self):
        write_json(STATE / "registry.json", {
            "round": self.round, "next_oid": self.next_oid,
            "deliveries": self.pending_deliveries,
            "orgs": [vars(o) for o in self.orgs.values()]})

    # -- lifecycle ----------------------------------------------------------
    def _make_org(self, source: str, parent: int, gen: int, balance: int,
                  author: str, root: int = 0) -> Organism:
        oid = self.next_oid
        self.next_oid += 1
        home = ORGS / str(oid)
        (home / "work").mkdir(parents=True)
        (home / "io").mkdir()
        (home / "inbox").mkdir()
        (home / "source.py").write_text(source)
        h = self.db.save_source(source, self.round, author)
        o = Organism(oid=oid, parent=parent, gen=gen, born_round=self.round,
                     balance=balance, src_hash=h, author=author,
                     root=root or oid)
        self.orgs[oid] = o
        self.db.con.execute(
            "insert into organisms(oid,parent,gen,born_round,src_hash)"
            " values(?,?,?,?,?)", (oid, parent, gen, self.round, h))
        return o

    def _genesis(self):
        names = sorted((APP / "ancestors").glob("*.py"))
        for path in names:
            self._make_org(path.read_text(), parent=0, gen=0,
                           balance=ANCESTOR_GRANT, author="genesis")
        # two extra generalists so the palette is not one-of-each fragile
        g = (APP / "ancestors" / "generalist.py").read_text()
        for _ in range(2):
            self._make_org(g, 0, 0, ANCESTOR_GRANT, "genesis")
        self.db.event(self.round, f"genesis: {len(self.orgs)} ancestors seeded")

    def _die(self, o: Organism, cause: str):
        self.db.con.execute(
            "update organisms set died_round=?, cause=?, jobs_won=?,"
            " trades_sold=?, final_balance=? where oid=?",
            (self.round, cause, o.jobs_won, o.trades_sold, o.balance, o.oid))
        shutil.rmtree(o.home, ignore_errors=True)
        del self.orgs[o.oid]

    # -- one organism's turn -------------------------------------------------
    def _run_org(self, o: Organism) -> dict:
        io = o.home / "io"
        actions_file = io / "actions.jsonl"
        actions_file.unlink(missing_ok=True)
        inbox = sorted(p.name for p in (o.home / "inbox").iterdir())[:50]
        market = [{"seller": s.oid, "name": n, "price": g["price"],
                   "size": g["size"]}
                  for s in self.orgs.values() if s.oid != o.oid
                  for n, g in s.goods.items()][:200]
        write_json(io / "context.json", {
            "oid": o.oid, "round": self.round, "balance": o.balance,
            "gen": o.gen,
            "jobs": self.broker.listing(body=self.body_live),
            "market": market, "my_goods": {n: g["price"] for n, g in o.goods.items()},
            "inbox": inbox})
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin",
               "PYTHONPATH": str(APP / "shim"), "GRID_IO": "../io",
               "HOME": str(o.home / "work"), "LANG": "C.UTF-8"}
        t0 = time.time()
        try:
            proc = subprocess.Popen(
                ["python3", "-S", "../source.py"], cwd=o.home / "work", env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=_limits, start_new_session=False)
        except OSError:
            return {"oid": o.oid, "cpu_ms": 50, "rss_mb": 0, "status": "spawn-fail"}
        cpu_ms, rss_mb, status = 0, 0, "ok"
        deadline = t0 + WALL_LIMIT_S
        while True:
            try:
                pid, st, ru = os.wait4(proc.pid, os.WNOHANG)
            except ChildProcessError:
                pid, st, ru = proc.pid, 0, None
            if pid:
                proc.returncode = 0  # reaped; stop Popen from waiting again
                if ru:
                    cpu_ms = int((ru.ru_utime + ru.ru_stime) * 1000)
                    rss_mb = ru.ru_maxrss // 1024
                break
            if time.time() > deadline:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                status = "walltime"
            time.sleep(0.02)
        return {"oid": o.oid, "cpu_ms": max(cpu_ms, 1), "rss_mb": rss_mb,
                "status": status}

    # -- settlement -----------------------------------------------------------
    def _settle(self, o: Organism, usage: dict, summary: dict,
                spawn_queue: list):
        charge = (usage["cpu_ms"] + ROUND_OVERHEAD
                  + max(0, usage["rss_mb"] - RSS_FREE_MB) * RSS_CYCLES_PER_MB)
        rent = sum(g["size"] // 10240 * GOOD_RENT_PER_10KB + 1
                   for g in o.goods.values())
        o.balance -= charge + rent
        summary["cpu_ms"] += usage["cpu_ms"]
        lines = []
        try:
            raw = (o.home / "io" / "actions.jsonl").read_text()
            lines = raw.splitlines()[:MAX_ACTIONS_PER_ROUND]
        except OSError:
            pass
        for line in lines:
            try:
                a = json.loads(line)
                kind = a["act"]
            except Exception:
                continue
            try:
                if kind == "submit":
                    self._do_submit(o, a, summary)
                elif kind == "publish":
                    self._do_publish(o, a)
                elif kind == "unpublish":
                    gone = o.goods.pop(str(a.get("name", "")), None)
                    if gone:  # delisting frees the bytes too, or the store
                        Path(gone["path"]).unlink(missing_ok=True)  # leaks 80MB/day

                elif kind == "fetch":
                    self._do_fetch(o, a, summary)
                elif kind == "spawn":
                    spawn_queue.append((o.oid, a))
            except Exception:
                continue

    def _resolve_in_work(self, o: Organism, rel: str) -> Path | None:
        p = (o.home / "work" / rel).resolve()
        return p if p.is_relative_to(o.home) and p.is_file() else None

    def _do_submit(self, o: Organism, a: dict, summary: dict):
        jid = int(a["jid"])
        if jid == 0 and BODY_URL:
            p = self._resolve_in_work(o, str(a["path"]))
            if p and p.stat().st_size <= 4096 and len(self.body_queue) < 4:
                self.body_queue.append((o.oid, p.read_bytes()[:64]))
            return
        job = self.broker.open.get(jid)
        p = self._resolve_in_work(o, str(a["path"]))
        if not job or not p or p.stat().st_size > MAX_GOOD_BYTES * 4:
            return
        if not self.broker.verify(job, p.read_bytes()):
            job["fails"] = job.get("fails", 0) + 1
            return
        if True:
            reward = self.broker.settle(jid, o.oid, self.round)
            o.balance += reward
            o.jobs_won += 1
            o.last_income_round = self.round
            summary["paid_out"] += reward
            summary["jobs_won"] += 1
            summary["wins"].append(o.oid)
            self.db.con.execute("insert into ledger values(?,?,?,?)",
                                (self.round, o.oid, reward, f"job:{job['type']}"))

    def _do_publish(self, o: Organism, a: dict):
        p = self._resolve_in_work(o, str(a["path"]))
        if not p or p.stat().st_size > MAX_GOOD_BYTES or len(o.goods) >= 16:
            return
        name = str(a["name"])[:48]
        store = o.home / "goods"
        store.mkdir(exist_ok=True)
        dest = store / name
        shutil.copyfile(p, dest)
        o.goods[name] = {"path": str(dest), "price": max(1, int(a["price"])),
                         "size": dest.stat().st_size}

    def _do_fetch(self, o: Organism, a: dict, summary: dict):
        seller = self.orgs.get(int(a["seller"]))
        if not seller or seller.oid == o.oid:
            return
        good = seller.goods.get(str(a["name"]))
        if not good or o.balance < good["price"]:
            return
        o.balance -= good["price"]
        seller.balance += good["price"]
        seller.trades_sold += 1
        seller.last_income_round = self.round
        summary["trades"] += 1
        summary["deals"].append([o.oid, seller.oid])
        self.pending_deliveries.append(
            {"buyer": o.oid, "src": good["path"], "name": str(a["name"])})
        self.db.con.execute("insert into trades values(?,?,?,?,?)",
                            (self.round, o.oid, seller.oid, str(a["name"]),
                             good["price"]))

    def _do_spawns(self, spawn_queue: list, summary: dict):
        self.rng.shuffle(spawn_queue)
        donors = [((ORGS / str(oid) / "source.py"))
                  for oid in self.rng.sample(list(self.orgs),
                                             min(6, len(self.orgs)))]
        donor_src = []
        for d in donors:
            try:
                donor_src.append(d.read_text())
            except OSError:
                pass
        for parent_oid, a in spawn_queue:
            parent = self.orgs.get(parent_oid)
            if not parent:
                continue
            grant = int(a.get("grant", 0))
            source = str(a.get("source", ""))[:MAX_SOURCE_BYTES]
            if grant < MIN_SPAWN_GRANT or parent.balance < grant or not source:
                continue
            parent.balance -= grant
            if len(self.orgs) >= MAX_POP:
                parent.balance += grant  # no room: refund, no tax
                continue
            child_grant = int(grant * (1 - BIRTH_TAX))
            if self.llm_pool and self.rng.random() < 0.25:
                child_src, author = self.llm_pool.pop(0), "llm"
            else:
                child_src, author = mutate.mutate(source, donor_src, self.rng)
            try:
                compile(child_src, "<c>", "exec")
            except SyntaxError:
                parent.balance += int(grant * STILLBORN_REFUND)
                continue
            child = self._make_org(child_src, parent.oid, parent.gen + 1,
                                   child_grant, author, root=parent.root)
            summary["births"] += 1
            summary["born"].append(child.oid)
            summary["burned"] += grant - child_grant
            if author == "llm":
                summary["llm_muts"] += 1
                self.db.event(self.round,
                              f"the coder model authored organism {child.oid}")

    # -- the round ------------------------------------------------------------
    def tick(self):
        self.round += 1
        summary = dict(births=0, deaths=0, paid_out=0, burned=0, jobs_won=0,
                       trades=0, llm_muts=0, cpu_ms=0,
                       born=[], died=[], wins=[], deals=[])
        # yesterday's movements get paid before today's turns
        for oid, pay, motion in self.body_payouts:
            o = self.orgs.get(oid)
            if o:
                o.balance += pay
                o.last_income_round = self.round
                summary["paid_out"] += pay
                summary["wins"].append(oid)
                self.body_paid_total += pay
                self.db.con.execute("insert into ledger values(?,?,?,?)",
                                    (self.round, oid, pay, "body"))
                if self.body_paid_total == pay:
                    self.db.event(self.round,
                                  f"FIRST LIMB MOVEMENT - organism {oid} "
                                  f"moved the real world (motion {motion})")
        self.body_payouts = []
        self.broker.expire(self.round)
        self.broker.replenish(self.round,
                              target=max(8, len(self.orgs)))
        # yesterday's purchases arrive before today's turns
        for d in self.pending_deliveries:
            buyer = self.orgs.get(d["buyer"])
            if buyer and Path(d["src"]).exists():
                try:
                    shutil.copyfile(d["src"],
                                    buyer.home / "inbox" / d["name"][:48])
                except OSError:
                    pass
        self.pending_deliveries = []
        living = list(self.orgs.values())
        self.rng.shuffle(living)
        with ThreadPoolExecutor(WORKERS) as pool:
            usages = list(pool.map(self._run_org, living))
        spawn_queue: list = []
        for o, usage in zip(living, usages):
            self._settle(o, usage, summary, spawn_queue)
        self._do_spawns(spawn_queue, summary)
        for o in list(self.orgs.values()):
            if o.balance <= 0:
                summary["died"].append(o.oid)
                self._die(o, "broke")
                summary["deaths"] += 1
        if not self.orgs:
            self.db.event(self.round, "EXTINCTION - the market consumed "
                                      "everyone; reseeding ancestors")
            self._genesis()
        self.db.con.execute(
            "insert into rounds values(?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.round, time.time(), len(self.orgs), summary["births"],
             summary["deaths"], summary["paid_out"], summary["burned"],
             len(self.broker.open), summary["jobs_won"], summary["trades"],
             summary["llm_muts"], summary["cpu_ms"]))
        if self.round % 200 == 0:
            self.db.con.executemany(
                "insert into org_snapshots values(?,?,?,?,?,?)",
                [(self.round, o.oid, o.balance, o.jobs_won, o.trades_sold,
                  len(o.goods)) for o in self.orgs.values()])
        if self.round % 500 == 0:
            self._janitor()
        self.db.con.commit()
        self._save()
        with self.lock:
            self.stats_cache = self._snapshot(summary)

    def _janitor(self):
        """Keep the capture, cap the bulk. The fossil record (organisms,
        sources, rounds, events, org_snapshots) is permanent; the two
        high-churn tables are pruned past ~50k rounds, and goods files no
        listing points at are deleted - delisted inventory used to linger
        as unbilled ghost bytes."""
        horizon = self.round - 50_000
        if horizon > 0:
            self.db.con.execute("delete from ledger where round < ?", (horizon,))
            self.db.con.execute(
                "delete from jobs where posted_round < ? and winner is null",
                (horizon,))
        for o in self.orgs.values():
            store = o.home / "goods"
            if store.is_dir():
                keep = {Path(g["path"]).name for g in o.goods.values()}
                for f in store.iterdir():
                    if f.name not in keep:
                        f.unlink(missing_ok=True)

    def _snapshot(self, summary: dict) -> dict:
        orgs = sorted(self.orgs.values(), key=lambda o: -o.balance)
        return {
            "round": self.round, "ts": time.time(),
            "population": len(self.orgs),
            "summary": summary,
            "jobsOpen": len(self.broker.open),
            "bodyTrials": self.body_trials,
            "bodyLive": self.body_live,
            "bodyPaid": self.body_paid_total,
            "jobTypes": {t: sum(1 for j in self.broker.open.values()
                                if j["type"] == t)
                         for t in ("compress", "index", "checksum", "sort")},
            "market": sum(len(o.goods) for o in self.orgs.values()),
            "maxGen": max((o.gen for o in self.orgs.values()), default=0),
            "organisms": [
                {"oid": o.oid, "parent": o.parent, "gen": o.gen,
                 "root": o.root, "author": o.author,
                 "balance": o.balance, "age": self.round - o.born_round,
                 "jobsWon": o.jobs_won, "sold": o.trades_sold,
                 "goods": len(o.goods), "src": o.src_hash}
                for o in orgs],
            "events": [{"round": r, "text": t} for r, _, t in
                       self.db.con.execute(
                           "select * from events order by rowid desc limit 12")],
        }


# -- viewer -------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    world: World = None

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def do_GET(self):
        w = self.world
        if self.path == "/":
            self._send(200, (APP / "viewer.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with w.lock:
                self._send(200, json.dumps(w.stats_cache))
        elif self.path.startswith("/api/organism/"):
            try:
                oid = int(self.path.rsplit("/", 1)[1])
                o = w.orgs[oid]
                self._send(200, json.dumps({
                    "oid": oid, "gen": o.gen, "balance": o.balance,
                    "jobsWon": o.jobs_won, "sold": o.trades_sold,
                    "source": (o.home / "source.py").read_text()}))
            except Exception:
                self._send(404, "{}")
        else:
            self._send(404, "{}")


def main():
    world = World()
    Handler.world = world
    server = ThreadingHTTPServer(("0.0.0.0", 8840), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    world.db.event(world.round, "daemon up")
    while True:
        t0 = time.time()
        try:
            world.tick()
        except Exception as e:  # the world must not die of a bookkeeping bug
            world.db.event(world.round, f"tick error: {type(e).__name__}: {e}")
            world.db.con.commit()
        time.sleep(max(0.2, ROUND_SLEEP - (time.time() - t0)))


if __name__ == "__main__":
    main()
