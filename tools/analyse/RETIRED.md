# Retired colonies — 2026-09-11

Nine colonies stopped. Their **fossil records are untouched** and stay in
`~/.local/state/`; only the unit file moved, to
`~/.config/systemd/user/retired/`, so the fleet page stops listing them.
Restart any of them by moving the unit back and `systemctl --user enable --now`.

Reason for retiring at all: two thirds of the fleet was running to re-confirm
settled questions. The Grid is for seeing what happens, not for maintaining a
measurement rig.

| retired | port | question it answered |
|---|---|---|
| Colony One | 8787 | Lease. Exact renewal sat at 24.6% across 935,000 renewals — chance is 25% — and the lease caused 1.6% of deaths. Obligation is not a selective force next to hunger. |
| Colony Three | 8789 | Free `signal`/`listen`. Cost was never the barrier. |
| Colony Six | 8792 | Predation-only control. Predation is demonstrated at 348,000+ steals elsewhere. |
| control-1..4 | 8801-04 | Baseline. Colony Two continues it at epoch 92. |
| netlist-2, netlist-4 | 8814, 8816 | Encoding. Three replicates is enough for that question. |

## The one thing that needed care

Peer recolonisation is the largest survival lever in the record — half the cold
start failure rate (18.8% vs 37.8%) and thirty times the median epoch length.
Three of the retired colonies were peers for survivors, so the dead ports were
stripped from their `--peers` lists:

```
Colony Two, Colony Five, Colony Seven:  6 -> 3 live peers each
```

No new peering was introduced. Wiring survivors into the eviction, bitrot or
netlist groups would have destroyed the independence those replicates exist to
provide.

## What remains: 15 colonies, 2,232 organisms

```
eviction-1..4 + Colony Four   5   zero extinctions; generation 7,541; transfer at 56% of births
bitrot-1..4 + Colony Five     5   open: does an unreliable substrate select for redundancy
Colony Seven                  1   248,527 macro runs; two slots carry 78% of them
Colony Eight + netlist-1,3    3   packed (op, src, dst) encoding
Colony Two                    1   one long-running baseline, epoch 92
```

Nine slots free. Two replicates for anything new, not four — enough not to fool
ourselves, not enough to turn the fleet back into a lab.
