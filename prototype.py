"""
Hermes 灵动岛桌面小组件 — 高仿真原型

验证：三态切换 / 动画 / 拖拽 / 流式显示 / 样式
不做：WebSocket、数据库、Hermes 对接
"""

import sys
import random
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QRect, QSize, QMimeData, QEvent,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen,
    QIcon, QPixmap, QAction, QFontDatabase,
    QLinearGradient, QDrag, QCursor,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QGraphicsOpacityEffect,
    QApplication, QSystemTrayIcon, QMenu,
    QFrame, QSizePolicy, QSpacerItem,
)


# ═══════════════════════════════════════════════════════════
# 样式常量
# ═══════════════════════════════════════════════════════════

BG_COLOR = QColor(24, 24, 28, 240)       # 深黑底色
BG_COLOR_HIDDEN = QColor(24, 24, 28, 120) # 隐藏态半透明可见
BORDER_COLOR = QColor(60, 60, 70)         # 边框
TEXT_PRIMARY = "#e4e4e7"
TEXT_SECONDARY = "#a1a1aa"
TEXT_MUTED = "#71717a"
ACCENT = "#6366f1"                        # 蓝色强调
INPUT_BG = "#1e1e22"
INPUT_BORDER = "#3f3f46"


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def make_icon(emoji: str, size: int = 32) -> QIcon:
    """用 emoji 绘制临时图标。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    font = QFont("Segoe UI Emoji", size - 4)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, emoji)
    painter.end()
    return QIcon(pixmap)


# ═══════════════════════════════════════════════════════════
# 消息气泡
# ═══════════════════════════════════════════════════════════

class MessageBubble(QFrame):
    """单条消息气泡。支持流式追加文字。"""

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self._role = role
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        # 头像占位
        avatar = QLabel()
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if role == "user":
            avatar.setText("👤")
            avatar.setStyleSheet("font-size: 16px;")
        else:
            avatar.setText("🤖")
            avatar.setStyleSheet("font-size: 16px;")

        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)

        # 内容区
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)

        # 角色名
        role_label = QLabel("你" if role == "user" else "Hermes")
        role_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;"
        )
        content_layout.addWidget(role_label)

        # 消息内容
        self._text_label = QLabel(content)
        self._text_label.setWordWrap(True)
        self._text_label.setTextFormat(Qt.TextFormat.PlainText)
        bubble_style = (
            f"background: #27272a; border-radius: 12px; padding: 8px 12px;"
            f"color: {TEXT_PRIMARY}; font-size: 13px; line-height: 1.5;"
        )
        self._text_label.setStyleSheet(bubble_style)
        content_layout.addWidget(self._text_label)

        layout.addWidget(content_wrapper, stretch=1)

    def append_text(self, text: str):
        """流式追加文字。"""
        current = self._text_label.text()
        self._text_label.setText(current + text)

    @property
    def role(self) -> str:
        return self._role

    @property
    def text_content(self) -> str:
        return self._text_label.text()


# ═══════════════════════════════════════════════════════════
# 首行通知条（隐藏态 / 通知态共用）
# ═══════════════════════════════════════════════════════════

class NotifyStrip(QWidget):
    """隐藏在顶部的细条，也是通知展开后的内容区。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # Hermes 小图标
        icon_label = QLabel("⏺")
        icon_label.setStyleSheet("font-size: 14px; color: #22c55e;")
        icon_label.setFixedSize(18, 18)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 通知文字
        self._text = QLabel()
        self._text.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px;")
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._text, stretch=1)

    def set_notification(self, text: str):
        self._text.setText(text[:200])


# ═══════════════════════════════════════════════════════════
# 灵动岛主面板
# ═══════════════════════════════════════════════════════════

class DynamicIsland(QWidget):
    """灵动岛桌面面板。

    三种状态：
      HIDDEN     — 屏幕顶部 60×4 细条，半透明
      NOTIFY     — 收到消息展开为 320×52 圆角矩形
      INTERACTIVE— 点击后展开为 420×520，显示历史 + 输入框
    """

    # 尺寸
    W_HIDDEN, H_HIDDEN = 80, 8          # 隐藏态：粗一点的可见细条
    W_NOTIFY_MIN = 200                   # 通知态最小宽度
    W_NOTIFY_MAX = 500                   # 通知态最大宽度
    H_NOTIFY = 48                        # 通知态高度
    W_CHAT, H_CHAT = 420, 520
    PADDING = 16
    RADIUS = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "HIDDEN"           # HIDDEN | NOTIFY | CHAT
        self._dragging = False
        self._drag_offset = QPoint()
        self._seq = 0
        self._current_bubble: MessageBubble | None = None
        self._bubbles: list[MessageBubble] = []
        self._pending_bubbles: list[tuple[str, str]] = []  # (role, text) deferred until CHAT

        # 自动隐藏计时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(4000)
        self._hide_timer.timeout.connect(self._on_hide_timeout)

        # 全局鼠标位置轮询（隐藏态 hover 检测）
        self._mouse_poll_timer = QTimer(self)
        self._mouse_poll_timer.setInterval(100)
        self._mouse_poll_timer.timeout.connect(self._poll_mouse)
        self._mouse_poll_timer.start()
        self._was_near_strip = False

        # 窗口属性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 不设 WA_ShowWithoutActivating —— 窗口需要参与系统激活链
        # 才能收到 ActivationChange 事件，检测用户点击其他应用时折叠面板
        self.setMouseTracking(True)

        self._init_ui()
        self._init_position()
        self._apply_state(animate=False)

    # ── UI 构建 ──

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 通知条（HIDDEN / NOTIFY 共用）──
        self._notify = NotifyStrip(self)
        root.addWidget(self._notify)

        # ── 聊天区（CHAT 态显示）──
        self._chat_area = QWidget(self)
        chat_layout = QVBoxLayout(self._chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_COLOR.name()};")
        sep.setFixedHeight(1)
        chat_layout.addWidget(sep)

        # 滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 5px; background: transparent; margin: 0; }"
            "QScrollBar::handle:vertical { background: #3f3f46; border-radius: 3px; min-height: 30px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(self.PADDING, 10, self.PADDING, 10)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._scroll_content)

        chat_layout.addWidget(self._scroll, stretch=1)

        # ── 输入栏 ──
        input_bar = QWidget()
        input_bar.setFixedHeight(60)
        input_bar.setStyleSheet(f"background: transparent; border-top: 1px solid {BORDER_COLOR.name()};")
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(self.PADDING, 10, self.PADDING, 14)
        input_layout.setSpacing(10)

        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("给 Hermes 发消息...")
        self._input_field.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {INPUT_BG}; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {INPUT_BORDER}; border-radius: 10px;"
            f"  padding: 8px 14px; font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
        )
        self._input_field.returnPressed.connect(self._handle_send)
        input_layout.addWidget(self._input_field, stretch=1)

        self._send_btn = QPushButton("↑")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {ACCENT}; color: white; border: none;"
            f"  border-radius: 10px; font-size: 16px; font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{ background: #818cf8; }}"
            f"QPushButton:pressed {{ background: #4f46e5; }}"
        )
        self._send_btn.clicked.connect(self._handle_send)
        input_layout.addWidget(self._send_btn)

        chat_layout.addWidget(input_bar)
        root.addWidget(self._chat_area)

        # 初始不可见
        self._notify.setVisible(True)
        self._chat_area.setVisible(False)

    # ── 定位 ──

    def _init_position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.W_HIDDEN) // 2
        y = 0
        self.move(x, y)

    # ── 状态管理 ──

    def _apply_state(self, animate: bool = True):
        geo = self.geometry()
        if self._state == "HIDDEN":
            target = QRect(geo.x(), geo.y(), self.W_HIDDEN, self.H_HIDDEN)
            self._notify.setVisible(True)
            self._chat_area.setVisible(False)
            self._hide_timer.stop()
            self._bg_color = BG_COLOR_HIDDEN
            duration = 200
            easing = QEasingCurve.Type.InOutQuad
        elif self._state == "NOTIFY":
            w = self._calc_notify_width()
            target = QRect(geo.x(), geo.y(), w, self.H_NOTIFY)
            self._notify.setVisible(True)
            self._chat_area.setVisible(False)
            self._hide_timer.start()
            duration = 250
            easing = QEasingCurve.Type.OutQuad
        else:  # CHAT
            target = QRect(geo.x(), geo.y(), self.W_CHAT, self.H_CHAT)
            self._notify.setVisible(False)
            self._chat_area.setVisible(True)
            self._hide_timer.stop()
            duration = 280
            easing = QEasingCurve.Type.OutQuad

        if self._state == "CHAT":
            self._flush_pending()

        self._bg_color = BG_COLOR

        if animate and geo != target:
            self._anim = QPropertyAnimation(self, b"geometry", self)
            self._anim.setDuration(duration)
            self._anim.setStartValue(geo)
            self._anim.setEndValue(target)
            self._anim.setEasingCurve(easing)
            self._anim.finished.connect(lambda: self.setFixedSize(target.size()))
            self._anim.start()
        else:
            self.setFixedSize(target.size())
            self.setGeometry(target)

    def _go_hidden(self):
        self._state = "HIDDEN"
        self._apply_state()

    def _on_hide_timeout(self):
        """通知态超时折叠，但如果鼠标仍在附近则跳过本次。"""
        if self._state != "NOTIFY":
            return
        # 检查鼠标是否还在气泡上
        cursor_pos = QCursor.pos()
        rect = self.frameGeometry().adjusted(-10, -5, 10, 20)
        if rect.contains(cursor_pos):
            self._hide_timer.start()  # 重新计时
            return
        self._go_hidden()

    def _poll_mouse(self):
        """100ms 轮询全局鼠标位置，隐藏态 hover 时展开为提示气泡。"""
        if self._state != "HIDDEN":
            self._was_near_strip = False
            return

        cursor_pos = QCursor.pos()
        widget_rect = self.frameGeometry()
        detect_rect = widget_rect.adjusted(-30, -5, 30, 40)
        near = detect_rect.contains(cursor_pos)

        if near and not self._was_near_strip:
            self._was_near_strip = True
            # 鼠标接近 → 展开为小提示气泡
            self._state = "NOTIFY"
            self._notify.set_notification("Hermes — 点击打开")
            self._apply_state()
        elif not near and self._was_near_strip:
            self._was_near_strip = False
            # 鼠标移开 → 折叠回隐藏条
            self._go_hidden()

    def _calc_notify_width(self) -> int:
        """根据通知文字长度计算气泡宽度。"""
        text = self._notify._text.text()
        if not text:
            return self.W_NOTIFY_MIN
        fm = self._notify._text.fontMetrics()
        # 估算文字宽度：12px padding + 18px icon + 8px gap + 12px padding
        text_w = fm.horizontalAdvance(text)
        total = self.PADDING + 18 + 8 + text_w + self.PADDING + 10  # +10 余量
        return max(self.W_NOTIFY_MIN, min(total, self.W_NOTIFY_MAX))

    def _flush_pending(self):
        """将积压的消息气泡渲染到聊天区。"""
        if not self._pending_bubbles:
            return
        for role, text in self._pending_bubbles:
            bubble = MessageBubble(role, text, self._scroll_content)
            self._scroll_layout.addWidget(bubble)
            self._bubbles.append(bubble)
        self._pending_bubbles.clear()
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── 公开接口 ──

    def show_notification(self, text: str):
        """显示通知消息，展开 NOTIFY 态（宽度根据内容自适应）。"""
        self._notify.set_notification(text)
        if self._state == "HIDDEN":
            self._state = "NOTIFY"
            self._apply_state()
        elif self._state == "NOTIFY":
            # 已在通知态，刷新宽度
            self._apply_state()

    def start_stream(self):
        """开始一条流式回复。"""
        if self._state != "CHAT":
            self._state = "CHAT"
            self._apply_state()

        self._current_bubble = MessageBubble("assistant", "", self._scroll_content)
        self._scroll_layout.addWidget(self._current_bubble)
        self._bubbles.append(self._current_bubble)
        self._seq = 0

    def append_delta(self, text: str):
        """追加流式文字片段。"""
        if self._current_bubble:
            self._current_bubble.append_text(text)
            # 滚到底部
            QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ))

    def end_stream(self):
        """流式回复完成。"""
        self._current_bubble = None

    def add_user_bubble(self, text: str):
        """添加用户消息气泡。不在 CHAT 态时暂存，等展开后渲染。"""
        if self._state != "CHAT":
            self._pending_bubbles.append(("user", text))
            self._state = "CHAT"
            self._apply_state()
            return

        bubble = MessageBubble("user", text, self._scroll_content)
        self._scroll_layout.addWidget(bubble)
        self._bubbles.append(bubble)

    def add_system_bubble(self, text: str):
        """添加系统消息气泡。不在 CHAT 态时暂存，等展开后渲染。"""
        if self._state != "CHAT":
            self._pending_bubbles.append(("assistant", text))
            return

        bubble = MessageBubble("assistant", text, self._scroll_content)
        self._scroll_layout.addWidget(bubble)
        self._bubbles.append(bubble)

    # ── 事件 ──

    def changeEvent(self, event):
        """窗口失去激活态时折叠到隐藏态。"""
        if event.type() == QEvent.Type.ActivationChange:
            active = self.isActiveWindow()
            print(f"[DEBUG] ActivationChange: active={active}, state={self._state}")
            if not active and self._state == "CHAT":
                self._go_hidden()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._state in ("HIDDEN", "NOTIFY"):
                from_notify = self._state == "NOTIFY"
                self._state = "CHAT"
                self._apply_state()
                QTimer.singleShot(200, lambda: self._scroll.verticalScrollBar().setValue(
                    self._scroll.verticalScrollBar().maximum()
                ))
                # 从通知态点击时，模拟一段流式回复
                if from_notify:
                    self._trigger_demo_stream()
            else:
                self._dragging = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _trigger_demo_stream(self):
        """在聊天界面演示一段流式回复。"""
        demo_text = (
            "收到！让我来处理这件事..."
        )
        QTimer.singleShot(800, lambda: self._start_demo(demo_text))

    def _start_demo(self, text: str):
        chars = list(text)
        self.start_stream()
        self._demo_chars = chars
        self._demo_idx = 0
        self._demo_timer = QTimer(self)
        self._demo_timer.timeout.connect(self._demo_tick)
        self._demo_timer.start(50)

    def _demo_tick(self):
        if self._demo_idx < len(self._demo_chars):
            self.append_delta(self._demo_chars[self._demo_idx])
            self._demo_idx += 1
        else:
            self._demo_timer.stop()
            self.end_stream()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            new_pos.setY(max(0, min(new_pos.y(), 60)))
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def enterEvent(self, event):
        if self._state == "HIDDEN":
            # 悬停隐藏条时微微展开提示可点击
            self._bg_color = QColor(24, 24, 28, 180)
            self.update()
        elif self._state == "NOTIFY":
            self._hide_timer.stop()

    def leaveEvent(self, event):
        if self._state == "HIDDEN":
            self._bg_color = BG_COLOR_HIDDEN
            self.update()
        elif self._state == "NOTIFY":
            self._hide_timer.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        if self._state == "HIDDEN":
            # 隐藏态：半透明白色细条，悬停时变亮
            r = 4
            painter.setBrush(QBrush(self._bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, r, r)
        else:
            # NOTIFY / CHAT 态：完整圆角矩形
            painter.setBrush(QBrush(BG_COLOR))
            painter.setPen(QPen(BORDER_COLOR, 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), self.RADIUS, self.RADIUS)

        painter.end()

    # ── 内部 ──

    def _handle_send(self):
        text = self._input_field.text().strip()
        if not text:
            return
        self._input_field.clear()
        self.add_user_bubble(text)


# ═══════════════════════════════════════════════════════════
# Mock 消息流 — 模拟 Hermes 发来的消息
# ═══════════════════════════════════════════════════════════

MOCK_STREAMS = [
    "好的，我已经帮你查询了今天的天气。北京今天晴转多云，气温 12°C 到 24°C，"
    "空气质量良，适合户外活动。傍晚可能会有微风，建议带一件薄外套。",
    "这个问题的解决方案其实很简单。你可以先检查一下配置文件中的 `server.port` 设置是否正确，"
    "然后在终端执行 `hermes gateway restart` 重启网关服务。如果还有问题，可以查看 `~/.hermes/gateway.log` 日志文件。",
    "让我分析一下你的需求。你需要的是一个能够：\n\n1. 自动轮询最新消息\n2. 支持多种格式解析\n"
    "3. 错误重试机制\n\n我已经为你生成了对应的 Python 代码框架，请查收。",
]

MOCK_NOTIFICATIONS = [
    "[后台任务完成] 数据导出已完成，共处理 12,430 条记录。",
    "[Cron 任务] 每周报告已生成，点击查看详情。",
    "[系统提示] Hermes 新版本 v2.3.0 已发布，包含 3 项新功能和 5 个 bug 修复。",
    "[提醒] 明天上午 10 点有团队会议，请提前准备。",
    "[GitHub] Pull Request #342 已被合并到 main 分支。",
]


class MockMessageFlow:
    """模拟 Hermes 消息流，发 2 条通知后停止，方便验证 hover 行为。"""

    def __init__(self, island: DynamicIsland):
        self._island = island
        self._phase_timer = QTimer()
        self._phase_timer.timeout.connect(self._show_notification)
        self._phase_timer.setSingleShot(True)
        self._count = 0
        self._max_count = 2

    def start(self):
        """开始模拟：5s 后首条通知，之后每条间隔随机。"""
        self._phase_timer.start(5000)

    def _show_notification(self):
        if self._count >= self._max_count:
            return
        text = random.choice(MOCK_NOTIFICATIONS)
        self._island.show_notification(text)
        self._count += 1
        # 随机间隔 6-10s 发下一条
        self._phase_timer.start(random.randint(6000, 10000))


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 全局暗色风格
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(30, 30, 35))
    palette.setColor(palette.ColorRole.WindowText, QColor(220, 220, 225))
    palette.setColor(palette.ColorRole.Base, QColor(25, 25, 30))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(35, 35, 40))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor(40, 40, 45))
    palette.setColor(palette.ColorRole.ToolTipText, QColor(220, 220, 225))
    palette.setColor(palette.ColorRole.Text, QColor(220, 220, 225))
    palette.setColor(palette.ColorRole.Button, QColor(45, 45, 50))
    palette.setColor(palette.ColorRole.ButtonText, QColor(220, 220, 225))
    palette.setColor(palette.ColorRole.Highlight, QColor(99, 102, 241))
    palette.setColor(palette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # 全局样式表
    app.setStyleSheet("""
        * { font-family: "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif; }
        QToolTip { background: #18181b; color: #e4e4e7; border: 1px solid #3f3f46; padding: 6px; border-radius: 6px; }
    """)

    # 创建面板
    island = DynamicIsland()
    island.show()

    # 预填充欢迎消息
    island.add_system_bubble("👋 你好！我是 Hermes，一个 AI Agent 助手。\n有什么可以帮你的？")

    # 系统托盘
    tray = QSystemTrayIcon()
    tray.setIcon(make_icon("🔵"))
    tray.setToolTip("Hermes Panel")

    menu = QMenu()
    quit_action = QAction("退出")
    quit_action.triggered.connect(lambda: (tray.hide(), app.quit()))
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.show()

    # 启动 mock（5s 后开始发第一条通知，总共只发 2 条）
    mock = MockMessageFlow(island)
    mock.start()

    print("=" * 50)
    print("  Hermes Dynamic Island - Prototype")
    print("=" * 50)
    print()
    print("  Controls:")
    print("  - Top strip: hidden state (waiting)")
    print("  - Auto expand: notification in 5s")
    print("  - Click strip: enter chat mode")
    print("  - Drag panel: reposition")
    print("  - System tray: right-click > Quit")
    print()
    print("  Click the top strip or wait for demo...")
    print()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
