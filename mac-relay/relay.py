"""
JMessage Mac Relay — Phase 1
Watches chat.db for new messages, serves them over WebSocket,
accepts send commands via AppleScript.
"""

import asyncio
import base64
import json
import logging
import os
import sqlite3
import ssl
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import websockets

# --- Config ---
CHAT_DB = os.path.expanduser("~/Library/Messages/chat.db")
POLL_INTERVAL = 1.5  # seconds
WS_HOST = "0.0.0.0"
WS_PORT = 8765
AUTH_TOKEN = os.environ.get("JMESSAGE_TOKEN")
if not AUTH_TOKEN:
    raise RuntimeError("JMESSAGE_TOKEN environment variable must be set")
APPLE_EPOCH_OFFSET = 978307200  # seconds between Unix epoch and Apple epoch (2001-01-01)
CERT_DIR = os.path.dirname(os.path.abspath(__file__))
CERTS_DIR = os.path.join(CERT_DIR, "certs")
SSL_CERT = os.path.join(CERTS_DIR, "server.pem")
SSL_KEY = os.path.join(CERTS_DIR, "server.key")
SSL_CA = os.path.join(CERTS_DIR, "ca.pem")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.expanduser("~/jmessage-relay/logs/relay.log")),
    ],
)
log = logging.getLogger("jmessage")

# --- Contact Name Cache ---
_contact_cache: dict[str, str] = {}


import re

ADDRESSBOOK_DB = os.path.expanduser(
    "~/Library/Application Support/AddressBook/AddressBook-v22.abcddb"
)

_contacts_loaded = False


def _load_contacts_from_db():
    """Load all contacts from the AddressBook SQLite database.
    Maps phone numbers and emails to display names."""
    global _contacts_loaded
    if _contacts_loaded:
        return
    _contacts_loaded = True

    if not os.path.exists(ADDRESSBOOK_DB):
        log.warning(f"AddressBook not found at {ADDRESSBOOK_DB}")
        return

    try:
        db = sqlite3.connect(f"file:{ADDRESSBOOK_DB}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row

        # Phone numbers
        for r in db.execute("""
            SELECT r.ZFIRSTNAME, r.ZLASTNAME, p.ZFULLNUMBER
            FROM ZABCDRECORD r
            JOIN ZABCDPHONENUMBER p ON p.ZOWNER = r.Z_PK
            WHERE (r.ZFIRSTNAME IS NOT NULL OR r.ZLASTNAME IS NOT NULL)
              AND p.ZFULLNUMBER IS NOT NULL
        """).fetchall():
            name = f"{r['ZFIRSTNAME'] or ''} {r['ZLASTNAME'] or ''}".strip()
            if not name:
                continue
            phone = r["ZFULLNUMBER"]
            _contact_cache[phone] = name
            # Also store digits-only for flexible matching
            digits = re.sub(r'[^\d]', '', phone)
            if len(digits) >= 7:
                _contact_cache[digits] = name
                if len(digits) == 10:
                    _contact_cache[f"+1{digits}"] = name
                if len(digits) == 11 and digits.startswith("1"):
                    _contact_cache[f"+{digits}"] = name

        # Emails
        for r in db.execute("""
            SELECT r.ZFIRSTNAME, r.ZLASTNAME, e.ZADDRESS
            FROM ZABCDRECORD r
            JOIN ZABCDEMAILADDRESS e ON e.ZOWNER = r.Z_PK
            WHERE (r.ZFIRSTNAME IS NOT NULL OR r.ZLASTNAME IS NOT NULL)
              AND e.ZADDRESS IS NOT NULL
        """).fetchall():
            name = f"{r['ZFIRSTNAME'] or ''} {r['ZLASTNAME'] or ''}".strip()
            if name:
                _contact_cache[r["ZADDRESS"].lower()] = name

        db.close()
        log.info(f"Loaded {len(_contact_cache)} contact mappings from AddressBook")
    except Exception as e:
        log.warning(f"Failed to load contacts: {e}")


def _strip_sms_suffix(identifier: str) -> str:
    """Strip (smsft), (smsfp), etc. from chat identifiers."""
    return re.sub(r'\(sms\w*\)', '', identifier).strip()


def resolve_contact_name(identifier: str) -> str:
    """Look up a contact name for a phone number or email.
    Uses AddressBook SQLite cache."""
    if not identifier or identifier == "me":
        return ""
    _load_contacts_from_db()
    # Direct cache hit
    if identifier in _contact_cache:
        return _contact_cache[identifier]
    # Strip SMS suffixes like (smsft), (smsfp)
    cleaned = _strip_sms_suffix(identifier)
    if cleaned != identifier and cleaned in _contact_cache:
        _contact_cache[identifier] = _contact_cache[cleaned]
        return _contact_cache[cleaned]
    # Try lowercase (email)
    lower = cleaned.lower()
    if lower in _contact_cache:
        _contact_cache[identifier] = _contact_cache[lower]
        return _contact_cache[lower]
    # Try digits-only match (phone)
    digits = re.sub(r'[^\d]', '', cleaned)
    if len(digits) >= 7 and digits in _contact_cache:
        _contact_cache[identifier] = _contact_cache[digits]
        return _contact_cache[digits]
    # Not found
    _contact_cache[identifier] = ""
    return ""


# --- Clients ---
clients: set = set()


def apple_date_to_iso(apple_ns: int) -> str:
    """Convert Apple nanosecond timestamp to ISO 8601 string."""
    if apple_ns is None or apple_ns == 0:
        return None
    unix_ts = (apple_ns / 1_000_000_000) + APPLE_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()


def get_db():
    """Open a read-only connection to chat.db."""
    db = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def get_max_rowid() -> int:
    """Get current max message ROWID."""
    db = get_db()
    try:
        row = db.execute("SELECT MAX(ROWID) FROM message").fetchone()
        return row[0] or 0
    finally:
        db.close()


def fetch_messages_since(last_rowid: int) -> list:
    """Fetch all messages with ROWID > last_rowid."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT m.ROWID as id, m.guid, m.text, m.is_from_me, m.service,
                   m.date, m.date_read, m.date_delivered,
                   m.cache_has_attachments, m.associated_message_type,
                   m.associated_message_guid, m.expressive_send_style_id,
                   h.id as sender, h.service as sender_service,
                   c.ROWID as chat_rowid, c.chat_identifier, c.display_name,
                   c.service_name as chat_service
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            LEFT JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE m.ROWID > ?
            ORDER BY m.ROWID ASC
            """,
            (last_rowid,),
        ).fetchall()

        messages = []
        for r in rows:
            msg = {
                "type": "message",
                "data": {
                    "id": r["id"],
                    "guid": r["guid"],
                    "text": r["text"],
                    "sender": r["sender"] if not r["is_from_me"] else "me",
                    "sender_name": resolve_contact_name(r["sender"]) if not r["is_from_me"] else "",
                    "is_from_me": bool(r["is_from_me"]),
                    "service": r["service"] or "iMessage",
                    "chat_id": r["chat_identifier"],
                    "chat_name": r["display_name"] or resolve_contact_name(r["chat_identifier"]) or "",
                    "date": apple_date_to_iso(r["date"]),
                    "date_read": apple_date_to_iso(r["date_read"]),
                    "date_delivered": apple_date_to_iso(r["date_delivered"]),
                    "has_attachments": bool(r["cache_has_attachments"]),
                    "tapback_type": r["associated_message_type"],
                    "tapback_target": r["associated_message_guid"],
                    "expressive_style": r["expressive_send_style_id"],
                    "attachments": [],
                },
            }

            # Fetch attachments if present
            if r["cache_has_attachments"]:
                atts = db.execute(
                    """
                    SELECT a.ROWID as att_id, a.filename, a.mime_type,
                           a.transfer_name, a.total_bytes
                    FROM attachment a
                    JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
                    WHERE maj.message_id = ?
                    """,
                    (r["id"],),
                ).fetchall()
                for a in atts:
                    msg["data"]["attachments"].append(
                        {
                            "id": a["att_id"],
                            "filename": a["transfer_name"] or os.path.basename(a["filename"] or ""),
                            "mime_type": a["mime_type"],
                            "size": a["total_bytes"],
                            "path": os.path.basename(a["filename"] or ""),
                        }
                    )

            messages.append(msg)
        return messages
    finally:
        db.close()


def fetch_conversations() -> list:
    """Fetch all conversations with latest message info."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT c.ROWID, c.chat_identifier, c.display_name, c.service_name,
                   MAX(m.date) as last_date,
                   (SELECT m2.text FROM message m2
                    JOIN chat_message_join cmj2 ON m2.ROWID = cmj2.message_id
                    WHERE cmj2.chat_id = c.ROWID
                    ORDER BY m2.date DESC LIMIT 1) as last_text
            FROM chat c
            LEFT JOIN chat_message_join cmj ON c.ROWID = cmj.chat_id
            LEFT JOIN message m ON cmj.message_id = m.ROWID
            GROUP BY c.ROWID
            ORDER BY last_date DESC
            LIMIT 50
            """,
        ).fetchall()

        convos = []
        for r in rows:
            chat_id = r["chat_identifier"]
            name = r["display_name"] or resolve_contact_name(chat_id) or ""
            convos.append({
                "chat_id": chat_id,
                "display_name": name,
                "service": r["service_name"] or "iMessage",
                "last_message": r["last_text"],
                "last_date": apple_date_to_iso(r["last_date"]),
            })
        return convos
    finally:
        db.close()


def fetch_chat_history(chat_identifier: str, limit: int = 50) -> list:
    """Fetch message history for a specific chat."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT m.ROWID as id, m.guid, m.text, m.is_from_me, m.service,
                   m.date, m.date_read, m.date_delivered,
                   m.cache_has_attachments, m.associated_message_type,
                   m.associated_message_guid, m.expressive_send_style_id,
                   h.id as sender
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE c.chat_identifier = ?
              AND ((m.text IS NOT NULL AND m.text != '') OR m.cache_has_attachments = 1)
              AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
            ORDER BY m.date DESC
            LIMIT ?
            """,
            (chat_identifier, limit),
        ).fetchall()

        messages = []
        for r in rows:
            msg = {
                "id": r["id"],
                "guid": r["guid"],
                "text": r["text"],
                "sender": r["sender"] if not r["is_from_me"] else "me",
                "sender_name": resolve_contact_name(r["sender"]) if not r["is_from_me"] else "",
                "is_from_me": bool(r["is_from_me"]),
                "service": r["service"] or "iMessage",
                "date": apple_date_to_iso(r["date"]),
                "date_read": apple_date_to_iso(r["date_read"]),
                "tapback_type": r["associated_message_type"],
                "tapback_target": r["associated_message_guid"],
                "has_attachments": bool(r["cache_has_attachments"]),
                "attachments": [],
            }
            if r["cache_has_attachments"]:
                atts = db.execute(
                    """
                    SELECT a.ROWID as att_id, a.filename, a.mime_type,
                           a.transfer_name, a.total_bytes
                    FROM attachment a
                    JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
                    WHERE maj.message_id = ?
                    """,
                    (r["id"],),
                ).fetchall()
                for a in atts:
                    msg["attachments"].append(
                        {
                            "id": a["att_id"],
                            "filename": a["transfer_name"] or "",
                            "mime_type": a["mime_type"],
                            "size": a["total_bytes"],
                        }
                    )
            messages.append(msg)

        messages.reverse()  # oldest first
        return messages
    finally:
        db.close()


def send_imessage(recipient: str, text: str) -> dict:
    """Send a message via AppleScript. Uses 'on run' args to avoid injection."""
    script = (
        'on run {targetRecipient, messageText}\n'
        '    tell application "Messages"\n'
        '        set targetService to 1st account whose service type = iMessage\n'
        '        set targetBuddy to participant targetRecipient of targetService\n'
        '        send messageText to targetBuddy\n'
        '    end tell\n'
        'end run'
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", script, recipient, text],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            log.info(f"Sent message to {recipient}")
            return {"type": "send_result", "data": {"success": True, "recipient": recipient}}
        else:
            log.error(f"AppleScript error: {result.stderr}")
            return {"type": "send_result", "data": {"success": False, "error": "Failed to send message"}}
    except Exception as e:
        log.error(f"Send failed: {e}")
        return {"type": "send_result", "data": {"success": False, "error": "Failed to send message"}}


def fetch_chat_members(chat_identifier: str) -> list:
    """Fetch members of a chat (for group chats)."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT h.id as identifier, h.service
            FROM handle h
            JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
            JOIN chat c ON chj.chat_id = c.ROWID
            WHERE c.chat_identifier = ?
            """,
            (chat_identifier,),
        ).fetchall()
        members = []
        for r in rows:
            ident = r["identifier"]
            name = resolve_contact_name(ident)
            members.append({
                "identifier": ident,
                "display_name": name,
                "service": r["service"] or "iMessage",
            })
        return members
    finally:
        db.close()


def fetch_typing_status() -> list:
    """Check for active typing indicators in chat.db."""
    db = get_db()
    try:
        # The chat_typing table exists in newer macOS versions
        try:
            rows = db.execute(
                """
                SELECT c.chat_identifier, h.id as sender
                FROM chat_message_join cmj
                JOIN chat c ON cmj.chat_id = c.ROWID
                JOIN message m ON cmj.message_id = m.ROWID
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.is_from_me = 0
                ORDER BY m.date DESC
                LIMIT 1
                """
            ).fetchall()
        except Exception:
            return []
        return []  # Typing detection via chat.db is unreliable — see note below
    finally:
        db.close()


def search_messages(query: str, limit: int = 50) -> list:
    """Search messages across all chats."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT m.ROWID as id, m.text, m.is_from_me, m.date, m.service,
                   h.id as sender, c.chat_identifier, c.display_name
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE m.text LIKE ?
              AND m.text IS NOT NULL
              AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
            ORDER BY m.date DESC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        ).fetchall()

        results = []
        for r in rows:
            chat_id = r["chat_identifier"]
            sender_id = r["sender"]
            results.append({
                "id": r["id"],
                "text": r["text"],
                "is_from_me": bool(r["is_from_me"]),
                "sender": resolve_contact_name(sender_id) or sender_id if not r["is_from_me"] else "me",
                "date": apple_date_to_iso(r["date"]),
                "service": r["service"] or "iMessage",
                "chat_id": chat_id,
                "chat_name": r["display_name"] or resolve_contact_name(chat_id) or chat_id,
            })
        return results
    finally:
        db.close()


def fetch_tapbacks_for_chat(chat_identifier: str, limit: int = 200) -> list:
    """Fetch tapback reactions for messages in a chat."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT m.associated_message_guid, m.associated_message_type,
                   m.is_from_me, h.id as sender
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE c.chat_identifier = ?
              AND m.associated_message_type IS NOT NULL
              AND m.associated_message_type != 0
            ORDER BY m.date DESC
            LIMIT ?
            """,
            (chat_identifier, limit),
        ).fetchall()

        # Tapback types: 2000=love, 2001=like, 2002=dislike, 2003=laugh, 2004=emphasis, 2005=question
        # Remove types: 3000-3005
        tapback_emoji = {
            2000: "❤️", 2001: "👍", 2002: "👎", 2003: "😂", 2004: "‼️", 2005: "❓",
            3000: None, 3001: None, 3002: None, 3003: None, 3004: None, 3005: None,
        }
        tapbacks = {}
        for r in rows:
            target = r["associated_message_guid"]
            tt = r["associated_message_type"]
            emoji = tapback_emoji.get(tt)
            if emoji is None:
                continue
            sender = resolve_contact_name(r["sender"]) or r["sender"] if not r["is_from_me"] else "You"
            if target not in tapbacks:
                tapbacks[target] = []
            tapbacks[target].append({"emoji": emoji, "sender": sender})
        return tapbacks
    finally:
        db.close()


def fetch_chat_attachments(chat_identifier: str) -> list:
    """Fetch all attachments for a chat with full file paths."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT a.ROWID as att_id, a.filename, a.mime_type,
                   a.transfer_name, a.total_bytes, m.is_from_me,
                   m.date, h.id as sender
            FROM attachment a
            JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
            JOIN message m ON maj.message_id = m.ROWID
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE c.chat_identifier = ?
            ORDER BY m.date DESC
            """,
            (chat_identifier,),
        ).fetchall()

        return [
            {
                "id": r["att_id"],
                "filename": r["transfer_name"] or os.path.basename(r["filename"] or ""),
                "mime_type": r["mime_type"],
                "size": r["total_bytes"],
                "path": r["filename"],  # full path kept server-side for reading
                "is_from_me": bool(r["is_from_me"]),
                "sender": resolve_contact_name(r["sender"]) or r["sender"] if not r["is_from_me"] else "me",
                "date": apple_date_to_iso(r["date"]),
            }
            for r in rows
        ]
    finally:
        db.close()


def fetch_chat_urls(chat_identifier: str) -> list:
    """Extract all URLs from messages in a chat."""
    import re
    url_re = re.compile(r'https?://[^\s<>"\')\]]+')
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT m.text, m.date, m.is_from_me, h.id as sender
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE c.chat_identifier = ?
              AND m.text LIKE '%http%'
            ORDER BY m.date DESC
            """,
            (chat_identifier,),
        ).fetchall()

        urls = []
        for r in rows:
            for url in url_re.findall(r["text"] or ""):
                urls.append({
                    "url": url,
                    "sender": resolve_contact_name(r["sender"]) or r["sender"] if not r["is_from_me"] else "me",
                    "date": apple_date_to_iso(r["date"]),
                })
        return urls
    finally:
        db.close()


def read_attachment_file(att_path: str):
    """Read an attachment file and return base64-encoded content."""
    if not att_path:
        return None
    expanded = os.path.expanduser(att_path)
    if not os.path.exists(expanded):
        return None
    try:
        with open(expanded, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        log.warning(f"Failed to read attachment {att_path}: {e}")
        return None


# --- WebSocket ---

async def broadcast(message: dict):
    """Send a message to all connected clients."""
    global clients
    if not clients:
        return
    payload = json.dumps(message)
    dead = set()
    for ws in clients:
        try:
            await ws.send(payload)
        except websockets.exceptions.ConnectionClosed:
            dead.add(ws)
    if dead:
        clients -= dead


async def handle_client(websocket):
    """Handle a WebSocket client connection."""
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
    log.info(f"Client connected ({len(clients)} total)")

    # Send conversation list on connect
    convos = fetch_conversations()
    await websocket.send(json.dumps({"type": "conversations", "data": convos}))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                data = msg.get("data", {})
            except (json.JSONDecodeError, AttributeError):
                continue

            try:
                if msg_type == "send":
                    recipient = data.get("chat_id")
                    text = data.get("text")
                    if not recipient or not text:
                        continue
                    result = send_imessage(recipient, text)
                    await websocket.send(json.dumps(result))

                elif msg_type == "get_history":
                    chat_id = data.get("chat_id")
                    if not chat_id:
                        continue
                    limit = min(int(data.get("limit", 50)), 200)
                    history = fetch_chat_history(chat_id, limit)
                    await websocket.send(
                        json.dumps({"type": "history", "data": {"chat_id": chat_id, "messages": history}})
                    )

                elif msg_type == "get_conversations":
                    convos = fetch_conversations()
                    await websocket.send(json.dumps({"type": "conversations", "data": convos}))

                elif msg_type == "get_chat_members":
                    chat_id = data.get("chat_id")
                    if not chat_id:
                        continue
                    members = fetch_chat_members(chat_id)
                    await websocket.send(json.dumps({
                        "type": "chat_members",
                        "data": {"chat_id": chat_id, "members": members}
                    }))

                elif msg_type == "search":
                    query = data.get("query", "").strip()
                    if not query:
                        continue
                    limit = min(int(data.get("limit", 50)), 100)
                    results = search_messages(query, limit)
                    await websocket.send(json.dumps({
                        "type": "search_results",
                        "data": {"query": query, "results": results}
                    }))

                elif msg_type == "get_tapbacks":
                    chat_id = data.get("chat_id")
                    if not chat_id:
                        continue
                    tapbacks = fetch_tapbacks_for_chat(chat_id)
                    await websocket.send(json.dumps({
                        "type": "tapbacks",
                        "data": {"chat_id": chat_id, "tapbacks": tapbacks}
                    }))

                elif msg_type == "demo_inject":
                    # Broadcast a fake message to all clients (for demo/testing)
                    await broadcast(data)

                elif msg_type == "get_chat_attachments":
                    chat_id = data.get("chat_id")
                    if not chat_id:
                        continue
                    attachments = fetch_chat_attachments(chat_id)
                    urls = fetch_chat_urls(chat_id)
                    await websocket.send(json.dumps({
                        "type": "chat_attachments",
                        "data": {"chat_id": chat_id, "attachments": attachments, "urls": urls}
                    }))

                elif msg_type == "get_attachment_data":
                    att_path = data.get("path")
                    att_id = data.get("id")
                    if not att_path:
                        continue
                    content = read_attachment_file(att_path)
                    await websocket.send(json.dumps({
                        "type": "attachment_data",
                        "data": {"id": att_id, "path": att_path, "content": content}
                    }))

            except (KeyError, TypeError, ValueError) as e:
                log.warning(f"Invalid message from client: {e}")
                continue

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        log.info(f"Client disconnected ({len(clients)} total)")


async def poll_new_messages():
    """Poll chat.db for new messages and broadcast them."""
    last_rowid = get_max_rowid()
    log.info(f"Starting poll from ROWID {last_rowid}")

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            messages = fetch_messages_since(last_rowid)
            for msg in messages:
                last_rowid = max(last_rowid, msg["data"]["id"])
                tt = msg["data"].get("tapback_type") or 0
                has_text = bool(msg["data"].get("text"))
                has_att = bool(msg["data"].get("has_attachments"))

                if tt != 0:
                    # Broadcast tapbacks as their own type
                    tapback_emoji = {
                        2000: "❤️", 2001: "👍", 2002: "👎", 2003: "😂", 2004: "‼️", 2005: "❓",
                    }
                    emoji = tapback_emoji.get(tt)
                    if emoji:
                        msg["type"] = "tapback"
                        msg["data"]["emoji"] = emoji
                        await broadcast(msg)
                    continue

                if not has_text and not has_att:
                    continue
                await broadcast(msg)
                sender = msg["data"]["sender"]
                log.info(f"New: [{msg['data']['service']}] {sender}")
        except Exception as e:
            log.error(f"Poll error: {e}")


async def main():
    if not os.path.exists(SSL_CERT) or not os.path.exists(SSL_KEY):
        raise RuntimeError(f"TLS certs required: {SSL_CERT} and {SSL_KEY} must exist")

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(SSL_CERT, SSL_KEY)
    if os.path.exists(SSL_CA):
        ssl_ctx.load_verify_locations(SSL_CA)
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        log.info(f"JMessage Relay starting on wss://{WS_HOST}:{WS_PORT} (mTLS)")
    else:
        log.info(f"JMessage Relay starting on wss://{WS_HOST}:{WS_PORT} (TLS)")
    log.info(f"Watching {CHAT_DB}")

    async with websockets.serve(handle_client, WS_HOST, WS_PORT, ssl=ssl_ctx, max_size=50 * 1024 * 1024):
        await poll_new_messages()


if __name__ == "__main__":
    asyncio.run(main())
