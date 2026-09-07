#!/usr/bin/env python3
"""Generate GUIDE.md from what each colony's code and unit file actually say.

Written because the same mistake kept recurring: comparing colonies without
knowing how they differ, then reporting the difference as a result. Colony two
recolonises from peers and starts epochs with evolved genomes; colony eight has
no peers and restarts from ancestors every time. That single fact invalidated
two conclusions before anyone noticed it.

Nothing here is typed by hand. Every value is read from the unit file, the git
tree, or by importing the colony's own modules in its own interpreter.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path("/home/etl")
UNITS = HOME / ".config/systemd/user"
VENV = HOME / "odin/thegrid-worktree/.venv/bin/python"
REFERENCE = "thegrid-colony2"

COLONIES = [
    ("One", "thegrid-colony.service", "thegrid-colony1", "thegrid"),
    ("Two", "thegrid-colony2.service", "thegrid-colony2", "thegrid-colony2"),
    ("Three", "thegrid-colony3.service", "thegrid-colony3", "thegrid-colony3"),
    ("Four", "thegrid-colony4.service", "thegrid-colony4", "thegrid-colony4"),
    ("Five", "thegrid-colony5.service", "thegrid-colony5", "thegrid-colony5"),
    ("Six", "thegrid-colony6.service", "thegrid-colony6", "thegrid-colony6"),
    ("Seven", "thegrid-colony7.service", "thegrid-colony7", "thegrid-colony7"),
    ("Eight", "thegrid-colony8.service", "thegrid-colony8", "thegrid-colony8"),
]

# Run inside each tree, in its own interpreter, so a tree with a different
# instruction set reports its own rather than a neighbour's.
PROBE = r'''
import json, sys
sys.path.insert(0, ".")
from src.colony.isa import ISA, NUM_OPS, Op, build_ancestor, build_founder_palette
from src.colony.colony import Colony
from src.colony.world import World, WorldConfig
out = {"num_ops": NUM_OPS, "ops": [i.name for i in ISA],
       "costs": {i.name: i.cost for i in ISA},
       "ancestor_len": len(build_ancestor()),
       "palette": len(build_founder_palette()),
       "child_energy": getattr(Colony, "CHILD_ENERGY", None),
       "max_group": getattr(Colony, "MAX_GROUP", None)}
try:
    from src.colony.isa import unpack, REG_COUNT
    out["encoding"] = "packed (op, src, dst)"
    out["registers"] = REG_COUNT
except ImportError:
    out["encoding"] = "tape (bare opcode)"
    out["registers"] = 3
try:
    from src.colony.isa import FEATURE_OPS
    out["feature_ops"] = {k: [ISA[int(o)].name for o in v] for k, v in FEATURE_OPS.items()}
except ImportError:
    out["feature_ops"] = None
from src.colony.substrate import SubstrateWorld
out["subsidy_ticks"] = getattr(SubstrateWorld, "subsidy_ticks", None)
out["has_cpu_income"] = hasattr(SubstrateWorld, "regen_multiplier")
src = open("src/colony/world.py").read()
out["salvage"] = ("global reclaim pool" if "reclaim_pool" in src else "scrap on tiles, decaying")
out["commons_hold"] = "slot_heat" in src
cfg = WorldConfig()
out["world"] = {"tile_regen": cfg.tile_regen, "harvest_rate": cfg.harvest_rate,
                "tile_capacity": cfg.tile_capacity}
from src.colony.substrate import SubstrateWorld as _W
_w = _W(WorldConfig())
_q, _mid = {}, (_w.config.width // 4, _w.config.height // 4)
_corners = [(_mid[0], _mid[1]), (_mid[0] * 3, _mid[1]),
            (_mid[0], _mid[1] * 3), (_mid[0] * 3, _mid[1] * 3)]
for _row in _w.energy:
    for _i in range(len(_row)):
        _row[_i] = 0.0
_before = [_w.energy[_y][_x] for _x, _y in _corners]
_w.step()
_regen = [round(_w.energy[_y][_x] - _b, 4) for (_x, _y), _b in zip(_corners, _before)]
for _row in _w.energy:
    for _i in range(len(_row)):
        _row[_i] = _w.config.tile_capacity
_harv = [round(_w.harvest(_x, _y), 4) for _x, _y in _corners]
_ops = ["HARVEST", "MOVE", "SCAN", "BUILD", "SIGNAL", "NAND", "POST"]
_cost = {}
for _n in _ops:
    try:
        _o = getattr(Op, _n)
    except AttributeError:
        continue
    _cost[_n] = [round(_w.instruction_cost_multiplier(_o, _x, _y), 3) for _x, _y in _corners]
out["quadrants"] = {
    "order": ["NW", "NE", "SW", "SE"],
    "regen_per_step": _regen,
    "harvest_per_call": _harv,
    "instruction_cost": _cost,
    "task_reward": [round(_w.task_reward_multiplier(_x, _y), 3) for _x, _y in _corners],
}
import inspect
out["max_age"] = inspect.signature(Colony.__init__).parameters["max_age"].default
out["founders_default"] = inspect.signature(Colony.__init__).parameters["founders"].default
print(json.dumps(out))
'''


def sh(*args, cwd=None) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True).stdout.strip()


def unit_facts(path: Path) -> dict:
    if not path.exists():
        return {"missing": True}
    text = path.read_text()
    exec_line = next((l for l in text.splitlines() if l.startswith("ExecStart=")), "")
    def flag(name, default=""):
        parts = exec_line.split(f"--{name} ")
        if len(parts) < 2:
            return default
        value = parts[1].split(" --")[0].strip()
        return value.strip('"')
    return {
        "port": flag("port"), "mutator": flag("mutator", "odin"),
        "features": [f for f in flag("features").split(",") if f],
        "peers": [p for p in flag("peers").split(",") if p],
        "ticks_per_second": flag("ticks-per-second"),
        "state": flag("state"),
        "memory_max": next((l.split("=")[1] for l in text.splitlines()
                            if l.startswith("MemoryMax=")), "?"),
    }


def probe(tree: Path) -> dict:
    if not tree.exists():
        return {"missing": True}
    result = subprocess.run([str(VENV), "-c", PROBE], cwd=tree,
                            capture_output=True, text=True)
    if result.returncode != 0:
        return {"error": result.stderr.strip().splitlines()[-1:] or ["probe failed"]}
    return json.loads(result.stdout)


def build() -> str:
    ref = HOME / "odin" / REFERENCE
    rows, details = [], []
    for label, unit, tree_name, state in COLONIES:
        tree = HOME / "odin" / tree_name
        u = unit_facts(UNITS / unit)
        p = probe(tree)
        branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=tree)
        head = sh("git", "rev-parse", "--short", "HEAD", cwd=tree)
        dirty = sh("git", "status", "--porcelain", cwd=tree)
        differs = sh("git", "diff", "--name-only", f"{REFERENCE and ''}HEAD", cwd=tree)
        # which source files differ from the reference tree
        diff_ref = ""
        if tree != ref and tree.exists():
            # -x __pycache__: every .pyc differs by compile timestamp and says
            # nothing about the code.
            diff_ref = sh("diff", "-rq", "-x", "__pycache__",
                          str(ref / "src/colony"), str(tree / "src/colony"))
        changed = []
        for line in diff_ref.splitlines():
            if line.startswith("Files ") and line.endswith(" differ"):
                changed.append(line.split(" and ")[0].removeprefix("Files ").split("/")[-1])
            elif line.startswith("Only in "):
                changed.append(line.split(": ")[-1] + " (present in only one tree)")
        changed = sorted(set(changed))
        active = sh("systemctl", "--user", "is-active", unit.replace(".service", ""))
        rows.append((label, u.get("port", "?"), u.get("mutator", "?"),
                     ",".join(u.get("features") or []) or "-",
                     "yes" if u.get("peers") else "no",
                     p.get("encoding", "?"), active or "?"))
        details.append((label, tree_name, branch, head, bool(dirty), u, p, changed))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"# The Grid — colony guide\n",
           f"_Generated {now} from the unit files and each colony's own code. "
           f"Do not edit by hand; run `build_guide.py`._\n",
           "## At a glance\n",
           "| colony | port | mutator | features | recolonises | encoding | service |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")

    out.append("\n## Why comparisons between these are hard\n")
    peered = [r[0] for r in rows if r[4] == "yes"]
    solo = [r[0] for r in rows if r[4] == "no"]
    out.append(f"Colonies **{', '.join(peered) or 'none'}** recolonise from peers when they go "
               f"extinct, so an epoch there can begin with genomes that already evolved "
               f"elsewhere. Colonies **{', '.join(solo) or 'none'}** always restart from the "
               f"ancestral founder palette. Composition and complexity figures are therefore "
               f"not comparable across that line without first separating ancestor-seeded "
               f"epochs from recolonised ones — an epoch's early average genome length "
               f"identifies which it was.\n")
    out.append("The world itself does reset every epoch: `_new_colony` builds a fresh "
               "`SubstrateWorld`, so the code commons, macro slots, shared bus and reclaim "
               "pool all start empty. Only the population can carry over.\n")

    # The map is not four equal quarters, and every number below is measured by
    # running the colony's own code rather than read off the literals in
    # world.py. A frozen 1.8x climate multiplier hid here for weeks precisely
    # because this guide reported the scalar tile_regen and nothing else.
    q = next((d[6].get("quadrants") for d in details if d[6].get("quadrants")), None)
    if q:
        out.append("\n## What each quadrant is worth\n")
        out.append("`biome(x, y) = (x >= w/2) + 2*(y >= h/2)`, so NW is the top-left of "
                   "the map as drawn and SE the bottom-right. Measured by stepping a real "
                   "world, not transcribed:\n")
        out.append("| | NW forage | NE nomad | SW engineer | SE information |")
        out.append("|---|---|---|---|---|")
        out.append("| regeneration per step | " + " | ".join(str(v) for v in q["regen_per_step"]) + " |")
        out.append("| energy per harvest | " + " | ".join(str(v) for v in q["harvest_per_call"]) + " |")
        for name, vals in q["instruction_cost"].items():
            out.append(f"| `{name.lower()}` cost | " + " | ".join(f"{v}x" for v in vals) + " |")
        out.append("| task reward | " + " | ".join(f"{v}x" for v in q["task_reward"]) + " |")
        best = q["order"][max(range(4), key=lambda i: q["regen_per_step"][i])]
        worst = q["order"][min(range(4), key=lambda i: q["regen_per_step"][i])]
        spread = (max(q["regen_per_step"]) / min(q["regen_per_step"])
                  if min(q["regen_per_step"]) > 0 else float("inf"))
        out.append(f"\n**{best}** regenerates fastest and **{worst}** slowest, a "
                   f"{spread:.1f}x spread. A population concentrated in one quadrant is "
                   f"the map being obeyed, not a behaviour to explain — check this table "
                   f"before reaching for any other reason.\n")

    for label, tree_name, branch, head, dirty, u, p, changed in details:
        out.append(f"\n## Colony {label}\n")
        if p.get("missing") or u.get("missing"):
            out.append("_tree or unit file missing_\n")
            continue
        if p.get("error"):
            out.append(f"_probe failed: {p['error']}_\n")
            continue
        out.append(f"- **tree** `~/odin/{tree_name}` on `{branch}` at `{head}`"
                   + (" — **uncommitted changes present**" if dirty else ""))
        out.append(f"- **port** {u['port']} · **state** `{u['state']}` · "
                   f"**memory ceiling** {u['memory_max']} · **{u['ticks_per_second']} ticks/s**")
        out.append(f"- **mutator** `{u['mutator']}`"
                   + (" — routes ~5% of births through the local model via the operator "
                      "service; falls back to random if nothing answers the queue"
                      if u["mutator"] == "odin" else " — blind variation only"))
        out.append(f"- **features** {', '.join(u['features']) or 'none'}")
        if p.get("feature_ops"):
            for feat in u["features"]:
                if feat in p["feature_ops"]:
                    out.append(f"    - `{feat}` enables {', '.join(p['feature_ops'][feat])}")
            inert = [o for f, ops in p["feature_ops"].items() if f not in u["features"]
                     for o in ops]
            if inert:
                out.append(f"    - inert here (execute as nop): {', '.join(inert)}")
        out.append(f"- **recolonisation** {'from ' + str(len(u['peers'])) + ' peers' if u['peers'] else 'disabled — always reseeds from ancestors'}")
        out.append(f"- **encoding** {p['encoding']}, {p['registers']} registers, "
                   f"{p['num_ops']} opcodes, ancestor {p['ancestor_len']} instructions, "
                   f"founder palette {p['palette']}")
        out.append(f"- **economy** child costs {p['child_energy']} energy (taken from the "
                   f"parent), salvage is {p['salvage']}, "
                   f"tile income {'coupled to host spare CPU' if p['has_cpu_income'] else 'not coupled to the host'}, "
                   f"grazing subsidy withdrawn over {p['subsidy_ticks']:,} ticks"
                   if p.get("subsidy_ticks") else "- **economy** (unknown)")
        out.append(f"- **commons** {'slots are held while called' if p['commons_hold'] else 'publish overwrites unconditionally'}"
                   f" · max group {p['max_group']} · max age {p['max_age']}")
        if changed:
            out.append(f"- **source differs from {REFERENCE}** in: {', '.join(changed)}")
        else:
            out.append(f"- **source identical to {REFERENCE}**")
        base = probe(HOME / "odin" / REFERENCE).get("costs", {}) if tree_name != REFERENCE else {}
        if base:
            diffs = {k: (base[k], v) for k, v in p["costs"].items()
                     if k in base and abs(base[k] - v) > 1e-9}
            if diffs:
                out.append("- **instruction costs changed from the reference:** "
                           + ", ".join(f"`{k}` {a} → {b}" for k, (a, b) in diffs.items()))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/etl/odin/thegrid-guide/GUIDE.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build())
    print(f"wrote {target}")
