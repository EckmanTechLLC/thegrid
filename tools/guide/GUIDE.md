# The Grid — colony guide

_Generated 2026-09-07 11:48 from the unit files and each colony's own code. Do not edit by hand; run `build_guide.py`._

## At a glance

| colony | port | mutator | features | recolonises | encoding | service |
|---|---|---|---|---|---|---|
| One | 8787 | odin | predation,lease | yes | tape (bare opcode) | active |
| Two | 8788 | random | - | yes | tape (bare opcode) | active |
| Three | 8789 | random | - | yes | tape (bare opcode) | active |
| Four | 8790 | random | burn,predation | yes | tape (bare opcode) | active |
| Five | 8791 | random | bounty,predation | yes | tape (bare opcode) | active |
| Six | 8792 | random | predation | yes | tape (bare opcode) | active |
| Seven | 8793 | odin | bounty,burn,macro,predation | yes | tape (bare opcode) | active |
| Eight | 8794 | random | - | no | packed (op, src, dst) | active |

## Why comparisons between these are hard

Colonies **One, Two, Three, Four, Five, Six, Seven** recolonise from peers when they go extinct, so an epoch there can begin with genomes that already evolved elsewhere. Colonies **Eight** always restart from the ancestral founder palette. Composition and complexity figures are therefore not comparable across that line without first separating ancestor-seeded epochs from recolonised ones — an epoch's early average genome length identifies which it was.

The world itself does reset every epoch: `_new_colony` builds a fresh `SubstrateWorld`, so the code commons, macro slots, shared bus and reclaim pool all start empty. Only the population can carry over.


## What each quadrant is worth

`biome(x, y) = (x >= w/2) + 2*(y >= h/2)`, so NW is the top-left of the map as drawn and SE the bottom-right. Measured by stepping a real world, not transcribed:

| | NW forage | NE nomad | SW engineer | SE information |
|---|---|---|---|---|
| regeneration per step | 0.075 | 0.039 | 0.024 | 0.045 |
| energy per harvest | 8.1 | 4.68 | 4.68 | 4.68 |
| `harvest` cost | 0.917x | 1.833x | 1.833x | 1.904x |
| `move` cost | 1.41x | 0.776x | 1.833x | 1.41x |
| `scan` cost | 1.41x | 0.776x | 1.41x | 1.41x |
| `build` cost | 1.974x | 1.833x | 0.635x | 1.904x |
| `signal` cost | 1.974x | 1.41x | 1.41x | 0.776x |
| `nand` cost | 1.41x | 1.41x | 1.41x | 0.776x |
| `post` cost | 1.41x | 1.41x | 1.41x | 0.776x |
| task reward | 0.75x | 0.75x | 0.75x | 1.75x |

**NW** regenerates fastest and **SW** slowest, a 3.1x spread. A population concentrated in one quadrant is the map being obeyed, not a behaviour to explain — check this table before reaching for any other reason.


## Colony One

- **tree** `~/odin/thegrid-colony1` on `colony2-experimental` at `e042982`
- **port** 8787 · **state** `/home/etl/.local/state/thegrid/colony.pkl` · **memory ceiling** 4G · **10 ticks/s**
- **mutator** `odin` — routes ~5% of births through the local model via the operator service; falls back to random if nothing answers the queue
- **features** predation, lease
    - `predation` enables steal, corrupt
    - inert here (execute as nop): burn, offer, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source identical to thegrid-colony2**

## Colony Two

- **tree** `~/odin/thegrid-colony2` on `colony2-experimental` at `e042982`
- **port** 8788 · **state** `/home/etl/.local/state/thegrid-colony2/colony.pkl` · **memory ceiling** 1G · **10 ticks/s**
- **mutator** `random` — blind variation only
- **features** none
    - inert here (execute as nop): burn, offer, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7, steal, corrupt
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source identical to thegrid-colony2**

## Colony Three

- **tree** `~/odin/thegrid-colony3` on `colony2-experimental` at `c30c5ff`
- **port** 8789 · **state** `/home/etl/.local/state/thegrid-colony3/colony.pkl` · **memory ceiling** 4G · **10 ticks/s**
- **mutator** `random` — blind variation only
- **features** none
    - inert here (execute as nop): burn, offer, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7, steal, corrupt
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is scrap on tiles, decaying, tile income not coupled to the host, grazing subsidy withdrawn over 500,000 ticks
- **commons** publish overwrites unconditionally · max group 8 · max age 2400
- **source differs from thegrid-colony2** in: colony.py, isa.py, live.py, organism.py, substrate.py, world.py
- **instruction costs changed from the reference:** `signal` 0.45 → 0.0, `listen` 0.3 → 0.0

## Colony Four

- **tree** `~/odin/thegrid-colony4` on `colony2-experimental` at `e042982`
- **port** 8790 · **state** `/home/etl/.local/state/thegrid-colony4/colony.pkl` · **memory ceiling** 1536M · **10 ticks/s**
- **mutator** `random` — blind variation only
- **features** burn, predation
    - `burn` enables burn
    - `predation` enables steal, corrupt
    - inert here (execute as nop): offer, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source identical to thegrid-colony2**

## Colony Five

- **tree** `~/odin/thegrid-colony5` on `colony2-experimental` at `e042982`
- **port** 8791 · **state** `/home/etl/.local/state/thegrid-colony5/colony.pkl` · **memory ceiling** 1536M · **10 ticks/s**
- **mutator** `random` — blind variation only
- **features** bounty, predation
    - `bounty` enables offer
    - `predation` enables steal, corrupt
    - inert here (execute as nop): burn, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source identical to thegrid-colony2**

## Colony Six

- **tree** `~/odin/thegrid-colony6` on `colony2-experimental` at `e042982`
- **port** 8792 · **state** `/home/etl/.local/state/thegrid-colony6/colony.pkl` · **memory ceiling** 1536M · **10 ticks/s**
- **mutator** `random` — blind variation only
- **features** predation
    - `predation` enables steal, corrupt
    - inert here (execute as nop): burn, offer, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source identical to thegrid-colony2**

## Colony Seven

- **tree** `~/odin/thegrid-colony7` on `colony2-experimental` at `e042982`
- **port** 8793 · **state** `/home/etl/.local/state/thegrid-colony7/colony.pkl` · **memory ceiling** 1536M · **10 ticks/s**
- **mutator** `odin` — routes ~5% of births through the local model via the operator service; falls back to random if nothing answers the queue
- **features** bounty, burn, macro, predation
    - `bounty` enables offer
    - `burn` enables burn
    - `macro` enables define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7
    - `predation` enables steal, corrupt
- **recolonisation** from 6 peers
- **encoding** tape (bare opcode), 3 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source identical to thegrid-colony2**

## Colony Eight

- **tree** `~/odin/thegrid-colony8` on `colony8-netlist` at `93c0951`
- **port** 8794 · **state** `/home/etl/.local/state/thegrid-colony8/colony.pkl` · **memory ceiling** 1536M · **10 ticks/s**
- **mutator** `random` — blind variation only
- **features** none
    - inert here (execute as nop): burn, offer, define, macro0, macro1, macro2, macro3, macro4, macro5, macro6, macro7, steal, corrupt
- **recolonisation** disabled — always reseeds from ancestors
- **encoding** packed (op, src, dst), 8 registers, 50 opcodes, ancestor 9 instructions, founder palette 23
- **economy** child costs 16.0 energy (taken from the parent), salvage is global reclaim pool, tile income coupled to host spare CPU, grazing subsidy withdrawn over 500,000 ticks
- **commons** slots are held while called · max group 8 · max age 2400
- **source differs from thegrid-colony2** in: history.py, isa.py, live.py, mutation.py, organism.py, record.py
