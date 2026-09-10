# Operating rules

These two files are not part of the engine. They exist because the engine kept
being reported on incorrectly, and every instrument in `tools/` was built after
a mistake rather than before it.

- `CLAUDE.md` — copy this to the WORKING DIRECTORY of whatever machine drives
  the colonies, not into a colony tree. The repo has carried a CLAUDE.md since
  August saying "always check the codebase, read files, never rely on memory",
  and it went unread for three weeks because CLAUDE.md loads from the working
  directory and the working directory was on a different host, reached over
  SSH. The right instruction in the wrong filesystem is the same as no
  instruction.

- `grid-field-check.py` — a PreToolUse hook. Register it under
  `~/.claude/settings.json` with matcher `Bash`. It fires on any read of
  `/api/state` or `/api/fleet` and injects what the fields actually mean.
  It exists because `tasks` is `colony.task_firsts` - a task mapped to the tick
  it was FIRST SOLVED AT - and four days of reported task counts were
  timestamps. The fleet page rendered it correctly the entire time; the error
  came from bypassing the instrument to read raw JSON.

The hook is the only one of the three layers that cannot be skipped, forgotten,
or lost to a context compaction.
