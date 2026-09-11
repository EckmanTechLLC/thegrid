#!/usr/bin/env python3
"""Retire the colonies whose question is answered, without breaking the rest.

Peer recolonisation is the largest survival lever in the record - half the cold
start failure rate and thirty times the median epoch length - so a retirement
that leaves dead ports in a survivor's --peers list would quietly damage the
thing being preserved. Dead ports are stripped; no new peering is introduced,
because crossing the replicate groups would destroy their independence.

Fossil records are NOT deleted. The unit file moves to retired/ so the fleet
page stops listing the colony; the SQLite record stays where it is.
"""
import re, subprocess
from pathlib import Path

UNITS = Path.home() / ".config/systemd/user"
RETIRED = UNITS / "retired"
RETIRED.mkdir(exist_ok=True)

RETIRE = {  # unit stem -> why
    "thegrid-colony":   "lease answered: exact renewal at chance over 935,000 samples, 1.6% of deaths",
    "thegrid-colony3":  "free signal/listen answered",
    "thegrid-colony6":  "predation demonstrated at 348,000+ steals elsewhere",
    "thegrid-control1": "baseline established; Colony Two continues it",
    "thegrid-control2": "baseline established; Colony Two continues it",
    "thegrid-control3": "baseline established; Colony Two continues it",
    "thegrid-control4": "baseline established; Colony Two continues it",
    "thegrid-netlist2": "three encoding replicates is enough",
    "thegrid-netlist4": "three encoding replicates is enough",
}

dead_ports = set()
for stem in RETIRE:
    f = UNITS / f"{stem}.service"
    if f.exists():
        m = re.search(r"--port (\d+)", f.read_text())
        if m:
            dead_ports.add(m.group(1))

print(f"retiring {len(RETIRE)} colonies on ports {sorted(dead_ports)}\n")

for stem in RETIRE:
    subprocess.run(["systemctl", "--user", "disable", "--now", f"{stem}.service"],
                   capture_output=True)
    f = UNITS / f"{stem}.service"
    if f.exists():
        f.rename(RETIRED / f.name)
        print(f"  retired  {stem}")

fixed = 0
for f in sorted(UNITS.glob("thegrid-*.service")):
    text = f.read_text()
    m = re.search(r'--peers "([^"]*)"', text)
    if not m:
        continue
    peers = [p for p in m.group(1).split(",") if p.split(":")[-1] not in dead_ports]
    if len(peers) == len(m.group(1).split(",")):
        continue
    text = (text.replace(m.group(0), f'--peers "{",".join(peers)}"') if peers
            else text.replace(" " + m.group(0), ""))
    f.write_text(text)
    print(f"  repeered {f.stem:<22} {len(m.group(1).split(','))} -> {len(peers)} live peers")
    fixed += 1

subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
print(f"\n  {fixed} survivors repeered; daemon reloaded")
