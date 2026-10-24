# CI/CD با GitHub Actions

فایل workflow در `.github/workflows/deploy.yml` است. روی pull request و push به `main` فرانت را build و image بک‌اند را می‌سازد. استقرار فقط پس از آماده شدن سرور و دسترسی SSH فعال می‌شود.

## Secrets و variable مخزن

در تنظیمات مخزن، این Actions secrets را بسازید:

- `DEPLOY_HOST`: نشانی سرور
- `DEPLOY_USER`: کاربر استقرار
- `DEPLOY_PORT`: پورت SSH
- `DEPLOY_PATH`: مسیر اختصاصی برنامه روی سرور
- `DEPLOY_SSH_KEY`: کلید خصوصی مخصوص GitHub Actions
- `DEPLOY_KNOWN_HOSTS`: کلید میزبان SSH که fingerprint آن جداگانه تأیید شده باشد

برای استقرار خودکار بعد از هر push موفق به `main`، repository variable به نام `DEPLOY_ENABLED` را برابر `true` قرار دهید. تا آن زمان، build و CI اجرا می‌شوند اما چیزی روی سرور منتشر نمی‌شود. اجرای دستی workflow نیز با ورودی `deploy` کنترل می‌شود.

## پیش‌نیازهای سرور

روی سرور باید Docker و Docker Compose نصب باشند. در مسیر `DEPLOY_PATH` فایل `.env` و دیتابیس `data/torob.sqlite` باید وجود داشته باشند. هر دو مورد خارج از Git و خارج از انتقال‌های workflow نگه داشته می‌شوند؛ در نتیجه pushهای بعدی داده‌ها و تنظیمات را حذف یا جایگزین نمی‌کنند.

پس از استقرار، workflow وضعیت Compose و endpoint سلامت `/api/health` را بررسی می‌کند. دامنه و TLS در تنظیم Nginx فعلی تعریف نشده‌اند و باید جداگانه تنظیم شوند.
