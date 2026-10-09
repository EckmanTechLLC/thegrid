"""The organism's senses and hands. File-based, settled by the daemon.

An organism process imports this, reads the world through context(), and
queues actions. Everything is advisory until the daemon settles it after
the process exits; lying in an action just wastes the round.
"""
import json
import os
from pathlib import Path

_IO = Path(os.environ.get("GRID_IO", "../io"))
_ACTIONS = _IO / "actions.jsonl"
_ctx = None


def context() -> dict:
    """balance, round, oid, jobs[], market[], my_goods{}, inbox[]."""
    global _ctx
    if _ctx is None:
        _ctx = json.loads((_IO / "context.json").read_text())
    return _ctx


def _act(kind: str, **kw) -> None:
    kw["act"] = kind
    with open(_ACTIONS, "a") as f:
        f.write(json.dumps(kw) + "\n")


def submit(jid: int, result_path: str) -> None:
    """Enter a result for a posted job. First VERIFIED submission wins."""
    _act("submit", jid=int(jid), path=str(result_path))


def publish(name: str, path: str, price: int) -> None:
    """Offer a file on the market. Buyers pay `price` per fetch; you pay
    storage rent every round it stays listed."""
    _act("publish", name=str(name)[:48], path=str(path), price=int(price))


def unpublish(name: str) -> None:
    _act("unpublish", name=str(name)[:48])


def fetch(seller: int, name: str) -> None:
    """Buy a good. Fee leaves your balance now; the file lands in inbox/
    next round."""
    _act("fetch", seller=int(seller), name=str(name)[:48])


def spawn(source: str, grant: int) -> None:
    """Reproduce. You supply the child's source (usually your own, perhaps
    edited); the world may mutate it further. The grant leaves your balance;
    10% is burned as birth tax."""
    _act("spawn", source=str(source)[:65536], grant=int(grant))


def balance() -> int:
    return context()["balance"]


def jobs() -> list:
    return context()["jobs"]


def market() -> list:
    return context()["market"]
