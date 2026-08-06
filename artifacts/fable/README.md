# colony — substrate-native artificial life

The core for thegrid's second life. Entities are programs whose needs are not
simulated: they are the actual resources of the machine they run on. CPU time,
RAM, and thermal headroom. Nothing here is a hunger bar.

Drop this in as `src/colony/` alongside the existing `src/`.

## Run it

```bash
python -m colony.run --ticks 20000                    # blind mutation baseline
python -m colony.run --ticks 20000 --mutator llm --backend ollama --model llama3.1
```

## What it is

**`isa.py`** — 18 instructions. The genome is the program. Includes the
ancestor: a hand-written self-replicator, the only thing seeded. Every other
behaviour has to be found.

**`world.py`** — three scarcities, all global and all real to the organism:
patchy regenerating energy per tile; a hard colony-wide memory cap; and heat
that rises with total instruction throughput and multiplies everyone's costs
past a threshold. The heat is a genuine commons problem — no organism can
escape it alone.

**`organism.py`** — the VM and the metabolism. One instruction per tick per
organism; that round-robin slice *is* the CPU budget. Every instruction costs
energy at ISA prices scaled by current heat. Run out and you die, your RAM is
released, and something else gets the room.

**`tasks.py`** — the reward faucet, from Avida. The environment pays energy
bonuses for logic operations computed from environmental inputs, with `nand` as
the only primitive. This is what stops the system from converging on lean
self-copiers and halting, which was Tierra's ceiling. Harder tasks pay more.

**`mutation.py`** — where variation comes from. `RandomMutator` is the blind
baseline and control condition. `LLMMutator` is the real idea: **the model is
never in the tick loop.** It fires only at reproduction, reading the parent's
source and telemetry and proposing a variant. Selection still happens in the
substrate. Calls cost the parent energy, so thinking is metabolically real and
under selection pressure — a lineage that squanders calls dies.

**`colony.py`** — scheduler, lineage tracking, telemetry. Population is bounded
by the memory cap; there is no population constant anywhere.

## Watching it

```bash
python -m colony.record --ticks 9000 --out run.html                    # baseline
python -m colony.record --ticks 9000 --mutator fixture --out run.html  # with task solves
```

Writes a self-contained page. Motes are coloured by founding lineage, so a
strain sweeping the map is visible; the genome panel diffs the dominant genome
against the ancestor with a real LCS diff; the whole instrument picks up a red
cast while the colony is thermally throttling itself.

`--mutator fixture` is a deterministic test double, **not a model** — it splices
known task machinery so the reward path can be exercised without an API key.
Use `--mutator ollama` or `--mutator anthropic` for the real thing.

## Tuning notes

Two parameters were swept because the first guesses were wrong in ways that
hollowed out the design:

- **`tile_regen` 1.2 → 0.06.** At 1.2 the world regenerated far faster than the
  colony consumed, every tile sat at capacity, starvation stopped happening,
  and memory became the only binding constraint. At 0.06 starvation dominates
  deaths (1643 vs 36 senescence over 9k ticks) and generations reach 40 instead
  of 16. Energy is now genuinely scarce.
- **`heat_threshold` 40 → 22.** After the regen change, population settled near
  130 and heat equilibrated around 26 — the commons problem never engaged. At
  22 throttling fires in bursts and self-regulates: hot, costs rise, deaths,
  cools.

Both are worth re-sweeping after any change to costs or population, since they
are coupled.

## What the runs showed

Blind mutation, 15,000 ticks: the colony sustains, saturates the memory cap
(~290 organisms), reaches generation 25, and the dominant genome drifts —
instructions inserted, `scan` appearing, replication loop intact. Heat
throttling engages around tick 1,000 and settles near a 1.7x cost multiplier.
Deaths are starvation early, senescence later.

**Zero tasks solved in 15,000 ticks.** Blind mutation never assembles the
`input`/`nand`/`output` machinery. This is the finding that justifies the whole
LLM-operator design — that gap is precisely what an informed proposal
distribution is for.

With the operator on (fixture-driven), task solving establishes within ~200
ticks and spreads. More interesting: solutions the fixture never encoded (`orn`,
`not`, `xor`) appeared later via random drift *on top of* the LLM-seeded
machinery. LLM makes the discontinuous jump; blind mutation refines. That
interaction is the thing to watch for with a real model attached.

## Porting to the VM — what has to change

The interfaces are already shaped for it. Three swaps:

1. **Energy → real CPU time.** Replace the per-instruction accounting in
   `World.charge_instruction` with actual scheduler quota under a cgroup. The
   organism's slice becomes a real time slice.
2. **Memory → real RSS.** `World.request_memory` becomes a real allocation
   against a `memory.max` cgroup limit. Failure becomes a real allocation
   failure.
3. **Heat → real sensors.** `World.heat` reads from `/sys/class/thermal`
   instead of accumulating a counter. This one is worth doing early — it is the
   part of the design with no simulated equivalent.

Run the whole thing inside a container with a bounded slice of the host. Real
scarcity inside, no risk outside.

## Where it plugs into thegrid

The existing Flux client and frontend were always meant to be the observation
deck. Publish `Snapshot` to Flux each sample interval and the canvas becomes a
population/resource view rather than one agent walking around. The old
`src/agents/` LLM loop is superseded — that model is now the mutation operator
in `mutation.py`, not the mind.

## Open design questions

- **Reward schedule.** Task rewards are currently flat per organism. Avida
  found the shape of this schedule matters enormously — diminishing returns on
  repeated solves, or bonuses only while a task is rare, both change what
  evolves.
- **LLM call rate.** 5% of births is a guess. Too high and the substrate stops
  being the selector; too low and nothing jumps.
- **Parasitism.** There is currently no way to read another organism's genome.
  Adding one is what produced Tierra's most interesting dynamics, and it is a
  small ISA addition — but it changes the system's character substantially.
- **Ancestor dependence.** Everything descends from one hand-written
  replicator. Seeding several structurally different ancestors would test how
  much of the observed behaviour is an artifact of that one design.
