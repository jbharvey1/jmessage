"""JMessage Demo Responder — simulates incoming messages for recording demos."""

import json
import ssl
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import websockets.sync.client as ws_sync


def load_config(path="config.json"):
    return json.loads(Path(path).read_text())


def make_ssl_ctx(config):
    certs = config.get("certs", {})
    ca, cert, key = certs.get("ca"), certs.get("client_cert"), certs.get("client_key")
    if not all([ca, cert, key]):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(ca)
    ctx.load_cert_chain(cert, key)
    return ctx


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def msg(chat_id, text, sender, service="iMessage", guid=None, attachments=None):
    return {
        "type": "message",
        "data": {
            "id": int(time.time() * 1000) % 999999,
            "guid": guid or f"demo-{int(time.time()*1000)}",
            "text": text,
            "sender": sender,
            "sender_name": sender,
            "is_from_me": False,
            "service": service,
            "chat_id": chat_id,
            "chat_name": sender,
            "date": now_iso(),
            "date_read": None,
            "date_delivered": None,
            "has_attachments": bool(attachments),
            "tapback_type": 0,
            "tapback_target": None,
            "expressive_style": None,
            "attachments": attachments or [],
        },
    }


def tapback(chat_id, sender, target_guid, emoji, tapback_type=2001):
    return {
        "type": "message",
        "data": {
            "id": int(time.time() * 1000) % 999999,
            "guid": f"tapback-{int(time.time()*1000)}",
            "text": None,
            "sender": sender,
            "sender_name": sender,
            "is_from_me": False,
            "service": "iMessage",
            "chat_id": chat_id,
            "chat_name": sender,
            "date": now_iso(),
            "date_read": None,
            "date_delivered": None,
            "has_attachments": False,
            "tapback_type": tapback_type,
            "tapback_target": target_guid,
            "expressive_style": None,
            "attachments": [],
        },
    }


# ── Demo Scenarios ──

SCENARIOS = {
    "conversation": [
        # Natural back-and-forth with a friend
        (2, msg("+15551234567", "Hey are you free tonight?", "Alex Chen")),
        (4, msg("+15551234567", "Thinking about grabbing dinner at that new ramen place", "Alex Chen")),
        (8, msg("+15551234567", "The one on Pearl St", "Alex Chen")),
        (15, msg("+15551234567", "Ok cool I'll make a reservation for 7", "Alex Chen")),
        (3, msg("+15551234567", "Actually they don't take reservations lol", "Alex Chen")),
        (5, msg("+15551234567", "Let's just show up at 6:30 before the rush", "Alex Chen")),
    ],

    "group": [
        # Group chat activity
        (2, msg("chat999demo", "Who's coming to the game Sunday?", "Mike", "iMessage")),
        (4, msg("chat999demo", "I'm in", "Sarah", "iMessage")),
        (3, msg("chat999demo", "Same, what time?", "Dave", "iMessage")),
        (5, msg("chat999demo", "Kickoff is at 1 but tailgate starts at 11", "Mike", "iMessage")),
        (4, msg("chat999demo", "I'll bring the grill", "Dave", "iMessage")),
        (3, msg("chat999demo", "I got drinks covered", "Sarah", "iMessage")),
        (2, msg("chat999demo", "LFG 🏈", "Mike", "iMessage")),
    ],

    "sms": [
        # SMS conversation (green)
        (3, msg("+15559876543", "Your package has been delivered", "FedEx", "SMS")),
        (8, msg("+15559876543", "Left at front door", "FedEx", "SMS")),
    ],

    "attachment": [
        # Someone sends a photo
        (3, msg("+15551234567", "Check out this view from the hike today", "Alex Chen",
                attachments=[{"id": 1, "filename": "IMG_4521.heic", "mime_type": "image/heic", "size": 3145728}])),
        (6, msg("+15551234567", "Summit was insane", "Alex Chen")),
    ],

    "burst": [
        # Rapid fire messages from different people
        (1, msg("+15551234567", "Yo", "Alex Chen")),
        (1, msg("+15559876543", "Meeting moved to 3pm", "Boss", "SMS")),
        (1, msg("chat999demo", "Anyone seen my keys?", "Dave", "iMessage")),
        (2, msg("+15551234567", "You there?", "Alex Chen")),
        (1, msg("+15558675309", "Happy birthday!! 🎂🎉", "Mom")),
        (1, msg("chat999demo", "Check the couch", "Sarah", "iMessage")),
    ],

    "full": [
        # Full demo sequence — good for screen recording
        # Scene 1: Quiet, then a message comes in
        (3, msg("+15551234567", "Hey! Long time no talk", "Alex Chen")),
        (5, msg("+15551234567", "I saw you were working on that messaging app", "Alex Chen")),
        (4, msg("+15551234567", "How's it going?", "Alex Chen")),

        # Scene 2: Pause for user to reply, then continue
        (12, msg("+15551234567", "That's awesome, a terminal client?", "Alex Chen")),
        (4, msg("+15551234567", "Haha old school, I love it", "Alex Chen")),

        # Scene 3: Attachment
        (8, msg("+15551234567", "Check this out", "Alex Chen",
                attachments=[{"id": 2, "filename": "screenshot.png", "mime_type": "image/png", "size": 524288}])),
        (4, msg("+15551234567", "Built something similar last year", "Alex Chen")),

        # Scene 4: Different person, SMS
        (6, msg("+15559876543", "Reminder: dentist appointment tomorrow at 2pm", "Dr. Smith Office", "SMS")),

        # Scene 5: Group chat
        (5, msg("chat999demo", "Friday night plans?", "Mike", "iMessage")),
        (3, msg("chat999demo", "Board game night at my place", "Sarah", "iMessage")),
        (2, msg("chat999demo", "I'm bringing Catan", "Dave", "iMessage")),
        (4, msg("chat999demo", "Nice, I'll bring snacks", "Mike", "iMessage")),

        # Scene 6: Back to original convo
        (6, msg("+15551234567", "Anyway let me know if you want to grab coffee this week", "Alex Chen")),
        (3, msg("+15551234567", "I'm free Wed or Thurs", "Alex Chen")),

        # Scene 7: Mom
        (8, msg("+15558675309", "Don't forget to call grandma, it's her birthday", "Mom")),
        (3, msg("+15558675309", "She'd love to hear from you", "Mom")),
    ],
}


def run_demo(scenario_name="full"):
    # Use demo config if it exists, otherwise regular config
    demo_cfg = Path("config.demo.json")
    config = load_config(str(demo_cfg) if demo_cfg.exists() else "config.json")
    ssl_ctx = make_ssl_ctx(config) if "certs" in config else None

    scenario = SCENARIOS.get(scenario_name)
    if not scenario:
        print(f"Unknown scenario: {scenario_name}")
        print(f"Available: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    print(f"Connecting to relay...")
    ws = ws_sync.connect(config["relay_url"], ssl=ssl_ctx, max_size=50 * 1024 * 1024)
    ws.send(json.dumps({"type": "auth", "token": config["auth_token"]}))

    # Drain the initial conversations response
    try:
        ws.recv(timeout=3)
    except TimeoutError:
        pass

    print(f"Running demo: {scenario_name} ({len(scenario)} messages)")
    print(f"Press Ctrl+C to stop\n")

    try:
        for delay, message in scenario:
            sender = message["data"].get("sender_name") or message["data"]["sender"]
            text = message["data"].get("text") or "[attachment]"
            chat = message["data"]["chat_id"]

            print(f"  [{delay}s] {sender}: {text[:50]}".encode('ascii', 'replace').decode())
            time.sleep(delay)

            # Inject via relay — broadcasts to all connected clients
            ws.send(json.dumps({"type": "demo_inject", "data": message}))

        print(f"\nDemo complete!")
    except KeyboardInterrupt:
        print(f"\nStopped.")
    finally:
        ws.close()


if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "full"
    run_demo(scenario)
