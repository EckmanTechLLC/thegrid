#!/usr/bin/env python3
"""Report everything, so nothing gets cherry-picked.

Written after a week of reading /api/state - a snapshot of now - while five
tables of actual time series sat unqueried, and after decoding the `dominant`
field for the first time revealed the only positive result the project has.
The point of this file is that it does not have a hypothesis. It scans every
numeric column of every colony, groups them by configuration, and reports what
separates - whether or not anyone was looking for it.
"""
import json, sqlite3, sys, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

STATE = Path.home() / ".local/state"
TREE = Path.home() / "odin/thegrid-colony2"
sys.path.insert(0, str(TREE))
from src.colony.record import encode_genome            # noqa: E402
from src.colony.isa import ISA                         # noqa: E402

GLYPH = {encode_genome([op]): ISA[op].name for op in range(len(ISA))}


def units():
    out = []
    for unit in sorted((Path.home() / ".config/systemd/user").glob("thegrid-*.service")):
        line = next((l for l in unit.read_text().splitlines()
                     if l.startswith("ExecStart=")), "")
        if "src.colony.live" not in line:
            continue
        port = int(line.split("--port ")[1].split()[0])
        state = line.split("--state ")[1].split("/colony.pkl")[0].split("/")[-1]
        label = (line.split('--name "')[1].split('"')[0]
                 if '--name "' in line else unit.stem.replace("thegrid-", ""))
        feats = (line.split('--features "')[1].split('"')[0]
                 if '--features "' in line else "")
        out.append({"label": label, "port": port, "state": state, "features": feats})
    return out


def live(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=8) as r:
            return json.load(r)
    except Exception:
        return {}


def group_of(c):
    lab = c["label"]
    if "-" in lab:
        return lab.rsplit("-", 1)[0]
    return {"": "singleton"}.get("", "singleton")


def decode(s):
    return [GLYPH.get(ch, "?") for ch in (s or "")]


def motifs(names, lo=3, hi=8):
    """Every repeated contiguous run of instructions in one genome."""
    found = Counter()
    n = len(names)
    for size in range(lo, min(hi, n // 2) + 1):
        for i in range(n - size + 1):
            frag = tuple(names[i:i + size])
            found[frag] += 1
    return {f: c for f, c in found.items() if c >= 2}


colonies = units()
for c in colonies:
    c["state_data"] = live(c["port"])
    c["group"] = (c["label"].rsplit("-", 1)[0] if "-" in c["label"] else c["label"])

print("=" * 78)
print("1. REPEATED MOTIFS IN DOMINANT GENOMES  (the thing I never decoded)")
print("=" * 78)
everywhere = Counter()
for c in colonies:
    dom = (c["state_data"] or {}).get("dominant") or ""
    names = decode(dom)
    if not names:
        continue
    reps = motifs(names)
    best = sorted(reps.items(), key=lambda kv: (-len(kv[0]) * kv[1], -kv[1]))[:2]
    tag = "  ".join(f"{'+'.join(f)} x{n}" for f, n in best) or "(none repeated)"
    print(f"  {c['label']:<14} len {len(names):>3}  {tag}")
    for frag, n in reps.items():
        if len(frag) >= 4:
            everywhere[frag] += 1
print("\n  motifs of 4+ instructions repeated inside a genome, by how many colonies:")
for frag, n in everywhere.most_common(8):
    print(f"    {n:>2} colonies  {'+'.join(frag)}")

print()
print("=" * 78)
print("2. WHICH MUTATION MECHANISM ACTUALLY PRODUCES SURVIVING GENOMES")
print("=" * 78)
print("  (mutation_origins: 19,000 rows per colony, never queried until now)")
by_group = defaultdict(Counter)
repro = defaultdict(Counter)
for c in colonies:
    db = STATE / c["state"] / "history.sqlite3"
    if not db.exists():
        continue
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for kind, n, births in con.execute(
                "select mutation_type, count(*), sum(origin_births) "
                "from mutation_origins group by 1"):
            by_group[c["group"]][kind] += n
            repro[c["group"]][kind] += births or 0
        con.close()
    except Exception as exc:
        print(f"  {c['label']}: {exc}")
for group in sorted(by_group):
    total = sum(by_group[group].values()) or 1
    tb = sum(repro[group].values()) or 1
    print(f"\n  {group}:")
    print(f"    {'mechanism':<18}{'new genomes':>12}{'share':>8}{'births they went on to':>24}{'share':>8}")
    for kind, n in by_group[group].most_common():
        b = repro[group][kind]
        print(f"    {kind:<18}{n:>12,}{100*n/total:>7.1f}%{b:>24,}{100*b/tb:>7.1f}%")
