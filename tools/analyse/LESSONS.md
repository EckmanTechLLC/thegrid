# What works

Toward a colony configured to survive and thrive. Only mechanisms that produced
a measured effect. Drawn from the whole record — **799 epochs, 7,673,264
distinct genomes, 8,820,379 parent-to-child transitions, 7,549,052 mutation
origins** — not from a snapshot.

**CONFIRMED** — holds across the full record or four-plus independent colonies.
**OBSERVED** — real and measured, but narrow or unstable. Don't design on these alone.

---

## 1. CONFIRMED — Horizontal acquisition is the only mechanism that beats break-even

Across every mutation event the project has ever recorded, one mechanism
produces genomes that out-reproduce their share. Every blind-variation
mechanism is below 1.0.

```
mechanism              new genomes    share    their births   share   ratio
segment_transfer           847,537    11.2%       4,097,300   32.4%   2.89x
single_deletion            471,007     6.2%         801,961    6.3%   1.02x
block_deletion             189,803     2.5%         266,054    2.1%   0.84x
point_substitution       4,100,412    54.3%       5,335,442   42.2%   0.78x
segment_inversion          211,959     2.8%         267,211    2.1%   0.75x
single_insertion           695,079     9.2%         803,039    6.4%   0.69x
segment_duplication        365,253     4.8%         401,428    3.2%   0.66x
random_burst               668,156     8.9%         668,956    5.3%   0.60x
```

`segment_transfer` is `copyn` — lifting a contiguous working block out of a
neighbour. It is 11% of what gets made and 32% of what goes on to breed.
Point substitution, the workhorse at 54% of all new genomes, is **below**
break-even.

**Design rule:** copying a neighbour beats inventing. Make `peek`/`copyn` cheap
and available; it is the highest-yield source of viable novelty in the system.

## 2. CONFIRMED — Seed from evolved genomes, never from ancestors

The single largest survival lever measured.

```
                          epochs   died <2k ticks   median epoch length
recolonises from peers       558      105 (18.8%)           126,773
ancestral seed only          217       82 (37.8%)             4,212
```

Half the failure rate and a **30x longer median epoch**. A fresh ancestral
palette has to rediscover a working replicator against the clock; a migrant
arrives already viable.

**Design rule:** peer with other colonies and recolonise from their living
genomes. Reject migrants carrying opcodes inert at the destination, or lacking
their own `alloc`+`copy`+`fork` — a passenger that cannot replicate alone is
not a founder.

## 3. CONFIRMED — Staying alive is what buys depth

Evolutionary depth scales monotonically with how long an epoch survives.

```
epoch length      epochs     mean deepest generation
<2k                  187                           2
2k-50k               179                          65
50k-200k             124                         207
200k+                285                         377
```

Nothing else in the record moves generation depth this reliably. Longevity is
not a nice-to-have; it is the mechanism.

## 4. CONFIRMED — Eviction keeps a colony alive; starvation does not

Remove death-by-hunger and death-by-age. An organism persists by default and is
reclaimed only when it has been useless for a full lifespan, or when memory is
wanted and it is the least recently useful thing holding any.

```
                epochs   extinctions   deepest lineage
eviction             4             0            7,224
control             23            19             ~250
bitrot              78            74             ~340
netlist             70            66              549
```

Zero extinctions in 48 hours across five colonies while the rest of the fleet
burned 159 epochs. Generation **7,224** against a previous project best in the
hundreds. Combined with item 3, this is the direct route to depth.

**Design rule:** existence free, reclamation the only death. A program does not
get hungry; it runs until something needs the room. Memory-pressure eviction
must **not** exempt newborns, or births outrun reclamation and the population
runs away.

## 5. CONFIRMED — Populations duplicate whatever pays, so choose what pays

Tandem duplication of the earning motif happens in every colony. Only the
target differs, and the economy sets the target.

```
grazing colonies     scan+move+harvest x2-4
netlist              copy+ifnotdone+jmpb x2          (the replication loop)
eviction             input+swap+input+nand+output x2-3   (the task circuit)
```

One copy of the task circuit was seeded; selection produced two and three, and
one colony duplicated its `publish` alongside it.

**Design rule:** you do not require complexity, you make it the thing that
earns. The duplication machinery already exists and points wherever income is.

## 6. CONFIRMED — Remove the cheap income and inheritance turns sideways

With grazing gone, horizontal acquisition does not merely appear, it takes over
— amplifying item 1 by a further 2x.

```
                % of new genomes    % of the births they produced   enrichment
eviction              27.9%                    58.2%                  2.09x
bitrot                 5.6%                     6.4%                  1.15x
netlist                1.1%                     1.4%                  1.24x
control                1.7%                     1.6%                  0.96x
```

Stable for three consecutive days while the volume climbed from 2.4% to 27.9%.
**More than half of all reproduction is now a copy of a neighbour's working
block rather than of a parent.**

## 7. CONFIRMED — Predation follows the currency

Where energy gates survival, predation is theft. Where it does not, it becomes
sabotage.

```
                steals    corrupt   corrupt/steal
eviction        58,667    153,004       2.61x
singleton       80,077      6,859       0.09x
bitrot         348,363      8,711       0.03x
```

An ~80x swing. Energy buys nothing in the eviction colonies, so taking it is
pointless — but destroying a rival's genome frees the thing that is actually
scarce, which is resident memory.

**Design rule:** whatever you make scarce decides how they attack each other.
It is a dial, not an accident.

## 8. CONFIRMED — Genomes grow, and the substrate does compute

Two worries the record disposes of.

```
genome length     share of 3.78M sampled genomes
9 (ancestor)                 2.6%
10-19                       56.2%
20-39                       36.7%
40+                          1.0%
```

**93.9% are longer than the nine-instruction ancestor.** Populations accrete
machinery; they do not collapse to the minimal replicator.

And six of the seven logic tasks are being solved right now across the fleet —
`and` in 20 of 24 colonies, `orn` 16, `or` 14, `xor` 14, `nand` 11, `not` 10.
The substrate supports real computation. Only `forecast`, the delayed-recall
task, stays out of reach.

## 9. CONFIRMED — Replication is the only reason any of this is knowable

Epoch-to-epoch variance inside one colony reaches **68x**. Four replicates per
configuration, each with its own tree, state and port, peered only within their
own group.

Three findings drawn from single colonies died on contact with replicates: a
bus read/write ratio that looked like an encoding property, a composition
advantage for the packed encoding, and a quadrant-occupancy result that was
clean for a day and gone the next.

**Design rule:** never run one of anything you intend to learn from.

## 10. CONFIRMED — Real hardware makes a real environment

Instruction cost rises with the actual AMD Tctl reading. Tile regeneration
tracks spare CPU from `/proc/stat`. Genome reservations commit real pages
against a cgroup ceiling. In the bit-rot colonies a bit in a living genome
flips when the box runs above its own trailing thermal baseline — thousands of
flips, and exactly zero when cool.

Colony count is cheap (24 colonies ≈ 4% of the box); tick rate is the expensive
dial, and raising it starves every colony at once until the CPU baseline
re-adapts.

---

## Observed, worth building on, not yet proven

- **Explicit operands may be what makes a call graph possible.** The packed
  `(op, src, dst)` encoding lets `fetch` and `call` name a destination register
  instead of clobbering a shared one, and royalties appear there and barely
  anywhere else — but the figure swings by an order of magnitude across a day.
- **Bit rot and wide task repertoires travel together.** Those colonies reach
  six of seven tasks and carry the fleet's highest complexity. Redundancy is
  what an unreliable substrate should select for, but they also run bounty and
  predation, so the cause is not isolated.
- **Model-authored mutation works given room to answer**, but is statistically
  negligible so far: 21 `model_proposal` events in 7.5M. A hybrid-reasoning
  model needs budget for the reasoning *and* the answer, or it returns nothing.
- **Withdraw an income slowly rather than cutting it.** Draining the tile at
  full rate while paying a shrinking fraction gives a gradient instead of a
  cliff, and the population re-specialises as it falls.
- **Reward the intermediate steps.** Lenski 2003 evolved EQU only in runs where
  simpler logic functions also paid; never where EQU alone was rewarded. Our
  one unreachable task, `forecast`, is the one with no partial credit.

---

## The colony built to thrive

Every line is one of the confirmed items above, turned around.

1. **No starvation, no senescence.** Eviction only — on disuse, and on memory
   pressure with no newborn exemption. (4)
2. **Peer it, and recolonise from living migrants.** Half the failure rate,
   thirty times the median epoch. Filter migrants for self-sufficiency. (2)
3. **Make `peek` and `copyn` cheap.** Horizontal acquisition is the only
   above-break-even source of viable novelty in seven and a half million
   events. (1, 6)
4. **Make being useful to another organism the only way to reproduce**, and
   make inventing from scratch expensive. (5, 6)
5. **Choose scarcity deliberately** — it decides whether they rob or sabotage. (7)
6. **Use the packed encoding**, so a fetched value can be named rather than
   dropped into a shared register. (observed)
7. **Pay partial credit on the way to hard tasks.** (observed)
8. **Run at least four of it.** One colony produces anecdotes. (9)

The single highest-value combination, if only two things can be done: **peer
recolonisation plus eviction.** One halves the failure rate and multiplies
epoch length thirtyfold; the other removes extinction almost entirely. Depth
follows from length, and everything else follows from depth.
