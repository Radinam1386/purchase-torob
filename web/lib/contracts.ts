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

export interface PriceFreshness {
  daysAgo?: number | null;
  level: "fresh" | "moderate" | "stale" | "unknown";
  label: string;
}

export interface Offer {
  id?: string;
  shopId: string;
  productId: string;
  price: number | null;
  priceUnit: string;
  priceUpdatedAt?: string | null;
  priceFreshness?: PriceFreshness | null;
  warranty?: { provider?: string | null; months?: number | null } | null;
  stock: StockStatus;
}

export interface ShopResult {
  shop: Shop;
  offer: Offer;
  distanceKm: number;
  openNow: KnownValue<boolean>;
  reasons: string[];
  priceFreshness?: PriceFreshness | null;
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

export type InquiryChannel = "panel" | "sms" | "chat" | "ai_call";
export type InquiryStatus =
  | "draft"
  | "sent"
  | "delivered"
  | "read"
  | "answered"
  | "no_answer"
  | "cancelled";

export interface InquiryTimelineStep {
  stage: InquiryStatus;
  label: string;
  title?: string;
  status?: string;
  timestamp?: string | null;
  completed: boolean;
}

export interface InquiryRequestDetails {
  etaMinutes?: number | null;
  quantity?: number;
  sizeOrColor?: string | null;
  holdRequested?: boolean;
}

export interface InquiryAnswer {
  inStock: boolean;
  price?: number | null;
  note?: string | null;
  transcript?: string | null;
  priceChanged?: boolean;
  holdConfirmed?: boolean;
}

export interface Inquiry {
  id: string;
  shopId: string;
  productId: string;
  offerId?: string | null;
  sessionId?: string | null;
  channel: InquiryChannel;
  status: InquiryStatus;
  message?: string | null;
  requests?: InquiryRequestDetails;
  requestDetails?: InquiryRequestDetails | null;
  answer?: InquiryAnswer | null;
  timeline?: InquiryTimelineStep[];
  createdAt?: string | null;
  sentAt?: string | null;
  deliveredAt?: string | null;
  readAt?: string | null;
  answeredAt?: string | null;
  expiresAt?: string | null;
  persona?: string | null;
  batchId?: string | null;
  simulated: true;
  shopName?: string | null;
  productTitle?: string | null;
  datasetPrice?: number | null;
}

export interface MessageDraftCard {
  kind: "message_draft";
  inquiryId: string;
  shop: Shop;
  product: Product;
  offer: Offer;
  channel: InquiryChannel;
  message: string;
  requests: InquiryRequestDetails;
  shopOpenAtEta: KnownValue<boolean>;
  warning?: string | null;
  confirmed: boolean;
  source: "simulated";
}

export interface InquiryBatchItem {
  inquiryId: string;
  shop: Shop;
  offer: Offer;
  status: InquiryStatus;
  channel: InquiryChannel;
  answer?: InquiryAnswer | null;
}

export interface InquiryBatchCard {
  kind: "inquiry_batch";
  batchId: string;
  product: Product;
  items: InquiryBatchItem[];
  source: "simulated";
}

export type AssistantCard =
  | { kind: "product_cards"; products: Product[]; source: DataSource }
  | { kind: "shop_cards"; results: ShopResult[]; source: DataSource }
  | { kind: "compare"; results: ShopResult[]; source: DataSource }
  | MessageDraftCard
  | {
      kind: "inquiry";
      inquiry: Inquiry;
      shop?: Shop | null;
      product?: Product | null;
      source: "simulated";
    }
  | InquiryBatchCard
  | {
      kind: "alternatives";
      options: { product: Product; results: ShopResult[] }[];
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
  selectedOfferIds: string[];
  selectedInquiryIds?: string[];
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
  type:
    | "text_delta"
    | "tool_start"
    | "tool_end"
    | "response"
    | "conversation"
    | "inquiry_update"
    | "done"
    | "error";
  text?: string;
  name?: string;
  callId?: string;
  ok?: boolean;
  durationMs?: number;
  response?: AssistantResponse;
  conversation?: ConversationState;
  inquiry?: Inquiry;
  message?: string;
}
