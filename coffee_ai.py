import sys, os, io, base64, math, random, json, time
import urllib.request, urllib.error
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QFrame, QTextEdit, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QCursor
from PIL import ImageGrab, Image

try:
    import winsound
except ImportError:
    winsound = None

PROXY_URL = 'https://gentle-base-e6e8coffee-proxy.piksarmult.workers.dev'
SYSTEM_RULE = 'Ти дружній офісний ШІ-помічник Кофі. Продовжуй поточний діалог природно українською мовою. НІКОЛИ не вітайся знову ("Привіт", "Я Кофі") — відповідай одразу по суті запитання.'

DATA_DIR = os.path.join(os.path.expanduser("~"), ".coffee_ai")
os.makedirs(DATA_DIR, exist_ok=True)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")

class AIWorker(QThread):
    finished = pyqtSignal(str, str, bool)

    def __init__(self, prompt, history, image=None):
        super().__init__()
        self.prompt = prompt
        self.history = list(history)
        self.image = image

    def run(self):
        user_parts = [{"text": self.prompt}]
        if self.image is not None:
            buf = io.BytesIO()
            self.image.save(buf, format="JPEG", quality=80)
            b64_img = base64.b64encode(buf.getvalue()).decode("ascii")
            user_parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64_img
                }
            })

        contents = [
            {"role": "user", "parts": [{"text": SYSTEM_RULE}]},
            {"role": "model", "parts": [{"text": "Зрозумів, відповідаю одразу по суті без зайвих привітань."}]},
            *self.history,
            {"role": "user", "parts": user_parts}
        ]

        payload = json.dumps({"contents": contents}).encode("utf-8")

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
                        reply = data["text"].replace("**", "").strip()
                        self.finished.emit(self.prompt, reply, True)
                        return
                    err = data.get("error", "Невідома відповідь сервера")
                    self.finished.emit("", f"Помилка: {err[:100]}", False)
                    return
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                if ("429" in body or "RESOURCE_EXHAUSTED" in body) and attempt == 0:
                    time.sleep(2.0)
                    continue
                if "429" in body or "RESOURCE_EXHAUSTED" in body:
                    self.finished.emit("", "Тимчасово вичерпано ліміт запитів Google API. Зачекай хвилину ☕", False)
                else:
                    self.finished.emit("", f"Помилка сервера ({e.code}): {body[:90]}", False)
                return
            except Exception as ex:
                self.finished.emit("", f"Немає зв'язку з сервером: {str(ex)[:90]}", False)
                return

class CartoonCoffeeAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(370, 490)
        self.drag_pos = QPoint()
        self.click_start = QPoint()
        self.bounce_step = 0
        self.eye_dx = 0.0
        self.eye_dy = 0.0
        self.last_cursor = QCursor.pos()
        self.idle_ticks = 0
        self.idle_target = (0.0, 0.0)
        self.emotion = "normal"  # normal, thinking, error
        self.chat_history = self.load_json(HISTORY_FILE, [])
        self.tasks = self.load_json(TASKS_FILE, [])
        self.pomo_seconds = 25 * 60
        self.pomo_running = False
        self.worker = None
        self.init_ui()
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(45)

        self.pomo_timer = QTimer(self)
        self.pomo_timer.timeout.connect(self.tick_pomodoro)

    def load_json(self, path, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

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
            QPushButton { background-color: #b5651d; color: white; border: 1.5px solid #1a1a1a; border-radius: 8px; padding: 5px 7px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #965215; }
            QPushButton#lightBtn { background-color: #f5ebe0; color: #1a1a1a; }
            QPushButton#lightBtn:hover { background-color: #eadbc8; }
            QPushButton#chipBtn { background-color: #fff8f0; color: #5d4037; border: 1px solid #bcaaa4; border-radius: 10px; padding: 3px 6px; font-size: 10px; }
            QPushButton#chipBtn:hover { background-color: #f5ebe0; border-color: #b5651d; color: #1a1a1a; }
            QListWidget { border: 1px dashed #bcaaa4; border-radius: 8px; background: #fdf9f6; font-size: 11.5px; color: #1a1a1a; }
        ''')
        bl = QVBoxLayout(self.bubble)
        bl.setSpacing(5)

        # Верхня панель з Pomodoro
        top_row = QHBoxLayout()
        self.b_pomo = QPushButton('⏱ 25:00')
        self.b_pomo.setObjectName('lightBtn')
        self.b_pomo.setToolTip('Запустити / скинути фокус-таймер на 25 хв')
        self.b_pomo.clicked.connect(self.toggle_pomodoro)
        top_row.addWidget(self.b_pomo)

        top_row.addStretch()

        b_clear = QPushButton('🧹 Новий чат')
        b_clear.setObjectName('lightBtn')
        b_clear.setToolTip("Очистити збережену пам'ять діалогу")
        b_clear.clicked.connect(self.clear_history)
        top_row.addWidget(b_clear)
        bl.addLayout(top_row)

        # Вікно повідомлень
        self.msg_box = QTextEdit()
        self.msg_box.setReadOnly(True)
        initial_text = 'Привіт! Я Кофі ☕ Я пам’ятаю наші розмови, читаю буфер обміну та стежу за таймером. Чим допомогти?'
        if self.chat_history:
            for item in reversed(self.chat_history):
                if item.get("role") == "model" and item.get("parts"):
                    initial_text = item["parts"][0].get("text", initial_text)
                    break
        self.msg_box.setText(initial_text)
        self.msg_box.setMinimumHeight(82)
        self.msg_box.setMaximumHeight(130)
        bl.addWidget(self.msg_box)

        # Висувна панель справ
        self.tasks_frame = QFrame()
        self.tasks_frame.setVisible(False)
        tl = QVBoxLayout(self.tasks_frame)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        t_inp_row = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText('Нова справа (Enter)...')
        self.task_input.returnPressed.connect(self.add_task)
        t_inp_row.addWidget(self.task_input)
        b_add_t = QPushButton('+')
        b_add_t.clicked.connect(self.add_task)
        t_inp_row.addWidget(b_add_t)
        tl.addLayout(t_inp_row)

        self.tasks_list = QListWidget()
        self.tasks_list.setMaximumHeight(85)
        self.tasks_list.itemClicked.connect(self.toggle_task_item)
        self.tasks_list.itemDoubleClicked.connect(self.delete_task_item)
        tl.addWidget(self.tasks_list)
        bl.addWidget(self.tasks_frame)
        self.refresh_tasks_ui()

        # Швидкі пресети
        chips_row = QHBoxLayout()
        chips_row.setSpacing(4)
        presets = [
            ('🌐 Переклад', 'Переклади це на природну англійську (або українську, якщо текст англійською):'),
            ('✍️ Виправити', 'Виправ орфографічні та пунктуаційні помилки в цьому тексті і поверни чистий варіант:'),
            ('🤝 Ввічливо', 'Перепиши цей текст більш ввічливо та професійно для ділового листування:'),
            ('⚡ Коротко', 'Виділи головну суть цього тексту у 3 коротких пунктах:')
        ]
        for label, instr in presets:
            btn = QPushButton(label)
            btn.setObjectName('chipBtn')
            btn.clicked.connect(lambda checked, i=instr: self.run_preset(i))
            chips_row.addWidget(btn)
        bl.addLayout(chips_row)

        # Поле вводу
        row1 = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText('Напиши запитання...')
        self.input_field.returnPressed.connect(self.ask_text)
        row1.addWidget(self.input_field)
        b_send = QPushButton('➤')
        b_send.clicked.connect(self.ask_text)
        row1.addWidget(b_send)
        bl.addLayout(row1)

        # Нижня панель дій
        row2 = QHBoxLayout()
        b_scan = QPushButton('👀 Екран')
        b_scan.clicked.connect(self.analyze_screen)
        row2.addWidget(b_scan)

        b_clip = QPushButton('📎 З буфера')
        b_clip.setObjectName('lightBtn')
        b_clip.setToolTip('Пояснити або перекласти текст із буфера обміну')
        b_clip.clicked.connect(self.analyze_clipboard)
        row2.addWidget(b_clip)

        b_tasks = QPushButton('📋')
        b_tasks.setObjectName('lightBtn')
        b_tasks.setToolTip('Список справ (клік — виконано, подвійний — видалити)')
        b_tasks.clicked.connect(lambda: self.tasks_frame.setVisible(not self.tasks_frame.isVisible()))
        row2.addWidget(b_tasks)

        b_hide = QPushButton('🔽')
        b_hide.setObjectName('lightBtn')
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

    # --- POMODORO ---
    def toggle_pomodoro(self):
        if self.pomo_running:
            self.pomo_timer.stop()
            self.pomo_running = False
            self.pomo_seconds = 25 * 60
            self.b_pomo.setText('⏱ 25:00')
            self.b_pomo.setStyleSheet('')
        else:
            self.pomo_running = True
            self.b_pomo.setStyleSheet('background-color: #b5651d; color: white;')
            self.pomo_timer.start(1000)

    def tick_pomodoro(self):
        self.pomo_seconds -= 1
        m, s = divmod(self.pomo_seconds, 60)
        self.b_pomo.setText(f'⏱ {m:02d}:{s:02d}')
        if self.pomo_seconds <= 0:
            self.pomo_timer.stop()
            self.pomo_running = False
            self.pomo_seconds = 25 * 60
            self.b_pomo.setText('⏱ 25:00')
            self.b_pomo.setStyleSheet('')
            self.bubble.setVisible(True)
            self.emotion = "normal"
            self.msg_box.setText('Час вийшов! 25 хвилин фокусу позаду ☕ Зроби ковток кави та розімни спину!')
            if winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

    # --- СПИСОК СПРАВ ---
    def refresh_tasks_ui(self):
        self.tasks_list.clear()
        if not self.tasks:
            item = QListWidgetItem('Справ поки немає ☕')
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tasks_list.addItem(item)
            return
        for t in self.tasks:
            prefix = '✅ ' if t.get('done') else '⬜ '
            self.tasks_list.addItem(prefix + t.get('text', ''))

    def add_task(self):
        txt = self.task_input.text().strip()
        if not txt:
            return
        self.tasks.append({'text': txt, 'done': False})
        self.save_json(TASKS_FILE, self.tasks)
        self.task_input.clear()
        self.refresh_tasks_ui()

    def toggle_task_item(self, item):
        row = self.tasks_list.row(item)
        if 0 <= row < len(self.tasks):
            self.tasks[row]['done'] = not self.tasks[row]['done']
            self.save_json(TASKS_FILE, self.tasks)
            self.refresh_tasks_ui()

    def delete_task_item(self, item):
        row = self.tasks_list.row(item)
        if 0 <= row < len(self.tasks):
            self.tasks.pop(row)
            self.save_json(TASKS_FILE, self.tasks)
            self.refresh_tasks_ui()

    # --- БУФЕР ОБМІНУ ТА ПРЕСЕТИ ---
    def analyze_clipboard(self):
        clip = QApplication.clipboard().text().strip()
        if not clip:
            self.msg_box.setText('Буфер обміну порожній. Спочатку скопіюй якийсь текст (Ctrl+C)!')
            return
        self.emotion = "thinking"
        self.msg_box.setText('Читаю скопійоване... 📎⚡')
        prompt = f'Ось текст із мого буфера обміну. Коротко поясни його суть або переклади українською, якщо він іноземною:\n\n{clip}'
        self.worker = AIWorker(prompt, self.chat_history)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

    def run_preset(self, instruction):
        target = self.input_field.text().strip()
        if not target:
            target = QApplication.clipboard().text().strip()
        if not target:
            self.msg_box.setText('Введи текст у поле або скопіюй його (Ctrl+C), а потім натисни швидку кнопку!')
            return
        self.input_field.clear()
        self.emotion = "thinking"
        self.msg_box.setText('Обробляю... ⚡')
        self.worker = AIWorker(f'{instruction}\n\n{target}', self.chat_history)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

    def clear_history(self):
        self.chat_history = []
        self.save_json(HISTORY_FILE, self.chat_history)
        self.emotion = "normal"
        self.msg_box.setText('Пам’ять розмови очищено 🧹 Про що поговоримо далі?')

    # --- АНІМАЦІЯ ТА МАЛЮВАННЯ ---
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
        dx_wobble = int(math.sin(self.bounce_step * 0.4) * 3) if self.emotion == "thinking" else 0
        cx = self.width() - 62 + dx_wobble
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

        # Брови залежно від емоції
        brow_shift = self.eye_dy * 0.45
        p.setPen(QPen(QColor('#141414'), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self.emotion == "thinking":
            p.drawLine(int(cx - 15), int(cy + 40), int(cx - 4), int(cy + 43))
            p.drawLine(int(cx + 4), int(cy + 43), int(cx + 15), int(cy + 40))
        elif self.emotion == "error":
            p.drawLine(int(cx - 15), int(cy + 44), int(cx - 4), int(cy + 40))
            p.drawLine(int(cx + 4), int(cy + 40), int(cx + 15), int(cy + 44))
        else:
            p.drawArc(QRectF(cx - 16, cy + 39 + brow_shift, 12, 6), 25 * 16, 130 * 16)
            p.drawArc(QRectF(cx + 4, cy + 39 + brow_shift, 12, 6), 25 * 16, 130 * 16)

        # Вії
        lash_pen = QPen(QColor('#141414'), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(lash_pen)
        p.drawLine(int(cx - 14), int(cy + 48), int(cx - 18), int(cy + 45))
        p.drawLine(int(cx - 15), int(cy + 51), int(cx - 20), int(cy + 49))
        p.drawLine(int(cx - 15), int(cy + 54), int(cx - 19), int(cy + 53))

        p.drawLine(int(cx + 14), int(cy + 48), int(cx + 18), int(cy + 45))
        p.drawLine(int(cx + 15), int(cy + 51), int(cx + 20), int(cy + 49))
        p.drawLine(int(cx + 15), int(cy + 54), int(cx + 19), int(cy + 53))

        # Білки очей (примружені, коли думає)
        eye_h = 15 if self.emotion == "thinking" else 21
        eye_y = cy + 47 if self.emotion == "thinking" else cy + 44
        p.setPen(QPen(QColor('#141414'), 2.1))
        p.setBrush(QColor('#ffffff'))
        p.drawEllipse(QRectF(cx - 14.5, eye_y, 14.5, eye_h))
        p.drawEllipse(QRectF(cx, eye_y, 14.5, eye_h))

        # Зіниці
        pupil_h = 10.5 if self.emotion == "thinking" else 13.5
        pupil_y = cy + 49.5 if self.emotion == "thinking" else cy + 48
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#141414'))
        p.drawPie(QRectF(cx - 10.5 + self.eye_dx, pupil_y + self.eye_dy, 8.2, pupil_h), 215 * 16, 290 * 16)
        p.drawPie(QRectF(cx + 3.5 + self.eye_dx, pupil_y + self.eye_dy, 8.2, pupil_h), 215 * 16, 290 * 16)

        # Рот залежно від емоції
        p.setPen(QPen(QColor('#141414'), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        smile = QPainterPath()
        if self.emotion == "thinking":
            smile.moveTo(cx - 7, cy + 71)
            smile.quadTo(cx, cy + 69, cx + 7, cy + 71)
            p.drawPath(smile)
        elif self.emotion == "error":
            smile.moveTo(cx - 10, cy + 74)
            smile.quadTo(cx, cy + 67, cx + 10, cy + 74)
            p.drawPath(smile)
        else:
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

    def on_ai_reply(self, user_prompt, reply_text, success):
        if success and user_prompt:
            self.emotion = "normal"
            self.chat_history.append({"role": "user", "parts": [{"text": user_prompt}]})
            self.chat_history.append({"role": "model", "parts": [{"text": reply_text}]})
            if len(self.chat_history) > 20:
                self.chat_history = self.chat_history[-20:]
            self.save_json(HISTORY_FILE, self.chat_history)
        else:
            self.emotion = "error"
        self.msg_box.setText(reply_text)

    def analyze_screen(self):
        self.emotion = "thinking"
        self.msg_box.setText('Дивлюся на екран... ⚡👀')
        self.hide()
        QApplication.processEvents()
        shot = ImageGrab.grab()
        self.show()

        w, h = shot.size
        if w > 1280:
            shot = shot.resize((1280, int(h * (1280 / w))), Image.Resampling.BILINEAR)

        prompt = 'Подивись на мій екран: якщо є помилка — коротко вкажи її. Інакше дай 1 коротку пораду (до 2 речень).'
        self.worker = AIWorker(prompt, self.chat_history, shot)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

    def ask_text(self):
        txt = self.input_field.text().strip()
        if not txt:
            return
        self.input_field.clear()
        self.emotion = "thinking"
        self.msg_box.setText('Думаю... ⚡')
        self.worker = AIWorker(txt, self.chat_history)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = CartoonCoffeeAssistant()
    w.show()
    sys.exit(app.exec())
