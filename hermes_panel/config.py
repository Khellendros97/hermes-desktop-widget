"""Configuration management via QSettings. All modules import SETTINGS from here."""
from PyQt6.QtCore import QSettings

SETTINGS = QSettings("HermesPanel", "config")

DEFAULTS = {
    "server/host": "127.0.0.1",
    "server/port": 8643,
    "server/token": "",
    "server/tls": False,
    "server/verify_cert": True,
    "panel/x": -1,
    "panel/hide_delay_ms": 5000,
    "portal/url": "",
    "app/autostart": False,
}

def get(key: str) -> str:
    val = SETTINGS.value(key, DEFAULTS.get(key, ""))
    # QSettings stores bools natively; normalize to string for callers
    if isinstance(val, bool):
        return "true" if val else "false"
    if val is None:
        return ""
    return str(val)

def set_(key: str, value):
    SETTINGS.setValue(key, value)
