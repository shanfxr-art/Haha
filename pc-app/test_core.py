"""Tests core.py against the REAL hub code. Run: HUB_DIR=/path/to/hub python3 test_core.py  (needs node)"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import core
from PIL import Image

HUB_DIR = os.environ.get("HUB_DIR", "")
if not HUB_DIR or not os.path.exists(os.path.join(HUB_DIR, "index.js")):
    print("set HUB_DIR to the folder with the hub's index.js"); sys.exit(2)
ok = bad = 0
def check(n, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL:", n)

tmp = tempfile.mkdtemp()
for f in ("index.js", "jarvis-lib.js"):
    shutil.copy(os.path.join(HUB_DIR, f), tmp)
OWNER, PCT, PORT = "o" * 32, "p" * 48, "24811"
json.dump({"token": OWNER, "pcToken": PCT, "bind": "127.0.0.1", "geminiKey": "k" * 20, "ladder": ["gemini-3.5-flash-lite"]}, open(os.path.join(tmp, "config.json"), "w"))
srv = subprocess.Popen(["node", "index.js"], cwd=tmp, env=dict(os.environ, SERVER_PORT=PORT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = "http://127.0.0.1:" + PORT

def call(method, path, body=None, tok=OWNER, timeout=30):
    r = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method)
    r.add_header("Authorization", "Bearer " + tok); r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp: return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, {}

try:
    for _ in range(50):
        try: urllib.request.urlopen(base + "/v1/health", timeout=1)
        except urllib.error.HTTPError: break
        except Exception: time.sleep(0.2)
    states, logs, shown, conn = [], [], [], []
    reg = core.build_registry(hud_show=lambda t, b, s: shown.append((t, b, s)), grab=lambda: Image.new("RGB", (2400, 1350), (10, 20, 30)))
    hub = core.Hub(base, PCT, reg, on_state=states.append, on_log=logs.append, on_connection=conn.append, poll_timeout=5)
    threading.Thread(target=hub.run, daemon=True).start()
    time.sleep(1.5)
    check("app connected", hub.online and conn[:1] == [True])
    s, j = call("GET", "/v1/devices/status"); check("hub sees the PC online", j.get("pc", {}).get("online") is True)

    s, j = call("POST", "/v1/pc/command", {"action": "ping"}); check("ping", j.get("result") == "pong")
    s, j = call("POST", "/v1/pc/command", {"action": "status"}); check("status", "Jarvis PC v" in j.get("result", ""))
    s, j = call("POST", "/v1/pc/command", {"action": "screenshot"}); check("screenshot reported", j.get("hasImage") is True and "1600x900" in j.get("result", ""))
    req = urllib.request.Request(base + "/v1/pc/screenshot", headers={"Authorization": "Bearer " + OWNER})
    data = urllib.request.urlopen(req).read(); check("hub stored a JPEG", data[:2] == b"\xff\xd8" and len(data) > 500)
    s, j = call("POST", "/v1/pc/command", {"action": "show", "args": {"t": "Hello", "b": "Body", "s": 5}}); check("show", shown == [("Hello", "Body", 5)])
    s, j = call("POST", "/v1/pc/command", {"action": "click", "args": {"x": 1, "y": 2}}); check("unbuilt action says so", "not built" in j.get("result", ""))
    s, j = call("POST", "/v1/pc/command", {"action": "delete_file", "args": {"path": "x"}}); check("risky action not run", "not built" in j.get("result", "") or "Refused" in j.get("result", ""))
    check("state goes thinking then idle", "thinking" in states and states[-1] == "idle")
    call("POST", "/v1/state", {"state": "speaking"}); time.sleep(1.2)
    check("hub state change reaches the HUD", "speaking" in states)
    check("PC token cannot use owner paths", call("GET", "/v1/health", tok=PCT)[0] == 403)

    # a registry that has a risky action must refuse it when the hub did not mark it risky
    r2 = core.Registry(); r2.register("boom", lambda a: "ran", risky=True)
    check("risky guard", "Refused" in r2.run("boom", {}, False)["text"] and r2.run("boom", {}, True)["text"] == "ran")
    r2.register("bad", lambda a: 1 / 0)
    check("action crash contained", "failed" in r2.run("bad", {}, False)["text"])

    # wrong token: no crash, reports it
    h2 = core.Hub(base, "x" * 48, reg, on_log=logs.append, poll_timeout=2)
    threading.Thread(target=h2.run, daemon=True).start(); time.sleep(1.5); h2.close()
    check("bad token reported", any("refused the token" in l for l in logs))
    hub.close()
finally:
    srv.kill(); shutil.rmtree(tmp, ignore_errors=True)
print("%d checks passed%s" % (ok, ", %d FAILED" % bad if bad else ""))
sys.exit(1 if bad else 0)
