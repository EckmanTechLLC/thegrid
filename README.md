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
