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

Twenty-two colonies run as `systemd --user` services on one host, each with its
own source tree, state directory, SQLite fossil record, and viewer on its own
port. A fleet page on :8799 discovers them from the unit files and shows them
together.

| colony | port | features | mutator | what it is for |
|---|---|---|---|---|
| `arena` | 8823 | predation, grazing | random | eight hand-designed specialists competing in one colony |
| `Colony Four` | 8790 | predation, eviction | random | no grazing; nothing starves, disuse is what kills |
| `eviction-1..4` | 8805-08 | predation, eviction | random | four replicates of it |
| `service1..2` | 8817-18 | predation, eviction, service | random | calls billed per call; income only from being called |
| `observe1..2` | 8819-20 | predation, observe | random | an organism can read a neighbour's telemetry |
| `Colony Five` | 8791 | bounty, predation, bitrot | random | bits flip in living genomes when the box runs hot |
| `bitrot-1..4` | 8809-12 | bounty, predation, bitrot | random | four replicates of it |
| `rot1..2` | 8821-22 | bitrot, bounty, predation | random | the same, at a rate that actually bites |
| `Colony Eight` | 8794 | none | random | packed `(op, src, dst)` encoding |
| `netlist-1, -3` | 8813, 8815 | none | random | two replicates of it |
| `Colony Seven` | 8793 | bounty, burn, macro, predation | odin | everything on, and the only colony with macros |
| `colony2` | 8788 | none | random | the long-running baseline, and the reference tree |

**Replicates matter more than variety.** Epoch-to-epoch variance inside a single
colony reaches 68x, so anything observed once is an anecdote. Three findings
drawn from single colonies died on contact with replicates. Groups peer only
within themselves; wiring them together would destroy the independence they
exist to provide.

Nine colonies were retired once their question was answered — the lease, free
signal/listen, a predation-only control, four baseline replicates. Their fossil
records are kept; only the unit file moved to `retired/`. See
`tools/analyse/RETIRED.md`.

### Branches

- `main` / `colony2-experimental` — the shared engine, deployed units, tools.
- `colony4-eviction` — no grazing; eviction instead of starvation.
- `colony5-bitrot` — bit rot keyed to the real thermal sensor.
- `colony3-free-signal` — the older economy, and `signal`/`listen` at zero cost.
- `colony8-netlist` — a word packs `(op, src, dst)` across eight registers.
- `colony-arena` — hand-designed specialists, a founding boom, a starvation grace.
- `colony-service` — calls billed per call rather than as a cut of the caller's gain.
- `colony-observe` — a new opcode at 50 that reads a neighbour's telemetry.
- `colony-rot` — bit rot cranked and capped.
- `archive/main-2026-09-04` — main before the September rewrite, kept so pinned
  submodules keep resolving.

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

## What the record is for

`tools/analyse/LESSONS.md` holds what has actually survived replication, and
`tools/analyse/deep_dive.py` regenerates the evidence. The short version: a
reward that is merely offered gets ignored — `forecast` has never been solved
above chance, free signalling changed nothing, an obligation with a 4x payoff
sat at chance across 935,000 samples. What changes behaviour is removing the
easy alternative. Take away cheap grazing and the same duplication machinery
that copied a foraging loop starts copying a task circuit instead.

## Tools

All three run out of a checkout of this repository at
`~/odin/thegrid-tools`, the same way every colony runs out of its own checkout.
There is one copy of each tool, it is the copy under version control, and
editing one is an ordinary commit. They previously lived in standalone
directories with snapshots pasted in here, and the snapshots drifted within a
day - a dashboard fix, a token-budget change and a JavaScript syntax fix were
all present in the running copy and absent from the published one.

The tools share a history with the engine deliberately. The guide imports each
colony's own modules, the fleet page uses the viewer's exact palette, and the
operator reuses the colonies' own `build_prompt` and `parse_genome`. They are
instruments for this codebase rather than independent projects, so versioning
them apart from it would be pretending to a separation that does not exist.

- `tools/fleet` — every colony on one page, discovered from the unit files. The colony viewers send no
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

### Exporting genomes

The fossil record is readable one genome at a time, unauthenticated, at an id
that does not move:

    GET /api/genomes/<genome_id>                 one record
    GET /api/genomes?since_epoch=27&limit=100    a page, oldest first; follow `next`
    GET /api/genomes/isa                         the opcode table the ids mean something against

`genome_id` is the first 16 hex digits of SHA-256 over the sequence as bytes,
one byte per instruction. It is a content hash, so it survives recolonisation
by construction and two colonies that evolve the same sequence share it. Each
record carries the sequence (`encoded`, the viewer's glyph string, and
`instructions`, the same words by name), `first_epoch`, `first_tick` and
`first_generation` where the sequence was first seen here, `parent_genome_id`,
the `mechanisms` on that first birth - the eight blind ones plus
`model_proposal` where an `odin` birth consumed an operator's proposal -
`model_proposed` as a plain yes, no, or `null` for rows older than the tag,
and the `isa_version`, `features` and `mutator` that were running when it was
first seen. The envelope names the `colony`, the `deployment` (`--deployment`
or `THEGRID_DEPLOYMENT`, defaulting to the hostname) and what the process runs
`live`, which a record's own fields may lawfully disagree with.

Nothing in a record ranks it. Births, ages, tiers and "hireable" are not there
on purpose: they would be this project asserting fitness, which is the claim it
keeps getting wrong. Whoever consumes the record applies their own rule.

A reader checks a record without trusting this server. Take the ISA from
`/api/genomes/isa`, map each name in `instructions` to its index, and
recompute:

    ops = [names.index(n) for n in record["instructions"]]
    sha256(bytes(ops)).hexdigest()[:16] == record["genome_id"]

and for the table itself, hash the encoding and the `[name, cost]` pairs in
order as compact JSON:

    body = json.dumps([[o["name"], o["cost"]] for o in table["opcodes"]], separators=(",", ":"))
    sha256(f"{table['encoding']}|{body}".encode()).hexdigest()[:12] == table["isaVersion"]

A mismatch on either means the record and the table it claims to belong to
are not the ones being served, and no field of the record should be read
until that is explained.

## License

MIT. See `LICENSE`.

## Tests

`pytest` passes 33/33 on every colony except colony eight, whose packed
`(op, src, dst)` encoding the shared test file does not yet speak - it builds
genomes as bare opcodes, so 8 tests there fail on the encoding rather than on
behaviour. Adapting them is outstanding work.
