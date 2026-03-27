"""Theme picker screen — shown on first launch."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Vertical, Horizontal

from themes import THEMES, THEME_ORDER, get_theme


DEMO_MESSAGES = [
    {"sender": "Mom", "text": "Are you coming for dinner Sunday?", "is_from_me": False, "service": "iMessage"},
    {"sender": "You", "text": "Yeah I'll be there around 6", "is_from_me": True, "service": "iMessage"},
    {"sender": "Mom", "text": "Perfect! I'm making lasagna", "is_from_me": False, "service": "iMessage"},
    {"sender": "You", "text": "Can't wait", "is_from_me": True, "service": "iMessage"},
    {"sender": "Jake", "text": "dude check this out", "is_from_me": False, "service": "SMS"},
]


class ThemePickerScreen(Screen):
    """Full-screen theme picker with live preview."""

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select_theme", "Select", show=True),
    ]

    CSS = """
    ThemePickerScreen {
        layout: vertical;
        background: #000000;
    }
    #picker-title {
        dock: top;
        height: 3;
        content-align: center middle;
        background: #111111;
        color: #ffffff;
        text-style: bold;
    }
    #picker-body {
        height: 1fr;
        layout: horizontal;
    }
    #theme-list {
        width: 30;
        height: 1fr;
        padding: 1 2;
    }
    .theme-item {
        height: 3;
        padding: 0 2;
        content-align: left middle;
    }
    #preview-area {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
    }
    #picker-hint {
        dock: bottom;
        height: 1;
        background: #111111;
        color: #666666;
        content-align: center middle;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._selected = 0

    def compose(self) -> ComposeResult:
        yield Static("JMessage — Choose a Theme", id="picker-title")
        with Horizontal(id="picker-body"):
            yield Vertical(id="theme-list")
            yield Vertical(id="preview-area")
        yield Static("↑↓ navigate  |  Enter to select  |  Ctrl+T to cycle later", id="picker-hint")

    def on_mount(self) -> None:
        self._render_list()
        self._render_preview()

    def _render_list(self) -> None:
        container = self.query_one("#theme-list", Vertical)
        container.remove_children()
        for i, key in enumerate(THEME_ORDER):
            t = THEMES[key]
            if i == self._selected:
                markup = (
                    f"[bold {t['accent']}]▸ {t['label']}[/]\n"
                    f"  [{t['dim_color']}]{t['desc']}[/]"
                )
            else:
                markup = (
                    f"[#888888]  {t['label']}[/]\n"
                    f"  [#555555]{t['desc']}[/]"
                )
            item = Static(markup, classes="theme-item")
            container.mount(item)

    def _render_preview(self) -> None:
        container = self.query_one("#preview-area", Vertical)
        container.remove_children()

        key = THEME_ORDER[self._selected]
        t = get_theme(key)

        # Preview header
        header = Static(
            f"[bold {t['accent']}]Mom[/]  [{t['hint_color']}]+1 (303) 555-0142[/]"
            f"    [{t['hint_color']}]iMessage[/]"
        )
        header.styles.background = t["header_bg"]
        header.styles.padding = (0, 1)
        container.mount(header)

        # Separator
        sep = Static(f"[{t['separator_color']}]── Today ──[/]")
        sep.styles.text_align = "center"
        sep.styles.background = t["bg"]
        sep.styles.padding = (1, 1, 0, 1)
        container.mount(sep)

        # Demo messages
        for msg in DEMO_MESSAGES:
            is_mine = msg["is_from_me"]
            is_sms = "SMS" in msg["service"]

            if is_mine:
                sender_color = t["you_color"]
                text_color = t["you_color"]
                sender = "You"
            else:
                sender_color = t["sms_color"] if is_sms else t["imessage_color"]
                text_color = t["text_color"]
                sender = msg["sender"]

            sms_tag = f" [{t['sms_tag_color']}]SMS[/]" if is_sms else ""

            sender_line = Static(
                f"[{sender_color}]{sender}[/]{sms_tag}  [{t['timestamp_color']}]3:42 PM[/]"
            )
            sender_line.styles.background = t["bg"]
            sender_line.styles.padding = (0, 1)
            container.mount(sender_line)

            text_line = Static(f"[{text_color}]{msg['text']}[/]")
            text_line.styles.background = t["bg"]
            text_line.styles.padding = (0, 1)
            container.mount(text_line)

        # Delivery status
        status = Static(f"[{t['timestamp_color']}]Delivered[/]")
        status.styles.background = t["bg"]
        status.styles.padding = (0, 1)
        container.mount(status)

        # Input bar preview
        input_bar = Static(f"[{t['hint_color']}]>[/] [{t['accent']}]_[/]")
        input_bar.styles.background = t["header_bg"]
        input_bar.styles.padding = (1, 1)
        container.mount(input_bar)

        # Update screen background
        self.query_one("#picker-title").styles.background = t["header_bg"]
        self.query_one("#picker-hint").styles.background = t["header_bg"]
        self.query_one("#picker-hint").styles.color = t["hint_color"]

    def action_move_up(self) -> None:
        if self._selected > 0:
            self._selected -= 1
            self._render_list()
            self._render_preview()

    def action_move_down(self) -> None:
        if self._selected < len(THEME_ORDER) - 1:
            self._selected += 1
            self._render_list()
            self._render_preview()

    def action_select_theme(self) -> None:
        self.dismiss(THEME_ORDER[self._selected])
