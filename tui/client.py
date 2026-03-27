"""WebSocket client for JMessage relay."""

import json
import logging
import ssl
import threading
import time

from textual.message import Message

log = logging.getLogger("jmessage.client")


class ServerMessage(Message):
    """A message received from the relay server."""

    def __init__(self, msg_type: str, data) -> None:
        self.msg_type = msg_type
        self.data = data
        super().__init__()


class ConnectionStatus(Message):
    """Connection state change."""

    def __init__(self, connected: bool, error: str = "") -> None:
        self.connected = connected
        self.error = error
        super().__init__()


class SendFailed(Message):
    """A send attempt failed (disconnected or error)."""

    def __init__(self, chat_id: str, text: str, reason: str) -> None:
        self.chat_id = chat_id
        self.text = text
        self.reason = reason
        super().__init__()


class RelayClient:
    """Threaded WebSocket client that posts Textual messages to the app."""

    def __init__(self, app, relay_url: str, auth_token: str, certs=None) -> None:
        self.app = app
        self.relay_url = relay_url
        self.auth_token = auth_token
        self.certs = certs or {}
        self._stop = threading.Event()
        self._thread = None
        self._ws = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _make_ssl_context(self):
        ca = self.certs.get("ca")
        cert = self.certs.get("client_cert")
        key = self.certs.get("client_key")
        if not ca or not cert or not key:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(ca)
        ctx.load_cert_chain(cert, key)
        return ctx

    def _post(self, msg):
        """Post a Textual message to the app from the background thread."""
        try:
            self.app.call_from_thread(self.app.post_message, msg)
        except Exception:
            pass  # app may be shutting down

    def _run(self) -> None:
        import websockets.sync.client as ws_sync

        backoff = 1
        self._post(ConnectionStatus(connected=False, error="Connecting..."))

        while not self._stop.is_set():
            try:
                ssl_ctx = self._make_ssl_context()
                with ws_sync.connect(self.relay_url, ssl=ssl_ctx, max_size=50 * 1024 * 1024) as ws:
                    ws.send(json.dumps({"type": "auth", "token": self.auth_token}))
                    self._post(ConnectionStatus(connected=True))
                    backoff = 1
                    self._ws = ws

                    while not self._stop.is_set():
                        try:
                            raw = ws.recv(timeout=1.0)
                        except TimeoutError:
                            continue
                        # Parse each message independently — don't kill connection on bad data
                        try:
                            msg = json.loads(raw)
                            self._post(ServerMessage(msg["type"], msg.get("data", {})))
                        except (json.JSONDecodeError, KeyError, TypeError) as e:
                            log.warning(f"Malformed message: {e}")
                            continue

            except (ssl.SSLError, FileNotFoundError) as e:
                log.error(f"Certificate error: {e}")
                self._ws = None
                self._post(ConnectionStatus(connected=False, error=f"Certificate error: {e}"))
                if self._stop.is_set():
                    break
                # Cert errors won't self-resolve — slow retry
                time.sleep(60)

            except Exception as e:
                log.warning(f"Connection lost: {e}")
                self._ws = None
                self._post(ConnectionStatus(connected=False, error=str(e)))
                if self._stop.is_set():
                    break
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def send(self, msg: dict) -> bool:
        """Send a JSON message to the relay. Returns True if sent."""
        ws = self._ws
        if not ws:
            return False
        try:
            ws.send(json.dumps(msg))
            return True
        except Exception as e:
            log.error(f"Send failed: {e}")
            return False

    def request_conversations(self) -> None:
        self.send({"type": "get_conversations"})

    def request_history(self, chat_id: str, limit: int = 50) -> None:
        self.send({"type": "get_history", "data": {"chat_id": chat_id, "limit": limit}})

    def send_message(self, chat_id: str, text: str) -> None:
        if not self.send({"type": "send", "data": {"chat_id": chat_id, "text": text}}):
            self._post(SendFailed(chat_id, text, "Not connected"))

    def request_chat_attachments(self, chat_id: str) -> None:
        self.send({"type": "get_chat_attachments", "data": {"chat_id": chat_id}})

    def request_attachment_data(self, att_id: int, path: str) -> None:
        self.send({"type": "get_attachment_data", "data": {"id": att_id, "path": path}})

    def request_chat_members(self, chat_id: str) -> None:
        self.send({"type": "get_chat_members", "data": {"chat_id": chat_id}})

    def search(self, query: str, limit: int = 50) -> None:
        self.send({"type": "search", "data": {"query": query, "limit": limit}})

    def request_tapbacks(self, chat_id: str) -> None:
        self.send({"type": "get_tapbacks", "data": {"chat_id": chat_id}})
