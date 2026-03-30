"""Mock JMessage relay — Red Rising theme for demos."""

import asyncio
import json
from datetime import datetime, timezone, timedelta

import websockets

AUTH_TOKEN = "demo"
WS_HOST = "127.0.0.1"
WS_PORT = 8766
clients = set()


def now_iso(offset_hours=0):
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).isoformat()


CONVERSATIONS = [
    {"chat_id": "+15551234567", "display_name": "Sevro au Barca", "service": "iMessage",
     "last_message": "It always matters. Omnis vir lupus.", "last_date": None},
    {"chat_id": "+15558675309", "display_name": "Mustang", "service": "iMessage",
     "last_message": "We should coordinate. My scouts can cover your western flank.", "last_date": None},
    {"chat_id": "chat999demo", "display_name": "Howlers", "service": "iMessage",
     "last_message": "Focus, Howlers.", "last_date": None},
    {"chat_id": "+15559876543", "display_name": "Proctor Mars", "service": "SMS",
     "last_message": "Resources deposited at drop point Gamma. Don't ask questions.", "last_date": None},
    {"chat_id": "+15552468013", "display_name": "Cassius au Bellona", "service": "iMessage",
     "last_message": "We should talk, Darrow.", "last_date": None},
    {"chat_id": "+15553691470", "display_name": "Dancer", "service": "iMessage",
     "last_message": "Stay sharp. The Sons are watching.", "last_date": None},
    {"chat_id": "+15557924680", "display_name": "", "service": "SMS",
     "last_message": "You can't hide what you are forever.", "last_date": None},
    {"chat_id": "+15551357924", "display_name": "Pax au Telemanus", "service": "iMessage",
     "last_message": "For glory, brother.", "last_date": None},
]


def make_history(chat_id):
    histories = {
        "+15551234567": [
            {"guid": "s1", "text": "Wolves don't sleep, Reaper.", "is_from_me": False, "sender": "+15551234567", "sender_name": "Sevro au Barca", "service": "iMessage", "date": now_iso(-3), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "s2", "text": "Neither do I. What's the count?", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-2.8), "date_read": now_iso(-2.7), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "s3", "text": "Twelve confirmed from Ceres. They're sloppy.", "is_from_me": False, "sender": "+15551234567", "sender_name": "Sevro au Barca", "service": "iMessage", "date": now_iso(-2.5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "s4", "text": "Good. Sloppy means predictable.", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-2.3), "date_read": now_iso(-2.2), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "s5", "text": "I sharpened my razor. Just saying.", "is_from_me": False, "sender": "+15551234567", "sender_name": "Sevro au Barca", "service": "iMessage", "date": now_iso(-2), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "s6", "text": "Save it for when it matters.", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-1.5), "date_read": now_iso(-1.4), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "s7", "text": "It always matters. Omnis vir lupus.", "is_from_me": False, "sender": "+15551234567", "sender_name": "Sevro au Barca", "service": "iMessage", "date": now_iso(-1), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
        "+15558675309": [
            {"guid": "m1", "text": "Your strategy at the river was reckless.", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mustang", "service": "iMessage", "date": now_iso(-24), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m2", "text": "It worked.", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-23), "date_read": now_iso(-22), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m3", "text": "This time. What happens when it doesn't?", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mustang", "service": "iMessage", "date": now_iso(-22), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m4", "text": "Then I adapt. That's what I do.", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-21), "date_read": now_iso(-20), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m5", "text": "You almost said something interesting there, Darrow.", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mustang", "service": "iMessage", "date": now_iso(-20), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m6", "text": "We should coordinate. My scouts can cover your western flank.", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mustang", "service": "iMessage", "date": now_iso(-3), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
        "chat999demo": [
            {"guid": "g1", "text": "Brothers, who hunts tonight?", "is_from_me": False, "sender": "+15551357924", "sender_name": "Pax au Telemanus", "service": "iMessage", "date": now_iso(-5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g2", "text": "All of us. Full moon means full assault.", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-4.8), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g3", "text": "I call first blood.", "is_from_me": False, "sender": "+15551234567", "sender_name": "Sevro au Barca", "service": "iMessage", "date": now_iso(-4.5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g4", "text": "Must you always be so crude?", "is_from_me": False, "sender": "+15553691470", "sender_name": "Roque au Fabii", "service": "iMessage", "date": now_iso(-4), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g5", "text": "Must you always be such a pixie?", "is_from_me": False, "sender": "+15551234567", "sender_name": "Sevro au Barca", "service": "iMessage", "date": now_iso(-3.8), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g6", "text": "Haha. Focus, Howlers.", "is_from_me": False, "sender": "+15551357924", "sender_name": "Pax au Telemanus", "service": "iMessage", "date": now_iso(-3.5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
        "+15559876543": [
            {"guid": "p1", "text": "Resources deposited at drop point Gamma. Don't ask questions.", "is_from_me": False, "sender": "+15559876543", "sender_name": "Proctor Mars", "service": "SMS", "date": now_iso(-24), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
    }
    return histories.get(chat_id, [])


async def handle_client(websocket):
    try:
        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
        auth = json.loads(auth_msg)
        if auth.get("type") != "auth" or auth.get("token") != AUTH_TOKEN:
            await websocket.send(json.dumps({"type": "error", "data": {"message": "Invalid auth"}}))
            await websocket.close()
            return
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await websocket.close()
        return

    clients.add(websocket)

    for i, c in enumerate(CONVERSATIONS):
        c["last_date"] = now_iso(-i * 3)

    await websocket.send(json.dumps({"type": "conversations", "data": CONVERSATIONS}))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                data = msg.get("data", {})
            except (json.JSONDecodeError, AttributeError):
                continue

            if msg_type == "get_conversations":
                await websocket.send(json.dumps({"type": "conversations", "data": CONVERSATIONS}))
            elif msg_type == "get_history":
                chat_id = data.get("chat_id", "")
                await websocket.send(json.dumps({"type": "history", "data": {"chat_id": chat_id, "messages": make_history(chat_id)}}))
            elif msg_type == "send":
                await websocket.send(json.dumps({"type": "send_result", "data": {"success": True, "recipient": data.get("chat_id")}}))
            elif msg_type == "get_tapbacks":
                await websocket.send(json.dumps({"type": "tapbacks", "data": {"chat_id": data.get("chat_id", ""), "tapbacks": {}}}))
            elif msg_type == "get_chat_members":
                members = []
                if data.get("chat_id") == "chat999demo":
                    members = [
                        {"identifier": "+15551234567", "display_name": "Sevro au Barca", "service": "iMessage"},
                        {"identifier": "+15551357924", "display_name": "Pax au Telemanus", "service": "iMessage"},
                        {"identifier": "+15553691470", "display_name": "Roque au Fabii", "service": "iMessage"},
                    ]
                await websocket.send(json.dumps({"type": "chat_members", "data": {"chat_id": data.get("chat_id", ""), "members": members}}))
            elif msg_type == "demo_inject":
                payload = json.dumps(data)
                for ws in clients:
                    try:
                        await ws.send(payload)
                    except websockets.exceptions.ConnectionClosed:
                        pass
            elif msg_type == "search":
                await websocket.send(json.dumps({"type": "search_results", "data": {"query": data.get("query", ""), "results": []}}))
            elif msg_type == "get_chat_attachments":
                await websocket.send(json.dumps({
                    "type": "chat_attachments",
                    "data": {
                        "chat_id": data.get("chat_id", ""),
                        "attachments": [
                            {"id": 10, "filename": "terrain_analysis.png", "mime_type": "image/png", "size": 2100000,
                             "is_from_me": False, "sender": "Mustang", "date": now_iso(-12), "path": "terrain_analysis.png"},
                            {"id": 11, "filename": "institute_north_sector.pdf", "mime_type": "application/pdf", "size": 890000,
                             "is_from_me": False, "sender": "Mustang", "date": now_iso(-8), "path": "institute_north_sector.pdf"},
                            {"id": 12, "filename": "perimeter_scan.holo", "mime_type": "application/octet-stream", "size": 524000,
                             "is_from_me": False, "sender": "Sevro au Barca", "date": now_iso(-6), "path": "perimeter_scan.holo"},
                            {"id": 13, "filename": "garrison_roster.pdf", "mime_type": "application/pdf", "size": 340000,
                             "is_from_me": True, "sender": "me", "date": now_iso(-24), "path": "garrison_roster.pdf"},
                        ],
                        "urls": [
                            {"url": "https://institute-archive.mars/tactical/flanking-doctrine", "sender": "Mustang", "date": now_iso(-6)},
                            {"url": "https://house-mars.mil/orders/night-ops-7g", "sender": "Sevro au Barca", "date": now_iso(-12)},
                        ],
                    }
                }))
            elif msg_type == "get_attachment_data":
                await websocket.send(json.dumps({"type": "attachment_data", "data": {"id": data.get("id"), "path": "", "content": None}}))

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)


async def main():
    print(f"Mock Relay on ws://{WS_HOST}:{WS_PORT}")
    async with websockets.serve(handle_client, WS_HOST, WS_PORT, max_size=50 * 1024 * 1024):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
