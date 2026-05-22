from collections import deque
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient, QPainterPath, QBrush

from ui.style import T

class StatCard(QWidget):
    def __init__(self, title: str, unit: str, color: str = None, parent=None):
        super().__init__(parent)
        self._color = color or T['accent']
        self.setMinimumWidth(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setStyleSheet(f"color:{T['muted2']};font-size:9px;letter-spacing:1.5px;font-weight:bold;")

        self._val_lbl = QLabel('—')
        self._val_lbl.setStyleSheet(f"color:{self._color};font-size:22px;font-weight:900;")

        self._unit_lbl = QLabel(unit)
        self._unit_lbl.setStyleSheet(f"color:{T['muted2']};font-size:10px;")

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._val_lbl)
        layout.addWidget(self._unit_lbl)

        self.setStyleSheet(f"""
            StatCard {{
                background:{T['surface2']};
                border:1px solid {T['border']};
                border-radius:8px;
            }}
        """)

    def set_value(self, v, decimals: int = 0):
        if isinstance(v, float):
            v_str = f'{v:.{decimals}f}'
        elif v is None:
            v_str = '—'
        else:
            v_str = str(v)
        self._val_lbl.setText(v_str)
        fs = 22 if len(v_str) <= 5 else 18 if len(v_str) <= 8 else 14
        self._val_lbl.setStyleSheet(f"color:{self._color};font-size:{fs}px;font-weight:900;")

    def set_color(self, color: str):
        self._color = color
        v_str = self._val_lbl.text()
        fs = 22 if len(v_str) <= 5 else 18 if len(v_str) <= 8 else 14
        self._val_lbl.setStyleSheet(f"color:{color};font-size:{fs}px;font-weight:900;")

    def set_unit(self, unit: str):
        self._unit_lbl.setText(unit)


class TempGraph(QWidget):
    """Scrolling line graph for one value, ported from v1."""
    def __init__(self, label: str, unit: str, max_val: float,
                 color: str = None, history: int = 60, parent=None):
        super().__init__(parent)
        self._label   = label
        self._unit    = unit
        self._max_val = max_val
        self._color   = color or T['accent']
        self._history = deque([0.0] * history, maxlen=history)
        self.setMinimumHeight(120)

    def push(self, value: float):
        self._history.append(value)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h  = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 44, 12, 10, 24
        iw = w - pad_l - pad_r
        ih = h - pad_t  - pad_b

        # Background
        p.fillRect(0, 0, w, h, QColor(T['surface2']))

        hist = list(self._history)
        # Hybrid auto-scaling: use self._max_val as minimum max limit, grow if data exceeds it
        current_max = max(hist) if hist else 0.0
        scale_max = max(self._max_val, current_max) or 1.0

        # Grid lines
        pen = QPen(QColor(T['border']))
        pen.setWidth(1)
        p.setPen(pen)
        for pct in (0.25, 0.5, 0.75, 1.0):
            y = pad_t + ih - int(pct * ih)
            p.drawLine(pad_l, y, w - pad_r, y)
            lbl = f'{int(scale_max * pct)}'
            p.setPen(QPen(QColor(T['muted2'])))
            p.setFont(QFont('monospace', 8))
            p.drawText(0, y + 5, pad_l - 4, 12, Qt.AlignRight, lbl)
            p.setPen(pen)

        # Data
        n = len(hist)
        if n < 2:
            return

        def pt(i, v):
            x = pad_l + int(i / (n - 1) * iw)
            y = pad_t + ih - int(max(0.0, min(v, scale_max)) / scale_max * ih)
            return QPointF(x, y)

        pts = [pt(i, v) for i, v in enumerate(hist)]

        # Fill
        path = QPainterPath()
        path.moveTo(pts[0].x(), pad_t + ih)
        for pp in pts:
            path.lineTo(pp)
        path.lineTo(pts[-1].x(), pad_t + ih)
        path.closeSubpath()
        grad = QLinearGradient(0, pad_t, 0, pad_t + ih)
        c = QColor(self._color)
        c.setAlpha(50); grad.setColorAt(0, c)
        c.setAlpha(5);  grad.setColorAt(1, c)
        p.fillPath(path, QBrush(grad))

        # Line
        lpen = QPen(QColor(self._color)); lpen.setWidth(2)
        p.setPen(lpen)
        for i in range(1, len(pts)):
            p.drawLine(pts[i-1], pts[i])

        # Labels
        p.setPen(QPen(QColor(T['muted2'])))
        p.setFont(QFont('monospace', 8))
        p.drawText(pad_l, h - 4, f'{self._label}')
        cur = hist[-1]
        p.setPen(QPen(QColor(self._color)))
        p.setFont(QFont('monospace', 9))
        p.drawText(w - 70, pad_t + 14, f'{cur:.1f}{self._unit}')


class FanCurveWidget(QWidget):
    """Drag-to-edit fan curve canvas, ported from v1."""
    from PySide6.QtCore import Signal
    curve_changed   = Signal(list)  # fires every drag pixel — visual preview only
    curve_committed = Signal(list)  # fires on mouse release — update daemon + save

    PRESETS = {
        'silent':      [(30,20),(45,25),(60,35),(70,50),(80,70),(90,100)],
        'balanced':    [(30,30),(45,40),(60,55),(70,70),(80,85),(90,100)],
        'performance': [(30,50),(45,60),(60,75),(70,88),(80,100),(90,100)],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = list(self.PRESETS['balanced'])
        self.drag_idx = -1
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def set_preset(self, name: str):
        if name in self.PRESETS:
            self.points = list(self.PRESETS[name])
            self.update()
            # Preset selection is a committed action — emit both signals
            self.curve_changed.emit(self.points)
            self.curve_committed.emit(self.points)

    def set_points(self, pts):
        self.points = sorted(pts, key=lambda p: p[0])
        self.update()

    def paintEvent(self, _):
        p   = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad  = 44
        iw   = w - pad * 2
        ih   = h - pad * 2

        p.fillRect(0, 0, w, h, QColor(T['surface2']))

        # Grid
        pen_g = QPen(QColor(T['border'])); pen_g.setWidth(1)
        p.setFont(QFont('monospace', 8))
        for i in range(5):
            pct = i / 4
            # Vertical (temp)
            x = pad + int(pct * iw)
            p.setPen(pen_g); p.drawLine(x, pad, x, pad + ih)
            p.setPen(QPen(QColor(T['muted2'])))
            p.drawText(x - 14, pad + ih + 14, f'{int(30 + pct * 80)}°')
            # Horizontal (duty)
            y = pad + int((1 - pct) * ih)
            p.setPen(pen_g); p.drawLine(pad, y, pad + iw, y)
            p.setPen(QPen(QColor(T['muted2'])))
            p.drawText(0, y + 5, pad - 4, 12, Qt.AlignRight, f'{int(pct*100)}%')

        # Danger zone (>85°C)
        x85 = pad + int((85 - 30) / 80 * iw)
        p.fillRect(x85, pad, pad + iw - x85, ih, QColor(255, 51, 85, 18))

        # Curve fill + line
        pts = [QPointF(pad + (t - 30) / 80 * iw,
                        pad + ih - (d / 100 * ih))
               for t, d in self.points]

        path = QPainterPath()
        path.moveTo(pts[0].x(), pad + ih)
        for pp in pts:
            path.lineTo(pp)
        path.lineTo(pts[-1].x(), pad + ih)
        path.closeSubpath()
        grad = QLinearGradient(0, pad, 0, pad + ih)
        c = QColor(T['accent']); c.setAlpha(45); grad.setColorAt(0, c)
        c.setAlpha(5);           grad.setColorAt(1, c)
        p.fillPath(path, QBrush(grad))

        lp = QPen(QColor(T['accent'])); lp.setWidth(2)
        p.setPen(lp)
        for i in range(1, len(pts)):
            p.drawLine(pts[i-1], pts[i])

        # Control points
        for i, pp in enumerate(pts):
            p.setBrush(QBrush(QColor(T['accent'])))
            p.setPen(QPen(QColor(T['bg']), 2))
            p.drawEllipse(pp, 6, 6)
            # Tooltip
            t, d = self.points[i]
            p.setPen(QPen(QColor(T['muted2'])))
            p.setFont(QFont('monospace', 7))
            p.drawText(int(pp.x()) - 16, int(pp.y()) - 10, f'{t}°/{d}%')

    def _pt_at(self, pos):
        w, h = self.width(), self.height()
        pad = 44; iw = w - pad*2; ih = h - pad*2
        for i, (t, d) in enumerate(self.points):
            x = pad + (t - 30) / 80 * iw
            y = pad + ih - (d / 100 * ih)
            if (QPointF(x, y) - pos).manhattanLength() < 15:
                return i
        return -1

    def _px_to_val(self, pos):
        w, h = self.width(), self.height()
        pad = 44; iw = w - pad*2; ih = h - pad*2
        t = 30 + (pos.x() - pad) / iw * 80
        d = 100 - (pos.y() - pad) / ih * 100
        return max(30, min(110, round(t))), max(0, min(100, round(d)))

    def mousePressEvent(self, e):
        self.drag_idx = self._pt_at(e.position())

    def mouseMoveEvent(self, e):
        if self.drag_idx >= 0:
            t, d = self._px_to_val(e.position())
            self.points[self.drag_idx] = (t, d)
            self.points.sort(key=lambda x: x[0])
            self.drag_idx = next((i for i, p in enumerate(self.points) if p == (t, d)),
                                  self.drag_idx)
            self.update()
            self.curve_changed.emit(self.points)

    def mouseReleaseEvent(self, _):
        if self.drag_idx >= 0:
            # Drag ended — emit committed signal once with final position
            self.curve_committed.emit(self.points)
        self.drag_idx = -1


def make_sep():
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f'background:{T["border"]};max-height:1px;border:none;')
    return f

def status_label() -> QLabel:
    lbl = QLabel('')
    lbl.setStyleSheet(f'font-size:11px;min-height:18px;')
    return lbl

def set_status(lbl: QLabel, msg: str, kind: str = 'ok'):
    colors = {'ok': T['green'], 'err': T['danger'], 'warn': T['warn'], 'info': T['muted2']}
    icons  = {'ok': '✓', 'err': '✗', 'warn': '⚠', 'info': '·'}
    lbl.setStyleSheet(f'color:{colors.get(kind, T["text"])};font-size:11px;')
    lbl.setText(f'{icons.get(kind, "")}  {msg}')
