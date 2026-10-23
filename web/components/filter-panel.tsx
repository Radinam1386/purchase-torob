import { Check, Crosshair, MapPin, RotateCcw, SlidersHorizontal } from "lucide-react";

import { formatNumber, parseToman } from "@/lib/format";

export interface FilterValues {
  location: string;
  budget: string;
  radiusKm: number;
  openNow: boolean;
  installment: boolean;
}

interface FilterPanelProps {
  values: FilterValues;
  busy: boolean;
  hasSelectedProduct: boolean;
  onChange: (values: FilterValues) => void;
  onUseCurrentLocation: () => void;
  onApply: () => void;
  onReset: () => void;
}

const QUICK_BUDGETS = [5_000_000, 15_000_000, 30_000_000];

export function FilterPanel({
  values,
  busy,
  hasSelectedProduct,
  onChange,
  onUseCurrentLocation,
  onApply,
  onReset,
}: FilterPanelProps) {
  function update<K extends keyof FilterValues>(key: K, value: FilterValues[K]) {
    onChange({ ...values, [key]: value });
  }

  const parsedBudget = parseToman(values.budget);

  return (
    <aside className="filter-panel" aria-label="فیلترهای جستجوی حضوری">
      <div className="filter-heading">
        <div className="filter-heading-icon"><SlidersHorizontal size={17} /></div>
        <div>
          <h2>شرایط خرید</h2>
          <p>نتیجه را برای خودت تنظیم کن</p>
        </div>
        <button type="button" className="reset-button" onClick={onReset} aria-label="پاک کردن فیلترها" title="پاک کردن فیلترها">
          <RotateCcw size={15} />
        </button>
      </div>

      <div className="filter-field">
        <label htmlFor="location-input">محدوده‌ی جستجو</label>
        <div className="location-control">
          <MapPin size={16} />
          <input
            id="location-input"
            value={values.location}
            onChange={(event) => update("location", event.target.value)}
            placeholder="مثلاً ونک، تهران"
            autoComplete="off"
          />
          <button type="button" onClick={onUseCurrentLocation} aria-label="استفاده از موقعیت من" title="موقعیت من">
            <Crosshair size={16} />
          </button>
        </div>
        <span className="field-note">نام محله را وارد کن یا موقعیت خودت را انتخاب کن.</span>
      </div>

      <div className="filter-field">
        <div className="field-label-row">
          <label htmlFor="budget-input">حداکثر بودجه</label>
          <span className="field-note">اختیاری</span>
        </div>
        <div className="budget-control">
          <input
            id="budget-input"
            inputMode="numeric"
            value={values.budget}
            onChange={(event) => update("budget", event.target.value)}
            placeholder="مثلاً ۲۰٬۰۰۰٬۰۰۰"
            aria-describedby="budget-unit"
          />
          <span id="budget-unit">تومان</span>
        </div>
        <div className="quick-budgets" aria-label="بودجه‌های پیشنهادی">
          {QUICK_BUDGETS.map((budget) => (
            <button
              type="button"
              key={budget}
              className={parsedBudget === budget ? "active" : ""}
              onClick={() => update("budget", formatNumber(budget))}
            >
              {formatNumber(budget / 1_000_000)} میلیون
            </button>
          ))}
        </div>
      </div>

      <div className="filter-field radius-field">
        <div className="field-label-row">
          <label htmlFor="radius-input">شعاع جستجو</label>
          <output htmlFor="radius-input">{formatNumber(values.radiusKm)} کیلومتر</output>
        </div>
        <input
          id="radius-input"
          type="range"
          min="1"
          max="20"
          step="1"
          value={values.radiusKm}
          onChange={(event) => update("radiusKm", Number(event.target.value))}
          aria-label="شعاع جستجو به کیلومتر"
        />
        <div className="range-ends"><span>۱ کیلومتر</span><span>۲۰ کیلومتر</span></div>
      </div>

      <div className="filter-divider" />

      <div className="filter-toggles">
        <ToggleRow
          title="فقط فروشگاه‌های باز"
          description="برای مراجعه‌ی همین حالا"
          checked={values.openNow}
          onChange={(checked) => update("openNow", checked)}
        />
        <ToggleRow
          title="خرید قسطی حضوری"
          description="فقط با مدرک پرداخت حضوری"
          checked={values.installment}
          onChange={(checked) => update("installment", checked)}
        />
      </div>

      {hasSelectedProduct ? (
        <button type="button" className="apply-filters" onClick={onApply} disabled={busy}>
          <Check size={16} /> اعمال روی همین کالا
        </button>
      ) : (
        <p className="filter-hint">با جستجوی یک کالا، این شرایط روی فروشگاه‌ها اعمال می‌شوند.</p>
      )}
    </aside>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span className="toggle-copy"><strong>{title}</strong><small>{description}</small></span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="toggle-track" aria-hidden="true"><span /></span>
    </label>
  );
}
