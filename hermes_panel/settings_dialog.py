"""Settings dialog for Hermes Desktop Panel."""

import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QPushButton, QGroupBox,
)

from hermes_panel.config import get, set_


class SettingsDialog(QDialog):
    """Configuration dialog for server connection, panel behavior, and system settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hermes Panel Settings")
        self.setMinimumWidth(400)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # -- Server --
        server_group = QGroupBox("Server connection")
        server_form = QFormLayout()

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("127.0.0.1")
        server_form.addRow("Host:", self._host_input)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(8643)
        server_form.addRow("Port:", self._port_input)

        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_input.setPlaceholderText("Enter auth token")
        server_form.addRow("Token:", self._token_input)

        self._tls_check = QCheckBox("Enable TLS (wss://)")
        server_form.addRow(self._tls_check)

        self._verify_cert_check = QCheckBox("Verify TLS certificate")
        server_form.addRow(self._verify_cert_check)

        server_group.setLayout(server_form)
        layout.addWidget(server_group)

        # -- Panel --
        panel_group = QGroupBox("Panel behavior")
        panel_form = QFormLayout()

        self._hide_delay = QSpinBox()
        self._hide_delay.setRange(1000, 30000)
        self._hide_delay.setSuffix(" ms")
        self._hide_delay.setSingleStep(500)
        panel_form.addRow("Auto-hide delay:", self._hide_delay)

        self._multiline_check = QCheckBox("Multi-line notification (dynamic height)")
        panel_form.addRow(self._multiline_check)

        panel_group.setLayout(panel_form)
        layout.addWidget(panel_group)

        # -- Portal --
        portal_group = QGroupBox("Portal")
        portal_form = QFormLayout()

        self._portal_url_input = QLineEdit()
        self._portal_url_input.setPlaceholderText("https://example.com")
        portal_form.addRow("URL:", self._portal_url_input)

        portal_group.setLayout(portal_form)
        layout.addWidget(portal_group)

        # -- System --
        system_group = QGroupBox("System")
        system_form = QFormLayout()

        self._autostart_check = QCheckBox("Launch at startup")
        system_form.addRow(self._autostart_check)

        system_group.setLayout(system_form)
        layout.addWidget(system_group)

        # -- Buttons --
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _load_values(self):
        self._host_input.setText(get("server/host"))
        self._port_input.setValue(int(get("server/port") or 8643))
        self._token_input.setText(get("server/token"))
        self._tls_check.setChecked(get("server/tls").lower() in ("true", "1", "yes"))
        self._verify_cert_check.setChecked(get("server/verify_cert").lower() in ("true", "1", "yes"))
        self._hide_delay.setValue(int(get("panel/hide_delay_ms") or 5000))
        self._multiline_check.setChecked(get("panel/multiline_notify").lower() in ("true", "1", "yes"))
        self._portal_url_input.setText(get("portal/url"))
        self._autostart_check.setChecked(get("app/autostart").lower() in ("true", "1", "yes"))

    def _save(self):
        set_("server/host", self._host_input.text())
        set_("server/port", self._port_input.value())
        set_("server/token", self._token_input.text())
        set_("server/tls", self._tls_check.isChecked())
        set_("server/verify_cert", self._verify_cert_check.isChecked())
        set_("panel/hide_delay_ms", self._hide_delay.value())
        set_("panel/multiline_notify", self._multiline_check.isChecked())
        set_("portal/url", self._portal_url_input.text().strip())
        set_("app/autostart", self._autostart_check.isChecked())

        self._apply_autostart(self._autostart_check.isChecked())
        self.accept()

    def _apply_autostart(self, enable: bool):
        if sys.platform != "win32":
            return

        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
        except OSError:
            return

        if enable:
            exe = sys.executable
            script = sys.argv[0]
            winreg.SetValueEx(key, "HermesPanel", 0, winreg.REG_SZ, f'"{exe}" "{script}"')
        else:
            try:
                winreg.DeleteValue(key, "HermesPanel")
            except OSError:
                pass
        winreg.CloseKey(key)
