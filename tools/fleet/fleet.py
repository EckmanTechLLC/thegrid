#!/usr/bin/env python3
"""One page for the whole fleet.

Each colony serves its own viewer on its own port, so seeing all seven meant
seven tabs. A browser cannot poll them itself - different ports are different
origins and the colonies send no CORS headers - so this fans out server-side
and returns one combined document. The colonies are not modified and do not
know this exists.
"""
from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
def discover() -> list[tuple[str, int]]:
    """Read the colonies out of the unit files rather than a hardcoded list.

    There are two dozen of these now and the number changes whenever a
    replicate group is added. A list maintained by hand would be wrong within
    the day - it already was once, when colony eight was added and this file
    was not updated.
    """
    units = Path.home() / ".config/systemd/user"
    found = []
    for unit in sorted(units.glob("thegrid-*.service")):
        text = unit.read_text()
        line = next((l for l in text.splitlines() if l.startswith("ExecStart=")), "")
        if "src.colony.live" not in line:
            continue                       # fleet, operator: not colonies
        port = line.split("--port ")[1].split()[0] if "--port " in line else None
        label = (line.split('--name "')[1].split('"')[0]
                 if '--name "' in line else unit.stem.replace("thegrid-", ""))
        if port:
            found.append((label, int(port)))
    return found


COLONIES = discover()
# Only what the dashboard draws. The full snapshot carries five 2,304-character
# fields per colony; sending all of them seven times over would be 80KB a poll.
KEEP = ("name", "epoch", "tick", "population", "generation", "cost", "features",
        "complexity", "lease", "groups", "predation", "frontier", "bus", "machine",
        "weather", "width", "height",
        "tasks", "deathsByCause", "reclaimPool", "slotsHeld", "publishRefused",
        "signalsHeard", "memoryBytes", "memoryMaxBytes", "dominant", "carriers",
        "biomePopulations", "mutator")


def fetch(entry: tuple[str, int]) -> dict:
    label, port = entry
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=6) as r:
            state = json.load(r)
    except Exception as exc:
        return {"label": label, "port": port, "up": False, "error": type(exc).__name__}
    trimmed = {k: state[k] for k in KEEP if k in state}
    # The colony knows its own name; the unit stem is only a fallback for
    # the older units that predate --name.
    trimmed.update(label=state.get("name") or label, port=port, up=True)
    return trimmed



# ---------------------------------------------------------------- notable --
# Two dozen cards of numbers do not tell you where to look. These rules do,
# and they are deliberately conservative: a badge has to mean something, or
# everything gets one and the page is noise again.
#
# The replicate groups are what make this possible. A colony can now be
# compared against SIBLINGS running the identical configuration, so "unusual"
# means unusual for its own group rather than unusual against a fleet of
# colonies that were never comparable in the first place.

# Mechanisms that are almost always exactly zero. Any of them moving is worth
# a look, because most of them have never moved at all.
RARE = [("royalties", "a published routine got CALLED"),
        ("signalsHeard", "a signal was actually HEARD"),
        ("bountyClaims", "a bounty was claimed"),
        ("macroRuns", "population-authored macros ran")]


def group_of(label: str) -> str:
    """Replicate group, or the colony's own name if it has no siblings."""
    return label.rsplit("-", 1)[0] if "-" in label else label


def notable(colonies: list[dict]) -> None:
    """Attach a short list of reasons each colony might be worth opening."""
    live = [c for c in colonies if c.get("up")]
    if not live:
        return
    groups: dict[str, list[dict]] = {}
    for c in live:
        groups.setdefault(group_of(c.get("label", "")), []).append(c)

    def num(c, *path, default=0):
        node = c
        for key in path:
            node = (node or {}).get(key) if isinstance(node, dict) else None
        return node if isinstance(node, (int, float)) else default

    fleet_complexity = max((num(c, "complexity", "max") for c in live), default=0)
    deepest = max((num(c, "generation") for c in live), default=0)

    for c in live:
        why = []
        siblings = [s for s in groups[group_of(c.get("label", ""))] if s is not c]

        # 1. Out of line with its own replicates. Needs at least two siblings,
        #    otherwise "unusual" is just one number next to one other number.
        if len(siblings) >= 2:
            pops = [num(s, "population") for s in siblings]
            mean = sum(pops) / len(pops)
            spread = (sum((v - mean) ** 2 for v in pops) / len(pops)) ** 0.5
            mine = num(c, "population")
            if spread > 0 and abs(mine - mean) > 2.5 * spread and abs(mine - mean) > 25:
                direction = "far above" if mine > mean else "far below"
                why.append(f"population {direction} its replicates ({mine} vs ~{mean:.0f})")

        # 2. A mechanism that is dead ACROSS THE FLEET RIGHT NOW has fired
        #    here. Measured against the other colonies rather than against my
        #    assumptions: signalsHeard and bounty claims were both hardcoded as
        #    "almost always zero" and both turned out to be running in a third
        #    of the fleet, which flagged 14 of 24 colonies and made the page
        #    useless again.
        for key, blurb in RARE:
            value = num(c, key) or num(c, "frontier", key) or num(c, "bus", key)
            if not value:
                continue
            holders = sum(1 for o in live
                          if (num(o, key) or num(o, "frontier", key)
                              or num(o, "bus", key)))
            if holders <= max(1, len(live) // 5):
                why.append(blurb)

        # 3. Solving something none of its siblings can.
        mine_tasks = set((c.get("tasks") or {}).keys())
        if siblings and mine_tasks:
            theirs = set().union(*[set((s.get("tasks") or {}).keys()) for s in siblings])
            new = mine_tasks - theirs
            if new:
                why.append("solves " + ", ".join(sorted(new)) + " and its replicates do not")

        # 4. Fleet extremes.
        if fleet_complexity and num(c, "complexity", "max") == fleet_complexity:
            why.append(f"most complex genome in the fleet ({fleet_complexity} acquired opcodes)")
        if deepest and num(c, "generation") == deepest:
            why.append(f"deepest lineage in the fleet (generation {deepest})")

        # 5. On the edge.
        pop = num(c, "population")
        if 0 < pop <= 5:
            why.append(f"about to go extinct ({pop} left)")

        c["notable"] = why[:3]

    # Anything every sibling also shows is a property of the CONFIGURATION,
    # not a reason to open this particular colony. All four eviction
    # replicates carrying the same badge tells you about eviction; it does not
    # tell you which one to look at.
    for c in live:
        siblings = [s for s in groups[group_of(c.get("label", ""))] if s is not c]
        if not siblings:
            continue
        shared = set(c.get("notable") or [])
        for sib in siblings:
            shared &= set(sib.get("notable") or [])
        if shared:
            c["notable"] = [w for w in c["notable"] if w not in shared]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):        # keep the journal readable
        pass

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/fleet"):
            with ThreadPoolExecutor(max_workers=min(32, max(1, len(COLONIES)))) as pool:
                colonies = list(pool.map(fetch, COLONIES))
            notable(colonies)
            self._send(json.dumps({"colonies": colonies},
                                  separators=(",", ":")).encode(), "application/json")
        elif self.path in ("/", "/index.html"):
            self._send((HERE / "fleet.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("FLEET_PORT", "8799"))
    print(f"[fleet] serving {len(COLONIES)} colonies on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
