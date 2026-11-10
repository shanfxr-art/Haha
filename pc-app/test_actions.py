"""Offline test for actions.py with a fake mouse/keyboard. Run: python3 test_actions.py"""
import os; os.environ['JARVIS_OPEN']='0'
import os, sys, tempfile, time, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jcore as core, jactions as actions

ok = bad = 0
def check(n, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL:", n)

class Gui:
    def __init__(s): s.log = []
    def __getattr__(s, n): return lambda *a, **k: s.log.append((n, a, k))
gui, opened, ran, exits, clip = Gui(), [], [], [], {"v": "old"}
def runner(cmd, **k):
    ran.append((cmd, k)); return types.SimpleNamespace(returncode=0, stdout="hello\n", stderr="")
shared = {"scale": 1.5}
reg = core.Registry()
actions.register(reg, shared, gui=gui, opener=opened.append, runner=runner,
                 clip={"get": lambda: clip["v"], "set": lambda t: clip.update(v=t)}, exit_fn=exits.append)
R = lambda n, a=None, risky=False: reg.run(n, a or {}, risky)["text"]

check("click scaled", R("click", {"x": 100, "y": 200}) == "Clicked at 150,300." and gui.log[-1][1] == (150, 300))
check("right click", gui.log and R("right_click", {"x": 10, "y": 10}).startswith("Right-clicked") and gui.log[-1][2]["button"] == "right")
check("drag", "Dragged" in R("drag", {"x1": 0, "y1": 0, "x2": 100, "y2": 100}))
check("scroll down", R("scroll", {"direction": "down", "amount": 4}) == "Scrolled down." and gui.log[-1][1] == (-4,))
check("click from telegram text", R("click", {"text": "10 20"}) == "Clicked at 15,30.")
check("click bad arg", "failed" in R("click", {"x": "abc", "y": 1}))
check("type ascii", R("type", {"text": "hi", "enter": True}) == "Typed 2 characters." and gui.log[-1][1] == ("enter",))
R("type", {"text": "héllo"}); check("type unicode pastes, clipboard restored", ("hotkey", ("ctrl", "v"), {}) in gui.log and clip["v"] == "old")
check("hotkey", R("hotkey", {"keys": "Ctrl+C"}) == "Pressed ctrl+c." and gui.log[-1][1] == ("ctrl", "c"))
check("hotkey single refused", "failed" in R("hotkey", {"keys": "c"}))
check("key", R("key", {"key": "Enter"}) == "Pressed enter.")
check("open alias", R("open_app", {"name": "Calculator"}) == "Opened Calculator." and opened[-1] == "calc")
R("open_url", {"url": "example.com"}); check("open url https", opened[-1] == "https://example.com")
check("open url junk", "failed" in R("open_url", {"url": "a b c"}))

# risky gate
check("run_command refused without approval", R("run_command", {"command": "dir"}).startswith("Refused"))
check("run_command approved", "hello" in R("run_command", {"command": "dir"}, True) and ran[-1][0][0] == "powershell")
check("close_app needs approval", R("close_app", {"name": "chrome"}).startswith("Refused"))
check("close_app blocks node", "could break" in R("close_app", {"name": "node.exe"}, True))
check("close_app blocks tailscale", "could break" in R("close_app", {"name": "tailscale"}, True))
check("close_app injection", "failed" in R("close_app", {"name": "x & del *"}, True))
R("close_app", {"name": "chrome"}, True); check("close_app graceful", ran[-1][0] == ["taskkill", "/IM", "chrome.exe"])
R("close_app", {"name": "chrome", "force": True}, True); check("close_app force", ran[-1][0][-1] == "/F")
R("restart_app", {}, True); time.sleep(2); check("restart exits", exits == [0])

# files
d = tempfile.mkdtemp(); f = os.path.join(d, "a", "note.txt")
check("write_file refused unapproved", R("write_file", {"path": f, "content": "x"}).startswith("Refused"))
check("write_file", "Wrote 5" in R("write_file", {"path": f, "content": "hello"}, True))
R("write_file", {"path": f, "content": "!", "append": True}, True)
check("read_file", R("read_file", {"path": f}) == "hello!")
check("list_dir", "note.txt" in R("list_dir", {"path": os.path.dirname(f)}) and "[dir]" in R("list_dir", {"path": d}))
check("move_file", "Moved" in R("move_file", {"path": f, "to": os.path.join(d, "b.txt")}, True) and os.path.exists(os.path.join(d, "b.txt")))
check("delete folder needs recursive", "recursive" in R("delete_file", {"path": os.path.join(d, "a")}, True))
check("delete file", "Deleted" in R("delete_file", {"path": os.path.join(d, "b.txt")}, True))
check("protect drive root", "Refused" in R("delete_file", {"path": "/"}, True))
check("protect app folder", "Refused" in R("write_file", {"path": os.path.join(os.path.dirname(actions.__file__), "x.py"), "content": "x"}, True))
open(os.path.join(d, "bin"), "wb").write(b"\x00\x01" * 50)
check("binary file", "binary" in R("read_file", {"path": os.path.join(d, "bin")}))
check("read missing file fails safely", "failed" in R("read_file", {"path": os.path.join(d, "nope")}))

# download from a local server
import http.server, threading, functools
open(os.path.join(d, "srv.txt"), "w").write("data" * 100)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=d))
threading.Thread(target=srv.serve_forever, daemon=True).start()
dest = os.path.join(d, "dl", "got.txt")
check("download", "Downloaded 0 KB" in R("download", {"url": "http://127.0.0.1:%d/srv.txt" % srv.server_port, "path": dest}, True) and open(dest).read() == "data" * 100)
check("download bad url", "failed" in R("download", {"url": "ftp://x"}, True))

# clipboard + screenshot scale wired through core
check("clipboard set/get", R("clipboard_set", {"text": "abc"}) .startswith("Copied") and R("clipboard_get") == "abc")
from PIL import Image
reg2 = core.build_registry(grab=lambda: Image.new("RGB", (3200, 1800)))
r = reg2.run("screenshot", {}, False); check("screenshot ok", "1600x900" in r["text"] and r.get("image"))
check("all hub actions registered", all(n in reg2.fns for n in "ping status screenshot click double_click right_click move drag scroll type key hotkey open_app close_app focus_window list_windows run_command list_dir read_file write_file move_file delete_file download clipboard_get clipboard_set open_url volume lock show restart_app".split()))
risky = {n for n, (f, r) in reg2.fns.items() if r}
check("risky set matches hub", risky == {"run_command", "write_file", "move_file", "delete_file", "download", "close_app", "lock", "restart_app"})
print("passed %d, failed %d" % (ok, bad)); sys.exit(1 if bad else 0)
