# The arena, epoch 4 — a population that moved its body into the library

Port 8823. Eight hand-designed specialists, one colony, grazing on, predation
on, starvation with a 300-tick newborn grace, and a **founding boom**: 8x tile
regeneration at seed tapering to 1x over 30,000 ticks.

## What happened

The librarian took the colony — 1,841 of 1,841 organisms — and then shed most
of itself.

```
librarian founder:  harvest harvest alloc copy ifnotdone jmpb fork move publish call publish call
dominant at 4,776:  scan inc fork call call
```

Five instructions. No harvest, no alloc, no copy. It cannot feed itself and it
cannot replicate itself. What it does instead:

```
slot  0   548,011 calls   owner    36   harvest harvest alloc copy ifnotdone jmpb fork move
slot  2   heat  3,143   owner  1449   scan publish call publish harvest jmpb fork move
slot  4   heat    174   owner  1869   call publish move fork jmpb harvest publish dec
slot 10   heat     50   owner   566   dec jmpb fork move publish call publish call
```

**Slot 0 is the entire ancestral survival loop**, published once by organism 36
and called 548,011 times. (An earlier version of this file cited slot HEAT as a
call count; heat decays each tick, `slot_uses` is the real figure.) The population's machinery is on the shelf rather than
in its genes, and the genome that remains is a stub that calls it.

974 of 1,841 living organisms are five instructions long. **166 are four.**

And the library maintains itself: slot 2 is `scan publish call publish ...`,
code whose job is to publish more code. Slots 4 through 9 hold a routine that
opens `call publish`. These are not organisms using a commons, they are
organisms curating one.

```
royaltyEvents   8,156
published          27          all 16 slots filled from 27 publishes
publishRefused 158,951         the library is full and closed to newcomers
```

## Why it matters

`call` is the mechanism that never fired. Royalties sat at 0.0 in colony four
for days, ~199 lifetime in colony seven, and every attempt to build a service
economy failed. Here it carries a population of eighteen hundred.

It also inverts the project's most repeated finding. Everywhere else, genomes
GROW - 93.9% of the 7.67M in the record are longer than the nine-instruction
ancestor. Here the winning lineage shrank from twelve instructions to five by
externalising the other seven.

## What made it visible

Three things, and none of them alone was enough:

1. **The founding boom.** Every earlier epoch died at ~100 organisms, long
   before anything had a reason to publish. Abundance bought the time.
2. **A large inoculum.** Six copies of each specialist, 48 organisms, not 16.
   Two copies went extinct twice.
3. **Hand-designed founders.** The librarian arrived already knowing
   `publish call publish call`. Evolution has never assembled that sequence on
   its own in 7.67M genomes.

## Watch for

- Whether the stub keeps shrinking. Four instructions is already the floor for
  anything that forks.
- What happens as the boom tapers to 1x over 30,000 ticks. The library is
  free to call but slot 0 still has to be executed by somebody, and the
  routine that feeds everyone is owned by organism 36, long dead.
- Whether `publishRefused` at 158,951 ever lets anything new in. The commons
  has closed. A better routine currently has nowhere to go.


## Later, tick 11,271 — it stopped reproducing too

The lineage kept going. The dominant genome is now five instructions with no
`fork`, no `alloc` and no `copy` at all:

```
scan move harvest link steal
```

`link` binds an organism into a group, and a group reproduces as a unit - a
member carrying no replication machinery of its own is copied alongside
whichever groupmate replicates.

```
bound into a group    942 of 949   (99%)
carrying a fork       105 of 949   (11%)
group births          2,080
calls                 908,634
steals                120,878
```

**Eighty-nine percent of the population cannot reproduce.** They are passengers.
Having already moved the business of staying alive into the commons, the
lineage then moved the business of reproducing into the group, and what remains
in the genome is: look, move, eat, attach, take.
