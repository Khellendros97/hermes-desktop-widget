"""WebSocket client for communicating with the Hermes desktop adapter.

Manages connection lifecycle: connect, authenticate, heartbeat, auto-reconnect.
Emits Qt signals for UI integration.
"""

import json
import logging
import time
import threading
from typing import Optional

import websocket
from PyQt6.QtCore import QObject, pyqtSignal

_log = logging.getLogger(__name__)
from PyQt6.QtCore import QObject, pyqtSignal

from hermes_panel.protocol import (
    OutgoingMessage, deserialize,
    IncomingDelta, IncomingDone, IncomingNotification,
    IncomingError, IncomingAuthOk,
)


class HermesClient(QObject):
    """Connects to Hermes desktop WebSocket server and translates messages to Qt signals."""

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    auth_ok = pyqtSignal()
    delta_received = pyqtSignal(str, int)
    done_received = pyqtSignal(str)
    notification_received = pyqtSignal(str, str, str)  # text, level, style
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._should_stop = False
        self._reconnect_delay = 1
        self._url = ""
        self._token = ""
        self._verify_cert = True

        # -- Connection state tracking for on-demand reconnect --
        self._connected = False
        self._connected_event = threading.Event()
        self._wake_reconnect = threading.Event()

    def connect_to_server(self, host: str, port: int, token: str, tls: bool = True, verify_cert: bool = True):
        self._should_stop = False
        self._url = f"{'wss' if tls else 'ws'}://{host}:{port}/ws"
        self._token = token
        self._verify_cert = verify_cert
        self._reconnect_delay = 1
        self._start()

    def disconnect(self):
        self._should_stop = True
        self._wake_reconnect.set()  # Wake the reconnect loop so it sees should_stop
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def send_message(self, text: str, reconnect_timeout: float = 5.0):
        """Send a message, automatically reconnecting if the connection is lost.

        If the WebSocket is not currently connected, attempts an on-demand
        reconnect (with exponential backoff reset) before sending. Returns
        immediately if reconnect fails within *reconnect_timeout* seconds.
        """
        if not self._connected:
            _log.info("send_message: not connected, attempting on-demand reconnect...")
            self._reconnect_now(reconnect_timeout)

        if not self._connected:
            _log.warning("send_message: reconnect failed, giving up")
            self.error_occurred.emit("Not connected to server (reconnect failed)")
            return

        try:
            msg = OutgoingMessage(text=text)
            self._ws.send(msg.to_json())
            _log.info("Message sent: %s...", text[:50])
        except Exception as e:
            _log.error("send_message failed: %s", e)
            self.error_occurred.emit(f"Send failed: {e}")

    # -- Internal --

    def _start(self):
        self._connected_event.clear()
        self._wake_reconnect.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._should_stop:
            self._ws = websocket.WebSocketApp(
                self._url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            ssl_opt = {"cert_reqs": 0} if self._url.startswith("wss://") and not self._verify_cert else {}
            self._ws.run_forever(ping_interval=30, ping_timeout=10, sslopt=ssl_opt or None)

            if self._should_stop:
                break

            # Wait for the reconnect delay, but allow early wake via _wake_reconnect.
            # When woken (user triggered a reconnect), don't double the delay.
            woken = self._wake_reconnect.wait(timeout=self._reconnect_delay)
            self._wake_reconnect.clear()
            if self._should_stop:
                break
            if not woken:
                # Only backoff on timeout, not on manual wake
                self._reconnect_delay = min(self._reconnect_delay * 2, 30)

    def _reconnect_now(self, timeout: float):
        """Force an immediate reconnect from the caller's thread.

        Resets the backoff timer, wakes the reconnect loop, closes any stale
        connection, and blocks until a new connection is established (or
        *timeout* seconds elapse).
        """
        self._reconnect_delay = 1
        self._connected_event.clear()
        self._wake_reconnect.set()  # Wake the background loop's sleep

        # Closing the old ws causes on_close → run_forever returns → loop restarts
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        # Wait for the new connection to come up
        self._connected_event.wait(timeout=timeout)

    def _on_open(self, ws):
        self._reconnect_delay = 1
        auth_msg = OutgoingMessage(type_="auth", token=self._token)
        ws.send(auth_msg.to_json())
        self._connected = True
        self._connected_event.set()
        self.connected.emit()

    def _on_message(self, ws, raw: str):
        msg = deserialize(raw)
        if msg is None:
            _log.debug("_on_message: unknown or unparseable: %s", raw[:200])
            return

        _log.debug("_on_message: type=%s", type(msg).__name__)
        if isinstance(msg, IncomingAuthOk):
            self.auth_ok.emit()
        elif isinstance(msg, IncomingDelta):
            self.delta_received.emit(msg.text, msg.seq)
        elif isinstance(msg, IncomingDone):
            _log.info("_on_message: done with session_id=%r", msg.session_id)
            self.done_received.emit(msg.session_id)
        elif isinstance(msg, IncomingNotification):
            self.notification_received.emit(msg.text, msg.level, msg.style)
        elif isinstance(msg, IncomingError):
            self.error_occurred.emit(msg.text)

    def _on_error(self, ws, error):
        pass

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected = False
        self._connected_event.clear()
        self.disconnected.emit()
