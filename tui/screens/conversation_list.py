"""Conversation list screen — overlay for picking a chat."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static


class ConversationListScreen(Screen):
    """Overlay screen showing all conversations, newest first."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("left", "jump_top", "Top", show=False),
        Binding("right", "jump_bottom", "Bottom", show=False),
        Binding("tab", "toggle_known", "Known only", show=True),
    ]

    DEFAULT_CSS = """
    ConversationListScreen {
        layout: vertical;
    }
    #list-header {
        dock: top;
        height: 1;
        layout: horizontal;
    }
    #list-title {
        width: 1fr;
        text-style: bold;
        padding: 0 1;
    }
    #list-hints {
        width: auto;
        padding: 0 1;
    }
    #convo-list {
        height: 1fr;
    }
    #convo-list > ListItem {
        height: 1;
        padding: 0 1;
    }
    .convo-row {
        height: 1;
    }
    #search-input {
        dock: bottom;
        display: none;
        border: none;
    }
    #list-footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._conversations: list[dict] = []
        self._filtered: list[dict] = []
        self._search_active = False

    @property
    def t(self) -> dict:
        return self.app.theme_colors

    @property
    def _known_only(self) -> bool:
        return self.app.known_only

    @_known_only.setter
    def _known_only(self, value: bool) -> None:
        self.app.known_only = value
        self.app._prefs["known_only"] = value
        self.app._save_prefs()

    def compose(self) -> ComposeResult:
        with Static(id="list-header"):
            yield Static("Conversations", id="list-title")
            yield Static("/: search | Enter: open | Tab: known | Esc: back", id="list-hints")
        yield ListView(id="convo-list")
        yield Static("", id="list-footer")
        yield Input(placeholder="Filter by name...", id="search-input")

    def on_mount(self) -> None:
        self._apply_theme()
        self._conversations = list(self.app.conversations)
        if self._known_only:
            self.query_one("#list-title", Static).update("Conversations (known)")
        self._apply_filters()

    def _apply_theme(self) -> None:
        t = self.t
        self.styles.background = t["bg"]
        for sel in ("#list-header", "#list-title", "#list-hints"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#list-title").styles.color = t["accent"]
        self.query_one("#list-hints").styles.color = t["hint_color"]
        self.query_one("#convo-list").styles.background = t["bg"]
        self.query_one("#list-footer").styles.background = t["bg"]
        self.query_one("#list-footer").styles.color = t["dim_color"]
        self.query_one("#search-input").styles.background = t["header_bg"]
        self.query_one("#search-input").styles.color = t["text_color"]

    def _rebuild_list(self) -> None:
        t = self.t
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

            sms_tag = f" [italic {t['sms_tag_color']}]SMS[/]" if "SMS" in service else ""
            badge = f" [on {t['badge_color']}][#000000] {unread} [/][/]" if unread else ""
            max_preview = 40
            if len(preview) > max_preview:
                preview = preview[:max_preview] + "..."

            row_text = (
                f"[{t['name_color']}]{name}[/]{sms_tag}  "
                f"[#888888]{self._escape(preview)}[/]{badge}"
                f"  [{t['timestamp_color']}]{timestamp}[/]"
            )
            item = ListItem(Label(row_text))
            item.data = convo
            list_view.append(item)

        count = len(self._filtered)
        self.query_one("#list-footer", Static).update(
            f"{count} conversation{'s' if count != 1 else ''} | {unread_total} unread"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        convo = getattr(event.item, "data", None)
        if not convo:
            return
        self.app.unread_counts.pop(convo.get("chat_id", ""), None)
        self.dismiss(convo)

    def action_go_back(self) -> None:
        if self._search_active:
            self._search_active = False
            search = self.query_one("#search-input", Input)
            search.display = False
            search.value = ""
            self._apply_filters()
            self.query_one("#convo-list", ListView).focus()
        else:
            self.dismiss(None)

    def action_jump_top(self) -> None:
        self.query_one("#convo-list", ListView).index = 0

    def action_jump_bottom(self) -> None:
        self.query_one("#convo-list", ListView).index = len(self._filtered) - 1

    def _apply_filters(self) -> None:
        convos = self._conversations
        if self._known_only:
            convos = [
                c for c in convos
                if c.get("display_name")
                or "@" in c.get("chat_id", "")
                or c.get("chat_id", "").startswith("chat")
            ]
        if self._search_active:
            query = self.query_one("#search-input", Input).value.strip().lower()
            if query:
                convos = [
                    c for c in convos
                    if query in (c.get("display_name") or c.get("chat_id", "")).lower()
                ]
        self._filtered = convos
        self._rebuild_list()

    def action_toggle_known(self) -> None:
        self._known_only = not self._known_only
        title = "Conversations (known)" if self._known_only else "Conversations"
        self.query_one("#list-title", Static).update(title)
        self._apply_filters()

    def action_focus_search(self) -> None:
        self._search_active = True
        search = self.query_one("#search-input", Input)
        search.display = True
        search.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_filters()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#convo-list", ListView).focus()

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

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("[", "\\[")
