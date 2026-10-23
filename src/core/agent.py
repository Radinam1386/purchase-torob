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
        workflow.add_node("catalog_summary", self._catalog_summary)
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
        workflow.add_conditional_edges("tools", self._route_after_tools,
                                       {"catalog_summary": "catalog_summary", "agent": "agent"})
        workflow.add_edge("catalog_summary", END)
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
        conversation = dict(conversation)
        parsed_state = ConversationState.model_validate(conversation)
        _apply_constraints(parsed_state, latest)
        conversation["budget"] = parsed_state.budget
        preferences = dict(conversation.get("preferences") or {})
        advisor = dict(preferences.get("_advisor", {}))
        selected = bool(conversation.get("selectedProductId") or conversation.get("selected_product_id"))
        previous_category = advisor.get("category")
        latest_text = normalize_fa(latest)
        detected = _product_category(latest)
        if detected and detected != advisor.get("category"):
            advisor = {"category": detected}
            conversation["selectedProductId"] = None
        category = detected or advisor.get("category") or next(
            (_product_category(turn) for turn in reversed(user_turns) if _product_category(turn)), None)
        if not category:
            return {}
        use_match = re.search(
            r"(?:برای\s+)?برنامه\s*نویسی|موسیقی|موزیک|بازی|گیم|دانشگاه|کار|عکاسی|فیلم|ورزش|دویدن|روزمره|پیاده(?:\s+روی)?|سفر|مکالمه|تماس|طراحی|مصرف خانگی",
            latest_text)
        if selected and re.search(
            r"(?:تماس|مکالمه)\s*(?:بگیر|بگیرید|کن|برقرار)|تماس\s*(?:با\s*)?فروشنده|برای\s*(?:تماس|مکالمه)\s*آماده|استعلام|(?:آماده|شروع|نتیجه|پیگیری).*تماس",
            latest_text):
            use_match = None
        use = use_match.group(0) if use_match else advisor.get("use")
        if not use and advisor.get("pending_question") == "use" and not detected and not _explicit_search_now(latest):
            answer = re.sub(r"\d[\d.,٬]*\s*(?:میلیارد|میلیون|هزار|م)?", " ", latest_text)
            answer = re.sub(r"\b(?:من|برای|واسه|تا|حدود|بودجه|تومان|دارم|هستم|است|میخوام|می|خوام)\b", " ", answer)
            if len(re.findall(r"[^\W\d_]", answer)) > 2 and not re.search(r"نمی\s*دانم|نمی\s*دونم|نمیدونم", answer):
                use = latest.strip()[:200]
        # A budget is known only when a real numeric limit was successfully parsed.
        budget_known = conversation.get("budget") is not None
        bypass = _explicit_search_now(latest) or _has_specific_model(latest)
        confirmed = advisor.get("status") == "ready_to_search" and bool(re.fullmatch(
            r"(?:بله|اره|آره|اوکی|باشه|تایید|تأیید|شروع کن)[.!؟\s]*", latest_text))
        requirements = {**advisor, "category": category, "use": use,
                        "budget_known": budget_known, "use_known": bool(use), "status": "collecting_requirements"}
        important = dict(advisor.get("important_preferences") or {})
        hard = dict(advisor.get("hard_constraints") or {})
        extracted, conflicts = _preference_details(category, latest_text)
        bounds = _budget_bounds(latest_text)
        if bounds.get("min", 0) > bounds.get("max", math.inf):
            conflicts.append("budget")
        budget_answer = bool(bounds or re.fullmatch(
            r"\d[\d.,٬٫]*\s*(?:میلیارد|میلیون|هزار|م)?\s*(?:تومان)?[.!؟\s]*", latest_text))
        unresolved = [field for field in advisor.get("contradictions", [])
                      if field not in extracted and not (field == "budget" and budget_answer)]
        requirements["contradictions"] = list(dict.fromkeys([*unresolved, *conflicts]))
        for key, value in extracted.items():
            if key not in conflicts:
                important[key] = value
                hard.pop(key, None)
                if re.search(r"(?:فقط|حتما|الزامی|ضروری)\s+" + re.escape(normalize_fa(value)), latest_text):
                    hard[key] = value
        if "budget" not in requirements["contradictions"]:
            if budget_known:
                hard["budgetMax"] = conversation["budget"]
            else:
                hard.pop("budgetMax", None)
            if "min" in bounds:
                hard["budgetMin"] = bounds["min"]
            elif bounds:
                hard.pop("budgetMin", None)
        requirements["important_preferences"] = important
        requirements["hard_constraints"] = hard
        if selected:
            previous_hard = dict(advisor.get("hard_constraints") or {})
            previous_budget = (preferences.get("searchProfile") or {}).get("budget", conversation.get("budget"))
            if previous_budget is not None:
                previous_hard.setdefault("budgetMax", previous_budget)
            changed = bool(
                category != previous_category or requirements["contradictions"]
                or (use_match and use != advisor.get("use"))
                or any(value != (advisor.get("important_preferences") or {}).get(key) for key, value in extracted.items())
                or ((extracted or budget_answer) and hard != previous_hard)
                or (_has_specific_model(latest) and latest != advisor.get("specific_model")))
            if not changed:
                advisor["category"] = category
                advisor.setdefault("status", "selected_product")
                preferences["_advisor"] = advisor
                conversation["preferences"] = preferences
                _sync_search_profile(conversation)
                return {"conversation": conversation}
            conversation.update(selectedProductId=None, selectedShopIds=[], selectedOfferIds=[])
            for field, value in (("selected_product_id", None), ("selected_shop_ids", []), ("selected_offer_ids", [])):
                if field in conversation:
                    conversation[field] = value
        requirements["requirements_text"] = (str(advisor.get("requirements_text", "")) + " " + latest)[-4000:]
        if _has_specific_model(latest):
            requirements["specific_model"] = latest
        preferences["_advisor"] = requirements
        conversation["preferences"] = preferences
        if requirements["contradictions"]:
            requirements["status"] = "clarifying_requirements"
            question = ("محدودیت‌های بودجه با هم سازگار نیستند؛ حداقل و سقف نهایی بودجه‌ات چقدره؟"
                        if "budget" in requirements["contradictions"] else
                        "دو نوع متفاوت گفتی؛ مدل روگوشی می‌خوای یا ایرباد؟" if "type" in requirements["contradictions"] else
                        "دو ترجیح ناسازگار گفتی؛ اتصال هدفون باسیم باشه یا فقط بی‌سیم؟")
            _sync_search_profile(conversation)
            return {"conversation": conversation, "clarification_question": question}
        if bypass or confirmed:
            requirements["status"] = "searching"
            requirements["assumptions"] = [label for known, label in (
                (budget_known, "بودجه مشخص نیست؛ محدودیت قیمت اعمال نمی‌شود"),
                (bool(use), "کاربرد مشخص نیست؛ جست‌وجوی عمومی انجام می‌شود")) if not known]
            if not important:
                requirements["assumptions"].append("ترجیحات تخصصی مشخص نیست؛ نوع و ویژگی اضافه فرض نمی‌شود")
            _sync_search_profile(conversation)
            return {"conversation": conversation}
        if not use:
            requirements["pending_question"] = "use"
            question = f"{category} رو بیشتر برای چه کاری می‌خوای؟"
            if not budget_known:
                question += " حدود بودجه‌ات چقدره؟"
            elif not important:
                labels = _CATEGORY_PREFERENCES.get(category, {})
                if labels:
                    question += " ترجیح یا محدودیت مهمی درباره " + "، ".join(list(labels.values())[:2]) + " داری؟"
        elif not budget_known:
            requirements["pending_question"] = "budget"
            question = f"برای {category} با کاربرد {use}، حدود بودجه‌ات چقدره؟"
            missing = [(key, label) for key, label in _CATEGORY_PREFERENCES.get(category, {}).items() if key not in important]
            if missing:
                question += " ترجیح یا محدودیت مهمی درباره " + "، ".join(label for _, label in missing[:2]) + " داری؟"
        else:
            requirements.pop("pending_question", None)
            requirements["status"] = "ready_to_search"
            budget = conversation.get("budget")
            budget_label = f"{budget:,} تومان" if budget is not None else "بودجه‌ای که گفتی"
            question = f"خلاصه ترجیحات: {category} برای {use}، سقف {budget_label}. جست‌وجو کنم؟ می‌تونی همین‌جا ترجیحات رو اصلاح کنی."
            if important:
                question = question.replace(". جست‌وجو", "؛ " + "، ".join(important.values()) + ". جست‌وجو", 1)
            _sync_search_profile(conversation)
            return {"conversation": conversation, "clarification_question": question}
        requirements["status"] = "clarifying_requirements"
        _sync_search_profile(conversation)
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
        advisor = (conversation.get("preferences") or {}).get("_advisor", {})
        model = (self._model.bind_tools([tool for tool in TOOLS if tool.name == "search_products"],
                                       tool_choice={"type": "function", "function": {"name": "search_products"}})
                 if advisor.get("status") == "searching" else self._model_with_tools)
        response = await model.ainvoke(
            [SystemMessage(content=self._make_prompt(state)), *state.get("messages", [])]
        )
        advisor = (conversation.get("preferences") or {}).get("_advisor", {})
        for call in response.tool_calls:
            if call.get("name") == "search_products" and advisor.get("category") and not advisor.get("specific_model"):
                # The catalog's words describe products, not an assumed use-case or subtype.
                # A broad consultation has only established category, use and budget.
                known_text = normalize_fa(str(advisor.get("requirements_text", ""))).replace(" ", "")
                query_terms = normalize_fa(str(call["args"].get("query", ""))).split()
                if any(term not in known_text for term in query_terms):
                    call["args"]["query"] = advisor["category"]
            if call.get("name") == "search_products":
                call["args"]["max_price"] = conversation.get("budget")
                minimum = (advisor.get("hard_constraints") or {}).get("budgetMin")
                if minimum is not None:
                    if not isinstance(call["args"].get("filters"), dict):
                        call["args"]["filters"] = {}
                if isinstance(call["args"].get("filters"), dict):
                    call["args"]["filters"]["min_price"] = minimum
                    call["args"]["filters"]["max_price"] = conversation.get("budget")
        rounds = state.get("tool_rounds", 0) + int(bool(response.tool_calls))
        if rounds > settings.max_tool_rounds:
            raise RuntimeError("حداکثر دور ابزار ایجنت تمام شد.")
        return {
            "messages": [response],
            "conversation": state["conversation"],
            "tool_rounds": rounds,
        }

    @staticmethod
    def _route_after_tools(state: AgentState) -> Literal["catalog_summary", "agent"]:
        advisor = (state.get("conversation", {}).get("preferences") or {}).get("_advisor", {})
        message = state["messages"][-1]
        if advisor.get("status") == "searching" and isinstance(message, ToolMessage) and message.name == "search_products":
            payload = parse_tool_payload(message.content) or {}
            if message.status != "error" and "error" not in payload and isinstance(payload.get("data"), list):
                return "catalog_summary"
        return "agent"

    @staticmethod
    def _catalog_summary(state: AgentState) -> dict[str, Any]:
        payload = parse_tool_payload(state["messages"][-1].content) or {}
        text = ("جست‌وجوی واقعی انجام شد؛ فهرست کامل محصولات و فیلترها در صفحه نتایج باز می‌شود. "
                "قیمت‌های دیتاست و موجودی فعلی تأیید نشده‌اند." if payload.get("data") else
                "با این معیارها محصولی در دیتاست پیدا نشد؛ می‌تونی جست‌وجو و فیلترها رو در صفحه نتایج اصلاح کنی.")
        return {"messages": [AIMessage(content=json.dumps({"text": text}, ensure_ascii=False))]}

    def _make_prompt(self, state: AgentState) -> str:
        user_id = state.get("user_id", "local")
        conversation = state.get("conversation", {})
        preferences = self._load_preferences(user_id)
        conversation["preferences"] = {
            **preferences,
            **conversation.get("preferences", {}),
        }
        state["conversation"] = conversation
        serialized_state = json.dumps(conversation, ensure_ascii=False)
        return (
            f"{self._system_prompt}\n\n"
            "فقط ترجیحات صریح کاربر را به جست‌وجو اضافه کن. اگر نوع روگوشی/ایرباد یا برند را نگفته، آن را حدس نزن. "
            "محدودیت بودجه و کاربرد در وضعیت گفتگو ذخیره شده‌اند؛ سؤال تکراری نپرس.\n"
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
        if final_state.get("clarification_question"):
            response.clarification_question = final_state["clarification_question"]
        advisor = (final_state.get("conversation", {}).get("preferences") or {}).get("_advisor", {})
        if response.search_query is not None:
            assumptions = advisor.get("assumptions") or []
            if assumptions:
                response.text = "فرض‌های جست‌وجو: " + "؛ ".join(assumptions) + "\n\n" + response.text
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
    "هدست": "هدفون",
    "هندزفری": "هدفون",
    "ایرباد": "هدفون",
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
_CATEGORY_PREFERENCES = {
    "هدفون": {"type": "نوع روگوشی یا ایرباد", "connection": "اتصال باسیم یا بی‌سیم",
                "noiseCancellation": "حذف نویز", "comfort": "راحتی"},
    "لپ‌تاپ": {"workload": "نوع و سنگینی کار", "portability": "حمل و وزن", "battery": "باتری"},
    "گوشی": {"camera": "دوربین", "battery": "باتری", "storage": "حافظه"},
    "کفش": {"size": "سایز", "comfort": "راحتی پیاده‌روی"},
    "کتونی": {"size": "سایز", "comfort": "راحتی پیاده‌روی"},
}


def _preference_details(category: str, text: str) -> tuple[dict[str, str], list[str]]:
    """Keep explicit, category-relevant facts; optional unknowns never block a search."""
    # ponytail: phrase rules cover common explicit preferences; extend these patterns for new categories.
    patterns = {
        "type": [(r"رو\s*گوشی|روی\s*گوش", "روگوشی"), (r"ایرباد|داخل\s*گوش|تو\s*گوشی", "ایرباد")],
        "connection": [(r"(?<!\w)(?:با\s*سیم|سیمی)(?!\w)", "باسیم"),
                       (r"بی\s*سیم|بلوتوث|wireless", "بی‌سیم")],
        "noiseCancellation": [(r"حذف\s*نویز|نویز\s*کنسل|\banc\b", "حذف نویز")],
        "comfort": [(r"راحت\w*|نرم\w*|قوس\s*پا", "راحتی")],
        "portability": [(r"سبک|قابل\s*حمل|وزن\s*کم", "سبک و قابل حمل")],
        "battery": [(r"باتری|شارژدهی", "باتری و شارژدهی")],
        "camera": [(r"دوربین|عکاسی|فیلم\s*برداری", "دوربین و عکاسی")],
        "storage": [(r"حافظه\s*(?:داخلی)?\s*\d+\s*(?:گیگ|ترابایت)?", "")],
        "size": [(r"(?:سایز|اندازه)\s*\d+(?:\.\d+)?", "")],
        "workload": [(r"برنامه\s*نویسی|رندر\w*|بازی|گیم\w*|طراحی|کار\s*سنگین|کار\s*سبک", "")],
    }
    preferences = {}
    contradictions = []
    for key in _CATEGORY_PREFERENCES.get(category, {}):
        found = []
        for pattern, label in patterns[key]:
            for match in re.finditer(pattern, text):
                # A rejected feature is a known restriction, not an affirmative preference.
                negative = bool(re.match(r"\s*(?:نمی\s*خوام|نمی\s*خواهم|نمیخوام|نه|لازم نیست|مهم نیست)", text[match.end():]))
                value = (label or match.group(0)) + (" نمی‌خواهم" if negative else "")
                found.append(value)
        distinct = list(dict.fromkeys(found))
        if len(distinct) > 1 and key in {"connection", "type"} and not any("نمی‌خواهم" in value for value in distinct):
            contradictions.append(key)
        elif distinct:
            preferences[key] = "، ".join(distinct)
    return preferences, contradictions


def _sync_search_profile(conversation: dict[str, Any]) -> None:
    preferences = conversation.get("preferences") or {}
    advisor = preferences.get("_advisor") or {}
    if not advisor.get("category"):
        return
    important = advisor.get("important_preferences") or {}
    unknown = [label for key, label in _CATEGORY_PREFERENCES.get(advisor["category"], {}).items() if key not in important]
    if not advisor.get("use"):
        unknown.insert(0, "کاربرد")
    if conversation.get("budget") is None:
        unknown.insert(0, "بودجه")
    preferences["searchProfile"] = {
        "product": advisor.get("specific_model") or advisor["category"], "category": advisor["category"],
        "use": advisor.get("use"), "budget": conversation.get("budget"),
        "importantPreferences": important, "hardConstraints": advisor.get("hard_constraints") or {},
        "unknownInformation": unknown, "stage": advisor.get("status", "collecting_requirements"),
        "contradictions": advisor.get("contradictions") or [],
    }


def _budget_bounds(text: str) -> dict[str, int]:
    text = normalize_fa(text).replace("٫", ".")
    bounds = {}
    for match in re.finditer(r"(حداقل|حداکثر|تا سقف|سقف|تا|بودجه(?:\s*(?:من|ام|م))?)\s*(?:حدود\s*)?(\d[\d.,٬]*)\s*(میلیارد|میلیون|هزار|م)?", text):
        try:
            value = float(match[2].replace(",", "").replace("٬", "")) * {"میلیارد": 10**9, "میلیون": 10**6, "هزار": 1000, "م": 10**6}.get(match[3], 1)
            if math.isfinite(value) and 0 <= value <= 10**15:
                bounds["min" if match[1] == "حداقل" else "max"] = int(value)
        except ValueError:
            pass
    return bounds


_BUYING_CONTEXT = re.compile(
    r"(?:بودجه|حداکثر|تا سقف|تا\s*[\d۰-۹٠-٩]|میلیون|میلیارد|هزار|"
    r"برای\s+(?:بازی|گیم|دانشگاه|کار|عکاسی|فیلم|ورزش|دویدن|روزمره|سفر|طراحی)|"
    r"بازی|گیم|دانشگاه|عکاسی|دویدن|روزمره|پیاده|سفر|برنامه.?نویسی|طراحی|"
    r"برای خانه|مصرف خانگی|صنعتی|چاپ روی پارچه|۳\s*متری|سه متری|مدل\s*[a-zA-Z0-9۰-۹٠-٩-]+)",
    re.IGNORECASE,
)


def _product_category(text: str) -> str | None:
    normalized = normalize_fa(text)
    for term, label in sorted(_BROAD_PRODUCT_CATEGORIES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(r"(?<!\w)" + re.escape(normalize_fa(term)) + r"(?!\w)", normalized):
            return label
    return None


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
    return bool(re.search(r"همین الان|الان نشون بده|محصولات رو نشون|خودت بهترین|جستجو کن|جست وجو کن|پیدا کن|خودت انتخاب کن|فرقی نداره|مهم نیست|بدون بودجه|هر قیمتی", normalized))


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
    bounds = _budget_bounds(normalized_text)
    budget_match = re.search(
        r"(?:بودجه(?:\s*(?:من|ام|م))?|حداکثر|تا سقف|تا)\s*(?:حدود\s*)?"
        r"(?<![-\d])([\d][\d.,٬]*)\s*(میلیارد|میلیون|هزار|م)?",
        normalized_text,
    )
    if budget_match is None:
        budget_match = re.search(r"(?<![-\d])([\d][\d.,٬]*)\s*(میلیارد|میلیون|هزار)(?:\s*تومان)?", normalized_text)
    if budget_match is None and (state.preferences.get("_advisor") or {}).get("category"):
        budget_match = re.fullmatch(r"\s*(\d[\d.,٬]*)\s*(میلیارد|میلیون|هزار|م)?\s*(?:تومان)?[.!؟\s]*", normalized_text)
    if re.search(r"بدون بودجه|هر قیمتی|بودجه (?:مهم نیست|ندارم)", normalized_text):
        state.budget = None
        advisor = state.preferences.get("_advisor")
        if isinstance(advisor, dict):
            advisor["budget_known"] = False
    if budget_match and bounds.get("min", 0) <= bounds.get("max", math.inf) and ("min" not in bounds or "max" in bounds):
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
            state.budget = bounds.get("max", int(calculated_budget))
        except (OverflowError, ValueError):
            logger.info("Ignoring unparseable budget value: %r", amount_text)
    if "max" in bounds and bounds.get("min", 0) <= bounds["max"]:
        state.budget = bounds["max"]

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
    if "selectedProductId" in latest or "selected_product_id" in latest:
        selected_product = latest.get("selectedProductId", latest.get("selected_product_id"))
        if selected_product != state.selected_product_id:
            state.selected_shop_ids = []
            state.selected_offer_ids = []
        state.selected_product_id = selected_product
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
            if message.name == "search_products":
                payload = parse_tool_payload(message.content) or {}
                advisor = state.preferences.setdefault("_advisor", {})
                if not isinstance(advisor, dict):
                    advisor = state.preferences["_advisor"] = {}
                successful = message.status != "error" and "error" not in payload and isinstance(payload.get("data"), list)
                advisor["status"] = "showing_results" if successful else "ready_to_search"
            elif message.name == "resolve_location":
                resolved = (parse_tool_payload(message.content) or {}).get("data")
                if resolved:
                    state.location = ConversationLocation.model_validate(resolved)
            elif message.name == "draft_inquiry":
                data = (parse_tool_payload(message.content) or {}).get("data", {})
                inq_id = data.get("inquiry_id")
                if inq_id and inq_id not in state.selected_inquiry_ids:
                    state.selected_inquiry_ids.append(inq_id)
    _sync_search_profile({"budget": state.budget, "preferences": state.preferences})


def _emit(event: AgentEvent, callback: EventCallback | None) -> AgentEvent:
    if callback:
        callback(event)
    logger.debug("agent_event %s", event.model_dump(exclude_none=True, mode="json"))
    return event


def create_agent() -> ShoppingAgent:
    return ShoppingAgent()
