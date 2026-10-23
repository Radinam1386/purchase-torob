import type { Offer, Product, Shop, ShopResult } from "./contracts";

const API_ROOT = (process.env.NEXT_PUBLIC_AGENT_API ?? "").replace(/\/$/, "");
const WORKSPACE = "torob-in-person.workspace.v1";
export const SCENARIOS = {
  confirmed: "قیمت مطابق دیتاست",
  price_changed: "قیمت تغییر کرده",
  out_of_stock: "محصول موجود نیست",
  needs_review: "نیاز به بررسی بیشتر",
  no_answer: "پاسخی دریافت نشد",
  alternative: "پیشنهاد جایگزین",
} as const;
export type MockScenario = keyof typeof SCENARIOS;
export interface ContactSelection { product: Product; shop: Shop; offer: Offer }
export interface MockRun {
  id: string; source: "simulated"; provider: "mock"; status: "completed" | "needs_review" | "no_answer";
  scenario: MockScenario; createdAt: string; product: Product; shop: Shop; datasetOffer: Offer;
  simulatedPrice: number | null; simulatedInStock: boolean | null; priceDifference: number | null;
  transcript: { role: "agent" | "seller" | "system"; text: string }[];
  stages: { id: string; label: string; timestamp: string }[];
  analysis: string; alternatives: ShopResult[]; limitation: string;
}
export interface BuyerReport {
  id: string; source: "buyer_report"; reported_price?: number | null; reportedPrice?: number | null;
  in_stock?: boolean | null; inStock?: boolean | null; observed_at?: string | null; observedAt?: string | null;
  checked_at?: string; checkedAt?: string; method: string; note?: string; outcome: string;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, { credentials: "include", cache: "no-store", ...options });
  const body = await response.json().catch(() => null);
  if (!response.ok || !body) throw new Error(typeof body?.detail === "string" ? body.detail : "دریافت اطلاعات انجام نشد؛ دوباره تلاش کن.");
  return body as T;
}
export function getContactSelection(offerId: string, signal?: AbortSignal) {
  return request<ContactSelection & { source: "dataset" }>(`/api/contact/selection?${new URLSearchParams({offer_id: offerId})}`, {signal});
}
export function createMockCall(input: {offerId: string; scenario: MockScenario; newPrice?: number; runKey: string}) {
  return request<{run: MockRun}>("/api/mock-calls", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(input)});
}
export function getMockCall(id: string, signal?: AbortSignal) {
  return request<{run: MockRun}>(`/api/mock-calls/${encodeURIComponent(id)}`, {signal});
}
export function getMockHistory(page: number, signal?: AbortSignal) {
  return request<{total: number; page: number; page_size: number; data: MockRun[]}>(`/api/mock-calls?page=${page}&page_size=10`, {signal});
}
export function getBuyerReports(selection: ContactSelection, signal?: AbortSignal) {
  return request<{source: "buyer_report"; checks: BuyerReport[]}>(`/api/price-checks?${new URLSearchParams({product_id:selection.product.id,shop_id:selection.shop.id,offer_id:selection.offer.id ?? ""})}`, {signal});
}
export function createBuyerReport(selection: ContactSelection, input: {outcome: string; reportedPrice?: number; inStock: boolean | null; method: string; observedAt: string; note: string}) {
  return request<{id:string}>("/api/price-checks", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...input,productId:selection.product.id,shopId:selection.shop.id,offerId:selection.offer.id})});
}

export function rememberContactSelection(selection: ContactSelection, stage = "preparing_contact") {
  try {
    const saved = JSON.parse(window.localStorage.getItem(WORKSPACE) || "{}");
    const conversation = saved.conversation || { location: null, budget: null, radiusKm: 4, filters: {installment:false,express:false,openNow:false}, preferences: {} };
    conversation.selectedProductId = selection.product.id;
    conversation.selectedShopIds = [selection.shop.id];
    conversation.selectedOfferIds = selection.offer.id ? [selection.offer.id] : [];
    conversation.preferences = {...conversation.preferences, _advisor: {...conversation.preferences?._advisor, status: stage},
      searchProfile: {...conversation.preferences?.searchProfile, stage}};
    window.localStorage.setItem(WORKSPACE, JSON.stringify({...saved,conversation,marketplaceProduct:selection.product,contactSelection:selection}));
  } catch { /* URL identifiers keep the contact flow usable when browser storage is unavailable. */ }
}
export function rememberContactStage(stage: string) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(WORKSPACE) || "{}");
    if (!saved.conversation) return;
    const preferences = saved.conversation.preferences || {};
    saved.conversation.preferences = {...preferences,_advisor:{...preferences._advisor,status:stage},searchProfile:{...preferences.searchProfile,stage}};
    window.localStorage.setItem(WORKSPACE,JSON.stringify(saved));
  } catch { /* The server-side Mock history remains the authoritative result. */ }
}
