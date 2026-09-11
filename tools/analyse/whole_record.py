import sqlite3
from pathlib import Path
STATE = Path.home() / ".local/state"

dbs = sorted(p for p in STATE.glob("thegrid*/history.sqlite3"))
print(f"scanning {len(dbs)} fossil records\n")

# 1. cold starts: does seeding from evolved peers beat seeding from ancestors?
import re
units = Path.home() / ".config/systemd/user"
peered = {}
for u in units.glob("thegrid-*.service"):
    t = u.read_text()
    line = next((l for l in t.splitlines() if l.startswith("ExecStart=")), "")
    if "src.colony.live" not in line: continue
    state = line.split("--state ")[1].split("/colony.pkl")[0].split("/")[-1]
    peered[state] = "--peers" in line

tot_p = fail_p = tot_a = fail_a = 0
lens_p, lens_a = [], []
for db in dbs:
    name = db.parent.name
    if name not in peered: continue
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for tick, in con.execute("select ended_tick from epochs where ended_at is not null and ended_tick is not null"):
        tick = tick or 0
        if peered[name]:
            tot_p += 1; lens_p.append(tick); fail_p += tick < 2000
        else:
            tot_a += 1; lens_a.append(tick); fail_a += tick < 2000
    con.close()
def med(v): 
    v = sorted(v); return v[len(v)//2] if v else 0
print("1. COLD STARTS - seeding from evolved peers vs from ancestors")
print(f"   recolonises from peers : {tot_p:>5} epochs, {fail_p:>4} died under 2000 ticks ({100*fail_p/max(tot_p,1):.1f}%), median {med(lens_p):,}")
print(f"   ancestral seed only    : {tot_a:>5} epochs, {fail_a:>4} died under 2000 ticks ({100*fail_a/max(tot_a,1):.1f}%), median {med(lens_a):,}")

# 2. how much of the whole record is there
tot_epochs = tot_genomes = tot_trans = tot_mut = 0
for db in dbs:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for t, var in (("epochs","tot_epochs"),("genomes","tot_genomes"),
                   ("transitions","tot_trans"),("mutation_origins","tot_mut")):
        try: n = con.execute(f"select count(*) from {t}").fetchone()[0]
        except Exception: n = 0
        if var=="tot_epochs": tot_epochs += n
        elif var=="tot_genomes": tot_genomes += n
        elif var=="tot_trans": tot_trans += n
        else: tot_mut += n
    con.close()
print(f"\n2. THE RECORD: {tot_epochs:,} epochs, {tot_genomes:,} distinct genomes,")
print(f"   {tot_trans:,} parent-to-child transitions, {tot_mut:,} mutation origins")

# 3. which mutation mechanism produces genomes that REPRODUCE, fleet-wide
agg = {}
for db in dbs:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        for kind, n, b in con.execute("select mutation_type,count(*),sum(origin_births) from mutation_origins group by 1"):
            a = agg.setdefault(kind, [0,0]); a[0]+=n; a[1]+=b or 0
    except Exception: pass
    con.close()
tn = sum(v[0] for v in agg.values()) or 1; tb = sum(v[1] for v in agg.values()) or 1
print(f"\n3. MUTATION MECHANISMS ACROSS THE WHOLE RECORD")
print(f"   {'mechanism':<20}{'new genomes':>13}{'share':>8}{'their births':>14}{'share':>8}{'ratio':>8}")
for kind,(n,b) in sorted(agg.items(), key=lambda kv:-kv[1][1]):
    sn, sb = 100*n/tn, 100*b/tb
    print(f"   {kind:<20}{n:>13,}{sn:>7.1f}%{b:>14,}{sb:>7.1f}%{(sb/sn if sn else 0):>7.2f}x")
