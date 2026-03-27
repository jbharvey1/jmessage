"""JMessage TUI — terminal-native iMessage client."""

import json
import logging
import sys
from pathlib import Path

from textual.app import App, ComposeResult

from textual.binding import Binding

from client import ConnectionStatus, RelayClient, SendFailed, ServerMessage
from screens.attachments import AttachmentsScreen
from screens.conversation import ConversationScreen
from screens.conversation_list import ConversationListScreen
from screens.options import OptionsScreen
from screens.search import SearchScreen
from themes import get_theme, THEME_ORDER, THEMES

PREFS_FILE = Path(__file__).parent / "preferences.json"

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class JMessageApp(App):
    """Terminal iMessage client."""

    TITLE = "JMessage"
    BINDINGS = [
        Binding("ctrl+t", "cycle_theme", "Theme", show=False, priority=True),
        Binding("ctrl+h", "show_help", "Help", show=False, priority=True),
        Binding("ctrl+o", "show_options", "Options", show=False, priority=True),
    ]

    def __init__(self, config_path: str = "config.json") -> None:
        super().__init__()
        self.config = self._load_config(config_path)
        self.client: RelayClient | None = None
        self.conversations: list[dict] = []
        self.unread_counts: dict[str, int] = {}
        self._connected = False
        self._prefs = self._load_prefs()
        self.known_only = self._prefs.get("known_only", False)
        self.theme_colors = get_theme(self._prefs.get("theme", "midnight"))

    def _load_config(self, path: str) -> dict:
        config_file = Path(path)
        if not config_file.exists():
            print(f"Error: {path} not found. Copy config.example.json to config.json and configure it.")
            sys.exit(1)
        try:
            config = json.loads(config_file.read_text())
        except json.JSONDecodeError as e:
            print(f"Error: {path} contains invalid JSON: {e}")
            sys.exit(1)
        for key in ("relay_url", "auth_token"):
            if key not in config:
                print(f"Error: {path} missing required field '{key}'")
                sys.exit(1)
        return config

    def _load_prefs(self) -> dict:
        if PREFS_FILE.exists():
            try:
                return json.loads(PREFS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_prefs(self) -> None:
        try:
            PREFS_FILE.write_text(json.dumps(self._prefs, indent=2))
        except OSError:
            pass

    def set_theme(self, name: str) -> None:
        self.theme_colors = get_theme(name)
        self._prefs["theme"] = name
        self._save_prefs()

    def compose(self) -> ComposeResult:
        yield from []

    def on_mount(self) -> None:
        self.push_screen(ConversationScreen())

        if "theme" not in self._prefs:
            # First run — show theme picker
            from screens.theme_picker import ThemePickerScreen
            self.push_screen(ThemePickerScreen(), callback=self._on_theme_picked)
        else:
            self._start_client()

    def _on_theme_picked(self, theme_name: str | None) -> None:
        self.set_theme(theme_name or "midnight")
        # Re-apply theme to the conversation screen underneath
        screen = self.screen
        if isinstance(screen, ConversationScreen):
            screen._apply_theme()
        self._start_client()

    def _start_client(self) -> None:
        if self.client:
            return
        certs = self.config.get("certs")
        self.client = RelayClient(
            app=self,
            relay_url=self.config["relay_url"],
            auth_token=self.config["auth_token"],
            certs=certs,
        )
        self.client.start()

    def action_cycle_theme(self) -> None:
        current = self._prefs.get("theme", "midnight")
        try:
            idx = THEME_ORDER.index(current)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(THEME_ORDER)
        name = THEME_ORDER[next_idx]
        self.set_theme(name)
        # Re-apply to current screen
        screen = self.screen
        if hasattr(screen, "_apply_theme"):
            screen._apply_theme()
        self.notify(f"Theme: {THEMES[name]['label']}", timeout=2)

    def action_show_help(self) -> None:
        t = self.theme_colors
        help_text = (
            f"[bold {t['accent']}]JMessage Hotkeys[/]\n\n"
            f"[{t['name_color']}]Esc[/]         [{t['text_color']}]Open conversation list[/]\n"
            f"[{t['name_color']}]Tab[/]         [{t['text_color']}]Next conversation[/]\n"
            f"[{t['name_color']}]Shift+Tab[/]   [{t['text_color']}]Previous conversation[/]\n"
            f"[{t['name_color']}]Up/Down[/]     [{t['text_color']}]Scroll messages[/]\n"
            f"[{t['name_color']}]Enter[/]       [{t['text_color']}]Send message[/]\n"
            f"[{t['name_color']}]Ctrl+Enter[/]  [{t['text_color']}]New line[/]\n"
            f"[{t['name_color']}]Ctrl+A[/]      [{t['text_color']}]Attachments list[/]\n"
            f"[{t['name_color']}]Ctrl+N[/]      [{t['text_color']}]New conversation[/]\n"
            f"[{t['name_color']}]Ctrl+F[/]      [{t['text_color']}]Search messages[/]\n\n"
            f"[bold {t['accent']}]Conversation List[/]\n\n"
            f"[{t['name_color']}]Tab[/]         [{t['text_color']}]Toggle known-only filter[/]\n"
            f"[{t['name_color']}]/[/]           [{t['text_color']}]Search by name[/]\n"
            f"[{t['name_color']}]Left/Right[/]  [{t['text_color']}]Jump to top/bottom[/]\n\n"
            f"[bold {t['accent']}]Global[/]\n\n"
            f"[{t['name_color']}]Ctrl+T[/]      [{t['text_color']}]Cycle theme[/]\n"
            f"[{t['name_color']}]Ctrl+O[/]      [{t['text_color']}]Options[/]\n"
            f"[{t['name_color']}]Ctrl+H[/]      [{t['text_color']}]This help[/]\n"
            f"[{t['name_color']}]Ctrl+C[/]      [{t['text_color']}]Quit[/]"
        )
        self.notify(help_text, timeout=10)

    def show_search(self) -> None:
        self.push_screen(SearchScreen(), callback=self._on_search_result)

    def _on_search_result(self, result) -> None:
        if result and isinstance(result, dict):
            screen = self.screen
            if isinstance(screen, ConversationScreen):
                chat_id = result.get("chat_id")
                chat_name = result.get("chat_name") or chat_id
                service = result.get("service") or "iMessage"
                screen.load_chat(chat_id, chat_name, service)

    def action_show_options(self) -> None:
        self.push_screen(OptionsScreen(), callback=self._on_options_closed)

    def _on_options_closed(self, changed) -> None:
        screen = self.screen
        if isinstance(screen, ConversationScreen):
            screen._apply_theme()
            screen.update_status_bar()

    def on_connection_status(self, message: ConnectionStatus) -> None:
        self._connected = message.connected
        screen = self.screen
        if isinstance(screen, ConversationScreen):
            if message.connected:
                self.client.request_conversations()
            screen.update_status_bar()

    def on_send_failed(self, message: SendFailed) -> None:
        self.notify(f"Send failed: {message.reason}", severity="error", timeout=5)
        screen = self.screen
        if isinstance(screen, ConversationScreen) and screen.chat_id == message.chat_id:
            screen.mark_last_send_failed()

    def on_server_message(self, message: ServerMessage) -> None:
        if message.msg_type == "conversations":
            self.conversations = message.data
            if isinstance(self.screen, ConversationListScreen):
                self.screen._conversations = list(self.conversations)
                self.screen._filtered = list(self.conversations)
                self.screen._rebuild_list()
            # Restore last open chat on first connect
            elif isinstance(self.screen, ConversationScreen) and not self.screen.chat_id:
                last = self._prefs.get("last_chat")
                if last:
                    convo = next((c for c in self.conversations if c.get("chat_id") == last.get("chat_id")), None)
                    if convo:
                        self.screen.load_chat(
                            convo["chat_id"],
                            convo.get("display_name") or convo["chat_id"],
                            convo.get("service") or "iMessage",
                        )

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

            self._update_conversation_preview(chat_id, msg_data)

            screen = self.screen
            if isinstance(screen, ConversationScreen) and screen.chat_id == chat_id:
                if not is_from_me:
                    screen.append_message(msg_data)
            else:
                if not is_from_me:
                    self.unread_counts[chat_id] = self.unread_counts.get(chat_id, 0) + 1

        elif message.msg_type == "send_result":
            if not message.data.get("success"):
                self.notify(
                    f"Send failed: {message.data.get('error', 'unknown')}",
                    severity="error",
                    timeout=5,
                )
                screen = self.screen
                if isinstance(screen, ConversationScreen):
                    screen.mark_last_send_failed()

        elif message.msg_type == "chat_attachments":
            screen = self.screen
            if isinstance(screen, AttachmentsScreen):
                screen.load_data(
                    message.data.get("attachments", []),
                    message.data.get("urls", []),
                )

        elif message.msg_type == "attachment_data":
            screen = self.screen
            if isinstance(screen, AttachmentsScreen):
                screen.handle_attachment_data(
                    message.data.get("id"),
                    message.data.get("path", ""),
                    message.data.get("content"),
                )

        elif message.msg_type == "tapbacks":
            chat_id = message.data.get("chat_id", "")
            screen = self.screen
            if isinstance(screen, ConversationScreen) and screen.chat_id == chat_id:
                screen.set_tapbacks(message.data.get("tapbacks", {}))

        elif message.msg_type == "tapback":
            # Real-time tapback from poll
            msg_data = message.data
            chat_id = msg_data.get("chat_id", "")
            screen = self.screen
            if isinstance(screen, ConversationScreen) and screen.chat_id == chat_id:
                guid = msg_data.get("tapback_target", "")
                emoji = msg_data.get("emoji", "")
                sender = msg_data.get("sender_name") or msg_data.get("sender") or ""
                if guid and emoji:
                    if guid not in screen._tapbacks:
                        screen._tapbacks[guid] = []
                    screen._tapbacks[guid].append({"emoji": emoji, "sender": sender})
                    screen.render_messages(screen._messages)

        elif message.msg_type == "chat_members":
            chat_id = message.data.get("chat_id", "")
            screen = self.screen
            if isinstance(screen, ConversationScreen) and screen.chat_id == chat_id:
                screen.set_members(message.data.get("members", []))

        elif message.msg_type == "search_results":
            screen = self.screen
            if isinstance(screen, SearchScreen):
                screen.load_results(message.data.get("results", []))

        elif message.msg_type == "error":
            error_msg = message.data.get("message", "Unknown error") if isinstance(message.data, dict) else str(message.data)
            self.notify(f"Relay error: {error_msg}", severity="error", timeout=5)

    def _update_conversation_preview(self, chat_id: str, msg_data: dict) -> None:
        for convo in self.conversations:
            if convo.get("chat_id") == chat_id:
                convo["last_message"] = msg_data.get("text") or ""
                convo["last_date"] = msg_data.get("date")
                break
        else:
            self.conversations.insert(0, {
                "chat_id": chat_id,
                "display_name": msg_data.get("chat_name") or chat_id,
                "service": msg_data.get("service") or "iMessage",
                "last_message": msg_data.get("text") or "",
                "last_date": msg_data.get("date"),
            })

        self.conversations.sort(
            key=lambda c: c.get("last_date") or "", reverse=True
        )

    def show_conversation_list(self) -> None:
        self.push_screen(
            ConversationListScreen(),
            callback=self._on_conversation_selected,
        )

    def _on_conversation_selected(self, convo: dict | None) -> None:
        if convo is None:
            return
        self._save_last_chat(convo)
        screen = self.screen
        if isinstance(screen, ConversationScreen):
            screen.load_chat(
                chat_id=convo["chat_id"],
                display_name=convo.get("display_name") or convo["chat_id"],
                service=convo.get("service") or "iMessage",
            )

    def _save_last_chat(self, convo: dict) -> None:
        self._prefs["last_chat"] = {
            "chat_id": convo.get("chat_id"),
            "display_name": convo.get("display_name"),
            "service": convo.get("service"),
        }
        self._save_prefs()

    def _on_screen_resume(self) -> None:
        super()._on_screen_resume()
        screen = self.screen
        if isinstance(screen, ConversationScreen) and self._connected:
            service_label = "SMS" if "SMS" in screen.chat_service else "iMessage"
            screen.query_one("#header-right").update(
                f"{service_label} | Esc: conversations"
            )


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    app = JMessageApp(config_path)
    app.run()
