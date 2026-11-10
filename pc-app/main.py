"""Jarvis PC app entry. Env: HUB_URL, PC_TOKEN. Runs with the sphere HUD, or headless if the HUD cannot start."""
import os, sys, threading, time
import core


def main():
    url, token = os.environ.get("HUB_URL", ""), os.environ.get("PC_TOKEN", "")
    if not url or not token:
        print("HUB_URL or PC_TOKEN is missing")
        return 1
    bridge = None
    app = None
    try:
        from PyQt6 import QtWidgets
        import hud
        app = QtWidgets.QApplication(sys.argv)
        bridge = hud.Bridge()
        win = hud.Hud(bridge)
        win.showMaximized()
    except Exception as e:  # no display or Qt: keep working without the screen
        print("HUD not started (%s), running headless" % str(e)[:200])
        app = None

    def emit(sig):
        return (lambda *a: getattr(bridge, sig).emit(*a)) if bridge else (lambda *a: None)

    reg = core.build_registry(hud_show=(lambda t, b, s: bridge.card.emit(t, b, s)) if bridge else None)
    log = emit("log")
    hub = core.Hub(url, token, reg, on_state=emit("state"), on_log=lambda m: (print(m, flush=True), log(m)), on_connection=emit("online"))
    threading.Thread(target=hub.run, daemon=True).start()
    if app:
        return app.exec()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    sys.exit(main())
