import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import {
  getConversationId,
  sendMessage,
  streamMessages,
  type ChatEntry,
  type WidgetConfig,
} from "./api";
import "./style.css";

const LAUNCHER_ICON = "💬";

export function ChatWidget({ config }: { config: WidgetConfig }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, open]);

  const subscribe = (conversationId: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    (async () => {
      try {
        for await (const entry of streamMessages(config, conversationId, controller.signal)) {
          setMessages((prev) =>
            prev.some((m) => m.id === entry.id) ? prev : [...prev, entry],
          );
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
  };

  useEffect(() => {
    const existing = getConversationId();
    if (existing) subscribe(existing);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const send = async () => {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    const optimistic: ChatEntry = {
      id: `local-${Date.now()}`,
      body,
      fromCustomer: true,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setDraft("");
    try {
      let conversationId = getConversationId();
      if (!conversationId) {
        conversationId = crypto.randomUUID();
        localStorage.setItem("triage_widget_conversation_id", conversationId);
      }
      await sendMessage(config, conversationId, body);
      subscribe(conversationId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <button
        className="tw-launcher"
        onClick={() => setOpen(true)}
        aria-label="Open chat"
      >
        {LAUNCHER_ICON}
      </button>
    );
  }

  return (
    <div className="tw-panel">
      <div className="tw-header">
        <span>Support Chat</span>
        <button className="tw-close" onClick={() => setOpen(false)} aria-label="Close chat">
          ×
        </button>
      </div>
      <div className="tw-messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="tw-empty">Hi! How can we help you today?</div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.fromCustomer ? "tw-msg tw-customer" : "tw-msg"}>
            {m.body}
          </div>
        ))}
      </div>
      {error && <div className="tw-error">{error}</div>}
      <div className="tw-input-row">
        <input
          type="text"
          value={draft}
          placeholder="Type a message…"
          onInput={(e) => setDraft((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
        />
        <button onClick={() => void send()} disabled={sending || !draft.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}

export function mountWidget(target: HTMLElement, config: WidgetConfig) {
  render(<ChatWidget config={config} />, target);
}
