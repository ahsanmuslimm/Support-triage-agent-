export interface WidgetConfig {
  apiUrl: string;
  apiKey: string;
  tenantId: string;
}

export interface ChatEntry {
  id: string;
  body: string;
  fromCustomer: boolean;
  createdAt: string | null;
}

export function readConfig(): WidgetConfig {
  // bootstrap() runs on DOMContentLoaded, where document.currentScript is
  // already null — fall back to the conventional embed script id.
  const script =
    (document.currentScript as HTMLScriptElement | null) ??
    (document.getElementById("triage-widget") as HTMLScriptElement | null);
  const dataset = script?.dataset ?? {};
  return {
    apiUrl: dataset.apiUrl ?? "http://localhost:8000",
    apiKey: dataset.apiKey ?? "",
    tenantId: dataset.tenantId ?? "",
  };
}

function headers(config: WidgetConfig): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (config.apiKey) h["X-API-Key"] = config.apiKey;
  if (config.tenantId) h["X-Tenant-ID"] = config.tenantId;
  return h;
}

function visitorId(): string {
  const key = "triage_widget_visitor_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

function conversationKey(): string {
  return "triage_widget_conversation_id";
}

export function getConversationId(): string | null {
  return localStorage.getItem(conversationKey());
}

export async function sendMessage(
  config: WidgetConfig,
  conversationId: string,
  body: string,
): Promise<void> {
  const resp = await fetch(
    `${config.apiUrl}/api/v1/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: headers(config),
      body: JSON.stringify({
        body,
        channel_type: "web_chat",
        sender_id: visitorId(),
      }),
    },
  );
  if (!resp.ok && resp.status !== 409) {
    throw new Error(`send failed: ${resp.status}`);
  }
}

export async function* streamMessages(
  config: WidgetConfig,
  conversationId: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEntry> {
  const resp = await fetch(
    `${config.apiUrl}/api/v1/streams/conversations/${conversationId}`,
    { headers: headers(config), signal },
  );
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
        if (!line.startsWith("data: ") || line.length <= 6) continue;
        try {
          const event = JSON.parse(line.slice(6)) as {
            type?: string;
            id?: string;
            body?: string;
            sender_id?: string;
            created_at?: string | null;
          };
          if (event.type === "message" && event.id) {
            yield {
              id: event.id,
              body: event.body ?? "",
              fromCustomer: event.sender_id === visitorId(),
              createdAt: event.created_at ?? null,
            };
          }
        } catch {
          // ignore malformed frames
        }
      }
    }
  }
}
