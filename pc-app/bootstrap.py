"""Writes Mark's config/api_keys.json from env so every Mark skill uses YOUR keys with no login.
Env: GEMINI_KEY (same as hub geminiKey), GROQ_KEY (optional fallback), HUB_URL, PC_TOKEN."""
import json, os, pathlib
BASE = pathlib.Path(__file__).resolve().parent
GROQ_LADDER = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")

def run():
    (BASE / "config").mkdir(exist_ok=True)
    key, groq = os.environ.get("GEMINI_KEY", "").strip(), os.environ.get("GROQ_KEY", "").strip()
    data = {"gemini_api_key": key, "assistant_name": "Jarvis", "user_name": "Sir"}
    if groq:   # failover rung used when every Gemini model is out of quota / down
        pid = "openai_compat@groq"
        data["providers"] = {"mode": "gemini", "sidecar": pid, "sidecar_first": False, "creds": {
            pid: {"base_url": "https://api.groq.com/openai/v1", "model": GROQ_LADDER[0], "api_key": groq, "catalog": "groq"}}}
    p = BASE / "config" / "api_keys.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return bool(key)
