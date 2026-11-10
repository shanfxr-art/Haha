"""Jarvis PC app: hub connection and command dispatch. No GUI imports here, so it runs (and is tested) without Qt."""
import base64, io, json, os, platform, socket, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

VERSION = "0.1.0"
STATES = ("idle", "listening", "thinking", "speaking")


class Registry:
    """Actions plug in here. Step 4 adds the control tools by calling register()."""

    def __init__(self):
        self.fns = {}

    def register(self, name, fn, risky=False):
        self.fns[name] = (fn, risky)

    def run(self, name, args, risky_flag):
        item = self.fns.get(name)
        if not item:
            return {"text": "Action '%s' is not built into this PC app yet." % name}
        fn, risky = item
        # The hub only sends a risky action after you approved it; refuse anything it did not mark as such.
        if risky and not risky_flag:
            return {"text": "Refused: '%s' needs approval and the hub did not mark it as approved." % name}
        try:
            r = fn(args or {})
        except Exception as e:  # never let one action kill the app
            return {"text": "%s failed: %s" % (name, str(e)[:300])}
        return r if isinstance(r, dict) else {"text": str(r)}


class Hub:
    def __init__(self, url, token, registry, on_state=None, on_log=None, on_connection=None, poll_timeout=35):
        self.url = url.rstrip("/")
        self.token = token
        self.reg = registry
        self.on_state = on_state or (lambda s: None)
        self.on_log = on_log or (lambda m: None)
        self.on_connection = on_connection or (lambda ok: None)
        self.poll_timeout = poll_timeout
        self.after = 0
        self.online = False
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.started = time.time()

    # ---- http ----
    def _req(self, method, path, body=None, timeout=15):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.url + path, data=data, method=method)
        r.add_header("Authorization", "Bearer " + self.token)
        r.add_header("User-Agent", "jarvis-pc/" + VERSION)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")

    def _set_online(self, ok):
        if ok != self.online:
            self.online = ok
            self.on_connection(ok)
            self.on_log("Hub connected" if ok else "Hub connection lost")

    # ---- loop ----
    def run(self):
        delay = 1
        while not self.stop.is_set():
            try:
                if not self.online:   # the long poll only answers after up to 25 s, so check the link first
                    self._req("GET", "/v1/pc/info", timeout=10)
                    self._set_online(True)
                j = self._req("GET", "/v1/pc/next?after=%d" % self.after, timeout=self.poll_timeout + 10)
                self._set_online(True)
                delay = 1
                for c in j.get("cmds", []):
                    cid = int(c.get("id", 0))
                    if cid <= self.after:
                        continue
                    self.after = max(self.after, cid)
                    if c.get("action") == "state":
                        s = (c.get("args") or {}).get("state", "idle")
                        self.on_state(s if s in STATES else "idle")
                    else:
                        self.pool.submit(self._handle, c)
            except urllib.error.HTTPError as e:
                self._set_online(False)
                if e.code in (401, 403):
                    self.on_log("Hub refused the token (%d). Check PC_TOKEN." % e.code)
                    delay = 30
                else:
                    delay = min(delay * 2, 30)
                self.stop.wait(delay)
            except Exception:
                self._set_online(False)
                self.stop.wait(delay)
                delay = min(delay * 2, 30)

    def _handle(self, c):
        name = str(c.get("action", ""))
        self.on_log("> " + name)
        self.on_state("thinking")
        res = self.reg.run(name, c.get("args") or {}, bool(c.get("risky")))
        body = {"id": c.get("id"), "text": str(res.get("text", ""))[:4000]}
        if res.get("image"):
            body["image"] = res["image"]
        for attempt in range(3):
            try:
                self._req("POST", "/v1/pc/result", body, timeout=30)
                break
            except Exception:
                time.sleep(1 + attempt)
        self.on_log("< " + body["text"][:80])
        self.on_state("idle")

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)


# ---------- built-in actions (step 3) ----------
def build_registry(hud_show=None, grab=None):
    reg = Registry()
    started = time.time()

    def ping(a):
        return "pong"

    def status(a):
        up = int(time.time() - started)
        return "Jarvis PC v%s on %s (%s), host %s, app up %d min %d s." % (VERSION, platform.system(), platform.release(), socket.gethostname(), up // 60, up % 60)

    def screenshot(a):
        g = grab
        if g is None:
            from PIL import ImageGrab
            g = ImageGrab.grab
        im = g().convert("RGB")
        if im.width > 1600:
            im = im.resize((1600, int(im.height * 1600 / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70)
        return {"text": "Screenshot %dx%d." % im.size, "image": base64.b64encode(buf.getvalue()).decode()}

    def show(a):
        title = str(a.get("t") or a.get("title") or "JARVIS")[:60]
        body = str(a.get("b") or a.get("body") or a.get("text") or "")[:600]
        secs = max(0, min(3600, int(float(a.get("s") or a.get("secs") or 0))))
        if hud_show:
            hud_show(title, body, secs)
            return "Shown on the PC screen."
        return "No screen to show it on."

    for n, f in (("ping", ping), ("status", status), ("screenshot", screenshot), ("show", show)):
        reg.register(n, f)
    return reg
