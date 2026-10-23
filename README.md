# هسته‌ی دستیار خرید حضوری ترب

دستیار خرید حضوری تهران با هسته‌ی Python/LangGraph و رابط React/Next.js. رابط فارسی و راست‌به‌چپ برای پیدا کردن محصول، تنظیم محدوده‌ی جستجو، دیدن فروشگاه‌ها و مقایسه‌ی پیشنهادها طراحی شده است.

## راه‌اندازی

به Python 3.11 یا جدیدتر نیاز است. ساخت محیط مجازی و نصب وابستگی‌ها:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

کلید مدل و در صورت نیاز کلید جستجوی وب را در `.env` وارد کنید. مقدار کلید در کد قرار ندارد.

## فرمان‌ها

```bash
python -m src.scripts.load_data  # ساخت مجدد SQLite/FTS5 و گزارش کیفیت
python -m src.scripts.test_tools # smoke test ابزارهای محلی
python -m src.scripts.check_llm  # تست واقعی models، پاسخ و tool calling
python -m src.cli.chat           # گفتگوی ترمینال با LLM واقعی
python -m src.scripts.evals      # اجرای ۱۵ سناریوی ارزیابی با LLM واقعی
```

## اجرای رابط کاربری

در ترمینال اول، API را از ریشه‌ی پروژه اجرا کنید:

```bash
uvicorn src.api:app --reload --port 8000
```

در ترمینال دوم، Next.js را اجرا کنید:

```bash
cd web
npm install
npm run dev
```

رابط در `http://localhost:3000` و API در `http://localhost:8000` در دسترس است. برای تغییر آدرس API می‌توانید `NEXT_PUBLIC_AGENT_API` را در `web/.env.local` تنظیم کنید. کلیدهای مدل و سرویس‌های خارجی فقط در `.env` ریشه‌ی پروژه قرار می‌گیرند.

لودر دیتاست را در فایل SQLite موقت می‌سازد و تنها پس از تکمیل موفق، جایگزین `data/torob.sqlite` می‌کند. گزارش کیفیت در `data/quality-report.json` است.

## ساختار

- `src/core/contract.py`: قرارداد Pydantic و کارت‌های خروجی با نام فیلدهای سازگار با UI (`camelCase`).
- `src/core/agent.py`: مدل LangChain سازگار با OpenAI، گراف LangGraph، مدیریت state، رویداد و لاگ ابزار.
- `src/core/tools/`: ابزارهای مستقل و گروه‌بندی‌شده برای کالا، فروشگاه، مکان، وب و ترجیحات.
- `src/core/database.py`: اتصال SQLite.
- `src/scripts/`: بارگذاری داده، smoke test و ارزیابی.
- `prompts/system.fa.md`: قواعد agent به فارسی.
- `src/api.py`: پل FastAPI برای استریم رویدادهای ایجنت به رابط.
- `web/`: رابط React و Next.js، کارت‌های پاسخ و فیلترهای جستجو.

ابزارهای وب نیازمند دسترسی شبکه‌اند. اگر جستجوی وب در دسترس نباشد، ایجنت باید محدودیت را شفاف اعلام کند و از آن به‌عنوان منبع حقیقت استفاده نکند.
