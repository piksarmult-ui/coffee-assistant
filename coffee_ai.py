import sys, os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QFrame, QTextEdit)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath
from PIL import ImageGrab, Image
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
            
            candidates = ['gemini-3.1-flash-lite-preview', 'gemini-3-flash-preview', 'gemini-2.5-flash']
            try:
                for m in client.models.list():
                    name = m.name.replace('models/', '')
                    if ('lite' in name or 'flash' in name) and name not in candidates:
                        candidates.append(name)
            except Exception:
                pass

            last_err = "Не знайдено моделі"
            for model_name in candidates:
                try:
                    res = client.models.generate_content(model=model_name, contents=contents)
                    if res and res.text:
                        clean_text = res.text.replace('**', '').strip()
                        self.finished.emit(clean_text)
                        return
                except Exception as e:
                    last_err = str(e)
                    if 'API_KEY_INVALID' in last_err or '400' in last_err:
                        break
                    continue

            self.finished.emit(f"Помилка: {last_err[:100]}")
        except Exception as e:
            self.finished.emit(f"Помилка: {str(e)[:100]}")

class CartoonCoffeeAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(340, 430)
        self.drag_pos = QPoint()
        self.click_start = QPoint()
        self.bounce_step = 0
        self.worker = None
        self.init_ui()
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(100)

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        
        self.bubble = QFrame(self)
        self.bubble.setObjectName("mainBubble")
        self.bubble.setStyleSheet('''
            QFrame#mainBubble { background-color: #ffffff; border: 2.5px solid #1a1a1a; border-radius: 18px; padding: 8px; }
            QTextEdit { 
                color: #1a1a1a; 
                font-family: 'Segoe UI'; 
                font-size: 12px; 
                border: none; 
                background: transparent; 
            }
            QScrollBar:vertical { border: none; background: #f5ebe0; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #b5651d; border-radius: 3px; }
            QLineEdit { border: 1.5px solid #bcaaa4; border-radius: 8px; padding: 5px 8px; font-size: 12px; color: #1a1a1a; background: #fff; }
            QPushButton { background-color: #b5651d; color: white; border: 1.5px solid #1a1a1a; border-radius: 8px; padding: 5px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #965215; }
        ''')
        bl = QVBoxLayout(self.bubble)
        bl.setSpacing(6)

        has_key = bool(get_key())
        start_text = 'Привіт! Я Кофі ☕ Натисни на мене або «🔽», щоб сховати віконце!' if has_key else 'Встав свій ключ Gemini API у поле нижче та натисни «ОК»:'
        
        self.msg_box = QTextEdit()
        self.msg_box.setReadOnly(True)
        self.msg_box.setText(start_text)
        self.msg_box.setMinimumHeight(85)
        self.msg_box.setMaximumHeight(130)
        bl.addWidget(self.msg_box)

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
        b_hide.setToolTip('Сховати діалог (залишити лише стаканчик)')
        b_hide.clicked.connect(lambda: self.bubble.setVisible(False))
        row2.addWidget(b_hide)

        b_key = QPushButton('🔑')
        b_key.setToolTip('Ключ API')
        b_key.clicked.connect(lambda: self.key_box.setVisible(not self.key_box.isVisible()))
        row2.addWidget(b_key)

        b_close = QPushButton('✖')
        b_close.setStyleSheet('background-color: #757575;')
        b_close.setToolTip('Закрити програму')
        b_close.clicked.connect(QApplication.quit)
        row2.addWidget(b_close)
        bl.addLayout(row2)

        self.layout.addWidget(self.bubble)
        self.layout.addSpacing(125)

    def save_key(self):
        val = self.key_input.text().strip()
        if val:
            open(KEY_FILE, 'w', encoding='utf-8').write(val)
            self.key_box.setVisible(False)
            self.msg_box.setText('Ключ збережено! Готовий допомагати ☕')

    def update_animation(self):
        self.bounce_step = (self.bounce_step + 1) % 20
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        dy = -2 if self.bounce_step < 10 else 0
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

        p.setPen(QPen(QColor('#141414'), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx - 17, cy + 41, 13, 6), 20 * 16, 140 * 16)
        p.drawArc(QRectF(cx + 4, cy + 41, 13, 6), 20 * 16, 140 * 16)

        p.setPen(QPen(QColor('#141414'), 2))
        p.setBrush(QColor('#ffffff'))
        p.drawEllipse(QRectF(cx - 16, cy + 46, 13, 17))
        p.drawEllipse(QRectF(cx + 3, cy + 46, 13, 17))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#141414'))
        p.drawPie(QRectF(cx - 11, cy + 49, 7, 11), 35 * 16, 290 * 16)
        p.drawPie(QRectF(cx + 8, cy + 49, 7, 11), 35 * 16, 290 * 16)

        p.setPen(QPen(QColor('#141414'), 2))
        p.setBrush(QColor('#212121'))
        mouth = QPainterPath()
        mouth.moveTo(cx - 9, cy + 67)
        mouth.quadTo(cx, cy + 69, cx + 9, cy + 67)
        mouth.quadTo(cx + 8, cy + 77, cx, cy + 77)
        mouth.quadTo(cx - 8, cy + 77, cx - 9, cy + 67)
        p.drawPath(mouth)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#e53935'))
        p.drawEllipse(QRectF(cx - 4, cy + 71, 8, 5))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.click_start = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        if (e.globalPosition().toPoint() - self.click_start).manhattanLength() < 8:
            # Перевіряємо, що клікнули саме по області стаканчика внизу праворуч
            pos = e.position().toPoint()
            if pos.x() > self.width() - 120 and pos.y() > self.height() - 135:
                self.bubble.setVisible(not self.bubble.isVisible())

    def on_ai_reply(self, text):
        self.msg_box.setText(text)

    def analyze_screen(self):
        key = get_key()
        if not key:
            self.key_box.setVisible(True)
            self.msg_box.setText('Спочатку встав API-ключ у поле нижче 👇')
            return
        self.msg_box.setText('Швидко дивлюся на екран... ⚡👀')
        self.hide()
        QApplication.processEvents()
        shot = ImageGrab.grab()
        self.show()

        w, h = shot.size
        if w > 1280:
            shot = shot.resize((1280, int(h * (1280 / w))), Image.Resampling.BILINEAR)

        prompt = 'Ти маленький офісний помічник Кофі. Подивись на екран: якщо є помилка — коротко вкажи її. Інакше дай 1 коротку пораду (до 2 речень українською).'
        self.worker = AIWorker(key, prompt, shot)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

    def ask_text(self):
        txt = self.input_field.text().strip()
        if not txt: return
        key = get_key()
        if not key:
            self.key_box.setVisible(True)
            self.msg_box.setText('Спочатку встав API-ключ у поле нижче 👇')
            return
        self.input_field.clear()
        self.msg_box.setText('Думаю... ⚡')
        prompt = f'Відповідай стисло українською як помічник Кофі: {txt}'
        self.worker = AIWorker(key, prompt)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = CartoonCoffeeAssistant()
    w.show()
    sys.exit(app.exec())
