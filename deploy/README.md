# Deploying The Grid

Seven colonies run on one machine (Odin), each as its own systemd --user
service with its own state directory, port and viewer. The **code is shared** —
colonies one, two and four through seven run byte-identical trees off the
`colony2-experimental` branch. What makes them different colonies is the
configuration in these unit files, not different source.

Colony three is the exception: it runs the `colony3-old-economy` branch, which
kept the earlier economy (scrap lying on the map with decay, and tile income
not coupled to the host's spare CPU).

## The arms

| unit            | port | mutator | features                    | state dir       | peers |
|-----------------|------|---------|-----------------------------|-----------------|-------|
| thegrid-colony  | 8787 | odin    | predation                   | thegrid         | yes   |
| thegrid-colony2 | 8788 | random  | -                           | thegrid-colony2 | yes   |
| thegrid-colony3 | 8789 | random  | -                           | thegrid-colony3 | yes   |
| thegrid-colony4 | 8790 | random  | burn,predation              | thegrid-colony4 | yes   |
| thegrid-colony5 | 8791 | random  | bounty,predation            | thegrid-colony5 | yes   |
| thegrid-colony6 | 8792 | random  | macro,predation             | thegrid-colony6 | yes   |
| thegrid-colony7 | 8793 | odin    | bounty,burn,macro,predation | thegrid-colony7 | yes   |

`--features` gates the newer instructions. A disabled opcode executes as a nop
rather than being absent, so opcode indices and glyphs stay identical across
every arm and genomes remain directly comparable — a genome can migrate between
colonies and mean the same thing, except that some of its instructions do
nothing at the destination.

- `burn` — spends real CPU on the host, warming the chip and consuming
  scheduler time, which raises instruction cost and lowers income for every
  colony on the box, including the burner's own.
- `bounty` — `offer` escrows energy at a bus address for a wanted value;
  whoever posts that value collects. Settles through the ordinary bus write.
- `macro` — `define` plus eight macro opcodes whose meaning the population
  authors, rather than the instruction set being fixed by the author.
- `predation` — `steal` (a strict energy transfer between adjacent organisms)
  and `corrupt` (writing into a neighbour's genome).

`--mutator odin` routes about 5% of births through `OdinMutator`, which writes
a request to `<state>/operator/request.json` and waits for a `proposal.json`.
`grid_operator.py` is the consumer: it sends the genome and the colony's own
`build_prompt` to a local model and writes back a validated variant. Without
that service running, every birth silently falls back to the random operator.

`--peers` enables recolonisation: when a colony goes extinct it seeds from 24
living genomes fetched from a random peer's `/api/emigrants` rather than from
the ancestral founder palette, falling back to founders if no peer answers.

**Known problem:** migrants whose replication depends on an opcode that is
inert at the destination cannot reproduce there. Colony four has recorded
consecutive epochs ending at exactly `max_age` with zero births after being
recolonised from a macro-using peer. Receiving colonies should reject genomes
carrying instructions they do not implement; that fix is not written yet.

## Services

- `grid_operator.py` — model-backed mutation operator, polls the queues of the
  `--mutator odin` colonies. Expects an OpenAI-compatible endpoint; defaults to
  `http://127.0.0.1:8002/v1/chat/completions`.
- `fleet.py` / `fleet.html` — a dashboard on :8799 showing all seven colonies on
  one page. It fans out to each colony server-side because a browser cannot poll
  seven ports itself: different ports are different origins and the colonies
  send no CORS headers.

## Install

Unit files assume the tree is at `/home/etl/odin/thegrid-colonyN` and the
interpreter at `/home/etl/odin/thegrid-worktree/.venv/bin/python`; adjust both
for another host. `drop-ins.txt` records the memory limits applied with
`systemctl --user set-property` on top of the units.

    cp deploy/systemd/*.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now thegrid-colony{,2,3,4,5,6,7} thegrid-operator thegrid-fleet

Each colony serves its own viewer on its own port; the fleet dashboard is on
:8799.
