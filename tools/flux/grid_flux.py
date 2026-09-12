"""Publish The Grid's live colony state into Flux as shared world state.

Makes the colonies subscribable by anyone: reads on Flux are public, so this is the
public, verifiable feed that in-city prediction markets would settle against.

  FLUX_URL        default https://api.flux-universe.com
  FLUX_TOKEN      bearer token issued with a namespace
  FLUX_NAMESPACE  namespace the token owns (entity ids must be prefixed with it)

  python3 grid_flux.py            publish once
  python3 grid_flux.py --dry-run  print the exact events, publish nothing
"""
import json, os, sys, time, urllib.error, urllib.request

FLUX_URL = os.environ.get("FLUX_URL", "https://api.flux-universe.com").rstrip("/")
_TF = os.path.expanduser("~/.flux_thegrid_token")
TOKEN = os.environ.get("FLUX_TOKEN", "")
if not TOKEN and os.path.exists(_TF):
    TOKEN = open(_TF).read().strip()
NS = os.environ.get("FLUX_NAMESPACE", "thegrid")
# The fleet is Matt's and it changes — a seventh colony became an eighth without
# this bridge noticing, because the list was hardcoded from a stale peers string.
# So discover them instead: scan the range, ask each observer its own name.
PORT_RANGE = range(int(os.environ.get("GRID_PORT_LO", 8785)),
                   int(os.environ.get("GRID_PORT_HI", 8850)) + 1)


def slug(name, port):
    """Entity id from the colony's OWN reported name, so a rename follows through."""
    s = "".join(c.lower() if c.isalnum() else "-" for c in (name or "").strip())
    while "--" in s:
        s = s.replace("--", "-")
    s = s.strip("-")
    return s or f"colony-port-{port}"


def discover():
    """Every observer answering right now, as {port: name}."""
    found = {}
    for port in PORT_RANGE:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/state", timeout=2) as r:
                found[str(port)] = json.load(r).get("name") or f"colony {port}"
        except Exception:
            continue
    return found


DRY = "--dry-run" in sys.argv


def observe(port):
    return json.load(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/state", timeout=10))


def properties(s):
    """What a subscriber can actually use.

    /api/state exposes ~82 keys; this publishes the ones that carry meaning,
    flattened, because a flat namespace is what a websocket subscriber can
    filter on. Large per-tile maps (energy, biomeField, organisms, signalField,
    structureField, scrapField, events, isa) stay out — they are big, they change
    every tick, and nothing downstream reads them.

    NOTE: the signalling counters below are here because omitting them caused a
    false negative. `weatherCueSignals` alone says a signal was EMITTED near a
    cue; `signalsHeard`, `signalGuidedMoves` and `postSignalHarvested` are what
    say anyone RECEIVED it, acted on it, and ate because of it. Reporting the
    first without the last three read as "signalling never emerged" when Colony
    Five had the whole chain running.
    """
    def g(d, *ks, default=None):
        cur = d
        for k in ks:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return default if cur is None else cur

    lg, cx, w = s.get("lineages") or {}, s.get("complexity") or {}, s.get("weather") or {}
    q = ["NW", "NE", "SW", "SE"]
    p = {
        "name": s.get("name"),
        "mutator": g(s, "mutator", "kind"),
        "features": ",".join(s.get("features") or []) or "none",

        # where the world is
        "epoch": s.get("epoch"), "tick": s.get("tick"),
        "population": s.get("population"), "generation": s.get("generation"),
        "births": s.get("births"), "deaths": s.get("deaths"),
        "deaths_starvation": g(s, "deathsByCause", "starvation", default=0),
        "deaths_senescence": g(s, "deathsByCause", "senescence", default=0),
        "width": s.get("width"), "height": s.get("height"),

        # who is alive — strains is the fixed-index array, so a lineage keeps its
        # slot across time and bands can actually be tracked
        "lineages": lg.get("count"), "top_share": lg.get("topShare"),
        "lineage_sizes": lg.get("sizes"), "strains": s.get("strains"),
        "biome_populations": s.get("biomePopulations"),

        # what they have become
        "complexity_median": cx.get("median"), "complexity_mean": cx.get("mean"),
        "complexity_max": cx.get("max"),
        "dominant_genome": s.get("dominant"), "ancestor_genome": s.get("ancestor"),

        # communication — the whole chain, not just emission
        "weather_cues_seen": s.get("weatherCuesSeen"),
        "weather_cue_signals": s.get("weatherCueSignals"),
        "signals_active": s.get("activeSignals"),
        "signals_heard": s.get("signalsHeard"),
        "signal_guided_moves": s.get("signalGuidedMoves"),
        "post_signal_harvested": s.get("postSignalHarvested"),

        # movement and reading of each other
        "moves": s.get("moves"), "scans": s.get("scans"),
        "guided_moves": s.get("guidedMoves"),
        "neighbour_reads": s.get("neighborReads"),
        "foreign_copies": s.get("foreignCopies"), "self_writes": s.get("selfWrites"),

        # the shared code economy
        "published_routines": s.get("published"), "calls": s.get("calls"),
        "publish_refused": s.get("publishRefused"),
        "code_slots_used": s.get("codeSlotsUsed"),
        # Names the instruction table these glyphs mean something against, and
        # which deployment the record came from. Both asked for in
        # EckmanTechLLC/thegrid#5: a genome is only checkable against the
        # table that produced it, and two deployments publish under
        # thegrid/ so a colony name alone does not say whose record it is.
        "isa_version": s.get("isaVersion"),
        "deployment": s.get("deployment"),
        # The September mechanisms.
        "evicted": g(s, "evicted", default=0),
        "useful_living": g(s, "usefulLiving", default=0),
        "observations": g(s, "observations", default=0),
        "royalties": s.get("royalties"), "royalty_events": s.get("royaltyEvents"),
        "salvaged": s.get("salvaged"), "built_tiles": s.get("builtTiles"),
        "bus_writes": g(s, "bus", "writes"), "bus_reads": g(s, "bus", "reads"),
        "groups_count": g(s, "groups", "count"), "groups_largest": g(s, "groups", "largest"),

        # feature-specific, present only when the feature is on
        "predation_steals": g(s, "predation", "steals"),
        "predation_corruptions": g(s, "predation", "corruptions"),
        "bounties_offered": g(s, "frontier", "bountiesOffered"),
        "bounty_claims": g(s, "frontier", "bountyClaims"),
        "burns": g(s, "frontier", "burns"),
        "lease_active": g(s, "lease", "active"),
        "bit_flips": s.get("bitFlips"),

        # weather, which is real
        "storms": w.get("storms"),
        "drought_quadrant": q[(w.get("droughtQuadrant") or 0) % 4],
        "bloom_quadrant": q[(w.get("bloomQuadrant") or 0) % 4],
        "die_temp_c": w.get("heatRawC"), "weather_source": w.get("source"),

        # the machine underneath
        "substrate": s.get("substrate"), "heat": s.get("heat"),
        "cost_multiplier": s.get("cost"), "memory_pressure": s.get("memory"),
        "cpu_usage_usec": s.get("cpuUsageUsec"),
        "machine_spare": g(s, "machine", "spare"),
        "started_at": s.get("startedAt"),
        "observed_at": int(time.time() * 1000),
    }
    return {k: v for k, v in p.items() if v is not None}


def event(entity, props):
    return {
        "stream": "thegrid",
        "source": "odin-grid-bridge",
        "timestamp": int(time.time() * 1000),
        "payload": {"entity_id": f"{NS}/{entity}", "properties": props},
    }


def publish(ev):
    req = urllib.request.Request(
        f"{FLUX_URL}/api/events", data=json.dumps(ev).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("User-Agent", "OdinGridBridge/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, (r.read()[:200].decode(errors="replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode(errors="replace")


def main():
    if not TOKEN and not DRY:
        print("FLUX_TOKEN not set — run with --dry-run, or export a namespace token")
        return 2
    colonies = discover()
    if not colonies:
        print("no colony observers answering"); return 1
    rc = 0
    for port, name in sorted(colonies.items(), key=lambda kv: int(kv[0])):
        entity = slug(name, port)
        try:
            s = observe(port)
        except Exception as e:
            print(f"{entity}: observer unreachable ({e})"); rc = 1; continue
        ev = event(entity, properties(s))
        if DRY:
            print(json.dumps(ev, indent=2)[:900]); print()
            continue
        code, body = publish(ev)
        ok = code in (200, 201, 202, 204)
        print(f"{ev['payload']['entity_id']}: HTTP {code} {'ok' if ok else body}")
        if not ok: rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
