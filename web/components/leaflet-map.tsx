"use client";

import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

import { directionsUrl, formatDistance, formatPrice, openLabel, stockLabel } from "@/lib/format";
import type { ShopResult } from "@/lib/contracts";

export interface MapPoint {
  lat: number;
  lng: number;
}

export default function LeafletMap({
  center,
  results,
  selectedShopId,
  onSelectShop,
}: {
  center: MapPoint;
  results: ShopResult[];
  selectedShopId?: string | null;
  onSelectShop?: (shopId: string) => void;
}) {
  const resultsByShop = new Map<string, ShopResult[]>();
  for (const result of results) {
    const group = resultsByShop.get(result.shop.id) ?? [];
    group.push(result);
    resultsByShop.set(result.shop.id, group);
  }
  // Lightweight deterministic spatial clustering; no synthetic coordinates are introduced.
  const clusters = new Map<string, ShopResult[][]>();
  for (const group of resultsByShop.values()) {
    const item = group[0];
    if (typeof item.shop.lat !== "number" || typeof item.shop.lng !== "number") continue;
    const key = `${Math.floor(item.shop.lat / 0.004)}:${Math.floor(item.shop.lng / 0.004)}`;
    clusters.set(key, [...(clusters.get(key) ?? []), group]);
  }

  return (
    <MapContainer
      key={`${center.lat.toFixed(4)}-${center.lng.toFixed(4)}`}
      center={[center.lat, center.lng]}
      zoom={12}
      scrollWheelZoom={false}
      className="offers-map-canvas"
      aria-label="نقشه‌ی فروشگاه‌های نزدیک"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {[...clusters.values()].flatMap((cluster) => {
        if (cluster.length > 1) {
          const lat = cluster.reduce((sum, group) => sum + group[0].shop.lat!, 0) / cluster.length;
          const lng = cluster.reduce((sum, group) => sum + group[0].shop.lng!, 0) / cluster.length;
          return [<CircleMarker key={`cluster-${cluster[0][0].shop.id}`} center={[lat,lng]} radius={Math.min(18, 9 + Math.log2(cluster.length) * 2)} pathOptions={{color:"#fff",weight:3,fillColor:"#bd4b38",fillOpacity:.9}}><Popup><div className="map-popup" dir="rtl"><strong>{cluster.length} فروشگاه نزدیک به هم</strong>{cluster.map(group=><div key={group[0].shop.id}><b>{group[0].shop.displayName}</b><span>{formatDistance(group[0].distanceKm)} · {formatPrice(group[0].offer.price,group[0].offer.priceUnit)}</span></div>)}</div></Popup></CircleMarker>];
        }
        const shopResults = cluster[0];
        const result = shopResults[0];
        const lat = result.shop.lat;
        const lng = result.shop.lng;
        if (typeof lat !== "number" || typeof lng !== "number") return null;
        const directions = directionsUrl(lat, lng);
        return (
          <CircleMarker
            key={result.shop.id}
            center={[lat, lng]}
            radius={8}
            eventHandlers={{ click: () => onSelectShop?.(result.shop.id) }}
            pathOptions={{ color: "#fff", weight: 3, fillColor: selectedShopId===result.shop.id ? "#222" : "#d86c4a", fillOpacity: 1 }}
          >
            <Popup>
              <div className="map-popup" dir="rtl">
                <strong>{result.shop.displayName}</strong>
                <span>{formatDistance(result.distanceKm)} · {openLabel(result.openNow)}</span>
                {shopResults.map((shopResult, index) => (
                  <div
                    className="map-popup-offer"
                    key={shopResult.offer.id ?? `${shopResult.offer.productId}-${index}`}
                  >
                    <small>
                      {shopResult.offer.id
                        ? `آفر #${shopResult.offer.id.slice(-6)}`
                        : "شناسه‌ی آفر قدیمی"}
                    </small>
                    <span>{formatPrice(shopResult.offer.price, shopResult.offer.priceUnit)}</span>
                    <small>{stockLabel(shopResult.offer.stock)}</small>
                  </div>
                ))}
                {directions && <a href={directions} target="_blank" rel="noreferrer">مسیریابی</a>}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
