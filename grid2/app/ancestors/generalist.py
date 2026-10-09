# Ancestor: generalist. Tries whatever job pays best, breeds past a cushion.
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import grid

ctx = grid.context()
SPAWN_AT = 30000
GRANT = 9000


def do(job):
    data = Path(job["input"]).read_bytes()
    out = Path("result.bin")
    if job["type"] == "compress":
        out.write_bytes(gzip.compress(data, 6))
    elif job["type"] == "checksum":
        out.write_bytes(hashlib.sha256(data).hexdigest().encode())
    elif job["type"] == "index":
        counts = Counter(data.decode("utf-8", "replace").lower().split())
        out.write_text(json.dumps(counts))
    elif job["type"] == "sort":
        lines = sorted(data.decode("utf-8", "replace").splitlines())
        out.write_text("\n".join(lines))
    else:
        return
    grid.submit(job["jid"], str(out))


best = sorted(ctx["jobs"], key=lambda j: -j["reward"])
for job in best[:2]:
    try:
        do(job)
    except Exception:
        pass

if ctx["balance"] > SPAWN_AT:
    grid.spawn(Path("../source.py").read_text(), GRANT)
