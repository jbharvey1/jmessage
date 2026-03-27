"""Conversation screen — displays messages and input bar for a single chat."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static


class MessageDisplay(Static):
    """A single message line with Rich markup."""
    pass


class ConversationScreen(Screen):
    """Main screen showing chat messages and input."""

    BINDINGS = [
        Binding("escape", "show_conversations", "Conversations", show=True),
        Binding("tab", "next_conversation", "Next", show=False, priority=True),
        Binding("shift+tab", "prev_conversation", "Prev", show=False, priority=True),
        Binding("ctrl+a", "show_attachments", "Attachments", show=False, priority=True),
        Binding("ctrl+n", "new_conversation", "New", show=False, priority=True),
        Binding("ctrl+f", "search_messages", "Search", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    ConversationScreen {
        layout: vertical;
    }
    #header-bar {
        dock: top;
        height: 1;
        layout: horizontal;
    }
    #header-left {
        width: 1fr;
        padding: 0 1;
    }
    #header-right {
        width: auto;
        padding: 0 1;
    }
    #messages {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    MessageDisplay {
        height: auto;
        padding: 0 1;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        layout: horizontal;
    }
    #status-connection {
        width: auto;
        padding: 0 1;
    }
    #status-info {
        width: 1fr;
        padding: 0 1;
    }
    #status-keys {
        width: auto;
        padding: 0 1;
    }
    #message-input {
        dock: bottom;
        border: none;
    }
    #message-input:focus {
        border: none;
    }
    #empty-state {
        height: 1fr;
        content-align: center middle;
    }
    .date-separator {
        text-align: center;
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
        self._tapbacks: dict = {}  # guid -> [{"emoji": "👍", "sender": "Mom"}]
        self._members: list[dict] = []

    @property
    def t(self) -> dict:
        return self.app.theme_colors

    def compose(self) -> ComposeResult:
        with Static(id="header-bar"):
            yield Static("JMessage", id="header-left")
            yield Static("Esc: conversations", id="header-right")
        yield Static("Press Esc to view conversations", id="empty-state")
        yield VerticalScroll(id="messages")
        with Horizontal(id="status-bar"):
            yield Static("", id="status-connection")
            yield Static("", id="status-info")
            yield Static("Ctrl+H: help", id="status-keys")
        yield Input(placeholder="Type a message...", id="message-input")

    def on_mount(self) -> None:
        self.query_one("#messages").display = False
        self.query_one("#message-input").display = False
        self._apply_theme()

    def update_status_bar(self) -> None:
        """Update the status bar with connection state and metrics."""
        t = self.t
        connected = getattr(self.app, "_connected", False)
        if connected:
            conn_text = "[#000000 on #4caf50] CONNECTED [/]"
        else:
            error = ""
            conn_text = "[#ffffff on #f44336] DISCONNECTED [/]"

        self.query_one("#status-connection").update(conn_text)

        # Info section: message count, conversation count
        parts = []
        num_convos = len(getattr(self.app, "conversations", []))
        if num_convos:
            parts.append(f"{num_convos} convos")
        num_unread = sum(getattr(self.app, "unread_counts", {}).values())
        if num_unread:
            parts.append(f"[{t['badge_color']}]{num_unread} unread[/]")
        if self._messages:
            parts.append(f"{len(self._messages)} msgs")
        filter_on = getattr(self.app, "known_only", False)
        if filter_on:
            parts.append(f"[{t['accent']}]known-only[/]")
        info = f"[{t['dim_color']}]{' | '.join(parts)}[/]" if parts else ""
        self.query_one("#status-info").update(info)

    def _apply_theme(self) -> None:
        t = self.t
        self.styles.background = t["bg"]
        for sel in ("#header-bar", "#header-left", "#header-right"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#header-left").styles.color = t["accent"]
        self.query_one("#header-right").styles.color = t["hint_color"]
        self.query_one("#messages").styles.background = t["bg"]
        self.query_one("#message-input").styles.background = t["header_bg"]
        self.query_one("#message-input").styles.color = t["text_color"]
        self.query_one("#empty-state").styles.color = t["dim_color"]
        self.query_one("#empty-state").styles.background = t["bg"]
        for sel in ("#status-bar", "#status-connection", "#status-info", "#status-keys"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#status-keys").styles.color = t["hint_color"]
        self.update_status_bar()

        # Re-render messages with new theme colors
        if self._messages:
            self.render_messages(self._messages)
        # Re-apply header text if chat is loaded
        if self.chat_id:
            service_label = "SMS" if "SMS" in self.chat_service else "iMessage"
            self.query_one("#header-left").update(
                f"[bold {t['accent']}]{self.chat_name}[/]  [{t['hint_color']}]{self.chat_identifier}[/]"
            )
            self.query_one("#header-right").update(
                f"{service_label} | Esc: conversations"
            )

    def load_chat(self, chat_id: str, display_name: str, service: str) -> None:
        """Set the active chat and request history."""
        self.chat_id = chat_id
        self.chat_name = display_name or chat_id
        self.chat_identifier = chat_id
        self.chat_service = service or "iMessage"
        self._messages.clear()
        t = self.t

        # Save as last open chat
        self.app._save_last_chat({"chat_id": chat_id, "display_name": display_name, "service": service})

        service_label = "SMS" if "SMS" in self.chat_service else "iMessage"
        self.query_one("#header-left").update(
            f"[bold {t['accent']}]{self.chat_name}[/]  [{t['hint_color']}]{self.chat_identifier}[/]"
        )
        self.query_one("#header-right").update(
            f"{service_label} | Esc: conversations"
        )

        self.query_one("#empty-state").display = False
        self.query_one("#messages").display = True
        self.query_one("#message-input").display = True

        messages_container = self.query_one("#messages", VerticalScroll)
        messages_container.remove_children()

        limit = self.app._prefs.get("history_limit", 50)
        self.app.client.request_history(chat_id, limit)
        self.app.client.request_tapbacks(chat_id)
        # Request members for group chats
        if chat_id.startswith("chat"):
            self.app.client.request_chat_members(chat_id)

        # Update terminal title
        self._update_terminal_title()

    def _render_msg_widgets(self, msg: dict, container) -> None:
        """Render a single message into the container."""
        t = self.t
        is_mine = msg.get("is_from_me", False)
        sender = "You" if is_mine else (msg.get("sender_name") or msg.get("sender") or self.chat_name)
        timestamp = self._format_time(msg.get("date"))
        is_sms = "SMS" in (msg.get("service") or self.chat_service)
        other_color = t["sms_color"] if is_sms else t["imessage_color"]
        sender_color = t["you_color"] if is_mine else other_color
        text_color = t["you_color"] if is_mine else t["text_color"]

        w = MessageDisplay(f"[{sender_color}]{sender}[/]  [{t['timestamp_color']}]{timestamp}[/]")
        w.styles.background = t["bg"]
        container.mount(w)

        text = msg.get("text") or ""
        att_label = ""
        if msg.get("has_attachments"):
            atts = msg.get("attachments", [])
            if atts:
                names = [a.get("filename") or a.get("mime_type", "file") for a in atts]
                att_label = " ".join(f"[{t['badge_color']}]\\[{n}][/]" for n in names)
            else:
                att_label = f"[{t['badge_color']}]\\[attachment][/]"

        if text and att_label:
            markup = f"[{text_color}]{self._escape(text)}[/] {att_label}"
        elif att_label:
            markup = att_label
        else:
            markup = f"[{text_color}]{self._escape(text)}[/]"

        w2 = MessageDisplay(markup)
        w2.styles.background = t["bg"]
        container.mount(w2)

        # Tapback reactions
        guid = msg.get("guid", "")
        reactions = self._tapbacks.get(guid, [])
        if reactions:
            emoji_str = " ".join(f"{r['emoji']}" for r in reactions)
            w3 = MessageDisplay(f"[{t['dim_color']}]  {emoji_str}[/]")
            w3.styles.background = t["bg"]
            container.mount(w3)

    def render_messages(self, messages: list[dict]) -> None:
        """Render a list of message dicts into the messages container."""
        self._messages = messages
        t = self.t
        container = self.query_one("#messages", VerticalScroll)
        container.remove_children()

        last_date_str = ""
        for msg in messages:
            date_str = self._format_date_header(msg.get("date"))
            if date_str and date_str != last_date_str:
                sep = MessageDisplay(f"[{t['separator_color']}]── {date_str} ──[/]", classes="date-separator")
                sep.styles.background = t["bg"]
                container.mount(sep)
                last_date_str = date_str

            self._render_msg_widgets(msg, container)

        if messages and messages[-1].get("is_from_me"):
            last = messages[-1]
            if last.get("date_read"):
                status = f"Read {self._format_time(last['date_read'])}"
            else:
                status = "Delivered"
            w = MessageDisplay(f"[{t['timestamp_color']}]{status}[/]")
            w.styles.background = t["bg"]
            container.mount(w)

        container.scroll_end(animate=False)

    def append_message(self, msg: dict) -> None:
        """Append a single new message and scroll to bottom."""
        self._messages.append(msg)
        container = self.query_one("#messages", VerticalScroll)
        self._render_msg_widgets(msg, container)
        container.scroll_end(animate=False)

        if not msg.get("is_from_me", False) and self.app._prefs.get("bell", True):
            self.app.bell()

    def mark_last_send_failed(self) -> None:
        """Mark the last outgoing message as failed to send."""
        t = self.t
        container = self.query_one("#messages", VerticalScroll)
        children = list(container.children)
        if children:
            failed = MessageDisplay(f"[#f85149]⚠ Failed to send[/]")
            failed.styles.background = t["bg"]
            container.mount(failed)
            container.scroll_end(animate=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send message on Enter."""
        text = event.value.strip()
        if not text or not self.chat_id:
            return
        event.input.value = ""

        self.append_message({
            "text": text,
            "is_from_me": True,
            "sender": "me",
            "date": datetime.now().isoformat(),
            "has_attachments": False,
        })

        self.app.client.send_message(self.chat_id, text)

    def on_key(self, event) -> None:
        """Auto-focus input when user starts typing."""
        input_widget = self.query_one("#message-input", Input)
        if (
            not input_widget.has_focus
            and self.chat_id
            and event.is_printable
            and input_widget.display
        ):
            input_widget.focus()

    def _get_filtered_conversations(self) -> list[dict]:
        convos = self.app.conversations
        if self.app.known_only:
            convos = [
                c for c in convos
                if c.get("display_name")
                or "@" in c.get("chat_id", "")
                or c.get("chat_id", "").startswith("chat")
            ]
        return convos

    def action_next_conversation(self) -> None:
        if not self.chat_id:
            return
        convos = self._get_filtered_conversations()
        for i, c in enumerate(convos):
            if c.get("chat_id") == self.chat_id:
                if i + 1 < len(convos):
                    nxt = convos[i + 1]
                    self.load_chat(nxt["chat_id"], nxt.get("display_name") or nxt["chat_id"], nxt.get("service") or "iMessage")
                return

    def action_prev_conversation(self) -> None:
        if not self.chat_id:
            return
        convos = self._get_filtered_conversations()
        for i, c in enumerate(convos):
            if c.get("chat_id") == self.chat_id:
                if i > 0:
                    prev = convos[i - 1]
                    self.load_chat(prev["chat_id"], prev.get("display_name") or prev["chat_id"], prev.get("service") or "iMessage")
                return

    def action_show_attachments(self) -> None:
        if not self.chat_id:
            return
        from screens.attachments import AttachmentsScreen
        self.app.push_screen(AttachmentsScreen(self.chat_id, self.chat_name))

    def action_new_conversation(self) -> None:
        from screens.new_conversation import NewConversationScreen
        self.app.push_screen(NewConversationScreen(), callback=self._on_new_convo)

    def _on_new_convo(self, result) -> None:
        if result:
            self.load_chat(result, result, "iMessage")

    def action_search_messages(self) -> None:
        self.app.show_search()

    def action_show_conversations(self) -> None:
        self.app.show_conversation_list()

    def set_tapbacks(self, tapbacks: dict) -> None:
        """Set tapback data and re-render if messages are loaded."""
        self._tapbacks = tapbacks
        if self._messages:
            self.render_messages(self._messages)

    def set_members(self, members: list) -> None:
        """Set group chat members and update header."""
        self._members = members
        if members:
            t = self.t
            names = [m.get("display_name") or m.get("identifier") for m in members[:5]]
            suffix = f" +{len(members) - 5}" if len(members) > 5 else ""
            member_str = ", ".join(names) + suffix
            self.query_one("#header-right").update(
                f"[{t['dim_color']}]{member_str}[/]"
            )

    def _update_terminal_title(self) -> None:
        """Update terminal window title with unread count."""
        unread = sum(getattr(self.app, "unread_counts", {}).values())
        if unread:
            title = f"JMessage ({unread} unread)"
        elif self.chat_name:
            title = f"JMessage — {self.chat_name}"
        else:
            title = "JMessage"
        # ANSI escape to set terminal title
        import sys
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()

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
            hour = dt.hour % 12 or 12
            minute = dt.strftime("%M")
            ampm = "AM" if dt.hour < 12 else "PM"
            return f"{hour}:{minute} {ampm}"
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("[", "\\[")
