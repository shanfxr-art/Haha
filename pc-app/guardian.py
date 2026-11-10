"""Guardian: background watch over this PC and the owner's watched topics. Alerts go to the hub (-> phone/Telegram). Never asks anything."""
import threading, time

CPU, RAM, DISK = 92.0, 92.0, 95.0   # percent
CHECK_S, NEWS_S, COOLDOWN_S = 60, 1800, 1800


def start(alert):
    last = {}

    def fire(key, text):
        if time.time() - last.get(key, 0) >= COOLDOWN_S:
            last[key] = time.time()
            try: alert(text)
            except Exception: pass

    def loop():
        import psutil
        hot, nxt = 0, time.time() + 300
        while True:
            try:
                hot = hot + 1 if psutil.cpu_percent(interval=1) > CPU else 0
                if hot >= 3: fire("cpu", "CPU has been above %d%% for 3 minutes." % CPU)
                if psutil.virtual_memory().percent > RAM: fire("ram", "RAM is above %d%%." % RAM)
                if psutil.disk_usage("C:\\" if __import__("os").name == "nt" else "/").percent > DISK: fire("disk", "Disk is above %d%% full." % DISK)
                if time.time() >= nxt:
                    nxt = time.time() + NEWS_S
                    from actions import background_monitor as bm
                    for item in bm.check_all()[:5]: fire("news:" + item[:60], "Watched topic: " + item[:300])
            except Exception:
                pass
            time.sleep(CHECK_S - 1)

    threading.Thread(target=loop, daemon=True, name="guardian").start()
