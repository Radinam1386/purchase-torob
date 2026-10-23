"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { rememberContactSelection } from "@/lib/contact";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import type { CircleMarker as LeafletCircleMarker } from "leaflet";
import { directionsUrl, formatDate, formatDistance, formatPrice, openLabel } from "@/lib/format";
import type { ShopResult } from "@/lib/contracts";

export interface MapPoint { lat: number; lng: number }
export function hasValidCoordinates(shop: { lat?: number | null; lng?: number | null }) {
  return typeof shop.lat === "number" && Number.isFinite(shop.lat) && Math.abs(shop.lat) <= 90
    && typeof shop.lng === "number" && Number.isFinite(shop.lng) && Math.abs(shop.lng) <= 180;
}
type MapProps = { center: MapPoint; results: ShopResult[]; selectedShopId?: string | null;
  onSelectShop?: (id: string) => void; productNames?: Record<string, string>; radiusKm?: number };

function ShopMarker({ group, selected, onSelectShop, productNames }: {
  group: ShopResult[]; selected: boolean; onSelectShop?: (id: string) => void; productNames: Record<string, string>;
}) {
  const marker = useRef<LeafletCircleMarker | null>(null);
  const map = useMap();
  const first = group[0];
  useEffect(() => {
    if (!selected || !marker.current) return;
    const layer = marker.current;
    const open = () => {
      if (map.hasLayer(layer) && layer.getPopup() && !layer.isPopupOpen()) layer.openPopup();
    };
    // Cluster selection also changes the viewport; reopen only after the layer/view is ready.
    layer.on("add", open); map.on("moveend", open); open();
    return () => { layer.off("add", open); map.off("moveend", open); };
  }, [selected, map]);
  const directions = directionsUrl(first.shop.lat, first.shop.lng);
  return <CircleMarker ref={marker} center={[first.shop.lat!, first.shop.lng!]} radius={selected ? 11 : 8}
    pathOptions={{ color: "#fff", weight: 3, fillColor: selected ? "#222" : "#d86c4a", fillOpacity: 1 }}
    eventHandlers={{ click: () => onSelectShop?.(first.shop.id), add: (event) => {
      const element = (event.target as LeafletCircleMarker).getElement();
      element?.setAttribute("aria-label", first.shop.displayName); element?.setAttribute("role", "button"); element?.setAttribute("tabindex", "0");
      element?.addEventListener("keydown", key => { if (["Enter", " "].includes((key as KeyboardEvent).key)) {
        key.preventDefault(); onSelectShop?.(first.shop.id); marker.current?.openPopup();
      } });
    } }}>
    <Popup key={selected ? "selected" : "normal"} closeOnClick={!selected}><div className="map-popup" dir="rtl"><strong>{first.shop.displayName}</strong>
      <span>{formatDistance(first.distanceKm)} · {openLabel(first.openNow)}</span><span>{first.shop.addressText || "نشانی ثبت نشده"}</span>
      {group.map((result, index) => <div className="map-popup-offer" key={result.offer.id ?? index}>
        <b>{productNames[result.offer.productId] || "پیشنهاد مرتبط"}</b><span>{formatPrice(result.offer.price, result.offer.priceUnit)}</span>
        <small>قیمت دیتاست · {formatDate(result.offer.priceUpdatedAt)} · موجودی تأییدنشده</small>
        {result.offer.id && <Link className="offer-contact-action" href={`/contact?offer_id=${encodeURIComponent(result.offer.id)}`} onClick={() => rememberContactSelection({ product: { id: result.offer.productId, titleFa: productNames[result.offer.productId] || "محصول انتخاب‌شده" }, shop: result.shop, offer: result.offer })}>بررسی قیمت و تماس با فروشگاه</Link>}
      </div>)}{directions && <a href={directions} target="_blank" rel="noreferrer">مسیریابی</a>}
    </div></Popup>
  </CircleMarker>;
}

function Markers({ center, results, selectedShopId, onSelectShop, productNames = {}, radiusKm }: MapProps) {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({ animate: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  const groups = useMemo(() => {
    const byShop = new Map<string, ShopResult[]>();
    for (const result of results) { if (!hasValidCoordinates(result.shop)) continue;
      const items = byShop.get(result.shop.id) ?? []; items.push(result); byShop.set(result.shop.id, items); }
    return [...byShop.values()];
  }, [results]);
  useEffect(() => {
    if (radiusKm && radiusKm > 0) {
      const latDelta = radiusKm / 111.32, lngDelta = latDelta / Math.max(.05, Math.cos(center.lat * Math.PI / 180));
      map.fitBounds([[center.lat - latDelta, center.lng - lngDelta], [center.lat + latDelta, center.lng + lngDelta]], { padding: [16, 16], maxZoom: 16, animate: false });
    } else map.setView([center.lat, center.lng], 12, { animate: false });
  }, [center.lat, center.lng, radiusKm, map]);
  useEffect(() => {
    const selected = groups.find(group => group[0].shop.id === selectedShopId)?.[0];
    if (selected) map.setView([selected.shop.lat!, selected.shop.lng!], Math.max(map.getZoom(), 17), { animate: false });
  }, [selectedShopId, groups, map]);
  // ponytail: pixel buckets avoid another dependency; a very large catalogue should use server-side map tiles.
  const clusters = new Map<string, ShopResult[][]>();
  for (const group of groups) {
    if (group[0].shop.id === selectedShopId) continue;
    const point = map.project([group[0].shop.lat!, group[0].shop.lng!], zoom);
    const bucket = `${Math.floor(point.x / 48)}:${Math.floor(point.y / 48)}`;
    const items = clusters.get(bucket) ?? []; items.push(group); clusters.set(bucket, items);
  }
  const rendered = [...clusters.values()].map(cluster => {
    if (cluster.length === 1) return <ShopMarker key={cluster[0][0].shop.id} group={cluster[0]}
      selected={cluster[0][0].shop.id === selectedShopId} onSelectShop={onSelectShop} productNames={productNames} />;
    // The cluster anchor is an actual member coordinate, never an invented shop location.
    const first = cluster[0][0];
    return <CircleMarker key={`cluster-${first.shop.id}`} center={[first.shop.lat!, first.shop.lng!]}
      radius={Math.min(22, 11 + Math.log2(cluster.length) * 2)} pathOptions={{ color: "#fff", weight: 3, fillColor: "#bd4b38", fillOpacity: .93 }}
      eventHandlers={{ add: event => {
        const layer = event.target as LeafletCircleMarker, element = layer.getElement();
        element?.setAttribute("aria-label", `گروه ${cluster.length} فروشگاه`); element?.setAttribute("role", "button"); element?.setAttribute("tabindex", "0");
        element?.addEventListener("keydown", key => { if (["Enter", " "].includes((key as KeyboardEvent).key)) { key.preventDefault(); layer.openPopup(); } });
      } }}>
      <Popup><div className="map-popup" dir="rtl"><strong>{cluster.length} فروشگاه نزدیک به هم</strong>
        <button type="button" onClick={() => map.setView([first.shop.lat!, first.shop.lng!], Math.min(19, zoom + 2), { animate: false })}>بزرگ‌نمایی این گروه</button>
        {cluster.map(group => <button type="button" key={group[0].shop.id} aria-pressed={group[0].shop.id === selectedShopId}
          onClick={() => onSelectShop?.(group[0].shop.id)}>{group[0].shop.displayName} · {group.length} پیشنهاد · {formatPrice(group[0].offer.price, group[0].offer.priceUnit)}</button>)}
      </div></Popup>
    </CircleMarker>;
  });
  const selectedGroup = groups.find(group => group[0].shop.id === selectedShopId);
  if (selectedGroup) rendered.push(<ShopMarker key={selectedGroup[0].shop.id} group={selectedGroup} selected onSelectShop={onSelectShop} productNames={productNames} />);
  return rendered;
}

export default function LeafletMap(props: MapProps) {
  const [tileError, setTileError] = useState(false), [attempt, setAttempt] = useState(0);
  return <div className="map-interactive">
    {tileError && <div role="alert" className="map-tile-error">نقشه زمینه بارگذاری نشد؛ فهرست و موقعیت فروشگاه‌های دیتاست همچنان در دسترس است.
      <button type="button" onClick={() => { setTileError(false); setAttempt(value => value + 1); }}>تلاش دوباره نقشه</button></div>}
    {/* Leaflet 1.9 leaves a zoom-transition timer after route teardown; instant zoom avoids that stale callback. */}
    <MapContainer center={[props.center.lat, props.center.lng]} zoom={12} zoomAnimation={false} scrollWheelZoom className="offers-map-canvas" aria-label="نقشه فروشگاه‌های مرتبط">
      <TileLayer key={attempt} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" eventHandlers={{ tileerror: () => setTileError(true) }} />
      <Markers {...props} />
    </MapContainer>
  </div>;
}
