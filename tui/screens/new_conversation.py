"""New conversation screen — Ctrl+N to compose a new message."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, Static


class NewConversationScreen(Screen):
    """Simple screen to enter a phone number or email to start a new chat."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back", show=True),
    ]

    DEFAULT_CSS = """
    NewConversationScreen {
        layout: vertical;
        align: center middle;
    }
    #new-header {
        dock: top;
        height: 1;
        layout: horizontal;
    }
    #new-title {
        width: 1fr;
        text-style: bold;
        padding: 0 1;
    }
    #new-hints {
        width: auto;
        padding: 0 1;
    }
    #new-prompt {
        height: auto;
        content-align: center middle;
        padding: 3 0 1 0;
    }
    #new-input {
        width: 50;
        margin: 0 auto;
        border: none;
    }
    #new-input:focus {
        border: none;
    }
    """

    @property
    def t(self) -> dict:
        return self.app.theme_colors

    def compose(self) -> ComposeResult:
        with Static(id="new-header"):
            yield Static("New Conversation", id="new-title")
            yield Static("Enter: start | Esc: cancel", id="new-hints")
        yield Static("Enter a phone number or email:", id="new-prompt")
        yield Input(placeholder="+1234567890 or name@email.com", id="new-input")

    def on_mount(self) -> None:
        t = self.t
        self.styles.background = t["bg"]
        for sel in ("#new-header", "#new-title", "#new-hints"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#new-title").styles.color = t["accent"]
        self.query_one("#new-hints").styles.color = t["hint_color"]
        self.query_one("#new-prompt").styles.color = t["text_color"]
        self.query_one("#new-prompt").styles.background = t["bg"]
        self.query_one("#new-input").styles.background = t["header_bg"]
        self.query_one("#new-input").styles.color = t["text_color"]
        self.query_one("#new-input").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self.dismiss(value)

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)
