"""Jarvis PC app: control tools (step 4). Mouse, keyboard, windows, apps, files, commands, downloads, clipboard.
Needs no Qt. Windows-first; the GUI/OS pieces are imported lazily so the logic can be tested anywhere."""
import ctypes, os, re, subprocess, sys, threading, time, urllib.request

WIN = sys.platform == "win32"
BLOCKED_PROCS = {"python", "pythonw", "node", "cmd", "conhost", "powershell", "pwsh", "explorer", "tailscale", "tailscaled",
                 "tailscale-ipn", "system", "csrss", "winlogon", "wininit", "services", "svchost", "lsass", "smss", "rdpclip", "dwm"}
ALIASES = {"chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "firefox": "firefox", "notepad": "notepad", "calculator": "calc",
           "calc": "calc", "explorer": "explorer", "files": "explorer", "file explorer": "explorer", "cmd": "cmd", "terminal": "wt",
           "powershell": "powershell", "task manager": "taskmgr", "paint": "mspaint", "settings": "ms-settings:", "word": "winword",
           "excel": "excel", "spotify": "spotify", "discord": "discord", "vscode": "code", "vs code": "code"}
KEYS = {"enter": "enter", "return": "enter", "esc": "esc", "escape": "esc", "tab": "tab", "space": "space", "backspace": "backspace",
        "delete": "delete", "del": "delete", "up": "up", "down": "down", "left": "left", "right": "right", "home": "home", "end": "end",
        "pageup": "pageup", "pagedown": "pagedown", "win": "win", "windows": "win", "ctrl": "ctrl", "control": "ctrl", "alt": "alt",
        "shift": "shift"}


def _num(v, default=None):
    try:
        return float(v)
    except Exception:
        if default is None:
            raise ValueError("a number is needed, got %r" % (v,))
        return default


def _path(a, *names):
    for n in names + ("path", "text"):
        if a.get(n):
            return os.path.expandvars(os.path.expanduser(str(a[n]).strip().strip('"')))
    raise ValueError("a path is needed")


def _protected(p):
    """Refuse drive roots, Windows itself and the app's own folder, even with approval."""
    full = os.path.abspath(p)
    if os.path.dirname(full) == full:
        return "that is a drive root"
    low = full.lower().replace("/", "\\")
    for bad in (os.environ.get("SystemRoot", "C:\\Windows"), os.environ.get("ProgramFiles", "C:\\Program Files"), os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")):
        if low == bad.lower() or low.startswith(bad.lower().rstrip("\\") + "\\"):
            return "that is inside a protected system folder"
    here = os.path.dirname(os.path.abspath(__file__)).lower().replace("/", "\\")
    if low == here or low.startswith(here + "\\"):
        return "that is the Jarvis app's own folder"
    return ""


def _keyname(k):
    k = str(k).strip().lower()
    return KEYS.get(k, k)


class Control:
    def __init__(self, shared=None, gui=None, opener=None, runner=None, clip=None, exit_fn=None):
        self.shared = shared if shared is not None else {"scale": 1.0}
        self._gui = gui
        self.opener = opener or self._open
        self.runner = runner or subprocess.run
        self.clip = clip or {"get": self._clip_get, "set": self._clip_set}
        self.exit_fn = exit_fn or os._exit

    # ---- helpers ----
    def gui(self):
        if self._gui is None:
            import pyautogui
            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0.02
            self._gui = pyautogui
        return self._gui

    def _xy(self, a):
        s = float(self.shared.get("scale") or 1.0)
        if a.get("x") is None and a.get("text"):   # Telegram sends "/pc click 532 1184" as plain text
            n = re.findall(r"-?\d+(?:\.\d+)?", str(a["text"]))
            if len(n) >= 2:
                a = {"x": n[0], "y": n[1]}
        return int(round(_num(a.get("x")) * s)), int(round(_num(a.get("y")) * s))

    def _ps(self, cmd, timeout):
        return self.runner(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                           capture_output=True, text=True, timeout=timeout, errors="replace")

    def _clip_get(self):
        r = self._ps("Get-Clipboard -Raw", 15)
        return (r.stdout or "").rstrip("\r\n")

    def _clip_set(self, text):
        r = self.runner(["clip"], input=text, text=True, capture_output=True, timeout=15)
        if r.returncode:
            raise RuntimeError("clipboard failed")

    @staticmethod
    def _open(target):
        if WIN:
            os.startfile(target)  # ShellExecute: finds apps by name, no shell parsing
        else:
            subprocess.Popen(["xdg-open", target])

    # ---- mouse ----
    def click(self, a):
        x, y = self._xy(a); self.gui().click(x, y, button="left"); return "Clicked at %d,%d." % (x, y)

    def double_click(self, a):
        x, y = self._xy(a); self.gui().doubleClick(x, y); return "Double-clicked at %d,%d." % (x, y)

    def right_click(self, a):
        x, y = self._xy(a); self.gui().click(x, y, button="right"); return "Right-clicked at %d,%d." % (x, y)

    def move(self, a):
        x, y = self._xy(a); self.gui().moveTo(x, y); return "Moved the mouse to %d,%d." % (x, y)

    def drag(self, a):
        s = float(self.shared.get("scale") or 1.0)
        if a.get("x2") is None and a.get("text"):
            n = re.findall(r"-?\d+(?:\.\d+)?", str(a["text"]))
            if len(n) >= 4:
                a = {"x1": n[0], "y1": n[1], "x2": n[2], "y2": n[3]}
        x1, y1 = _num(a.get("x1", a.get("x"))) * s, _num(a.get("y1", a.get("y"))) * s
        x2, y2 = _num(a.get("x2")) * s, _num(a.get("y2")) * s
        g = self.gui(); g.moveTo(int(x1), int(y1)); g.dragTo(int(x2), int(y2), duration=0.4, button="left")
        return "Dragged from %d,%d to %d,%d." % (x1, y1, x2, y2)

    def scroll(self, a):
        n = int(_num(a.get("amount", a.get("clicks", a.get("dy", 3))), 3))
        d = str(a.get("direction", "")).lower()
        if d == "down":
            n = -abs(n)
        elif d == "up":
            n = abs(n)
        if a.get("x") is not None and a.get("y") is not None:
            x, y = self._xy(a); self.gui().moveTo(x, y)
        self.gui().scroll(n)
        return "Scrolled %s." % ("up" if n > 0 else "down")

    # ---- keyboard ----
    def type(self, a):
        text = str(a.get("text", ""))
        if not text:
            raise ValueError("text is needed")
        text = text[:2000]
        if text.isascii():
            self.gui().write(text, interval=0.01)
        else:   # unicode: paste it
            old = None
            try:
                old = self.clip["get"]()
            except Exception:
                pass
            self.clip["set"](text); time.sleep(0.1)
            self.gui().hotkey("ctrl", "v"); time.sleep(0.2)
            if old is not None:
                try: self.clip["set"](old)
                except Exception: pass
        if str(a.get("enter", "")).lower() in ("1", "true", "yes"):
            self.gui().press("enter")
        return "Typed %d characters." % len(text)

    def key(self, a):
        k = _keyname(a.get("key") or a.get("text") or "")
        if not k:
            raise ValueError("key is needed")
        self.gui().press(k); return "Pressed %s." % k

    def hotkey(self, a):
        raw = str(a.get("keys") or a.get("text") or a.get("key") or "")
        ks = [_keyname(k) for k in re.split(r"[+\s,]+", raw) if k]
        if len(ks) < 2:
            raise ValueError("give two or more keys, like ctrl+c")
        self.gui().hotkey(*ks); return "Pressed %s." % "+".join(ks)

    # ---- apps and windows ----
    def open_app(self, a):
        name = str(a.get("name") or a.get("app") or a.get("text") or "").strip()
        if not name:
            raise ValueError("an app name is needed")
        target = ALIASES.get(name.lower(), name)
        self.opener(target)
        return "Opened %s." % name

    def open_url(self, a):
        u = str(a.get("url") or a.get("text") or "").strip()
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        if not re.match(r"^https?://[^\s]+$", u, re.I):
            raise ValueError("that is not a web address")
        self.opener(u); return "Opened %s." % u

    def close_app(self, a):
        name = str(a.get("name") or a.get("app") or a.get("text") or "").strip()
        base = re.sub(r"\.exe$", "", ALIASES.get(name.lower(), name), flags=re.I)
        if not re.match(r"^[\w .\-]{1,60}$", base):
            raise ValueError("that is not a valid app name")
        if base.lower() in BLOCKED_PROCS:
            return "Refused: closing '%s' could break the PC or Jarvis itself." % base
        cmd = ["taskkill", "/IM", base + ".exe"] + (["/F"] if str(a.get("force", "")).lower() in ("1", "true", "yes") else [])
        r = self.runner(cmd, capture_output=True, text=True, timeout=30, errors="replace")
        return ((r.stdout or "") + (r.stderr or "")).strip()[:500] or "Closed %s." % base

    def _windows(self):
        if not WIN:
            return []
        u = ctypes.windll.user32
        out = []
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, _):
            if u.IsWindowVisible(h):
                n = u.GetWindowTextLengthW(h)
                if n:
                    b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                    out.append((h, b.value))
            return True
        u.EnumWindows(proto(cb), 0)
        return out

    def list_windows(self, a):
        f = str(a.get("name") or a.get("text") or "").lower()
        ws = [t for _, t in self._windows() if not f or f in t.lower()]
        return "\n".join(ws[:40]) or "No open windows" + (" matching '%s'." % f if f else ".")

    def focus_window(self, a):
        f = str(a.get("name") or a.get("title") or a.get("text") or "").lower()
        if not f:
            raise ValueError("a window name is needed")
        for h, t in self._windows():
            if f in t.lower():
                u = ctypes.windll.user32
                u.ShowWindow(h, 9); u.SetForegroundWindow(h)
                return "Focused: " + t[:80]
        return "No window matching '%s'." % f

    def lock(self, a):
        if not WIN:
            raise RuntimeError("lock only works on Windows")
        ctypes.windll.user32.LockWorkStation(); return "Locked."

    def volume(self, a):
        v = str(a.get("level") if a.get("level") is not None else a.get("text", "")).strip().lower()
        if v in ("mute", "unmute", "toggle"):
            self.gui().press("volumemute"); return "Toggled mute."
        if v in ("up", "down"):
            for _ in range(5):
                self.gui().press("volume" + v)
            return "Volume " + v + "."
        n = int(_num(v)); n = max(0, min(100, n))
        for _ in range(50):
            self.gui().press("volumedown")
        for _ in range(n // 2):
            self.gui().press("volumeup")
        return "Volume set to about %d%%." % n

    def restart_app(self, a):
        threading.Timer(1.5, lambda: self.exit_fn(0)).start()   # the watchdog in master.js starts the app again
        return "Restarting the PC app. It is back in a few seconds."

    # ---- commands and files ----
    def run_command(self, a):
        c = str(a.get("command") or a.get("text") or "").strip()
        if not c:
            raise ValueError("a command is needed")
        t = int(max(1, min(100, _num(a.get("timeout"), 60))))
        try:
            r = self._ps(c, t)
        except subprocess.TimeoutExpired:
            return "Stopped after %d seconds with no finish." % t
        out = ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()
        return ("[exit %s]\n" % r.returncode + out)[:3500]

    def list_dir(self, a):
        p = _path(a) if (a.get("path") or a.get("text")) else os.path.expanduser("~")
        items = sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = []
        for e in items[:100]:
            try:
                lines.append(("[dir]  " + e.name) if e.is_dir() else "%s  (%d KB)" % (e.name, e.stat().st_size // 1024))
            except OSError:
                lines.append(e.name)
        return (p + "\n" + "\n".join(lines) + ("\n... %d more" % (len(items) - 100) if len(items) > 100 else "")) if lines else p + " is empty."

    def read_file(self, a):
        p = _path(a)
        if os.path.getsize(p) > 5_000_000:
            return "File is over 5 MB; too big to read here."
        with open(p, "rb") as f:
            data = f.read(20000)
        if b"\x00" in data[:2000]:
            return "That looks like a binary file, not text."
        return data.decode("utf-8", "replace") + ("\n...[cut at 20000 bytes]" if os.path.getsize(p) > 20000 else "")

    def write_file(self, a):
        p = _path(a)
        why = _protected(p)
        if why:
            return "Refused: " + why + "."
        content = str(a.get("content", a.get("data", "")))
        if a.get("path") is None and a.get("text") is not None and not content:
            raise ValueError("content is needed")
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        mode = "a" if str(a.get("append", "")).lower() in ("1", "true", "yes") else "w"
        with open(p, mode, encoding="utf-8", newline="") as f:
            f.write(content)
        return "Wrote %d characters to %s." % (len(content), p)

    def move_file(self, a):
        src = _path(a, "src", "from", "source")
        dst = os.path.expandvars(os.path.expanduser(str(a.get("to") or a.get("dst") or a.get("dest") or "").strip().strip('"')))
        if not dst:
            raise ValueError("a destination (to) is needed")
        for p in (src, dst):
            why = _protected(p)
            if why:
                return "Refused: " + why + "."
        import shutil
        shutil.move(src, dst); return "Moved %s to %s." % (src, dst)

    def delete_file(self, a):
        p = _path(a)
        why = _protected(p)
        if why:
            return "Refused: " + why + "."
        if os.path.isdir(p):
            if str(a.get("recursive", "")).lower() not in ("1", "true", "yes"):
                return "That is a folder. Say recursive=true to delete it with everything inside."
            import shutil
            shutil.rmtree(p); return "Deleted folder %s." % p
        os.remove(p); return "Deleted %s." % p

    def download(self, a):
        u = str(a.get("url") or "").strip()
        if not re.match(r"^https?://[^\s]+$", u, re.I):
            raise ValueError("a web link (url) is needed")
        dest = a.get("path") or a.get("to") or ""
        if dest:
            dest = os.path.expandvars(os.path.expanduser(str(dest)))
        else:
            name = re.sub(r"[^\w.\-]", "_", u.split("?")[0].rstrip("/").split("/")[-1])[:80] or "download"
            dest = os.path.join(os.path.expanduser("~"), "Downloads", name)
        if os.path.isdir(dest):
            dest = os.path.join(dest, re.sub(r"[^\w.\-]", "_", u.split("?")[0].rstrip("/").split("/")[-1])[:80] or "download")
        why = _protected(dest)
        if why:
            return "Refused: " + why + "."
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        req = urllib.request.Request(u, headers={"User-Agent": "jarvis-pc"})
        total, end = 0, time.time() + 100
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                total += len(b)
                if total > 200 * 1024 * 1024 or time.time() > end:
                    f.close(); os.remove(dest)
                    return "Stopped: the download was over 200 MB or took too long."
                f.write(b)
        return "Downloaded %d KB to %s." % (total // 1024, dest)

    def clipboard_get(self, a):
        return self.clip["get"]()[:3500] or "The clipboard is empty."

    def clipboard_set(self, a):
        t = str(a.get("text", ""))
        self.clip["set"](t); return "Copied %d characters to the clipboard." % len(t)


# name, method, risky: risky must match the hub's PC_RISKY list
TOOLS = [("click", False), ("double_click", False), ("right_click", False), ("move", False), ("drag", False), ("scroll", False),
         ("type", False), ("key", False), ("hotkey", False), ("open_app", False), ("open_url", False), ("close_app", True),
         ("list_windows", False), ("focus_window", False), ("lock", True), ("volume", False), ("restart_app", True),
         ("run_command", True), ("list_dir", False), ("read_file", False), ("write_file", True), ("move_file", True),
         ("delete_file", True), ("download", True), ("clipboard_get", False), ("clipboard_set", False)]


def register(reg, shared=None, **kw):
    c = Control(shared, **kw)
    for name, risky in TOOLS:
        reg.register(name, getattr(c, name), risky=risky)
    return c
