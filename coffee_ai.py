import sys, os
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient, QPainterPath
from PIL import ImageGrab
from google import genai

KEY_FILE = os.path.join(os.path.expanduser('~'), 'coffee_key.txt')

def get_key():
    if os.path.exists(KEY_FILE):
        return open(KEY_FILE, 'r', encoding='utf-8').read().strip()
    return ''

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
            
            # Збираємо актуальні моделі 3-го покоління та всі доступні моделі для цього ключа
            candidates = ['gemini-3.1-flash-lite-preview', 'gemini-3-flash-preview', 'gemini-3.1-pro-preview']
            try:
                for m in client.models.list():
                    name = m.name.replace('models/', '')
                    if 'gemini' in name and 'embedding' not in name and 'imagen' not in name and name not in candidates:
                        candidates.append(name)
            except Exception:
                pass

            last_err = "Не знайдено робочої моделі"
            for model_name in candidates:
                try:
                    res = client.models.generate_content(model=model_name, contents=contents)
                    if res and res.text:
                        self.finished.emit(res.text)
                        return
                except Exception as e:
                    last_err = str(e)
                    # Якщо проблема саме в ключі — зупиняємось одразу
                    if 'API_KEY_INVALID' in last_err or '400' in last_err:
                        break
                    continue

            self.finished.emit(f"Помилка: {last_err[:100]}")
        except Exception as e:
            self.finished.emit(f"Помилка: {str(e)[:100]}")

class ThermosAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(350, 460)
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
            QLineEdit { border: 1px solid #d7ccc8; border-radius: 8px; padding: 5px 8px; font-size: 12px; color: #3e2723; background: #fff; }
            QPushButton { background-color: #6f4e37; color: white; border-radius: 8px; padding: 6px 10px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #5a3e2b; }
        ''')
        bl = QVBoxLayout(self.bubble)
        has_key = bool(get_key())
        start_text = 'Привіт! Готовий до роботи ☕ Натисни на кружку, щоб сховати меню.' if has_key else 'Встав свій ключ Gemini API у поле нижче та натисни «ОК»:'
        self.msg_label = QLabel(start_text)
        self.msg_label.setWordWrap(True)
        bl.addWidget(self.msg_label)

        self.key_box = QWidget()
        key_row = QHBoxLayout(self.key_box)
        key_row.setContentsMargins(0, 0, 0, 0)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText('Встав AIza...')
        self.key_input.setText(get_key())
        key_row.addWidget(self.key_input)
        b_save_key = QPushButton('ОК')
        b_save_key.setStyleSheet('background-color: #2e7d32;')
        b_save_key.clicked.connect(self.save_key)
        key_row.addWidget(b_save_key)
        self.key_box.setVisible(not has_key)
        bl.addWidget(self.key_box)

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
        b_key.setToolTip('Показати/сховати поле ключа')
        b_key.clicked.connect(lambda: self.key_box.setVisible(not self.key_box.isVisible()))
        row2.addWidget(b_key)
        b_close = QPushButton('✖')
        b_close.setStyleSheet('background-color: #a1887f; padding: 6px 8px;')
        b_close.clicked.connect(QApplication.quit)
        row2.addWidget(b_close)
        bl.addLayout(row2)

        self.layout.addWidget(self.bubble)
        self.layout.addSpacing(155)

    def save_key(self):
        val = self.key_input.text().strip()
        if val:
            open(KEY_FILE, 'w', encoding='utf-8').write(val)
            self.key_box.setVisible(False)
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
            self.key_box.setVisible(True)
            self.msg_label.setText('Спочатку встав API-ключ у поле нижче 👇')
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
            self.key_box.setVisible(True)
            self.msg_label.setText('Спочатку встав API-ключ у поле нижче 👇')
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
