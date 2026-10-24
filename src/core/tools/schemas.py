"""Input schemas used to expose predictable tools to the language model."""

from pydantic import BaseModel, ConfigDict, Field


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchProductsInput(ToolInput):
    query: str = Field(description="نام یا توضیح محصول به فارسی")
    category: str | None = None
    max_price: int | None = None
    filters: dict[str, str | int] | None = None
    limit: int = Field(default=8, ge=1, le=20)


class GetOffersInput(ToolInput):
    product_id: str
    lat: float = Field(description="عرض جغرافیایی فعلی کاربر")
    lng: float = Field(description="طول جغرافیایی فعلی کاربر")
    radius: float = Field(default=4, ge=0, le=100)
    max_price: int | None = None
    installment: bool = False
    express: bool = False
    open_now: bool = False


class CompareShopsInput(ToolInput):
    shop_ids: list[str] = Field(default_factory=list, max_length=8)
    offer_ids: list[str] = Field(default_factory=list, max_length=8)
    product_id: str
    lat: float | None = None
    lng: float | None = None


class ShopInput(ToolInput):
    shop_id: str


class VisitGuideInput(ToolInput):
    shop_id: str
    product_id: str | None = None
    offer_id: str | None = None
    backup_shop_id: str | None = None
    lat: float | None = None
    lng: float | None = None


class InquiryInput(ToolInput):
    shop_id: str
    product_id: str
    offer_id: str | None = None


class DraftInquiryInput(ToolInput):
    shop_id: str
    product_id: str
    offer_id: str | None = None
    eta_minutes: int | None = Field(default=None, description="تخمین زمان رسیدن کاربر به دقیقه")
    quantity: int = Field(default=1, ge=1, description="تعداد درخواستی")
    size_or_color: str | None = Field(default=None, description="رنگ، سایز یا مشخصه فنی مورد نظر")
    hold_requested: bool = Field(default=False, description="درخواست رزرو و نگهداری کالا تا رسیدن کاربر")
    channel: str | None = Field(default=None, description="کانال ارتباطی (panel, sms, chat, ai_call)")


class SendInquiryInput(ToolInput):
    inquiry_id: str = Field(description="شناسه استعلام یا پیش‌نویس")
    confirmed: bool = Field(default=False, description="تأیید صریح کاربر برای ارسال")
    edited_message: str | None = Field(default=None, description="متن ویرایش‌شده پیام توسط کاربر")


class SendInquiryBatchInput(ToolInput):
    shop_ids: list[str] = Field(min_length=1, max_length=5, description="شناسه‌های ۲ تا ۳ فروشگاه")
    product_id: str
    eta_minutes: int | None = None
    quantity: int = Field(default=1, ge=1)
    size_or_color: str | None = None
    hold_requested: bool = False
    confirmed: bool = Field(default=False, description="تأیید صریح کاربر برای ارسال")


class GetInquiryStatusInput(ToolInput):
    inquiry_id: str


class ListInquiriesInput(ToolInput):
    shop_id: str | None = None
    status: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class CancelInquiryInput(ToolInput):
    inquiry_id: str
    reason: str | None = None


class FollowUpInquiryInput(ToolInput):
    inquiry_id: str
    escalate_channel: bool = Field(default=True, description="ارتقای کانال در صورت بی‌پاسخ بودن")


class AlternativesInput(ToolInput):
    product_id: str
    shop_id: str | None = None
    max_price: int | None = None
    lat: float | None = None
    lng: float | None = None
    radius: float = Field(default=4, ge=0, le=100)
    installment: bool = False
    express: bool = False
    open_now: bool = False


class HubInput(ToolInput):
    category_or_product: str


class QuickLookInput(ToolInput):
    product_id: str


class WebSearchInput(ToolInput):
    query: str


class LocationInput(ToolInput):
    text: str


class SavePreferenceInput(ToolInput):
    key: str
    value: object


class LoadPreferencesInput(ToolInput):
    pass
