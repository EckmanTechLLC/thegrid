"""Recover genomes.source for rows written before the opcode was unpacked.

source was built with ISA[word], and a packed word carries (op, src, dst) and
reaches 4095, so 100,985 of colony eight's rows hold "?514" where an
instruction name belongs. encoded is lossy - 4096 words map to 64 glyphs - but
the 64 it preserves ARE the opcode field, and source only ever held names, so
the recovery is exact for what that column is supposed to contain. The src and
dst registers were never in this column and are not being invented here.
"""
import sys, sqlite3, shutil
from pathlib import Path
sys.path.insert(0, ".")
from src.colony.record import encode_genome
from src.colony.isa import ISA

GLYPH = {}
for op in range(64):
    GLYPH[encode_genome([op])] = ISA[op].name if op < len(ISA) else f"?{op}"
assert len(GLYPH) == 64, f"glyph map is not a bijection: {len(GLYPH)}"

db_path = Path(sys.argv[1])
dry = "--apply" not in sys.argv
if not dry:
    backup = db_path.with_suffix(".sqlite3.pre-backfill")
    if not backup.exists():
        shutil.copy2(db_path, backup)
        print(f"  backup -> {backup.name}")

con = sqlite3.connect(db_path, timeout=30)
con.execute("PRAGMA busy_timeout=30000")
rows = con.execute(
    "SELECT genome_id, encoded, source FROM genomes WHERE source LIKE '%?%'").fetchall()
fixed, unfixable, sample = 0, 0, []
updates = []
for gid, encoded, source in rows:
    try:
        recovered = " · ".join(GLYPH[ch] for ch in encoded)
    except KeyError:
        unfixable += 1
        continue
    if "?" in recovered and "?" in source:
        # still a real out-of-range opcode; leave it, it is honest
        pass
    if recovered != source:
        updates.append((recovered, gid))
        fixed += 1
        if len(sample) < 2:
            sample.append((source[:46], recovered[:46]))
print(f"  rows with '?': {len(rows):,}   recoverable: {fixed:,}   unfixable: {unfixable:,}")
for before, after in sample:
    print(f"    before: {before}")
    print(f"    after:  {after}")
if dry:
    print("  DRY RUN - nothing written. pass --apply to commit.")
else:
    con.executemany("UPDATE genomes SET source=? WHERE genome_id=?", updates)
    con.commit()
    left = con.execute("SELECT count(*) FROM genomes WHERE source LIKE '%?%'").fetchone()[0]
    print(f"  applied {len(updates):,} updates; rows still containing '?': {left:,}")
con.close()
