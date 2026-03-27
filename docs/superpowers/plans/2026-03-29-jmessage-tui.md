# JMessage TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a terminal-native iMessage client using Textual that connects to the existing Mac relay over WebSocket.

**Architecture:** Single Python package with 4 files — entry point/app (`jmessage.py`), WebSocket client (`client.py`), conversation screen (`screens/conversation.py`), and conversation list screen (`screens/conversation_list.py`). The app connects to the existing Mac relay via mTLS WebSocket, receives real-time message pushes, and renders them in a keyboard-driven TUI.

**Tech Stack:** Python 3.11+, Textual (TUI framework), websockets (async WebSocket client), Rich (text rendering via Textual)

---

### Task 1: Project Setup and Dependencies

**Files:**
- Create: `tui/requirements.txt`
- Create: `tui/config.example.json`
- Create: `tui/.gitignore`

- [ ] **Step 1: Create the tui directory**

```bash
mkdir -p c:/ai/jmessage/tui/screens
```

- [ ] **Step 2: Create requirements.txt**

Create `tui/requirements.txt`:
```
textual>=3.0.0
websockets>=13.0
```

- [ ] **Step 3: Create config.example.json**

Create `tui/config.example.json`:
```json
{
  "relay_url": "wss://192.168.1.40:8765",
  "auth_token": "your-secret-token",
  "certs": {
    "ca": "certs/ca.pem",
    "client_cert": "certs/client.pem",
    "client_key": "certs/client.key"
  }
}
```

- [ ] **Step 4: Create .gitignore**

Create `tui/.gitignore`:
```
config.json
certs/
__pycache__/
*.pyc
```

- [ ] **Step 5: Install dependencies**

```bash
cd c:/ai/jmessage/tui
pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add tui/requirements.txt tui/config.example.json tui/.gitignore
git commit -m "feat(tui): project scaffold with dependencies and config template"
```

---

### Task 2: WebSocket Client

**Files:**
- Create: `tui/client.py`

The WebSocket client runs as a background thread, connects to the Mac relay with mTLS, authenticates, and posts Textual messages to the app when data arrives. It handles reconnection with exponential backoff.

- [ ] **Step 1: Create client.py with custom Textual messages**

Create `tui/client.py`:
```python
"""WebSocket client for JMessage relay."""

import json
import logging
import ssl
import threading
import time
from pathlib import Path

from textual.message import Message

log = logging.getLogger("jmessage.client")


class ServerMessage(Message):
    """A message received from the relay server."""

    def __init__(self, msg_type: str, data: dict | list) -> None:
        self.msg_type = msg_type
        self.data = data
        super().__init__()


class ConnectionStatus(Message):
    """Connection state change."""

    def __init__(self, connected: bool, error: str = "") -> None:
        self.connected = connected
        self.error = error
        super().__init__()


class RelayClient:
    """Threaded WebSocket client that posts Textual messages to the app."""

    def __init__(self, app, relay_url: str, auth_token: str, certs: dict | None = None) -> None:
        self.app = app
        self.relay_url = relay_url
        self.auth_token = auth_token
        self.certs = certs or {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _make_ssl_context(self) -> ssl.SSLContext | None:
        ca = self.certs.get("ca")
        cert = self.certs.get("client_cert")
        key = self.certs.get("client_key")
        if not ca or not cert or not key:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(ca)
        ctx.load_cert_chain(cert, key)
        return ctx

    def _run(self) -> None:
        import websockets.sync.client as ws_sync

        backoff = 1
        while not self._stop.is_set():
            try:
                ssl_ctx = self._make_ssl_context()
                with ws_sync.connect(self.relay_url, ssl=ssl_ctx) as ws:
                    # Authenticate
                    ws.send(json.dumps({"type": "auth", "token": self.auth_token}))

                    self.app.call_from_thread(
                        self.app.post_message, ConnectionStatus(connected=True)
                    )
                    backoff = 1  # reset on successful connect

                    # Store ws ref so app can send through us
                    self._ws = ws

                    while not self._stop.is_set():
                        try:
                            raw = ws.recv(timeout=1.0)
                        except TimeoutError:
                            continue
                        msg = json.loads(raw)
                        self.app.call_from_thread(
                            self.app.post_message,
                            ServerMessage(msg["type"], msg.get("data", {})),
                        )

            except Exception as e:
                log.warning(f"Connection lost: {e}")
                self._ws = None
                self.app.call_from_thread(
                    self.app.post_message,
                    ConnectionStatus(connected=False, error=str(e)),
                )
                if self._stop.is_set():
                    break
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def send(self, msg: dict) -> None:
        """Send a JSON message to the relay. Called from the main thread."""
        ws = getattr(self, "_ws", None)
        if ws:
            try:
                ws.send(json.dumps(msg))
            except Exception as e:
                log.error(f"Send failed: {e}")

    def request_conversations(self) -> None:
        self.send({"type": "get_conversations"})

    def request_history(self, chat_id: str, limit: int = 50) -> None:
        self.send({"type": "get_history", "data": {"chat_id": chat_id, "limit": limit}})

    def send_message(self, chat_id: str, text: str) -> None:
        self.send({"type": "send", "data": {"chat_id": chat_id, "text": text}})
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd c:/ai/jmessage/tui
python -c "from client import RelayClient, ServerMessage, ConnectionStatus; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add tui/client.py
git commit -m "feat(tui): websocket client with mTLS, reconnect, and Textual message posting"
```

---

### Task 3: Conversation Screen

**Files:**
- Create: `tui/screens/__init__.py`
- Create: `tui/screens/conversation.py`

The main screen that shows chat messages and an input bar. Handles scrolling through messages, typing, and sending.

- [ ] **Step 1: Create screens/__init__.py**

Create `tui/screens/__init__.py`:
```python
```

(Empty file — just makes it a package.)

- [ ] **Step 2: Create conversation.py**

Create `tui/screens/conversation.py`:
```python
"""Conversation screen — displays messages and input bar for a single chat."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static


class MessageDisplay(Static):
    """A single message line with Rich markup."""
    pass


class ConversationScreen(Screen):
    """Main screen showing chat messages and input."""

    BINDINGS = [
        Binding("escape", "show_conversations", "Conversations", show=True),
    ]

    CSS = """
    ConversationScreen {
        layout: vertical;
        background: #1a1a2e;
    }
    #header {
        dock: top;
        height: 1;
        background: #16213e;
        color: #4fc3f7;
        padding: 0 1;
    }
    #header-right {
        dock: top;
        height: 1;
        background: #16213e;
        color: #666666;
        text-align: right;
        padding: 0 1;
    }
    #header-bar {
        dock: top;
        height: 1;
        layout: horizontal;
        background: #16213e;
    }
    #header-left {
        width: 1fr;
        background: #16213e;
        color: #4fc3f7;
        padding: 0 1;
    }
    #header-right {
        width: auto;
        background: #16213e;
        color: #666666;
        padding: 0 1;
    }
    #messages {
        height: 1fr;
        background: #1a1a2e;
        scrollbar-size: 1 1;
    }
    MessageDisplay {
        height: auto;
        padding: 0 1;
        background: #1a1a2e;
    }
    #input-bar {
        dock: bottom;
        height: 3;
        background: #16213e;
        padding: 0 1;
    }
    #message-input {
        background: #16213e;
        color: #e0e0e0;
        border: none;
    }
    #message-input:focus {
        border: none;
    }
    #empty-state {
        height: 1fr;
        content-align: center middle;
        color: #555555;
        background: #1a1a2e;
    }
    .date-separator {
        text-align: center;
        color: #555555;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.chat_id: str | None = None
        self.chat_name: str = ""
        self.chat_identifier: str = ""
        self.chat_service: str = "iMessage"
        self._messages: list[dict] = []

    def compose(self) -> ComposeResult:
        with Static(id="header-bar"):
            yield Static("JMessage", id="header-left")
            yield Static("Esc: conversations", id="header-right")
        yield Static("Press Esc to view conversations", id="empty-state")
        yield VerticalScroll(id="messages")
        yield Input(placeholder="Type a message...", id="message-input")

    def on_mount(self) -> None:
        self.query_one("#messages").display = False
        self.query_one("#message-input").display = False

    def load_chat(self, chat_id: str, display_name: str, service: str) -> None:
        """Set the active chat and request history."""
        self.chat_id = chat_id
        self.chat_name = display_name or chat_id
        self.chat_identifier = chat_id
        self.chat_service = service or "iMessage"
        self._messages.clear()

        # Update header
        service_label = "SMS" if "SMS" in self.chat_service else "iMessage"
        self.query_one("#header-left").update(
            f"[bold #4fc3f7]{self.chat_name}[/]  [#555555]{self.chat_identifier}[/]"
        )
        self.query_one("#header-right").update(
            f"{service_label} | Esc: conversations"
        )

        # Show message area and input, hide empty state
        self.query_one("#empty-state").display = False
        self.query_one("#messages").display = True
        self.query_one("#message-input").display = True

        # Clear old messages
        messages_container = self.query_one("#messages", VerticalScroll)
        messages_container.remove_children()

        # Request history from relay
        self.app.client.request_history(chat_id)

    def render_messages(self, messages: list[dict]) -> None:
        """Render a list of message dicts into the messages container."""
        self._messages = messages
        container = self.query_one("#messages", VerticalScroll)
        container.remove_children()

        last_date_str = ""
        for msg in messages:
            # Date separator
            date_str = self._format_date_header(msg.get("date"))
            if date_str and date_str != last_date_str:
                container.mount(
                    MessageDisplay(f"[#555555]── {date_str} ──[/]", classes="date-separator")
                )
                last_date_str = date_str

            # Sender + timestamp line
            is_mine = msg.get("is_from_me", False)
            sender = "You" if is_mine else (msg.get("sender") or self.chat_name)
            timestamp = self._format_time(msg.get("date"))
            sender_color = "#4fc3f7" if is_mine else "#888888"

            container.mount(
                MessageDisplay(f"[{sender_color}]{sender}[/]  [#555555]{timestamp}[/]")
            )

            # Message text
            text = msg.get("text") or ""
            text_color = "#4fc3f7" if is_mine else "#e0e0e0"
            if msg.get("has_attachments") and not text:
                text = "[attachment]"
            container.mount(MessageDisplay(f"[{text_color}]{self._escape(text)}[/]"))

        # Delivery status for last outgoing message
        if messages and messages[-1].get("is_from_me"):
            last = messages[-1]
            if last.get("date_read"):
                status = f"Read {self._format_time(last['date_read'])}"
            else:
                status = "Delivered"
            container.mount(MessageDisplay(f"[#555555]{status}[/]"))

        # Scroll to bottom
        container.scroll_end(animate=False)

    def append_message(self, msg: dict) -> None:
        """Append a single new message and scroll to bottom."""
        self._messages.append(msg)
        container = self.query_one("#messages", VerticalScroll)

        is_mine = msg.get("is_from_me", False)
        sender = "You" if is_mine else (msg.get("sender") or self.chat_name)
        timestamp = self._format_time(msg.get("date"))
        sender_color = "#4fc3f7" if is_mine else "#888888"
        text = msg.get("text") or ""
        text_color = "#4fc3f7" if is_mine else "#e0e0e0"
        if msg.get("has_attachments") and not text:
            text = "[attachment]"

        container.mount(
            MessageDisplay(f"[{sender_color}]{sender}[/]  [#555555]{timestamp}[/]")
        )
        container.mount(MessageDisplay(f"[{text_color}]{self._escape(text)}[/]"))
        container.scroll_end(animate=False)

        # Terminal bell for incoming messages
        if not is_mine:
            self.app.bell()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send message on Enter."""
        text = event.value.strip()
        if not text or not self.chat_id:
            return
        event.input.value = ""

        # Optimistic display
        self.append_message({
            "text": text,
            "is_from_me": True,
            "sender": "me",
            "date": datetime.now().isoformat(),
            "has_attachments": False,
        })

        # Send to relay
        self.app.client.send_message(self.chat_id, text)

    def action_show_conversations(self) -> None:
        """Push the conversation list screen."""
        from screens.conversation_list import ConversationListScreen
        self.app.push_screen(ConversationListScreen())

    def _format_date_header(self, iso_date: str | None) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            today = datetime.now(dt.tzinfo).date() if dt.tzinfo else datetime.now().date()
            delta = (today - dt.date()).days
            if delta == 0:
                return "Today"
            elif delta == 1:
                return "Yesterday"
            elif delta < 7:
                return dt.strftime("%A")
            else:
                return dt.strftime("%b %d")
        except (ValueError, TypeError):
            return ""

    def _format_time(self, iso_date: str | None) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            return dt.strftime("%-I:%M %p").lstrip("0") if hasattr(dt, "strftime") else ""
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def _escape(text: str) -> str:
        """Escape Rich markup characters in user text."""
        return text.replace("[", "\\[")
```

- [ ] **Step 3: Verify it imports cleanly**

```bash
cd c:/ai/jmessage/tui
python -c "from screens.conversation import ConversationScreen; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tui/screens/__init__.py tui/screens/conversation.py
git commit -m "feat(tui): conversation screen with message rendering, input, and optimistic send"
```

---

### Task 4: Conversation List Screen

**Files:**
- Create: `tui/screens/conversation_list.py`

The overlay screen summoned by Esc. Shows conversations sorted newest-first with selection, unread badges, and search filtering.

- [ ] **Step 1: Create conversation_list.py**

Create `tui/screens/conversation_list.py`:
```python
"""Conversation list screen — overlay for picking a chat."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static


class ConversationSelected(Message):
    """Fired when user picks a conversation."""

    def __init__(self, chat_id: str, display_name: str, service: str) -> None:
        self.chat_id = chat_id
        self.display_name = display_name
        self.service = service
        super().__init__()


class ConversationListScreen(Screen):
    """Overlay screen showing all conversations, newest first."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("slash", "focus_search", "Search", show=True),
    ]

    CSS = """
    ConversationListScreen {
        layout: vertical;
        background: #1a1a2e;
    }
    #list-header {
        dock: top;
        height: 1;
        layout: horizontal;
        background: #16213e;
    }
    #list-title {
        width: 1fr;
        background: #16213e;
        color: #4fc3f7;
        text-style: bold;
        padding: 0 1;
    }
    #list-hints {
        width: auto;
        background: #16213e;
        color: #666666;
        padding: 0 1;
    }
    #convo-list {
        height: 1fr;
        background: #1a1a2e;
    }
    #convo-list > ListItem {
        height: 1;
        background: #1a1a2e;
        padding: 0 1;
    }
    #convo-list > ListItem.--highlight {
        background: #1e3a5f;
    }
    .convo-row {
        height: 1;
        color: #e0e0e0;
    }
    #search-input {
        dock: bottom;
        display: none;
        background: #16213e;
        color: #e0e0e0;
        border: none;
    }
    #list-footer {
        dock: bottom;
        height: 1;
        background: #1a1a2e;
        color: #555555;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._conversations: list[dict] = []
        self._filtered: list[dict] = []
        self._search_active = False

    def compose(self) -> ComposeResult:
        with Static(id="list-header"):
            yield Static("Conversations", id="list-title")
            yield Static("/: search | Enter: open | Esc: back", id="list-hints")
        yield ListView(id="convo-list")
        yield Static("", id="list-footer")
        yield Input(placeholder="Filter by name...", id="search-input")

    def on_mount(self) -> None:
        self._conversations = list(self.app.conversations)
        self._filtered = list(self._conversations)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Rebuild the ListView from filtered conversations."""
        list_view = self.query_one("#convo-list", ListView)
        list_view.clear()
        unread_total = 0
        for convo in self._filtered:
            chat_id = convo.get("chat_id", "")
            name = convo.get("display_name") or chat_id
            preview = convo.get("last_message") or ""
            service = convo.get("service") or "iMessage"
            timestamp = self._format_relative_time(convo.get("last_date"))
            unread = self.app.unread_counts.get(chat_id, 0)
            unread_total += unread

            # Build the row markup
            sms_tag = " [italic #666666]SMS[/]" if "SMS" in service else ""
            badge = f" [on #4fc3f7][#000000] {unread} [/][/]" if unread else ""
            # Truncate preview to keep it on one line
            max_preview = 40
            if len(preview) > max_preview:
                preview = preview[:max_preview] + "..."

            row_text = (
                f"[#e0e0e0]{name}[/]{sms_tag}  "
                f"[#888888]{self._escape(preview)}[/]{badge}"
                f"  [#555555]{timestamp}[/]"
            )
            item = ListItem(Label(row_text), id=f"convo-{chat_id}")
            item.data = convo  # stash for selection handler
            list_view.append(item)

        count = len(self._filtered)
        self.query_one("#list-footer", Static).update(
            f"{count} conversation{'s' if count != 1 else ''} | {unread_total} unread"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Open the selected conversation."""
        convo = getattr(event.item, "data", None)
        if not convo:
            return
        chat_id = convo.get("chat_id", "")
        display_name = convo.get("display_name") or chat_id
        service = convo.get("service") or "iMessage"

        # Clear unread count
        self.app.unread_counts.pop(chat_id, None)

        # Dismiss this screen and tell the app which chat to open
        self.dismiss(convo)

    def action_go_back(self) -> None:
        if self._search_active:
            self._search_active = False
            search = self.query_one("#search-input", Input)
            search.display = False
            search.value = ""
            self._filtered = list(self._conversations)
            self._rebuild_list()
            self.query_one("#convo-list", ListView).focus()
        else:
            self.dismiss(None)

    def action_focus_search(self) -> None:
        self._search_active = True
        search = self.query_one("#search-input", Input)
        search.display = True
        search.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter conversations as user types."""
        query = event.value.strip().lower()
        if not query:
            self._filtered = list(self._conversations)
        else:
            self._filtered = [
                c for c in self._conversations
                if query in (c.get("display_name") or c.get("chat_id", "")).lower()
            ]
        self._rebuild_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """On Enter in search, focus the list so user can pick."""
        self.query_one("#convo-list", ListView).focus()

    def _format_relative_time(self, iso_date: str | None) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            delta = (now.date() - dt.date()).days
            if delta == 0:
                return dt.strftime("%-I:%M %p").lstrip("0")
            elif delta == 1:
                return "Yesterday"
            elif delta < 7:
                return dt.strftime("%A")
            else:
                return dt.strftime("%b %d")
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("[", "\\[")
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd c:/ai/jmessage/tui
python -c "from screens.conversation_list import ConversationListScreen; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add tui/screens/conversation_list.py
git commit -m "feat(tui): conversation list screen with search, selection, and unread badges"
```

---

### Task 5: Main App (jmessage.py)

**Files:**
- Create: `tui/jmessage.py`

The Textual App subclass that wires everything together — loads config, starts the WebSocket client, handles server messages, and manages screen transitions.

- [ ] **Step 1: Create jmessage.py**

Create `tui/jmessage.py`:
```python
"""JMessage TUI — terminal-native iMessage client."""

import json
import logging
import sys
from pathlib import Path

from textual.app import App, ComposeResult

from client import ConnectionStatus, RelayClient, ServerMessage
from screens.conversation import ConversationScreen
from screens.conversation_list import ConversationListScreen

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class JMessageApp(App):
    """Terminal iMessage client."""

    TITLE = "JMessage"
    CSS = """
    Screen {
        background: #1a1a2e;
    }
    """

    def __init__(self, config_path: str = "config.json") -> None:
        super().__init__()
        self.config = self._load_config(config_path)
        self.client: RelayClient | None = None
        self.conversations: list[dict] = []
        self.unread_counts: dict[str, int] = {}
        self._connected = False

    def _load_config(self, path: str) -> dict:
        config_file = Path(path)
        if not config_file.exists():
            print(f"Error: {path} not found. Copy config.example.json to config.json and configure it.")
            sys.exit(1)
        return json.loads(config_file.read_text())

    def compose(self) -> ComposeResult:
        yield from []  # Screens handle all composition

    def on_mount(self) -> None:
        # Install the conversation screen as default
        self.push_screen(ConversationScreen())

        # Start WebSocket client
        certs = self.config.get("certs")
        self.client = RelayClient(
            app=self,
            relay_url=self.config["relay_url"],
            auth_token=self.config["auth_token"],
            certs=certs,
        )
        self.client.start()

    def on_connection_status(self, message: ConnectionStatus) -> None:
        """Handle connection state changes from the WebSocket client."""
        self._connected = message.connected
        screen = self.screen
        if isinstance(screen, ConversationScreen):
            if message.connected:
                # Connection established — header will be updated when chat loads
                pass
            else:
                screen.query_one("#header-right").update(
                    f"[#f85149]disconnected — retrying...[/]"
                )

    def on_server_message(self, message: ServerMessage) -> None:
        """Handle all messages from the relay server."""
        if message.msg_type == "conversations":
            self.conversations = message.data
            # If conversation list is showing, refresh it
            if isinstance(self.screen, ConversationListScreen):
                self.screen._conversations = list(self.conversations)
                self.screen._filtered = list(self.conversations)
                self.screen._rebuild_list()

        elif message.msg_type == "history":
            chat_id = message.data.get("chat_id", "")
            messages = message.data.get("messages", [])
            screen = self.screen
            if isinstance(screen, ConversationScreen) and screen.chat_id == chat_id:
                screen.render_messages(messages)

        elif message.msg_type == "message":
            msg_data = message.data
            chat_id = msg_data.get("chat_id", "")
            is_from_me = msg_data.get("is_from_me", False)

            # Update conversation list data
            self._update_conversation_preview(chat_id, msg_data)

            # If this chat is currently open, append the message
            screen = self.screen
            if isinstance(screen, ConversationScreen) and screen.chat_id == chat_id:
                if not is_from_me:
                    screen.append_message(msg_data)
                # If it's from me, it was already shown optimistically
            else:
                # Increment unread count
                if not is_from_me:
                    self.unread_counts[chat_id] = self.unread_counts.get(chat_id, 0) + 1

        elif message.msg_type == "send_result":
            if not message.data.get("success"):
                self.notify(
                    f"Send failed: {message.data.get('error', 'unknown')}",
                    severity="error",
                    timeout=5,
                )

        elif message.msg_type == "error":
            error_msg = message.data.get("message", "Unknown error") if isinstance(message.data, dict) else str(message.data)
            self.notify(f"Relay error: {error_msg}", severity="error", timeout=5)

    def _update_conversation_preview(self, chat_id: str, msg_data: dict) -> None:
        """Update the conversations list with the latest message preview."""
        for convo in self.conversations:
            if convo.get("chat_id") == chat_id:
                convo["last_message"] = msg_data.get("text") or ""
                convo["last_date"] = msg_data.get("date")
                break
        else:
            # New conversation we haven't seen before
            self.conversations.insert(0, {
                "chat_id": chat_id,
                "display_name": msg_data.get("chat_name") or chat_id,
                "service": msg_data.get("service") or "iMessage",
                "last_message": msg_data.get("text") or "",
                "last_date": msg_data.get("date"),
            })

        # Re-sort newest first
        self.conversations.sort(
            key=lambda c: c.get("last_date") or "", reverse=True
        )

    def _on_screen_resume(self) -> None:
        """Called when a screen is popped and we return to the previous screen."""
        super()._on_screen_resume()
        screen = self.screen
        if isinstance(screen, ConversationScreen) and self._connected:
            service_label = "SMS" if "SMS" in screen.chat_service else "iMessage"
            screen.query_one("#header-right").update(
                f"{service_label} | Esc: conversations"
            )


def _open_conversation_callback(app: JMessageApp, convo: dict | None) -> None:
    """Callback when conversation list screen is dismissed."""
    if convo is None:
        return
    screen = app.screen
    if isinstance(screen, ConversationScreen):
        screen.load_chat(
            chat_id=convo["chat_id"],
            display_name=convo.get("display_name") or convo["chat_id"],
            service=convo.get("service") or "iMessage",
        )


# Monkey-patch the push_screen in ConversationScreen to use callback
_original_show_conversations = ConversationScreen.action_show_conversations


def _patched_show_conversations(self):
    self.app.push_screen(
        ConversationListScreen(),
        callback=lambda convo: _open_conversation_callback(self.app, convo),
    )


ConversationScreen.action_show_conversations = _patched_show_conversations


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    app = JMessageApp(config_path)
    app.run()
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd c:/ai/jmessage/tui
python -c "from jmessage import JMessageApp; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add tui/jmessage.py
git commit -m "feat(tui): main app wiring config, websocket client, screen transitions, and message routing"
```

---

### Task 6: Windows Time Format Fix and Polish

**Files:**
- Modify: `tui/screens/conversation.py`
- Modify: `tui/screens/conversation_list.py`

The `%-I` strftime format doesn't work on Windows (it uses `%#I` instead). Fix both screens to handle this cross-platform.

- [ ] **Step 1: Fix time formatting in conversation.py**

In `tui/screens/conversation.py`, replace the `_format_time` method:

```python
    def _format_time(self, iso_date: str | None) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            hour = dt.hour % 12 or 12
            minute = dt.strftime("%M")
            ampm = "AM" if dt.hour < 12 else "PM"
            return f"{hour}:{minute} {ampm}"
        except (ValueError, TypeError):
            return ""
```

- [ ] **Step 2: Fix time formatting in conversation_list.py**

In `tui/screens/conversation_list.py`, replace the `_format_relative_time` method:

```python
    def _format_relative_time(self, iso_date: str | None) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            delta = (now.date() - dt.date()).days
            if delta == 0:
                hour = dt.hour % 12 or 12
                minute = dt.strftime("%M")
                ampm = "AM" if dt.hour < 12 else "PM"
                return f"{hour}:{minute} {ampm}"
            elif delta == 1:
                return "Yesterday"
            elif delta < 7:
                return dt.strftime("%A")
            else:
                return dt.strftime("%b %d")
        except (ValueError, TypeError):
            return ""
```

- [ ] **Step 3: Also fix _format_date_header in conversation.py**

In `tui/screens/conversation.py`, the `_format_date_header` uses `%b %d` which works fine on Windows. No change needed — verify by inspection.

- [ ] **Step 4: Commit**

```bash
git add tui/screens/conversation.py tui/screens/conversation_list.py
git commit -m "fix(tui): cross-platform time formatting for Windows compatibility"
```

---

### Task 7: Manual Testing and Config Setup

**Files:**
- Modify: `tui/config.json` (user creates from example)

- [ ] **Step 1: Copy config and certs**

```bash
cd c:/ai/jmessage/tui
cp config.example.json config.json
# Edit config.json with actual relay URL and token
# Copy certs from existing client:
cp -r ../client/certs ./certs/
```

Edit `config.json` to match the existing Electron client's settings (same relay URL, token, and cert paths).

- [ ] **Step 2: Launch the TUI**

```bash
cd c:/ai/jmessage/tui
python jmessage.py
```

Verify:
- App launches instantly
- Header shows "JMessage" and "Esc: conversations"
- Empty state shows "Press Esc to view conversations"
- No crash, no error output

- [ ] **Step 3: Test conversation list**

Press `Esc`. Verify:
- Conversation list appears with conversations from Mac relay
- Newest conversations are at the top
- Each row shows name, preview, timestamp
- SMS conversations show "SMS" tag
- Up/Down arrows move the highlight
- Footer shows conversation count

- [ ] **Step 4: Test opening a conversation**

Press `Enter` on a conversation. Verify:
- Header updates with contact name + phone/email + service type
- Message history loads and displays
- Your messages are in cyan, theirs in default color
- Date separators appear between different days
- Delivery status shows below your last message
- Messages are scrollable with Up/Down

- [ ] **Step 5: Test sending a message**

Type a message and press `Enter`. Verify:
- Message appears immediately (optimistic display) in cyan
- Input clears
- No error notification appears

- [ ] **Step 6: Test search**

Press `Esc` to open conversation list, then `/`. Verify:
- Search input appears at the bottom
- Typing filters the list by contact name
- `Esc` clears search and returns to full list
- `Enter` in search focuses the list for selection

- [ ] **Step 7: Test terminal bell**

Have someone send you a message (or send from another device). Verify:
- New message appears in the conversation if it's open
- Terminal bell rings (audible beep or visual flash depending on terminal)
- If conversation list is open, the preview updates

- [ ] **Step 8: Test in different terminals**

Run the TUI in:
- cmd (Windows Command Prompt)
- WezTerm
- SSH session (if available)

Verify it renders correctly in all three.

- [ ] **Step 9: Final commit**

```bash
git add -A
git commit -m "feat(tui): JMessage TUI — terminal-native iMessage client

Complete Python TUI replacement for the Electron client.
Uses Textual + websockets, connects to existing Mac relay.
Keyboard-driven: Esc for conversations, arrows to navigate,
Enter to send, / to search."
```
