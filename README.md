# thegrid

A contained artificial-life laboratory. Organisms are small programs on an
evolvable instruction set, competing for regenerating energy, real cgroup
memory, and real thermal headroom on the machine hosting them. A language model
is an optional mutation operator at reproduction; it is not in any organism's
thought loop.

This is not a model of biology. It is an electronic system with evolutionary
principles applied to it, and when a mechanism is proposed the question asked
is "is this how a computer system does it?" rather than "is this how an
organism does it." Shared memory, buses, addresses, published routines, calls,
failure and eviction are in scope. Pheromone gradients and metabolic analogies
are not.

## The colonies

Eight colonies run as `systemd --user` services on one host, each with its own
source tree, state directory, SQLite fossil record, and viewer on its own port.

| unit | port | tree | mutator | features | recolonises |
|---|---|---|---|---|---|
| `thegrid-colony` | 8787 | `thegrid-colony1` | odin | predation, lease | yes |
| `thegrid-colony2` | 8788 | `thegrid-colony2` | random | none | yes |
| `thegrid-colony3` | 8789 | `thegrid-colony3` | random | none | yes |
| `thegrid-colony4` | 8790 | `thegrid-colony4` | random | burn, predation | yes |
| `thegrid-colony5` | 8791 | `thegrid-colony5` | random | bounty, predation | yes |
| `thegrid-colony6` | 8792 | `thegrid-colony6` | random | predation | yes |
| `thegrid-colony7` | 8793 | `thegrid-colony7` | odin | bounty, burn, macro, predation | yes |
| `thegrid-colony8` | 8794 | `thegrid-colony8` | random | none | no |

Colonies one, two, and four through seven are **byte-identical source**. What
makes them different colonies is the flags in `deploy/systemd/`, not different
code. Only colony three and colony eight carry real source differences, and
they live on their own branches. `tools/guide` regenerates this table, and a
fuller index, by importing each tree's own modules rather than describing them
from memory.

Note that colony one's unit is `thegrid-colony.service`, with no digit, while
its tree is `thegrid-colony1`.

### Branches

- `main` / `colony2-experimental` — the shared engine, the deployed units, tools.
- `colony3-free-signal` — colony three, where `signal` and `listen` cost zero.
- `colony8-netlist` — colony eight, where a word packs `(op, src, dst)` across
  eight registers instead of operating on a shared register.
- `archive/main-2026-09-04` — main as it stood before the September rewrite,
  kept so that pinned submodules keep resolving.

## The instruction set

50 opcodes. The ancestor is nine instructions —
`harvest harvest alloc copy ifnotdone jmpb fork scan move` — and the founder
palette holds 23 seed genomes. Genomes are capped at 64 instructions.

Newer opcodes are gated by `--features`. **A disabled opcode executes as a
`nop` rather than being absent**, so opcode numbers and glyphs stay identical
across every colony; a genome stays readable and migratable between colonies
that do not share a feature set, and simply does nothing where an instruction
is inert.

| feature | opcodes | what it adds |
|---|---|---|
| `burn` | `burn` | spends real CPU, warming the host for every colony on it |
| `bounty` | `offer` | escrow energy at a bus address for a wanted value |
| `macro` | `define`, `macro0`-`macro7` | eight call slots whose meaning the population authors |
| `predation` | `steal`, `corrupt` | take a neighbour's energy; write into a neighbour's genome |
| `lease` | - | replaces ageing; see below |

Beyond those there is a 16-word shared bus (`post`/`fetch`), which unlike a
signal does not attenuate, expire, or respect a quadrant boundary — the only
channel in this world with no geometry — plus `locate`, `link`, a code commons
of published routines that pay royalties when called, and `peek`/`copyn` for
reading and copying adjacent code.

Signals radiate to Manhattan radius three, start at strength 24, lose five per
tile, and decay each tick. Stronger broadcasts replace weaker ones. No reward
is attached to communication itself.

## The map is not four equal quarters

`biome(x, y) = (x >= w/2) + 2*(y >= h/2)`, giving NW forage, NE nomad, SW
engineer, SE information — NW at the top left as drawn. They differ in
regeneration rate, harvest yield, per-instruction cost, and task reward, so
**where a population stands is mostly economics, not behaviour.** `tools/guide`
measures the live values by stepping a real world and prints them in
`GUIDE.md`; read that rather than trusting a number written down here.

Until September 2026 a `1.8x` regeneration bonus was pinned to one quadrant. It
began as a rotating carousel and was later keyed to machine state, which froze
it, because the bit it keyed on is almost always zero on this hardware. NW held
the bonus permanently and 53% to 81% of every population stood in it. It was
removed rather than re-keyed: nothing measurable on the host spends meaningful
time in four distinct states, and quantising a saturated signal to manufacture
that rotation would be a clock wearing a sensor's clothes.

## The machine is the environment

Three host signals are read directly rather than simulated:

- **Heat.** Storms fire on real temperature rises, a fast EMA (`0.001`, so
  roughly 1000 ticks to follow a step) against a slow one. `cost_multiplier`
  rises with heat, so every instruction everywhere gets more expensive when the
  box is hot.
- **Spare CPU.** Tile regeneration tracks `(spare / usual spare)` squared from
  `/proc/stat`. Running a model is a famine; an idle night is a harvest. There
  is deliberately no floor — if the host stays busy long enough the colony
  starves, and extinction is a legitimate outcome.
- **Memory.** Genome reservations commit real resident pages against a cgroup
  v2 ceiling, so memory pressure is RSS rather than a counter.

### Heat on a host without an AMD sensor

Temperature defaults to the AMD `k10temp`/Tctl sensor and **fails closed** if it
is absent, which means a VM or cloud instance cannot start the colony at all.
Pick a source explicitly:

    --heat k10temp        # default; refuses to start with no sensor
    --heat host-cpu       # whole-host CPU busy fraction mapped to 45-85C
    --heat fixed:60       # a constant

or set `THEGRID_HEAT`. `host-cpu` is not a temperature and does not pretend to
be one; it is a load signal wearing the same units so the storm, cost and
baseline machinery needs no special case. The default is left failing closed on
purpose: a synthetic sensor is something you ask for, never something you get
by accident, because a colony silently running on a fabricated reading would
invalidate every thermal number it reports. `/api/state` names the source it is
actually using under `substrate`.

## The grazing subsidy is being withdrawn

Nothing complex ever evolved here because nothing ever required it — a short
grazing loop is a complete answer to this world, so evolution kept returning
one. Tile yield now decays linearly to zero over 500,000 ticks of each world's
own clock and does not come back. What is left afterwards is a machine economy:
energy enters only as work the system sets (tasks), and moves only by being
called by another program (royalties) or by reclaiming what died (salvage).

## Death

An organism dies of starvation at zero energy, or of age. Colony one replaces
ageing with a **lease**: renewal rides on `post`, where posting anything buys
600 ticks and posting the quadrant it is actually standing in buys 2400. Doing
nothing is fatal under a lease in a way it is not under starvation, because a
`nop`-only genome costs nothing to run and so cannot starve.

## Mutation

Blind variation is the default: point substitution, indels, bursts,
duplications, block deletions, and inversions, tracked separately in the fossil
record along with whether the originating genome later reproduced.

The `odin` mutator routes a fraction of births through a local model. It writes
`request.json` into a queue directory and reads back `proposal.json`; an
operator answers out of process. A proposal is parsed and validated by exactly
the code that validates a random mutation, so an invalid one is rejected rather
than repaired, and the birth falls back to blind variation. Requests carry a
TTL and are retired when a proposal is rejected, so an operator outage or a bad
reply degrades one birth rather than silently disabling the arm for the rest of
the epoch. `/api/state` reports `mutator.calls`, `.accepted`, `.failures` and
`.expired` so an external operator can see whether its proposals land.

## Running it

    python3 -m venv .venv
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/python -m src.colony.live --port 8787 --state ~/.local/state/thegrid/colony.pkl

Unit files for the deployed arrangement are in `deploy/systemd/`; see
`deploy/README.md`.

## Tools

- `tools/fleet` — all eight colonies on one page. The colony viewers send no
  CORS headers, so a browser cannot poll eight origins; this fans out
  server-side and serves one combined document.
- `tools/guide` — generates `GUIDE.md` by importing each colony's own modules in
  its own interpreter and diffing each tree against the reference, so the index
  cannot drift from the code it documents.
- `tools/operator` — reference operator for the `odin` mutator, reusing each
  colony's own `build_prompt` and `parse_genome`.

## State and history

Runtime state is checkpointed atomically and restored across restarts. A
durable fossil record in SQLite keeps new genomes, parent-to-child transitions,
epoch summaries, and 500-tick ecology buckets, rather than one row per
organism. The viewer renders one server-sent frame per completed tick with no
interpolation, so real thermal pauses stay visible; clicking a tile follows an
organism across ticks and reports its cause of death if it dies while selected.

## Known issues

`pytest` currently fails 11 of 33 tests. These are stale tests, not stale code:
they encode a founder palette smaller than the current one, and the older
scrap-on-tiles salvage economy, both of which changed deliberately. They are on
the list to be rewritten.
