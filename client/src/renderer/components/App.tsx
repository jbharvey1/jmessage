import React, { useState, useEffect, useRef, useCallback } from "react";

// --- Types ---
interface Conversation {
  chat_id: string;
  display_name: string;
  service: string;
  last_message: string | null;
  last_date: string | null;
}

interface Message {
  id: number;
  guid?: string;
  text: string | null;
  sender: string;
  is_from_me: boolean;
  service: string;
  date: string;
  date_read?: string | null;
  date_delivered?: string | null;
  tapback_type?: number;
  tapback_target?: string | null;
  has_attachments?: boolean;
  attachments?: any[];
  chat_id?: string;
  _optimistic?: boolean;
}

// --- WebSocket Hook (connects to local proxy in main process) ---
function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Record<string, Message[]>>({});
  const [unread, setUnread] = useState<Record<string, number>>({});
  const selectedChatRef = useRef<string | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket("ws://127.0.0.1:18765");
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data as string);

      if (data.type === "conversations") {
        setConversations(data.data);
        setConnected(true);
        authedRef.current = true;
      } else if (data.type === "history") {
        setMessages((prev) => ({
          ...prev,
          [data.data.chat_id]: data.data.messages.filter(
            (m: Message) => m.tapback_type === 0 || m.tapback_type === undefined
          ),
        }));
      } else if (data.type === "message") {
        const msg = data.data as Message;
        if (msg.tapback_type && msg.tapback_type !== 0) return;
        if (!msg.text && !msg.has_attachments) return;
        if (!msg.is_from_me && msg.chat_id !== selectedChatRef.current) {
          setUnread((prev) => ({
            ...prev,
            [msg.chat_id!]: (prev[msg.chat_id!] || 0) + 1,
          }));
        }
        setMessages((prev) => {
          const chatId = msg.chat_id!;
          const existing = prev[chatId] || [];
          if (msg.is_from_me) {
            const optIdx = existing.findIndex(
              (m) => m._optimistic && m.text === msg.text
            );
            if (optIdx !== -1) {
              const updated = [...existing];
              updated[optIdx] = msg;
              return { ...prev, [chatId]: updated };
            }
          }
          if (existing.find((m) => m.id === msg.id)) return prev;
          return { ...prev, [chatId]: [...existing, msg] };
        });
        setConversations((prev) => {
          const idx = prev.findIndex((c) => c.chat_id === msg.chat_id);
          if (idx === -1) return prev;
          const updated = [...prev];
          updated[idx] = {
            ...updated[idx],
            last_message: msg.text,
            last_date: msg.date,
          };
          updated.sort((a, b) => {
            if (!a.last_date) return 1;
            if (!b.last_date) return -1;
            return b.last_date.localeCompare(a.last_date);
          });
          return updated;
        });
      }
    };

    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 2000);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  const send = useCallback((msg: any) => {
    wsRef.current?.send(JSON.stringify(msg));
  }, []);

  const getHistory = useCallback(
    (chatId: string) => {
      send({ type: "get_history", data: { chat_id: chatId, limit: 100 } });
    },
    [send]
  );

  const sendMessage = useCallback(
    (chatId: string, text: string) => {
      const optimistic: Message = {
        id: -Date.now(),
        text,
        sender: "me",
        is_from_me: true,
        service: "iMessage",
        date: new Date().toISOString(),
        _optimistic: true,
      };
      setMessages((prev) => ({
        ...prev,
        [chatId]: [...(prev[chatId] || []), optimistic],
      }));
      setConversations((prev) => {
        const idx = prev.findIndex((c) => c.chat_id === chatId);
        if (idx === -1) return prev;
        const updated = [...prev];
        updated[idx] = { ...updated[idx], last_message: text, last_date: optimistic.date };
        updated.sort((a, b) => {
          if (!a.last_date) return 1;
          if (!b.last_date) return -1;
          return b.last_date.localeCompare(a.last_date);
        });
        return updated;
      });
      send({ type: "send", data: { chat_id: chatId, text } });
    },
    [send]
  );

  const clearUnread = useCallback((chatId: string) => {
    setUnread((prev) => {
      if (!prev[chatId]) return prev;
      const next = { ...prev };
      delete next[chatId];
      return next;
    });
  }, []);

  return { connected, conversations, messages, unread, clearUnread, selectedChatRef, getHistory, sendMessage };
}

// --- Helpers ---
function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString();
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDateSeparator(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return d.toLocaleDateString([], { weekday: "long" });
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function shouldShowDateSeparator(msgs: Message[], idx: number): boolean {
  if (idx === 0) return true;
  const prev = new Date(msgs[idx - 1].date).toDateString();
  const curr = new Date(msgs[idx].date).toDateString();
  return prev !== curr;
}

function shouldShowTimestamp(msgs: Message[], idx: number): boolean {
  if (idx === 0) return true;
  const prev = msgs[idx - 1];
  const curr = msgs[idx];
  const diff = new Date(curr.date).getTime() - new Date(prev.date).getTime();
  return diff > 300000 || prev.is_from_me !== curr.is_from_me; // 5 min gap or sender change
}

function isLastInGroup(msgs: Message[], idx: number): boolean {
  if (idx === msgs.length - 1) return true;
  const curr = msgs[idx];
  const next = msgs[idx + 1];
  return curr.is_from_me !== next.is_from_me ||
    new Date(next.date).getTime() - new Date(curr.date).getTime() > 60000;
}

function isFirstInGroup(msgs: Message[], idx: number): boolean {
  if (idx === 0) return true;
  const curr = msgs[idx];
  const prev = msgs[idx - 1];
  return curr.is_from_me !== prev.is_from_me ||
    new Date(curr.date).getTime() - new Date(prev.date).getTime() > 60000;
}

function getInitials(name: string): string {
  const parts = name.replace(/[+\d\s()-]/g, " ").trim().split(/\s+/);
  if (parts.length === 0 || parts[0] === "") return "#";
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function hashColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9"];
  return colors[Math.abs(hash) % colors.length];
}

// --- Components ---

function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        minWidth: size,
        borderRadius: "50%",
        background: hashColor(name),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size * 0.38,
        fontWeight: 600,
        color: "white",
      }}
    >
      {getInitials(name)}
    </div>
  );
}

function ConversationList({
  conversations,
  selected,
  onSelect,
  onNewMessage,
  unread,
}: {
  conversations: Conversation[];
  selected: string | null;
  onSelect: (id: string) => void;
  onNewMessage: () => void;
  unread: Record<string, number>;
}) {
  const [search, setSearch] = useState("");
  const filtered = search
    ? conversations.filter(
        (c) =>
          (c.display_name || c.chat_id).toLowerCase().includes(search.toLowerCase()) ||
          (c.last_message || "").toLowerCase().includes(search.toLowerCase())
      )
    : conversations;

  return (
    <div
      style={{
        width: 340,
        minWidth: 340,
        background: "var(--sidebar-bg)",
        borderRight: "1px solid var(--separator)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 16px 8px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontSize: 24, fontWeight: 700 }}>Messages</span>
        <button
          onClick={onNewMessage}
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            border: "none",
            background: "var(--bubble-sent-imessage)",
            color: "white",
            fontSize: 18,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          title="New Message"
        >
          ✎
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: "4px 16px 10px" }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search"
          style={{
            width: "100%",
            background: "var(--input-bg)",
            border: "none",
            borderRadius: 10,
            padding: "8px 12px",
            color: "white",
            fontSize: 14,
            outline: "none",
          }}
        />
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.map((c) => {
          const isSelected = selected === c.chat_id;
          return (
            <div
              key={c.chat_id}
              onClick={() => onSelect(c.chat_id)}
              style={{
                padding: "10px 16px",
                cursor: "pointer",
                background: isSelected ? "var(--bubble-sent-imessage)" : "transparent",
                display: "flex",
                gap: 12,
                alignItems: "center",
                transition: "background 0.12s",
              }}
              onMouseEnter={(e) => {
                if (!isSelected) (e.currentTarget.style.background = "rgba(255,255,255,0.05)");
              }}
              onMouseLeave={(e) => {
                if (!isSelected) (e.currentTarget.style.background = "transparent");
              }}
            >
              <Avatar name={c.display_name || c.chat_id} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontWeight: unread[c.chat_id] ? 700 : 600, fontSize: 15 }}>
                    {c.display_name || c.chat_id}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0, marginLeft: 8 }}>
                    <span
                      style={{
                        fontSize: 12,
                        color: isSelected ? "rgba(255,255,255,0.7)" : unread[c.chat_id] ? "var(--bubble-sent-imessage)" : "var(--text-secondary)",
                      }}
                    >
                      {relativeTime(c.last_date)}
                    </span>
                    {unread[c.chat_id] && !isSelected ? (
                      <div
                        style={{
                          background: "var(--bubble-sent-imessage)",
                          color: "white",
                          borderRadius: 10,
                          minWidth: 20,
                          height: 20,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 12,
                          fontWeight: 700,
                          padding: "0 6px",
                        }}
                      >
                        {unread[c.chat_id]}
                      </div>
                    ) : null}
                  </div>
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: isSelected ? "rgba(255,255,255,0.7)" : unread[c.chat_id] ? "var(--text-primary)" : "var(--text-secondary)",
                    fontWeight: unread[c.chat_id] ? 500 : 400,
                    marginTop: 2,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {c.last_message || ""}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MessageBubble({
  msg,
  isFirst,
  isLast,
  showTime,
  msgs,
  idx,
}: {
  msg: Message;
  isFirst: boolean;
  isLast: boolean;
  showTime: boolean;
  msgs: Message[];
  idx: number;
}) {
  const isMe = msg.is_from_me;
  const isIMSG = (msg.service || "").toLowerCase().includes("imessage");
  const bubbleColor = isMe
    ? isIMSG
      ? "var(--bubble-sent-imessage)"
      : "var(--bubble-sent-sms)"
    : "var(--bubble-received)";

  // Large emoji mode
  const emojiOnly =
    msg.text &&
    /^[\p{Emoji_Presentation}\p{Extended_Pictographic}\s\u{FE0F}\u{200D}]{1,11}$/u.test(msg.text) &&
    !/[a-zA-Z0-9]/.test(msg.text) &&
    [...msg.text.replace(/[\s\u{FE0F}\u{200D}]/gu, "")].length <= 3;

  // Bubble corner radii for grouping
  const r = 18;
  const s = 6; // small radius for grouped side
  let borderRadius: string;
  if (isMe) {
    borderRadius = isFirst && isLast
      ? `${r}px`
      : isFirst
      ? `${r}px ${r}px ${s}px ${r}px`
      : isLast
      ? `${r}px ${s}px ${r}px ${r}px`
      : `${r}px ${s}px ${s}px ${r}px`;
  } else {
    borderRadius = isFirst && isLast
      ? `${r}px`
      : isFirst
      ? `${r}px ${r}px ${r}px ${s}px`
      : isLast
      ? `${s}px ${r}px ${r}px ${r}px`
      : `${s}px ${r}px ${r}px ${s}px`;
  }

  const showDateSep = shouldShowDateSeparator(msgs, idx);

  return (
    <>
      {showDateSep && (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-secondary)",
            fontSize: 12,
            fontWeight: 600,
            padding: "16px 0 8px",
          }}
        >
          {formatDateSeparator(msg.date)}
        </div>
      )}
      {showTime && !showDateSep && (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-secondary)",
            fontSize: 11,
            padding: "8px 0 4px",
          }}
        >
          {formatTime(msg.date)}
        </div>
      )}
      <div
        style={{
          display: "flex",
          justifyContent: isMe ? "flex-end" : "flex-start",
          padding: `${isFirst ? 6 : 1}px 16px ${isLast ? 6 : 1}px`,
        }}
      >
        {emojiOnly ? (
          <div style={{ fontSize: 48, lineHeight: 1.2, padding: "2px 0" }}>{msg.text}</div>
        ) : (
          <div
            style={{
              background: bubbleColor,
              color: isMe ? "white" : "var(--text-primary)",
              padding: "8px 14px",
              borderRadius,
              maxWidth: "65%",
              fontSize: 16,
              lineHeight: 1.35,
              wordBreak: "break-word",
              opacity: msg._optimistic ? 0.7 : 1,
            }}
          >
            {msg.text || (msg.has_attachments ? "📎 Attachment" : "")}
          </div>
        )}
      </div>
      {isLast && isMe && !msg._optimistic && (
        <div
          style={{
            textAlign: "right",
            paddingRight: 18,
            fontSize: 11,
            color: "var(--text-secondary)",
            paddingBottom: 4,
          }}
        >
          {msg.date_read
            ? `Read ${formatTime(msg.date_read)}`
            : msg.date_delivered
            ? "Delivered"
            : ""}
        </div>
      )}
    </>
  );
}

function ChatView({
  chatId,
  chatName,
  messages,
  onSend,
}: {
  chatId: string;
  chatName: string;
  messages: Message[];
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const prevChatRef = useRef(chatId);
  useEffect(() => {
    if (chatId !== prevChatRef.current) {
      // New conversation selected — jump instantly, no animation
      bottomRef.current?.scrollIntoView();
      prevChatRef.current = chatId;
    } else {
      // Same conversation, new message — smooth scroll
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, chatId]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [chatId]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    onSend(text);
    setInput("");
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--separator)",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <Avatar name={chatName || chatId} size={34} />
        <span style={{ fontWeight: 600, fontSize: 16 }}>{chatName || chatId}</span>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {messages.map((msg, idx) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            isFirst={isFirstInGroup(messages, idx)}
            isLast={isLastInGroup(messages, idx)}
            showTime={shouldShowTimestamp(messages, idx)}
            msgs={messages}
            idx={idx}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div
        style={{
          padding: "10px 16px 14px",
          borderTop: "1px solid var(--separator)",
          display: "flex",
          gap: 10,
          alignItems: "flex-end",
        }}
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="iMessage"
          style={{
            flex: 1,
            background: "var(--input-bg)",
            border: "1px solid var(--separator)",
            borderRadius: 20,
            padding: "10px 16px",
            color: "white",
            fontSize: 15,
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim()}
          style={{
            width: 34,
            height: 34,
            borderRadius: "50%",
            border: "none",
            background: input.trim() ? "var(--bubble-sent-imessage)" : "var(--separator)",
            color: "white",
            fontSize: 16,
            fontWeight: 700,
            cursor: input.trim() ? "pointer" : "default",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "background 0.15s",
          }}
        >
          ↑
        </button>
      </div>
    </div>
  );
}

function NewMessageView({
  onSend,
  onCancel,
}: {
  onSend: (recipient: string, text: string) => void;
  onCancel: () => void;
}) {
  const [recipient, setRecipient] = useState("");
  const [text, setText] = useState("");
  const recipientRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    recipientRef.current?.focus();
  }, []);

  const handleSend = () => {
    const r = recipient.trim();
    const t = text.trim();
    if (!r || !t) return;
    onSend(r, t);
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          padding: "14px 20px",
          borderBottom: "1px solid var(--separator)",
          fontWeight: 600,
          fontSize: 17,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        New Message
        <button
          onClick={onCancel}
          style={{
            background: "none",
            border: "none",
            color: "var(--bubble-sent-imessage)",
            fontSize: 14,
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          Cancel
        </button>
      </div>
      <div
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--separator)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span style={{ color: "var(--text-secondary)", fontSize: 15 }}>To:</span>
        <input
          ref={recipientRef}
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
          placeholder="+1 (555) 123-4567"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            color: "white",
            fontSize: 15,
            outline: "none",
          }}
        />
      </div>
      <div style={{ flex: 1 }} />
      <div
        style={{
          padding: "10px 16px 14px",
          borderTop: "1px solid var(--separator)",
          display: "flex",
          gap: 10,
          alignItems: "flex-end",
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="iMessage"
          style={{
            flex: 1,
            background: "var(--input-bg)",
            border: "1px solid var(--separator)",
            borderRadius: 20,
            padding: "10px 16px",
            color: "white",
            fontSize: 15,
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          disabled={!recipient.trim() || !text.trim()}
          style={{
            width: 34,
            height: 34,
            borderRadius: "50%",
            border: "none",
            background:
              recipient.trim() && text.trim()
                ? "var(--bubble-sent-imessage)"
                : "var(--separator)",
            color: "white",
            fontSize: 16,
            fontWeight: 700,
            cursor: recipient.trim() && text.trim() ? "pointer" : "default",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          ↑
        </button>
      </div>
    </div>
  );
}

function EmptyState({ connected }: { connected: boolean }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--text-secondary)",
        gap: 8,
      }}
    >
      <div style={{ fontSize: 48, opacity: 0.3 }}>💬</div>
      <div style={{ fontSize: 18, fontWeight: 500 }}>
        {connected ? "Select a conversation" : "Connecting..."}
      </div>
      {!connected && (
        <div style={{ fontSize: 13 }}>Looking for Mac relay at {WS_URL}</div>
      )}
    </div>
  );
}

// --- App ---
export function App() {
  const { connected, conversations, messages, unread, clearUnread, selectedChatRef, getHistory, sendMessage } =
    useWebSocket();
  const [selectedChat, setSelectedChat] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);

  const handleSelect = (chatId: string) => {
    setSelectedChat(chatId);
    selectedChatRef.current = chatId;
    clearUnread(chatId);
    setComposing(false);
    if (!messages[chatId]) {
      getHistory(chatId);
    }
  };

  const handleNewMessage = () => {
    setComposing(true);
    setSelectedChat(null);
  };

  const handleComposeSend = (recipient: string, text: string) => {
    sendMessage(recipient, text);
    setComposing(false);
    setSelectedChat(recipient);
    setTimeout(() => getHistory(recipient), 2000);
  };

  const selectedConvo = conversations.find((c) => c.chat_id === selectedChat);
  const chatMessages = selectedChat ? messages[selectedChat] || [] : [];

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <ConversationList
        conversations={conversations}
        selected={selectedChat}
        onSelect={handleSelect}
        onNewMessage={handleNewMessage}
        unread={unread}
      />
      {composing ? (
        <NewMessageView
          onSend={handleComposeSend}
          onCancel={() => setComposing(false)}
        />
      ) : selectedChat ? (
        <ChatView
          chatId={selectedChat}
          chatName={selectedConvo?.display_name || selectedChat}
          messages={chatMessages}
          onSend={(text) => sendMessage(selectedChat, text)}
        />
      ) : (
        <EmptyState connected={connected} />
      )}
    </div>
  );
}
