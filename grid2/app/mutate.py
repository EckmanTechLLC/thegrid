"""Variation. Random text/AST surgery, horizontal splice, and - when the
local coder model answers - authored mutation. Selection never cares which
engine made a child; the broker pays for verified work and nothing else.
"""
from __future__ import annotations

import ast
import json
import os
import random
import re
import urllib.request

LLM_URL = os.environ.get("GRID2_LLM_URL", "")
LLM_P = float(os.environ.get("GRID2_LLM_P", "0.15"))
_llm_model: str | None = None

PROMPT = """You are a mutation operator in an artificial-life experiment.
Below is a small Python program (an organism). Produce a VARIANT of it:
keep it roughly the same size and intent, but change one behavior - a
constant, a strategy, an ordering, a threshold, or one new small trick.
It must stay valid Python using only the standard library and the `grid`
module it already uses. Reply with ONLY the complete program code, no
markdown fences, no commentary.

PROGRAM:
"""


def _llm_mutate(source: str, timeout: int = 45, context: str = "") -> str | None:
    global _llm_model
    try:
        if _llm_model is None:
            with urllib.request.urlopen(LLM_URL + "/v1/models", timeout=5) as r:
                _llm_model = json.load(r)["data"][0]["id"]
        body = json.dumps({
            "model": _llm_model,
            "messages": [{"role": "user", "content":
                (PROMPT + source
                 + ("\n\nSENSORY INPUT - what this organism perceives this "
                    "round (its world; you may use anything here):\n" + context
                    if context else ""))}],
            "max_tokens": 2048, "temperature": 0.9,
        }).encode()
        req = urllib.request.Request(
            LLM_URL + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.load(r)["choices"][0]["message"]["content"]
        text = re.sub(r"^```(python)?\s*|\s*```$", "", text.strip(),
                      flags=re.MULTILINE)
        return text if text.strip() else None
    except Exception:
        return None


def _splice(source: str, donor: str) -> str:
    """Horizontal transfer: graft one of the donor's functions in."""
    try:
        tree = ast.parse(donor)
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        if not funcs:
            return source
        graft = ast.unparse(random.choice(funcs))
        lines = source.splitlines()
        at = random.randrange(len(lines) + 1)
        return "\n".join(lines[:at] + ["", graft, ""] + lines[at:])
    except Exception:
        return source


def _text_ops(source: str) -> str:
    lines = source.splitlines()
    if not lines:
        return source
    op = random.random()
    i = random.randrange(len(lines))
    if op < 0.30 and len(lines) > 4:              # delete a line
        del lines[i]
    elif op < 0.55:                               # duplicate a line
        lines.insert(i, lines[i])
    elif op < 0.75 and len(lines) > 2:            # swap adjacent lines
        j = min(i + 1, len(lines) - 1)
        lines[i], lines[j] = lines[j], lines[i]
    else:                                         # perturb a number
        def bump(m):
            v = int(m.group())
            return str(max(0, v + random.choice(
                (-v // 2, -1, 1, v // 2, v)) )) if v else "1"
        order = list(range(len(lines)))
        random.shuffle(order)
        for k in order:
            new, n = re.subn(r"\d+", bump, lines[k], count=1)
            if n:
                lines[k] = new
                break
    return "\n".join(lines)


def mutate(source: str, donors: list[str], rng: random.Random) -> tuple[str, str]:
    """Return (child_source, author). Compile-validated; falls back to the
    parent's own source if nothing valid emerges (a clean copy, not a crash).
    """
    for _ in range(4):
        author = "ast"
        if LLM_URL and rng.random() < LLM_P:
            candidate = _llm_mutate(source)
            author = "llm"
            if candidate is None:
                candidate, author = _text_ops(source), "ast"
        elif donors and rng.random() < 0.20:
            candidate, author = _splice(source, rng.choice(donors)), "hgt"
        else:
            candidate = _text_ops(source)
        try:
            compile(candidate, "<child>", "exec")
            return candidate, author
        except SyntaxError:
            continue
    return source, "copy"
