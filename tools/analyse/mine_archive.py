"""Work out which intervention snapshots are independent history.

Most are point-in-time copies of the same colony, so summing them would count
the same epochs several times. A snapshot whose genome ids are a subset of
another's is superseded; only the maximal ones carry information the others do
not.
"""
import sqlite3
from pathlib import Path

root = Path.home() / ".local/state/thegrid-interventions"
snaps = []
for f in sorted(root.rglob("*.sqlite3")):
    try:
        con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        n_ep, lo, hi = con.execute(
            "select count(*), min(epoch), max(epoch) from epochs").fetchone()
        ids = {r[0] for r in con.execute("select genome_id from genomes")}
        con.close()
    except Exception:
        continue
    if not ids:
        continue
    snaps.append({"path": f, "name": str(f.relative_to(root)), "epochs": n_ep,
                  "lo": lo, "hi": hi, "ids": ids})

snaps.sort(key=lambda s: -len(s["ids"]))
maximal = []
for s in snaps:
    covered_by = next((m for m in maximal if s["ids"] <= m["ids"]), None)
    if covered_by:
        s["superseded_by"] = covered_by["name"]
    else:
        maximal.append(s)

print(f"{len(snaps)} readable snapshots; {len(maximal)} are NOT a subset of another\n")
print(f"  {'snapshot':<58}{'epochs':>7}{'genomes':>10}  status")
for s in snaps:
    status = "superseded by " + s["superseded_by"].split("/")[0] if "superseded_by" in s else "INDEPENDENT"
    print(f"  {s['name'][:56]:<58}{s['epochs']:>7}{len(s['ids']):>10,}  {status}")

union = set()
for m in maximal:
    union |= m["ids"]
print(f"\n  distinct genomes across the independent snapshots: {len(union):,}")
Path("/tmp/maximal.txt").write_text("\n".join(str(m["path"]) for m in maximal))
