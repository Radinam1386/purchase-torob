"""Typed data contracts shared by tools, the agent, and future clients."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


def _camel_case(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)

Source = Literal["dataset", "web", "ai_knowledge", "simulated"]
StockStatus = Literal["unverified", "verified_in_stock", "verified_out"]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        alias_generator=_camel_case,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class KnownValue(ContractModel):
    value: bool | None
    source: Source
    known: bool


class Product(ContractModel):
    id: str
    title_fa: str
    title_en: str | None = None
    brand: str | None = None
    category: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)


class Shop(ContractModel):
    id: str
    display_name: str
    has_real_name: bool
    instagram: str | None = None
    website: str | None = None
    lat: float | None = None
    lng: float | None = None
    address_text: str | None = None
    mall: str | None = None
    floor: str | None = None
    unit: str | None = None
    hours: dict[str, object] = Field(default_factory=dict)
    tarob_pay_in_store: bool | None = None
    installment: bool | None = None
    kalabarg: bool | None = None
    express_delivery: bool | None = None


class Warranty(ContractModel):
    provider: str | None = None
    months: int | None = None


class Offer(ContractModel):
    id: str
    shop_id: str
    product_id: str
    price: int | None
    price_unit: str = "تومان"
    price_updated_at: str | None = None
    warranty: Warranty | None = None
    stock: StockStatus = "unverified"


class ShopResult(ContractModel):
    shop: Shop
    offer: Offer
    distance_km: float
    open_now: KnownValue
    reasons: list[str]


class InquiryAnswer(ContractModel):
    in_stock: bool
    price: int | None = None
    note: str | None = None


class Inquiry(ContractModel):
    id: str
    shop_id: str
    product_id: str
    offer_id: str | None = None
    status: Literal["sent", "reviewing", "answered", "no_answer"] = "sent"
    answer: InquiryAnswer | None = None
    simulated: Literal[True] = True


class MarketHub(ContractModel):
    category: str
    name: str
    neighborhood: str
    lat: float
    lng: float
    note: str
    coordinate_source: Source
    coordinate_verified: bool


class ProductCards(ContractModel):
    kind: Literal["product_cards"]
    products: list[Product]
    source: Source


class ShopCards(ContractModel):
    kind: Literal["shop_cards"]
    results: list[ShopResult]
    source: Source


class CompareCard(ContractModel):
    kind: Literal["compare"]
    results: list[ShopResult]
    source: Source


class InquiryCard(ContractModel):
    kind: Literal["inquiry"]
    inquiry: Inquiry
    source: Literal["simulated"] = "simulated"


class AlternativeOption(ContractModel):
    product: Product
    results: list[ShopResult]


class AlternativesCard(ContractModel):
    kind: Literal["alternatives"]
    options: list[AlternativeOption]
    source: Source


class HubCard(ContractModel):
    kind: Literal["hub"]
    hubs: list[MarketHub]
    source: Literal["ai_knowledge"] = "ai_knowledge"


class QuickLookCard(ContractModel):
    kind: Literal["quick_look"]
    product_id: str
    label: Literal["خلاصه هوش مصنوعی"]
    strengths: list[str]
    weaknesses: list[str]
    in_person_checks: list[str]
    source: Literal["ai_knowledge"] = "ai_knowledge"


class MallGuideCard(ContractModel):
    kind: Literal["mall_guide"]
    shop: Shop
    directions: list[str]
    offer: ShopResult | None = None
    inquiry: Inquiry | None = None
    backup: ShopResult | None = None
    source: Literal["dataset"] = "dataset"


class WebResult(ContractModel):
    title: str
    url: str
    snippet: str
    source: Literal["web"] = "web"


class WebCards(ContractModel):
    kind: Literal["web_results"]
    results: list[WebResult]
    source: Literal["web"] = "web"


AssistantCard = Annotated[
    Union[
        ProductCards, ShopCards, CompareCard, InquiryCard, AlternativesCard,
        HubCard, QuickLookCard, MallGuideCard, WebCards,
    ],
    Field(discriminator="kind"),
]


class AssistantResponse(ContractModel):
    text: str
    cards: list[AssistantCard] = Field(default_factory=list)
    clarification_question: str | None = None


class ConversationLocation(ContractModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    label: str | None = None


class ConversationFilters(ContractModel):
    installment: bool | None = None
    express: bool | None = None
    open_now: bool | None = None


class ConversationState(ContractModel):
    location: ConversationLocation | None = None
    budget: int | None = Field(default=None, ge=0)
    radius_km: float = Field(default=4, ge=0, le=100)
    filters: ConversationFilters = Field(default_factory=ConversationFilters)
    selected_product_id: str | None = Field(default=None, max_length=120)
    selected_shop_ids: list[str] = Field(default_factory=list, max_length=8)
    selected_offer_ids: list[str] = Field(default_factory=list, max_length=8)
    preferences: dict[str, object] = Field(default_factory=dict)


class AgentEvent(ContractModel):
    type: Literal["text_delta", "tool_start", "tool_end", "response"]
    text: str | None = None
    name: str | None = None
    call_id: str | None = None
    ok: bool | None = None
    duration_ms: int | None = None
    response: AssistantResponse | None = None
