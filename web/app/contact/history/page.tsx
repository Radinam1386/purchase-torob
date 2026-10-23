"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { getMockHistory, SCENARIOS, type MockRun } from "@/lib/contact";
import { formatNumber, formatPrice } from "@/lib/format";

function History(){
  const params=useSearchParams(), raw=Number(params.get("page")||1),page=Number.isSafeInteger(raw)&&raw>0?raw:1;
  const [data,setData]=useState<{total:number;page_size:number;data:MockRun[]}|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(""),[retry,setRetry]=useState(0);
  useEffect(()=>{const controller=new AbortController();setLoading(true);setError("");getMockHistory(page,controller.signal).then(setData).catch(problem=>{if(!controller.signal.aborted)setError(problem instanceof Error?problem.message:"دریافت تاریخچه انجام نشد.");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[page,retry]);
  return <main className="catalog-page contact-page" dir="rtl"><header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href="/products">انتخاب محصول</Link><Link href="/chat">ادامه گفتگو</Link></nav></header><section className="contact-heading"><h1>تاریخچه تماس‌های شبیه‌سازی‌شده</h1><p>این نتیجه‌ها فقط Mock هستند و تأیید واقعی قیمت یا موجودی محسوب نمی‌شوند. تاریخچه مربوط به همین مرورگر است.</p></section>
    {loading?<div className="catalog-state" role="status">دریافت تاریخچه…</div>:error?<div className="catalog-state" role="alert"><p>{error}</p><button onClick={()=>setRetry(value=>value+1)}>تلاش دوباره</button></div>:<><p className="contact-history-total">{formatNumber(data?.total ?? 0)} اجرای Mock ذخیره‌شده</p><section className="contact-history" data-testid="mock-history">{data?.data.map(run=><article key={run.id} data-run-id={run.id}><span className="source-pill">تماس Mock</span><h2>{run.product.titleFa}</h2><p>{run.shop.displayName} · {SCENARIOS[run.scenario]}</p><p>قیمت دیتاست: {formatPrice(run.datasetOffer.price)} · قیمت Mock: {formatPrice(run.simulatedPrice)}</p><small>{new Date(run.createdAt).toLocaleString("fa-IR")}</small><Link href={`/contact?run_id=${encodeURIComponent(run.id)}`}>مشاهده گزارش و گفتگو</Link></article>)}</section>{!data?.data.length&&<div className="catalog-state"><p>هنوز تماس Mock ثبت نشده است.</p><Link href="/products">انتخاب محصول و فروشگاه</Link></div>}<nav className="load-more" aria-label="صفحه‌بندی تاریخچه">{page>1&&<Link href={`/contact/history?page=${page-1}`}>صفحه قبل تاریخچه</Link>}{data&&page*data.page_size<data.total&&<Link href={`/contact/history?page=${page+1}`}>صفحه بعد تاریخچه</Link>}</nav></>}
  </main>;
}
export default function ContactHistoryPage(){return <Suspense fallback={<main className="catalog-state">آماده‌سازی تاریخچه…</main>}><History/></Suspense>;}
