# Ancestor: librarian. Indexes text, and PUBLISHES its indexes on the
# market - betting that someone, someday, will pay to not recompute them.
import json
from collections import Counter
from pathlib import Path

import grid

ctx = grid.context()
SPAWN_AT = 28000
GRANT = 8500

mine = [j for j in ctx["jobs"] if j["type"] in ("index", "sort")]
for n, job in enumerate(mine[:2]):
    try:
        data = Path(job["input"]).read_bytes().decode("utf-8", "replace")
        out = Path(f"result{n}.bin")
        if job["type"] == "index":
            idx = json.dumps(Counter(data.lower().split()))
            out.write_text(idx)
            good = Path(f"good{n}.json")
            good.write_text(idx)
            grid.publish(f"idx-{job['jid']}", str(good), price=15)
        else:
            out.write_text("\n".join(sorted(data.splitlines())))
        grid.submit(job["jid"], str(out))
    except Exception:
        pass

# prune stale listings so rent does not bleed us out
for name in list(ctx["my_goods"])[8:]:
    grid.unpublish(name)

if ctx["balance"] > SPAWN_AT:
    grid.spawn(Path("../source.py").read_text(), GRANT)
