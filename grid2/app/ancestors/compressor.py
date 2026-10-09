# Ancestor: compression specialist. Works only compress jobs, tries harder
# (lzma beats gzip on ratio; the reward pays for saved bytes).
import gzip
import lzma
from pathlib import Path

import grid

ctx = grid.context()
SPAWN_AT = 26000
GRANT = 8000

mine = [j for j in ctx["jobs"] if j["type"] == "compress"]
mine.sort(key=lambda j: -j["kb"])
for n, job in enumerate(mine[:2]):
    try:
        data = Path(job["input"]).read_bytes()
        small = lzma.compress(data, preset=6)
        alt = gzip.compress(data, 9)
        if len(alt) < len(small):
            small = alt
        out = Path(f"result{n}.bin")
        out.write_bytes(small)
        grid.submit(job["jid"], str(out))
    except Exception:
        pass

if ctx["balance"] > SPAWN_AT:
    grid.spawn(Path("../source.py").read_text(), GRANT)
