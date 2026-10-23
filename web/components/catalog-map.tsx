"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { rememberContactSelection } from "@/lib/contact";
import { MapPin, Store } from "lucide-react";
import { resolveLocation } from "@/lib/api";
import type { ConversationState, Product, ShopResult } from "@/lib/contracts";
import { formatDate, formatDistance, formatNumber, formatPrice, openLabel } from "@/lib/format";

const MapView = dynamic(() => import("@/components/leaflet-map"), { ssr: false, loading: () => <div className="offers-map-loading">در حال بارگذاری نقشه…</div> });
const API_ROOT = (process.env.NEXT_PUBLIC_AGENT_API ?? "").replace(/\/$/, ""), WORKSPACE = "torob-in-person.workspace.v1";
const DEFAULT = { lat: 35.7219, lng: 51.4097, label: "مرکز پیش‌فرض تهران" };
const SHOP_PAGE_SIZE = 30;
type Point = { lat: number; lng: number; label: string };
type MapResponse = { source: "dataset"; results: ShopResult[]; shop_count: number; offer_count: number;
  product_count: number; missing_coordinates_count: number; matched_offer_count: number; products: { id: string; titleFa: string }[] };
function numeric(params: URLSearchParams, key: string, fallback: number, min: number, max: number) {
  const value = params.has(key) ? Number(params.get(key)) : NaN;
  return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
}
function located(result: ShopResult) {
  const { lat, lng } = result.shop;
  return typeof lat === "number" && Number.isFinite(lat) && Math.abs(lat) <= 90
    && typeof lng === "number" && Number.isFinite(lng) && Math.abs(lng) <= 180;
}

export default function CatalogMap({ queryString, standalone = false }: { queryString: string; standalone?: boolean }) {
  const router = useRouter(), pathname = usePathname();
  const [params, setParams] = useState<string | null>(null), [data, setData] = useState<MapResponse | null>(null);
  const [center, setCenter] = useState<Point>(DEFAULT), [area, setArea] = useState(DEFAULT.label);
  const [latitude, setLatitude] = useState(String(DEFAULT.lat)), [longitude, setLongitude] = useState(String(DEFAULT.lng));
  const [radius, setRadius] = useState(4), [busy, setBusy] = useState(true), [resolving, setResolving] = useState(false);
  const [error, setError] = useState(""), [filterError, setFilterError] = useState("");
  const [selectedShop, setSelectedShop] = useState<string | null>(null), [retry, setRetry] = useState(0);
  const [resultsUrl, setResultsUrl] = useState("/products"), [listMode, setListMode] = useState<"all" | "located" | "missing">("all");
  const [shopPage, setShopPage] = useState(1);

  useEffect(() => {
    const query = new URLSearchParams(queryString);
    const hasSearchContext = ["q", "category", "brand", "product_ids", "productIds"].some(key => query.has(key));
    let conversation: ConversationState | null = null;
    let inheritPreferenceFilters = false;
    try {
      const saved = JSON.parse(localStorage.getItem(WORKSPACE) || "{}"); conversation = saved.conversation ?? null;
      const previous = localStorage.getItem("torob-last-results-url");
      if (standalone && !hasSearchContext && !query.has("q")) {
        if (previous?.startsWith("/products?")) new URLSearchParams(previous.split("?")[1]).forEach((value, key) => { if (!query.has(key)) query.set(key, value); });
        else if (saved.marketplaceProduct?.id) { query.set("product_ids", (saved.marketplaceProduct as Product).id); inheritPreferenceFilters = true; }
      }
      if (previous === "/products" || previous?.startsWith("/products?")) setResultsUrl(previous);
    } catch { /* URL search works even with malformed old browser state. */ }
    if (query.get("productIds") && !query.has("product_ids")) query.set("product_ids", query.get("productIds")!);
    query.delete("productIds"); query.delete("page"); query.delete("page_size");
    const point: Point = {
      lat: numeric(query, "lat", conversation?.location?.lat ?? DEFAULT.lat, -90, 90),
      lng: numeric(query, "lng", conversation?.location?.lng ?? DEFAULT.lng, -180, 180),
      label: query.get("location_label") || conversation?.location?.label || DEFAULT.label,
    };
    const nextRadius = numeric(query, "radius_km", conversation?.radiusKm ?? 4, 0, 100);
    query.set("lat", String(point.lat)); query.set("lng", String(point.lng)); query.set("radius_km", String(nextRadius)); query.set("location_label", point.label);
    if (!hasSearchContext && inheritPreferenceFilters && !query.has("max_price") && conversation?.budget) query.set("max_price", String(conversation.budget));
    if (!hasSearchContext && inheritPreferenceFilters) for (const [key, value] of Object.entries({ installment: conversation?.filters?.installment, express: conversation?.filters?.express, open_now: conversation?.filters?.openNow })) if (!query.has(key) && value) query.set(key, "true");
    setCenter(point); setArea(point.label); setLatitude(String(point.lat)); setLongitude(String(point.lng));
    setRadius(nextRadius); setParams(query.toString());
    if (["q", "category", "brand"].some(key => query.has(key))) {
      const backQuery = new URLSearchParams(query); backQuery.delete("all"); backQuery.delete("product_ids");
      const backUrl = `/products?${backQuery}`; setResultsUrl(backUrl);
      if (standalone) try { localStorage.setItem("torob-last-results-url", backUrl); } catch { /* The return link is sufficient without storage. */ }
    }
  }, [queryString, standalone]);
  useEffect(() => {
    if (params === null) return;
    const controller = new AbortController();
    async function load() {
      setBusy(true); setError(""); setSelectedShop(null); setShopPage(1);
      const query = new URLSearchParams(params!);
      for (const key of ["page", "page_size", "sort", "label", "location_label", "view"]) query.delete(key);
      if (!["q", "category", "brand", "product_ids"].some(key => query.get(key))) { setData(null); setError("ابتدا در صفحه محصولات جستجو کن یا یک محصول را انتخاب کن."); setBusy(false); return; }
      try {
        const response = await fetch(`${API_ROOT}/api/map/offers?${query}`, { signal: controller.signal, cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "دریافت فروشگاه‌ها ناموفق بود.");
        if (!Array.isArray(body.results)) throw new Error("پاسخ فروشگاه‌ها معتبر نیست."); setData(body as MapResponse);
      } catch (cause) { if (!controller.signal.aborted) { setData(null); setError(cause instanceof Error ? cause.message : "دریافت فروشگاه‌ها ناموفق بود."); } }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }
    void load(); return () => controller.abort();
  }, [params, retry]);

  function apply(point: Point) {
    if (params === null) return;
    const query = new URLSearchParams(params); query.set("lat", String(point.lat)); query.set("lng", String(point.lng)); query.set("radius_km", String(radius)); query.set("location_label", point.label);
    // A resolved area selects the radius centre; it is not a literal shop-city name.
    query.delete("city"); query.delete("page"); router.push(`${pathname}?${query}`, { scroll: false });
    setCenter(point); setArea(point.label); setLatitude(String(point.lat)); setLongitude(String(point.lng)); setParams(query.toString()); setFilterError("");
    const backQuery = new URLSearchParams(resultsUrl.split("?")[1] ?? "");
    backQuery.delete("city");
    for (const key of ["lat", "lng", "radius_km", "location_label"]) backQuery.set(key, query.get(key)!);
    const backUrl = `/products?${backQuery}`; setResultsUrl(backUrl);
    try { localStorage.setItem("torob-last-results-url", backUrl); } catch { /* The current page link still preserves the location. */ }
    try { const saved = JSON.parse(localStorage.getItem(WORKSPACE) || "{}"); if (saved.conversation) {
      saved.conversation.location = point; saved.conversation.radiusKm = radius; localStorage.setItem(WORKSPACE, JSON.stringify(saved));
    } } catch { /* Location remains persisted in the URL. */ }
  }
  async function applyArea(event: React.FormEvent) {
    event.preventDefault(); setFilterError(""); if (!area.trim()) { setFilterError("نام شهر یا محله را وارد کن."); return; }
    if (area.trim() === center.label) { apply(center); return; } setResolving(true);
    try { const point = await resolveLocation(area.trim()); apply({ ...point, label: point.label || area.trim() }); }
    catch (cause) { setFilterError(cause instanceof Error ? cause.message : "محدوده پیدا نشد؛ مختصات دقیق را وارد کن."); }
    finally { setResolving(false); }
  }
  function applyCoordinates() {
    const lat = Number(latitude), lng = Number(longitude);
    if (!latitude.trim() || !longitude.trim() || !Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) { setFilterError("عرض جغرافیایی باید بین ۹۰− تا ۹۰ و طول بین ۱۸۰− تا ۱۸۰ باشد."); return; }
    apply({ lat, lng, label: `مختصات انتخابی ${lat}, ${lng}` });
  }
  const groups = useMemo(() => {
    const byShop = new Map<string, ShopResult[]>(); for (const result of data?.results ?? []) { const list = byShop.get(result.shop.id) ?? []; list.push(result); byShop.set(result.shop.id, list); } return [...byShop.values()];
  }, [data]);
  const displayed = groups.filter(group => listMode === "all" || (listMode === "located" ? located(group[0]) : !located(group[0])));
  const pageCount = Math.max(1, Math.ceil(displayed.length / SHOP_PAGE_SIZE));
  const visibleShops = displayed.slice((shopPage - 1) * SHOP_PAGE_SIZE, shopPage * SHOP_PAGE_SIZE);
  function selectShop(id: string) {
    const group = groups.find(items => items[0].shop.id === id);
    if (!group) return;
    const mode = listMode === "missing" && located(group[0]) ? "located"
      : listMode === "located" && !located(group[0]) ? "missing" : listMode;
    const candidates = groups.filter(items => mode === "all" || (mode === "located" ? located(items[0]) : !located(items[0])));
    setListMode(mode); setShopPage(Math.floor(candidates.findIndex(items => items[0].shop.id === id) / SHOP_PAGE_SIZE) + 1);
    setSelectedShop(id);
  }
  const productNames = useMemo(() => Object.fromEntries((data?.products ?? []).map(product => [product.id, product.titleFa])), [data]);
  const markers = useMemo(() => (data?.results ?? []).filter(located), [data]);
  const queryLabel = params ? new URLSearchParams(params).get("q") : "";
  const heading = queryLabel || (data?.products.length === 1 ? data.products[0].titleFa : "محصولات نتایج جستجو");
  return <section className="catalog-map" dir="rtl" aria-label="فروشگاه‌های مرتبط با نتایج">
    <section className="map-page-heading"><h2>فروشگاه‌های مرتبط روی نقشه</h2><p>{heading}</p>
      <p aria-live="polite" data-testid="map-counts">{data ? `${formatNumber(data.shop_count)} فروشگاه · ${formatNumber(data.offer_count)} آفر · ${formatNumber(data.product_count)} محصول` : "در انتظار دریافت فروشگاه‌ها"}</p>
      <form className="map-location-form" onSubmit={event => void applyArea(event)}>
        <label><MapPin size={16} /> شهر یا محدوده<input value={area} onChange={event => setArea(event.target.value)} placeholder="مثلاً تهران، میدان ولیعصر" /></label>
        <label>شعاع جستجو: {formatNumber(radius)} کیلومتر<input aria-label="شعاع جستجو" type="range" min="0" max="100" step="1" value={radius} onChange={event => setRadius(Number(event.target.value))} /></label>
        <button type="submit" disabled={busy || resolving}>{resolving ? "یافتن محدوده…" : "اعمال محدوده"}</button>
      </form>
      <details className="map-coordinate-controls"><summary>انتخاب مرکز با مختصات دقیق</summary><div>
        <label>عرض جغرافیایی<input inputMode="decimal" dir="ltr" value={latitude} onChange={event => setLatitude(event.target.value)} /></label>
        <label>طول جغرافیایی<input inputMode="decimal" dir="ltr" value={longitude} onChange={event => setLongitude(event.target.value)} /></label>
        <button type="button" disabled={busy || resolving} onClick={applyCoordinates}>اعمال مختصات</button>
      </div></details>
      <small>مرکز فعلی: {center.label} · مختصات فروشگاه‌ها فقط از دیتاست است. قیمت و موجودی فعلی تأیید نشده‌اند.</small>
      {filterError && <p role="alert" className="map-filter-error">{filterError}</p>}
    </section>
    {busy ? <div className="catalog-state" role="status">در حال دریافت فروشگاه‌ها و پیشنهادهای مرتبط از دیتاست…</div>
      : error ? <div className="catalog-state" role="alert"><p>{error}</p><button onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button><Link href={resultsUrl}>انتخاب محصول یا تغییر جستجو</Link></div>
      : !data?.shop_count ? <div className="catalog-state"><p>فروشگاه مرتبطی در این محدوده و با فیلترهای فعلی پیدا نشد.</p><p>شعاع را بیشتر کن، محدوده را تغییر بده یا فیلترهای نتایج را اصلاح کن.</p><Link href={resultsUrl}>اصلاح فیلترهای محصولات</Link></div>
      : <div className="map-layout"><section className="map-canvas-shell" aria-label="نقشه فروشگاه‌ها">
          {markers.length ? <MapView center={center} results={markers} radiusKm={Number(new URLSearchParams(params!).get("radius_km"))} selectedShopId={selectedShop} onSelectShop={selectShop} productNames={productNames} />
            : <div className="catalog-state"><p>مختصات معتبری برای این فروشگاه‌ها ثبت نشده است.</p><p>پیشنهادها در فهرست آمده؛ مکان یا فاصله تخمین زده نشده است.</p></div>}
          <small>هر نشانگر یک فروشگاه است. گروه‌های پرتراکم با بزرگ‌نمایی باز می‌شوند.</small>
        </section><aside className="map-shop-list" aria-label="فهرست فروشگاه‌ها"><h2><Store size={17} /> {formatNumber(data.shop_count)} فروشگاه</h2>
          <div className="map-list-tabs" role="group" aria-label="نوع موقعیت فروشگاه">{([["all", "همه"], ["located", "روی نقشه"], ["missing", "بدون مختصات"]] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={listMode === value} onClick={() => { setListMode(value); setShopPage(1); }}>{label}</button>)}</div>
          {data.missing_coordinates_count > 0 && <p className="map-missing-note">{formatNumber(data.missing_coordinates_count)} فروشگاه بدون مختصات معتبر، جدا از فروشگاه‌های داخل شعاع آمده‌اند؛ قرارگیری آن‌ها در محدوده قابل تأیید نیست.</p>}
          {!displayed.length && <p className="map-missing-note">فروشگاهی در این بخش وجود ندارد.</p>}
          {visibleShops.map(group => { const first = group[0], hasLocation = located(first); return <article key={first.shop.id} data-shop-id={first.shop.id} className={`map-shop-card ${selectedShop === first.shop.id ? "selected" : ""}`}>
              <button type="button" className="map-shop-select" aria-pressed={selectedShop === first.shop.id} onClick={() => selectShop(first.shop.id)}><b>{first.shop.displayName}</b><span>{hasLocation ? formatDistance(first.distanceKm) : "مختصات ثبت نشده؛ فاصله نامشخص"} · {openLabel(first.openNow)}</span></button>
              <small>{first.shop.addressText || "نشانی ثبت نشده"}</small><small>{formatNumber(group.length)} آفر برای {formatNumber(new Set(group.map(result => result.offer.productId)).size)} محصول</small>
              {group.map((result, index) => <div className="map-list-offer" key={result.offer.id ?? index}><Link href={`/products/${encodeURIComponent(result.offer.productId)}`}>{productNames[result.offer.productId] || "جزئیات محصول"}</Link><b>{formatPrice(result.offer.price, result.offer.priceUnit)}</b><small>قیمت دیتاست · {formatDate(result.offer.priceUpdatedAt)} · موجودی تأییدنشده</small>{result.offer.id && <Link className="offer-contact-action" href={`/contact?offer_id=${encodeURIComponent(result.offer.id)}`} onClick={() => rememberContactSelection({ product: { id: result.offer.productId, titleFa: productNames[result.offer.productId] || "محصول انتخاب‌شده" }, shop: result.shop, offer: result.offer })}>بررسی قیمت و تماس با فروشگاه</Link>}</div>)}
            </article>; })}
          {pageCount > 1 && <nav className="map-list-tabs" aria-label="صفحه‌بندی فروشگاه‌ها">
            <button type="button" disabled={shopPage <= 1} onClick={() => setShopPage(page => page - 1)}>صفحه قبل فروشگاه‌ها</button>
            <span aria-live="polite">صفحه {formatNumber(shopPage)} از {formatNumber(pageCount)} · {formatNumber(displayed.length)} فروشگاه</span>
            <button type="button" disabled={shopPage >= pageCount} onClick={() => setShopPage(page => page + 1)}>صفحه بعد فروشگاه‌ها</button>
          </nav>}
        </aside></div>}
  </section>;
}
