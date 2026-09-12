# Publishing the colonies to Flux

One entity per colony at `thegrid/<name>`, every two minutes by cron.

This lived in `~/odin-city/` for a while, which is a different project — it
ended up there because that host was once used for both. The colonies own their
own publishing now, and this is where it lives.

    */2 * * * * cd /home/etl/odin/thegrid-tools/tools/flux && \
      FLUX_NAMESPACE=thegrid /usr/bin/python3 grid_flux.py >> \
      /home/etl/.local/state/grid-flux/log 2>&1

Run it with `--dry-run` to print the payloads without publishing; no token
needed for that.

## Two faults it had when it moved here

**Half the fleet was invisible.** `GRID_PORT_HI` was 8810, so the scan stopped
at bitrot-2 and eleven colonies were never published — including the arena and
both service colonies. It is 8850 now. The range is the only thing that needs
touching when colonies are added; it discovers by asking each port its own
name, so nothing is hardcoded.

**Five fields did not exist when it was written**, two of which were asked for
in EckmanTechLLC/thegrid#5:

- `isa_version` — a genome is only meaningful against the table that produced
  it, and colony eight's packed (op, src, dst) glyphs mean something different
  from a tape colony's.
- `deployment` — two deployments publish under `thegrid/`, so a colony name
  alone does not say whose record a genome came from.
- `evicted`, `useful_living`, `observations` — the September mechanisms.

Note that `properties()` drops `None`, so a field absent from a colony simply
does not appear on that entity rather than publishing as null.
