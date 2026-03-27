# JMessage TUI Design Spec

## Overview

Replace the Electron+React client with a Python TUI built on Textual (Rich ecosystem). The Mac relay (`relay.py`) stays as-is — this is a client-only rewrite. The goal is a terminal-native iMessage client optimized for monitoring with fast keyboard-driven replies.

## Design Goals

- **Instant launch** — `python jmessage.py` and you're reading messages
- **Keyboard-only** — no mouse needed, vim-influenced navigation
- **Monitoring-first** — watch for incoming messages, reply when needed
- **Terminal-agnostic** — works in cmd, WezTerm, SSH sessions
- **Lean codebase** — minimal files, no abstractions beyond what Textual provides

## Technology

| Component | Choice |
|-----------|--------|
| Framework | Textual (Python TUI framework, built on Rich) |
| Transport | websockets (Python, same as relay) |
| Config | JSON file (`config.json`) — relay URL, auth token, cert paths |
| Python | 3.11+ |

## Architecture

```
jmessage.py          # Entry point + Textual App subclass, screen management, key bindings
├── screens/
│   ├── conversation.py   # Message view — shows chat history, input bar
│   └── conversation_list.py  # Esc overlay — conversation picker
├── client.py        # WebSocket client — async connect, send, receive, reconnect
└── config.json      # Relay URL, auth token, mTLS cert paths
```

**4 files total.** No utils, no helpers, no abstractions.

### Data Flow

1. `client.py` connects to Mac relay via WebSocket (mTLS)
2. Sends `auth` message with token
3. Requests `get_conversations` on connect
4. Relay pushes `message` events as they arrive in real-time
5. TUI updates conversation list and active chat view reactively
6. User sends via `send` message type, gets `send_result` back

### WebSocket Protocol (unchanged from relay)

**Client sends:**
- `{"type": "auth", "token": "..."}` — authenticate
- `{"type": "get_conversations"}` — fetch conversation list
- `{"type": "get_history", "data": {"chat_id": "...", "limit": 50}}` — fetch chat history
- `{"type": "send", "data": {"chat_id": "...", "text": "..."}}` — send message

**Server sends:**
- `{"type": "conversations", "data": [...]}` — conversation list
- `{"type": "history", "data": {"chat_id": "...", "messages": [...]}}` — chat history
- `{"type": "message", "data": {...}}` — new incoming message (real-time push)
- `{"type": "send_result", "data": {"success": true, "recipient": "..."}}` — send confirmation

## Screens

### Conversation View (main screen)

The default screen. Shows messages for the active conversation.

```
Mom  +1 (303) 555-0142              iMessage | Esc: conversations
─────────────────────────────────────────────────────────────────
                        ── Yesterday ──
Mom                                                      3:42 PM
Are you coming for dinner Sunday?
You                                                      3:45 PM
Yeah I'll be there around 6
Mom                                                      3:45 PM
Perfect! I'm making lasagna
                          ── Today ──
Mom                                                     11:20 AM
Can you pick up wine on the way?
You                                                     11:22 AM
Sure, red or white?
Delivered
─────────────────────────────────────────────────────────────────
> _                                   Enter: send | Ctrl+Enter: newline
```

**Layout:**
- **Header:** Contact name, phone/email, service type (iMessage/SMS), key hints
- **Message area:** Scrollable, dense line-by-line rendering
  - Your messages in cyan, theirs in default text color
  - Sender name + timestamp on one line, message text on next line
  - Date separators centered between message groups
  - Delivery status (Delivered, Read) below your last message
  - No bubbles — left-aligned colored text
- **Input bar:** `>` prompt, always at bottom

**Key bindings:**
- **Up/Down** — scroll through messages
- **Esc** — open conversation list
- **Start typing** — focus drops to input
- **Enter** — send message
- **Ctrl+Enter** — insert newline (multi-line compose)

### Conversation List (Esc overlay)

Summoned with Esc, replaces the conversation view temporarily.

```
Conversations                          /: search | Enter: open | Esc: back
─────────────────────────────────────────────────────────────────
> Mom          Can you pick up wine on the way?              11:20 AM
  Jake         dude check this out                [2]        10:45 AM
  Sarah        See you tomorrow!                           Yesterday
  Work Group   SMS  Meeting moved to 3pm                   Yesterday
  Dad          Thanks son                                    Mar 26
─────────────────────────────────────────────────────────────────
5 conversations | 2 unread
```

**Layout:**
- **Header:** Title + key hints
- **List:** One row per conversation — selection indicator, name, preview, unread badge, time
  - Selected row highlighted with background color + `>` indicator
  - Unread conversations show badge with count
  - SMS conversations show italic "SMS" tag
  - Sorted newest-first
- **Footer:** Conversation count + unread count

**Key bindings:**
- **Up/Down** — move selection
- **Enter** — open selected conversation (loads history, switches to conversation view)
- **/** — enter search/filter mode (type to narrow by name, Esc to clear filter)
- **Esc** — back to conversation view (if one was open)

### Empty State

On first launch before selecting a conversation:

```
JMessage                                              Esc: conversations
─────────────────────────────────────────────────────────────────

                    Press Esc to view conversations

─────────────────────────────────────────────────────────────────
```

## Notifications

- **In-place update:** When a new message arrives, the conversation list updates with the new preview and moves that conversation to the top. If that conversation is currently open, the new message appears at the bottom of the message view.
- **Terminal bell:** Ring the terminal bell (`\a`) when a new message arrives from someone else. This triggers a visual flash or sound depending on the terminal emulator.
- No external notification integration — the TUI is for reading/replying, not alerting.

## Connection Management

- Connect on startup, auto-reconnect on disconnect with exponential backoff
- Show connection status in header when disconnected: `[disconnected — retrying...]`
- mTLS using certs from `config.json` (same cert setup as existing Electron client)

## Configuration

`config.json` (same format as existing client):

```json
{
  "relay_url": "wss://192.168.1.40:8765",
  "auth_token": "your-secret-token",
  "certs": {
    "ca": "certs/ca.pem",
    "client_cert": "certs/client.pem",
    "client_key": "certs/client.key"
  }
}
```

## What's NOT in scope

- Media/attachments (images, video, audio) — text only
- Tapback reactions
- Group chat special handling
- Contact name resolution from AddressBook
- Emoji picker
- Message effects
- Read receipts / typing indicators
- MCP server integration
- Windows toast notifications
- System tray

## Testing

- E2E: Reuse existing `test-e2e.js` protocol tests to verify relay compatibility
- Manual: Test keyboard navigation, message display, send/receive flow
- Terminal compatibility: Verify in cmd, WezTerm, SSH (PuTTY/OpenSSH)
