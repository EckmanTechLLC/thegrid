# Deploying The Grid

Eight colonies run on one machine as `systemd --user` services, each with its
own source tree, state directory, port and viewer. The unit files in this
directory are copies of what is actually loaded on that machine.

**The code is mostly shared.** Colonies one, two, and four through seven run
byte-identical source; what makes them different colonies is the flags in these
unit files, not different code. Colony three (`colony3-free-signal`) and colony
eight (`colony8-netlist`) are the two that carry real source differences.

The per-colony table — port, tree, mutator, features, recolonisation — is in
the root `README.md` and is generated from these unit files. An earlier version
of this file kept that table by hand and drifted out of date: it named seven
colonies, credited colony six with a feature its unit does not enable, and
pointed colony three at a branch it no longer ran. Read the units, or the
generated table, rather than trusting a hand-maintained copy.

`tools/guide` builds a fuller index the same way, by importing each colony's
own modules in its own interpreter rather than describing them from memory.

## Installing

Unit files go in `~/.config/systemd/user/`. Each one pins `WorkingDirectory`
and `PYTHONPATH` to its own tree, so the interpreter is shared but the source
is resolved per colony:

    systemctl --user daemon-reload
    systemctl --user enable --now thegrid-colony2

Note that colony one's unit is `thegrid-colony.service`, with no digit, while
its tree is `thegrid-colony1`. That mismatch is easy to trip over when
restarting the fleet in a loop.
