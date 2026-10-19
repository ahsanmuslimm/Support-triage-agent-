"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { listConversations, type Conversation, type ConversationStatus } from "@/lib/api";

const STATUSES: (ConversationStatus | "all")[] = [
  "all",
  "open",
  "pending",
  "escalated",
  "resolved",
  "closed",
];

export default function DashboardPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [status, setStatus] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setConversations(await listConversations(status === "all" ? undefined : status));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  return (
    <>
      <div className="toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "All statuses" : s}
            </option>
          ))}
        </select>
        <button onClick={() => void refresh()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
        <span className="muted">{conversations.length} conversations</span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="conversation-list">
        {conversations.length === 0 && !error ? (
          <div className="empty-state">No conversations yet.</div>
        ) : (
          conversations.map((c) => (
            <Link
              key={c.id}
              href={`/conversations/${c.id}`}
              className="conversation-row"
            >
              <span className={`badge ${c.status}`}>{c.status}</span>
              <span className="subject">{c.intent_primary ?? c.id.slice(0, 8)}</span>
              <span className="muted">{c.message_count} msgs</span>
              <span className="muted">{c.channel_id}</span>
              <span className="muted">
                {c.last_message_at ? new Date(c.last_message_at).toLocaleString() : "—"}
              </span>
            </Link>
          ))
        )}
      </div>
    </>
  );
}
