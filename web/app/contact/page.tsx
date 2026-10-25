"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Clock, LoaderCircle, PhoneCall } from "lucide-react";
import { formatDate, formatNumber, formatPrice, parseToman } from "@/lib/format";
import { createBuyerReport, createMockCall, getBuyerReports, getContactSelection, getMockCall,
  rememberContactSelection, rememberContactStage, SCENARIOS,
  type BuyerReport, type ContactSelection, type MockRun, type MockScenario } from "@/lib/contact";
import { MobileNav } from "@/components/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";

const PROCESS = ["آماده‌سازی اطلاعات تماس", "شروع شبیه‌سازی", "ارسال درخواست Mock", "دریافت پاسخ شبیه‌سازی‌شده", "تحلیل پاسخ توسط Agent", "نمایش نتیجه"];
function dateTime(value?: string | null) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "زمان نامشخص";
  return new Date(value).toLocaleString("fa-IR");
}
function localNow() { return new Date(Date.now() - new Date().getTimezoneOffset()*60000).toISOString().slice(0,16); }

function Contact() {
  const params = useSearchParams(), router = useRouter();
  const offerId = params.get("offer_id") || "", runId = params.get("run_id") || "";
  const [selection,setSelection] = useState<ContactSelection | null>(null), [run,setRun] = useState<MockRun | null>(null);
  const [loading,setLoading] = useState(true), [running,setRunning] = useState(false), [error,setError] = useState("");
  const [scenario,setScenario] = useState<MockScenario>("confirmed"), [newPrice,setNewPrice] = useState("");
  const [retry,setRetry] = useState(0);
  const pendingKey = useRef<string | null>(null), alive = useRef(true);
  useEffect(()=>{ alive.current=true; return ()=>{alive.current=false;}; },[]);
  useEffect(()=>{
    const controller = new AbortController();
    setLoading(true); setError(""); setRun(null); setSelection(null); pendingKey.current=null;
    async function load() {
      try {
        if (runId) {
          const result=await getMockCall(runId,controller.signal);
          if (controller.signal.aborted) return;
          setRun(result.run); setScenario(result.run.scenario);
          const selected={product:result.run.product,shop:result.run.shop,offer:result.run.datasetOffer};
          setSelection(selected); rememberContactSelection(selected,"contact_result");
        } else {
          if (!offerId) throw new Error("ابتدا یک پیشنهاد مشخص از فروشگاه‌های محصول انتخاب کن.");
          const selected=await getContactSelection(offerId,controller.signal);
          if (controller.signal.aborted) return;
          setSelection(selected); rememberContactSelection(selected);
        }
      } catch(problem) { if(!controller.signal.aborted) setError(problem instanceof Error?problem.message:"دریافت انتخاب انجام نشد."); }
      finally { if(!controller.signal.aborted) setLoading(false); }
    }
    void load(); return ()=>controller.abort();
  },[offerId,runId,retry]);

  async function start(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if(!selection?.offer.id || running) return;
    const changedPrice=parseToman(newPrice);
    if(scenario==="price_changed" && (newPrice.trim().startsWith("-") || changedPrice===null || changedPrice<=0 || !Number.isSafeInteger(changedPrice) || changedPrice>9_000_000_000_000_000 || changedPrice===selection.offer.price)) {
      setError("برای سناریوی تغییر قیمت، مبلغ مثبت و متفاوت با قیمت دیتاست وارد کن."); return;
    }
    setRunning(true); setError(""); rememberContactStage("mock_running");
    const key=pendingKey.current ?? window.crypto.randomUUID(); pendingKey.current=key;
    try {
      const result=await createMockCall({offerId:selection.offer.id,scenario,runKey:key,...(scenario==="price_changed"?{newPrice:changedPrice!}:{})});
      if(!alive.current) return;
      setRun(result.run); rememberContactStage("contact_result"); pendingKey.current=null;
      router.replace(`/contact?run_id=${encodeURIComponent(result.run.id)}`,{scroll:false});
    } catch(problem) {
      if(alive.current) {setError(problem instanceof Error?problem.message:"اجرای Mock انجام نشد؛ دوباره تلاش کن.");rememberContactStage("preparing_contact");}
    } finally { if(alive.current) setRunning(false); }
  }

  return <main className="catalog-page contact-page" dir="rtl">
    <header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href="/chat">ادامه گفتگو</Link><Link href="/contact/history">تاریخچه تماس‌های Mock</Link></nav><ThemeToggle /><span className="source-pill">فقط شبیه‌سازی</span></header>
    <section className="contact-heading"><Link href={selection?`/products/${encodeURIComponent(selection.product.id)}`:"/products"}><ArrowRight size={16}/> بازگشت به محصول و فروشگاه‌ها</Link><h1><PhoneCall size={24}/> تماس شبیه‌سازی‌شده (Mock)</h1><p>هدف: بررسی قیمت، موجودی و امکان خرید حضوری. این مسیر هیچ تماس تلفنی واقعی برقرار نمی‌کند.</p></section>
    {loading?<div className="catalog-state" role="status"><LoaderCircle className="spin"/> در حال دریافت اطلاعات انتخاب‌شده…</div>:!selection?<div className="catalog-state" role="alert"><p>{error}</p><button onClick={()=>setRetry(value=>value+1)}>تلاش دوباره</button><Link href="/products">انتخاب محصول</Link></div>:<>
      <section className="contact-selection" data-testid="contact-selection" data-product-id={selection.product.id} data-shop-id={selection.shop.id} data-offer-id={selection.offer.id}>
        <div><small>محصول انتخاب‌شده · دیتاست ترب</small><h2>{selection.product.titleFa}</h2><p>{selection.shop.displayName}</p><small>{selection.shop.addressText || "نشانی ثبت نشده است."}</small></div>
        <div className="contact-dataset-price"><small>قیمت ثبت‌شده در دیتاست</small><strong>{formatPrice(selection.offer.price,selection.offer.priceUnit)}</strong><span>{formatDate(selection.offer.priceUpdatedAt)}</span><small>قیمت فعلی و موجودی تأیید نشده‌اند.</small></div>
      </section>
      {error && <div className="contact-error" role="alert">{error}</div>}
      {run?<RunResult run={run} onRerun={()=>router.push(`/contact?offer_id=${encodeURIComponent(selection.offer.id ?? "")}`)}/>:<form className="contact-controls" onSubmit={start}>
        <label>سناریوی قابل تکرار<select aria-label="سناریوی تماس Mock" value={scenario} disabled={running} onChange={event=>{setScenario(event.target.value as MockScenario);pendingKey.current=null;setError("");}}>{Object.entries(SCENARIOS).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        {scenario==="price_changed" && <label>قیمت جدید در شبیه‌سازی، تومان<input aria-label="قیمت جدید Mock" inputMode="decimal" value={newPrice} onChange={event=>{setNewPrice(event.target.value);pendingKey.current=null;}} disabled={running} required/></label>}
        <p>سناریو را خودت تعیین می‌کنی. پاسخ Mock داده آزمایشی است و تأیید واقعی فروشنده محسوب نمی‌شود.</p>
        <button type="submit" disabled={running}>{running?<><LoaderCircle size={17} className="spin"/> اجرای ارتباط Mock…</>:<><PhoneCall size={17}/> شروع شبیه‌سازی تماس</>}</button>
      </form>}
      {running && <ol className="contact-stages" aria-live="polite" aria-label="مراحل تماس Mock">{PROCESS.map((label,index)=><li key={label} className={index<3?"active":""}><span>{index+1}</span>{label}{index<3?<LoaderCircle size={14} className="spin"/>:<Clock size={14}/>}</li>)}</ol>}
      <ManualReport key={selection.offer.id} selection={selection}/>
    </>}
    <MobileNav />
  </main>;
}

function RunResult({run,onRerun}:{run:MockRun;onRerun:()=>void}) {
  return <section className="contact-result" data-testid="mock-result" data-run-id={run.id}>
    <div className="contact-result-heading"><h2>گزارش تماس شبیه‌سازی‌شده</h2><span className="source-pill">پاسخ Mock · تأیید واقعی نیست</span></div>
    <p className="contact-analysis" data-testid="mock-analysis">{run.analysis}</p>
    <dl className="contact-summary"><div><dt>سناریو</dt><dd>{SCENARIOS[run.scenario]}</dd></div><div><dt>قیمت دیتاست</dt><dd>{formatPrice(run.datasetOffer.price,run.datasetOffer.priceUnit)}</dd></div><div><dt>قیمت شبیه‌سازی‌شده</dt><dd data-testid="mock-price">{formatPrice(run.simulatedPrice,run.datasetOffer.priceUnit)}</dd></div><div><dt>موجودی شبیه‌سازی‌شده</dt><dd data-testid="mock-stock">{run.simulatedInStock===null?"نامشخص":run.simulatedInStock?"موجود در سناریو":"ناموجود در سناریو"}</dd></div><div><dt>اختلاف با دیتاست</dt><dd>{run.priceDifference===null?"قابل محاسبه نیست":`${run.priceDifference>0?"+":""}${formatNumber(run.priceDifference)} تومان`}</dd></div><div><dt>زمان اجرای Mock</dt><dd>{dateTime(run.createdAt)}</dd></div><div><dt>شناسه اجرا</dt><dd dir="ltr">{run.id}</dd></div></dl>
    <ol className="contact-stages">{run.stages.map(stage=><li key={stage.id}><Check size={15}/><span>{stage.label}</span><small>{dateTime(stage.timestamp)}</small></li>)}</ol>
    <div className="contact-transcript" aria-label="گفتگوی شبیه‌سازی‌شده">{run.transcript.map((turn,index)=><p key={index} className={`contact-turn-${turn.role}`}><b>{turn.role==="agent"?"دستیار":turn.role==="seller"?"فروشنده شبیه‌سازی‌شده":"موتور Mock"}</b><span>{turn.text}</span></p>)}</div>
    {run.scenario==="alternative" && <div className="contact-alternatives"><h3>آفرهای جایگزین واقعی در دیتاست</h3>{run.alternatives.length?run.alternatives.map((result,index)=><article key={result.offer.id ?? index}><b>{result.shop.displayName}</b><span>{formatPrice(result.offer.price,result.offer.priceUnit)} · قیمت دیتاست، موجودی تأییدنشده</span><Link href={`/products/${encodeURIComponent(result.offer.productId)}`}>مشخصات محصول جایگزین</Link>{result.offer.id && <Link onClick={()=>rememberContactSelection({product:{id:result.offer.productId,titleFa:"محصول جایگزین"},shop:result.shop,offer:result.offer})} href={`/contact?offer_id=${encodeURIComponent(result.offer.id)}`}>انتخاب این آفر برای Mock</Link>}</article>):<p>آفر جایگزین مرتبطی در داده‌های موجود پیدا نشد؛ گزینه ساختگی اضافه نشده است.</p>}</div>}
    <p className="contact-limitation">{run.limitation}</p><div className="contact-actions"><button onClick={onRerun}>اجرای مجدد با سناریوی دیگر</button><Link href="/contact/history">مشاهده تاریخچه</Link></div>
  </section>;
}

function ManualReport({selection}:{selection:ContactSelection}) {
  const [price,setPrice]=useState(""),[availability,setAvailability]=useState("unknown"),[method,setMethod]=useState("phone");
  const [observedAt,setObservedAt]=useState(localNow),[note,setNote]=useState("");
  const [reports,setReports]=useState<BuyerReport[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState(""),[retry,setRetry]=useState(0);
  useEffect(()=>{const controller=new AbortController();getBuyerReports(selection,controller.signal).then(body=>setReports(body.checks)).catch(problem=>{if(!controller.signal.aborted)setError(problem instanceof Error?problem.message:"دریافت گزارش‌ها انجام نشد.");});return()=>controller.abort();},[selection,retry]);
  async function submit(event:React.FormEvent<HTMLFormElement>) {
    event.preventDefault();setError("");setNotice("");const reported=parseToman(price),date=new Date(observedAt);
    if(price.trim()&&(reported===null||reported<=0||!Number.isSafeInteger(reported)||reported>9_000_000_000_000_000||price.trim().startsWith("-"))){setError("قیمت اعلام‌شده باید یک مبلغ مثبت و معتبر باشد.");return;}
    if(Number.isNaN(date.getTime())||date.getTime()>Date.now()+60000){setError("زمان تماس یا مراجعه باید معتبر و در گذشته باشد.");return;}
    const inStock=availability==="in_stock"?true:availability==="out_of_stock"?false:null;
    const outcome=availability==="no_answer"?"no_answer":inStock===false?"unavailable":reported!==null&&selection.offer.price!==null&&reported!==selection.offer.price?"changed":reported!==null||inStock===true?"confirmed":"unclear";
    setBusy(true);
    try{await createBuyerReport(selection,{outcome,...(reported!==null?{reportedPrice:reported}:{}),inStock,method,observedAt:date.toISOString(),note});setNotice("گزارش با منشأ «گزارش‌شده توسط کاربر» ثبت شد؛ قیمت دیتاست تغییر نکرد.");setRetry(value=>value+1);}catch(problem){setError(problem instanceof Error?problem.message:"ثبت گزارش انجام نشد.");}finally{setBusy(false);}
  }
  return <section className="buyer-report"><h2>ثبت نتیجه تماس یا مراجعه واقعی توسط خودت</h2><p>اگر بیرون از برنامه با فروشگاه ارتباط گرفته‌ای، نتیجه را اینجا ثبت کن. منشأ این اطلاعات «گزارش‌شده توسط کاربر» است؛ سیستم آن را تأیید نمی‌کند.</p>
    <form onSubmit={submit} aria-label="گزارش تماس واقعی کاربر"><label>قیمت اعلام‌شده، تومان<input aria-label="قیمت گزارش‌شده توسط کاربر" inputMode="decimal" value={price} onChange={event=>setPrice(event.target.value)} placeholder="اگر مشخص نیست خالی بگذار"/></label><label>موجودی اعلام‌شده<select aria-label="موجودی گزارش‌شده" value={availability} onChange={event=>setAvailability(event.target.value)}><option value="unknown">نامشخص</option><option value="in_stock">موجود</option><option value="out_of_stock">ناموجود</option><option value="no_answer">پاسخی دریافت نکردم</option></select></label><label>روش دریافت اطلاعات<select aria-label="روش تماس واقعی" value={method} onChange={event=>setMethod(event.target.value)}><option value="phone">تماس خارج از برنامه</option><option value="visit">مراجعه حضوری</option><option value="other">روش دیگر</option></select></label><label>زمان تماس یا مراجعه<input aria-label="زمان تماس واقعی" type="datetime-local" value={observedAt} onChange={event=>setObservedAt(event.target.value)} required/></label><label className="buyer-report-note">توضیحات<textarea aria-label="توضیحات گزارش کاربر" value={note} onChange={event=>setNote(event.target.value)} maxLength={1000}/></label><button disabled={busy} type="submit">{busy?"در حال ثبت…":"ثبت گزارش کاربر"}</button></form>
    {error && <div role="alert" className="contact-error">{error}<button type="button" onClick={()=>setRetry(value=>value+1)}>دریافت دوباره گزارش‌ها</button></div>}{notice && <p role="status" className="contact-success">{notice}</p>}
    <div className="buyer-report-history" data-testid="buyer-reports">{reports.map(report=><article key={report.id}><b>گزارش‌شده توسط کاربر</b><span>{formatPrice(report.reportedPrice ?? report.reported_price)} · {report.outcome==="no_answer"?"پاسخ دریافت نشده":(report.inStock ?? report.in_stock)===true?"موجودی اعلام‌شده: موجود":(report.inStock ?? report.in_stock)===false?"موجودی اعلام‌شده: ناموجود":"موجودی نامشخص"}</span><small>زمان ارتباط: {dateTime(report.observedAt ?? report.observed_at)} · زمان ثبت: {dateTime(report.checkedAt ?? report.checked_at)}</small>{report.note && <p>{report.note}</p>}</article>)}</div>
  </section>;
}
export default function ContactPage(){return <Suspense fallback={<main className="catalog-state">در حال آماده‌سازی ارتباط…</main>}><Contact/></Suspense>;}
