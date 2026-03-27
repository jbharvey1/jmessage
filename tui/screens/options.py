"""Options screen — Ctrl+O settings panel."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from themes import THEMES, THEME_ORDER


SETTINGS = [
    {"key": "theme", "label": "Theme", "type": "cycle", "options": THEME_ORDER},
    {"key": "known_only", "label": "Known-only filter", "type": "toggle"},
    {"key": "bell", "label": "Terminal bell on messages", "type": "toggle"},
    {"key": "history_limit", "label": "Message history limit", "type": "cycle", "options": [50, 100, 200]},
    {"key": "relay_url", "label": "Relay URL", "type": "display"},
    {"key": "auth_token", "label": "Auth token", "type": "display_masked"},
]


class OptionsScreen(Screen):
    """Settings screen with arrow-key navigation and Enter/Space to toggle."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back", show=True),
        Binding("enter", "toggle_setting", "Change", show=True),
        Binding("space", "toggle_setting", "Change", show=False),
    ]

    DEFAULT_CSS = """
    OptionsScreen {
        layout: vertical;
    }
    #opt-header {
        dock: top;
        height: 1;
        layout: horizontal;
    }
    #opt-title {
        width: 1fr;
        text-style: bold;
        padding: 0 1;
    }
    #opt-hints {
        width: auto;
        padding: 0 1;
    }
    #opt-list {
        height: 1fr;
    }
    #opt-list > ListItem {
        height: 1;
        padding: 0 1;
    }
    #opt-footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._changed = False

    @property
    def t(self) -> dict:
        return self.app.theme_colors

    def compose(self) -> ComposeResult:
        with Static(id="opt-header"):
            yield Static("Options", id="opt-title")
            yield Static("Enter: change | Esc: back", id="opt-hints")
        yield ListView(id="opt-list")
        yield Static("", id="opt-footer")

    def on_mount(self) -> None:
        self._apply_theme()
        self._rebuild_list()

    def _apply_theme(self) -> None:
        t = self.t
        self.styles.background = t["bg"]
        for sel in ("#opt-header", "#opt-title", "#opt-hints"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#opt-title").styles.color = t["accent"]
        self.query_one("#opt-hints").styles.color = t["hint_color"]
        self.query_one("#opt-list").styles.background = t["bg"]
        self.query_one("#opt-footer").styles.background = t["bg"]
        self.query_one("#opt-footer").styles.color = t["dim_color"]

    def _get_value(self, setting: dict) -> str:
        key = setting["key"]
        t = self.t
        if key == "theme":
            name = self.app._prefs.get("theme", "midnight")
            return THEMES.get(name, {}).get("label", name)
        elif key == "known_only":
            return "ON" if self.app.known_only else "OFF"
        elif key == "bell":
            return "ON" if self.app._prefs.get("bell", True) else "OFF"
        elif key == "history_limit":
            return str(self.app._prefs.get("history_limit", 50))
        elif key == "relay_url":
            return self.app.config.get("relay_url", "")
        elif key == "auth_token":
            token = self.app.config.get("auth_token", "")
            if len(token) > 4:
                return token[:2] + "•" * (len(token) - 4) + token[-2:]
            return "•" * len(token)
        return ""

    def _get_value_color(self, setting: dict) -> str:
        t = self.t
        key = setting["key"]
        if key in ("known_only", "bell"):
            val = self.app.known_only if key == "known_only" else self.app._prefs.get("bell", True)
            return "#4caf50" if val else "#f44336"
        return t["accent"]

    def _rebuild_list(self) -> None:
        t = self.t
        list_view = self.query_one("#opt-list", ListView)
        list_view.clear()

        for setting in SETTINGS:
            val = self._get_value(setting)
            val_color = self._get_value_color(setting)
            editable = setting["type"] in ("cycle", "toggle")
            arrow = " ◂▸" if editable else ""

            row = (
                f"[{t['name_color']}]{setting['label']}[/]"
                f"    [{val_color}]{val}[/]"
                f"[{t['hint_color']}]{arrow}[/]"
            )
            item = ListItem(Label(row))
            item.data = setting
            list_view.append(item)

        self.query_one("#opt-footer", Static).update(
            f"[{t['dim_color']}]Enter/Space to change • Esc to go back[/]"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._do_toggle(event.list_view.index)

    def action_toggle_setting(self) -> None:
        list_view = self.query_one("#opt-list", ListView)
        self._do_toggle(list_view.index)

    def _do_toggle(self, idx) -> None:
        if idx is None or idx >= len(SETTINGS):
            return
        setting = SETTINGS[idx]
        key = setting["key"]

        if setting["type"] == "toggle":
            if key == "known_only":
                self.app.known_only = not self.app.known_only
                self.app._prefs["known_only"] = self.app.known_only
            elif key == "bell":
                current = self.app._prefs.get("bell", True)
                self.app._prefs["bell"] = not current
            self.app._save_prefs()
            self._changed = True
            self._rebuild_list()

        elif setting["type"] == "cycle":
            options = setting["options"]
            if key == "theme":
                current = self.app._prefs.get("theme", "midnight")
                try:
                    idx_cur = options.index(current)
                except ValueError:
                    idx_cur = -1
                next_val = options[(idx_cur + 1) % len(options)]
                self.app.set_theme(next_val)
                self._apply_theme()
                self._changed = True
                self._rebuild_list()

            elif key == "history_limit":
                current = self.app._prefs.get("history_limit", 50)
                try:
                    idx_cur = options.index(current)
                except ValueError:
                    idx_cur = 0
                next_val = options[(idx_cur + 1) % len(options)]
                self.app._prefs["history_limit"] = next_val
                self.app._save_prefs()
                self._changed = True
                self._rebuild_list()

    def action_dismiss_screen(self) -> None:
        self.dismiss(self._changed)
