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
      {results.map((result) => {
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
                <span>{formatPrice(result.offer.price, result.offer.priceUnit)}</span>
                <span>{formatDistance(result.distanceKm)} · {openLabel(result.openNow)}</span>
                <small>{stockLabel(result.offer.stock)}</small>
                {directions && <a href={directions} target="_blank" rel="noreferrer">مسیریابی</a>}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
