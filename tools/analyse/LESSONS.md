# What works

Toward a colony configured to survive and thrive. Only mechanisms that
produced a measured effect. Every number here was read from the live fleet or
the fossil records, and each is marked by how much weight it can carry.

**CONFIRMED** — replicated across four or more independent colonies.
**OBSERVED** — real and measured, but n=1 or unstable. Do not design on these alone.

---

## 1. CONFIRMED — Eviction keeps a colony alive; starvation does not

Remove death-by-hunger and death-by-age. Nothing starves and nothing ages out.
An organism persists by default and is reclaimed only when it has been useless
for a full lifespan, or when memory is wanted and it is the least recently
useful thing holding any.

```
                epochs   extinctions   deepest lineage
eviction             4             0            7,224
control             23            19              ~250
bitrot              78            74              ~340
netlist             70            66              549
```

Zero extinctions in 48 hours across five colonies while the rest of the fleet
burned 159 epochs between them. Generation **7,224** against a project-wide
previous best in the hundreds.

**Design rule:** make existence free and *reclamation* the only death. A
program does not get hungry; it runs until something needs the room.

## 2. CONFIRMED — Populations duplicate whatever pays. Choose what pays.

Tandem duplication of the earning motif happens in every colony. What differs
is only the target, and the target is set by the economy:

```
grazing colonies     scan+move+harvest x2-4      harvest+scan+move+harvest x3
netlist              copy+ifnotdone+jmpb x2      (the replication loop)
eviction             input+swap+input+nand+output x2-3   (the task circuit)
```

One copy of the task circuit was seeded. Selection produced two and three, and
one colony duplicated its `publish` alongside it.

**Design rule:** you do not make complexity required, you make it the thing
that earns. The duplication machinery already exists and will point wherever
income is.

## 3. CONFIRMED — Take away the cheap income and inheritance goes sideways

With grazing removed, horizontally acquired code (`copyn`, recorded as
`segment_transfer`) does not merely appear — it takes over.

```
                % of new genomes    % of the births they produced   enrichment
eviction              27.9%                    58.2%                  2.09x
bitrot                 5.6%                     6.4%                  1.15x
netlist                1.1%                     1.4%                  1.24x
control                1.7%                     1.6%                  0.96x
```

Stable at 2.0–2.2x for three consecutive days, while the volume climbed from
2.4% to 27.9%. **More than half of all reproduction is now a copy of a
neighbour's working block**, not a copy of a parent.

**Design rule:** give organisms a way to read and copy each other, then make
inventing from scratch expensive. Acquisition becomes the dominant mode.

## 4. CONFIRMED — Predation follows the currency

Where energy gates survival, predation is theft. Where it does not, predation
becomes sabotage.

```
                steals    corrupt   corrupt/steal
eviction        58,667    153,004       2.61x
singleton       80,077      6,859       0.09x
bitrot         348,363      8,711       0.03x
```

An ~80x swing in the ratio. In the eviction colonies energy buys nothing, so
taking it is pointless — but destroying a rival's genome frees the one thing
that is actually scarce, which is resident memory.

**Design rule:** whatever you make scarce determines how organisms attack each
other. This is a dial, not an accident.

## 5. CONFIRMED — Replication is what makes any of this knowable

Epoch-to-epoch variance inside one colony reaches **68x**. Four replicates per
configuration, each with its own tree, state and port, peered only within their
own group.

Three findings drawn from single colonies died on contact with replicates: a
bus read/write ratio that looked like an encoding property, a composition
advantage for the packed encoding, and a quadrant-occupancy result that was
stable for a day and gone the next. One finding survived and is item 3 above.

**Design rule:** never run one of anything you intend to learn from.

## 6. CONFIRMED — Real hardware makes a real environment

The machine is not simulated. Instruction cost rises with the actual AMD Tctl
reading; tile regeneration tracks spare CPU from `/proc/stat`; genome
reservations commit real pages against a cgroup ceiling; and in the bit-rot
colonies a bit in a living genome flips when the box runs above its own
trailing thermal baseline — 20,588 flips and counting, zero when cool.

Colony count is cheap (24 colonies ≈ 4% of the box). Tick rate is the expensive
dial, and raising it starves every colony at once until the CPU baseline
re-adapts.

**Design rule:** couple to something physically real and the environment
acquires texture nothing hand-written would have.

---

## Observed, worth building on, not yet proven

- **Explicit operands may be what makes a call graph possible.** The packed
  `(op, src, dst)` encoding lets `fetch` and `call` name a destination register
  instead of clobbering a shared one. Royalties appear there and barely
  anywhere else — but the figure swings by an order of magnitude across a day,
  so treat it as a lead.
- **Bit rot and wide task repertoires travel together.** The bit-rot colonies
  reach six of seven tasks and carry the fleet's highest complexity. Redundancy
  is exactly what an unreliable substrate should select for, and this is the
  right shape — but those colonies also run bounty and predation, so the cause
  is not isolated.
- **Model-authored mutation works, given room to answer.** A hybrid-reasoning
  model needs budget for *both* the reasoning and the answer; starved of it, it
  returns nothing. With room: 386 served, 4 rejected, 0 errors in a day. Its
  proposals are motivated — one stripped `signal` from a genome after its own
  telemetry showed 61 sent and 0 heard.
- **Withdraw an income slowly rather than cutting it.** Draining the tile at
  full rate while paying a shrinking fraction produces a gradient instead of a
  cliff, and the population re-specialises as it falls rather than dying all at
  once.

---

## For the colony built to thrive

Nothing here is a guess about what would work; each line is one of the
confirmed items above, turned around.

1. **No starvation, no senescence.** Eviction only, on disuse and on memory
   pressure. Memory-pressure eviction must not exempt newborns, or births
   outrun reclamation.
2. **Make being useful to another organism the only way to reproduce.**
3. **Provide `peek`, `copyn`, `publish` and `call`, and make invention costly.**
   Acquisition will become the main channel on its own.
4. **Choose scarcity deliberately** — it decides whether they rob or sabotage
   each other.
5. **Use the packed encoding**, so a fetched value can be named rather than
   dropped into a shared register.
6. **Run at least four of it.** One colony can only produce anecdotes.
