"""Search screen — search messages across all conversations."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static


class SearchScreen(Screen):
    """Full-text search across all messages."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back", show=True),
    ]

    DEFAULT_CSS = """
    SearchScreen {
        layout: vertical;
    }
    #search-header {
        dock: top;
        height: 1;
        layout: horizontal;
    }
    #search-title {
        width: 1fr;
        text-style: bold;
        padding: 0 1;
    }
    #search-hints {
        width: auto;
        padding: 0 1;
    }
    #search-input {
        dock: top;
        border: none;
    }
    #search-input:focus {
        border: none;
    }
    #search-results {
        height: 1fr;
    }
    #search-results > ListItem {
        height: 2;
        padding: 0 1;
    }
    #search-footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._results: list[dict] = []

    @property
    def t(self) -> dict:
        return self.app.theme_colors

    def compose(self) -> ComposeResult:
        with Static(id="search-header"):
            yield Static("Search Messages", id="search-title")
            yield Static("Enter: open chat | Esc: back", id="search-hints")
        yield Input(placeholder="Type to search...", id="search-input")
        yield ListView(id="search-results")
        yield Static("", id="search-footer")

    def on_mount(self) -> None:
        self._apply_theme()
        self.query_one("#search-input", Input).focus()

    def _apply_theme(self) -> None:
        t = self.t
        self.styles.background = t["bg"]
        for sel in ("#search-header", "#search-title", "#search-hints"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#search-title").styles.color = t["accent"]
        self.query_one("#search-hints").styles.color = t["hint_color"]
        self.query_one("#search-input").styles.background = t["header_bg"]
        self.query_one("#search-input").styles.color = t["text_color"]
        self.query_one("#search-results").styles.background = t["bg"]
        self.query_one("#search-footer").styles.background = t["bg"]
        self.query_one("#search-footer").styles.color = t["dim_color"]

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self.app.client.search(query)
        self.query_one("#search-footer", Static).update("Searching...")

    def load_results(self, results: list[dict]) -> None:
        self._results = results
        t = self.t
        list_view = self.query_one("#search-results", ListView)
        list_view.clear()

        for r in results:
            sender = r.get("sender") or "me"
            chat_name = r.get("chat_name") or r.get("chat_id", "")
            text = (r.get("text") or "")[:60]
            timestamp = self._format_time(r.get("date"))

            row = (
                f"[{t['name_color']}]{chat_name}[/]  "
                f"[{t['timestamp_color']}]{timestamp}[/]\n"
                f"[{t['dim_color']}]{sender}:[/] [{t['text_color']}]{self._escape(text)}[/]"
            )
            item = ListItem(Label(row))
            item.data = r
            list_view.append(item)

        self.query_one("#search-footer", Static).update(
            f"{len(results)} result{'s' if len(results) != 1 else ''}"
        )
        if results:
            list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        r = getattr(event.item, "data", None)
        if not r:
            return
        self.dismiss(r)

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)

    def _format_time(self, iso_date):
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            return dt.strftime("%b %d %Y")
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("[", "\\[")
