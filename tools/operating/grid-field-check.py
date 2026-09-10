#!/usr/bin/env python3
"""Interrupt a raw /api/state read with what the fields actually mean.

Written because the fleet page and its own tooltip both rendered `tasks`
correctly, and four days of wrong numbers came from bypassing them to curl the
raw JSON, where a field called `tasks` holding 83954 reads as a count and
nothing contradicts you.

PreToolUse hook: does not block, injects context. Reading raw state is often
the right thing; reading it without the data dictionary is not.
"""
import json, re, sys

try:
    event = json.load(sys.stdin)
except Exception:
    sys.exit(0)

command = (event.get("tool_input") or {}).get("command", "")
if not re.search(r"api/(state|fleet)", command):
    sys.exit(0)

notes = []
if "tasks" in command or "api/state" in command:
    notes.append(
        "`tasks` is colony.task_firsts: task -> THE TICK IT WAS FIRST SOLVED AT, "
        "not a count. {'not': 83954} = first solved at tick 83,954. "
        "Distinct tasks = len(tasks). Real solve counts: forecastsSolved, "
        "and per-organism tasks_solved."
    )
notes.append(
    "/api/state is a snapshot of NOW. For any trend, query "
    "~/.local/state/thegrid-*/history.sqlite3 (epochs, ecology_buckets, "
    "genome_stats, transitions, mutation_origins)."
)
notes.append(
    "Full field reference: the '/api/state field' table in "
    "~/odin/thegrid-tools/tools/guide/GUIDE.md. Never report from one colony "
    "when it has replicates."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": " ".join(notes),
    }
}))
