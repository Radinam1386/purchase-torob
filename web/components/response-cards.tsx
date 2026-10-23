import {
  ArrowUpLeft,
  BadgeCheck,
  Building2,
  CalendarClock,
  CircleHelp,
  Clock3,
  ExternalLink,
  MapPin,
  Navigation,
  PackageCheck,
  PackageSearch,
  Route,
  ShieldCheck,
  Store,
} from "lucide-react";

import {
  directionsUrl,
  formatDate,
  formatDistance,
  formatPrice,
  openLabel,
  sourceLabel,
  stockLabel,
} from "@/lib/format";
import type { AssistantCard, Product, ShopResult } from "@/lib/contracts";

interface CardActions {
  selectedShopIds: string[];
  onChooseProduct: (product: Product) => void;
  onAskInquiry: (result: ShopResult) => void;
  onToggleCompare: (result: ShopResult) => void;
}

interface ResponseCardsProps extends CardActions {
  cards: AssistantCard[];
}

export function ResponseCards({
  cards,
  selectedShopIds,
  onChooseProduct,
  onAskInquiry,
  onToggleCompare,
}: ResponseCardsProps) {
  if (!cards.length) return null;

  return (
    <div className="response-cards">
      {cards.map((card, index) => (
        <CardRenderer
          key={`${card.kind}-${index}`}
          card={card}
          selectedShopIds={selectedShopIds}
          onChooseProduct={onChooseProduct}
          onAskInquiry={onAskInquiry}
          onToggleCompare={onToggleCompare}
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
  selectedShopIds,
  onChooseProduct,
  onAskInquiry,
  onToggleCompare,
}: CardRendererProps) {
  switch (card.kind) {
    case "product_cards":
      return (
        <CardShell icon={<PackageSearch size={17} />} title="مدل‌های پیدا شده" source={card.source}>
          <div className="product-options">
            {card.products.map((product) => (
              <ProductOption key={product.id} product={product} onChoose={onChooseProduct} />
            ))}
            {!card.products.length && <EmptyResults>مدلی با این مشخصات پیدا نشد.</EmptyResults>}
          </div>
        </CardShell>
      );

    case "shop_cards":
      return (
        <ShopResultsCard
          title="فروشگاه‌های دارای آفر"
          results={card.results}
          source={card.source}
          selectedShopIds={selectedShopIds}
          onAskInquiry={onAskInquiry}
          onToggleCompare={onToggleCompare}
        />
      );

    case "compare":
      return (
        <ShopResultsCard
          title="مقایسه‌ی فروشگاه‌ها"
          results={card.results}
          source={card.source}
          selectedShopIds={selectedShopIds}
          onAskInquiry={onAskInquiry}
          onToggleCompare={onToggleCompare}
        />
      );

    case "alternatives":
      return (
        <CardShell icon={<PackageCheck size={17} />} title="جایگزین‌های نزدیک" source={card.source}>
          {card.products.length > 0 && (
            <div className="product-options">
              {card.products.slice(0, 3).map((product) => (
                <ProductOption key={product.id} product={product} onChoose={onChooseProduct} />
              ))}
            </div>
          )}
          {card.results.length > 0 && (
            <ShopResultList
              results={card.results}
              selectedShopIds={selectedShopIds}
              onAskInquiry={onAskInquiry}
              onToggleCompare={onToggleCompare}
            />
          )}
          {!card.products.length && !card.results.length && (
            <EmptyResults>در این محدوده جایگزین ثبت‌شده‌ای پیدا نشد.</EmptyResults>
          )}
        </CardShell>
      );

    case "inquiry":
      return (
        <div className="inquiry-card" role="status">
          <span className="inquiry-icon"><BadgeCheck size={18} /></span>
          <div>
            <strong>استعلام نمونه‌سازی شد</strong>
            <p>هیچ تماس یا پیامی ارسال نشده؛ موجودی و قیمت هنوز تأیید نشده‌اند.</p>
          </div>
          <SourceTag source="simulated" />
        </div>
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
        <CardShell icon={<Route size={17} />} title="راهنمای داخل پاساژ" source="dataset">
          <strong className="mall-shop-name">{card.shop.displayName}</strong>
          <ul className="directions-list">{card.directions.map((item) => <li key={item}>{item}</li>)}</ul>
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
  selectedShopIds,
  onAskInquiry,
  onToggleCompare,
}: {
  title: string;
  results: ShopResult[];
  source: Parameters<typeof sourceLabel>[0];
  selectedShopIds: string[];
  onAskInquiry: (result: ShopResult) => void;
  onToggleCompare: (result: ShopResult) => void;
}) {
  return (
    <CardShell icon={<Store size={17} />} title={title} source={source}>
      <ShopResultList
        results={results}
        selectedShopIds={selectedShopIds}
        onAskInquiry={onAskInquiry}
        onToggleCompare={onToggleCompare}
      />
    </CardShell>
  );
}

function ShopResultList({
  results,
  selectedShopIds,
  onAskInquiry,
  onToggleCompare,
}: {
  results: ShopResult[];
  selectedShopIds: string[];
  onAskInquiry: (result: ShopResult) => void;
  onToggleCompare: (result: ShopResult) => void;
}) {
  if (!results.length) return <EmptyResults>با این فیلترها فروشگاهی پیدا نشد. شعاع را بیشتر کن یا فیلتر بازبودن را بردار.</EmptyResults>;

  return (
    <div className="shop-results">
      {results.slice(0, 3).map((result, index) => {
        const shop = result.shop;
        const url = directionsUrl(shop.lat, shop.lng);
        const isSelected = selectedShopIds.includes(shop.id);
        const open = result.openNow.value;
        return (
          <article className="shop-result" key={`${shop.id}-${result.offer.productId}-${index}`}>
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
            </div>

            <p className="shop-reason">{result.reasons[0] || "آفر این کالا در دیتاست ترب ثبت شده است."}</p>

            <div className="offer-facts">
              <span><CalendarClock size={13} /> آخرین تغییر قیمت: {formatDate(result.offer.priceUpdatedAt)}</span>
              <span className="stock-status"><PackageCheck size={13} /> {stockLabel(result.offer.stock)}</span>
              {result.offer.warranty?.months && (
                <span><ShieldCheck size={13} /> ضمانت {result.offer.warranty.months} ماهه</span>
              )}
            </div>

            {(shop.installment || shop.tarobPayInStore || shop.expressDelivery) && (
              <div className="shop-benefits">
                {shop.installment && <span>قسطی حضوری</span>}
                {shop.tarobPayInStore && <span>ترب‌پی حضوری</span>}
                {shop.expressDelivery && <span>ارسال فوری</span>}
              </div>
            )}

            <div className="shop-actions">
              {url ? (
                <a className="route-action" href={url} target="_blank" rel="noreferrer">
                  <Navigation size={15} /> مسیر
                </a>
              ) : <span className="muted-action"><MapPin size={14} /> مسیر نامشخص</span>}
              <button type="button" className="link-action" onClick={() => onAskInquiry(result)}>
                استعلام نمونه‌سازی
              </button>
              <button
                type="button"
                className={`compare-action ${isSelected ? "selected" : ""}`}
                aria-pressed={isSelected}
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
