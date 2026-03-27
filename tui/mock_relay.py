"""Mock JMessage relay — serves fake data for demos. No real iMessage data."""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta

import websockets

AUTH_TOKEN = "demo"
WS_HOST = "127.0.0.1"
WS_PORT = 8766
clients = set()

# Fake conversations
CONVERSATIONS = [
    {"chat_id": "+15551234567", "display_name": "Alex Chen", "service": "iMessage",
     "last_message": "Let's just show up at 6:30 before the rush", "last_date": None},
    {"chat_id": "+15558675309", "display_name": "Mom", "service": "iMessage",
     "last_message": "Are you coming for dinner Sunday?", "last_date": None},
    {"chat_id": "chat999demo", "display_name": "Weekend Crew", "service": "iMessage",
     "last_message": "LFG", "last_date": None},
    {"chat_id": "+15559876543", "display_name": "Dr. Smith Office", "service": "SMS",
     "last_message": "Your appointment is confirmed for Tuesday", "last_date": None},
    {"chat_id": "+15552468013", "display_name": "Jake Rivera", "service": "iMessage",
     "last_message": "dude check this out", "last_date": None},
    {"chat_id": "+15553691470", "display_name": "Sarah Kim", "service": "iMessage",
     "last_message": "See you tomorrow!", "last_date": None},
    {"chat_id": "+15557924680", "display_name": "", "service": "SMS",
     "last_message": "Your package has shipped", "last_date": None},
    {"chat_id": "+15551357924", "display_name": "Dad", "service": "iMessage",
     "last_message": "Thanks son", "last_date": None},
]

def now_iso(offset_hours=0):
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).isoformat()

def make_history(chat_id):
    """Generate fake chat history for each conversation."""
    histories = {
        "+15551234567": [
            {"guid": "a1", "text": "Hey are you free tonight?", "is_from_me": False, "sender": "+15551234567", "sender_name": "Alex Chen", "service": "iMessage", "date": now_iso(-2), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a2", "text": "Yeah what's up?", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-1.9), "date_read": now_iso(-1.8), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a3", "text": "Thinking about grabbing dinner at that new ramen place", "is_from_me": False, "sender": "+15551234567", "sender_name": "Alex Chen", "service": "iMessage", "date": now_iso(-1.8), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a4", "text": "The one on Pearl St", "is_from_me": False, "sender": "+15551234567", "sender_name": "Alex Chen", "service": "iMessage", "date": now_iso(-1.7), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a5", "text": "Oh yeah I've been wanting to try that place", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-1.5), "date_read": now_iso(-1.4), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a6", "text": "Ok cool let's do it", "is_from_me": False, "sender": "+15551234567", "sender_name": "Alex Chen", "service": "iMessage", "date": now_iso(-1.3), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a7", "text": "They don't take reservations though lol", "is_from_me": False, "sender": "+15551234567", "sender_name": "Alex Chen", "service": "iMessage", "date": now_iso(-1.2), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "a8", "text": "Let's just show up at 6:30 before the rush", "is_from_me": False, "sender": "+15551234567", "sender_name": "Alex Chen", "service": "iMessage", "date": now_iso(-1), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
        "+15558675309": [
            {"guid": "m1", "text": "Don't forget we're doing brunch Saturday", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mom", "service": "iMessage", "date": now_iso(-24), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m2", "text": "I'll be there!", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-23), "date_read": now_iso(-22), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m3", "text": "Can you pick up some orange juice on the way?", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mom", "service": "iMessage", "date": now_iso(-22), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m4", "text": "Sure, pulp or no pulp?", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-21), "date_read": now_iso(-20), "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m5", "text": "No pulp please", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mom", "service": "iMessage", "date": now_iso(-20), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "m6", "text": "Are you coming for dinner Sunday?", "is_from_me": False, "sender": "+15558675309", "sender_name": "Mom", "service": "iMessage", "date": now_iso(-3), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
        "chat999demo": [
            {"guid": "g1", "text": "Who's coming to the game Sunday?", "is_from_me": False, "sender": "+15552468013", "sender_name": "Jake Rivera", "service": "iMessage", "date": now_iso(-5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g2", "text": "I'm in", "is_from_me": True, "sender": "me", "sender_name": "", "service": "iMessage", "date": now_iso(-4.8), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g3", "text": "Same, what time?", "is_from_me": False, "sender": "+15553691470", "sender_name": "Sarah Kim", "service": "iMessage", "date": now_iso(-4.5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g4", "text": "Kickoff is at 1 but tailgate starts at 11", "is_from_me": False, "sender": "+15552468013", "sender_name": "Jake Rivera", "service": "iMessage", "date": now_iso(-4), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
            {"guid": "g5", "text": "LFG", "is_from_me": False, "sender": "+15552468013", "sender_name": "Jake Rivera", "service": "iMessage", "date": now_iso(-3.5), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
        ],
        "+15559876543": [
            {"guid": "s1", "text": "Your appointment is confirmed for Tuesday at 2pm", "is_from_me": False, "sender": "+15559876543", "sender_name": "Dr. Smith Office", "service": "SMS", "date": now_iso(-48), "date_read": None, "has_attachments": False, "attachments": [], "tapback_type": 0, "tapback_target": None},
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
    print(f"Client connected ({len(clients)} total)")

    # Set timestamps relative to now
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
                history = make_history(chat_id)
                await websocket.send(json.dumps({
                    "type": "history",
                    "data": {"chat_id": chat_id, "messages": history}
                }))

            elif msg_type == "send":
                await websocket.send(json.dumps({
                    "type": "send_result",
                    "data": {"success": True, "recipient": data.get("chat_id")}
                }))

            elif msg_type == "get_tapbacks":
                await websocket.send(json.dumps({
                    "type": "tapbacks",
                    "data": {"chat_id": data.get("chat_id", ""), "tapbacks": {}}
                }))

            elif msg_type == "get_chat_members":
                members = []
                if data.get("chat_id") == "chat999demo":
                    members = [
                        {"identifier": "+15552468013", "display_name": "Jake Rivera", "service": "iMessage"},
                        {"identifier": "+15553691470", "display_name": "Sarah Kim", "service": "iMessage"},
                    ]
                await websocket.send(json.dumps({
                    "type": "chat_members",
                    "data": {"chat_id": data.get("chat_id", ""), "members": members}
                }))

            elif msg_type == "demo_inject":
                # Broadcast to all clients
                payload = json.dumps(data)
                for ws in clients:
                    try:
                        await ws.send(payload)
                    except websockets.exceptions.ConnectionClosed:
                        pass

            elif msg_type == "search":
                await websocket.send(json.dumps({
                    "type": "search_results",
                    "data": {"query": data.get("query", ""), "results": []}
                }))

            elif msg_type == "get_chat_attachments":
                await websocket.send(json.dumps({
                    "type": "chat_attachments",
                    "data": {
                        "chat_id": data.get("chat_id", ""),
                        "attachments": [
                            {"id": 10, "filename": "recipe.pdf", "mime_type": "application/pdf", "size": 245000,
                             "is_from_me": False, "sender": "Mom", "date": "2026-03-28T10:00:00+00:00", "path": "recipe.pdf"},
                            {"id": 11, "filename": "IMG_2847.heic", "mime_type": "image/heic", "size": 3200000,
                             "is_from_me": False, "sender": "Mom", "date": "2026-03-29T14:30:00+00:00", "path": "IMG_2847.heic"},
                            {"id": 12, "filename": "garden_video.mov", "mime_type": "video/quicktime", "size": 15400000,
                             "is_from_me": False, "sender": "Mom", "date": "2026-03-27T09:15:00+00:00", "path": "garden_video.mov"},
                            {"id": 13, "filename": "shopping_list.png", "mime_type": "image/png", "size": 890000,
                             "is_from_me": True, "sender": "me", "date": "2026-03-26T16:45:00+00:00", "path": "shopping_list.png"},
                        ],
                        "urls": [
                            {"url": "https://example.com/best-tomato-soup-recipe", "sender": "Mom", "date": "2026-03-29T15:00:00+00:00"},
                            {"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "sender": "Mom", "date": "2026-03-28T11:30:00+00:00"},
                            {"url": "https://amazon.com/dp/B09V3KXJPB", "sender": "me", "date": "2026-03-27T08:00:00+00:00"},
                        ],
                    }
                }))

            elif msg_type == "get_attachment_data":
                await websocket.send(json.dumps({
                    "type": "attachment_data",
                    "data": {"id": data.get("id"), "path": "", "content": None}
                }))

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"Client disconnected ({len(clients)} total)")


async def main():
    print(f"Mock JMessage Relay on ws://{WS_HOST}:{WS_PORT} (token: {AUTH_TOKEN})")
    print("No TLS, no real data. For demos only.")
    async with websockets.serve(handle_client, WS_HOST, WS_PORT, max_size=50 * 1024 * 1024):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
