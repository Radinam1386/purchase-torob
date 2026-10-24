import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpLeft,
  BadgeCheck,
  Building2,
  CalendarClock,
  CheckCircle2,
  CircleHelp,
  Clock3,
  ExternalLink,
  Layers,
  MailQuestion,
  MapPin,
  Navigation,
  PackageCheck,
  PackageSearch,
  PhoneCall,
  Route,
  Send,
  ShieldCheck,
  Store,
} from "lucide-react";
import { useState } from "react";
import Link from "next/link";

import {
  directionsUrl,
  formatDate,
  formatDistance,
  formatPrice,
  openLabel,
  sourceLabel,
  stockLabel,
} from "@/lib/format";
import type {
  AssistantCard,
  InquiryBatchCard,
  MessageDraftCard,
  Product,
  ShopResult,
} from "@/lib/contracts";

interface CardActions {
  selectedOfferIds: string[];
  onChooseProduct: (product: Product) => void;
  onAskInquiry: (result: ShopResult) => void;
  onToggleCompare: (result: ShopResult) => void;
  onPrepareVisit: (result: ShopResult) => void;
  onConfirmDraft?: (draftId: string, editedText?: string) => void;
  onCancelInquiry?: (inquiryId: string) => void;
}

interface ResponseCardsProps extends CardActions {
  cards: AssistantCard[];
}

export function ResponseCards({
  cards,
  selectedOfferIds,
  onChooseProduct,
  onAskInquiry,
  onToggleCompare,
  onPrepareVisit,
  onConfirmDraft,
  onCancelInquiry,
}: ResponseCardsProps) {
  if (!cards.length) return null;

  return (
    <div className="response-cards">
      {cards.map((card, index) => (
        <CardRenderer
          key={`${card.kind}-${index}`}
          card={card}
          selectedOfferIds={selectedOfferIds}
          onChooseProduct={onChooseProduct}
          onAskInquiry={onAskInquiry}
          onToggleCompare={onToggleCompare}
          onPrepareVisit={onPrepareVisit}
          onConfirmDraft={onConfirmDraft}
          onCancelInquiry={onCancelInquiry}
        />
      ))}
    </div>
  );
}

interface CardRendererProps extends CardActions {
  card: AssistantCard;
}

function CardRenderer({
  card,
  selectedOfferIds,
  onChooseProduct,
  onAskInquiry,
  onToggleCompare,
  onPrepareVisit,
  onConfirmDraft,
  onCancelInquiry,
}: CardRendererProps) {
  switch (card.kind) {
    case "product_cards": {
      const q = card.products[0]?.category || card.products[0]?.titleFa || "";
      const count = card.products.length;
      return (
        <CardShell icon={<PackageSearch size={17} />} title="مدل‌های پیدا شده در دیتاست" source={card.source}>
          <div className="search-outcome-card">
            <p className="search-outcome-summary">
              {count > 0
                ? `${count} مدل بر اساس معیارهای شما در دیتاست ترب پیدا شد. تمام نتایج با امکان فیلتر، مرتب‌سازی و مقایسه در صفحه مستقل محصولات آماده است:`
                : "محصولی با این مشخصات در دیتاست پیدا نشد."}
            </p>
            {count > 0 && (
              <div className="search-outcome-actions">
                <Link
                  className="search-outcome-cta"
                  href={`/products?q=${encodeURIComponent(q)}&from=chat`}
                  onClick={() => {
                    try {
                      sessionStorage.setItem(
                        "torob-search-products",
                        JSON.stringify({
                          query: q,
                          products: card.products,
                          createdAt: Date.now(),
                        })
                      );
                    } catch {}
                  }}
                >
                  مشاهده نتایج در صفحه محصولات ({count} مدل) <ArrowLeft size={16} />
                </Link>
                <Link
                  className="search-outcome-map-link"
                  href={`/map?q=${encodeURIComponent(q)}`}
                >
                  <MapPin size={15} /> مشاهده فروشگاه‌ها روی نقشه
                </Link>
              </div>
            )}
          </div>
        </CardShell>
      );
    }

    case "shop_cards":
      return (
        <ShopResultsCard
          title="فروشگاه‌های دارای آفر"
          results={card.results}
          source={card.source}
          selectedOfferIds={selectedOfferIds}
          onAskInquiry={onAskInquiry}
          onToggleCompare={onToggleCompare}
          onPrepareVisit={onPrepareVisit}
        />
      );

    case "compare":
      return (
        <ShopResultsCard
          title="مقایسه‌ی فروشگاه‌ها"
          results={card.results}
          source={card.source}
          selectedOfferIds={selectedOfferIds}
          onAskInquiry={onAskInquiry}
          onToggleCompare={onToggleCompare}
          onPrepareVisit={onPrepareVisit}
        />
      );

    case "alternatives": {
      const options = card.options ?? [];
      return (
        <CardShell icon={<PackageCheck size={17} />} title="جایگزین‌های نزدیک" source={card.source}>
          {options.map(({ product, results }) => (
            <section className="alternative-option" key={product.id}>
              <ProductOption product={product} onChoose={onChooseProduct} />
              <ShopResultList
                results={results}
                selectedOfferIds={selectedOfferIds}
                onAskInquiry={onAskInquiry}
                onToggleCompare={onToggleCompare}
                onPrepareVisit={onPrepareVisit}
              />
            </section>
          ))}
          {!options.length && (
            <EmptyResults>در این محدوده جایگزین ثبت‌شده‌ای پیدا نشد.</EmptyResults>
          )}
        </CardShell>
      );
    }

    case "message_draft":
      return (
        <MessageDraftCardComponent
          card={card}
          onConfirmDraft={onConfirmDraft}
          onCancelInquiry={onCancelInquiry}
        />
      );

    case "inquiry_batch":
      return (
        <InquiryBatchCardComponent
          card={card}
          onCancelInquiry={onCancelInquiry}
        />
      );

    case "inquiry":
      return (
        <EnhancedInquiryCardComponent
          card={card}
          onCancelInquiry={onCancelInquiry}
        />
      );

    case "hub":
      return (
        <CardShell icon={<Building2 size={17} />} title="مرکزهای پیشنهادی بازار" source="ai_knowledge">
          <div className="hub-list">
            {card.hubs.slice(0, 3).map((hub) => {
              const url = directionsUrl(hub.lat, hub.lng);
              return (
                <article className="hub-item" key={`${hub.name}-${hub.neighborhood}`}>
                  <div className="hub-copy">
                    <strong>{hub.name}</strong>
                    <span><MapPin size={13} /> {hub.neighborhood}</span>
                    <p>{hub.note}</p>
                  </div>
                  {url && (
                    <a className="icon-button" href={url} target="_blank" rel="noreferrer" aria-label="نمایش مسیر روی نقشه">
                      <Navigation size={16} />
                    </a>
                  )}
                </article>
              );
            })}
            {!card.hubs.length && <EmptyResults>مرکز مشخصی برای این کالا در فهرست نیست.</EmptyResults>}
          </div>
          {!card.hubs.every((hub) => hub.coordinateVerified) && (
            <p className="quiet-note"><CircleHelp size={13} /> مختصات بعضی مرکزها تأییدنشده است؛ قبل از حرکت بررسی کن.</p>
          )}
        </CardShell>
      );

    case "quick_look":
      return (
        <CardShell icon={<ShieldCheck size={17} />} title={card.label} source="ai_knowledge">
          <div className="quick-look-grid">
            <section>
              <h4>نکات مثبت</h4>
              <ul>{card.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
            <section>
              <h4>قبل از خرید</h4>
              <ul>{card.inPersonChecks.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          </div>
          {card.weaknesses.length > 0 && <p className="quick-look-caveat">{card.weaknesses[0]}</p>}
        </CardShell>
      );

    case "mall_guide":
      return (
        <CardShell icon={<Route size={17} />} title="کارت مراجعه" source="dataset">
          <strong className="mall-shop-name">{card.shop.displayName}</strong>
          <ul className="directions-list">{card.directions.map((item) => <li key={item}>{item}</li>)}</ul>
          {card.offer && (
            <div className="visit-offer-summary">
              <span>قیمت ثبت‌شده: {formatPrice(card.offer.offer.price)}</span>
              <span>آخرین تغییر قیمت: {formatDate(card.offer.offer.priceUpdatedAt)}</span>
              <span>{openLabel(card.offer.openNow)} · {stockLabel(card.offer.offer.stock)}</span>
            </div>
          )}
          {card.inquiry && (
            <p className="quiet-note">
              استعلام نمونه‌سازی: {card.inquiry.status === "no_answer" ? "بی‌پاسخ" : card.inquiry.answer?.inStock ? "پاسخ موجود" : "پاسخ ناموجود"}؛ تماس واقعی انجام نشده.
            </p>
          )}
          {card.backup && (
            <div className="visit-backup">
              <strong>پشتیبان: {card.backup.shop.displayName}</strong>
              <span>{formatPrice(card.backup.offer.price)} · {formatDistance(card.backup.distanceKm)} · {stockLabel(card.backup.offer.stock)}</span>
            </div>
          )}
          {directionsUrl(card.shop.lat, card.shop.lng) && (
            <a className="text-link" href={directionsUrl(card.shop.lat, card.shop.lng) ?? "#"} target="_blank" rel="noreferrer">
              مسیر تا پاساژ <ArrowUpLeft size={15} />
            </a>
          )}
        </CardShell>
      );

    case "web_results":
      return (
        <CardShell icon={<ExternalLink size={16} />} title="نتایج تکمیلی وب" source="web">
          <div className="web-results">
            {card.results.slice(0, 3).map((result) => (
              <a href={result.url} key={result.url} target="_blank" rel="noreferrer" className="web-result">
                <strong>{result.title}</strong>
                <span>{result.snippet}</span>
              </a>
            ))}
            {!card.results.length && <EmptyResults>نتیجه‌ای از وب دریافت نشد.</EmptyResults>}
          </div>
        </CardShell>
      );
  }
}

function CardShell({
  icon,
  title,
  source,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  source: Parameters<typeof sourceLabel>[0];
  children: React.ReactNode;
}) {
  return (
    <section className="result-card">
      <div className="result-card-header">
        <div className="result-card-title"><span>{icon}</span><h3>{title}</h3></div>
        <SourceTag source={source} />
      </div>
      {children}
    </section>
  );
}

function SourceTag({ source }: { source: Parameters<typeof sourceLabel>[0] }) {
  return <span className={`source-tag source-${source}`}>{sourceLabel(source)}</span>;
}

function ProductOption({ product, onChoose }: { product: Product; onChoose: (product: Product) => void }) {
  const image = product.images?.[0];
  return (
    <article className="product-option">
      <div className="product-thumb">
        {image ? <img src={image} alt="" loading="lazy" /> : <Store size={20} />}
      </div>
      <div className="product-copy">
        <strong>{product.titleFa}</strong>
        <span>{[product.brand, product.category].filter(Boolean).join(" · ") || "جزئیات بیشتر نامشخص"}</span>
      </div>
      <button type="button" className="small-action" onClick={() => onChoose(product)}>دیدن فروشگاه‌ها</button>
    </article>
  );
}

function ShopResultsCard({
  title,
  results,
  source,
  selectedOfferIds,
  onAskInquiry,
  onToggleCompare,
  onPrepareVisit,
}: {
  title: string;
  results: ShopResult[];
  source: Parameters<typeof sourceLabel>[0];
  selectedOfferIds: string[];
  onAskInquiry: (result: ShopResult) => void;
  onToggleCompare: (result: ShopResult) => void;
  onPrepareVisit: (result: ShopResult) => void;
}) {
  return (
    <CardShell icon={<Store size={17} />} title={title} source={source}>
      <ShopResultList
        results={results}
        selectedOfferIds={selectedOfferIds}
        onAskInquiry={onAskInquiry}
        onToggleCompare={onToggleCompare}
        onPrepareVisit={onPrepareVisit}
      />
    </CardShell>
  );
}

function ShopResultList({
  results,
  selectedOfferIds,
  onAskInquiry,
  onToggleCompare,
  onPrepareVisit,
}: {
  results: ShopResult[];
  selectedOfferIds: string[];
  onAskInquiry: (result: ShopResult) => void;
  onToggleCompare: (result: ShopResult) => void;
  onPrepareVisit: (result: ShopResult) => void;
}) {
  if (!results.length) return <EmptyResults>با این فیلترها فروشگاهی پیدا نشد. شعاع را بیشتر کن یا فیلتر بازبودن را بردار.</EmptyResults>;

  return (
    <div className="shop-results">
      {results.slice(0, 3).map((result, index) => {
        const shop = result.shop;
        const offerId = result.offer?.id;
        const url = directionsUrl(shop.lat, shop.lng);
        const isSelected = offerId ? selectedOfferIds.includes(offerId) : false;
        const open = result.openNow.value;
        const freshness = result.offer.priceFreshness?.level;
        const freshnessLabel = result.offer.priceFreshness?.label;
        return (
          <article className="shop-result" key={offerId ?? `${shop.id}-${result.offer.productId}-${index}`}>
            <div className="shop-result-top">
              <div className="shop-number">{String(index + 1).padStart(2, "۰")}</div>
              <div className="shop-main">
                <h4>{shop.displayName}</h4>
                <p className="shop-address">
                  {shop.mall ? `${shop.mall} · ` : ""}{shop.floor ? `${shop.floor} · ` : ""}
                  {shop.addressText || "آدرس نامشخص"}
                </p>
              </div>
              <span className={`open-state ${open === true ? "is-open" : open === false ? "is-closed" : "is-unknown"}`}>
                <span />{openLabel(result.openNow)}
              </span>
            </div>

            <div className="shop-price-row">
              <strong>{formatPrice(result.offer.price, result.offer.priceUnit)}</strong>
              <span><MapPin size={13} /> {formatDistance(result.distanceKm)}</span>
              <span className="offer-id">
                {offerId ? `آفر #${offerId.slice(-6)}` : "شناسه‌ی آفر قدیمی"}
              </span>
            </div>

            {freshness && (
              <div className={`freshness-badge-row freshness-${freshness}`}>
                <span className="freshness-dot" />
                <span>تازگی قیمت: {freshnessLabel}</span>
                {freshness === "stale" && <span className="freshness-hint">(پیشنهاد: استعلام پیش از حرکت)</span>}
              </div>
            )}

            <p className="shop-reason">{result.reasons[0] || "آفر این کالا در دیتاست ترب ثبت شده است."}</p>

            <div className="offer-facts">
              <span><CalendarClock size={13} /> آخرین تغییر قیمت: {formatDate(result.offer.priceUpdatedAt)}</span>
              <span className="stock-status"><PackageCheck size={13} /> {stockLabel(result.offer.stock)}</span>
              {result.offer.warranty?.months && (
                <span><ShieldCheck size={13} /> ضمانت {result.offer.warranty.months} ماهه</span>
              )}
            </div>

            {(shop.installment !== false || shop.tarobPayInStore !== false || shop.expressDelivery === true) && (
              <div className="shop-benefits">
                {shop.installment === true && <span>قسطی حضوری</span>}
                {shop.installment == null && <span>قسطی حضوری: نامشخص</span>}
                {shop.tarobPayInStore === true && <span>ترب‌پی حضوری</span>}
                {shop.tarobPayInStore == null && <span>ترب‌پی حضوری: نامشخص</span>}
                {shop.expressDelivery && <span>ارسال فوری</span>}
              </div>
            )}

            <div className="shop-actions">
              {url ? (
                <a className="route-action" href={url} target="_blank" rel="noreferrer">
                  <Navigation size={15} /> مسیر
                </a>
              ) : <span className="muted-action"><MapPin size={14} /> مسیر نامشخص</span>}
              <button type="button" className="link-action" disabled={!offerId} onClick={() => onAskInquiry(result)}>
                استعلام نمونه‌سازی
              </button>
              <button type="button" className="link-action" disabled={!offerId} onClick={() => onPrepareVisit(result)}>
                کارت مراجعه
              </button>
              <button
                type="button"
                className={`compare-action ${isSelected ? "selected" : ""}`}
                aria-pressed={isSelected}
                disabled={!offerId}
                onClick={() => onToggleCompare(result)}
              >
                {isSelected ? "انتخاب شد" : "مقایسه"}
              </button>
            </div>
          </article>
        );
      })}
      <p className="dataset-caveat"><Clock3 size={13} /> قیمت ثبت‌شده با موجودی یکی نیست؛ قبل از مراجعه استعلام بگیر.</p>
    </div>
  );
}

function EmptyResults({ children }: { children: React.ReactNode }) {
  return <div className="empty-results"><CircleHelp size={16} /><span>{children}</span></div>;
}

// -------------------------------------------------------------
// Component 1: MessageDraftCardComponent
// -------------------------------------------------------------
function MessageDraftCardComponent({
  card,
  onConfirmDraft,
  onCancelInquiry,
}: {
  card: MessageDraftCard;
  onConfirmDraft?: (draftId: string, editedText?: string) => void;
  onCancelInquiry?: (inquiryId: string) => void;
}) {
  const [editedText, setEditedText] = useState(card.message);
  const [isEditing, setIsEditing] = useState(false);
  const [confirmed, setConfirmed] = useState(card.confirmed);

  const channelNames: Record<string, string> = {
    panel: "پنل ترب فروشنده",
    sms: "پیامک شبیه‌سازی‌شده",
    chat: "گفتگوی شبیه‌سازی‌شده",
    ai_call: "تماس هوش مصنوعی شبیه‌سازی‌شده",
  };

  return (
    <section className="result-card message-draft-card">
      <div className="result-card-header">
        <div className="result-card-title">
          <span><MailQuestion size={17} /></span>
          <h3>پیش‌نویس استعلام از فروشنده</h3>
        </div>
        <SourceTag source="simulated" />
      </div>

      <div className="draft-body">
        <div className="draft-meta">
          <div className="draft-shop-info">
            <strong>{card.shop.displayName}</strong>
            <span className="draft-channel-pill">
              کانال: {channelNames[card.channel] || card.channel}
            </span>
          </div>
          <span className="draft-product-title">{card.product.titleFa}</span>
        </div>

        {card.warning && (
          <div className="draft-warning">
            <AlertTriangle size={15} />
            <span>{card.warning}</span>
          </div>
        )}

        <div className="draft-details-row">
          {card.requests?.etaMinutes != null && (
            <span className="draft-detail-badge">
              <Clock3 size={12} /> زمان تخمینی رسیدن: {card.requests.etaMinutes} دقیقه
            </span>
          )}
          {card.requests?.holdRequested && (
            <span className="draft-detail-badge">
              <ShieldCheck size={12} /> درخواست نگه‌داشت موقت کالا
            </span>
          )}
          {card.requests?.sizeOrColor && (
            <span className="draft-detail-badge">
              مشخصات: {card.requests.sizeOrColor}
            </span>
          )}
        </div>

        <div className="draft-message-box">
          <div className="draft-box-header">
            <label htmlFor={`draft-text-${card.inquiryId}`}>متن پیام به فروشنده:</label>
            {!confirmed && (
              <button
                type="button"
                className="draft-edit-toggle"
                onClick={() => setIsEditing(!isEditing)}
              >
                {isEditing ? "اتمام ویرایش" : "ویرایش متن"}
              </button>
            )}
          </div>
          {isEditing && !confirmed ? (
            <textarea
              id={`draft-text-${card.inquiryId}`}
              className="draft-textarea"
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
              rows={3}
            />
          ) : (
            <p className="draft-text-preview">{editedText}</p>
          )}
        </div>

        <div className="draft-notice">
          <CircleHelp size={13} />
          <span>ارتباط ۱۰۰٪ شبیه‌سازی‌شده است. هیچ پیامک یا تماس واقعی ارسال نمی‌شود و شماره‌ای نمایش داده نمی‌شود.</span>
        </div>

        {!confirmed ? (
          <div className="draft-actions">
            <button
              type="button"
              className="confirm-inquiry-btn"
              onClick={() => {
                setConfirmed(true);
                onConfirmDraft?.(card.inquiryId, editedText);
              }}
            >
              <Send size={14} /> تأیید و ارسال استعلام
            </button>
            <button
              type="button"
              className="cancel-inquiry-btn"
              onClick={() => onCancelInquiry?.(card.inquiryId)}
            >
              انصراف
            </button>
          </div>
        ) : (
          <div className="draft-confirmed-badge">
            <CheckCircle2 size={15} /> استعلام با تأیید شما ارسال شد.
          </div>
        )}
      </div>
    </section>
  );
}

// -------------------------------------------------------------
// Component 2: InquiryBatchCardComponent
// -------------------------------------------------------------
function InquiryBatchCardComponent({
  card,
  onCancelInquiry,
}: {
  card: InquiryBatchCard;
  onCancelInquiry?: (inquiryId: string) => void;
}) {
  const channelNames: Record<string, string> = {
    panel: "پنل ترب",
    sms: "پیامک",
    chat: "گفتگو",
    ai_call: "تماس صوتی",
  };

  const statusLabels: Record<string, string> = {
    draft: "پیش‌نویس",
    sent: "ارسال شد",
    delivered: "تحویل شد",
    read: "مشاهده شد",
    answered: "پاسخ دریافت شد",
    no_answer: "بی‌پاسخ / منقضی",
    cancelled: "لغو شد",
  };

  return (
    <section className="result-card inquiry-batch-card">
      <div className="result-card-header">
        <div className="result-card-title">
          <span><Layers size={17} /></span>
          <h3>استعلام دسته‌ای ({card.items.length} فروشگاه)</h3>
        </div>
        <SourceTag source="simulated" />
      </div>

      <p className="batch-subtitle">
        ارسال هم‌زمان به چند فروشگاه؛ با اولین تأیید موجودی، باقی استعلام‌ها به‌طور خودکار لغو می‌شوند.
      </p>

      <div className="batch-items-list">
        {card.items.map((item) => (
          <article className="batch-item-row" key={item.inquiryId}>
            <div className="batch-item-info">
              <strong>{item.shop.displayName}</strong>
              <div className="batch-item-tags">
                <span className="batch-channel-tag">{channelNames[item.channel] || item.channel}</span>
                <span className={`batch-status-pill status-${item.status}`}>
                  {statusLabels[item.status] || item.status}
                </span>
                {item.answer?.inStock === true && <span className="batch-stock-tag in-stock">موجود</span>}
                {item.answer?.inStock === false && <span className="batch-stock-tag out-of-stock">ناموجود</span>}
              </div>
            </div>
            {item.status !== "cancelled" && item.status !== "answered" && item.status !== "no_answer" && (
              <button
                type="button"
                className="batch-cancel-btn"
                onClick={() => onCancelInquiry?.(item.inquiryId)}
              >
                لغو
              </button>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

// -------------------------------------------------------------
// Component 3: EnhancedInquiryCardComponent
// -------------------------------------------------------------
function EnhancedInquiryCardComponent({
  card,
  onCancelInquiry,
}: {
  card: Extract<AssistantCard, { kind: "inquiry" }>;
  onCancelInquiry?: (inquiryId: string) => void;
}) {
  const [showTranscript, setShowTranscript] = useState(false);
  const inquiry = card.inquiry;
  const answer = inquiry.answer;
  const channel = inquiry.channel || "panel";

  const channelNames: Record<string, string> = {
    panel: "پنل ترب فروشنده",
    sms: "پیامک شبیه‌سازی‌شده",
    chat: "گفتگوی شبیه‌سازی‌شده",
    ai_call: "تماس هوش مصنوعی شبیه‌سازی‌شده",
  };

  const isAnswered = inquiry.status === "answered";
  const inStock = answer?.inStock;
  const priceChanged = answer?.priceChanged;

  const headerTitle =
    inquiry.status === "no_answer"
      ? "پاسخی از فروشگاه دریافت نشد (منقضی)"
      : inquiry.status === "cancelled"
      ? "استعلام لغو شد"
      : inquiry.status === "draft"
      ? "پیش‌نویس استعلام"
      : isAnswered
      ? inStock
        ? priceChanged
          ? "پاسخ فروشنده: موجود با تغییر قیمت"
          : "پاسخ فروشنده: موجود در فروشگاه"
        : "پاسخ فروشنده: ناموجود"
      : "در حال پیگیری استعلام...";

  const statusClass =
    inquiry.status === "cancelled"
      ? "status-cancelled"
      : inquiry.status === "no_answer"
      ? "status-no-answer"
      : isAnswered
      ? inStock
        ? "status-in-stock"
        : "status-out-stock"
      : "status-pending";

  return (
    <section className={`result-card enhanced-inquiry-card ${statusClass}`}>
      <div className="result-card-header">
        <div className="result-card-title">
          <span><BadgeCheck size={18} /></span>
          <h3>{headerTitle}</h3>
        </div>
        <SourceTag source="simulated" />
      </div>

      <div className="inquiry-content">
        <div className="inquiry-header-row">
          <span className="inquiry-channel-pill">
            کانال: {channelNames[channel] || channel}
          </span>
          <span className="inquiry-sim-badge">نمونه‌سازی / بدون تماس واقعی</span>
        </div>

        {/* Dataset price vs Seller price distinction */}
        <div className="price-comparison-box">
          <div className="price-item dataset-price">
            <span className="price-item-label">قیمت ثبت‌شده در ترب (دیتاست):</span>
            <strong className="price-item-val">
              {inquiry.datasetPrice ? formatPrice(inquiry.datasetPrice) : "ثبت نشده"}
            </strong>
          </div>
          {answer?.price ? (
            <div className={`price-item seller-price ${priceChanged ? "price-different" : ""}`}>
              <span className="price-item-label">قیمت اعلامی فروشنده (نمونه‌سازی):</span>
              <strong className="price-item-val">{formatPrice(answer.price)}</strong>
              {priceChanged && <span className="price-change-tag">تغییر نسبت به دیتاست</span>}
            </div>
          ) : null}
        </div>
        <p className="price-guarantee-note">
          قیمت دیتاست ترب دست‌نخورده باقی مانده است. پاسخ فروشنده به‌صورت نمونه‌سازی و جداگانه نمایش داده می‌شود.
        </p>

        {/* Note / response from seller */}
        {answer?.note && (
          <div className="seller-note-box">
            <strong>توضیحات فروشنده:</strong>
            <p>{answer.note}</p>
          </div>
        )}

        {answer?.holdConfirmed && (
          <div className="hold-badge">
            <ShieldCheck size={14} /> نگه‌داشت موقت کالا تا زمان رسیدن شما تأیید شد.
          </div>
        )}

        {/* 5-step timeline */}
        {inquiry.timeline && inquiry.timeline.length > 0 && (
          <div className="inquiry-timeline">
            <h4>روند پیگیری استعلام</h4>
            <div className="timeline-steps">
              {inquiry.timeline.map((step, idx) => (
                <div className={`timeline-step step-${step.status || step.stage}`} key={idx}>
                  <div className="step-indicator">
                    <span className="step-dot" />
                    {idx < inquiry.timeline!.length - 1 && <span className="step-line" />}
                  </div>
                  <div className="step-info">
                    <span className="step-title">{step.title || step.label}</span>
                    <span className="step-time">
                      {step.timestamp
                        ? new Date(step.timestamp).toLocaleTimeString("fa-IR", {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })
                        : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* AI Call Transcript if available */}
        {answer?.transcript && (
          <div className="call-transcript-container">
            <button
              type="button"
              className="transcript-toggle-btn"
              onClick={() => setShowTranscript(!showTranscript)}
            >
              <PhoneCall size={14} />
              <span>{showTranscript ? "بستن متن مکالمه هوش مصنوعی" : "مشاهده‌ی متن مکالمه هوش مصنوعی با فروشنده"}</span>
            </button>
            {showTranscript && (
              <div className="transcript-box">
                <p className="transcript-note">متن گفتگوی خودکار صوتی Let Google Call (شبیه‌سازی‌شده):</p>
                <div className="transcript-dialogue">
                  {answer.transcript.split("\n").map((line, lIdx) => {
                    const isAi = line.startsWith("هوش مصنوعی:") || line.startsWith("دستیار:");
                    const isSeller = line.startsWith("فروشنده:");
                    return (
                      <div className={`dialogue-line ${isAi ? "line-ai" : isSeller ? "line-seller" : ""}`} key={lIdx}>
                        {line}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Cancel button if pending */}
        {(inquiry.status === "draft" || inquiry.status === "sent" || inquiry.status === "delivered" || inquiry.status === "read") && (
          <div className="inquiry-actions-row">
            <button
              type="button"
              className="cancel-inquiry-btn"
              onClick={() => onCancelInquiry?.(inquiry.id)}
            >
              لغو استعلام
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
