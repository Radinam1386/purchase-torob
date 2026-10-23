"use client";

import {
  ArrowDownLeft,
  ArrowLeftRight,
  Check,
  ChevronLeft,
  CircleHelp,
  Footprints,
  Headphones,
  Laptop,
  LoaderCircle,
  MapPin,
  MessageCircle,
  PackageSearch,
  ShoppingBag,
  SlidersHorizontal,
  Smartphone,
  Store,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { FilterPanel, type FilterValues } from "@/components/filter-panel";
import { ResponseCards } from "@/components/response-cards";
import { getApiHealth, resolveLocation, searchOffers, streamChat } from "@/lib/api";
import { formatNumber, parseToman } from "@/lib/format";
import type {
  AssistantCard,
  ChatEntry,
  ChatTurn,
  ConversationState,
  DataSource,
  Product,
  ShopResult,
  StreamEvent,
} from "@/lib/contracts";

const STORAGE_KEY = "torob-in-person.workspace.v1";
const DEFAULT_LOCATION = { lat: 35.7219, lng: 51.4097, label: "مرکز تهران" };
const INITIAL_CONVERSATION: ConversationState = {
  location: DEFAULT_LOCATION,
  budget: null,
  radiusKm: 4,
  filters: { installment: false, express: false, openNow: false },
  selectedProductId: null,
  selectedShopIds: [],
  selectedOfferIds: [],
  preferences: {},
};

const SUGGESTIONS = [
  { label: "کتونی برای پیاده‌روی", icon: Footprints },
  { label: "گوشی برای عکاسی", icon: Smartphone },
  { label: "لپ‌تاپ برای دانشگاه", icon: Laptop },
  { label: "هدفون روزمره", icon: Headphones },
];

const TOOL_LABELS: Record<string, string> = {
  search_products: "در حال پیدا کردن مدل‌های مناسب",
  get_offers: "در حال بررسی فروشگاه‌های نزدیک",
  compare_shops: "در حال مقایسه‌ی قیمت و فاصله",
  check_open_now: "در حال بررسی ساعت کاری",
  draft_inquiry: "در حال آماده‌سازی پیش‌نویس استعلام",
  send_inquiry: "در حال ارسال و پیگیری استعلام از فروشنده",
  send_inquiry_batch: "در حال ارسال استعلام دسته‌ای به فروشگاه‌ها",
  get_inquiry_status: "در حال بررسی وضعیت استعلام",
  list_inquiries: "در حال بازیابی استعلام‌ها",
  cancel_inquiry: "در حال لغو استعلام",
  follow_up_inquiry: "در حال پیگیری مجدد استعلام",
  inquire_shop: "در حال آماده‌کردن استعلام نمونه‌سازی",
  find_alternatives: "در حال پیدا کردن جایگزین‌ها",
  get_shop_location_hint: "در حال آماده‌کردن مسیر داخل پاساژ",
  suggest_market_hub: "در حال بررسی مرکزهای بازار",
  product_quick_look: "در حال جمع‌بندی نکات خرید حضوری",
  web_search: "در حال بررسی منبع وب",
  resolve_location: "در حال یافتن محدوده‌ی جستجو",
};

interface SavedWorkspace {
  conversation: ConversationState;
  filters: FilterValues;
  messages: ChatEntry[];
  history: ChatTurn[];
  userId: string;
  marketplaceProduct?: Product | null;
  marketplaceResults?: ShopResult[];
}

export function ShoppingWorkspace() {
  const router = useRouter();
  const [conversation, setConversation] = useState(INITIAL_CONVERSATION);
  const [filters, setFilters] = useState<FilterValues>({
    location: DEFAULT_LOCATION.label,
    budget: "",
    radiusKm: 4,
    openNow: false,
    installment: false,
    express: false,
  });
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [userId, setUserId] = useState("local");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [offersBusy, setOffersBusy] = useState(false);
  const [marketplaceProduct, setMarketplaceProduct] = useState<Product | null>(null);
  const [marketplaceResults, setMarketplaceResults] = useState<ShopResult[]>([]);
  const [marketplaceError, setMarketplaceError] = useState("");
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [apiHealth, setApiHealth] = useState<"checking" | "ready" | "offline" | "unconfigured">("checking");
  const [activeTools, setActiveTools] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [locationBusy, setLocationBusy] = useState(false);
  const scrollArea = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const offerSearchSequence = useRef(0);
  const selectionVersion = useRef(0);
  const mobileFilterDialog = useRef<HTMLDivElement>(null);
  const mobileFilterOpener = useRef<HTMLButtonElement>(null);
  const mobileFilterClose = useRef<HTMLButtonElement>(null);
  const activeChatRequest = useRef<AbortController | null>(null);
  const chatGeneration = useRef(0);
  const initialized = useRef(false);
  const initialMessage = useRef<string | null>(null);

  const selectedProductId = conversation.selectedProductId;
  const selectedOfferIds = conversation.selectedOfferIds ?? [];
  const activeToolText = useMemo(() => {
    const latest = Object.values(activeTools).at(-1);
    return latest ?? "";
  }, [activeTools]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const params = new URLSearchParams(window.location.search);
    const initialQuery = params.get("q")?.trim();
    if (params.get("new") === "1" || initialQuery) {
      initialMessage.current = initialQuery || null;
      setUserId(`web-${window.crypto.randomUUID()}`);
      try {
        window.localStorage.removeItem("torob-last-results-url");
        window.localStorage.removeItem("torob-product-compare.v1");
      } catch { /* A fresh chat does not depend on saved search state. */ }
      // Consume the entry command so refresh resumes instead of sending twice.
      window.history.replaceState(null, "", window.location.pathname);
      setReady(true);
      return;
    }
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const data = JSON.parse(saved) as Partial<SavedWorkspace>;
        if (data.conversation) setConversation(data.conversation);
        if (data.filters) {
          setFilters({
            ...data.filters,
            express: data.filters.express ?? false,
            budget: data.filters.budget || (data.conversation?.budget ? formatNumber(data.conversation.budget) : ""),
          });
        }
        if (data.messages) setMessages(restoreMessages(data.messages));
        if (data.history) setHistory(data.history);
        if (data.marketplaceProduct) setMarketplaceProduct(data.marketplaceProduct);
        if (data.marketplaceResults) setMarketplaceResults(data.marketplaceResults);
        if (data.userId) setUserId(data.userId);
        const lastResults = window.localStorage.getItem("torob-last-results-url");
        if (data.conversation && data.filters && lastResults?.startsWith("/products")) {
          const params = new URL(lastResults, window.location.origin).searchParams;
          const budget = params.has("max_price") ? parseToman(params.get("max_price") ?? "") : null;
          const searchFilters = { installment: params.get("installment") === "true", express: params.get("express") === "true", openNow: params.get("open_now") === "true" };
          setConversation({ ...data.conversation, budget, filters: searchFilters });
          setFilters({ ...data.filters, budget: budget === null ? "" : formatNumber(budget), ...searchFilters });
        }
      } else {
        setUserId(`web-${window.crypto.randomUUID()}`);
      }
    } catch {
      setUserId(`web-${Date.now()}`);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const saved: SavedWorkspace = {
      conversation,
      filters,
      messages,
      history,
      userId,
      marketplaceProduct,
      marketplaceResults,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  }, [conversation, filters, history, marketplaceProduct, marketplaceResults, messages, ready, userId]);

  useEffect(() => {
    if (!ready || !initialMessage.current) return;
    const message = initialMessage.current;
    initialMessage.current = null;
    void submitMessage(message);
  }, [ready]);

  useEffect(() => {
    if (!mobileFiltersOpen) return;
    const dialog = mobileFilterDialog.current;
    mobileFilterClose.current?.focus();

    function handleDialogKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileFiltersOpen(false);
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) {
        event.preventDefault();
        dialog.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleDialogKeyDown);
    return () => {
      document.removeEventListener("keydown", handleDialogKeyDown);
      mobileFilterOpener.current?.focus();
    };
  }, [mobileFiltersOpen]);

  useEffect(() => {
    const controller = new AbortController();
    getApiHealth(controller.signal)
      .then((health) => setApiHealth(health.databaseReady && health.llmConfigured ? "ready" : "unconfigured"))
      .catch(() => setApiHealth("offline"));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const node = scrollArea.current;
    if (node) node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [activeTools, marketplaceResults, messages, offersBusy]);

  function updateMessage(id: string, update: Partial<ChatEntry>) {
    setMessages((current) => current.map((item) => item.id === id ? { ...item, ...update } : item));
  }

  async function submitMessage(
    messageOverride?: string,
    conversationOverride?: ConversationState,
  ) {
    const message = (messageOverride ?? draft).trim();
    if (!message || busy) return;
    const selectionVersionAtRequest = selectionVersion.current;

    setError("");
    setNotice("");
    setBusy(true);
    setMobileFiltersOpen(false);
    setDraft("");

    const userEntry: ChatEntry = {
      id: window.crypto.randomUUID(),
      role: "user",
      content: message,
    };
    const replyId = window.crypto.randomUUID();
    setMessages((current) => [
      ...current,
      userEntry,
      { id: replyId, role: "assistant", content: "", cards: [] },
    ]);

    let nextConversation: ConversationState = {
      ...(conversationOverride ?? conversation),
      budget: parseToman(filters.budget),
      radiusKm: filters.radiusKm,
      filters: {
        ...(conversationOverride ?? conversation).filters,
        openNow: filters.openNow,
        installment: filters.installment,
        express: filters.express,
      },
    };

    const locationText = filters.location.trim();
    const currentLabel = nextConversation.location?.label ?? "";
    if (locationText && locationText !== currentLabel) {
      setLocationBusy(true);
      try {
        const point = await resolveLocation(locationText);
        nextConversation = { ...nextConversation, location: { ...point, label: point.label ?? locationText } };
        setConversation(nextConversation);
        setNotice(`محدوده روی ${locationText} تنظیم شد.`);
      } catch (locationError) {
        const messageText = locationError instanceof Error ? locationError.message : "محدوده پیدا نشد.";
        setBusy(false);
        setLocationBusy(false);
        setMessages((current) => current.filter((entry) => entry.id !== replyId));
        setDraft(message);
        setError(messageText);
        return;
      } finally {
        setLocationBusy(false);
      }
    }

    setConversation(nextConversation);
    const nextHistory = [...history, { role: "user" as const, content: message }];
    let replyText = "";
    let replyCards: AssistantCard[] = [];
    let pendingSearchQuery: string | null = null;
    let pendingSearchCategory: string | null = null;
    let pendingSearchMinPrice: number | null = null;
    let finalConversation = nextConversation;
    let needsClarification = false;
    const controller = new AbortController();
    activeChatRequest.current = controller;
    const generation = chatGeneration.current;

    try {
      for await (const event of streamChat({
        message,
        userId,
        conversation: nextConversation,
        history,
      }, controller.signal)) {
        if (generation !== chatGeneration.current) return;
        handleStreamEvent(event, replyId, (text) => {
          replyText = text;
        });
      }
      if (generation !== chatGeneration.current) return;
      if (replyText) {
        setHistory([...nextHistory, { role: "assistant", content: replyText }]);
      } else {
        setHistory(nextHistory);
      }
      const searchChanged = finalConversation.budget !== nextConversation.budget
        || JSON.stringify(finalConversation.filters) !== JSON.stringify(nextConversation.filters)
        || finalConversation.radiusKm !== nextConversation.radiusKm
        || JSON.stringify(finalConversation.location) !== JSON.stringify(nextConversation.location);
      if (pendingSearchQuery === null && searchChanged && !needsClarification) {
        const previous = window.localStorage.getItem("torob-last-results-url");
        if (previous?.startsWith("/products")) pendingSearchQuery = new URL(previous, window.location.origin).searchParams.get("q") ?? "";
      }
      // Finish and persist the stream before leaving; the final conversation event carries budget/state.
      if (pendingSearchQuery !== null) {
        const params = new URLSearchParams({ q: pendingSearchQuery, from: "chat" });
        if (pendingSearchCategory) params.set("category", pendingSearchCategory);
        if (pendingSearchMinPrice !== null) params.set("min_price", String(pendingSearchMinPrice));
        if (finalConversation.budget !== null) params.set("max_price", String(finalConversation.budget));
        const point = finalConversation.location;
        if (point) { params.set("lat", String(point.lat)); params.set("lng", String(point.lng)); }
        params.set("radius_km", String(finalConversation.radiusKm));
        for (const [key, value] of Object.entries(finalConversation.filters)) {
          if (value) params.set(key === "openNow" ? "open_now" : key, "true");
        }
        const resultsUrl = `/products?${params}`;
        const finalMessages: ChatEntry[] = [...messages, userEntry, {
          id: replyId, role: "assistant", content: replyText, cards: replyCards, resultsUrl,
        }];
        const finalFilters = { ...filters, budget: finalConversation.budget ? formatNumber(finalConversation.budget) : "",
          radiusKm: finalConversation.radiusKm, location: point?.label ?? filters.location,
          openNow: Boolean(finalConversation.filters.openNow), installment: Boolean(finalConversation.filters.installment), express: Boolean(finalConversation.filters.express) };
        setMessages(finalMessages);
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ conversation: finalConversation,
          filters: finalFilters, messages: finalMessages, history: [...nextHistory, {role: "assistant", content: replyText}],
          userId, marketplaceProduct, marketplaceResults } satisfies SavedWorkspace));
        window.localStorage.setItem("torob-last-results-url", resultsUrl);
        router.push(resultsUrl);
      }
    } catch (requestError) {
      if (generation !== chatGeneration.current) return;
      const messageText = requestError instanceof Error ? requestError.message : "ارتباط قطع شد؛ دوباره تلاش کن.";
      updateMessage(replyId, { content: messageText });
      setHistory([...nextHistory, { role: "assistant", content: messageText }]);
    } finally {
      if (generation === chatGeneration.current) {
        activeChatRequest.current = null;
        setBusy(false);
        setActiveTools({});
        window.setTimeout(() => composer.current?.focus(), 50);
      }
    }

    function handleStreamEvent(
      event: StreamEvent,
      targetId: string,
      onResponse: (text: string) => void,
    ) {
      if (event.type === "tool_start" && event.callId) {
        const toolLabel = TOOL_LABELS[event.name ?? ""] ?? "در حال بررسی گزینه‌ها";
        setActiveTools((current) => ({ ...current, [event.callId as string]: toolLabel }));
      }
      if (event.type === "tool_end" && event.callId) {
        setActiveTools((current) => {
          const updated = { ...current };
          delete updated[event.callId as string];
          return updated;
        });
      }
      if (event.type === "text_delta" && event.text) updateMessage(targetId, { content: event.text });
      if (event.type === "response" && event.response) {
        needsClarification = Boolean(event.response.clarificationQuestion);
        onResponse(event.response.text);
        const productCard = event.response.cards.find((card): card is Extract<AssistantCard,{kind:"product_cards"}> => card.kind === "product_cards");
        const visibleCards = event.response.cards.filter(isConversationCard);
        replyCards = visibleCards;
        updateMessage(targetId, { content: productCard
          ? `${event.response.text}\n\n${formatNumber(productCard.products.length)} گزینه در جستجوی اولیه پیدا شد. نتایج کامل در صفحه محصولات باز می‌شود.`
          : event.response.text, cards: visibleCards });
        if (event.response.searchQuery != null) pendingSearchQuery = event.response.searchQuery;
        else if (productCard) pendingSearchQuery = productCard.products[0]?.category ?? message;
        pendingSearchCategory = event.response.searchCategory ?? null;
        pendingSearchMinPrice = event.response.searchMinPrice ?? null;
        if (selectionVersion.current === selectionVersionAtRequest) {
          setConversation((current) => ({
            ...current,
            selectedProductId: current.selectedProductId ?? inferProductId(event.response?.cards ?? []),
          }));
        }
      }
      if (event.type === "conversation" && event.conversation) {
        const updatedConversation = {
          ...event.conversation,
          location: event.conversation.location
            ? { ...event.conversation.location }
            : null,
        };
        finalConversation = updatedConversation;
        if (selectionVersion.current === selectionVersionAtRequest) {
          setConversation(updatedConversation);
          setFilters((current) => ({
            ...current,
            location: updatedConversation.location?.label ?? current.location,
            budget: updatedConversation.budget ? formatNumber(updatedConversation.budget) : "",
            radiusKm: updatedConversation.radiusKm,
            openNow: Boolean(updatedConversation.filters.openNow),
            installment: Boolean(updatedConversation.filters.installment),
            express: Boolean(updatedConversation.filters.express),
          }));
        }
      }
      if (event.type === "error") {
        needsClarification = true;
        const messageText = event.message ?? "پاسخ‌گویی با مشکل روبه‌رو شد.";
        onResponse(messageText);
        updateMessage(targetId, { content: messageText, cards: [] });
      }
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitMessage();
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  }

  async function searchForProduct(
    product: Product,
    nextFilters: FilterValues,
    currentState: ConversationState,
  ) {
    const requestId = ++offerSearchSequence.current;
    selectionVersion.current += 1;
    setOffersBusy(true);
    setLocationBusy(false);
    setError("");
    setMarketplaceError("");
    setMobileFiltersOpen(false);
    setMarketplaceProduct(product);
    setMarketplaceResults([]);

    let nextConversation: ConversationState = {
      ...currentState,
      selectedProductId: product.id,
      selectedShopIds: [],
      selectedOfferIds: [],
      budget: parseToman(nextFilters.budget),
      radiusKm: nextFilters.radiusKm,
      filters: {
        ...currentState.filters,
        openNow: nextFilters.openNow,
        installment: nextFilters.installment,
        express: nextFilters.express,
      },
    };
    setConversation(nextConversation);

    try {
      const locationLabel = nextFilters.location.trim();
      const currentLabel = nextConversation.location?.label ?? "";
      if (locationLabel && locationLabel !== currentLabel) {
        setLocationBusy(true);
        const resolved = await resolveLocation(locationLabel);
        if (requestId !== offerSearchSequence.current) return;
        nextConversation = {
          ...nextConversation,
          location: { lat: resolved.lat, lng: resolved.lng, label: resolved.label ?? locationLabel },
        };
      }

      const point = nextConversation.location ?? DEFAULT_LOCATION;
      const query = {
        productId: product.id,
        location: { lat: point.lat, lng: point.lng },
        radius: nextFilters.radiusKm,
        maxPrice: nextConversation.budget,
        installment: nextFilters.installment,
        express: nextFilters.express,
        openNow: nextFilters.openNow,
      };
      const results = await searchOffers(query);
      if (requestId !== offerSearchSequence.current) return;
      setMarketplaceProduct(product);
      setMarketplaceResults(results);
      setConversation(nextConversation);
      setNotice(results.length
        ? `${formatNumber(results.length)} فروشگاه با شرایط فعلی پیدا شد.`
        : "در دیتاست آفر مکانی پیدا نشد؛ می‌توانی شعاع را بیشتر کنی، فیلترها را تغییر بدهی یا مرکز بازار را ببینی.");
    } catch (searchError) {
      if (requestId !== offerSearchSequence.current) return;
      const messageText = searchError instanceof Error ? searchError.message : "جستجوی فروشگاه‌ها انجام نشد.";
      setError(messageText);
      setMarketplaceError(messageText);
    } finally {
      if (requestId === offerSearchSequence.current) {
        setOffersBusy(false);
        setLocationBusy(false);
      }
    }
  }

  function handleChooseProduct(product: Product) {
    void searchForProduct(product, filters, conversation);
  }

  function handleAskInquiry(result: ShopResult) {
    const offerId = result.offer.id;
    if (!offerId) {
      setNotice("این آفر قدیمی شناسه‌ی قابل استعلام ندارد؛ فروشگاه‌ها را دوباره جست‌وجو کن.");
      return;
    }
    selectionVersion.current += 1;
    const next = {
      ...conversation,
      selectedProductId: result.offer.productId,
      selectedShopIds: [result.shop.id],
      selectedOfferIds: [offerId],
    };
    setConversation(next);
    void submitMessage(
      `برای محصول ${result.offer.productId} و آفر ${offerId} در فروشگاه ${result.shop.id} استعلام شبیه‌سازی‌شده بگیر و موجودی را روشن کن.`,
      next,
    );
  }

  function handleConfirmDraft(draftId: string, editedText?: string) {
    void submitMessage(
      `پیش‌نویس استعلام ${draftId} مورد تأیید است؛ ارسالش کن.${editedText ? ` متن نهایی پیام: "${editedText}"` : ""}`,
      conversation,
    );
  }

  function handleCancelInquiry(inquiryId: string) {
    void submitMessage(
      `استعلام ${inquiryId} را لغو کن.`,
      conversation,
    );
  }

  function handlePrepareVisit(result: ShopResult) {
    const offerId = result.offer.id;
    if (!offerId) {
      setNotice("این آفر قدیمی شناسه‌ی قابل مراجعه ندارد؛ فروشگاه‌ها را دوباره جست‌وجو کن.");
      return;
    }
    selectionVersion.current += 1;
    const next = {
      ...conversation,
      selectedProductId: result.offer.productId,
      selectedShopIds: [result.shop.id],
      selectedOfferIds: [offerId],
    };
    setConversation(next);
    void submitMessage(
      `برای محصول ${result.offer.productId} و آفر ${offerId} در فروشگاه ${result.shop.id} کارت نهایی مراجعه را با قیمت، تاریخ قیمت، ساعت کاری، آدرس پاساژ، آخرین استعلام نمونه‌سازی و یک فروشگاه پشتیبان بساز.`,
      next,
    );
  }

  function handleToggleCompare(result: ShopResult) {
    const offerId = result.offer.id;
    if (!offerId) {
      setNotice("این آفر قدیمی شناسه‌ی قابل مقایسه ندارد؛ فروشگاه‌ها را دوباره جست‌وجو کن.");
      return;
    }
    selectionVersion.current += 1;
    if (conversation.selectedProductId && conversation.selectedProductId !== result.offer.productId) {
      setNotice("برای مقایسه، آفرهای یک محصول را انتخاب کن؛ انتخاب قبلی پاک شد.");
      setConversation((current) => ({
        ...current,
        selectedProductId: result.offer.productId,
        selectedShopIds: [result.shop.id],
        selectedOfferIds: [offerId],
      }));
      return;
    }
    const isSelected = selectedOfferIds.includes(offerId);
    const nextIds = isSelected
      ? selectedOfferIds.filter((id) => id !== offerId)
      : [...selectedOfferIds, offerId].slice(-3);
    setNotice(nextIds.length > 1 ? `${formatNumber(nextIds.length)} آفر برای مقایسه انتخاب شد.` : "برای مقایسه، یک آفر دیگر هم انتخاب کن.");
    setConversation((current) => {
      return {
        ...current,
        selectedProductId: result.offer.productId,
        selectedShopIds: [],
        selectedOfferIds: nextIds,
      };
    });
  }

  function handleCompare() {
    if (!conversation.selectedProductId || selectedOfferIds.length < 2 || busy) return;
    const productId = conversation.selectedProductId;
    const offers = selectedOfferIds.join("، ");
    void submitMessage(
      `برای محصول ${productId} این شناسه‌های آفر را با هم مقایسه کن: ${offers}`,
      conversation,
    );
  }

  async function handleApplyFilters() {
    if (offersBusy || busy) return;
    setLocationBusy(true);
    setError("");
    try {
      let point = conversation.location ?? DEFAULT_LOCATION;
      if (filters.location.trim() && filters.location.trim() !== point.label) {
        const resolved = await resolveLocation(filters.location.trim());
        point = { ...resolved, label: resolved.label ?? filters.location.trim() };
      }
      const next = { ...conversation, location: point, budget: parseToman(filters.budget),
        radiusKm: filters.radiusKm, filters: {openNow: filters.openNow, installment: filters.installment, express: filters.express} };
      setConversation(next);
      const previous = window.localStorage.getItem("torob-last-results-url");
      if (previous) {
        const url = new URL(previous, window.location.origin);
        url.searchParams.delete("page");
        if (next.budget !== null) url.searchParams.set("max_price", String(next.budget));
        else url.searchParams.delete("max_price");
        url.searchParams.set("lat", String(point.lat)); url.searchParams.set("lng", String(point.lng));
        url.searchParams.set("radius_km", String(next.radiusKm));
        for (const [key, value] of Object.entries(next.filters)) {
          const param = key === "openNow" ? "open_now" : key;
          if (value) url.searchParams.set(param, "true"); else url.searchParams.delete(param);
        }
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ conversation: next, filters, messages, history, userId, marketplaceProduct, marketplaceResults } satisfies SavedWorkspace));
        window.localStorage.setItem("torob-last-results-url", `${url.pathname}${url.search}`);
        router.push(`${url.pathname}${url.search}`);
      } else setNotice("ترجیحات ذخیره شد؛ گفت‌وگو را ادامه بده.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "محدوده پیدا نشد؛ نام محله را اصلاح کن.");
    } finally { setLocationBusy(false); }
  }

  function handleFilterChange(nextFilters: FilterValues) {
    selectionVersion.current += 1;
    setFilters(nextFilters);
  }

  function handleWidenRadius() {
    if (!marketplaceProduct || offersBusy) return;
    const nextFilters = { ...filters, radiusKm: Math.min(filters.radiusKm + 4, 50) };
    setFilters(nextFilters);
    void searchForProduct(marketplaceProduct, nextFilters, conversation);
  }

  function handleRelaxFilters() {
    if (!marketplaceProduct || offersBusy) return;
    const nextFilters = { ...filters, budget: "", openNow: false, installment: false, express: false };
    setFilters(nextFilters);
    void searchForProduct(marketplaceProduct, nextFilters, { ...conversation, budget: null });
  }

  function handleSuggestMarket() {
    const product = marketplaceProduct ?? findProduct(messages, selectedProductId);
    if (!product || busy) return;
    void submitMessage(
      `برای ${product.titleFa} در محدوده و فیلترهای فعلی فروشگاهی پیدا نشد. دلیل را کوتاه توضیح بده و بورس کالا یا محله‌ی تخصصی مرتبط را پیشنهاد کن.`,
      conversation,
    );
  }

  function handleSearchWeb() {
    const product = marketplaceProduct ?? findProduct(messages, selectedProductId);
    if (!product || busy) return;
    void submitMessage(
      `برای ${product.titleFa} در دیتاست آفر مکانی پیدا نشد. حالا جستجوی تکمیلی وب را انجام بده و تمام نتایج بیرونی را صریح با منبع وب جدا کن.`,
      conversation,
    );
  }

  function handleUseCurrentLocation() {
    if (!navigator.geolocation) {
      setError("مرورگر امکان دریافت موقعیت را ندارد؛ نام محله را وارد کن.");
      return;
    }
    selectionVersion.current += 1;
    setLocationBusy(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const location = { lat: coords.latitude, lng: coords.longitude, label: "موقعیت فعلی شما" };
        setConversation((current) => ({ ...current, location }));
        setFilters((current) => ({ ...current, location: location.label }));
        setLocationBusy(false);
        setError("");
      },
      () => {
        setLocationBusy(false);
        setError("موقعیت دریافت نشد؛ اجازه‌ی مرورگر را بررسی کن یا نام محله را بنویس.");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    );
  }

  function handleResetFilters() {
    const nextFilters = {
      location: conversation.location?.label ?? DEFAULT_LOCATION.label,
      budget: "",
      radiusKm: 4,
      openNow: false,
      installment: false,
      express: false,
    };
    const nextConversation = {
      ...conversation,
      budget: null,
      radiusKm: 4,
      filters: { openNow: false, installment: false, express: false },
    };
    setFilters(nextFilters);
    setConversation(nextConversation);
    setNotice("فیلترها پاک شدند؛ برای به‌روزرسانی نتایج، اعمال فیلترها را بزن.");
  }

  function startNewChat() {
    chatGeneration.current += 1;
    activeChatRequest.current?.abort();
    activeChatRequest.current = null;
    offerSearchSequence.current += 1;
    selectionVersion.current += 1;
    setMessages([]);
    setHistory([]);
    setDraft("");
    setBusy(false);
    setOffersBusy(false);
    setActiveTools({});
    setError("");
    setNotice("");
    setMarketplaceError("");
    setMarketplaceProduct(null);
    setMarketplaceResults([]);
    window.localStorage.removeItem("torob-last-results-url");
    window.localStorage.removeItem("torob-product-compare.v1");
    setConversation((current) => ({ ...INITIAL_CONVERSATION, location: current.location, radiusKm: current.radiusKm }));
    setFilters((current) => ({ ...current, budget: "", openNow: false, installment: false, express: false }));
    composer.current?.focus();
  }

  function clearChat() {
    if (!messages.length && !history.length) return;
    if (!window.confirm("گفتگو و محصولات انتخاب‌شده پاک شوند؟")) return;
    startNewChat();
  }

  function chooseSuggestion(label: string) {
    setDraft(label);
    composer.current?.focus();
  }

  const statusText = {
    checking: "در حال اتصال",
    ready: "راهنمای خرید آماده است",
    offline: "اتصال به هسته برقرار نیست",
    unconfigured: "تنظیمات هسته کامل نیست",
  }[apiHealth];

  return (
    <div className="app-shell" dir="rtl">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="صفحه اصلی ترب حضوری">
          <span className="brand-mark"><span /><i /></span>
          <span className="brand-name">ترب<span>حضوری</span></span>
        </a>
        <nav className="chat-main-nav" aria-label="ناوبری اصلی">
          <Link href="/">خانه</Link>
          <Link href="/products">محصولات</Link>
          <Link href="/chat" aria-current="page">دستیار خرید</Link>
        </nav>
        <div className="topbar-context"><span className="topbar-pin"><MapPin size={14} /></span>تهران، خرید حضوری</div>
        <a
          href="/seller-sim"
          target="_blank"
          rel="noreferrer"
          className="seller-sim-link"
          title="شبیه‌ساز فروشنده برای سناریوی دو پنجره‌ای"
        >
          شبیه‌ساز فروشنده ↗
        </a>
        <div className={`service-status status-${apiHealth}`} title={statusText}>
          <span className="status-dot" />
          <span>{statusText}</span>
        </div>
      </header>

      <main id="top" className="page-content">
        <section className="page-intro">
          <div>
            <div className="eyebrow"><span /> راهنمای خرید حضوری در تهران</div>
            <h1>قبل از راه افتادن،<br /><em>با اطمینان انتخاب کن.</em></h1>
            <p>مدل مناسب را پیدا کن، فروشگاه‌های نزدیک را بسنج و بعد برای خرید حضوری راه بیفت.</p>
          </div>
          <div className="intro-route" aria-hidden="true">
            <div className="route-copy"><span className="route-start"><Store size={17} /></span><span className="route-line" /><span className="route-end"><MapPin size={17} /></span></div>
            <span>از انتخاب تا رسیدن</span>
          </div>
        </section>

        <div className="mobile-filter-row">
          <span><MapPin size={14} /> {filters.location || "تهران"}</span>
          <button
            ref={mobileFilterOpener}
            type="button"
            onClick={() => setMobileFiltersOpen(true)}
            aria-expanded={mobileFiltersOpen}
            aria-haspopup="dialog"
            aria-controls="mobile-filter-dialog"
          >
            <SlidersHorizontal size={15} /> شرایط خرید
          </button>
        </div>

        <div className="workspace-grid">
          <section className="conversation-panel" aria-label="گفتگوی راهنمای خرید">
            <div className="conversation-heading">
              <div className="advisor-avatar"><Store size={18} /></div>
              <div><h2>راهنمای خرید</h2><p>با اطلاعات فروشگاه‌های ترب</p></div>
              <span className="privacy-note"><Check size={13} /> بدون تماس واقعی</span>
              <div className="chat-actions">
                <button type="button" onClick={startNewChat} title="شروع گفتگوی خرید جدید">گفتگوی جدید</button>
                <button type="button" onClick={clearChat} disabled={!messages.length && !history.length} title="پاک کردن گفتگو">پاک‌کردن چت</button>
              </div>
            </div>

            <div className="conversation-scroll" ref={scrollArea} aria-live="polite">
              {!messages.length ? (
                <WelcomeState onChoose={chooseSuggestion} />
              ) : (
                <div className="message-list">
                  {messages.map((entry) => (
                    <article className={`message-row message-${entry.role}`} key={entry.id}>
                      {entry.role === "assistant" && <div className="message-avatar"><Store size={15} /></div>}
                      <div className="message-body">
                        {entry.content ? (
                          <div className={`message-bubble ${entry.role === "assistant" ? "assistant-bubble" : "user-bubble"}`}>
                            {entry.content}
                          </div>
                        ) : null}
                        {entry.role === "assistant" && entry.cards && entry.cards.length > 0 && (
                          <ResponseCards
                            cards={entry.cards.filter(isConversationCard)}
                            selectedOfferIds={selectedOfferIds}
                            onChooseProduct={handleChooseProduct}
                            onAskInquiry={handleAskInquiry}
                            onToggleCompare={handleToggleCompare}
                            onPrepareVisit={handlePrepareVisit}
                            onConfirmDraft={handleConfirmDraft}
                            onCancelInquiry={handleCancelInquiry}
                          />
                        )}
                        {entry.resultsUrl && <Link className="all-products-link" href={entry.resultsUrl}>مشاهده نتایج کامل و نقشه فروشگاه‌ها</Link>}
                      </div>
                    </article>
                  ))}
                  {busy && activeToolText && (
                    <div className="tool-progress" role="status">
                      <LoaderCircle size={15} className="spin" />
                      <span>{activeToolText}</span>
                      <span className="progress-dots"><i /><i /><i /></span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {notice && !busy && (
              <div className="inline-notice" role="status"><Check size={14} />{notice}<button type="button" onClick={() => setNotice("")} aria-label="بستن پیام"><X size={13} /></button></div>
            )}
            {error && <div className="inline-error" role="alert"><CircleHelp size={15} />{error}</div>}

            {selectedOfferIds.length > 1 && conversation.selectedProductId && (
              <div className="compare-bar">
                <span><ArrowLeftRight size={16} /> {formatNumber(selectedOfferIds.length)} آفر انتخاب شده</span>
                <button type="button" onClick={handleCompare} disabled={busy}>مقایسه‌ی انتخاب‌ها <ChevronLeft size={15} /></button>
              </div>
            )}

            <form className="composer" onSubmit={handleSubmit}>
              <textarea
                ref={composer}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="مثلاً کتونی برای پیاده‌روی تا ۴ میلیون..."
                rows={1}
                maxLength={1200}
                aria-label="جستجوی کالا یا پیام به راهنمای خرید"
                disabled={busy}
              />
              <button className="send-button" type="submit" disabled={busy || !draft.trim()} aria-label="شروع جستجو">
                {busy ? <LoaderCircle size={18} className="spin" /> : <ArrowDownLeft size={19} />}
              </button>
            </form>
            <div className="composer-footer">
              <span><MessageCircle size={12} /> هر وقت خواستی، شرایط خریدت را از پنل کنار صفحه تغییر بده.</span>
              <span>Enter برای ارسال</span>
            </div>
          </section>

          <FilterPanel
            idPrefix="desktop"
            values={filters}
            busy={busy || locationBusy || offersBusy}
            hasSelectedProduct={true}
            onChange={handleFilterChange}
            onUseCurrentLocation={handleUseCurrentLocation}
            onApply={handleApplyFilters}
            onReset={handleResetFilters}
          />
          {mobileFiltersOpen && (
            <div className="mobile-filter-overlay" role="presentation" onClick={() => setMobileFiltersOpen(false)}>
              <div
                id="mobile-filter-dialog"
                ref={mobileFilterDialog}
                className="mobile-filter-sheet"
                role="dialog"
                aria-modal="true"
                aria-label="فیلترهای خرید"
                tabIndex={-1}
                onClick={(event) => event.stopPropagation()}
              >
                <button ref={mobileFilterClose} type="button" className="close-sheet" onClick={() => setMobileFiltersOpen(false)} aria-label="بستن فیلترها"><X size={19} /></button>
                <FilterPanel
                  idPrefix="mobile"
                  values={filters}
                  busy={busy || locationBusy || offersBusy}
                  hasSelectedProduct={true}
                  onChange={handleFilterChange}
                  onUseCurrentLocation={handleUseCurrentLocation}
                  onApply={handleApplyFilters}
                  onReset={handleResetFilters}
                />
              </div>
            </div>
          )}
        </div>

        <footer className="page-footer">
          <span>قیمت ثبت‌شده با موجودی فرق دارد؛ پیش از مراجعه، جزئیات را بررسی کن.</span>
          <span>مناسب خرید حضوری در تهران</span>
        </footer>
      </main>
    </div>
  );
}

function WelcomeState({ onChoose }: { onChoose: (suggestion: string) => void }) {
  return (
    <div className="welcome-state">
      <div className="welcome-note">
        <div className="welcome-icon"><ShoppingBag size={19} /></div>
        <div>
          <h3>چی می‌خوای بخری؟</h3>
          <p>اسم کالا یا کاربردش را بنویس. اگر مدل دقیق را ندانی، با چند سؤال کوتاه پیدایش می‌کنیم.</p>
        </div>
      </div>
      <div className="suggestion-heading"><span>برای شروع</span><span className="suggestion-rule" /></div>
      <div className="suggestion-list">
        {SUGGESTIONS.map(({ label, icon: Icon }) => (
          <button key={label} type="button" className="suggestion-chip" onClick={() => onChoose(label)}>
            <Icon size={16} />{label}<ChevronLeft size={14} className="chip-arrow" />
          </button>
        ))}
      </div>
      <div className="welcome-footnote"><PackageSearch size={14} /> از جستجوی کالا شروع می‌کنیم؛ بعد نزدیک‌ترین آفرها را می‌بینی.</div>
    </div>
  );
}

function inferProductId(cards: AssistantCard[]): string | null {
  for (const card of cards) {
    if (card.kind === "shop_cards" || card.kind === "compare") {
      if (card.results[0]) return card.results[0].offer.productId;
    }
    if (card.kind === "alternatives" && card.options?.[0]?.results[0]) {
      return card.options[0].results[0].offer.productId;
    }
  }
  return null;
}

function findProduct(messages: ChatEntry[], productId: string | null): Product | null {
  if (!productId) return null;
  for (const entry of [...messages].reverse()) {
    for (const card of entry.cards ?? []) {
      if (card.kind === "product_cards" || card.kind === "alternatives") {
        const products = card.kind === "product_cards"
          ? card.products
          : (card.options ?? []).map((option) => option.product);
        const product = products.find((item) => item.id === productId);
        if (product) return product;
      }
    }
  }
  return { id: productId, titleFa: "محصول انتخاب‌شده" };
}

function restoreMessages(value: unknown): ChatEntry[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((entry): ChatEntry[] => {
    if (
      !isRecord(entry)
      || typeof entry.id !== "string"
      || typeof entry.content !== "string"
      || (entry.role !== "user" && entry.role !== "assistant")
    ) {
      return [];
    }
    const cards = Array.isArray(entry.cards)
      ? entry.cards.flatMap(restoreCard)
      : undefined;
    return [{ ...entry, cards } as ChatEntry];
  });
}

function isConversationCard(card: AssistantCard): boolean {
  return !["product_cards", "shop_cards", "compare", "alternatives"].includes(card.kind);
}

function restoreCard(value: unknown): AssistantCard[] {
  if (!isRecord(value) || typeof value.kind !== "string") return [];
  if (value.kind !== "alternatives") return [value as unknown as AssistantCard];
  if (Array.isArray(value.options)) return [value as unknown as AssistantCard];

  const products = Array.isArray(value.products)
    ? value.products.filter(
      (product): product is Record<string, unknown> => isRecord(product) && typeof product.id === "string",
    ) as unknown as Product[]
    : [];
  const results = Array.isArray(value.results)
    ? value.results.filter(
      (result): result is Record<string, unknown> => isRecord(result) && isRecord(result.offer),
    ) as unknown as ShopResult[]
    : [];
  const options = products.map((product) => ({
    product,
    results: results.filter((result) => (
      isRecord(result.offer) && result.offer.productId === product.id
    )),
  }));

  return [{
    kind: "alternatives",
    source: isDataSource(value.source) ? value.source : "dataset",
    options,
  } as AssistantCard];
}

function isDataSource(value: unknown): value is DataSource {
  return value === "dataset" || value === "web" || value === "ai_knowledge" || value === "simulated";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
