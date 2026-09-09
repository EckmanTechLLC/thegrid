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
from .mutation import ExperimentalMutator


class OdinMutator:
    # Class defaults, not just instance state. A live colony restores its
    # mutator from a pickled checkpoint, so an instance written before these
    # fields existed unpickles without them and every attribute added here
    # after the fact would raise on first use. Colony one crash-looped on
    # exactly that - AttributeError: no attribute 'request_ttl' - the first
    # time it saw a pending request after the field was introduced. Declaring
    # them on the class makes an old checkpoint fall back rather than break.
    request_ttl = 600.0
    expired = 0

    def __init__(self, queue: Path, rate: float = 0.05, energy_cost: float = 40.0,
                 request_ttl: float = 600.0):
        self.queue = queue
        self.rate = rate
        self.energy_cost = energy_cost
        # An unanswered request used to block every future one: the request
        # was written only when absent and removed only when a proposal was
        # consumed, so one operator outage or one bad reply degraded this arm
        # to blind mutation for the rest of the epoch - silently, since the
        # fallback is a real mutation and nothing looked wrong.
        self.request_ttl = request_ttl
        self.expired = 0
        # The fallback must be the SAME operator the other arms run, or the
        # comparison measures mutation rate instead of who authored the
        # mutation. It was RandomMutator (point 0.008 / indel 0.02) against
        # ExperimentalMutator elsewhere (0.012 / 0.06 plus bursts, inversions,
        # duplications and block deletions) - roughly 3x the indel rate. That
        # difference, not the model, is why the Odin arms carried the larger
        # and steadier populations.
        self.base = ExperimentalMutator()
        if hasattr(self.base, "upgrade"):
            self.base.upgrade()
        self.calls = 0
        self.accepted = 0
        self.failures = 0
        self._pending_parent = None

    @property
    def last_events(self) -> list[str]:
        """Gene-scale events from the fallback mutator, which does the work.

        Colony.fork reads self.mutator.last_events. That attribute lives on the
        BASE mutator, not on this wrapper, so getattr returned [] and every
        insertion, deletion, burst, duplication and inversion in the two odin
        colonies went unrecorded for the life of the project - their
        mutation_origins tables show only point_substitution and
        segment_transfer, which are recorded elsewhere. The mutations were
        always happening; the fossil record simply never saw them.
        """
        return getattr(self.base, "last_events", [])

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
                # That request has had its answer, bad as it was. Retiring it
                # here means the next birth files a fresh one instead of
                # leaving the operator to guess whether to reply again.
                request.unlink(missing_ok=True)
        stale = False
        if request.exists():
            try:
                age = time.time() - float(json.loads(request.read_text())["created_at"])
                stale = age > self.request_ttl
            except (OSError, ValueError, KeyError, TypeError):
                stale = True          # an unreadable request wedges the queue too
            if stale:
                self.expired += 1
        if stale or not request.exists():
            names = [ISA[op].name for op in genome if 0 <= op < len(ISA)]
            payload = {
                "request_id": hashlib.sha256((str(time.time_ns()) + repr(names)).encode()).hexdigest()[:16],
                "created_at": time.time(), "parent": parent.telemetry(),
                "genome": names,
                "instruction_set": [{"name": item.name, "cost": item.cost, "effect": item.doc}
                                    for item in ISA],
                "ecology": {
                    "signal/listen": "ephemeral local communication",
                    "build": "costly persistent improvement of a resource patch",
                    "peek/copyn": "read or copy adjacent organisms' code; enables parasitism",
                    "climate": "quadrants differ in regeneration, harvest yield and "
                               "per-instruction cost, and those differences do not move",
                },
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
