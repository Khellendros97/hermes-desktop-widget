"""System tray manager for Hermes Desktop Panel."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


RESOURCES = Path(__file__).parent / "resources"


class TrayManager(QSystemTrayIcon):
    """System tray icon with right-click context menu."""

    show_panel_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(self._make_icon())
        self.setToolTip("Hermes Panel")

        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)
        self.show()

    def _make_icon(self) -> QIcon:
        icon_path = RESOURCES / "icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))

        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(0, 0, 0, 0))
        p = QPainter(pixmap)
        p.setPen(QColor(200, 200, 200))
        p.drawText(pixmap.rect(), 0x84, "H")
        p.end()
        return QIcon(pixmap)

    def _build_menu(self):
        show_action = QAction("show/hide panel", self._menu)
        show_action.triggered.connect(self.show_panel_requested.emit)
        self._menu.addAction(show_action)

        self._menu.addSeparator()

        settings_action = QAction("settings", self._menu)
        settings_action.triggered.connect(self.settings_requested.emit)
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        quit_action = QAction("quit", self._menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_action)
