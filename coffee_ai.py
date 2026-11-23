import sys, io, base64, math, random, json, time
import urllib.request, urllib.error
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QFrame, QTextEdit)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QCursor
from PIL import ImageGrab, Image

PROXY_URL = 'https://gentle-base-e6e8coffee-proxy.piksarmult.workers.dev'

class AIWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, prompt, image=None):
        super().__init__()
        self.prompt = prompt
        self.image = image

    def run(self):
        parts = [{"text": self.prompt}]
        if self.image is not None:
            buf = io.BytesIO()
            self.image.save(buf, format="JPEG", quality=80)
            b64_img = base64.b64encode(buf.getvalue()).decode("ascii")
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64_img
                }
            })

        payload = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")

        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    PROXY_URL,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("text"):
                        self.finished.emit(data["text"].replace("**", "").strip())
                        return
                    err = data.get("error", "Невідома відповідь сервера")
                    self.finished.emit(f"Помилка: {err[:100]}")
                    return
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                if ("429" in body or "RESOURCE_EXHAUSTED" in body) and attempt == 0:
                    time.sleep(2.0)
                    continue
                if "429" in body or "RESOURCE_EXHAUSTED" in body:
                    self.finished.emit("Тимчасово вичерпано ліміт запитів Google API. Зачекай хвилину ☕")
                else:
                    self.finished.emit(f"Помилка сервера ({e.code}): {body[:90]}")
                return
            except Exception as ex:
                self.finished.emit(f"Немає зв'язку з сервером: {str(ex)[:90]}")
                return

class CartoonCoffeeAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(340, 410)
        self.drag_pos = QPoint()
        self.click_start = QPoint()
        self.bounce_step = 0
        self.eye_dx = 0.0
        self.eye_dy = 0.0
        self.last_cursor = QCursor.pos()
        self.idle_ticks = 0
        self.idle_target = (0.0, 0.0)
        self.worker = None
        self.init_ui()
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(45)

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        
        self.bubble = QFrame(self)
        self.bubble.setObjectName("mainBubble")
        self.bubble.setStyleSheet('''
            QFrame#mainBubble { background-color: #ffffff; border: 2.5px solid #1a1a1a; border-radius: 18px; padding: 8px; }
            QTextEdit { color: #1a1a1a; font-family: 'Segoe UI'; font-size: 12px; border: none; background: transparent; }
            QScrollBar:vertical { border: none; background: #f5ebe0; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #b5651d; border-radius: 3px; }
            QLineEdit { border: 1.5px solid #bcaaa4; border-radius: 8px; padding: 5px 8px; font-size: 12px; color: #1a1a1a; background: #fff; }
            QPushButton { background-color: #b5651d; color: white; border: 1.5px solid #1a1a1a; border-radius: 8px; padding: 5px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #965215; }
        ''')
        bl = QVBoxLayout(self.bubble)
        bl.setSpacing(6)

        self.msg_box = QTextEdit()
        self.msg_box.setReadOnly(True)
        self.msg_box.setText('Привіт! Я Кофі ☕ Завжди на зв’язку і стежу за курсором 👀 Запитай щось!')
        self.msg_box.setMinimumHeight(85)
        self.msg_box.setMaximumHeight(135)
        bl.addWidget(self.msg_box)

        row1 = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText('Напиши запитання...')
        self.input_field.returnPressed.connect(self.ask_text)
        row1.addWidget(self.input_field)
        b_send = QPushButton('➤')
        b_send.clicked.connect(self.ask_text)
        row1.addWidget(b_send)
        bl.addLayout(row1)

        row2 = QHBoxLayout()
        b_scan = QPushButton('👀 Що не так?')
        b_scan.clicked.connect(self.analyze_screen)
        row2.addWidget(b_scan)

        b_hide = QPushButton('🔽')
        b_hide.setToolTip('Сховати віконце')
        b_hide.clicked.connect(lambda: self.bubble.setVisible(False))
        row2.addWidget(b_hide)

        b_close = QPushButton('✖')
        b_close.setStyleSheet('background-color: #757575;')
        b_close.setToolTip('Закрити програму')
        b_close.clicked.connect(QApplication.quit)
        row2.addWidget(b_close)
        bl.addLayout(row2)

        self.layout.addWidget(self.bubble)
        self.layout.addSpacing(125)

    def update_animation(self):
        self.bounce_step = (self.bounce_step + 1) % 40
        cur = QCursor.pos()
        if cur != self.last_cursor:
            self.last_cursor = cur
            self.idle_ticks = 0
            global_eye = self.mapToGlobal(QPoint(self.width() - 62, self.height() - 60))
            vx = cur.x() - global_eye.x()
            vy = cur.y() - global_eye.y()
            angle = math.atan2(vy, vx)
            dist = min(2.8, math.hypot(vx, vy) / 42.0)
            target_dx = math.cos(angle) * dist
            target_dy = math.sin(angle) * dist * 1.4
        else:
            self.idle_ticks += 1
            if self.idle_ticks % 20 == 0:
                self.idle_target = random.choice([
                    (-2.6, -0.6), (2.6, -0.6), (0.0, -2.8), (-2.2, 2.2), (2.2, 2.2), (0.0, 0.0)
                ])
            target_dx, target_dy = self.idle_target

        self.eye_dx += (target_dx - self.eye_dx) * 0.35
        self.eye_dy += (target_dy - self.eye_dy) * 0.35
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        dy = -2 if self.bounce_step < 20 else 0
        cx = self.width() - 62
        cy = self.height() - 115 + dy

        outline = QPen(QColor('#141414'), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        p.setPen(outline)
        p.setBrush(QColor('#ffffff'))
        cup = QPainterPath()
        cup.moveTo(cx - 27, cy + 20)
        cup.lineTo(cx + 27, cy + 20)
        cup.lineTo(cx + 21, cy + 96)
        cup.quadTo(cx, cy + 102, cx - 21, cy + 96)
        cup.closeSubpath()
        p.drawPath(cup)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#e0e0e0'))
        shadow = QPainterPath()
        shadow.moveTo(cx + 15, cy + 22)
        shadow.lineTo(cx + 25, cy + 22)
        shadow.lineTo(cx + 19, cy + 95)
        shadow.lineTo(cx + 11, cy + 96)
        shadow.closeSubpath()
        p.drawPath(shadow)

        p.setPen(outline)
        p.setBrush(QColor('#b5651d'))
        sleeve = QPainterPath()
        sleeve.moveTo(cx - 26, cy + 36)
        sleeve.quadTo(cx, cy + 41, cx + 26, cy + 36)
        sleeve.lineTo(cx + 23, cy + 79)
        sleeve.quadTo(cx, cy + 84, cx - 23, cy + 79)
        sleeve.closeSubpath()
        p.drawPath(sleeve)

        p.setPen(QPen(QColor('#e6a15c'), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(int(cx + 17), int(cy + 43), int(cx + 15), int(cy + 73))

        p.setPen(outline)
        p.setBrush(QColor('#1c1c1c'))
        p.drawRoundedRect(QRectF(cx - 32, cy + 12, 64, 10), 5, 5)
        lid_top = QPainterPath()
        lid_top.moveTo(cx - 29, cy + 12)
        lid_top.lineTo(cx - 24, cy + 3)
        lid_top.quadTo(cx, cy, cx + 24, cy + 3)
        lid_top.lineTo(cx + 29, cy + 12)
        lid_top.closeSubpath()
        p.drawPath(lid_top)

        p.setPen(QPen(QColor('#ffffff'), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx - 22, cy + 4, 24, 6), 120 * 16, 60 * 16)
        p.drawLine(int(cx - 27), int(cy + 16), int(cx - 10), int(cy + 16))

        brow_shift = self.eye_dy * 0.45
        p.setPen(QPen(QColor('#141414'), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx - 16, cy + 39 + brow_shift, 12, 6), 25 * 16, 130 * 16)
        p.drawArc(QRectF(cx + 4, cy + 39 + brow_shift, 12, 6), 25 * 16, 130 * 16)

        lash_pen = QPen(QColor('#141414'), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(lash_pen)
        p.drawLine(int(cx - 14), int(cy + 48), int(cx - 18), int(cy + 45))
        p.drawLine(int(cx - 15), int(cy + 51), int(cx - 20), int(cy + 49))
        p.drawLine(int(cx - 15), int(cy + 54), int(cx - 19), int(cy + 53))

        p.drawLine(int(cx + 14), int(cy + 48), int(cx + 18), int(cy + 45))
        p.drawLine(int(cx + 15), int(cy + 51), int(cx + 20), int(cy + 49))
        p.drawLine(int(cx + 15), int(cy + 54), int(cx + 19), int(cy + 53))

        p.setPen(QPen(QColor('#141414'), 2.1))
        p.setBrush(QColor('#ffffff'))
        p.drawEllipse(QRectF(cx - 14.5, cy + 44, 14.5, 21))
        p.drawEllipse(QRectF(cx, cy + 44, 14.5, 21))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#141414'))
        p.drawPie(QRectF(cx - 10.5 + self.eye_dx, cy + 48 + self.eye_dy, 8.2, 13.5), 215 * 16, 290 * 16)
        p.drawPie(QRectF(cx + 3.5 + self.eye_dx, cy + 48 + self.eye_dy, 8.2, 13.5), 215 * 16, 290 * 16)

        p.setPen(QPen(QColor('#141414'), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        smile = QPainterPath()
        smile.moveTo(cx - 11, cy + 68)
        smile.quadTo(cx, cy + 77, cx + 11, cy + 68)
        p.drawPath(smile)
        p.drawArc(QRectF(cx - 13, cy + 66, 4, 4), 110 * 16, 140 * 16)
        p.drawArc(QRectF(cx + 9, cy + 66, 4, 4), 290 * 16, 140 * 16)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.click_start = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        if (e.globalPosition().toPoint() - self.click_start).manhattanLength() < 8:
            pos = e.position().toPoint()
            if pos.x() > self.width() - 120 and pos.y() > self.height() - 135:
                self.bubble.setVisible(not self.bubble.isVisible())

    def on_ai_reply(self, text):
        self.msg_box.setText(text)

    def analyze_screen(self):
        self.msg_box.setText('Дивлюся на екран... ⚡👀')
        self.hide()
        QApplication.processEvents()
        shot = ImageGrab.grab()
        self.show()

        w, h = shot.size
        if w > 1280:
            shot = shot.resize((1280, int(h * (1280 / w))), Image.Resampling.BILINEAR)

        prompt = 'Ти маленький офісний помічник Кофі. Подивись на екран: якщо є помилка — коротко вкажи її. Інакше дай 1 коротку пораду (до 2 речень українською).'
        self.worker = AIWorker(prompt, shot)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

    def ask_text(self):
        txt = self.input_field.text().strip()
        if not txt: return
        self.input_field.clear()
        self.msg_box.setText('Думаю... ⚡')
        prompt = f'Відповідай стисло українською як помічник Кофі: {txt}'
        self.worker = AIWorker(prompt)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = CartoonCoffeeAssistant()
    w.show()
    sys.exit(app.exec())
