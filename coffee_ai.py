import sys, os
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QFrame, QInputDialog
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient, QPainterPath
from PIL import ImageGrab
from google import genai

KEY_FILE = os.path.join(os.path.expanduser('~'), 'coffee_key.txt')

def get_key():
    if os.path.exists(KEY_FILE):
        return open(KEY_FILE, 'r', encoding='utf-8').read().strip()
    return ''

# Окремий фоновий потік для ШІ, щоб інтерфейс ніколи не зависав
class AIWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, key, prompt, image=None):
        super().__init__()
        self.key = key
        self.prompt = prompt
        self.image = image

    def run(self):
        try:
            client = genai.Client(api_key=self.key)
            contents = [self.image, self.prompt] if self.image else self.prompt
            res = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
            self.finished.emit(res.text)
        except Exception as e:
            self.finished.emit(f"Помилка: {str(e)[:80]}")

class ThermosAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(350, 430)
        self.drag_pos = QPoint()
        self.steam_offset = 0
        self.worker = None
        self.init_ui()
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(80)

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.bubble = QFrame(self)
        self.bubble.setStyleSheet('''
            QFrame { background-color: #ffffff; border: 2px solid #6f4e37; border-radius: 16px; padding: 8px; }
            QLabel { color: #3e2723; font-family: Segoe UI; font-size: 12px; border: none; }
            QLineEdit { border: 1px solid #d7ccc8; border-radius: 8px; padding: 5px 8px; font-size: 12px; color: #3e2723; }
            QPushButton { background-color: #6f4e37; color: white; border-radius: 8px; padding: 6px 10px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #5a3e2b; }
        ''')
        bl = QVBoxLayout(self.bubble)
        start_text = 'Привіт! Натисни 🔑 нижче, щоб вставити ключ Gemini API.' if not get_key() else 'Привіт! Готовий до роботи ☕ Натисни на кружку, щоб сховати меню.'
        self.msg_label = QLabel(start_text)
        self.msg_label.setWordWrap(True)
        bl.addWidget(self.msg_label)

        row1 = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText('Запитай або запиши справу...')
        self.input_field.returnPressed.connect(self.ask_text)
        row1.addWidget(self.input_field)
        b_send = QPushButton('➤')
        b_send.clicked.connect(self.ask_text)
        row1.addWidget(b_send)
        bl.addLayout(row1)

        row2 = QHBoxLayout()
        b_scan = QPushButton('👀 Що не так на екрані?')
        b_scan.clicked.connect(self.analyze_screen)
        row2.addWidget(b_scan)
        b_key = QPushButton('🔑')
        b_key.setToolTip('Вставити API ключ')
        b_key.clicked.connect(self.set_key)
        row2.addWidget(b_key)
        b_close = QPushButton('✖')
        b_close.setStyleSheet('background-color: #a1887f; padding: 6px 8px;')
        b_close.clicked.connect(QApplication.quit)
        row2.addWidget(b_close)
        bl.addLayout(row2)

        self.layout.addWidget(self.bubble)
        self.layout.addSpacing(155)

    def set_key(self):
        text, ok = QInputDialog.getText(self, 'Ключ Gemini API', 'Встав свій ключ (AIza...):', text=get_key())
        if ok and text.strip():
            open(KEY_FILE, 'w', encoding='utf-8').write(text.strip())
            self.msg_label.setText('Ключ збережено! Тепер я готовий працювати 🧠☕')

    def update_animation(self):
        self.steam_offset = (self.steam_offset + 1) % 30
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() - 85, self.height() - 145
        p.setPen(QPen(QColor(161, 136, 127, 170), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, dx in enumerate([-14, 0, 14]):
            ys = (self.steam_offset + i * 8) % 25
            path = QPainterPath()
            path.moveTo(cx + dx, cy - 5 - ys)
            path.quadTo(cx + dx - 6, cy - 15 - ys, cx + dx, cy - 25 - ys)
            p.drawPath(path)
        p.setPen(QPen(QColor('#37474f'), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawRoundedRect(QRectF(cx + 25, cy + 25, 25, 50), 10, 10)
        grad = QLinearGradient(cx - 38, cy, cx + 38, cy)
        grad.setColorAt(0, QColor('#3e2723'))
        grad.setColorAt(0.4, QColor('#6d4c41'))
        grad.setColorAt(1, QColor('#2c1b18'))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        body = QPainterPath()
        body.moveTo(cx - 38, cy + 12)
        body.lineTo(cx + 38, cy + 12)
        body.lineTo(cx + 30, cy + 115)
        body.lineTo(cx - 30, cy + 115)
        body.closeSubpath()
        p.drawPath(body)
        p.setBrush(QColor('#b0bec5'))
        p.drawRoundedRect(QRectF(cx - 30, cy + 112, 60, 12), 5, 5)
        p.drawEllipse(QRectF(cx - 39, cy + 4, 78, 18))
        p.setBrush(QColor('#26140e'))
        p.drawEllipse(QRectF(cx - 33, cy + 7, 66, 12))
        p.setBrush(QColor('#ffffff'))
        p.drawEllipse(QRectF(cx - 22, cy + 45, 16, 16))
        p.drawEllipse(QRectF(cx + 6, cy + 45, 16, 16))
        p.setBrush(QColor('#1a1a1a'))
        p.drawEllipse(QRectF(cx - 17, cy + 50, 7, 7))
        p.drawEllipse(QRectF(cx + 11, cy + 50, 7, 7))
        p.setPen(QPen(QColor('#ffffff'), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        smile = QPainterPath()
        smile.moveTo(cx - 8, cy + 72)
        smile.quadTo(cx, cy + 80, cx + 8, cy + 72)
        p.drawPath(smile)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.click_start = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        if (e.globalPosition().toPoint() - self.click_start).manhattanLength() < 5:
            self.bubble.setVisible(not self.bubble.isVisible())

    def on_ai_reply(self, text):
        self.msg_label.setText(text)

    def analyze_screen(self):
        key = get_key()
        if not key:
            self.set_key()
            return
        self.msg_label.setText('Дивлюся на екран... 🔍☕')
        self.hide()
        QApplication.processEvents()
        shot = ImageGrab.grab()
        self.show()

        prompt = 'Ти маленький помічник Кофі. Подивись на екран: якщо є помилка в тексті, коді чи таблиці — скажи, що не так. Інакше дай коротку корисну пораду (2-3 речення українською).'
        self.worker = AIWorker(key, prompt, shot)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

    def ask_text(self):
        txt = self.input_field.text().strip()
        if not txt: return
        key = get_key()
        if not key:
            self.set_key()
            return
        self.input_field.clear()
        self.msg_label.setText('Думаю... ☕')
        prompt = f'Відповідай коротко (2-3 речення) українською як офісний помічник Кофі: {txt}'
        self.worker = AIWorker(key, prompt)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = ThermosAssistant()
    w.show()
    sys.exit(app.exec())
