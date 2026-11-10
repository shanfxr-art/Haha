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


class Orb(QtWidgets.QWidget):
    N = 56

    def __init__(self):
        super().__init__()
        self.mode = "idle"
        self.level = [0.0] * self.N
        self.t0 = time.time()
        self.seed = [random.random() * 6.28 for _ in range(self.N)]
        self.setMinimumSize(320, 320)

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


class Hud(QtWidgets.QWidget):
    def __init__(self, bridge):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. PC")
        self.setStyleSheet("background:#0A0E13")
        self.orb = Orb(); self.card = Card()
        self.label = QtWidgets.QLabel("Ready"); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color:#EAF0F6;font-size:22px;letter-spacing:6px")
        self.conn = QtWidgets.QLabel("Connecting to hub..."); self.conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conn.setStyleSheet("color:#8C9AA8;font-size:13px")
        self.logv = QtWidgets.QLabel(""); self.logv.setStyleSheet("color:#8C9AA8;font-family:Consolas,monospace;font-size:12px")
        self.logv.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(28, 24, 28, 24)
        lay.addWidget(self.conn); lay.addWidget(self.orb, 1); lay.addWidget(self.label); lay.addWidget(self.card); lay.addWidget(self.logv)
        self.lines = []
        bridge.state.connect(self.set_state); bridge.log.connect(self.add_log)
        bridge.online.connect(self.set_online); bridge.card.connect(self.card.show_card)
        self.tick = QtCore.QTimer(self); self.tick.timeout.connect(self.orb.update); self.tick.start(33)

    def set_state(self, s):
        self.orb.set_mode(s); self.label.setText(LABELS.get(s, "Ready").upper())

    def set_online(self, ok):
        self.conn.setText("Hub online" if ok else "Hub offline, retrying")
        self.conn.setStyleSheet("color:%s;font-size:13px" % ("#4FD6A0" if ok else "#F2B35C"))

    def add_log(self, m):
        self.lines = (self.lines + [time.strftime("%H:%M:%S ") + m])[-6:]
        self.logv.setText("\n".join(self.lines))
