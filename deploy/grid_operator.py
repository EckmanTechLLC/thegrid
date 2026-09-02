#!/usr/bin/env python3
"""Answer The Grid's mutation requests using Odin's local coder model.

OdinMutator writes operator/request.json when an organism reproduces and it
wants an authored variant instead of a random one. Nothing was servicing that
queue, so every Odin-arm birth silently fell back to the random operator and
the "LLM mutator" arms were never LLM-driven at all. This is that consumer.

Deliberately not opinionated: the prompt carries the request's own genome,
instruction set and directive, and asks for one variant. It does not tell the
model what a good organism is, what to optimise, or which opcodes matter. The
selection pressure lives in the world, not in here.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
import urllib.request
from pathlib import Path

# mutation.py already contains build_prompt and parse_genome, written for
# exactly this job. I duplicated both, worse: my prompt sent the genome and the
# instruction set and nothing else, while build_prompt also sends the parent's
# lived telemetry and DELIBERATELY withholds any fitness score so the model
# reasons about mechanism instead of optimising a scalar it can game. Use the
# real one. Loaded from the colony tree so there is a single definition.
COLONY_TREE = os.environ.get("GRID_COLONY_TREE", "/home/etl/odin/thegrid-colony7")
sys.path.insert(0, COLONY_TREE)
from src.colony.mutation import build_prompt, parse_genome   # noqa: E402
from src.colony.isa import ISA, NAME_TO_OP                   # noqa: E402

ENDPOINT = os.environ.get("GRID_MODEL", "http://127.0.0.1:8002/v1/chat/completions")
MODEL = os.environ.get("GRID_MODEL_NAME", "qwen3.6-coder")
QUEUES = [Path(p) for p in os.environ.get(
    "GRID_QUEUES",
    str(Path.home() / ".local/state/thegrid/operator") + ":" +
    str(Path.home() / ".local/state/thegrid-colony7/operator")).split(":")]
POLL = float(os.environ.get("GRID_POLL", "3"))
COOLDOWN = float(os.environ.get("GRID_COOLDOWN", "20"))
# Measured: this model spends ~2,600 completion tokens on a proposal, almost
# all of it reasoning, and returns EMPTY content if it is cut off first.
# At 1,400 every answer came back finish_reason=length and unusable.
# Qwen's /no_think directive does not suppress it on this build - tested.
MAX_TOKENS = int(os.environ.get("GRID_MAX_TOKENS", "4000"))
TEMPERATURE = float(os.environ.get("GRID_TEMPERATURE", "1.0"))
MAX_GENOME = 64

stats = {"served": 0, "rejected": 0, "errors": 0}


def log(message: str) -> None:
    print(f"[operator] {message}", flush=True)


def ask(request: dict) -> list[str] | None:
    genome = [NAME_TO_OP[n] for n in request.get("genome", []) if n in NAME_TO_OP]
    if not genome:
        return None
    # build_prompt only ever calls parent.telemetry(); the request already
    # carries exactly that dict, recorded at the moment of the birth.
    parent = types.SimpleNamespace(telemetry=lambda: request.get("parent", {}))
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": build_prompt(parent, genome)}],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as response:
        payload = json.load(response)
    choice = payload["choices"][0]
    text = (choice["message"].get("content") or "").strip()
    if not text:
        log(f"empty content, finish_reason={choice.get('finish_reason')}, "
            f"completion_tokens={payload.get('usage', {}).get('completion_tokens')}")
        return None
    words = parse_genome(text)          # the colony's own parser, not mine
    if not words or len(words) > MAX_GENOME:
        return None
    return [ISA[w].name for w in words]


def serve(queue: Path) -> bool:
    request_path, proposal_path = queue / "request.json", queue / "proposal.json"
    if proposal_path.exists() or not request_path.exists():
        return False
    try:
        request = json.loads(request_path.read_text())
    except (OSError, ValueError):
        return False
    try:
        names = ask(request)
    except Exception as exc:            # the colony survives an unanswered queue
        stats["errors"] += 1
        log(f"{queue.parent.name}: model error: {type(exc).__name__}: {exc}")
        return True
    if names is None:
        stats["rejected"] += 1
        log(f"{queue.parent.name}: unusable proposal discarded")
        return True
    temporary = proposal_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "request_id": request.get("request_id"),
        "authored_at": time.time(),
        "genome": names,
    }))
    temporary.replace(proposal_path)     # atomic: the colony never sees a partial file
    stats["served"] += 1
    log(f"{queue.parent.name}: {len(request.get('genome', []))} -> {len(names)} instructions"
        f"  (served {stats['served']} rejected {stats['rejected']} errors {stats['errors']})")
    return True


def main() -> None:
    log(f"model {MODEL} at {ENDPOINT}")
    log("queues: " + ", ".join(str(q) for q in QUEUES))
    while True:
        worked = False
        for queue in QUEUES:
            if queue.exists():
                worked = serve(queue) or worked
        # A proposal costs ~95s of GPU. Pause after one so the colonies, the
        # coder endpoint and anything else on this box are not starved by it.
        time.sleep(COOLDOWN if worked else POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
