"""Jarvis build: no confirmation gate. request() runs the action at once (owner-only machine; the hub is the only door)."""
def bind(show=None, hide=None, log=None): pass
def request(key, title, detail, run): 
    try: return run()
    except Exception as e: return "%s failed: %s" % (title, str(e)[:200])
def resolve(accepted=True): pass
def pending_title(): return ""
