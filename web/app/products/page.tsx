"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowRight, MapPin, Search } from "lucide-react";
import CatalogMap from "@/components/catalog-map";
import { formatDate, formatNumber, formatPrice, parseToman } from "@/lib/format";
import { COMPARE_KEY, LAST_RESULTS_KEY, readSearchState, resultsUrl, searchParams, type SearchState } from "@/lib/search-state";

type Item = { id: string; titleFa: string; brand: string | null; category: string | null; images: string[]; minPrice: number | null; maxPrice?: number | null; offerCount?: number; shopCount?: number; priceUpdatedAt?: string | null; specHighlights?: { key: string; value: string }[] };
type Result = { total: number; page: number; page_size: number; data: Item[]; facets?: { brands: string[]; categories: string[] } };

function ProductImage({ image }: { image?: string }) {
  const [failed, setFailed] = useState(false), [loaded, setLoaded] = useState(false);
  return <>{image && !failed && <img src={image} alt="" loading="lazy" style={{ gridArea: "1 / 1", opacity: loaded ? 1 : 0 }} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />}{(!image || failed || !loaded) && <span className="image-placeholder" style={{ gridArea: "1 / 1" }} aria-label="محل تصویر محصول">ترب</span>}</>;
}

function Catalog() {
  const router = useRouter();
  const current = useSearchParams();
  const urlQuery = current.toString();
  const state = readSearchState(new URLSearchParams(urlQuery));
  const [data, setData] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [compare, setCompare] = useState<string[]>([]);
  const [compareReady, setCompareReady] = useState(false);
  const [view, setView] = useState<"products" | "map">("products");

  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(COMPARE_KEY) || "[]");
      if (Array.isArray(saved)) setCompare(saved.filter((id): id is string => typeof id === "string").slice(0, 3));
    } catch { /* A damaged saved selection must not prevent searching. */ }
    setCompareReady(true);
  }, []);

  useEffect(() => {
    if (compareReady) try { localStorage.setItem(COMPARE_KEY, JSON.stringify(compare)); } catch { /* Search routing remains available without storage. */ }
  }, [compare, compareReady]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setData(null);
    const query = new URLSearchParams(urlQuery);
    const next = readSearchState(query);
    if ([next.query, next.category, next.brand].some(value => value.trim())) {
      let conversation;
      try { conversation = JSON.parse(localStorage.getItem("torob-in-person.workspace.v1") || "{}").conversation; } catch { /* Explicit defaults work without saved location. */ }
      let changed = false;
      for (const [key, min, max, fallback] of [["lat", -90, 90, 35.7219], ["lng", -180, 180, 51.4097], ["radius_km", 0, 100, 4]] as const) {
        const value = query.get(key), numeric = Number(value);
        if (value?.trim() && Number.isFinite(numeric) && numeric >= min && numeric <= max) continue;
        const saved = key === "radius_km" ? conversation?.radiusKm : conversation?.location?.[key];
        query.set(key, String(typeof saved === "number" && Number.isFinite(saved) && saved >= min && saved <= max ? saved : fallback));
        changed = true;
      }
      if (changed) { router.replace(`/products?${query}`, { scroll: false }); return; }
    }
    const params = searchParams(next);
    params.delete("label"); params.set("page", String(next.page)); params.set("page_size", "24");
    try { localStorage.setItem(LAST_RESULTS_KEY, resultsUrl(next)); } catch { /* Routing does not depend on storage. */ }
    async function load() {
      try {
        const response = await fetch(`/api/products?${params}`, { signal: controller.signal, cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "دریافت محصولات انجام نشد.");
        if (!controller.signal.aborted) setData(body);
      } catch (problem) {
        if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : "دریافت محصولات انجام نشد.");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, [urlQuery, retry, router]);

  function apply(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next: SearchState = {
      ...state, query: String(form.get("q") || "").trim(), label: "", page: 1,
      brand: String(form.get("brand") || ""), category: String(form.get("category") || ""),
      minPrice: parseToman(String(form.get("min_price") || "")), maxPrice: parseToman(String(form.get("max_price") || "")),
      sort: String(form.get("sort") || "relevance") as SearchState["sort"],
    };
    if (["min_price", "max_price"].some(key => {
      const value = String(form.get(key) || "").trim();
      return value && (value.startsWith("-") || parseToman(value) === null);
    })) { setError("قیمت را به‌صورت عدد مثبت یا عبارتی مانند ۳ میلیون وارد کن."); return; }
    if (next.minPrice !== null && next.maxPrice !== null && next.minPrice > next.maxPrice) {
      setError("حداقل قیمت نباید بیشتر از سقف بودجه باشد."); return;
    }
    setError("");
    if (resultsUrl(next) === resultsUrl(state)) setRetry(value => value + 1);
    else router.push(resultsUrl(next), { scroll: false });
  }

  function toggle(id: string) { setCompare(old => old.includes(id) ? old.filter(value => value !== id) : old.length < 3 ? [...old, id] : old); }
  const mapParams = searchParams(state); mapParams.delete("page");
  mapParams.set("q", state.query);
  const clearUrl = resultsUrl({ ...state, query: "", label: "", brand: "", category: "", minPrice: null, maxPrice: null, page: 1 });
  const pages = data ? Math.ceil(data.total / data.page_size) : 0;

  return <main className="catalog-page" dir="rtl">
    <header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href="/">خانه</Link><Link href="/chat">بازگشت به چت</Link></nav><span className="source-pill">دیتاست ترب</span></header>
    <section className="catalog-head"><Link className="back-link" href="/chat"><ArrowRight size={16} /> ادامه مشاوره و اصلاح ترجیحات</Link><div><span className="eyebrow">نتایج جست‌وجو</span><h1>{state.label || state.query ? `نتایج «${state.label || state.query}»` : "محصولات دیتاست"}</h1><p aria-live="polite" data-testid="result-count" data-total={data?.total}>{data ? `${formatNumber(data.total)} محصول مطابق جست‌وجو و فیلترها` : loading ? "در حال جست‌وجو…" : ""}</p></div></section>
    <form key={urlQuery} onSubmit={apply} aria-label="جست‌وجو و فیلتر محصولات">
      <div className="catalog-head"><div className="catalog-search"><Search size={18} /><input aria-label="نام کالا یا مدل" name="q" defaultValue={state.query} placeholder="نام کالا یا مدل" /><button type="submit">جست‌وجو</button></div></div>
      <section className="catalog-toolbar">
        <label>برند <input aria-label="فیلتر برند" list="catalog-brands" name="brand" defaultValue={state.brand} placeholder="همه برندها" /></label><datalist id="catalog-brands">{data?.facets?.brands.map(brand => <option key={brand} value={brand} />)}</datalist>
        <label>دسته <select aria-label="فیلتر دسته" name="category" defaultValue={state.category}><option value="">همه دسته‌های مرتبط</option>{Array.from(new Set([state.category, ...(data?.facets?.categories || [])])).filter(Boolean).map(category => <option key={category} value={category}>{category}</option>)}</select></label>
        <label>حداقل تومان <input aria-label="حداقل قیمت" name="min_price" inputMode="decimal" defaultValue={state.minPrice ?? ""} placeholder="بدون حداقل" /></label>
        <label>سقف تومان <input aria-label="حداکثر قیمت" name="max_price" inputMode="decimal" defaultValue={state.maxPrice ?? ""} placeholder="بدون سقف" /></label>
        <label>مرتب‌سازی <select aria-label="مرتب‌سازی" name="sort" defaultValue={state.sort}><option value="relevance">مرتبط‌ترین</option><option value="price_asc">ارزان‌ترین</option><option value="price_desc">گران‌ترین</option></select></label>
        <button type="submit" disabled={loading}>اعمال فیلترها</button><Link href={clearUrl}>پاک‌کردن فیلترها</Link><Link href={`/map?${mapParams}`}><MapPin size={16} /> مشاهده فروشگاه‌ها روی نقشه</Link>
        <span className="dataset-note">قیمت ثبت‌شده در دیتاست؛ قیمت روز و موجودی تأیید نشده‌اند.</span>
      </section>
    </form>
    <div className="catalog-view-tabs" role="group" aria-label="نمای نتایج"><button type="button" aria-pressed={view === "products"} onClick={() => setView("products")}>محصولات</button><button type="button" aria-pressed={view === "map"} onClick={() => setView("map")}>نقشه و فروشگاه‌ها</button></div>
    <div className="catalog-workspace" data-view={view}><section className="catalog-products-pane" aria-label="محصولات جستجو">
    {compare.length > 0 && <div className="compare-dock" style={{ position: "static", transform: "none", margin: "18px auto", width: "fit-content" }}>{formatNumber(compare.length)} از ۳ کالا برای مقایسه{compare.length > 1 && <Link href={`/products/compare?ids=${compare.map(encodeURIComponent).join(",")}`}>مقایسه کالاها</Link>}<button onClick={() => setCompare([])}>پاک‌کردن انتخاب‌ها</button></div>}
    {error && <div className="catalog-state" role="alert"><b>{error}</b><p>اتصال را بررسی کن یا فیلترها را تغییر بده.</p><button onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button></div>}
    {loading ? <div className="product-grid" aria-busy="true" aria-label="بارگذاری محصولات">{Array.from({ length: 8 }, (_, index) => <div className="product-skeleton" key={index} />)}</div> : !error && data?.data.length ? <>
      <div className="product-grid" data-testid="product-results">{data.data.map(product => <article className="product-tile" key={product.id} data-product-id={product.id}>
        <Link href={`/products/${encodeURIComponent(product.id)}`} className="product-image" aria-label={`جزئیات ${product.titleFa}`}><ProductImage image={product.images?.[0]} /></Link>
        <div className="tile-meta">{product.category || "دسته نامشخص"}</div><Link href={`/products/${encodeURIComponent(product.id)}`} className="tile-title">{product.titleFa}</Link><div className="tile-brand">{product.brand || "برند نامشخص"}</div>
        {product.specHighlights?.length ? <dl className="tile-specs">{product.specHighlights.slice(0, 2).map(spec => <div key={spec.key}><dt>{spec.key}</dt><dd>{spec.value}</dd></div>)}</dl> : <p className="tile-specs">مشخصات بیشتر در صفحه محصول</p>}
        <p className="tile-fit-reason">{state.maxPrice !== null && product.minPrice !== null && product.minPrice <= state.maxPrice ? "دارای پیشنهاد در سقف بودجه انتخابی" : state.category ? `در دسته ${product.category || state.category}` : state.query ? `مطابق جست‌وجوی «${state.query}»` : "از محصولات ثبت‌شده در دیتاست"}</p>
        <div className="tile-price">{product.maxPrice != null && product.minPrice != null && product.maxPrice > product.minPrice ? `${formatPrice(product.minPrice)} تا ${formatPrice(product.maxPrice)}` : formatPrice(product.minPrice)}<small>قیمت دیتاست · موجودی تأییدنشده</small></div>
        <div className="tile-counts">{typeof product.shopCount === "number" ? `${formatNumber(product.shopCount)} فروشگاه` : "تعداد فروشگاه در جزئیات"}{typeof product.offerCount === "number" && ` · ${formatNumber(product.offerCount)} پیشنهاد`}</div><small className="tile-price-date">تاریخ ثبت قیمت: {formatDate(product.priceUpdatedAt)}</small>
        <div className="tile-actions"><Link href={`/products/${encodeURIComponent(product.id)}`}>جزئیات کالا</Link><Link href={`/products/${encodeURIComponent(product.id)}#offers`}>انتخاب فروشگاه</Link><label><input type="checkbox" aria-label={`مقایسه ${product.titleFa}`} checked={compare.includes(product.id)} disabled={!compare.includes(product.id) && compare.length >= 3} onChange={() => toggle(product.id)} /> مقایسه</label></div>
      </article>)}</div>
      <nav className="load-more" aria-label="صفحه‌بندی نتایج">{state.page > 1 && <Link aria-label="صفحه قبل" href={resultsUrl({ ...state, page: state.page - 1 })}>صفحه قبل</Link>}<span>صفحه {formatNumber(state.page)} از {formatNumber(pages)} · {formatNumber(data.total)} محصول</span>{state.page < pages && <Link aria-label="صفحه بعد" href={resultsUrl({ ...state, page: state.page + 1 })}>صفحه بعد</Link>}</nav>
    </> : !error && <div className="catalog-state"><b>{data?.total ? "این صفحه از نتایج خالی است." : "محصولی با این فیلترها پیدا نشد."}</b><p>بودجه یا عبارت جست‌وجو را تغییر بده.</p>{state.page > 1 && <Link href={resultsUrl({ ...state, page: 1 })}>صفحه اول</Link>}<Link href={clearUrl}>جست‌وجوی بدون فیلتر</Link><Link href="/chat">ادامه با دستیار</Link></div>}
    </section><aside className="catalog-map-pane" aria-label="نقشه هم‌زمان نتایج"><CatalogMap queryString={urlQuery} /></aside></div>
  </main>;
}

export default function ProductsPage() { return <Suspense fallback={<main className="catalog-state">در حال آماده‌سازی جست‌وجو…</main>}><Catalog /></Suspense>; }
