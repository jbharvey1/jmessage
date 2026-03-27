"""Attachments screen — lists all attachments and URLs for a chat."""

import base64
import os
import platform
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static


ATTACHMENTS_DIR = Path(__file__).parent.parent / "attachments"


class AttachmentsScreen(Screen):
    """Popup listing all attachments in the current chat."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back", show=True),
    ]

    DEFAULT_CSS = """
    AttachmentsScreen {
        layout: vertical;
    }
    #att-header {
        dock: top;
        height: 1;
        layout: horizontal;
    }
    #att-title {
        width: 1fr;
        text-style: bold;
        padding: 0 1;
    }
    #att-hints {
        width: auto;
        padding: 0 1;
    }
    #att-list {
        height: 1fr;
    }
    #att-list > ListItem {
        height: 1;
        padding: 0 1;
    }
    #att-footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    #att-status {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self, chat_id: str, chat_name: str) -> None:
        super().__init__()
        self._chat_id = chat_id
        self._chat_name = chat_name
        self._attachments: list[dict] = []
        self._urls: list[dict] = []
        self._items: list[dict] = []  # unified list for selection
        self._pending_download: dict | None = None
        self._bulk_mode: str | None = None  # "all" or "images"
        self._bulk_files: list[tuple[str, bytes]] = []
        self._bulk_expected: int = 0

    @property
    def t(self) -> dict:
        return self.app.theme_colors

    def compose(self) -> ComposeResult:
        t = self.t
        with Static(id="att-header"):
            yield Static("Attachments", id="att-title")
            yield Static("Enter: download | Esc: back", id="att-hints")
        yield ListView(id="att-list")
        yield Static("", id="att-status")
        yield Static("Loading...", id="att-footer")

    def on_mount(self) -> None:
        self._apply_theme()
        self.app.client.request_chat_attachments(self._chat_id)

    def _apply_theme(self) -> None:
        t = self.t
        self.styles.background = t["bg"]
        for sel in ("#att-header", "#att-title", "#att-hints"):
            try:
                w = self.query_one(sel)
                w.styles.background = t["header_bg"]
            except Exception:
                pass
        self.query_one("#att-title").styles.color = t["accent"]
        self.query_one("#att-hints").styles.color = t["hint_color"]
        self.query_one("#att-list").styles.background = t["bg"]
        self.query_one("#att-footer").styles.background = t["bg"]
        self.query_one("#att-footer").styles.color = t["dim_color"]
        self.query_one("#att-status").styles.background = t["bg"]
        self.query_one("#att-status").styles.color = t["dim_color"]

    def load_data(self, attachments: list[dict], urls: list[dict]) -> None:
        """Called by the app when chat_attachments response arrives."""
        self._attachments = attachments
        self._urls = urls
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        t = self.t
        list_view = self.query_one("#att-list", ListView)
        list_view.clear()
        self._items.clear()

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        # All bundle
        total = len(self._attachments) + (1 if self._urls else 0)
        self._items.append({"type": "all", "label": f"All (as all-{ts}.zip)", "ts": ts})
        item = ListItem(Label(f"[{t['accent']}]▸ All[/]  [{t['dim_color']}]{total} items → all-{ts}.zip[/]"))
        list_view.append(item)

        # URLs
        if self._urls:
            self._items.append({"type": "urls", "label": "urls.txt"})
            item = ListItem(Label(f"[{t['name_color']}]  urls.txt[/]  [{t['dim_color']}]{len(self._urls)} URLs[/]"))
            list_view.append(item)

        # Images zip
        images = [a for a in self._attachments if (a.get("mime_type") or "").startswith("image/")]
        if images:
            self._items.append({"type": "images", "label": "images.zip", "count": len(images)})
            item = ListItem(Label(f"[{t['name_color']}]  images.zip[/]  [{t['dim_color']}]{len(images)} images[/]"))
            list_view.append(item)

        # Individual attachments
        for att in self._attachments:
            fname = att.get("filename") or "unknown"
            size = att.get("size") or 0
            size_str = self._format_size(size)
            sender = att.get("sender") or ""
            self._items.append({"type": "file", "attachment": att})
            item = ListItem(Label(
                f"[{t['text_color']}]  {fname}[/]  [{t['dim_color']}]{size_str}  {sender}[/]"
            ))
            list_view.append(item)

        self.query_one("#att-footer", Static).update(
            f"{len(self._attachments)} attachments | {len(self._urls)} URLs"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is None or idx >= len(self._items):
            return
        item = self._items[idx]
        ATTACHMENTS_DIR.mkdir(exist_ok=True)

        if item["type"] == "urls":
            self._save_urls()
        elif item["type"] == "all":
            self._start_bulk_download("all", item.get("ts", ""))
        elif item["type"] == "images":
            self._start_bulk_download("images", "")
        elif item["type"] == "file":
            att = item["attachment"]
            self._pending_download = att
            self._set_status(f"Downloading {att.get('filename')}...")
            self.app.client.request_attachment_data(att["id"], att["path"])

    def _ensure_attachments_dir(self) -> bool:
        try:
            ATTACHMENTS_DIR.mkdir(exist_ok=True)
            return True
        except OSError as e:
            self._set_status(f"Cannot create attachments dir: {e}")
            return False

    def handle_attachment_data(self, att_id, path: str, content) -> None:
        """Called by the app when attachment_data response arrives."""
        if content is None:
            self._set_status("File not found on server")
            if self._bulk_mode:
                self._bulk_expected -= 1
                if len(self._bulk_files) >= self._bulk_expected:
                    self._finish_bulk_download()
            else:
                self._pending_download = None
            return

        try:
            raw = base64.b64decode(content)
        except Exception:
            self._set_status("Failed to decode attachment data")
            self._pending_download = None
            return

        if self._bulk_mode:
            fname = os.path.basename(path)
            self._bulk_files.append((fname, raw))
            self._set_status(f"Downloaded {len(self._bulk_files)}/{self._bulk_expected}...")
            if len(self._bulk_files) >= self._bulk_expected:
                self._finish_bulk_download()
            return

        if self._pending_download:
            if not self._ensure_attachments_dir():
                self._pending_download = None
                return
            fname = self._pending_download.get("filename") or os.path.basename(path)
            out = ATTACHMENTS_DIR / fname
            if out.exists():
                stem, suffix = out.stem, out.suffix
                out = ATTACHMENTS_DIR / f"{stem}_{datetime.now().strftime('%H%M%S')}{suffix}"
            try:
                out.write_bytes(raw)
            except OSError as e:
                self._set_status(f"Write failed: {e}")
                self._pending_download = None
                return
            self._set_status(f"Saved: attachments/{out.name}")
            self._open_file(out)
            self._pending_download = None

    def _save_urls(self) -> None:
        if not self._ensure_attachments_dir():
            return
        lines = []
        for u in self._urls:
            lines.append(f"{u['url']}  ({u.get('sender', '')} {u.get('date', '')})")
        out = ATTACHMENTS_DIR / "urls.txt"
        try:
            out.write_text("\n".join(lines), encoding="utf-8")
        except OSError as e:
            self._set_status(f"Write failed: {e}")
            return
        self._set_status(f"Saved: attachments/urls.txt ({len(self._urls)} URLs)")
        self._open_file(out)

    def _start_bulk_download(self, mode: str, ts: str) -> None:
        self._bulk_mode = mode
        self._bulk_ts = ts
        self._bulk_files = []

        if mode == "all":
            targets = list(self._attachments)
        else:  # images
            targets = [a for a in self._attachments if (a.get("mime_type") or "").startswith("image/")]

        self._bulk_targets = targets
        self._bulk_expected = len(targets)

        if self._bulk_expected == 0:
            self._finish_bulk_download()
            return

        self._set_status(f"Downloading 0/{self._bulk_expected}...")
        for att in targets:
            self.app.client.request_attachment_data(att["id"], att["path"])

    def _finish_bulk_download(self) -> None:
        if not self._ensure_attachments_dir():
            self._bulk_mode = None
            self._bulk_files = []
            return

        if self._bulk_mode == "all":
            zip_name = f"all-{self._bulk_ts}.zip"
        else:
            zip_name = "images.zip"

        zip_path = ATTACHMENTS_DIR / zip_name
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if self._bulk_mode == "all" and self._urls:
                    lines = []
                    for u in self._urls:
                        lines.append(f"{u['url']}  ({u.get('sender', '')} {u.get('date', '')})")
                    zf.writestr("urls.txt", "\n".join(lines))

                seen = set()
                for fname, data in self._bulk_files:
                    if fname in seen:
                        stem, _, ext = fname.rpartition(".")
                        fname = f"{stem}_{len(seen)}.{ext}" if ext else f"{fname}_{len(seen)}"
                    seen.add(fname)
                    zf.writestr(fname, data)
        except OSError as e:
            self._set_status(f"Zip write failed: {e}")
            self._bulk_mode = None
            self._bulk_files = []
            return

        self._set_status(f"Saved: attachments/{zip_name} ({len(self._bulk_files)} files)")
        self._open_file(zip_path)
        self._bulk_mode = None
        self._bulk_files = []

    def _set_status(self, text: str) -> None:
        t = self.t
        self.query_one("#att-status", Static).update(f"[{t['accent']}]{text}[/]")

    def _open_file(self, path: Path) -> None:
        """Open a file in the default browser/viewer."""
        try:
            if platform.system() == "Windows":
                subprocess.Popen(
                    [r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", str(path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # non-critical, file is saved regardless

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)

    @staticmethod
    def _format_size(size: int) -> str:
        if not size:
            return ""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size // 1024}KB"
        else:
            return f"{size // (1024 * 1024)}MB"
