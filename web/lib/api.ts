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

export async function savePriceCheck(input: {
  productId: string; shopId: string; offerId?: string; outcome: string;
  reportedPrice?: number; method: string; note?: string;
}) {
  const response = await fetch(`${API_ROOT}/api/price-checks`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
  const body = await response.json().catch(() => null) as { detail?: string; id?: string } | null;
  if (!response.ok || !body?.id) throw new Error(body?.detail ?? "ثبت بررسی انجام نشد.");
  return body;
}

export async function draftInquiry(input: {
  shopId: string;
  productId: string;
  offerId?: string | null;
  etaMinutes?: number | null;
  quantity?: number;
  sizeOrColor?: string | null;
  holdRequested?: boolean;
  channel?: string | null;
}) {
  const response = await fetch(`${API_ROOT}/api/inquiries/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(err?.detail ?? "خطا در تهیه پیش‌نویس استعلام");
  }
  return await response.json();
}

export async function confirmInquiry(input: {
  inquiryId: string;
  editedMessage?: string | null;
}) {
  const response = await fetch(`${API_ROOT}/api/inquiries/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(err?.detail ?? "خطا در ارسال استعلام");
  }
  return await response.json();
}

export async function cancelInquiry(inquiryId: string, reason?: string) {
  const response = await fetch(`${API_ROOT}/api/inquiries/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inquiryId, reason }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(err?.detail ?? "خطا در لغو استعلام");
  }
  return await response.json();
}

export async function listInquiries(params?: { shopId?: string; status?: string; limit?: number }) {
  const query = new URLSearchParams();
  if (params?.shopId) query.set("shop_id", params.shopId);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));

  const response = await fetch(`${API_ROOT}/api/inquiries?${query.toString()}`, { cache: "no-store" });
  if (!response.ok) throw new Error("دریافت فهرست استعلام‌ها با خطا مواجه شد.");
  return (await response.json()) as { inquiries: any[] };
}

export async function sellerReply(
  inquiryId: string,
  input: {
    action: "in_stock" | "out_of_stock" | "price_changed" | "delay_10m";
    customPrice?: number | null;
    note?: string | null;
  },
) {
  const response = await fetch(`${API_ROOT}/api/inquiries/${inquiryId}/seller-reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(err?.detail ?? "ثبت پاسخ با خطا مواجه شد.");
  }
  return await response.json();
}
