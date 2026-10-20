"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getConversation,
  streamConversation,
  updateConversation,
  type Conversation,
  type ConversationStatus,
  type StreamMessage,
} from "@/lib/api";

interface ChatMessage {
  id: string;
  body: string;
  senderId: string;
  channelType: string;
  createdAt: string | null;
}

export default function ConversationDetailPage() {
  // useParams (not use(params)): Next 14 passes a plain object, and React's
  // use() only accepts thenables/context — it crashed with error #438.
  const { id } = useParams<{ id: string }>();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const streamStarted = useRef(false);

  const loadConversation = useCallback(async () => {
    try {
      setConversation(await getConversation(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    void loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    if (streamStarted.current) return;
    streamStarted.current = true;
    const controller = new AbortController();
    (async () => {
      try {
        for await (const event of streamConversation(id, controller.signal)) {
          if (event.type === "message" && event.id) {
            const msg: ChatMessage = {
              id: event.id,
              body: event.body ?? "",
              senderId: event.sender_id ?? "unknown",
              channelType: event.channel_type ?? "",
              createdAt: event.created_at ?? null,
            };
            setMessages((prev) =>
              prev.some((m) => m.id === msg.id) ? prev : [...prev, msg],
            );
          }
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => controller.abort();
  }, [id]);

  const changeStatus = async (status: ConversationStatus) => {
    try {
      setConversation(await updateConversation(id, status));
      setActionError(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  if (error) {
    return (
      <>
        <div className="error-banner">{error}</div>
        <Link href="/">← Back to conversations</Link>
      </>
    );
  }
  if (!conversation) return <div className="empty-state">Loading…</div>;

  return (
    <>
      <div className="detail-header">
        <h1>
          Conversation {conversation.id.slice(0, 8)}{" "}
          <span className={`badge ${conversation.status}`}>{conversation.status}</span>
        </h1>
        <button onClick={() => void changeStatus("resolved")}>Resolve</button>
        <button onClick={() => void changeStatus("escalated")}>Escalate</button>
        <button onClick={() => void changeStatus("pending")}>Pending</button>
      </div>
      {actionError && <div className="error-banner">{actionError}</div>}
      <div className="muted" style={{ marginBottom: 12 }}>
        channel: {conversation.channel_id} · intent: {conversation.intent_primary ?? "—"} ·
        confidence: {conversation.confidence_score ?? "—"} · messages: {conversation.message_count}
      </div>

      <div className="message-list">
        {messages.length === 0 ? (
          <div className="empty-state">Waiting for messages…</div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className="message-bubble">
              <div>{m.body}</div>
              <div className="meta">
                {m.senderId} · {m.channelType} ·{" "}
                {m.createdAt ? new Date(m.createdAt).toLocaleString() : ""}
              </div>
            </div>
          ))
        )}
      </div>
      <Link href="/">← Back to conversations</Link>
    </>
  );
}
