"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { LAST_RESULTS_KEY } from "@/lib/search-state";
import { useSearchParams } from "next/navigation";
import CatalogMap from "@/components/catalog-map";
import { MobileNav } from "@/components/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";

function StoreMap() {
  const current = useSearchParams();
  const [previous, setPrevious] = useState<string | null>(null);
  useEffect(() => { try { const url = localStorage.getItem(LAST_RESULTS_KEY); if (url && /^\/products(?:\?|$)/.test(url)) setPrevious(url); } catch { /* URL links work without saved history. */ } }, []);
  const back = new URLSearchParams(current.toString()); back.delete("product_ids"); back.delete("productIds");
  return <main className="catalog-page map-page" dir="rtl">
    <header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href="/chat">بازگشت به گفتگو</Link><Link href={(current.has("product_ids") || current.has("productIds")) && previous ? previous : `/products?${back}`}>محصولات و نقشه</Link></nav><ThemeToggle /><span className="source-pill">دیتاست ترب</span></header>
    <CatalogMap queryString={current.toString()} standalone />
    <MobileNav />
  </main>;
}
export default function StoreMapPage() { return <Suspense fallback={<main className="catalog-state">در حال بارگذاری نقشه…</main>}><StoreMap /></Suspense>; }
