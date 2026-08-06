"""Where variation comes from.

The central design commitment: the LLM is never in the tick loop. It is not the
organism's mind. It fires only at reproduction, as a *mutation operator* —
reading a parent's source and telemetry and proposing a variant. Selection then
happens in the substrate, where the OS decides who starves. This is the
FunSearch / AlphaEvolve arrangement: an informed proposal distribution feeding a
search whose fitness signal is real.

Cost amortises to (at most) one call per birth instead of one per thought, and
because calls are paid for out of the organism's own energy, thinking is itself
under selection pressure. A lineage that squanders calls dies.

Two operators are provided:

  RandomMutator — point mutations during copy, indels at birth. The baseline.
                  Cheap, blind, and the control condition for any claim that
                  LLM guidance helps.

  LLMMutator    — wraps a base mutator; for a small fraction of births (and
                  only when the parent can pay the metabolic cost of a call)
                  asks a model for a variant instead. Falls back to the base
                  operator on any error, so the colony never stalls on a
                  network problem.
"""

from __future__ import annotations

import json
import os
import random
from typing import Protocol

from .isa import ISA, NUM_OPS, NAME_TO_OP, disassemble

LLM_CALL_ENERGY_COST = 40.0     # what it costs an organism to think


class Mutator(Protocol):
    def copy_error(self, word: int, rng: random.Random) -> int: ...
    def mutate_at_birth(self, genome: list[int], rng: random.Random) -> list[int]: ...


class RandomMutator:
    """Blind variation. The control condition."""

    def __init__(self, point_rate: float = 0.008, indel_rate: float = 0.02):
        self.point_rate = point_rate
        self.indel_rate = indel_rate

    def copy_error(self, word: int, rng: random.Random) -> int:
        if rng.random() < self.point_rate:
            return rng.randrange(NUM_OPS)
        return word

    def mutate_at_birth(self, genome: list[int], rng: random.Random) -> list[int]:
        if rng.random() < self.indel_rate and genome:
            if rng.random() < 0.5:
                genome.insert(rng.randrange(len(genome) + 1), rng.randrange(NUM_OPS))
            else:
                del genome[rng.randrange(len(genome))]
        return genome


class LLMMutator:
    """LLM-guided variation, priced in energy and used sparingly.

    `call_fn` takes a prompt string and returns the model's raw text. It is
    injected rather than hardcoded so this runs against Ollama, an API, or a
    recorded fixture without changing the colony.
    """

    def __init__(self, base: Mutator, call_fn=None, rate: float = 0.05,
                 energy_cost: float = LLM_CALL_ENERGY_COST):
        self.base = base
        self.call_fn = call_fn
        self.rate = rate
        self.energy_cost = energy_cost
        self.calls = 0
        self.accepted = 0
        self.failures = 0
        self._pending_parent = None

    def copy_error(self, word: int, rng: random.Random) -> int:
        return self.base.copy_error(word, rng)

    def offer(self, parent) -> None:
        """Colony calls this just before a birth so the operator can see the parent."""
        self._pending_parent = parent

    def mutate_at_birth(self, genome: list[int], rng: random.Random) -> list[int]:
        parent = self._pending_parent
        self._pending_parent = None

        eligible = (
            self.call_fn is not None
            and parent is not None
            and rng.random() < self.rate
            and parent.energy >= self.energy_cost
        )
        if not eligible:
            return self.base.mutate_at_birth(genome, rng)

        parent.energy -= self.energy_cost      # thinking is metabolically real
        self.calls += 1
        try:
            proposal = self._propose(parent, genome)
        except Exception:
            self.failures += 1
            return self.base.mutate_at_birth(genome, rng)

        if proposal is None:
            self.failures += 1
            return self.base.mutate_at_birth(genome, rng)

        self.accepted += 1
        return proposal

    def _propose(self, parent, genome: list[int]) -> list[int] | None:
        raw = self.call_fn(build_prompt(parent, genome))
        return parse_genome(raw)


# ── prompt construction ───────────────────────────────────────────────────

def isa_reference() -> str:
    return "\n".join(f"  {ins.name:<10} cost {ins.cost:>4}  {ins.doc}" for ins in ISA)


def build_prompt(parent, genome: list[int]) -> str:
    """What the model sees. Source plus lived outcome — never a fitness score.

    Withholding an explicit fitness number is deliberate: the model should
    reason about mechanism (what this organism actually did and failed to do),
    not optimise a scalar it can game.
    """
    telemetry = json.dumps(parent.telemetry(), indent=2)
    return f"""You are a mutation operator in an artificial life system. You propose variants
of self-replicating programs. Selection is real: this program competes for finite
CPU time, RAM, and energy against other programs, and dies when it cannot pay.

INSTRUCTION SET
{isa_reference()}

PHYSICS
- One instruction executes per tick. Every instruction costs energy.
- Energy comes only from `harvest` on the current tile. Tiles deplete and regenerate.
- `alloc` claims RAM for a child; it fails when the colony is out of memory.
- Replication requires: alloc, then copy until the buffer is full, then fork.
- The instruction pointer wraps at the end of the genome.
- `jmpb` jumps back (register C mod 8) + 1.
- The environment pays energy bonuses for logic tasks: read values with `input`,
  compute with `nand`, submit with `output`. Harder tasks pay more.

PARENT GENOME
{disassemble(genome, annotate=False)}

HOW THIS LINEAGE ACTUALLY FARED
{telemetry}

Propose one variant. Change something specific and motivated by the telemetry
above — do not rewrite from scratch, and do not break the replication loop
unless you are deliberately trading it for something better.

Respond with ONLY a JSON array of instruction names, no prose, no code fences.
Example: ["harvest", "alloc", "copy", "ifnotdone", "jmpb", "fork"]"""


def parse_genome(raw: str) -> list[int] | None:
    """Parse a model response into a genome. Returns None if unusable."""
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        text = max(parts, key=len)
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        names = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(names, list) or not names:
        return None

    genome: list[int] = []
    for item in names:
        if not isinstance(item, str) or item not in NAME_TO_OP:
            return None
        genome.append(NAME_TO_OP[item])
    return genome


def fixture_caller():
    """A deterministic stand-in for a model, for testing the operator path.

    This is NOT a model and makes no pretence of being one. It splices known
    task machinery into a parent genome so the full pipeline — prompt, parse,
    memory reconciliation, birth, reward — can be exercised without a network
    call or an API key. Use it to verify plumbing and to sanity-check that the
    reward faucet actually pays out. Any claim about whether LLM guidance helps
    must come from a real model, not from this.
    """
    def call(prompt: str) -> str:
        body = prompt.split("PARENT GENOME\n")[1].split("\n\nHOW")[0]
        names = [line.split(": ", 1)[1].strip() for line in body.splitlines() if ": " in line]
        if not names:
            return "[]"
        # Splice a minimal input/nand/output unit in ahead of the copy loop.
        cut = names.index("alloc") + 1 if "alloc" in names else len(names)
        variant = names[:cut] + ["input", "swap", "input", "nand", "output"] + names[cut:]
        return json.dumps(variant)

    return call


def ollama_caller(model: str = "llama3.1", host: str = "http://localhost:11434"):
    """Build a call_fn backed by a local Ollama instance."""
    import httpx

    def call(prompt: str) -> str:
        response = httpx.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json().get("response", "")

    return call


def anthropic_caller(model: str = "claude-sonnet-4-6"):
    """Build a call_fn backed by the Anthropic API."""
    import httpx

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    def call(prompt: str) -> str:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        blocks = response.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    return call
