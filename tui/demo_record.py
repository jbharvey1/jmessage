"""Scripted 30-second demo recording — drives both the TUI and fake messages."""

import json
import ssl
import time
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import websockets.sync.client as ws_sync
import pyautogui
pyautogui.PAUSE = 0.05


def load_config():
    p = Path("config.demo.json")
    return json.loads(p.read_text()) if p.exists() else json.loads(Path("config.json").read_text())


def connect_relay():
    config = load_config()
    certs = config.get("certs")
    ssl_ctx = None
    if certs:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_ctx.load_verify_locations(certs["ca"])
        ssl_ctx.load_cert_chain(certs["client_cert"], certs["client_key"])
    ws = ws_sync.connect(config["relay_url"], ssl=ssl_ctx, max_size=50*1024*1024)
    ws.send(json.dumps({"type": "auth", "token": config["auth_token"]}))
    try:
        ws.recv(timeout=3)
    except TimeoutError:
        pass
    return ws


def inject(ws, chat_id, text, sender, service="iMessage", attachments=None):
    msg = {
        "type": "message",
        "data": {
            "id": int(time.time() * 1000) % 999999,
            "guid": f"demo-{int(time.time()*1000)}",
            "text": text,
            "sender": sender,
            "sender_name": sender,
            "is_from_me": False,
            "service": service,
            "chat_id": chat_id,
            "chat_name": sender,
            "date": datetime.now(timezone.utc).isoformat(),
            "date_read": None, "date_delivered": None,
            "has_attachments": bool(attachments),
            "tapback_type": 0, "tapback_target": None,
            "expressive_style": None,
            "attachments": attachments or [],
        },
    }
    ws.send(json.dumps({"type": "demo_inject", "data": msg}))


def type_and_send(text):
    """Type text into the TUI input and press Enter."""
    # First keystroke triggers auto-focus but gets consumed.
    # Send a dummy key to grab focus, then type the real text.
    pyautogui.press("space")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(0.3)
    pyautogui.press("enter")


def main():
    print("Connecting to mock relay...")
    ws = connect_relay()
    print("Connected. Starting in 2s...")
    time.sleep(2)

    # ── Scene 1: Theme picker (5s) ──
    print("Scene 1: Theme picker")
    time.sleep(1)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.6)
    for _ in range(4):
        pyautogui.press("up")
        time.sleep(0.4)
    time.sleep(0.5)
    pyautogui.press("enter")  # Select Ocean
    time.sleep(1.5)

    # ── Scene 2: Show config (Ctrl+O) (3s) ──
    print("Scene 2: Config screen")
    pyautogui.hotkey("ctrl", "o")
    time.sleep(3)
    pyautogui.press("escape")
    time.sleep(1)

    # ── Scene 3: Open convo list, pick Alex Chen (3s) ──
    print("Scene 3: Open conversation")
    pyautogui.press("escape")
    time.sleep(1)
    pyautogui.press("down")
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.5)

    # ── Scene 4: Conversation with replies (12s) ──
    print("Scene 4: Conversation")
    inject(ws, "+15551234567", "Hey! You around?", "Alex Chen")
    time.sleep(2)
    inject(ws, "+15551234567", "Wanna grab dinner tonight?", "Alex Chen")
    time.sleep(2)
    type_and_send("Yeah where at?")
    time.sleep(2)
    inject(ws, "+15551234567", "That new ramen place on Pearl St", "Alex Chen")
    time.sleep(1.5)
    type_and_send("I'm in, 7 work?")
    time.sleep(2)
    inject(ws, "+15551234567", "Perfect see you there", "Alex Chen")
    time.sleep(1)

    # SMS notification
    inject(ws, "+15559876543", "Your package has been delivered", "FedEx", "SMS")
    time.sleep(1)

    # Group chat
    inject(ws, "chat999demo", "Game day Sunday who's in?", "Jake Rivera")
    time.sleep(1.5)

    # ── Scene 5: Switch to a convo with attachments (Tab to navigate) ──
    print("Scene 5: Attachments")
    # Go to Mom's convo via Esc > navigate
    pyautogui.press("escape")
    time.sleep(1)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("down")  # Mom is 2nd
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.5)

    # Inject some messages with attachments into Mom's chat
    inject(ws, "+15558675309", "Look at this recipe I found!", "Mom",
           attachments=[{"id": 10, "filename": "recipe.pdf", "mime_type": "application/pdf", "size": 245000}])
    time.sleep(1)
    inject(ws, "+15558675309", "And here's a photo from the garden", "Mom",
           attachments=[{"id": 11, "filename": "IMG_2847.heic", "mime_type": "image/heic", "size": 3200000}])
    time.sleep(1)
    inject(ws, "+15558675309", "Check out this article https://example.com/best-tomato-soup-recipe", "Mom")
    time.sleep(1.5)

    # Open attachments screen
    pyautogui.hotkey("ctrl", "a")
    time.sleep(3)
    pyautogui.press("escape")
    time.sleep(1)

    # ── Scene 6: Cycle themes (5s) ──
    print("Scene 6: Theme cycling")
    for _ in range(6):
        pyautogui.hotkey("ctrl", "t")
        time.sleep(0.8)
    pyautogui.hotkey("ctrl", "t")  # back to start
    time.sleep(1)

    print("Done!")
    ws.close()


if __name__ == "__main__":
    main()
