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
}: {
  center: MapPoint;
  results: ShopResult[];
}) {
  const resultsByShop = new Map<string, ShopResult[]>();
  for (const result of results) {
    const group = resultsByShop.get(result.shop.id) ?? [];
    group.push(result);
    resultsByShop.set(result.shop.id, group);
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
      {[...resultsByShop.values()].map((shopResults) => {
        const result = shopResults[0];
        if (typeof result.shop.lat !== "number" || typeof result.shop.lng !== "number") return null;
        const directions = directionsUrl(result.shop.lat, result.shop.lng);
        return (
          <CircleMarker
            key={result.shop.id}
            center={[result.shop.lat, result.shop.lng]}
            radius={8}
            pathOptions={{ color: "#fff", weight: 3, fillColor: "#d86c4a", fillOpacity: 1 }}
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
