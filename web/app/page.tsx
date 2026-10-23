import Link from "next/link";
import { ArrowLeft, MapPin, Search, ShieldCheck, Store, Tag } from "lucide-react";

const ideas = ["گوشی موبایل", "کتونی روزمره", "هدفون"];

export default function HomePage() {
  return <main className="landing" dir="rtl">
    <header className="site-nav"><Link className="brand" href="/">ترب <span>حضوری</span></Link><nav><Link href="/products">محصولات</Link><Link href="/chat">دستیار خرید</Link></nav><Link className="nav-cta" href="/chat">شروع خرید <ArrowLeft size={16}/></Link></header>
    <section className="hero"><div className="hero-copy"><span className="eyebrow"><MapPin size={14}/> خرید حضوری در تهران</span><h1>پیدا کن، مقایسه کن،<br/><em>با خیال راحت برو بخر.</em></h1><p>محصول و فروشگاه‌های اطرافت را پیدا کن؛ قیمت ثبت‌شده، فاصله و شرایط مراجعه را یک‌جا ببین.</p>
      <form action="/chat" className="hero-search"><input type="hidden" name="new" value="1"/><Search size={20}/><input name="q" aria-label="محصول برای شروع گفتگوی جدید" placeholder="مثلاً گوشی برای عکاسی می‌خوام…"/><button>شروع جست‌وجو <ArrowLeft size={17}/></button></form>
      <div className="idea-row"><span>از اینجا شروع کن</span>{ideas.map(x=><Link key={x} href={`/chat?new=1&q=${encodeURIComponent(x)}`}>{x}</Link>)}</div>
    </div><div className="hero-art" aria-label="تصویرسازی فروشگاه و کالا"><div className="art-circle"></div><div className="art-pin"><MapPin/><b>نزدیک تو</b><small>فروشگاه‌های اطراف</small></div><div className="art-bag">ترب</div><div className="art-card"><span>قیمت ثبت‌شده</span><b>مقایسه‌ی شفاف</b><i><Tag size={14}/> از دیتاست ترب</i></div><div className="art-store"><Store/><span>خرید از فروشگاه واقعی</span></div></div></section>
    <section className="feature-strip"><article><Search/><b>کشف کالا</b><span>با مدل دقیق یا نیازت شروع کن</span></article><article><Tag/><b>مقایسه‌ی قیمت</b><span>قیمت و زمان ثبت را جدا ببین</span></article><article><MapPin/><b>فروشگاه نزدیک</b><span>محدوده را خودت تعیین کن</span></article><article><ShieldCheck/><b>شفاف تا مراجعه</b><span>موجودی نامطمئن پنهان نمی‌ماند</span></article></section>
    <section className="landing-bottom"><div><span className="eyebrow">انتخاب با اطلاعات روشن</span><h2>خرید حضوری،<br/>از جست‌وجو تا مراجعه.</h2></div><Link className="large-cta" href="/chat">با دستیار شروع کن <ArrowLeft/></Link><Link className="text-link" href="/products">یا همه‌ی محصولات را ببین</Link></section>
    <footer className="site-footer"><span>ترب حضوری</span><span>قیمت ثبت‌شده با موجودی قطعی فرق دارد.</span></footer>
  </main>;
}
