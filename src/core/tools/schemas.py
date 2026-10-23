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
    shop_ids: list[str] = Field(min_length=1, max_length=8)
    product_id: str
    lat: float | None = None
    lng: float | None = None


class ShopInput(ToolInput):
    shop_id: str


class InquiryInput(ToolInput):
    shop_id: str
    product_id: str


class AlternativesInput(ToolInput):
    product_id: str
    shop_id: str | None = None
    max_price: int | None = None
    lat: float | None = None
    lng: float | None = None
    radius: float = Field(default=4, ge=0, le=100)


class HubInput(ToolInput):
    category_or_product: str


class QuickLookInput(ToolInput):
    product_id: str


class WebSearchInput(ToolInput):
    query: str


class LocationInput(ToolInput):
    text: str


class SavePreferenceInput(ToolInput):
    user_id: str
    key: str
    value: object


class LoadPreferencesInput(ToolInput):
    user_id: str
