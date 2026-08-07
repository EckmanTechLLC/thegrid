# thegrid

`thegrid` is a contained artificial-life laboratory. Organisms are tiny programs
that compete for regenerating energy, a hard shared memory budget, and thermal
headroom. The language model is an optional mutation operator at reproduction;
it is not placed in every organism's thought loop.

The repository also retains the original Phase 1 Aria/Flux prototype while the
colony observation layer is integrated with its useful infrastructure.

## Run the colony

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m src.colony.run --ticks 20000 --seed 42
.venv/bin/python -m src.colony.record --ticks 9000 --out run.html
```

## Live habitat

The persistent habitat runs continuously under the `thegrid-colony.service`
user service. Its LAN observer is available on port 8787. State is checkpointed
atomically to `~/.local/state/thegrid/colony.pkl` and restored after restarts.
The service has finite cgroup v2 CPU/RAM bounds; genome reservations commit real
resident pages, and thermal pressure is read from the AMD Tctl sensor. Mutation
requests are queued for Odin to author rather than sent to an API model.

The evolvable ISA also permits local signalling, listening, niche construction,
neighbour-genome inspection, and foreign-genome copying. Resource-rich climate
quadrants move over time, creating changing selection pressure. These mechanisms
permit cooperation, cheating, parasitism, defense, and ecological inheritance;
none of those outcomes is hard-coded.

For a foreground development run:

```bash
.venv/bin/python -m src.colony.live --host 0.0.0.0 --port 8787
```

Use `--mutator fixture` to test the informed-mutation plumbing deterministically.
The fixture is not evidence that an LLM improves evolution. Real model trials
must be compared against seeded blind-mutation controls.

## Safety boundary

The present substrate is accounted in software. It does not allocate arbitrary
host memory, control host scheduling, or read thermal sensors. Hardware-native
experiments will run inside explicit cgroup/container limits and remain off by
default.

## Provenance

The initial repository commit contains the earlier LLM-agent world. Materials
generated during an Anthropic Fable trial are preserved under
`artifacts/fable/` as unverified design input and recorded specimens. They are
not treated as ground truth.
