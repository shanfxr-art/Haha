"""Sphere HUD in the phone app's theme (aurora orb, spectrum ring). Needs PyQt6."""
import math, time, random
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QRadialGradient, QPainterPath, QPen, QFont, QBrush

BG = QColor("#0A0E13"); PANEL = QColor("#131A22"); CYAN = QColor("#6FB7FF"); VIOLET = QColor("#A48CFF")
MINT = QColor("#5EE6C8"); GREEN = QColor("#4FD6A0"); AMBER = QColor("#F2B35C"); DANGER = QColor("#F2707A")
DIM = QColor("#8C9AA8"); INK = QColor("#EAF0F6")
LABELS = {"idle": "Ready", "listening": "Listening", "thinking": "Thinking", "speaking": "Speaking"}


def rgba(c, a):
    return QColor(c.red(), c.green(), c.blue(), max(0, min(255, int(a))))


class Bridge(QtCore.QObject):
    """Hub threads call these; the signals deliver them on the GUI thread."""
    state = QtCore.pyqtSignal(str)
    log = QtCore.pyqtSignal(str)
    online = QtCore.pyqtSignal(bool)
    card = QtCore.pyqtSignal(str, str, int)
    agent = QtCore.pyqtSignal(str, str)   # kind, json


class Orb(QtWidgets.QWidget):
    N = 56

    def __init__(self):
        super().__init__()
        self.mode = "idle"
        self.level = [0.0] * self.N
        self.t0 = time.time()
        self.seed = [random.random() * 6.28 for _ in range(self.N)]
        self.setMinimumSize(240, 240)

    def set_mode(self, m):
        self.mode = m

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        t = time.time() - self.t0
        cx, cy = w / 2, h / 2
        R = min(w, h) * 0.30
        speed = {"idle": 0.35, "listening": 0.7, "thinking": 1.4, "speaking": 0.9}.get(self.mode, 0.35)

        # spectrum ring: idle = tiny dots, listening/speaking = bars that move, thinking = a turning arc
        for i in range(self.N):
            a = i / self.N * 2 * math.pi - math.pi / 2
            if self.mode in ("listening", "speaking"):
                tgt = 0.25 + 0.75 * abs(math.sin(t * 3.1 + self.seed[i] * 2 + i * 0.35)) * abs(math.sin(t * 1.3 + self.seed[i]))
            elif self.mode == "thinking":
                d = (i / self.N - (t * 0.6) % 1.0) % 1.0
                tgt = max(0.0, 0.9 - d * 3.0) if d < 0.3 else 0.0
            else:
                tgt = 0.0
            self.level[i] += (tgt - self.level[i]) * 0.25
            r0 = R * 1.18
            ln = 3 + self.level[i] * R * 0.38
            col = CYAN if self.mode != "speaking" else MINT
            pen = QPen(rgba(col, 90 + 150 * self.level[i]), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx + math.cos(a) * r0, cy + math.sin(a) * r0), QPointF(cx + math.cos(a) * (r0 + ln), cy + math.sin(a) * (r0 + ln)))

        # glass sphere
        path = QPainterPath(); path.addEllipse(QPointF(cx, cy), R, R)
        base = QRadialGradient(QPointF(cx - R * 0.3, cy - R * 0.4), R * 1.4)
        base.setColorAt(0, QColor("#1B242E")); base.setColorAt(1, QColor("#070A0E"))
        p.fillPath(path, QBrush(base))

        # aurora: three soft blobs drifting in opposite directions, added together
        p.save(); p.setClipPath(path); p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for k, (col, ph, dirn) in enumerate(((CYAN, 0.0, 1), (VIOLET, 2.1, -1), (MINT, 4.2, 1))):
            ang = dirn * t * speed + ph
            bx, by = cx + math.cos(ang) * R * 0.38, cy + math.sin(ang * 1.2) * R * 0.38
            rad = R * (0.85 + 0.12 * math.sin(t * speed * 1.7 + k))
            g = QRadialGradient(QPointF(bx, by), rad)
            g.setColorAt(0, rgba(col, 120 if self.mode != "idle" else 85)); g.setColorAt(1, rgba(col, 0))
            p.fillRect(QRectF(cx - R, cy - R, 2 * R, 2 * R), QBrush(g))
        p.restore()

        # rim light and one small specular glint
        rim = QRadialGradient(QPointF(cx, cy), R)
        rim.setColorAt(0.86, rgba(INK, 0)); rim.setColorAt(1.0, rgba(INK, 70))
        p.fillPath(path, QBrush(rim))
        p.setPen(QPen(rgba(INK, 60), 1.2)); p.drawEllipse(QPointF(cx, cy), R, R)
        gl = QRadialGradient(QPointF(cx - R * 0.42, cy - R * 0.5), R * 0.22)
        gl.setColorAt(0, rgba(INK, 150)); gl.setColorAt(1, rgba(INK, 0))
        p.fillRect(QRectF(cx - R, cy - R, 2 * R, 2 * R), QBrush(gl))
        p.end()


class Card(QtWidgets.QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QFrame{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.10);border-radius:16px}"
                           "QLabel{background:transparent;border:none}")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 14)
        self.t = QtWidgets.QLabel(); self.t.setStyleSheet("color:#6FB7FF;font-size:13px;font-weight:600;letter-spacing:2px")
        self.b = QtWidgets.QLabel(); self.b.setWordWrap(True); self.b.setStyleSheet("color:#EAF0F6;font-size:17px")
        lay.addWidget(self.t); lay.addWidget(self.b)
        self.timer = QtCore.QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.hide)
        self.hide()

    def show_card(self, title, body, secs):
        self.t.setText(title.upper()); self.b.setText(body); self.show()
        if secs > 0:
            self.timer.start(secs * 1000)


class Panel(QtWidgets.QFrame):
    """Glass panel: title + body label (rich text allowed)."""
    def __init__(self, title, mono=False, grow=True):
        super().__init__()
        self.setStyleSheet("Panel{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.09);border-radius:16px}QLabel{background:transparent;border:none}")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(6)
        t = QtWidgets.QLabel(title.upper()); t.setStyleSheet("color:#6FB7FF;font-size:11px;font-weight:600;letter-spacing:3px")
        self.body = QtWidgets.QLabel(); self.body.setWordWrap(True); self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body.setStyleSheet("color:#EAF0F6;font-size:13px;" + ("font-family:Consolas,monospace;" if mono else ""))
        lay.addWidget(t); lay.addWidget(self.body, 1)
        if not grow:
            self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum)

    def set(self, html):
        self.body.setText(html)


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Hud(QtWidgets.QWidget):
    """Left: orb, state, link, system meters. Right: mission + sub-agents, activity log, memory, cards."""
    def __init__(self, bridge):
        super().__init__()
        import json
        self._json = json
        self.setWindowTitle("J.A.R.V.I.S. PC")
        self.setStyleSheet("background:#0A0E13")
        self.orb = Orb(); self.card = Card()
        self.label = QtWidgets.QLabel("READY"); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color:#EAF0F6;font-size:22px;letter-spacing:6px")
        self.conn = QtWidgets.QLabel("Connecting to hub..."); self.conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conn.setStyleSheet("color:#8C9AA8;font-size:13px")
        self.sysp = Panel("System", True, False); self.mis = Panel("Mission"); self.logp = Panel("Activity", True); self.memp = Panel("Memory")
        left = QtWidgets.QVBoxLayout(); left.addWidget(self.conn); left.addWidget(self.orb, 1); left.addWidget(self.label); left.addWidget(self.sysp)
        right = QtWidgets.QGridLayout(); right.setSpacing(14)
        right.addWidget(self.card, 0, 0, 1, 2); right.addWidget(self.mis, 1, 0, 1, 2); right.addWidget(self.logp, 2, 0); right.addWidget(self.memp, 2, 1)
        right.setRowStretch(1, 2); right.setRowStretch(2, 3)
        lay = QtWidgets.QHBoxLayout(self); lay.setContentsMargins(24, 22, 24, 22); lay.setSpacing(22)
        lay.addLayout(left, 2); lay.addLayout(right, 5)
        self.lines = []; self.goal = ""; self.workers = {}; self.tasks = []; self.result = ""
        bridge.state.connect(self.set_state); bridge.log.connect(self.add_log)
        bridge.online.connect(self.set_online); bridge.card.connect(self.card.show_card); bridge.agent.connect(self.on_agent)
        self.tick = QtCore.QTimer(self); self.tick.timeout.connect(self.orb.update); self.tick.start(33)
        self.slow = QtCore.QTimer(self); self.slow.timeout.connect(self.refresh); self.slow.start(2500); self.refresh()
        self.mis.set("<span style='color:#8C9AA8'>No mission. Tell Jarvis what to do.</span>")

    def set_state(self, s):
        self.orb.set_mode(s); self.label.setText(LABELS.get(s, "Ready").upper())

    def set_online(self, ok):
        self.conn.setText("Hub online" if ok else "Hub offline, retrying")
        self.conn.setStyleSheet("color:%s;font-size:13px" % ("#4FD6A0" if ok else "#F2B35C"))

    def add_log(self, m):
        self.lines = (self.lines + [time.strftime("%H:%M:%S ") + m])[-40:]
        self.logp.set("<br>".join(_esc(x) for x in self.lines[-14:]))

    def on_agent(self, kind, raw):
        try:
            d = self._json.loads(raw)
        except Exception:
            return
        if kind == "mission":
            self.goal, self.tasks, self.workers, self.result = d.get("goal", ""), [], {}, ""
        elif kind == "plan":
            self.tasks = d.get("tasks", [])
        elif kind == "worker":
            self.workers[d.get("i", 0)] = d
        elif kind == "end":
            self.result = d.get("result", "")
        self.draw_mission()

    def draw_mission(self):
        rows = ["<b style='color:#6FB7FF'>%s</b>" % _esc(self.goal[:140])]
        for i, t in enumerate(self.tasks):
            w = self.workers.get(i, {})
            st = w.get("state", "queued")
            col = {"done": "#4FD6A0", "running": "#F2B35C"}.get(st, "#8C9AA8")
            tail = (" &middot; %s step %s" % (_esc(w.get("tool", "")), w.get("step", ""))) if st == "running" else ""
            rows.append("<span style='color:%s'>&#9679;</span> Agent %d &middot; %s%s<br><span style='color:#8C9AA8'>%s</span>" % (col, i + 1, st, tail, _esc(t[:110])))
        if self.result:
            rows.append("<span style='color:#4FD6A0'>Result:</span> %s" % _esc(self.result[:200]))
        self.mis.set("<br>".join(rows))

    def refresh(self):
        try:
            import psutil
            self.sysp.set("CPU %d%%<br>RAM %d%%<br>Disk %d%%" % (psutil.cpu_percent(), psutil.virtual_memory().percent, psutil.disk_usage("C:\\" if __import__("os").name == "nt" else "/").percent))
        except Exception:
            pass
        try:
            from memory import memory_manager as mm
            e = mm.all_entries_for_ui()[-8:]
            self.memp.set("<br>".join("<span style='color:#8C9AA8'>%s</span> %s" % (_esc(x.get("key", "")), _esc(str(x.get("value", ""))[:60])) for x in e) or "<span style='color:#8C9AA8'>Empty</span>")
        except Exception:
            pass
