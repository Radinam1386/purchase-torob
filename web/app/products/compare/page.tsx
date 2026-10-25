"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { BadgeCheck, GitCompareArrows } from "lucide-react";
import { formatPrice } from "@/lib/format";
import { LAST_RESULTS_KEY } from "@/lib/search-state";
import { MobileNav } from "@/components/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Product } from "@/lib/contracts";

type ComparedProduct = Product & { minPrice: number | null };

function ProductImageThumb({ image, title }: { image?: string; title: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="compare-image">
      {image && !failed
        ? <img src={image} alt={`تصویر ${title}`} onError={() => setFailed(true)} />
        : <span aria-hidden="true">ترب</span>}
    </div>
  );
}

function Comparison() {
  const params = useSearchParams();
  const ids = [...new Set((params.get("ids") || "").split(",").filter(Boolean))].slice(0, 3).join(",");
  const [items, setItems] = useState<ComparedProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [onlyDiff, setOnlyDiff] = useState(false);
  const [back, setBack] = useState("/products");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setItems([]);
    try { const saved = localStorage.getItem(LAST_RESULTS_KEY); if (saved && /^\/products(?:\?|$)/.test(saved)) setBack(saved); } catch { /* Independent route remains usable. */ }
    async function load() {
      try {
        const products = await Promise.all(ids.split(",").filter(Boolean).map(async id => {
          const response = await fetch(`/api/products/${encodeURIComponent(id)}`, { signal: controller.signal, cache: "no-store" });
          const body = await response.json();
          if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "دریافت یکی از محصولات انجام نشد.");
          return { ...body.product, minPrice: body.minPrice } as ComparedProduct;
        }));
        if (!controller.signal.aborted) setItems(products);
      } catch (problem) { if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : "دریافت اطلاعات مقایسه انجام نشد."); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load(); return () => controller.abort();
  }, [ids, retry]);

  const specs = useMemo(
    () => [...new Set(items.flatMap(item => Object.keys(item.specs || {})))],
    [items],
  );
  const cheapest = useMemo(() => {
    const prices = items.map(item => item.minPrice).filter((price): price is number => typeof price === "number" && price > 0);
    return prices.length ? Math.min(...prices) : null;
  }, [items]);
  const differingSpecs = useMemo(() => specs.filter(key => {
    const values = items.map(item => String(item.specs?.[key] ?? "").trim());
    return new Set(values).size > 1;
  }), [items, specs]);
  const visibleSpecs = onlyDiff && items.length > 1 ? differingSpecs : specs;

  return <main className="catalog-page compare-page" dir="rtl">
    <header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href={back}>بازگشت به نتایج</Link><Link href="/chat">ادامه چت</Link></nav><ThemeToggle /></header>
    <section className="catalog-head">
      <h1>مقایسه محصولات</h1>
      <p>مشخصات و قیمت ثبت‌شده در دیتاست؛ قیمت روز و موجودی تأییدنشده‌اند.</p>
      {items.length > 1 && specs.length > 0 && (
        <label className="compare-diff-toggle">
          <input type="checkbox" checked={onlyDiff} onChange={event => setOnlyDiff(event.target.checked)} />
          <span><GitCompareArrows size={15} /> فقط ردیف‌های متفاوت ({differingSpecs.length} از {specs.length})</span>
        </label>
      )}
    </section>
    {loading ? <div className="catalog-state" aria-busy="true">در حال دریافت مشخصات…</div> : error ? <div className="catalog-state" role="alert"><b>{error}</b><button onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button><Link href={back}>اصلاح انتخاب محصولات</Link></div> : items.length < 2 ? <div className="catalog-state"><b>برای مقایسه دست‌کم دو محصول انتخاب کن.</b><Link href={back}>انتخاب محصولات</Link></div> : <div className="compare-products-grid">{items.map(product => {
      const isCheapest = cheapest !== null && product.minPrice === cheapest;
      return <article key={product.id} className={isCheapest ? "compare-best" : ""}>
        {isCheapest && <span className="compare-best-badge"><BadgeCheck size={14} /> کمترین قیمت دیتاست</span>}
        <ProductImageThumb image={product.images?.[0]} title={product.titleFa} />
        <h2>{product.titleFa}</h2>
        <p>{product.brand || "برند نامشخص"} · {product.category || "دسته نامشخص"}</p>
        <strong>{formatPrice(product.minPrice)}</strong>
        <h3>مشخصات ثبت‌شده</h3>
        {visibleSpecs.length ? <dl>{visibleSpecs.map(key => <div key={key} className={items.length > 1 && new Set(items.map(item => String(item.specs?.[key] ?? "").trim())).size > 1 ? "spec-differs" : ""}><dt>{key}</dt><dd>{String(product.specs?.[key] ?? "ثبت نشده")}</dd></div>)}</dl>
          : <p>{onlyDiff ? "هیچ مشخصه‌ای بین این محصولات تفاوت ندارد." : "مشخصات ساختاریافته ثبت نشده است."}</p>}
        <Link href={`/products/${encodeURIComponent(product.id)}`}>جزئیات و فروشگاه‌ها</Link>
      </article>;
    })}</div>}
    <MobileNav />
  </main>;
}
export default function ComparePage() { return <Suspense fallback={<main className="catalog-state">در حال آماده‌سازی مقایسه…</main>}><Comparison /></Suspense>; }
