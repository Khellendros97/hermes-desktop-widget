"""Dynamic Island panel UI — the core desktop widget.

Three visual states:
  HIDDEN     — top-edge strip, half-transparent
  NOTIFY     — notification bubble, dynamic width
  CHAT       — full chat panel with history, input, streaming

Connects to HermesClient for real-time messaging.
"""

import re
import logging

_log = logging.getLogger(__name__)

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
    QPoint, QRect, QEvent, pyqtSignal, QUrl,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen,
    QPixmap, QIcon, QCursor,
    QDesktopServices,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame,
    QSizePolicy, QApplication, QTextEdit,
)

from hermes_panel.config import get, set_

# ── Style constants ──

BG_COLOR = QColor(24, 24, 28, 240)
BG_COLOR_HIDDEN = QColor(24, 24, 28, 120)
BORDER_COLOR = QColor(60, 60, 70)
TEXT_PRIMARY = "#e4e4e7"
TEXT_MUTED = "#71717a"
ACCENT = "#6366f1"
INPUT_BG = "#1e1e22"
INPUT_BORDER = "#3f3f46"
BUBBLE_BG_USER = "#3a3a40"
BUBBLE_BG_ASSISTANT = "#2d2d33"
QWIDGETSIZE_MAX = 16777215


def _normalize_notification_text(text: str) -> str:
    """Flatten multi-line/whitespace-heavy text for the single-line notify strip."""
    return re.sub(r"\s+", " ", text).strip()


def _normalize_portal_url(url: str) -> str:
    """Strip and ensure http(s) scheme; return empty string if invalid."""
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return url


def _markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML for QLabel rich text."""
    # Phase 1: extract code blocks and inline code, replace with placeholders
    code_blocks: dict[str, str] = {}

    def _save_code(m: re.Match) -> str:
        placeholder = f"\x00CODE{len(code_blocks)}\x00"
        lang = m.group(1)
        content = m.group(2)
        # Escape HTML inside code content
        content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        code_blocks[placeholder] = (
            f'<pre style="background:#1e1e22; padding:8px; border-radius:6px;'
            f'white-space:pre-wrap; word-break:break-word;">{content}</pre>'
        )
        return placeholder

    def _save_inline(m: re.Match) -> str:
        placeholder = f"\x00CODE{len(code_blocks)}\x00"
        content = m.group(1)
        content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        code_blocks[placeholder] = (
            f'<code style="background:#1e1e22; padding:1px 4px;'
            f'border-radius:3px; word-break:break-all;">{content}</code>'
        )
        return placeholder

    # Block code first (to avoid matching ``` inside inline)
    text = re.sub(r'```(\w*)\n?(.+?)```', _save_code, text, flags=re.DOTALL)
    # Inline code
    text = re.sub(r'`([^`]+)`', _save_inline, text)

    # Phase 2: escape HTML on non-code text
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Phase 3: markdown formatting
    text = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)

    # Phase 4: auto-link URLs (placeholders won't match URL pattern)
    text = re.sub(
        r'(?<![">])(https?://[^\s<>"\')\]]+)',
        r'<a href="\1" style="color:#818cf8;">\1</a>',
        text,
    )

    # Phase 5: newlines → <br>
    text = text.replace("\n", "<br>")

    # Phase 6: restore code placeholders
    for placeholder, html in code_blocks.items():
        text = text.replace(placeholder, html)

    return text


def _html_to_plain(html: str) -> str:
    """Convert rendered HTML back to plain text (inverse of _markdown_to_html)."""
    # Replace <br> variants with newlines before stripping tags
    text = re.sub(r'<br\s*/?>', '\n', html)
    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Unescape common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    return text


# ── Message Bubble ──

class MessageBubble(QFrame):
    """Single chat message bubble with markdown rendering via QLabel."""

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self._role = role
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        avatar = QLabel()
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setText("U" if role == "user" else "H")
        avatar.setStyleSheet(
            f"font-size: 14px; font-weight: bold; "
            f"color: {'#6366f1' if role == 'user' else '#22c55e'};"
        )
        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)

        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)

        role_label = QLabel("You" if role == "user" else "Hermes")
        role_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        content_layout.addWidget(role_label)

        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._label.linkActivated.connect(
            lambda url: QDesktopServices.openUrl(QUrl(url))
        )
        self._label.setStyleSheet(
            f"QLabel {{"
            f"  background: {BUBBLE_BG_ASSISTANT if role == 'assistant' else BUBBLE_BG_USER};"
            f"  color: {TEXT_PRIMARY};"
            f"  border-radius: 12px;"
            f"  padding: 10px 14px;"
            f"  font-size: 13px;"
            f"  line-height: 1.6;"
            f"}}"
        )
        content_layout.addWidget(self._label)

        layout.addWidget(content_wrapper, stretch=1)

        if content:
            self._set_content(content)

    def _set_content(self, text: str):
        html = _markdown_to_html(text)
        self._label.setText(html)

    def set_html(self, html: str):
        """Set label content from raw HTML (bypass markdown conversion — for loading history)."""
        self._label.setText(html)

    def append_text(self, text: str):
        current = _html_to_plain(self._label.text())
        self._set_content(current + text)

    @property
    def role(self) -> str:
        return self._role

    @property
    def text_content(self) -> str:
        return self._label.text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Constrain label to bubble width minus avatar to prevent overflow clipping
        max_w = self.width() - 28
        if max_w > 0:
            self._label.setMaximumWidth(max_w)


# ── Notify Strip ──

class NotifyStrip(QWidget):
    """Top notification bar used in HIDDEN and NOTIFY states."""

    NOTIFY_PADDING_TOP = 6
    NOTIFY_PADDING_BOTTOM = 6
    NOTIFY_MAX_HEIGHT = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_text = ""
        self._multiline = False
        self._style = ""  # "alert" | "rgb-breathing" | ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("font-size: 10px; color: #22c55e;")
        self._dot.setFixedSize(18, 18)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._dot)

        self._text = QLabel()
        font = QFont()
        font.setPointSize(10)
        self._text.setFont(font)
        self._text.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._text.setTextFormat(Qt.TextFormat.PlainText)
        self._text.setWordWrap(False)
        self._text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._text, stretch=1)

        self._portal_btn = QPushButton("🏠")
        self._portal_btn.setFixedSize(24, 24)
        self._portal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._portal_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #a1a1aa; border: none;"
            "  font-size: 13px; padding: 0;"
            "}"
            "QPushButton:hover { color: #e4e4e7; }"
        )
        self._portal_btn.clicked.connect(self._open_portal)
        layout.addWidget(self._portal_btn)

    def set_multiline_mode(self, enabled: bool):
        """Enable or disable multi-line notification mode."""
        self._multiline = enabled
        self._text.setWordWrap(enabled)
        if enabled:
            self._text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        else:
            self._text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._update_text()

    def set_notification(self, text: str):
        if self._multiline:
            self._raw_text = text.strip()
        else:
            self._raw_text = _normalize_notification_text(text)
        self._update_text()

    def set_style(self, style: str):
        """Set notification visual style: 'alert' (red) | 'rgb-breathing' | '' (default)."""
        self._style = style
        if style == "alert":
            self._dot.setStyleSheet("font-size: 10px; color: #ef4444;")
        elif style == "rgb-breathing":
            self._dot.setText("✓")
            self._dot.setStyleSheet("font-size: 10px; color: #22c55e;")
        else:
            self._dot.setText("●")
            self._dot.setStyleSheet("font-size: 10px; color: #22c55e;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self):
        if not self._raw_text:
            self._text.clear()
            return
        if self._multiline:
            self._text.setText(self._raw_text)
            return
        available_width = max(0, self._text.width())
        if available_width <= 0:
            self._text.setText(self._raw_text)
            return
        elided = self._text.fontMetrics().elidedText(
            self._raw_text,
            Qt.TextElideMode.ElideRight,
            available_width,
        )
        self._text.setText(elided)

    def _open_portal(self):
        self.window()._open_portal()

    def refresh_portal_visibility(self):
        self.window().refresh_portal_visibility()


# ── Dynamic Island ──

class DynamicIsland(QWidget):
    """Desktop panel widget. Docks to screen top, hides when idle."""

    message_sent = pyqtSignal(str)
    settings_requested = pyqtSignal()
    stream_finished = pyqtSignal(str, str)  # role, text_content

    W_HIDDEN, H_HIDDEN = 80, 8
    W_NOTIFY_MIN = 200
    W_NOTIFY_MAX = 500
    W_NOTIFY_MULTILINE = 420
    H_NOTIFY = 48
    NOTIFY_MAX_HEIGHT = 200
    W_CHAT, H_CHAT = 420, 520
    PADDING = 16
    RADIUS = 20

    def __init__(self):
        super().__init__()
        self._state = "HIDDEN"
        self._dragging = False
        self._drag_offset = QPoint()
        self._drag_start_pos = QPoint()
        self._current_bubble: MessageBubble | None = None
        self._bubbles: list[MessageBubble] = []
        self._pending_bubbles: list[tuple[str, str]] = []
        self._bg_color = BG_COLOR_HIDDEN
        self._stream_buffer: list[str] = []
        self._stream_active = False
        self._anim: QPropertyAnimation | None = None
        self._notify_style = ""       # "alert" | "rgb-breathing" | ""
        self._rgb_hue = 120.0         # RGB breathing hue (start from green)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)

        self._mouse_poll = QTimer(self)
        self._mouse_poll.setInterval(100)
        self._mouse_poll.timeout.connect(self._poll_mouse)
        self._mouse_poll.start()
        self._was_near_strip = False

        self._rgb_timer = QTimer(self)
        self._rgb_timer.setInterval(30)  # ~33 fps for smooth animation
        self._rgb_timer.timeout.connect(self._on_rgb_tick)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(0, 0)

        self._init_ui()
        self._init_position()
        self._refresh_multiline_mode()
        self._apply_state(animate=False)
        self.refresh_portal_visibility()

    # ── UI ──

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hidden-state indicator (8px bar, no content)
        self._hidden_bar = QWidget(self)
        self._hidden_bar.setFixedHeight(self.H_HIDDEN)
        self._hidden_bar.setStyleSheet("background: transparent;")
        root.addWidget(self._hidden_bar)

        self._notify = NotifyStrip(self)
        self._notify.setFixedHeight(self.H_NOTIFY)
        root.addWidget(self._notify)

        self._chat_area = QWidget(self)
        chat_layout = QVBoxLayout(self._chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Menu bar (chat state only)
        menu_bar = QWidget()
        menu_bar.setFixedHeight(28)
        menu_bar.setStyleSheet("background: transparent;")
        menu_layout = QHBoxLayout(menu_bar)
        menu_layout.setContentsMargins(self.PADDING, 0, self.PADDING - 4, 0)
        menu_layout.setSpacing(4)

        menu_layout.addStretch()

        self._chat_portal_btn = QPushButton("🏠")
        self._chat_portal_btn.setFixedSize(24, 24)
        self._chat_portal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chat_portal_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #a1a1aa; border: none;"
            "  font-size: 13px; padding: 0;"
            "}"
            "QPushButton:hover { color: #e4e4e7; }"
        )
        self._chat_portal_btn.clicked.connect(self._open_portal)
        menu_layout.addWidget(self._chat_portal_btn)

        gear_btn = QPushButton("⚙")
        gear_btn.setFixedSize(24, 24)
        gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gear_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #a1a1aa; border: none;"
            "  font-size: 13px; padding: 0;"
            "}"
            "QPushButton:hover { color: #e4e4e7; }"
        )
        gear_btn.clicked.connect(self.settings_requested.emit)
        menu_layout.addWidget(gear_btn)

        chat_layout.addWidget(menu_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_COLOR.name()};")
        sep.setFixedHeight(1)
        chat_layout.addWidget(sep)

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
        self._scroll_layout.setContentsMargins(self.PADDING, 14, self.PADDING, 14)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._scroll_content)
        # Viewport margins keep content away from rounded corners
        self._scroll.setViewportMargins(0, 8, 0, 8)
        chat_layout.addWidget(self._scroll, stretch=1)

        # Input bar
        # Quick action buttons
        quick_bar = QWidget()
        quick_bar.setStyleSheet("background: transparent;")
        quick_layout = QHBoxLayout(quick_bar)
        quick_layout.setContentsMargins(self.PADDING, 6, self.PADDING, 0)
        quick_layout.setSpacing(8)

        approve_btn = QPushButton("Approve")
        approve_btn.setFixedHeight(26)
        approve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        approve_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: #166534; color: #4ade80; border: 1px solid #22c55e;"
            f"  border-radius: 6px; padding: 0 12px; font-size: 11px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background: #14532d; }}"
        )
        approve_btn.clicked.connect(lambda: self._input_field.setText("/approve"))
        quick_layout.addWidget(approve_btn)

        reject_btn = QPushButton("Deny")
        reject_btn.setFixedHeight(26)
        reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reject_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: #78350f; color: #fcd34d; border: 1px solid #f59e0b;"
            f"  border-radius: 6px; padding: 0 12px; font-size: 11px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background: #92400e; }}"
        )
        reject_btn.clicked.connect(lambda: self._input_field.setText("/deny"))
        quick_layout.addWidget(reject_btn)

        quick_layout.addStretch()
        chat_layout.addWidget(quick_bar)

        input_bar = QWidget()
        input_bar.setMinimumHeight(70)
        input_bar.setStyleSheet(f"background: transparent; border-top: 1px solid {BORDER_COLOR.name()};")
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(self.PADDING, 10, self.PADDING, 14)
        input_layout.setSpacing(10)

        self._input_field = QTextEdit()
        self._input_field.setPlaceholderText("Message Hermes...")
        self._input_field.setAcceptRichText(False)
        self._input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input_field.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input_field.setFixedHeight(50)
        self._input_field.setStyleSheet(
            f"QTextEdit {{"
            f"  background: {INPUT_BG}; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {INPUT_BORDER}; border-radius: 10px;"
            f"  padding: 8px 14px; font-size: 13px;"
            f"}}"
            f"QTextEdit:focus {{ border-color: {ACCENT}; }}"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: #3f3f46; border-radius: 2px; }}"
        )
        self._input_field.installEventFilter(self)
        input_layout.addWidget(self._input_field, stretch=1)

        self._send_btn = QPushButton(">")
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

        self._chat_area.setVisible(False)

    def _init_position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        saved_x = int(get("panel/x") or -1)
        x = saved_x if saved_x >= 0 else (screen.width() - self.W_HIDDEN) // 2
        self.move(x, 0)

    def _is_multiline(self) -> bool:
        return get("panel/multiline_notify").lower() in ("true", "1", "yes")

    def _refresh_multiline_mode(self):
        self._notify.set_multiline_mode(self._is_multiline())

    # ── State ──

    def _apply_state(self, animate: bool = True):
        self._refresh_multiline_mode()
        geo = self.geometry()
        hide_delay = int(get("panel/hide_delay_ms") or 5000)
        self._hide_timer.setInterval(hide_delay)

        screen_w = QApplication.primaryScreen().availableGeometry().width()
        center_x = geo.x() + geo.width() / 2

        if self._state == "HIDDEN":
            target = QRect(
                max(0, min(int(center_x - self.W_HIDDEN / 2), screen_w - self.W_HIDDEN)),
                geo.y(), self.W_HIDDEN, self.H_HIDDEN,
            )
            self._hidden_bar.setVisible(True)
            self._notify.setVisible(False)
            self._chat_area.setVisible(False)
            self._hide_timer.stop()
            self._bg_color = BG_COLOR_HIDDEN
        elif self._state == "NOTIFY":
            w = self._calc_notify_width()
            h = self._calc_notify_height(w)
            target = QRect(
                max(0, min(int(center_x - w / 2), screen_w - w)),
                geo.y(), w, h,
            )
            self._hidden_bar.setVisible(False)
            self._notify.setVisible(True)
            self._notify.setFixedHeight(h)
            self._chat_area.setVisible(False)
            self._hide_timer.start()
        else:
            target = QRect(
                max(0, min(int(center_x - self.W_CHAT / 2), screen_w - self.W_CHAT)),
                geo.y(), self.W_CHAT, self.H_CHAT,
            )
            self._hidden_bar.setVisible(False)
            self._notify.setVisible(False)
            self._chat_area.setVisible(True)
            self._hide_timer.stop()
            self._flush_pending()
            self._flush_stream_buffer()

        self._bg_color = BG_COLOR
        duration, easing = self._animation_profile(geo, target)

        if animate and geo != target:
            if self._anim and self._anim.state() == QAbstractAnimation.State.Running:
                self._anim.stop()
                self._anim.deleteLater()

            self.setMinimumSize(0, 0)
            self.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

            anim = QPropertyAnimation(self, b"geometry", self)
            self._anim = anim
            anim.setDuration(duration)
            anim.setStartValue(geo)
            anim.setEndValue(target)
            anim.setEasingCurve(easing)
            anim.finished.connect(lambda: self._finish_animation(anim, target))
            anim.start()
        else:
            self.setFixedSize(target.size())
            self.setGeometry(target)

        self.refresh_portal_visibility()

    def _animation_profile(self, current: QRect, target: QRect) -> tuple[int, QEasingCurve.Type]:
        is_expanding = target.width() * target.height() > current.width() * current.height()
        if not is_expanding:
            return 240, QEasingCurve.Type.InOutCubic
        if target.height() == self.H_NOTIFY:
            return 320, QEasingCurve.Type.OutBack
        return 360, QEasingCurve.Type.OutBack

    def _finish_animation(self, anim: QPropertyAnimation, target: QRect):
        if self._anim is not anim:
            return
        self.setGeometry(target)
        self.setFixedSize(target.size())
        self._anim = None
        anim.deleteLater()
        self._scroll_to_bottom()

    def _go_hidden(self):
        self._state = "HIDDEN"
        self._apply_state()

    def _on_hide_timeout(self):
        if self._state != "NOTIFY":
            return
        cursor_pos = QCursor.pos()
        if self.frameGeometry().adjusted(-10, -5, 10, 20).contains(cursor_pos):
            self._hide_timer.start()
            return
        self._go_hidden()

    def _calc_notify_width(self) -> int:
        text = self._notify._raw_text
        if not text:
            return self.W_NOTIFY_MIN
        fm = self._notify._text.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        portal_w = 32 if self._notify._portal_btn.isVisible() else 0
        total = self.PADDING + 18 + 8 + text_w + portal_w + self.PADDING + 10
        if self._is_multiline():
            # In multiline mode, prefer wider width to show more text
            return max(self.W_NOTIFY_MIN, min(total, self.W_NOTIFY_MULTILINE))
        return max(self.W_NOTIFY_MIN, min(total, self.W_NOTIFY_MAX))

    def _calc_notify_height(self, width: int) -> int:
        if not self._is_multiline():
            return self.H_NOTIFY
        text = self._notify._raw_text
        if not text:
            return self.H_NOTIFY
        fm = self._notify._text.fontMetrics()
        # Available content width = window width minus layout margins and other widgets
        portal_w = 24 + 8 if self._notify._portal_btn.isVisible() else 0
        content_w = max(1, width - 12 - 18 - 8 - portal_w - 12)
        rect = fm.boundingRect(
            QRect(0, 0, content_w, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
            text,
        )
        # Height = text height + top padding + bottom padding
        h = rect.height() + 6 + 6 + 4  # +4 for some breathing room
        return max(self.H_NOTIFY, min(h, self.NOTIFY_MAX_HEIGHT))

    def _flush_pending(self):
        if not self._pending_bubbles:
            return
        for role, text in self._pending_bubbles:
            bubble = MessageBubble(role, text, self._scroll_content)
            self._scroll_layout.addWidget(bubble)
            self._bubbles.append(bubble)
        self._pending_bubbles.clear()
        self._scroll_to_bottom()

    def _flush_stream_buffer(self):
        """When entering CHAT, create a bubble from accumulated stream text."""
        if not self._stream_buffer:
            return
        text = "".join(self._stream_buffer)
        self._stream_buffer.clear()
        bubble = MessageBubble("assistant", text, self._scroll_content)
        self._scroll_layout.addWidget(bubble)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    # ── Mouse polling (hidden strip hover) ──

    def _poll_mouse(self):
        if self._state != "HIDDEN":
            self._was_near_strip = False
            return

        cursor_pos = QCursor.pos()
        detect_rect = self.frameGeometry().adjusted(-30, -5, 30, 40)
        near = detect_rect.contains(cursor_pos)

        if near and not self._was_near_strip:
            self._was_near_strip = True
            self._state = "NOTIFY"
            self._notify.set_notification("Hermes - Click to open")
            self._apply_state()
        elif not near and self._was_near_strip:
            self._was_near_strip = False
            self._go_hidden()

    # ── Public API ──

    def show_notification(self, text: str, style: str = ""):
        # Auto-detect visual style from text content if server didn't provide one
        if not style:
            if "⚠️" in text:
                style = "alert"
            elif "✅" in text:
                style = "rgb-breathing"
        self._notify_style = style
        self._notify.set_style(style)
        self._notify.set_notification(text)
        if style == "rgb-breathing":
            self._rgb_hue = 120.0  # start from green
            self._rgb_timer.start()
        elif style != "rgb-breathing" and self._rgb_timer.isActive():
            self._rgb_timer.stop()
        if self._state == "HIDDEN":
            self._state = "NOTIFY"
            self._apply_state()
        elif self._state == "NOTIFY":
            self._apply_state()
        else:
            self.add_system_bubble(text)

    def start_stream(self):
        """Start a streaming response from Hermes. Does NOT force CHAT — buffers deltas during NOTIFY."""
        self._stream_active = True
        self._stream_buffer.clear()

        if self._state == "CHAT":
            # Already in chat: create bubble immediately
            self._current_bubble = MessageBubble("assistant", "", self._scroll_content)
            self._scroll_layout.addWidget(self._current_bubble)
            self._bubbles.append(self._current_bubble)
            self._scroll_to_bottom()
        else:
            # Show notification with placeholder
            self.show_notification("Hermes is responding...")

    def append_delta(self, text: str):
        if self._state == "CHAT" and self._current_bubble:
            self._current_bubble.append_text(text)
            self._scroll_to_bottom()
        else:
            # Buffer during NOTIFY
            self._stream_buffer.append(text)
            # Update notification with accumulated text (first 100 chars)
            accumulated = "".join(self._stream_buffer)
            preview = accumulated[:100] + ("..." if len(accumulated) > 100 else "")

            # Auto-detect visual style from accumulated content
            style = ""
            if "⚠️" in accumulated:
                style = "alert"
                self._rgb_timer.stop()
            elif "✅" in accumulated:
                style = "rgb-breathing"
                self._rgb_hue = 120.0  # start from green
                self._rgb_timer.start()
            else:
                self._rgb_timer.stop()
            self._notify_style = style
            self._notify.set_style(style)

            self._notify.set_notification(preview)
            if self._state == "NOTIFY":
                self._apply_state()  # refresh width

    def end_stream(self):
        self._stream_active = False
        # Emit signal for persistence regardless of done_received
        if self._state == "CHAT" and self._current_bubble:
            content = self._current_bubble.text_content
            if content:
                self.stream_finished.emit("assistant", content)
        self._current_bubble = None
        if self._state != "CHAT":
            # Still in NOTIFY: keep showing the preview
            if self._stream_buffer:
                accumulated = "".join(self._stream_buffer)
                preview = accumulated[:120] + ("..." if len(accumulated) > 120 else "")
                self._notify.set_notification(preview)
            # Still in NOTIFY: keep showing the preview
            if self._stream_buffer:
                accumulated = "".join(self._stream_buffer)
                preview = accumulated[:120] + ("..." if len(accumulated) > 120 else "")
                self._notify.set_notification(preview)
                if self._state == "NOTIFY":
                    self._apply_state()

    def add_user_bubble(self, text: str):
        if self._state != "CHAT":
            self._pending_bubbles.append(("user", text))
            self._state = "CHAT"
            self._apply_state()
            return
        bubble = MessageBubble("user", text, self._scroll_content)
        self._scroll_layout.addWidget(bubble)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    def add_system_bubble(self, text: str):
        if self._state != "CHAT":
            self._pending_bubbles.append(("assistant", text))
            return
        bubble = MessageBubble("assistant", text, self._scroll_content)
        self._scroll_layout.addWidget(bubble)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    def load_history(self, messages: list[dict]):
        for msg in messages:
            if msg["role"] == "assistant":
                bubble = MessageBubble(msg["role"], parent=self._scroll_content)
                bubble.set_html(msg["content"])
            else:
                bubble = MessageBubble(msg["role"], msg["content"], self._scroll_content)
            self._scroll_layout.addWidget(bubble)
            self._bubbles.append(bubble)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── Events ──

    def eventFilter(self, obj, event):
        if obj is self._input_field and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Shift+Enter: insert newline (default behavior, do nothing)
                    return False
                else:
                    # Enter only: send message
                    self._handle_send()
                    return True
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self._state == "CHAT":
                self._go_hidden()

    def enterEvent(self, event):
        if self._state == "NOTIFY":
            self._hide_timer.stop()

    def leaveEvent(self, event):
        if self._state == "NOTIFY":
            self._hide_timer.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_start_pos = self.pos()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            new_pos.setY(max(0, min(new_pos.y(), 60)))
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            moved = self.pos() != self._drag_start_pos
            if moved:
                set_("panel/x", self.x())
            elif self._state in ("HIDDEN", "NOTIFY"):
                self._state = "CHAT"
                self._apply_state()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        if self._state == "HIDDEN":
            painter.setBrush(QBrush(self._bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 4, 4)
        else:
            painter.setBrush(QBrush(BG_COLOR))
            # Determine border based on notification style
            if self._state == "NOTIFY" and self._notify_style == "alert":
                painter.setBrush(QBrush(QColor("#7f1d1d")))
                painter.setPen(QPen(QColor("#ef4444"), 2))
            elif self._state == "NOTIFY" and self._notify_style == "rgb-breathing":
                border_color = QColor.fromHslF(self._rgb_hue / 360.0, 1.0, 0.6)
                painter.setPen(QPen(border_color, 2))
            else:
                painter.setPen(QPen(BORDER_COLOR, 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), self.RADIUS, self.RADIUS)

        painter.end()

    # ── Internal ──

    def _handle_send(self):
        text = self._input_field.toPlainText().strip()
        if not text:
            return
        self._input_field.clear()
        self.add_user_bubble(text)
        _log.info("Sending message: %s...", text[:50])
        self.message_sent.emit(text)
        self._scroll_to_bottom()

    def _open_portal(self):
        url = _normalize_portal_url(get("portal/url"))
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def refresh_portal_visibility(self):
        visible = bool(_normalize_portal_url(get("portal/url")))
        self._notify._portal_btn.setVisible(visible)
        self._chat_portal_btn.setVisible(visible)

    def _on_rgb_tick(self):
        """Advance RGB breathing hue and repaint."""
        self._rgb_hue = (self._rgb_hue + 4.0) % 360.0
        self.update()
