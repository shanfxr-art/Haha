"""Loads every Mark LVI skill (actions/*.py, one TOOL dict each) into the Jarvis registry. Failures skip one file, never the app."""
import os, pathlib, sys, threading
BASE = pathlib.Path(__file__).resolve().parent


def _heal():
    """Self-repair for a bad upload: empty __init__.py files can get dropped and the old core.py/actions.py can linger."""
    import importlib
    for d in ("core", "memory", "plugins", "providers"):
        f = BASE / d / "__init__.py"
        if (BASE / d).is_dir() and not f.exists():
            f.write_text("# package\n", encoding="utf-8")
    for old in ("core.py", "actions.py"):
        try: (BASE / old).unlink()
        except OSError: pass
    for m in ("core", "actions"):
        if m in sys.modules and not hasattr(sys.modules[m], "__path__"):
            del sys.modules[m]
    importlib.invalidate_caches()


_heal()
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


class Player:
    """Stand-in for Mark's Qt window: logs go to the HUD, video/quiz/voice calls are harmless no-ops (voice lives on the phone)."""
    def __init__(self, show=None, log=print):
        self._show, self._log = show, log
    def write_log(self, m, *a, **k): self._log(str(m)[:300])
    def show_video(self, *a, **k): return False
    def stop_video(self, *a, **k): pass
    def video_is_playing(self, *a, **k): return False
    def set_video_muted(self, *a, **k): pass
    def request_say(self, *a, **k): pass
    def show_quiz(self, *a, **k): pass
    def show_content(self, t="", b="", *a, **k):
        if self._show: self._show(str(t)[:60], str(b)[:600], 0)


def load(reg, shared, hud_show=None):
    import bootstrap
    from core.action_loader import discover_actions
    bootstrap.run()
    import shutil
    sk = pathlib.Path(os.environ.get('JARVIS_DATA') or BASE) / 'skills'   # self-written skills survive VM handover via the Drive backup
    sk.mkdir(parents=True, exist_ok=True)
    for f in sk.glob('x_*.py'):
        shutil.copy(f, BASE / 'actions' / f.name)
    player = Player(hud_show, lambda m: print(m, flush=True))
    ctx = {"player": player, "speak": lambda m, *a, **k: player.write_log(m), "response": None, "session_memory": None}
    mreg = discover_actions(BASE / "actions", reserved_names=set(reg.fns), logger=lambda m: print(m, flush=True))
    n = 0
    for d in mreg.get_tool_declarations():
        name = d["name"]
        reg.register(name, (lambda a, _n=name: mreg.run(_n, a, ctx)), False,
                     {"description": d.get("description", ""), "parameters": d.get("parameters", {})})
        n += 1
    shared["mreg"], shared["ctx"] = mreg, ctx
    try:
        import extras
        extras.register(reg, shared)
    except Exception as e:
        print("extras not loaded: %s" % str(e)[:300], flush=True)
    try:
        import agent
        agent.register(reg, shared)
    except Exception as e:
        print("agent not loaded: %s" % str(e)[:300], flush=True)
    print("Mark LVI skills loaded: %d" % n, flush=True)
    return n
