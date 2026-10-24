"""Single registry for the tools exposed to the LangGraph agent."""

from src.core.tools.catalog import search_products
from src.core.tools.discovery import (
    product_quick_look,
    resolve_location,
    suggest_market_hub,
    web_search,
)
from src.core.tools.preferences import load_user_preferences, save_user_preference
from src.core.tools.shops import (
    cancel_inquiry,
    check_open_now,
    compare_shops,
    draft_inquiry,
    find_alternatives,
    follow_up_inquiry,
    get_inquiry_status,
    get_offers,
    get_shop_location_hint,
    inquire_shop,
    list_inquiries,
    send_inquiry,
    send_inquiry_batch,
)

TOOLS = [
    search_products,
    get_offers,
    compare_shops,
    check_open_now,
    draft_inquiry,
    send_inquiry,
    send_inquiry_batch,
    get_inquiry_status,
    list_inquiries,
    cancel_inquiry,
    follow_up_inquiry,
    inquire_shop,
    find_alternatives,
    get_shop_location_hint,
    suggest_market_hub,
    product_quick_look,
    web_search,
    resolve_location,
    save_user_preference,
    load_user_preferences,
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
