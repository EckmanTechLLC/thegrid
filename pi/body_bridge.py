"""Body bridge - the spinal cord. Runs on etlpi.

Owns the GIGA's serial port exclusively, watches the world through the
phone's camera, and answers one question for the broker: when these bytes
were spoken to the body, did the physical world move more than it was
already moving? Per-trial baselines, so nobody gets paid for a sunbeam.
"""
import io
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageChops

CAM_URL = "http://192.168.50.28:4747/video"
SERIAL = "/dev/ttyACM0"
MAX_BYTES = 64
OBSERVE_S = 2.5
BASELINE_S = 1.2

latest = {"img": None, "ts": 0.0}
trial_lock = threading.Lock()


def camera_thread():
    while True:
        try:
            with urllib.request.urlopen(CAM_URL, timeout=10) as r:
                buf = b""
                while True:
                    chunk = r.read(16384)
                    if not chunk:
                        break
                    buf += chunk
                    a = buf.find(b"\xff\xd8")
                    b = buf.find(b"\xff\xd9", a + 2)
                    if a != -1 and b != -1:
                        try:
                            img = Image.open(io.BytesIO(buf[a:b + 2]))
                            latest["img"] = img.convert("L").resize((80, 45))
                            latest["ts"] = time.time()
                        except Exception:
                            pass
                        buf = buf[b + 2:]
                    if len(buf) > 1_000_000:
                        buf = b""
        except Exception:
            time.sleep(3)


def snap(max_age=1.5):
    img, ts = latest["img"], latest["ts"]
    if img is None or time.time() - ts > max_age:
        return None
    return img


def motion_over(seconds, samples=4):
    """Mean frame-to-frame difference across a window. None if blind."""
    vals, prev = [], snap()
    if prev is None:
        return None
    for _ in range(samples):
        time.sleep(seconds / samples)
        cur = snap()
        if cur is None:
            return None
        d = ImageChops.difference(prev, cur)
        vals.append(sum(d.getdata()) / (80 * 45))
        prev = cur
    return sum(vals) / len(vals)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "camera": snap() is not None,
                             "serial": True})
        else:
            self._send(404, {})

    def do_POST(self):
        if self.path != "/trial":
            return self._send(404, {})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(min(n, 8192)))
            payload = bytes(int(b) & 0xFF for b in req["bytes"][:MAX_BYTES])
        except Exception:
            return self._send(400, {"error": "bad request"})
        with trial_lock:   # the body is one; trials queue here
            base = motion_over(BASELINE_S)
            if base is None:
                return self._send(200, {"motion": 0, "camera": False})
            try:
                with open(SERIAL, "wb", buffering=0) as port:
                    for b in payload:
                        port.write(bytes([b]))
                        time.sleep(0.03)
            except OSError:
                return self._send(200, {"motion": 0, "camera": True,
                                        "serial": False})
            moved = motion_over(OBSERVE_S)
            if moved is None:
                return self._send(200, {"motion": 0, "camera": False})
            net = max(0.0, moved - base * 1.5)   # margin over its own moment
            self._send(200, {"motion": round(net, 2),
                             "baseline": round(base, 2),
                             "observed": round(moved, 2), "camera": True})


def main():
    import subprocess
    subprocess.run(["stty", "-F", SERIAL, "115200", "raw", "-echo"],
                   check=False)
    threading.Thread(target=camera_thread, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8841), Handler).serve_forever()


if __name__ == "__main__":
    main()
