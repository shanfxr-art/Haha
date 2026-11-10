"""Mark LVI features that main.py handled inline, exposed as plain tools."""
import io, json


def register(reg, shared):
    O = {"type": "OBJECT", "properties": {}}
    def P(**k): return {"type": "OBJECT", "properties": {n: {"type": "STRING", "description": d} for n, d in k.items()}}
    def add(name, fn, desc, params=None): reg.register(name, fn, False, {"description": desc, "parameters": params or O})

    from core import undo
    add("undo", lambda a: undo.undo_last(), "Undo the last reversible file/system action.")
    add("undo_history", lambda a: "\n".join(undo.history()) or "Nothing to undo.", "List undoable actions.")

    from memory import memory_manager as mm
    add("remember", lambda a: mm.remember(str(a.get("key", "")), str(a.get("value", "")), str(a.get("category") or "notes")), "Save a fact to long-term memory.", P(key="name", value="fact", category="notes|identity|preferences"))
    add("recall", lambda a: mm.search_memory(str(a.get("query", ""))), "Search long-term memory.", P(query="words"))
    add("forget", lambda a: mm.forget(str(a.get("key", "")), str(a.get("category") or "notes")), "Delete a memory entry.", P(key="name", category="category"))

    from actions import background_monitor as bm
    add("monitor_add", lambda a: bm.add_monitor(str(a.get("topic", ""))), "Watch a topic/news in the background.", P(topic="topic"))
    add("monitor_remove", lambda a: bm.remove_monitor(str(a.get("topic", ""))), "Stop watching a topic.", P(topic="topic"))
    add("monitor_check", lambda a: "\n".join(bm.check_all()) or "No news.", "Check all watched topics now.")

    from actions import system_monitor as sm
    add("system_status", lambda a: json.dumps(sm.get_system_status(), default=str)[:1500], "CPU, RAM, temperature, GPU of this PC.")

    def screen_ask(a):
        from PIL import ImageGrab
        from google.genai import types
        from core import gemini
        im = ImageGrab.grab().convert("RGB"); buf = io.BytesIO(); im.save(buf, "JPEG", quality=75)
        q = str(a.get("question") or "Describe what is on the screen and anything notable.")
        r = gemini.text([types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"), q], tier=gemini.SMART, timeout_ms=60000, default="")
        return r or "Vision models unavailable right now."
    add("screen_ask", screen_ask, "Look at the screen and answer a question about it.", P(question="what to look for"))
