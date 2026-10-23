"use client";

import dynamic from "next/dynamic";
import { Clock3, MapPin, Navigation, PackageSearch, Route, Store } from "lucide-react";

import {
  directionsUrl,
  formatDate,
  formatDistance,
  formatPrice,
  openLabel,
  sourceLabel,
  stockLabel,
} from "@/lib/format";
import type { Product, ShopResult } from "@/lib/contracts";
import type { MapPoint } from "@/components/leaflet-map";

const LeafletMap = dynamic(() => import("@/components/leaflet-map"), {
  ssr: false,
  loading: () => <div className="offers-map-loading">در حال آماده‌سازی نقشه…</div>,
});

export function NearbyOffers({
  product,
  center,
  results,
  error,
  busy,
  onWidenRadius,
  onRelaxFilters,
  onSuggestMarket,
  onSearchWeb,
  canWidenRadius,
  selectedOfferIds,
  onToggleCompare,
  onAskInquiry,
  onPrepareVisit,
}: {
  product: Product;
  center: MapPoint;
  results: ShopResult[];
  error: string;
  busy: boolean;
  onWidenRadius: () => void;
  onRelaxFilters: () => void;
  onSuggestMarket: () => void;
  onSearchWeb: () => void;
  canWidenRadius: boolean;
  selectedOfferIds: string[];
  onToggleCompare: (result: ShopResult) => void;
  onAskInquiry: (result: ShopResult) => void;
  onPrepareVisit: (result: ShopResult) => void;
}) {
  return (
    <section className="nearby-offers" aria-label="فروشگاه‌های نزدیک">
      <div className="nearby-heading">
        <div className="nearby-title">
          <span className="nearby-icon"><Store size={17} /></span>
          <div>
            <h3>فروشگاه‌های نزدیک</h3>
            <p>{product.titleFa}</p>
          </div>
        </div>
        <span className="source-tag source-dataset">{sourceLabel("dataset")}</span>
      </div>

      {busy ? (
        <div className="offers-loading" role="status"><span className="loading-dot" /> فیلترها اعمال می‌شوند…</div>
      ) : error ? (
        <div className="offers-error" role="alert">
          <strong>جستجوی فروشگاه‌ها انجام نشد.</strong>
          <span>{error}</span>
          <button type="button" onClick={onRelaxFilters}>تلاش دوباره</button>
        </div>
      ) : results.length ? (
        <>
          <div className="offers-map-frame">
            <LeafletMap center={center} results={results} />
          </div>
          <p className="map-caption"><MapPin size={13} /> نقشه موقعیت ثبت‌شده‌ی فروشگاه‌ها را نشان می‌دهد؛ قبل از حرکت، مسیر را بررسی کن.</p>
          <div className="nearby-list">
            {results.slice(0, 8).map((result) => {
              const route = directionsUrl(result.shop.lat, result.shop.lng);
              const offerId = result.offer?.id;
              return (
                <article className="nearby-shop" key={offerId ?? `${result.shop.id}-${result.offer.productId}`}>
                  <span className="nearby-shop-mark"><Store size={16} /></span>
                  <div className="nearby-shop-main">
                    <strong>{result.shop.displayName}</strong>
                    <span className="offer-id">
                      {offerId ? `آفر #${offerId.slice(-6)}` : "شناسه‌ی آفر قدیمی"}
                    </span>
                    <span className="nearby-address">{[result.shop.mall, result.shop.floor, result.shop.unit].filter(Boolean).join(" · ") || result.shop.addressText || "نشانی جزئی نامشخص"}</span>
                    <span className="nearby-meta"><MapPin size={12} /> {formatDistance(result.distanceKm)} <i /> {openLabel(result.openNow)}</span>
                    <span className="nearby-payment">
                      {result.shop.installment === true ? "قسطی حضوری" : result.shop.installment === null ? "قسطی حضوری: نامشخص" : "قسطی ثبت نشده"}
                      {result.shop.expressDelivery === true ? " · ارسال فوری" : ""}
                    </span>
                    <div className="nearby-actions">
                      <button
                        type="button"
                        className={offerId && selectedOfferIds.includes(offerId) ? "selected" : ""}
                        disabled={!offerId}
                        onClick={() => onToggleCompare(result)}
                      >
                        {offerId && selectedOfferIds.includes(offerId) ? "انتخاب شد" : "مقایسه"}
                      </button>
                      <button type="button" disabled={!offerId} onClick={() => onAskInquiry(result)}>استعلام نمونه‌سازی</button>
                      <button type="button" disabled={!offerId} onClick={() => onPrepareVisit(result)}><Route size={13} /> کارت مراجعه</button>
                    </div>
                  </div>
                  <div className="nearby-shop-price">
                    <strong>{formatPrice(result.offer.price, result.offer.priceUnit)}</strong>
                    <span><Clock3 size={11} /> {formatDate(result.offer.priceUpdatedAt)}</span>
                    <span className="stock-label">{stockLabel(result.offer.stock)}</span>
                    {route && <a href={route} target="_blank" rel="noreferrer"><Navigation size={13} /> مسیر</a>}
                  </div>
                </article>
              );
            })}
          </div>
        </>
      ) : (
        <div className="no-nearby-offers">
          <PackageSearch size={22} />
          <strong>در دیتاست آفر مکانی برای این کالا پیدا نشد.</strong>
          <p>با شعاع و فیلترهای فعلی آفر مکانی ثبت‌شده‌ای پیدا نشد؛ ممکن است کالا خارج از پوشش دیتاست باشد یا فیلترها محدودکننده باشند.</p>
          <div>
            {canWidenRadius && <button type="button" onClick={onWidenRadius}>شعاع را بیشتر کن</button>}
            <button type="button" onClick={onRelaxFilters}>فیلترهای سخت را بردار</button>
            <button type="button" onClick={onSuggestMarket}>پیشنهاد مرکز بازار</button>
            <button type="button" onClick={onSearchWeb}>جستجوی تکمیلی وب</button>
          </div>
        </div>
      )}
    </section>
  );
}
