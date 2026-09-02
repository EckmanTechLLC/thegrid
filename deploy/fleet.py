#!/usr/bin/env python3
"""One page for the whole fleet.

Each colony serves its own viewer on its own port, so seeing all seven meant
seven tabs. A browser cannot poll them itself - different ports are different
origins and the colonies send no CORS headers - so this fans out server-side
and returns one combined document. The colonies are not modified and do not
know this exists.
"""
from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLONIES = [
    ("One", 8787), ("Two", 8788), ("Three", 8789), ("Four", 8790),
    ("Five", 8791), ("Six", 8792), ("Seven", 8793),
]
# Only what the dashboard draws. The full snapshot carries five 2,304-character
# fields per colony; sending all of them seven times over would be 80KB a poll.
KEEP = ("name", "epoch", "tick", "population", "generation", "cost", "features",
        "complexity", "groups", "predation", "frontier", "bus", "machine",
        "weather", "width", "height", "energy", "biomeField", "organisms",
        "structureField", "signalField", "scrapField",
        "tasks", "deathsByCause", "reclaimPool", "slotsHeld", "publishRefused",
        "signalsHeard", "memoryBytes", "memoryMaxBytes", "dominant", "carriers")


def fetch(entry: tuple[str, int]) -> dict:
    label, port = entry
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=6) as r:
            state = json.load(r)
    except Exception as exc:
        return {"label": label, "port": port, "up": False, "error": type(exc).__name__}
    trimmed = {k: state[k] for k in KEEP if k in state}
    trimmed.update(label=label, port=port, up=True)
    return trimmed


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):        # keep the journal readable
        pass

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/fleet"):
            with ThreadPoolExecutor(max_workers=len(COLONIES)) as pool:
                colonies = list(pool.map(fetch, COLONIES))
            self._send(json.dumps({"colonies": colonies},
                                  separators=(",", ":")).encode(), "application/json")
        elif self.path in ("/", "/index.html"):
            self._send((HERE / "fleet.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("FLEET_PORT", "8799"))
    print(f"[fleet] serving {len(COLONIES)} colonies on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
