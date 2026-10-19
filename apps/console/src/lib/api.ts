export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";
export const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "";

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  if (TENANT_ID) headers["X-Tenant-ID"] = TENANT_ID;
  return headers;
}

export type ConversationStatus = "open" | "pending" | "resolved" | "escalated" | "closed";

export interface Conversation {
  id: string;
  tenant_id: string;
  customer_id: string;
  channel_id: string;
  status: ConversationStatus;
  priority: number;
  subject: string | null;
  message_count: number;
  unread_count: number;
  intent_primary: string | null;
  intent_secondary: string | null;
  confidence_score: number | null;
  is_auto_resolved: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  resolved_at: string | null;
}

export interface StreamMessage {
  type: "init" | "message" | "error";
  id?: string;
  body?: string;
  sender_id?: string;
  channel_type?: string;
  created_at?: string | null;
  error?: string;
}

export async function listConversations(status?: string): Promise<Conversation[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const qs = params.toString();
  const resp = await fetch(`${API_URL}/api/v1/conversations${qs ? `?${qs}` : ""}`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!resp.ok) throw new Error(`listConversations failed: ${resp.status}`);
  return resp.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const resp = await fetch(`${API_URL}/api/v1/conversations/${id}`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!resp.ok) throw new Error(`getConversation failed: ${resp.status}`);
  return resp.json();
}

export async function updateConversation(
  id: string,
  status: ConversationStatus,
): Promise<Conversation> {
  const resp = await fetch(`${API_URL}/api/v1/conversations/${id}?status=${status}`, {
    method: "PATCH",
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error(`updateConversation failed: ${resp.status}`);
  return resp.json();
}

export async function* streamConversation(
  conversationId: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamMessage> {
  const resp = await fetch(`${API_URL}/api/v1/streams/conversations/${conversationId}`, {
    headers: authHeaders(),
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`stream failed: ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (line.startsWith("data: ") && line.length > 6) {
          try {
            yield JSON.parse(line.slice(6)) as StreamMessage;
          } catch {
            // ignore malformed frames
          }
        }
      }
    }
  }
}
