import type { DataSource, KnownValue, ShopResult } from "./contracts";

const persianNumber = new Intl.NumberFormat("fa-IR");

export function formatNumber(value: number): string {
  return persianNumber.format(value);
}

export function formatPrice(value: number | null | undefined, unit = "تومان"): string {
  return typeof value === "number" && value > 0
    ? `${formatNumber(value)} ${unit}`
    : "قیمت نامشخص";
}

export function formatDistance(value: number): string {
  return `${persianNumber.format(value)} کیلومتر`;
}

export function formatDate(value?: string | null): string {
  if (!value) return "زمان ثبت نامشخص";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "زمان ثبت نامشخص";
  return new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium" }).format(date);
}

export function sourceLabel(source: DataSource): string {
  const labels: Record<DataSource, string> = {
    dataset: "دیتاست ترب",
    web: "وب",
    ai_knowledge: "دانش عمومی هوش مصنوعی",
    simulated: "نمونه‌سازی",
  };
  return labels[source];
}

export function openLabel(value: KnownValue<boolean>): string {
  if (!value.known || value.value === null) return "ساعت کاری نامشخص";
  return value.value ? "الان باز است" : "الان بسته است";
}

export function stockLabel(stock: ShopResult["offer"]["stock"]): string {
  if (stock === "verified_in_stock") return "موجودی تأییدشده";
  if (stock === "verified_out") return "ناموجودی تأییدشده";
  return "موجودی تأییدنشده";
}

export function directionsUrl(lat?: number | null, lng?: number | null): string | null {
  if (typeof lat !== "number" || typeof lng !== "number") return null;
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}

export function parseToman(value: string): number | null {
  const latin = value
    .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
  const digits = latin.replace(/[^0-9]/g, "");
  return digits ? Number(digits) : null;
}

export function formatBudgetInput(value: number | null): string {
  return value ? formatNumber(value) : "";
}
