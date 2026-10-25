"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowRight, BadgeCheck, MapPin, Store, X, ZoomIn } from "lucide-react";
import { formatDate, formatDistance, formatNumber, formatPrice, openLabel } from "@/lib/format";
import { rememberContactSelection } from "@/lib/contact";
import { LAST_RESULTS_KEY } from "@/lib/search-state";
import { MobileNav } from "@/components/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import type { ConversationState, Product, ShopResult } from "@/lib/contracts";

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [product, setProduct] = useState<Product | null>(null);
  const [minPrice, setMinPrice] = useState<number | null>(null);
  const [offers, setOffers] = useState<ShopResult[]>([]);
  const [back, setBack] = useState("/products");
  const [mapUrl, setMapUrl] = useState(`/map?product_ids=${encodeURIComponent(id)}`);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [offersError, setOffersError] = useState("");
  const [retry, setRetry] = useState(0);
  const [imageFailed, setImageFailed] = useState(false);
  const [zoomImage, setZoomImage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(""); setOffersError(""); setProduct(null); setOffers([]); setImageFailed(false);
    const mapParams = new URLSearchParams({ product_ids: id });
    try {
      const previous = localStorage.getItem(LAST_RESULTS_KEY);
      if (previous && /^\/products(?:\?|$)/.test(previous)) {
        setBack(previous);
        const params = new URL(previous, location.origin).searchParams;
        for (const key of ["min_price", "max_price", "lat", "lng", "radius_km", "city", "location", "installment", "express", "open_now"]) {
          if (params.has(key)) mapParams.set(key, params.get(key)!);
        }
      }
      const workspace = JSON.parse(localStorage.getItem("torob-in-person.workspace.v1") || "{}");
      const conversation = workspace.conversation as Partial<ConversationState> | undefined;
      if (conversation?.location && !mapParams.has("lat")) {
        mapParams.set("lat", String(conversation.location.lat)); mapParams.set("lng", String(conversation.location.lng));
      }
      if (!mapParams.has("radius_km")) mapParams.set("radius_km", String(conversation?.radiusKm ?? 4));
    } catch { /* Standalone product URLs work without saved context. */ }
    setMapUrl(`/map?${mapParams}`);
    async function load() {
      try {
        const response = await fetch(`/api/products/${encodeURIComponent(id)}`, { signal: controller.signal, cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "محصول در دیتاست پیدا نشد.");
        if (controller.signal.aborted) return;
        setProduct(body.product); setMinPrice(body.minPrice);
        try {
          const workspace = JSON.parse(localStorage.getItem("torob-in-person.workspace.v1") || "{}");
          if (workspace.conversation) {
            const changed = workspace.conversation.selectedProductId !== id;
            workspace.conversation.selectedProductId = id;
            workspace.conversation.preferences ||= {};
            workspace.conversation.preferences._advisor = { ...(workspace.conversation.preferences._advisor || {}), status: "selected_product" };
            workspace.conversation.preferences.searchProfile = { ...(workspace.conversation.preferences.searchProfile || {}), stage: "selected_product" };
            if (changed) { workspace.conversation.selectedShopIds = []; workspace.conversation.selectedOfferIds = []; }
            workspace.marketplaceProduct = body.product;
            localStorage.setItem("torob-in-person.workspace.v1", JSON.stringify(workspace));
          }
        } catch { /* Details remain usable without browser storage. */ }
        try {
          const result = await fetch(`/api/map/offers?${mapParams}`, { signal: controller.signal, cache: "no-store" });
          const body = await result.json();
          if (!result.ok) throw new Error(typeof body.detail === "string" ? body.detail : "دریافت پیشنهادهای فروشگاه‌ها انجام نشد.");
          if (!controller.signal.aborted) setOffers(body.results);
        } catch (problem) {
          if (!controller.signal.aborted) setOffersError(problem instanceof Error ? problem.message : "دریافت پیشنهادها انجام نشد.");
        }
      } catch (problem) {
        if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : "بارگذاری محصول انجام نشد.");
      } finally { if (!controller.signal.aborted) setBusy(false); }
    }
    void load();
    return () => controller.abort();
  }, [id, retry]);

  const shops = new Map<string, ShopResult[]>();
  for (const result of offers) {
    const group = shops.get(result.shop.id);
    if (group) group.push(result);
    else shops.set(result.shop.id, [result]);
  }
  const pricedOffers = offers.filter((result) => typeof result.offer.price === "number" && result.offer.price > 0);
  const cheapest = pricedOffers.length ? Math.min(...pricedOffers.map((result) => result.offer.price as number)) : null;
  const cheapestOfferIds = new Set(pricedOffers.filter((result) => result.offer.price === cheapest).map((result) => result.offer.id).filter(Boolean));
  return <main className="catalog-page detail-page" dir="rtl">
    <header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href="/chat">ادامه چت</Link><Link href={back}>نتایج جست‌وجو</Link></nav><ThemeToggle /></header>
    {error ? <div className="catalog-state" role="alert"><b>{error}</b><button onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button><Link href={back}>بازگشت به نتایج</Link></div> : busy ? <div className="catalog-state" aria-busy="true">در حال دریافت مشخصات و پیشنهادها…</div> : product && <>
      <div className="detail-head"><Link href={back}><ArrowRight size={16} /> بازگشت به نتایج با فیلترهای قبلی</Link><span className="eyebrow">اطلاعات محصول · دیتاست ترب</span><h1>{product.titleFa}</h1><p>{product.brand || "برند نامشخص"} · {product.category || "دسته نامشخص"}</p><div className="detail-price">{formatPrice(minPrice)}<small>کمترین قیمت ثبت‌شده در دیتاست؛ قیمت روز و موجودی تأییدنشده‌اند.</small></div><div className="detail-head-actions"><Link className="detail-map-button" href={mapUrl}><MapPin size={18} /> مشاهده فروشگاه‌های این محصول روی نقشه</Link><Link className="detail-secondary-button" href="/chat"><Store size={17} /> مشورت با دستیار خرید</Link></div></div>
      <section className="detail-content"><div className="detail-image">{product.images?.[0] && !imageFailed ? <button type="button" className="detail-image-zoom" onClick={() => setZoomImage(product.images![0])} aria-label="بزرگ‌نمایی تصویر محصول"><img src={product.images[0]} alt={product.titleFa} onError={() => setImageFailed(true)} /><span className="detail-zoom-hint"><ZoomIn size={14} /> بزرگ‌نمایی</span></button> : <span>تصویر موجود نیست</span>}</div><div><h2>مشخصات ثبت‌شده</h2>{Object.entries(product.specs || {}).length ? <dl>{Object.entries(product.specs || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl> : <p>مشخصات ساختاریافته ثبت نشده است.</p>}</div></section>
      <section id="offers" className="detail-offers"><h2><Store size={20} /> {formatNumber(shops.size)} فروشگاه · {formatNumber(offers.length)} پیشنهاد مطابق محدوده و فیلترها</h2><p>نام فروشگاه‌های فاقد نام واقعی با شناسه نمایش داده می‌شود. شماره‌های ساختگی نمایش داده نمی‌شوند.</p>
        {offersError ? <div className="catalog-state" role="alert"><b>{offersError}</b><button onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button></div> : Array.from(shops.entries()).map(([shopId, results]) => <article key={shopId} className="nearby-shop"><b>{results[0].shop.displayName}</b><span>{results[0].distanceKm == null ? "مختصات معتبر موجود نیست؛ فاصله و قرارگیری در شعاع قابل بررسی نیست." : formatDistance(results[0].distanceKm)} · {openLabel(results[0].openNow)}</span><small>{results[0].shop.addressText || "نشانی ثبت نشده است."}</small>{results.map((result, index) => <div className={`map-list-offer ${result.offer.id && cheapestOfferIds.has(result.offer.id) ? "offer-cheapest" : ""}`} key={result.offer.id || `${shopId}-${index}`}><span>{formatPrice(result.offer.price, result.offer.priceUnit)} · قیمت دیتاست{result.offer.id && cheapestOfferIds.has(result.offer.id) && <em className="cheapest-badge"><BadgeCheck size={13} /> کمترین قیمت این لیست</em>}</span><small>{formatDate(result.offer.priceUpdatedAt)} · موجودی تأییدنشده</small>{result.offer.id && <Link className="offer-contact-action" href={`/contact?offer_id=${encodeURIComponent(result.offer.id)}`} onClick={() => rememberContactSelection({ product, shop: result.shop, offer: result.offer })}>بررسی قیمت و تماس با فروشگاه</Link>}</div>)}</article>)}
        {!offersError && !offers.length && <div className="catalog-state"><b>پیشنهادی در محدوده و بودجه فعلی ثبت نشده است.</b><p>محدوده را روی نقشه تغییر بده یا بودجه جست‌وجو را اصلاح کن.</p><Link href={mapUrl}>تغییر محدوده روی نقشه</Link><Link href={back}>تغییر فیلترهای محصولات</Link></div>}
      </section>
      <div className="mobile-buy-bar" aria-hidden={false}>
        <div className="mobile-buy-price">
          <strong>{formatPrice(cheapest ?? minPrice)}</strong>
          <span>{cheapest !== null ? "کمترین قیمت ثبت‌شده · موجودی تأییدنشده" : "قیمت ثبت‌شده · موجودی تأییدنشده"}</span>
        </div>
        <Link className="mobile-buy-cta" href={mapUrl}><MapPin size={16} /> فروشگاه‌های نزدیک{typeof shops.size === "number" && shops.size > 0 ? ` (${formatNumber(shops.size)})` : ""}</Link>
      </div>
    </>}
    {zoomImage && (
      <div className="image-lightbox" role="dialog" aria-modal="true" aria-label="نمایش تصویر محصول" onClick={() => setZoomImage(null)}>
        <button type="button" className="lightbox-close" aria-label="بستن تصویر"><X size={20} /></button>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={zoomImage} alt={product?.titleFa ?? "تصویر محصول"} onClick={(event) => event.stopPropagation()} />
      </div>
    )}
    <MobileNav />
  </main>;
}
