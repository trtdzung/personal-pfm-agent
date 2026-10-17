import os

from greennode_agentbase.memory import MemoryClient
from greennode_agentbase.memory.models import (
    MemoryRecordInsertDirectlyRequest,
    MemoryRecordSearchRequest,
)
from langchain_core.tools import tool
from langgraph.config import get_config

MEMORY_ID = os.environ.get("MEMORY_ID")
if not MEMORY_ID:
    raise RuntimeError(
        "MEMORY_ID is not set. Refusing to start without a GreenNode AgentBase "
        "Memory resource configured -- remember_preference/recall_preference "
        "have nowhere to read/write long-term memory."
    )

USER_PREFERENCE_STRATEGY_ID = os.environ.get("USER_PREFERENCE_STRATEGY_ID")
if not USER_PREFERENCE_STRATEGY_ID:
    raise RuntimeError(
        "USER_PREFERENCE_STRATEGY_ID is not set. Refusing to start without a "
        "GreenNode AgentBase long-term memory strategy configured for the "
        "remember_preference/recall_preference tools (create one on the "
        "MEMORY_ID resource, type USER_PREFERENCE)."
    )

memory_client = MemoryClient()


def _user_preference_namespace(actor_id: str) -> str:
    return f"/strategies/{USER_PREFERENCE_STRATEGY_ID}/actors/{actor_id}"


def _memory_records_to_lines(response: object) -> list[str]:
    records = response if isinstance(response, list) else getattr(response, "list_data", None) or []
    return [getattr(record, "memory", None) or record.get("memory", "") for record in records]


@tool
def remember_preference(fact: str) -> str:
    """Store a USER PREFERENCE fact about the current customer -- i.e.
    something the customer chose/expressed about HOW they want to be served,
    answering "khách hàng thích gì?" (not "khách hàng có gì?", see
    remember_fact for that). In scope: kênh liên lạc ưa thích (channel),
    phong cách giao tiếp mong muốn (communication style), sản phẩm/loại thẻ
    họ tỏ ý thích, tuỳ chọn nhận thông báo (notification preference), loại
    nội dung/tư vấn họ muốn nhận (content preference), và ngân sách/hạn mức
    chi tiêu tự đặt ra (một mục tiêu cá nhân họ tuyên bố, không phải số liệu
    tài chính khách quan). KHÔNG dùng cho sự thật khách quan về khách hàng
    (sản phẩm đang sở hữu, tình hình tài chính thật, sự kiện đời sống, hành
    vi, lịch sử tương tác) -- đó là phạm vi của Semantic Memory, hiện chưa
    có tool tương ứng."""
    actor_id = get_config()["configurable"]["actor_id"]
    memory_client.insert_memory_records_directly(
        id=MEMORY_ID,
        namespace=_user_preference_namespace(actor_id),
        request=MemoryRecordInsertDirectlyRequest(memory_records=[fact]),
    )
    return f"Đã ghi nhớ: {fact}"


@tool
def recall_preference(query: str) -> str:
    """Search previously remembered USER PREFERENCE facts about the current
    customer -- "khách hàng thích gì?": kênh liên lạc ưa thích, phong cách
    giao tiếp, sản phẩm ưa thích, tuỳ chọn thông báo, loại nội dung muốn
    nhận, ngân sách/hạn mức tự đặt. Không phải nguồn cho sự thật khách quan
    (sản phẩm đang có, tình hình tài chính thật, sự kiện đời sống, hành vi,
    lịch sử tương tác) -- đó là phạm vi Semantic Memory, hiện chưa có tool
    tương ứng, đừng giả định tìm thấy loại thông tin đó ở đây."""
    actor_id = get_config()["configurable"]["actor_id"]
    response = memory_client.search_memory_records(
        id=MEMORY_ID,
        namespace=_user_preference_namespace(actor_id),
        request=MemoryRecordSearchRequest(query=query, limit=5, score_threshold=0.5),
    )
    lines = _memory_records_to_lines(response)
    if not lines:
        return "Không tìm thấy thông tin liên quan đã ghi nhớ trước đó."
    return "\n".join(f"- {line}" for line in lines)


# Semantic-memory tools -- inactive for now. The "Semantic memory" strategy
# already exists on MEMORY_ID (id starting ltms-2038ab25-...), but there's no
# SEMANTIC_STRATEGY_ID env var wired up yet, so these stay commented out
# until there's an actual use case for general (non-preference) recall.
# To enable: set SEMANTIC_STRATEGY_ID, uncomment below, and add
# remember_fact/recall_fact to the `tools=[...]` list in server.build_agent().
# See todo.md for the tracked follow-up.
#
# SEMANTIC_STRATEGY_ID = os.environ.get("SEMANTIC_STRATEGY_ID")
#
#
# def _semantic_namespace(actor_id: str) -> str:
#     return f"/strategies/{SEMANTIC_STRATEGY_ID}/actors/{actor_id}"
#
#
# @tool
# def remember_fact(fact: str) -> str:
#     """Store a SEMANTIC MEMORY fact about the current customer -- an
#     OBJECTIVE fact about what the customer HAS/IS, answering "khách hàng có
#     gì?" (not "khách hàng thích gì?", see remember_preference for that). In
#     scope: sản phẩm/dịch vụ đang sở hữu (thẻ, khoản vay, gói dịch vụ...),
#     tình hình tài chính khách quan (thu nhập, nợ, tài sản), sự kiện đời
#     sống quan trọng (chuyển việc, kết hôn, mua nhà...), hành vi thực tế
#     quan sát được, lịch sử tương tác trước đây với ngân hàng. KHÔNG dùng
#     cho sở thích/lựa chọn chủ quan của khách hàng (kênh liên lạc, phong
#     cách giao tiếp, ngân sách tự đặt...) -- đó là phạm vi remember_preference."""
#     actor_id = get_config()["configurable"]["actor_id"]
#     memory_client.insert_memory_records_directly(
#         id=MEMORY_ID,
#         namespace=_semantic_namespace(actor_id),
#         request=MemoryRecordInsertDirectlyRequest(memory_records=[fact]),
#     )
#     return f"Đã ghi nhớ: {fact}"
#
#
# @tool
# def recall_fact(query: str) -> str:
#     """Search previously remembered SEMANTIC MEMORY facts about the current
#     customer -- "khách hàng có gì?": sản phẩm/dịch vụ đang sở hữu, tình
#     hình tài chính khách quan, sự kiện đời sống, hành vi quan sát được,
#     lịch sử tương tác. Không phải nguồn cho sở thích/lựa chọn chủ quan
#     (kênh liên lạc, phong cách giao tiếp, ngân sách tự đặt...) -- đó là
#     phạm vi recall_preference."""
#     actor_id = get_config()["configurable"]["actor_id"]
#     response = memory_client.search_memory_records(
#         id=MEMORY_ID,
#         namespace=_semantic_namespace(actor_id),
#         request=MemoryRecordSearchRequest(query=query, limit=5, score_threshold=0.5),
#     )
#     lines = _memory_records_to_lines(response)
#     if not lines:
#         return "Không tìm thấy thông tin liên quan đã ghi nhớ trước đó."
#     return "\n".join(f"- {line}" for line in lines)
