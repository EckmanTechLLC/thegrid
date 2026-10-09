# Ancestor: scholar. Does cheap checksum work, and occasionally BUYS a
# good from the market - the first consumer, so trade exists at all.
import hashlib
from pathlib import Path

import grid

ctx = grid.context()
SPAWN_AT = 24000
GRANT = 7500

mine = [j for j in ctx["jobs"] if j["type"] == "checksum"]
for n, job in enumerate(mine[:3]):
    try:
        data = Path(job["input"]).read_bytes()
        out = Path(f"result{n}.bin")
        out.write_bytes(hashlib.sha256(data).hexdigest().encode())
        grid.submit(job["jid"], str(out))
    except Exception:
        pass

offers = sorted(ctx["market"], key=lambda g: g["price"])
if offers and ctx["balance"] > 5000 and ctx["round"] % 7 == 0:
    pick = offers[0]
    if pick["price"] <= 30:
        grid.fetch(pick["seller"], pick["name"])

if ctx["balance"] > SPAWN_AT:
    grid.spawn(Path("../source.py").read_text(), GRANT)
