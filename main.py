"""main.py — Hermes Desktop Panel entry point."""

import sys
import os
import logging
import traceback
from pathlib import Path

# Write logs to file for debugging
LOG_PATH = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "HermesPanel" / "panel.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
_log = logging.getLogger("main")

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from hermes_panel.config import get
from hermes_panel.client import HermesClient
from hermes_panel.store import MessageStore
from hermes_panel.tray import TrayManager
from hermes_panel.panel import DynamicIsland
from hermes_panel.settings_dialog import SettingsDialog


def _get_db_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(base, "HermesPanel")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        db_dir = os.path.join(base, "hermes-panel")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "messages.db")


class Application:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._apply_app_style()

        style_path = Path(__file__).parent / "hermes_panel" / "resources" / "styles.qss"
        if style_path.exists():
            self._app.setStyleSheet(style_path.read_text(encoding="utf-8"))

        self._store = MessageStore(_get_db_path())
        self._client = HermesClient()
        self._panel = DynamicIsland()
        self._panel.show()
        self._tray = TrayManager()

        self._last_saved = ""  # deduplicate assistant saves

        self._connect_signals()
        self._connect_to_server()
        self._load_history()

    def _apply_app_style(self):
        """Use the same non-native style as the validated prototype."""
        self._app.setStyle("Fusion")
        palette = self._app.palette()
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
        self._app.setPalette(palette)

    def _connect_signals(self):
        self._panel.message_sent.connect(self._on_user_message_sent)

        self._client.delta_received.connect(self._on_delta)
        self._client.done_received.connect(self._on_done)
        self._client.notification_received.connect(self._on_notification)
        self._client.error_occurred.connect(self._panel.show_notification)
        self._client.auth_ok.connect(lambda: None)

        self._panel.stream_finished.connect(self._on_stream_finished)

        self._tray.show_panel_requested.connect(self._toggle_panel)
        self._tray.settings_requested.connect(self._show_settings)
        self._tray.quit_requested.connect(self._quit)

        self._panel.settings_requested.connect(self._show_settings)

    def _connect_to_server(self):
        host = get("server/host")
        port = int(get("server/port") or 8643)
        token = get("server/token")
        tls = get("server/tls").lower() in ("true", "1", "yes")
        verify_cert = get("server/verify_cert").lower() in ("true", "1", "yes")

        _log.info("Config: host=%s port=%s token=%r tls=%s verify=%s",
                  host, port, token, tls, verify_cert)

        if token:
            self._client.connect_to_server(host, port, token, tls, verify_cert)
        else:
            _log.info("No token configured, showing notification")
            self._panel.show_notification("config token in settings")

    def _load_history(self):
        try:
            msgs = self._store.get_messages(limit=50)
            if msgs:
                self._panel.load_history(msgs)
        except Exception:
            pass

    def _on_user_message_sent(self, text: str):
        self._save_last_assistant()
        self._store.save_message("user", text)
        self._client.send_message(text)

    def _on_stream_finished(self, role: str, text: str):
        _log.info("_on_stream_finished: saving %s message", role)
        self._store.save_message(role, text)

    def _on_delta(self, text: str, seq: int):
        if seq == 0:
            self._save_last_assistant()
            self._panel.start_stream()
        self._panel.append_delta(text)

    def _save_last_assistant(self):
        """Save the most recent assistant bubble to store (deduplicated)."""
        for bubble in reversed(self._panel._bubbles):
            if bubble.role == "assistant" and bubble.text_content:
                content = bubble.text_content
                if content != self._last_saved:
                    self._store.save_message("assistant", content)
                    self._last_saved = content
                break

    def _on_done(self, session_id: str):
        self._panel.end_stream()
        self._save_last_assistant()

    def _on_notification(self, text: str, level: str):
        self._panel.show_notification(text)

    def _show_settings(self):
        dialog = SettingsDialog()
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self._client.disconnect()
            self._connect_to_server()
            self._panel.refresh_portal_visibility()

    def _toggle_panel(self):
        if self._panel._state == "HIDDEN":
            self._panel._state = "CHAT"
            self._panel._apply_state()
        else:
            self._panel._go_hidden()

    def _quit(self):
        self._save_last_assistant()
        self._client.disconnect()
        self._store.close()
        self._app.quit()

    def run(self):
        return self._app.exec()


def main():
    sys.excepthook = lambda t, v, tb: (
        traceback.print_exception(t, v, tb),
        _log.critical("Unhandled exception", exc_info=(t, v, tb)),
    )
    _log.info("Hermes Panel starting")
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
