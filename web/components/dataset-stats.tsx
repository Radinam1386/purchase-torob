"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Database, Store, Tag } from "lucide-react";

interface Stats {
  products: number;
  shops: number;
  offers: number;
  realNameShops?: number;
  topCategories?: { name: string; count: number }[];
}

const FALLBACK: Stats = { products: 225903, shops: 6476, offers: 331506 };

function formatCount(value: number): string {
  return new Intl.NumberFormat("fa-IR").format(value);
}

export function DatasetStats() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/stats", { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("stats unavailable");
        return response.json() as Promise<Stats>;
      })
      .then((body) => setStats(body))
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, []);

  const data = stats ?? FALLBACK;

  return (
    <section className="dataset-stats" aria-label="اندازه دیتاست ترب" data-live={stats ? "true" : "false"}>
      <div className="dataset-stat">
        <span className="dataset-stat-icon"><Tag size={17} /></span>
        <strong>{formatCount(data.products)}</strong>
        <span>محصول ثبت‌شده</span>
      </div>
      <div className="dataset-stat">
        <span className="dataset-stat-icon"><Store size={17} /></span>
        <strong>{formatCount(data.shops)}</strong>
        <span>فروشگاه تهران</span>
      </div>
      <div className="dataset-stat">
        <span className="dataset-stat-icon"><Database size={17} /></span>
        <strong>{formatCount(data.offers)}</strong>
        <span>آفر با قیمت و تاریخ</span>
      </div>
      {data.topCategories && data.topCategories.length > 0 && (
        <div className="dataset-stat-categories">
          <span>شروع سریع از پرتکرارترین دسته‌ها:</span>
          <div>
            {data.topCategories.slice(0, 4).map((category) => (
              <Link key={category.name} href={`/chat?q=${encodeURIComponent(category.name)}`}>
                {category.name}
              </Link>
            ))}
          </div>
        </div>
      )}
      <p className="dataset-stats-note">
        {failed || !stats
          ? "اعداد تقریبی از آخرین بارگذاری دیتاست ترب."
          : "زنده از دیتاست ترب خوانده شد؛ قیمت‌ها ثبت‌شده‌اند و موجودی تأییدنشده است."}
      </p>
    </section>
  );
}
