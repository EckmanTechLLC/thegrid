"""Asynchronous mutation bridge: the Odin agent authors proposals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path

from .isa import ISA, NAME_TO_OP
from .mutation import RandomMutator


class OdinMutator:
    def __init__(self, queue: Path, rate: float = 0.05, energy_cost: float = 40.0):
        self.queue = queue
        self.rate = rate
        self.energy_cost = energy_cost
        self.base = RandomMutator()
        self.calls = 0
        self.accepted = 0
        self.failures = 0
        self._pending_parent = None

    def copy_error(self, word: int, rng: random.Random) -> int:
        return self.base.copy_error(word, rng)

    def offer(self, parent) -> None:
        self._pending_parent = parent

    def _paths(self) -> tuple[Path, Path]:
        return self.queue / "request.json", self.queue / "proposal.json"

    def mutate_at_birth(self, genome: list[int], rng: random.Random) -> list[int]:
        parent = self._pending_parent
        self._pending_parent = None
        if parent is None or rng.random() >= self.rate or parent.energy < self.energy_cost:
            return self.base.mutate_at_birth(genome, rng)
        self.queue.mkdir(parents=True, exist_ok=True)
        request, proposal = self._paths()
        if proposal.exists():
            try:
                data = json.loads(proposal.read_text())
                names = data["genome"]
                variant = [NAME_TO_OP[name] for name in names]
                if not variant:
                    raise ValueError("empty proposal")
                proposal.unlink()
                request.unlink(missing_ok=True)
                parent.energy -= self.energy_cost
                self.calls += 1
                self.accepted += 1
                return variant
            except Exception:
                self.failures += 1
                proposal.rename(proposal.with_suffix(f".rejected-{int(time.time())}.json"))
        if not request.exists():
            names = [ISA[op].name for op in genome if 0 <= op < len(ISA)]
            payload = {
                "request_id": hashlib.sha256((str(time.time_ns()) + repr(names)).encode()).hexdigest()[:16],
                "created_at": time.time(), "parent": parent.telemetry(),
                "genome": names,
                "instruction_set": [item.name for item in ISA],
                "directive": "Odin must author one motivated variant; preserve viable replication.",
            }
            temporary = request.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2))
            os.replace(temporary, request)
        return self.base.mutate_at_birth(genome, rng)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or submit Odin mutation work.")
    parser.add_argument("--queue", type=Path,
                        default=Path.home() / ".local/state/thegrid/operator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    submit = sub.add_parser("submit")
    submit.add_argument("genome", help="JSON array of instruction names")
    submit.add_argument("--reason", required=True)
    args = parser.parse_args()
    request = args.queue / "request.json"
    proposal = args.queue / "proposal.json"
    if args.command == "inspect":
        print(request.read_text() if request.exists() else json.dumps({"pending": False}))
        return
    names = json.loads(args.genome)
    if not isinstance(names, list) or not names or any(name not in NAME_TO_OP for name in names):
        raise SystemExit("invalid genome")
    args.queue.mkdir(parents=True, exist_ok=True)
    proposal.write_text(json.dumps({"genome": names, "reason": args.reason,
                                    "authored_by": "Odin", "created_at": time.time()}, indent=2))
    print(f"submitted {len(names)} instructions")


if __name__ == "__main__":
    main()
