"""Scripted ~63s demo — Red Rising theme, timed to voiceover."""

import json
import ssl
import time
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
            "sender": sender, "sender_name": sender,
            "is_from_me": False, "service": service,
            "chat_id": chat_id, "chat_name": sender,
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
    pyautogui.press("space")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)
    pyautogui.typewrite(text, interval=0.03)
    time.sleep(0.3)
    pyautogui.press("enter")


def main():
    print("Connecting...")
    ws = connect_relay()
    print("Starting in 2s...")
    time.sleep(2)

    # ── Scene 1: Theme picker (7.7s) ──
    print("Scene 1: Themes")
    time.sleep(0.5)
    for _ in range(6):
        pyautogui.press("down")
        time.sleep(0.7)
    for _ in range(4):
        pyautogui.press("up")
        time.sleep(0.4)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    # ── Scene 2: Config (8.5s) ──
    print("Scene 2: Config")
    pyautogui.hotkey("ctrl", "o")
    time.sleep(2)
    for _ in range(5):
        pyautogui.press("down")
        time.sleep(1)
    pyautogui.press("escape")
    time.sleep(0.5)

    # ── Scene 3: Conversations (10.3s) ──
    print("Scene 3: Convos")
    pyautogui.press("escape")
    time.sleep(2)
    # Browse the list
    pyautogui.press("down")
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.5)
    # Toggle known-only filter
    pyautogui.press("tab")
    time.sleep(2)
    pyautogui.press("tab")
    time.sleep(1)
    # Go to top and select Sevro (first item)
    pyautogui.press("left")  # jump to top
    time.sleep(0.5)
    pyautogui.press("down")  # highlight first
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.8)

    # ── Scene 4: Messaging with Sevro (12.2s) ──
    print("Scene 4: Messaging")
    inject(ws, "+15551234567", "Darrow. Movement on the north ridge. Three, maybe four from House Ceres.", "Sevro au Barca")
    time.sleep(2)
    inject(ws, "+15551234567", "Want the Howlers on it?", "Sevro au Barca")
    time.sleep(2)
    type_and_send("Hold position. Let them commit.")
    time.sleep(2)
    inject(ws, "+15551234567", "Bloodydamn, you always make us wait. Fine.", "Sevro au Barca")
    time.sleep(1.5)
    type_and_send("Trust me. Hit them when they cross the creek.")
    time.sleep(1.5)
    inject(ws, "+15551234567", "Hic sunt leones, boyo.", "Sevro au Barca")
    time.sleep(1)
    # SMS from Proctor Mars
    inject(ws, "+15559876543", "Sector 7 will be unmonitored tonight. Do with that what you will.", "Proctor Mars", "SMS")
    time.sleep(1)
    # Howlers group
    inject(ws, "chat999demo", "I see torches. Southeast approach. At least a dozen.", "Pax au Telemanus")
    time.sleep(1.2)

    # ── Scene 5: Attachments via Mustang (11.7s) ──
    print("Scene 5: Attachments")
    pyautogui.press("escape")
    time.sleep(1)
    pyautogui.press("left")  # jump to top
    time.sleep(0.3)
    pyautogui.press("down")  # highlight first (Sevro)
    time.sleep(0.3)
    pyautogui.press("down")  # Mustang (second)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.5)
    inject(ws, "+15558675309", "Captured this from a Minerva scout. Ceres and Diana are allied.", "Mustang",
           attachments=[{"id": 10, "filename": "terrain_analysis.png", "mime_type": "image/png", "size": 2100000}])
    time.sleep(1)
    inject(ws, "+15558675309", "Here's the full battle map I drew up.", "Mustang",
           attachments=[{"id": 11, "filename": "institute_north_sector.pdf", "mime_type": "application/pdf", "size": 890000}])
    time.sleep(1)
    inject(ws, "+15558675309", "Read this before dawn https://institute-archive.mars/tactical/flanking-doctrine", "Mustang")
    time.sleep(1)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(3)
    pyautogui.press("down")
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.5)
    pyautogui.press("escape")
    time.sleep(0.9)

    # ── Scene 6: Theme cycling (11.5s) ──
    print("Scene 6: Themes")
    for _ in range(7):
        pyautogui.hotkey("ctrl", "t")
        time.sleep(1.5)
    time.sleep(1)

    # ── Scene 7: New conversation (5s, silent) ──
    print("Scene 7: New message")
    pyautogui.hotkey("ctrl", "n")
    time.sleep(2)
    pyautogui.press("space")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)
    pyautogui.typewrite("+1303555", interval=0.05)
    time.sleep(2)
    pyautogui.press("escape")
    time.sleep(1)

    print("Done!")
    ws.close()


if __name__ == "__main__":
    main()
