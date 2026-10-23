export type DataSource = "dataset" | "web" | "ai_knowledge" | "simulated";
export type StockStatus = "unverified" | "verified_in_stock" | "verified_out";

export interface Product {
  id: string;
  titleFa: string;
  titleEn?: string | null;
  brand?: string | null;
  category?: string | null;
  specs?: Record<string, string>;
  images?: string[];
}

export interface Shop {
  id: string;
  displayName: string;
  hasRealName: boolean;
  instagram?: string | null;
  website?: string | null;
  lat?: number | null;
  lng?: number | null;
  addressText?: string | null;
  mall?: string | null;
  floor?: string | null;
  unit?: string | null;
  hours?: Record<string, unknown>;
  tarobPayInStore?: boolean | null;
  installment?: boolean | null;
  kalabarg?: boolean | null;
  expressDelivery?: boolean | null;
}

export interface KnownValue<T> {
  value: T | null;
  source: DataSource;
  known: boolean;
}

export interface Offer {
  shopId: string;
  productId: string;
  price: number;
  priceUnit: string;
  priceUpdatedAt?: string | null;
  warranty?: { provider?: string | null; months?: number | null } | null;
  stock: StockStatus;
}

export interface ShopResult {
  shop: Shop;
  offer: Offer;
  distanceKm: number;
  openNow: KnownValue<boolean>;
  reasons: string[];
}

export interface MarketHub {
  category: string;
  name: string;
  neighborhood: string;
  lat: number;
  lng: number;
  note: string;
  coordinateSource: DataSource;
  coordinateVerified: boolean;
}

export interface WebResult {
  title: string;
  url: string;
  snippet: string;
  source: "web";
}

export interface AssistantResponse {
  text: string;
  cards: AssistantCard[];
  clarificationQuestion?: string | null;
}

export interface Inquiry {
  id: string;
  shopId: string;
  productId: string;
  status: "sent" | "reviewing" | "answered" | "no_answer";
  answer?: { inStock: boolean; price?: number | null; note?: string | null } | null;
  simulated: true;
}

export type AssistantCard =
  | { kind: "product_cards"; products: Product[]; source: DataSource }
  | { kind: "shop_cards"; results: ShopResult[]; source: DataSource }
  | { kind: "compare"; results: ShopResult[]; source: DataSource }
  | {
      kind: "inquiry";
      inquiry: Inquiry;
      source: "simulated";
    }
  | {
      kind: "alternatives";
      products: Product[];
      results: ShopResult[];
      source: DataSource;
    }
  | { kind: "hub"; hubs: MarketHub[]; source: "ai_knowledge" }
  | {
      kind: "quick_look";
      productId: string;
      label: "خلاصه هوش مصنوعی";
      strengths: string[];
      weaknesses: string[];
      inPersonChecks: string[];
      source: "ai_knowledge";
    }
  | {
      kind: "mall_guide";
      shop: Shop;
      directions: string[];
      offer?: ShopResult | null;
      inquiry?: Inquiry | null;
      backup?: ShopResult | null;
      source: "dataset";
    }
  | { kind: "web_results"; results: WebResult[]; source: "web" };

export interface ConversationState {
  location: { lat: number; lng: number; label?: string | null } | null;
  budget: number | null;
  radiusKm: number;
  filters: {
    installment: boolean | null;
    express: boolean | null;
    openNow: boolean | null;
  };
  selectedProductId: string | null;
  selectedShopIds: string[];
  preferences: Record<string, unknown>;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatEntry extends ChatTurn {
  id: string;
  cards?: AssistantCard[];
}

export interface StreamEvent {
  type: "text_delta" | "tool_start" | "tool_end" | "response" | "conversation" | "done" | "error";
  text?: string;
  name?: string;
  callId?: string;
  ok?: boolean;
  durationMs?: number;
  response?: AssistantResponse;
  conversation?: ConversationState;
  message?: string;
}
