# The Grid — operating rules

The colonies live on **Odin, <odin-host>**, over SSH. Nothing here is on this
laptop except the git push credentials and this file.

`~/odin/thegrid-colony2/CLAUDE.md` on Odin says *"Always check the codebase —
read files, never rely on memory."* It has said that since 2026-08-19 and was
never once read, because CLAUDE.md loads from the working directory and the
working directory is here, not there. That is why this file exists.

## Read these before answering, not after being corrected

| instrument | what it answers | when |
|---|---|---|
| `~/odin/thegrid-tools/tools/guide/GUIDE.md` | how each colony differs, and **what every `/api/state` field contains** | before any question about a colony, and after any code change (regenerate first) |
| `~/odin/thegrid-tools/tools/analyse/deep_dive.py` | motifs, mutation mechanisms, group separation | before turning any number into a claim |
| the fossil records in `~/.local/state/thegrid-*/history.sqlite3` | the actual time series | any question about a trend |

`/api/state` is a snapshot of **now**. It is not history. Five tables of real
time series sit in SQLite and went unqueried for a week while conclusions were
drawn from live snapshots.

## Traps that have already cost real time

- **`tasks` is `colony.task_firsts`** — a task mapped to the TICK IT WAS FIRST
  SOLVED AT. `{'not': 83954}` means first solved at tick 83,954, not 83,954
  times. Four days of reported task counts were timestamps. The fleet page
  renders `len(tasks)` and was right the whole time.
- **Never report from one colony.** Every real finding this project has came
  from a replicate-group comparison; the bus-ratio and netlist-encoding
  "findings" were n=1 and both died on contact with replicates.
- **Anything added to a pickled object needs a class-level default.** Colonies
  restore mutators and organisms from checkpoints; a field set only in
  `__init__` is absent on an existing one. This crash-looped colony one, then
  colony five, then all 24.
- **The trees are not interchangeable.** Colony 3 runs the old economy, colony
  8 packs `(op, src, dst)` and needs its own `genome_id`. Copying a file
  fleet-wide clobbered it. Diff before copying.
- **Verify the thing that has to work, not the thing beside it.** "systemd says
  active" is not "it works"; a colony passed both checks and died an hour later.
  For `fleet.html`, extract the `<script>` and `node --check` it.

## Standing instructions from Matt

- Live data only. Never answer from memory or a saved file.
- Only Matt authorises a reseed. Natural extinction reseeds on its own.
- Be concise. Detail on request.
- The Grid is an **electronic/program system** with evolutionary principles
  applied — Tron and Black Mirror, not biology. Test any mechanism with "is
  this how a computer system does it?"
- It is for fun. Breaking rules to see what happens is the point.
