import type { ChatTurn, ConversationState, ShopResult, StreamEvent } from "./contracts";

const API_ROOT = (process.env.NEXT_PUBLIC_AGENT_API ?? "").replace(/\/$/, "");

interface ChatRequest {
  message: string;
  userId: string;
  conversation: ConversationState;
  history: ChatTurn[];
}

export async function* streamChat(
  request: ChatRequest,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_ROOT}/api/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "اتصال به راهنمای خرید برقرار نشد.");
  }
  if (!response.body) throw new Error("جریان پاسخ در دسترس نیست.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLine = frame.split(/\r?\n/).find((line) => line.startsWith("data:"));
        if (dataLine) yield JSON.parse(dataLine.slice(5).trim()) as StreamEvent;
        boundary = buffer.indexOf("\n\n");
      }

      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
}

export async function resolveLocation(text: string, signal?: AbortSignal) {
  const response = await fetch(`${API_ROOT}/api/location/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  const body = (await response.json().catch(() => null)) as
    | { lat: number; lng: number; label?: string }
    | { detail?: string }
    | null;
  if (!response.ok || !body || !("lat" in body)) {
    throw new Error(body && "detail" in body ? body.detail ?? "محدوده پیدا نشد." : "محدوده پیدا نشد.");
  }
  return body;
}

export async function getApiHealth(signal?: AbortSignal) {
  const response = await fetch(`${API_ROOT}/api/health`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("سرویس آفلاین است.");
  return (await response.json()) as {
    status: string;
    databaseReady: boolean;
    llmConfigured: boolean;
  };
}

export async function searchOffers(input: {
  productId: string;
  location: { lat: number; lng: number };
  radius: number;
  maxPrice: number | null;
  installment: boolean;
  express: boolean;
  openNow: boolean;
}, signal?: AbortSignal): Promise<ShopResult[]> {
  const response = await fetch(`${API_ROOT}/api/offers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      productId: input.productId,
      lat: input.location.lat,
      lng: input.location.lng,
      radius: input.radius,
      maxPrice: input.maxPrice,
      installment: input.installment,
      express: input.express,
      openNow: input.openNow,
    }),
    signal,
  });
  const body = await response.json().catch(() => null) as
    | { source: string; data: ShopResult[] }
    | { detail?: string }
    | null;
  if (!response.ok || !body || !("data" in body)) {
    throw new Error(body && "detail" in body ? body.detail ?? "جستجو انجام نشد." : "جستجو انجام نشد.");
  }
  return body.data;
}
