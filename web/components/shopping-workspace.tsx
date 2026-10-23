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

import { FilterPanel, type FilterValues } from "@/components/filter-panel";
import { NearbyOffers } from "@/components/nearby-offers";
import { ResponseCards } from "@/components/response-cards";
import { getApiHealth, resolveLocation, searchOffers, streamChat } from "@/lib/api";
import { formatNumber, parseToman } from "@/lib/format";
import type {
  AssistantCard,
  ChatEntry,
  ChatTurn,
  ConversationState,
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
  preferences: {},
};

const SUGGESTIONS = [
  { label: "کتونی برای پیاده‌روی", icon: Footprints },
  { label: "گوشی برای عکاسی", icon: Smartphone },
  { label: "لپ‌تاپ برای دانشگاه", icon: Laptop },
  { label: "هدفون روزمره", icon: Headphones },
];

type OfferSearchMode = "matched" | "relaxed" | "wider" | "empty";

const TOOL_LABELS: Record<string, string> = {
  search_products: "در حال پیدا کردن مدل‌های مناسب",
  get_offers: "در حال بررسی فروشگاه‌های نزدیک",
  compare_shops: "در حال مقایسه‌ی قیمت و فاصله",
  check_open_now: "در حال بررسی ساعت کاری",
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
}

export function ShoppingWorkspace() {
  const [conversation, setConversation] = useState(INITIAL_CONVERSATION);
  const [filters, setFilters] = useState<FilterValues>({
    location: DEFAULT_LOCATION.label,
    budget: "",
    radiusKm: 4,
    openNow: false,
    installment: false,
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
  const [marketplaceMode, setMarketplaceMode] = useState<OfferSearchMode>("matched");
  const [marketplaceError, setMarketplaceError] = useState("");
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [apiHealth, setApiHealth] = useState<"checking" | "ready" | "offline" | "unconfigured">("checking");
  const [activeTools, setActiveTools] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [locationBusy, setLocationBusy] = useState(false);
  const scrollArea = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  const selectedProductId = conversation.selectedProductId;
  const selectedShopIds = conversation.selectedShopIds ?? [];
  const activeToolText = useMemo(() => {
    const latest = Object.values(activeTools).at(-1);
    return latest ?? "";
  }, [activeTools]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const data = JSON.parse(saved) as Partial<SavedWorkspace>;
        if (data.conversation) setConversation(data.conversation);
        if (data.filters) setFilters(data.filters);
        if (data.messages) setMessages(data.messages);
        if (data.history) setHistory(data.history);
        if (data.userId) setUserId(data.userId);
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
    const saved: SavedWorkspace = { conversation, filters, messages, history, userId };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  }, [conversation, filters, history, messages, ready, userId]);

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
      budget: filters.budget.trim() ? parseToman(filters.budget) : (conversationOverride ?? conversation).budget,
      radiusKm: filters.radiusKm,
      filters: {
        ...(conversationOverride ?? conversation).filters,
        openNow: filters.openNow,
        installment: filters.installment,
      },
    };

    const locationText = filters.location.trim();
    const currentLabel = nextConversation.location?.label ?? "";
    if (locationText && locationText !== currentLabel) {
      setLocationBusy(true);
      try {
        const point = await resolveLocation(locationText);
        nextConversation = { ...nextConversation, location: { ...point, label: locationText } };
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
    const controller = new AbortController();

    try {
      for await (const event of streamChat({
        message,
        userId,
        conversation: nextConversation,
        history,
      }, controller.signal)) {
        handleStreamEvent(event, replyId, (text) => {
          replyText = text;
        });
      }
      if (replyText) {
        setHistory([...nextHistory, { role: "assistant", content: replyText }]);
      } else {
        setHistory(nextHistory);
      }
    } catch (requestError) {
      const messageText = requestError instanceof Error ? requestError.message : "ارتباط قطع شد؛ دوباره تلاش کن.";
      updateMessage(replyId, { content: messageText });
      setHistory([...nextHistory, { role: "assistant", content: messageText }]);
    } finally {
      setBusy(false);
      setActiveTools({});
      window.setTimeout(() => composer.current?.focus(), 50);
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
        onResponse(event.response.text);
        updateMessage(targetId, { content: event.response.text, cards: event.response.cards });
        setConversation((current) => ({
          ...current,
          selectedProductId: current.selectedProductId ?? inferProductId(event.response?.cards ?? []),
        }));
      }
      if (event.type === "conversation" && event.conversation) {
        const updatedConversation = {
          ...event.conversation,
          location: event.conversation.location
            ? { ...event.conversation.location, label: filters.location || event.conversation.location.label }
            : null,
        };
        setConversation(updatedConversation);
        setFilters((current) => ({
          ...current,
          location: updatedConversation.location?.label ?? current.location,
          budget: updatedConversation.budget ? formatNumber(updatedConversation.budget) : current.budget,
          radiusKm: updatedConversation.radiusKm,
          openNow: Boolean(updatedConversation.filters.openNow),
          installment: Boolean(updatedConversation.filters.installment),
        }));
      }
      if (event.type === "error") {
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
    setOffersBusy(true);
    setLocationBusy(false);
    setError("");
    setMarketplaceError("");
    setMobileFiltersOpen(false);
    setMarketplaceProduct(product);

    let nextConversation: ConversationState = {
      ...currentState,
      selectedProductId: product.id,
      selectedShopIds: [],
      budget: nextFilters.budget.trim() ? parseToman(nextFilters.budget) : currentState.budget,
      radiusKm: nextFilters.radiusKm,
      filters: {
        ...currentState.filters,
        openNow: nextFilters.openNow,
        installment: nextFilters.installment,
      },
    };

    try {
      const locationLabel = nextFilters.location.trim();
      const currentLabel = nextConversation.location?.label ?? "";
      if (locationLabel && locationLabel !== currentLabel) {
        setLocationBusy(true);
        const resolved = await resolveLocation(locationLabel);
        nextConversation = {
          ...nextConversation,
          location: { lat: resolved.lat, lng: resolved.lng, label: locationLabel },
        };
      }

      const point = nextConversation.location ?? DEFAULT_LOCATION;
      const query = {
        productId: product.id,
        location: { lat: point.lat, lng: point.lng },
        radius: nextFilters.radiusKm,
        maxPrice: nextConversation.budget,
        installment: nextFilters.installment,
        openNow: nextFilters.openNow,
      };
      let results = await searchOffers(query);
      let mode: OfferSearchMode = "matched";
      if (!results.length) {
        results = await searchOffers({ ...query, maxPrice: null, installment: false, openNow: false });
        mode = results.length ? "relaxed" : "empty";
      }
      if (!results.length) {
        results = await searchOffers({
          ...query,
          radius: 100,
          maxPrice: null,
          installment: false,
          openNow: false,
        });
        mode = results.length ? "wider" : "empty";
      }
      setMarketplaceProduct(product);
      setMarketplaceResults(results);
      setMarketplaceMode(mode);
      setConversation(nextConversation);
      setNotice(mode === "matched"
        ? `${formatNumber(results.length)} فروشگاه با شرایط فعلی پیدا شد.`
        : results.length
          ? "نتیجه‌ی منطبق نبود؛ گزینه‌های نزدیک‌تر یا دورتر را با توضیح می‌بینی."
          : "در دیتاست آفر مکانی پیدا نشد؛ می‌توانی فیلتر یا مرکز بازار را بررسی کنی.");
    } catch (searchError) {
      const messageText = searchError instanceof Error ? searchError.message : "جستجوی فروشگاه‌ها انجام نشد.";
      setError(messageText);
      setMarketplaceError(messageText);
    } finally {
      setOffersBusy(false);
      setLocationBusy(false);
    }
  }

  function handleChooseProduct(product: Product) {
    void searchForProduct(product, filters, conversation);
  }

  function handleAskInquiry(result: ShopResult) {
    const next = {
      ...conversation,
      selectedProductId: result.offer.productId,
      selectedShopIds: [result.shop.id],
    };
    setConversation(next);
    void submitMessage(
      `برای محصول ${result.offer.productId} در فروشگاه ${result.shop.id} استعلام شبیه‌سازی‌شده بگیر و موجودی را روشن کن.`,
      next,
    );
  }

  function handlePrepareVisit(result: ShopResult) {
    const next = {
      ...conversation,
      selectedProductId: result.offer.productId,
      selectedShopIds: [result.shop.id],
    };
    setConversation(next);
    void submitMessage(
      `برای محصول ${result.offer.productId} در فروشگاه ${result.shop.id} کارت نهایی مراجعه را با قیمت، تاریخ قیمت، ساعت کاری، آدرس پاساژ، آخرین استعلام نمونه‌سازی و یک فروشگاه پشتیبان بساز.`,
      next,
    );
  }

  function handleToggleCompare(result: ShopResult) {
    if (conversation.selectedProductId && conversation.selectedProductId !== result.offer.productId) {
      setNotice("برای مقایسه، فروشگاه‌های یک محصول را انتخاب کن؛ انتخاب قبلی پاک شد.");
      setConversation((current) => ({
        ...current,
        selectedProductId: result.offer.productId,
        selectedShopIds: [result.shop.id],
      }));
      return;
    }
    const isSelected = selectedShopIds.includes(result.shop.id);
    const nextIds = isSelected
      ? selectedShopIds.filter((id) => id !== result.shop.id)
      : [...selectedShopIds, result.shop.id].slice(-3);
    setNotice(nextIds.length > 1 ? `${formatNumber(nextIds.length)} فروشگاه برای مقایسه انتخاب شد.` : "برای مقایسه، یک فروشگاه دیگر هم انتخاب کن.");
    setConversation((current) => {
      return {
        ...current,
        selectedProductId: result.offer.productId,
        selectedShopIds: nextIds,
      };
    });
  }

  function handleCompare() {
    if (!conversation.selectedProductId || selectedShopIds.length < 2 || busy) return;
    const productId = conversation.selectedProductId;
    const shops = selectedShopIds.join("، ");
    void submitMessage(
      `برای محصول ${productId} این فروشگاه‌ها را با هم مقایسه کن: ${shops}`,
      conversation,
    );
  }

  function handleApplyFilters() {
    const product = marketplaceProduct ?? findProduct(messages, selectedProductId);
    if (!product || offersBusy) return;
    void searchForProduct(product, filters, conversation);
  }

  function handleWidenRadius() {
    if (!marketplaceProduct || offersBusy) return;
    const nextFilters = { ...filters, radiusKm: Math.min(filters.radiusKm + 4, 20) };
    setFilters(nextFilters);
    void searchForProduct(marketplaceProduct, nextFilters, conversation);
  }

  function handleRelaxFilters() {
    if (!marketplaceProduct || offersBusy) return;
    const nextFilters = { ...filters, budget: "", openNow: false, installment: false };
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
    };
    const nextConversation = {
      ...conversation,
      budget: null,
      radiusKm: 4,
      filters: { openNow: false, installment: false, express: false },
    };
    setFilters(nextFilters);
    setConversation(nextConversation);
    const product = marketplaceProduct ?? findProduct(messages, selectedProductId);
    if (product) void searchForProduct(product, nextFilters, nextConversation);
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
        <div className="topbar-context"><span className="topbar-pin"><MapPin size={14} /></span>تهران، خرید حضوری</div>
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
          <button type="button" onClick={() => setMobileFiltersOpen(true)} aria-expanded={mobileFiltersOpen}>
            <SlidersHorizontal size={15} /> شرایط خرید
          </button>
        </div>

        <div className="workspace-grid">
          <section className="conversation-panel" aria-label="گفتگوی راهنمای خرید">
            <div className="conversation-heading">
              <div className="advisor-avatar"><Store size={18} /></div>
              <div><h2>راهنمای خرید</h2><p>با اطلاعات فروشگاه‌های ترب</p></div>
              <span className="privacy-note"><Check size={13} /> بدون تماس واقعی</span>
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
                            cards={entry.cards}
                            selectedShopIds={selectedShopIds}
                            onChooseProduct={handleChooseProduct}
                            onAskInquiry={handleAskInquiry}
                            onToggleCompare={handleToggleCompare}
                            onPrepareVisit={handlePrepareVisit}
                          />
                        )}
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
              {marketplaceProduct && (
                <NearbyOffers
                  product={marketplaceProduct}
                  center={conversation.location ?? DEFAULT_LOCATION}
                  results={marketplaceResults}
                  mode={marketplaceMode}
                  error={marketplaceError}
                  busy={offersBusy}
                  onWidenRadius={handleWidenRadius}
                  onRelaxFilters={handleRelaxFilters}
                  onSuggestMarket={handleSuggestMarket}
                  onSearchWeb={handleSearchWeb}
                  canWidenRadius={filters.radiusKm < 20}
                  selectedShopIds={selectedShopIds}
                  onToggleCompare={handleToggleCompare}
                  onAskInquiry={handleAskInquiry}
                  onPrepareVisit={handlePrepareVisit}
                />
              )}
            </div>

            {notice && !busy && (
              <div className="inline-notice" role="status"><Check size={14} />{notice}<button type="button" onClick={() => setNotice("")} aria-label="بستن پیام"><X size={13} /></button></div>
            )}
            {error && <div className="inline-error" role="alert"><CircleHelp size={15} />{error}</div>}

            {selectedShopIds.length > 1 && conversation.selectedProductId && (
              <div className="compare-bar">
                <span><ArrowLeftRight size={16} /> {formatNumber(selectedShopIds.length)} فروشگاه انتخاب شده</span>
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
            values={filters}
            busy={busy || locationBusy || offersBusy}
            hasSelectedProduct={Boolean(selectedProductId)}
            onChange={setFilters}
            onUseCurrentLocation={handleUseCurrentLocation}
            onApply={handleApplyFilters}
            onReset={handleResetFilters}
          />
          {mobileFiltersOpen && (
            <div className="mobile-filter-overlay" role="presentation" onClick={() => setMobileFiltersOpen(false)}>
              <div className="mobile-filter-sheet" role="dialog" aria-modal="true" aria-label="فیلترهای خرید" onClick={(event) => event.stopPropagation()}>
                <button type="button" className="close-sheet" onClick={() => setMobileFiltersOpen(false)} aria-label="بستن فیلترها"><X size={19} /></button>
                <FilterPanel
                  values={filters}
                  busy={busy || locationBusy || offersBusy}
                  hasSelectedProduct={Boolean(selectedProductId)}
                  onChange={setFilters}
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
    if (card.kind === "alternatives" && card.results[0]) return card.results[0].offer.productId;
  }
  return null;
}

function findProduct(messages: ChatEntry[], productId: string | null): Product | null {
  if (!productId) return null;
  for (const entry of [...messages].reverse()) {
    for (const card of entry.cards ?? []) {
      if (card.kind === "product_cards" || card.kind === "alternatives") {
        const product = card.products.find((item) => item.id === productId);
        if (product) return product;
      }
    }
  }
  return { id: productId, titleFa: "محصول انتخاب‌شده" };
}
