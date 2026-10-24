"""Stateful LangGraph workflow for in-person shopping conversations."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from src.core.config import PROJECT_ROOT, settings
from src.core.contract import AgentEvent, AssistantResponse, ConversationLocation, ConversationState
from src.core.database import database
from src.core.llm import OpenAICompatibleChatModel
from src.core.response import parse_tool_payload, response_from_messages
from src.core.tool_logging import ToolCallLogger
from src.core.text import normalize_fa
from src.core.tools.registry import TOOLS
from src.core.user_context import reset_current_user_id, set_current_user_id

logger = logging.getLogger("purchase_torob.agent")


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    conversation: dict[str, Any]
    user_id: str
    tool_rounds: int
    clarification_question: str | None


class ChatTurn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


EventCallback = Callable[[AgentEvent], None]


class ShoppingAgent:
    """Coordinate the model, typed tools, conversation state, and response."""

    def __init__(self) -> None:
        settings.validate_llm()
        self._system_prompt = self._load_system_prompt()
        self._model = self._create_model()
        self._model_with_tools = self._model.bind_tools(TOOLS)
        self._graph = self._create_graph()

    @staticmethod
    def _load_system_prompt() -> str:
        path = PROJECT_ROOT / "prompts" / "system.fa.md"
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _create_model() -> OpenAICompatibleChatModel:
        return OpenAICompatibleChatModel(
            model_name=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.timeout_seconds,
            reasoning_effort=settings.llm_reasoning_effort,
            max_completion_tokens=1800,
        )

    def _create_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("advisor_gate", self._advisor_gate)
        workflow.add_node("clarify", self._ask_clarifying_question)
        workflow.add_node("agent", self._call_model)
        workflow.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
        workflow.add_edge(START, "advisor_gate")
        workflow.add_conditional_edges(
            "advisor_gate",
            lambda state: "clarify" if state.get("clarification_question") else "agent",
            {"clarify": "clarify", "agent": "agent"},
        )
        workflow.add_edge("clarify", END)
        workflow.add_conditional_edges(
            "agent", self._route_after_model, {"tools": "tools", "end": END}
        )
        workflow.add_edge("tools", "agent")
        return workflow.compile()

    @staticmethod
    def _advisor_gate(state: AgentState) -> dict[str, Any]:
        """Collect only decision-critical details before searching broad requests."""
        user_turns = [
            str(message.content) for message in state.get("messages", [])
            if isinstance(message, HumanMessage)
        ]
        latest = user_turns[-1] if user_turns else ""
        conversation = state.get("conversation", {})
        if _explicit_search_now(latest) or _has_specific_model(latest):
            return {}
        if conversation.get("selected_product_id") or conversation.get("selectedProductId"):
            return {}

        advisor = dict((conversation.get("preferences") or {}).get("_advisor", {}))
        category = advisor.get("category") or next(
            (label for term, label in _BROAD_PRODUCT_CATEGORIES.items() if term in normalize_fa(" ".join(user_turns))),
            None,
        )
        if not category:
            return {}

        history_text = normalize_fa(" ".join(user_turns))
        budget_known = bool(conversation.get("budget") or re.search(
            r"(?:\d[\d,.]*\s*(?:تومان|میلیون|هزار)|بودجه.{0,12}\d)", history_text
        ))
        use_known = bool(re.search(
            r"موسیقی|موزیک|بازی|گیم|دانشگاه|کار|عکاسی|فیلم|ورزش|دویدن|روزمره|پیاده|سفر|مکالمه|تماس|طراحی",
            history_text,
        ))
        requirements = {**advisor, "category": category, "budget_known": budget_known,
                        "use_known": use_known, "status": "collecting_requirements"}
        preferences = dict(conversation.get("preferences") or {})
        preferences["_advisor"] = requirements
        conversation["preferences"] = preferences

        if not use_known:
            question = f"{category} رو بیشتر برای چه کاری می‌خوای؟ اگر بودجه‌ات رو هم بگی دقیق‌تر پیشنهاد می‌دم."
        elif not budget_known:
            if category == "هدفون":
                question = f"برای گوش دادن به موسیقی، حدود بودجه‌ات چقدره؟ ترجیح خاصی بین مدل‌های روگوشی یا ایرباد داری؟"
            elif category in {"کتونی", "کفش"}:
                question = f"برای {latest.strip()} در دسته‌ی {category}، حدود بودجه‌ات چقدره؟"
            else:
                question = f"اوکی، برای {category} و {latest.strip()}؛ حدود بودجه‌ات چقدره؟"
        else:
            return {"conversation": conversation}
        requirements["status"] = "clarifying_requirements"
        return {"conversation": conversation, "clarification_question": question}

    @staticmethod
    def _ask_clarifying_question(state: AgentState) -> dict[str, Any]:
        question = state["clarification_question"]
        return {
            "messages": [AIMessage(content=json.dumps({
                "text": "برای اینکه پیشنهاد دقیق‌تری بدم",
                "clarificationQuestion": question,
            }, ensure_ascii=False))],
            "conversation": state["conversation"],
        }

    async def _call_model(self, state: AgentState) -> dict[str, Any]:
        conversation = state.get("conversation", {})
        for message in reversed(state.get("messages", [])):
            if isinstance(message, ToolMessage) and message.name == "resolve_location":
                resolved = (parse_tool_payload(message.content) or {}).get("data")
                if isinstance(resolved, dict) and "lat" in resolved and "lng" in resolved:
                    conversation["location"] = resolved
                break
        state["conversation"] = conversation
        response = await self._model_with_tools.ainvoke(
            [SystemMessage(content=self._make_prompt(state)), *state.get("messages", [])]
        )
        rounds = state.get("tool_rounds", 0) + int(bool(response.tool_calls))
        if rounds > settings.max_tool_rounds:
            raise RuntimeError("حداکثر دور ابزار ایجنت تمام شد.")
        return {
            "messages": [response],
            "conversation": state["conversation"],
            "tool_rounds": rounds,
        }

    def _make_prompt(self, state: AgentState) -> str:
        user_id = state.get("user_id", "local")
        conversation = state.get("conversation", {})
        preferences = self._load_preferences(user_id)
        conversation["preferences"] = {
            **conversation.get("preferences", {}),
            **preferences,
        }
        state["conversation"] = conversation
        serialized_state = json.dumps(conversation, ensure_ascii=False)
        return (
            f"{self._system_prompt}\n\n"
            f"وضعیت جاری گفتگو (JSON): {serialized_state}"
        )

    @staticmethod
    def _load_preferences(user_id: str) -> dict[str, Any]:
        with database(readonly=True) as connection:
            row = connection.execute(
                "SELECT preferences_json FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return json.loads(row["preferences_json"]) if row else {}

    @staticmethod
    def _route_after_model(state: AgentState) -> Literal["tools", "end"]:
        latest = state["messages"][-1]
        return "tools" if isinstance(latest, AIMessage) and latest.tool_calls else "end"

    async def stream(
        self,
        user_text: str,
        *,
        user_id: str = "local",
        conversation: ConversationState | None = None,
        history: list[ChatTurn] | None = None,
        on_event: EventCallback | None = None,
    ) -> AsyncIterator[AgentEvent]:
        state = conversation or self.initial_state()
        _apply_constraints(state, user_text)
        messages = [_history_message(turn) for turn in (history or [])]
        messages.append(HumanMessage(content=user_text))

        graph_input: AgentState = {
            "messages": messages,
            "conversation": state.model_dump(mode="json", by_alias=True),
            "user_id": user_id,
            "tool_rounds": 0,
        }
        final_state: AgentState | None = None
        tool_started_at: dict[str, float] = {}
        tool_logger = ToolCallLogger()
        started_at = time.monotonic()
        user_context_token = set_current_user_id(user_id)

        try:
            async with asyncio.timeout(settings.timeout_seconds):
                async for chunk in self._graph.astream(
                    graph_input,
                    stream_mode=["updates", "values"],
                    version="v2",
                    config={"callbacks": [tool_logger]},
                ):
                    if time.monotonic() - started_at > settings.timeout_seconds:
                        raise TimeoutError
                    if chunk["type"] == "values":
                        final_state = chunk["data"]
                    elif chunk["type"] == "updates":
                        events = _events_from_update(chunk["data"], tool_started_at)
                        for event in events:
                            yield _emit(event, on_event)
        except TimeoutError as error:
            raise TimeoutError("زمان مجاز پاسخ‌گویی ایجنت تمام شد.") from error
        finally:
            reset_current_user_id(user_context_token)

        if final_state is None:
            raise RuntimeError("گراف ایجنت بدون خروجی پایان یافت.")
        response = response_from_messages(final_state["messages"])
        response.clarification_question = final_state.get("clarification_question")
        _update_conversation(state, final_state)
        yield _emit(AgentEvent(type="text_delta", text=response.text), on_event)
        yield _emit(AgentEvent(type="response", response=response), on_event)

    async def run(self, user_text: str, **kwargs) -> AssistantResponse:
        response = None
        async for event in self.stream(user_text, **kwargs):
            if event.type == "response":
                response = event.response
        if response is None:
            raise RuntimeError("پاسخی دریافت نشد.")
        return response

    @staticmethod
    def initial_state() -> ConversationState:
        return ConversationState(
            location=ConversationLocation(lat=settings.default_lat, lng=settings.default_lng),
            radius_km=settings.default_radius_km,
        )


def _history_message(turn: ChatTurn) -> AnyMessage:
    if turn["role"] == "user":
        return HumanMessage(content=turn["content"])
    return AIMessage(content=turn["content"])


_BROAD_PRODUCT_CATEGORIES = {
    "گوشی": "گوشی",
    "موبایل": "گوشی",
    "لپتاپ": "لپ‌تاپ",
    "لپ‌تاپ": "لپ‌تاپ",
    "کتونی": "کتونی",
    "کفش": "کفش",
    "ماشین لباسشویی": "ماشین لباسشویی",
    "یخچال": "یخچال",
    "تلویزیون": "تلویزیون",
    "دوربین": "دوربین",
    "هدفون": "هدفون",
    "تبلت": "تبلت",
    "پرینتر": "پرینتر",
    "پاوربانک": "پاوربانک",
    "مانیتور": "مانیتور",
    "ساعت هوشمند": "ساعت هوشمند",
    "کولر": "کولر",
    "جاروبرقی": "جاروبرقی",
    "دوچرخه": "دوچرخه",
    "مبل": "مبل",
}
_BUYING_CONTEXT = re.compile(
    r"(?:بودجه|حداکثر|تا سقف|تا\s*[\d۰-۹٠-٩]|میلیون|میلیارد|هزار|"
    r"برای\s+(?:بازی|گیم|دانشگاه|کار|عکاسی|فیلم|ورزش|دویدن|روزمره|سفر|طراحی)|"
    r"بازی|گیم|دانشگاه|عکاسی|دویدن|روزمره|پیاده|سفر|برنامه.?نویسی|طراحی|"
    r"برای خانه|مصرف خانگی|صنعتی|چاپ روی پارچه|۳\s*متری|سه متری|مدل\s*[a-zA-Z0-9۰-۹٠-٩-]+)",
    re.IGNORECASE,
)


def _needs_clarification(text: str, conversation: dict[str, Any]) -> bool:
    if (
        conversation.get("selected_product_id")
        or conversation.get("selectedProductId")
        or re.search(r"product_[\w-]+", text)
        or _has_specific_model(text)
    ):
        return False
    if _BUYING_CONTEXT.search(text):
        return False
    # A prior turn can already contain a use case, budget, or selected model.
    prior_context = " ".join(
        str(value) for key, value in conversation.items()
        if key in {"budget", "preferences", "selected_product_id", "selectedProductId"} and value
    )
    if conversation.get("budget") or conversation.get("preferences") or prior_context:
        return False
    return any(category in text for category in _BROAD_PRODUCT_CATEGORIES)


def _explicit_search_now(text: str) -> bool:
    normalized = normalize_fa(text)
    return bool(re.search(r"همین الان|الان نشون بده|محصولات رو نشون|خودت بهترین|جستجو کن|جست‌وجو کن|پیدا کن|خودت انتخاب کن|فرقی نداره|مهم نیست|بدون بودجه|هر قیمتی", normalized))


def _clarification_for(text: str) -> str:
    category = next(
        (label for term, label in _BROAD_PRODUCT_CATEGORIES.items() if term in text),
        "این کالا",
    )
    if category in {"گوشی", "لپ‌تاپ", "دوربین", "تبلت"}:
        return f"{category} رو بیشتر برای چه کاری می‌خوای و حدود بودجه‌ات چقدره؟"
    if category in {"کتونی", "کفش"}:
        return f"{category} رو برای روزمره می‌خوای یا ورزش، و حدود بودجه‌ات چقدره؟"
    return f"برای {category} حدود بودجه‌ات چقدره و چه ویژگی‌ای برات مهم‌تره؟"


def _has_specific_model(text: str) -> bool:
    normalized = normalize_fa(text)
    return bool(re.search(
        r"(?:(?:samsung|سامسونگ|galaxy|گلکسی|iphone|آیفون|xiaomi|شیائومی)\s*"
        r"(?:[a-z]{1,3}\s*)?\d{2,4}\s*[a-z]{0,8}\b|"
        r"[a-z]{1,3}\s*\d{2,4}\s*[a-z]{0,8}\b)",
        normalized,
        re.IGNORECASE,
    ))


def _apply_constraints(state: ConversationState, text: str) -> None:
    normalized_text = normalize_fa(text).replace("٫", ".")
    budget_match = re.search(
        r"(?:بودجه(?:\s*(?:من|ام|م))?|حداکثر|تا سقف|تا)\s*(?:حدود\s*)?"
        r"(?<![-\d])([\d][\d.,٬]*)\s*(میلیارد|میلیون|هزار|م)?",
        normalized_text,
    )
    if budget_match:
        amount_text = budget_match.group(1).replace("٬", "")
        if "," in amount_text:
            amount_text = amount_text.replace(",", "")
        try:
            amount = float(amount_text)
            if not math.isfinite(amount):
                raise ValueError("Budget is outside the supported numeric range")
            factor = {"میلیارد": 1_000_000_000, "میلیون": 1_000_000, "هزار": 1_000, "م": 1_000_000}.get(
                budget_match.group(2), 1
            )
            calculated_budget = amount * factor
            if not math.isfinite(calculated_budget) or calculated_budget > 10**15:
                raise ValueError("Budget is outside the supported numeric range")
            state.budget = int(calculated_budget)
        except (OverflowError, ValueError):
            logger.info("Ignoring unparseable budget value: %r", amount_text)

    radius_match = re.search(
        r"(?:شعاع|محدوده)\s*(\d+(?:\.\d+)?)(?![\d.])",
        normalized_text,
    )
    if radius_match:
        radius = float(radius_match.group(1))
        if 0 <= radius <= 100:
            state.radius_km = radius

    negative_installment = re.search(
        r"(?:قسطی|اقساط|قسط)\s*(?:نمی\s*(?:خوام|خواهم)|نمیخوام|نمیخواهم|نه)|"
        r"بدون\s+(?:خرید\s+)?(?:قسطی|قسط|اقساط)",
        normalized_text,
    )
    if negative_installment:
        state.filters.installment = False
    elif "قسطی" in normalized_text or "اقساط" in normalized_text:
        state.filters.installment = True
    if "ارسال فوری" in text:
        state.filters.express = True
    if "الان باز" in text or "باز باشد" in text:
        state.filters.open_now = True


def _events_from_update(
    update: dict[str, Any], tool_started_at: dict[str, float]
) -> list[AgentEvent]:
    events = []
    for node_update in update.values():
        if not isinstance(node_update, dict):
            continue
        for message in node_update.get("messages", []):
            if isinstance(message, AIMessage):
                events.extend(_tool_start_events(message, tool_started_at))
            elif isinstance(message, ToolMessage):
                events.append(_tool_end_event(message, tool_started_at))
    return events


def _tool_start_events(
    message: AIMessage, tool_started_at: dict[str, float]
) -> list[AgentEvent]:
    events = []
    for call in message.tool_calls:
        call_id = call.get("id") or f"{call['name']}-{len(tool_started_at)}"
        if call_id in tool_started_at:
            continue
        tool_started_at[call_id] = time.monotonic()
        events.append(AgentEvent(type="tool_start", name=call["name"], call_id=call_id))
    return events


def _tool_end_event(
    message: ToolMessage, tool_started_at: dict[str, float]
) -> AgentEvent:
    started_at = tool_started_at.pop(message.tool_call_id, time.monotonic())
    payload = parse_tool_payload(message.content) or {}
    ok = message.status != "error" and "error" not in payload
    return AgentEvent(
        type="tool_end",
        name=message.name or "unknown",
        call_id=message.tool_call_id,
        ok=ok,
        duration_ms=round((time.monotonic() - started_at) * 1000),
    )


def _update_conversation(state: ConversationState, graph_state: AgentState) -> None:
    latest = graph_state.get("conversation", {})
    state.budget = latest.get("budget", state.budget)
    state.radius_km = latest.get("radiusKm", latest.get("radius_km", state.radius_km))
    state.preferences = latest.get("preferences", state.preferences)
    filters = latest.get("filters")
    if isinstance(filters, dict):
        state.filters = state.filters.model_validate(filters)
    location = latest.get("location")
    if location:
        state.location = ConversationLocation.model_validate(location)

    for message in graph_state.get("messages", []):
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                cname = call["name"]
                args = call.get("args", {})
                if cname in {"get_offers", "compare_shops", "draft_inquiry"}:
                    if args.get("product_id"):
                        state.selected_product_id = args.get("product_id")
                if cname == "compare_shops":
                    state.selected_shop_ids = args.get("shop_ids", [])
                    state.selected_offer_ids = args.get("offer_ids", [])
                if cname in {"inquire_shop", "get_shop_location_hint", "draft_inquiry"}:
                    offer_id = args.get("offer_id")
                    if offer_id:
                        state.selected_offer_ids = [offer_id]
                    shop_id = args.get("shop_id")
                    if shop_id and shop_id not in state.selected_shop_ids:
                        state.selected_shop_ids = [shop_id]
                if cname in {"send_inquiry", "get_inquiry_status", "cancel_inquiry", "follow_up_inquiry"}:
                    inq_id = args.get("inquiry_id")
                    if inq_id and inq_id not in state.selected_inquiry_ids:
                        state.selected_inquiry_ids.append(inq_id)
        elif isinstance(message, ToolMessage):
            if message.name == "resolve_location":
                resolved = (parse_tool_payload(message.content) or {}).get("data")
                if resolved:
                    state.location = ConversationLocation.model_validate(resolved)
            elif message.name == "draft_inquiry":
                data = (parse_tool_payload(message.content) or {}).get("data", {})
                inq_id = data.get("inquiry_id")
                if inq_id and inq_id not in state.selected_inquiry_ids:
                    state.selected_inquiry_ids.append(inq_id)


def _emit(event: AgentEvent, callback: EventCallback | None) -> AgentEvent:
    if callback:
        callback(event)
    logger.debug("agent_event %s", event.model_dump(exclude_none=True, mode="json"))
    return event


def create_agent() -> ShoppingAgent:
    return ShoppingAgent()
