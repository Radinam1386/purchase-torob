"use client";

import {
  AlertCircle,
  ArrowRight,
  BadgeAlert,
  BadgeCheck,
  Check,
  Clock,
  Clock3,
  DollarSign,
  MessageSquare,
  Package,
  PhoneCall,
  RefreshCw,
  Send,
  ShieldCheck,
  Store,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";

import { listInquiries, sellerReply } from "@/lib/api";
import type { Inquiry, InquiryChannel, InquiryStatus } from "@/lib/contracts";
import { formatNumber, formatPrice } from "@/lib/format";

export default function SellerSimPage() {
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [customPriceInput, setCustomPriceInput] = useState<Record<string, string>>({});
  const [customNoteInput, setCustomNoteInput] = useState<Record<string, string>>({});
  const [editingPriceForId, setEditingPriceForId] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  async function fetchInquiries() {
    try {
      const data = await listInquiries({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      });
      setInquiries(data.inquiries || []);
      setLastUpdated(new Date().toLocaleTimeString("fa-IR"));
    } catch (err) {
      console.error("Failed to fetch inquiries", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchInquiries();
  }, [statusFilter]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      void fetchInquiries();
    }, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh, statusFilter]);

  async function handleAction(
    inquiryId: string,
    action: "in_stock" | "out_of_stock" | "price_changed" | "delay_10m",
  ) {
    try {
      setActionBusyId(inquiryId);
      const customPriceStr = customPriceInput[inquiryId];
      const customPrice = customPriceStr ? parseInt(customPriceStr.replace(/\D/g, ""), 10) : undefined;
      const note = customNoteInput[inquiryId];

      await sellerReply(inquiryId, {
        action,
        customPrice: !isNaN(Number(customPrice)) ? customPrice : undefined,
        note: note || undefined,
      });

      setEditingPriceForId(null);
      await fetchInquiries();
    } catch (err) {
      console.error("Failed to perform action", err);
    } finally {
      setActionBusyId(null);
    }
  }

  const channelBadges: Record<InquiryChannel, { label: string; icon: typeof MessageSquare; className: string }> = {
    panel: { label: "پنل فروشنده ترب", icon: Store, className: "channel-panel" },
    sms: { label: "پیامک (شبیه‌سازی)", icon: MessageSquare, className: "channel-sms" },
    chat: { label: "گفتگوی آنلاین", icon: MessageSquare, className: "channel-chat" },
    ai_call: { label: "تماس هوش مصنوعی", icon: PhoneCall, className: "channel-ai-call" },
  };

  const statusLabels: Record<InquiryStatus, { label: string; className: string }> = {
    draft: { label: "پیش‌نویس (تأیید نشده)", className: "status-draft" },
    sent: { label: "ارسال‌شده (جدید)", className: "status-sent" },
    delivered: { label: "تحویل‌شده", className: "status-delivered" },
    read: { label: "مشاهده‌شده", className: "status-read" },
    answered: { label: "پاسخ داده شد", className: "status-answered" },
    no_answer: { label: "منقضی / بی‌پاسخ", className: "status-no-answer" },
    cancelled: { label: "لغو توسط خریدار", className: "status-cancelled" },
  };

  return (
    <div className="seller-sim-container" dir="rtl">
      {/* Header */}
      <header className="seller-sim-header">
        <div className="seller-sim-header-inner">
          <div className="seller-brand">
            <span className="seller-logo"><Store size={22} /></span>
            <div>
              <h1>پنل فروشندگان ترب <em>(شبیه‌ساز ارتباط)</em></h1>
              <p>محیط تست دمو دو پنجره‌ای برای پاسخ‌دهی لحظه‌ای فروشگاه به خریدار</p>
            </div>
          </div>
          <div className="seller-sim-controls">
            <div className="auto-refresh-toggle">
              <label>
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <span>بروزرسانی خودکار (هر ۳ ثانیه)</span>
              </label>
            </div>
            <button
              type="button"
              className="refresh-btn"
              onClick={() => void fetchInquiries()}
              disabled={loading}
              title="بارگذاری مجدد"
            >
              <RefreshCw size={15} className={loading ? "spin" : ""} />
              <span>{lastUpdated ? `آخرین بروزرسانی: ${lastUpdated}` : "بروزرسانی"}</span>
            </button>
            <a href="/" className="back-to-shop-link">
              <span>بازگشت به برنامه خریدار</span>
              <ArrowRight size={14} />
            </a>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="seller-sim-main">
        {/* Filters and Counters */}
        <div className="seller-filter-bar">
          <div className="filter-buttons">
            <button
              type="button"
              className={statusFilter === "all" ? "active" : ""}
              onClick={() => setStatusFilter("all")}
            >
              همه استعلام‌ها ({inquiries.length})
            </button>
            <button
              type="button"
              className={statusFilter === "pending" ? "active" : ""}
              onClick={() => setStatusFilter("pending")}
            >
              در انتظار پاسخ ({inquiries.filter((i) => ["sent", "delivered", "read"].includes(i.status)).length})
            </button>
            <button
              type="button"
              className={statusFilter === "answered" ? "active" : ""}
              onClick={() => setStatusFilter("answered")}
            >
              پاسخ داده شده ({inquiries.filter((i) => i.status === "answered").length})
            </button>
            <button
              type="button"
              className={statusFilter === "draft" ? "active" : ""}
              onClick={() => setStatusFilter("draft")}
            >
              پیش‌نویس‌ها ({inquiries.filter((i) => i.status === "draft").length})
            </button>
          </div>

          <div className="seller-demo-hint">
            <BadgeAlert size={14} />
            <span>راهنمای دمو: دکمه‌های تک‌لمسی موجودی/قیمت فوراً وضعیت استعلام را در اپ خریدار به‌روز می‌کنند.</span>
          </div>
        </div>

        {/* Inquiries List */}
        <div className="seller-cards-list">
          {inquiries.length === 0 ? (
            <div className="seller-empty-state">
              <Store size={36} />
              <p>هیچ استعلامی با این فیلتر ثبت نشده است.</p>
              <span>از برنامه خریدار روی دکمه «استعلام نمونه‌سازی» یا «استعلام موجودی» کلیک کنید تا در این پنل دریافت شود.</span>
            </div>
          ) : (
            inquiries.map((inquiry) => {
              const channel = inquiry.channel || "panel";
              const ChannelIcon = channelBadges[channel]?.icon || Store;
              const status = inquiry.status;
              const isActionable = ["sent", "delivered", "read"].includes(status);
              const answer = inquiry.answer;
              const isBusy = actionBusyId === inquiry.id;

              return (
                <article className={`seller-inquiry-card status-border-${status}`} key={inquiry.id}>
                  {/* Card Header */}
                  <div className="seller-card-top">
                    <div className="seller-shop-badge">
                      <Store size={15} />
                      <strong>{inquiry.shopName || `فروشگاه #${inquiry.shopId}`}</strong>
                    </div>

                    <div className="seller-tags-row">
                      <span className={`channel-pill ${channelBadges[channel]?.className}`}>
                        <ChannelIcon size={13} />
                        {channelBadges[channel]?.label || channel}
                      </span>
                      <span className={`status-pill ${statusLabels[status]?.className}`}>
                        {statusLabels[status]?.label || status}
                      </span>
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="seller-card-body">
                    <div className="seller-product-row">
                      <div className="product-info-col">
                        <span className="product-title-text">
                          <Package size={14} />
                          {inquiry.productTitle || `محصول #${inquiry.productId}`}
                        </span>
                        {inquiry.datasetPrice && (
                          <span className="dataset-price-pill">
                            قیمت درج‌شده در ترب: {formatPrice(inquiry.datasetPrice)}
                          </span>
                        )}
                      </div>
                      <span className="inquiry-time-text">
                        <Clock size={12} />
                        {new Date(inquiry.createdAt || Date.now()).toLocaleTimeString("fa-IR", {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    </div>

                    {/* Request Details */}
                    {inquiry.requestDetails && (
                      <div className="seller-requests-tags">
                        {inquiry.requestDetails.etaMinutes != null && (
                          <span className="req-tag">
                            <Clock3 size={12} /> رسیدن خریدار تا {inquiry.requestDetails.etaMinutes} دقیقه دیگر
                          </span>
                        )}
                        {inquiry.requestDetails.holdRequested && (
                          <span className="req-tag hold-tag">
                            <ShieldCheck size={12} /> خریدار درخواست رزرو موقت دارد
                          </span>
                        )}
                        {inquiry.requestDetails.sizeOrColor && (
                          <span className="req-tag">
                            مشخصات: {inquiry.requestDetails.sizeOrColor}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Inquiry Message */}
                    {inquiry.timeline?.[0]?.title && (
                      <div className="inquiry-incoming-message">
                        <strong>پیام دستیار خریدار:</strong>
                        <p>«سلام، از طرف خریدار ترب حضوری تماس می‌گیرم/پیام می‌دهم؛ آیا کالا در فروشگاه شما موجود است؟»</p>
                      </div>
                    )}

                    {/* Already Answered Summary */}
                    {status === "answered" && answer && (
                      <div className={`seller-response-summary ${answer.inStock ? "answered-in-stock" : "answered-out-stock"}`}>
                        <div className="summary-title">
                          {answer.inStock ? <BadgeCheck size={16} /> : <XCircle size={16} />}
                          <strong>
                            پاسخ ثبت‌شده: {answer.inStock ? "موجود در فروشگاه" : "ناموجود"}
                            {answer.priceChanged && ` (تغییر قیمت به ${formatPrice(answer.price)})`}
                          </strong>
                        </div>
                        {answer.note && <p className="summary-note">{answer.note}</p>}
                        {answer.holdConfirmed && (
                          <span className="summary-hold">
                            <Check size={12} /> رزرو موقت تأیید شده است.
                          </span>
                        )}
                      </div>
                    )}

                    {/* 1-Touch Action Buttons for Seller */}
                    {isActionable && (
                      <div className="seller-actions-panel">
                        <span className="actions-title">پاسخ سریع با یک لمس:</span>
                        <div className="seller-action-buttons">
                          <button
                            type="button"
                            className="btn-action btn-in-stock"
                            disabled={isBusy}
                            onClick={() => void handleAction(inquiry.id, "in_stock")}
                          >
                            <BadgeCheck size={15} />
                            <span>موجود است (تأیید قیمت)</span>
                          </button>

                          <button
                            type="button"
                            className="btn-action btn-out-stock"
                            disabled={isBusy}
                            onClick={() => void handleAction(inquiry.id, "out_of_stock")}
                          >
                            <XCircle size={15} />
                            <span>ناموجود است</span>
                          </button>

                          <button
                            type="button"
                            className="btn-action btn-price-change"
                            disabled={isBusy}
                            onClick={() => {
                              setEditingPriceForId(
                                editingPriceForId === inquiry.id ? null : inquiry.id,
                              );
                            }}
                          >
                            <DollarSign size={15} />
                            <span>تغییر قیمت...</span>
                          </button>

                          <button
                            type="button"
                            className="btn-action btn-delay"
                            disabled={isBusy}
                            onClick={() => void handleAction(inquiry.id, "delay_10m")}
                          >
                            <Clock3 size={15} />
                            <span>۱۰ دقیقه بعد پاسخ می‌دهم</span>
                          </button>
                        </div>

                        {/* Price Change Input Drawer */}
                        {editingPriceForId === inquiry.id && (
                          <div className="seller-price-editor">
                            <label htmlFor={`price-${inquiry.id}`}>قیمت جدید فروشگاه (تومان):</label>
                            <div className="price-input-row">
                              <input
                                id={`price-${inquiry.id}`}
                                type="text"
                                placeholder={
                                  inquiry.datasetPrice
                                    ? formatNumber(Math.round(inquiry.datasetPrice * 1.05))
                                    : "مثلاً ۳۵,۰۰۰,۰۰۰"
                                }
                                value={customPriceInput[inquiry.id] || ""}
                                onChange={(e) =>
                                  setCustomPriceInput({
                                    ...customPriceInput,
                                    [inquiry.id]: e.target.value,
                                  })
                                }
                              />
                              <input
                                type="text"
                                placeholder="توضیح اختیاری (مثلاً: فقط رنگ مشکی)"
                                value={customNoteInput[inquiry.id] || ""}
                                onChange={(e) =>
                                  setCustomNoteInput({
                                    ...customNoteInput,
                                    [inquiry.id]: e.target.value,
                                  })
                                }
                              />
                              <button
                                type="button"
                                className="btn-save-price"
                                disabled={isBusy}
                                onClick={() => void handleAction(inquiry.id, "price_changed")}
                              >
                                <Check size={14} />
                                <span>ارسال قیمت جدید</span>
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </article>
              );
            })
          )}
        </div>
      </main>
    </div>
  );
}
