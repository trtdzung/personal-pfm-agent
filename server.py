from dataclasses import replace
import hmac
import inspect
import logging
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from fastapi import FastAPI, Header, HTTPException
from greennode_agent_bridge import AgentBaseMemoryEvents
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel

from llm import LLM_BASE_URL, LLM_MODEL, chat_model, chat_model_name, default_model  # noqa: F401 -- re-exported: tests/notebooks read them off `server`
from langchain_core.exceptions import ModelPermissionDeniedError

from checkpointer_cache import invalidate as invalidate_checkpointer_cache
from checkpointer_cache import patch_get_events_with_cache
from checkpointer_delete_pagination import patch_delete_events_reads_page_one_every_time
from checkpointer_delta_snapshot import patch_preserve_delta_snapshots
from checkpointer_local_cache_race import patch_merge_local_cache_into_fetch
from jar_endpoint import router as jar_router
from insight_endpoint import router as insight_router
from proactive_endpoint import router as proactive_router
from goal_coach import router as goal_coach_router
from goal_price import router as goal_price_router
from goal_suggest import router as goal_suggest_router
from fraud import router as fraud_router
from middleware.audit import log_model_calls, log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext
from middleware.seed_user_preferences import SeedUserPreferences
from middleware.tool_limits import tool_call_limits
from text_utils import extract_final_text, extract_ui_block, strip_foreign_script
from ui_guard import is_goal_form, read_turn_facts, ui_matches_facts
from tools.customer_data_tools import get_categories, get_jar_summary, query_beneficiaries
from tools.goal_insight_tools import get_goal_insight
from tools.goal_price_tools import estimate_goal_price
from tools.goal_plan_tools import build_goal_plan_card, loan_quote, project_target, savings_projection, simulate_goal_plan
from tools.goal_tools import get_goal_market, get_goals, plan_monthly
from tools.security_tools import check_fraud_watchlist, check_official_channel, search_msb_promotions
from tools.investment_tools import calculate_deposit_interest, project_investment_growth
from tools.market_news_tools import read_market_article, search_market_news
from tools.msb_knowledge_tools import search_msb_knowledge
import tools.memory_tools as memory_tools
from guardrails import PROFANITY_REPLY, SENSITIVE_INPUT_NOTE, contains_profanity, mask_sensitive_input, sanitize_output
from tools.memory_tools import recall_preference, remember_preference

logger = logging.getLogger("personal-card-agent")

def _fresh_goals_read(user_id: str):
    """A `get_goals` read made by the server, for a goal form whose turn never read the goals (the model skipped the first step
    of skill goal-manage). None when pfm cannot be read."""
    try:
        return get_goals.invoke(
            {"name": "get_goals", "args": {}, "id": "server-goals-read", "type": "tool_call"},
            config={"configurable": {"actor_id": user_id}},
        )
    except Exception:  # noqa: BLE001 -- a failed read only means the form is dropped, like before
        logger.warning("fresh get_goals read for the form guard failed for user_id=%s", user_id, exc_info=True)
        return None


def _ui_matches_turn(ui: dict, messages: list, user_id: str) -> bool:
    """`ui_matches_facts` on what the turn read; a goal form or plan roadmap from a turn that did NOT read the goals is checked
    against a fresh read instead (same checks: the date is after pfm's today, the goal id exists), so a valid card is not lost to a
    skipped tool call. Everything else the turn read (market, the plan card built by the tool) still counts."""
    facts = read_turn_facts(messages)
    if ui_matches_facts(ui, facts):
        return True
    if is_goal_form(ui) and facts.goals is None:
        fresh = _fresh_goals_read(user_id)
        if fresh is not None and ui_matches_facts(ui, replace(facts, goals=read_turn_facts([fresh]).goals)):
            logger.info("goal card kept: checked against a fresh get_goals read, the model had skipped it")
            return True
    return False


# The checkpointer is GreenNode's AgentBase memory: every read/write is a network call (~1.3-1.8s a read, more a write), and
# LangGraph's default "async" mode saves after EVERY step (model call, tool call), ~7s of overhead per step, ~47% of a turn in the
# prod traces. "exit" saves once when the turn ends -- also when it fails, so `_resume_after_content_filter` still finds its state.
CHECKPOINT_DURABILITY = "exit"


def _with_plan_card(ui: dict | None, plan_cards: list[dict] | None) -> dict | None:
    """The plan roadmap is built by `build_goal_plan_card` and the SERVER attaches it: the model only writes the short text, it
    does not re-type the card (~800 output tokens, ~20s per answer). A `plan_roadmap` the model pasted anyway is replaced by the
    tool's own card; another kind of block (e.g. `clarify_options`) is left alone."""
    if plan_cards and (ui is None or ui.get("type") == "plan_roadmap"):
        return plan_cards[-1]
    return ui


FORM_DROPPED_NOTE = (
    "Lưu ý: mình chưa hiện được form hoặc lộ trình ở lượt này vì chưa kiểm tra lại dữ liệu mục tiêu của bạn. "
    "Bạn nhắn lại yêu cầu một lần nữa để mình đề xuất lại nhé."
)

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"

SERVER_API_KEY = os.environ.get("SERVER_API_KEY")
if not SERVER_API_KEY:
    raise RuntimeError(
        "SERVER_API_KEY is not set. Refusing to start without an API key "
        "configured -- this server would otherwise serve customer "
        "financial data with no authentication."
    )

USER_PREFERENCE_STRATEGY_ID = os.environ.get("USER_PREFERENCE_STRATEGY_ID")
if not USER_PREFERENCE_STRATEGY_ID:
    raise RuntimeError(
        "USER_PREFERENCE_STRATEGY_ID is not set. Refusing to start without "
        "a strategy ID for the memory service."
    )

MEMORY_ID = os.environ.get("MEMORY_ID")
if not MEMORY_ID:
    raise RuntimeError(
        "MEMORY_ID is not set. Refusing to start without "
        "a memory ID for the memory service."
    )
AI_PLATFORM_API_KEY = os.environ.get("AI_PLATFORM_API_KEY")
if not AI_PLATFORM_API_KEY:
    raise RuntimeError(
        "AI_PLATFORM_API_KEY is not set. Refusing to start without an API key "
        "for GreenNode's VNG Cloud AI Platform (Model-as-a-Service) endpoint."
    )

def _default_model() -> BaseChatModel:
    return chat_model(AI_PLATFORM_API_KEY)


def _default_tools() -> list:
    """The tools the chat agent gets (shared with /health, which reports what the running container really has)."""
    return [
        remember_preference,
        recall_preference,
        get_jar_summary,
        get_categories,
        get_goals,
        get_goal_market,
        get_goal_insight,
        estimate_goal_price,
        plan_monthly,
        loan_quote,
        savings_projection,
        project_target,
        simulate_goal_plan,
        build_goal_plan_card,
        query_beneficiaries,
        project_investment_growth,
        calculate_deposit_interest,
        search_market_news,
        read_market_article,
        search_msb_knowledge,
        check_official_channel,
        check_fraud_watchlist,
        search_msb_promotions,
    ]


def build_agent(
    model: object | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    tools: list[BaseTool] | None = None,
):
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    checkpointer = checkpointer or AgentBaseMemoryEvents(memory_id=MEMORY_ID)
    # Works around a real perf bug in AgentBaseMemoryEvents: LangGraph's
    # get_state()/invoke() call checkpointer.get_tuple() once per
    # accumulated checkpoint (the `messages` channel needs the whole chain
    # walked to reduce), and each call re-fetches ALL events over the
    # network from scratch instead of reusing what it just fetched --
    # ~111 network round-trips (~65s) on a well-used thread vs. ~1s with
    # this cache. No-op for InMemorySaver (tests/notebooks). Request
    # handlers below call invalidate_checkpointer_cache() before touching
    # a thread so each request's first read is still guaranteed fresh --
    # see checkpointer_cache.py and todo.md's performance investigation.
    patch_get_events_with_cache(checkpointer)
    # Works around a correctness bug in AgentBaseMemoryEvents that breaks
    # EVERY request on a thread once it is busy enough to have written a
    # DeltaChannel snapshot blob (~50 updates to the `messages` channel):
    # the bridge mangles that blob on read, and state reconstruction dies
    # with "Message as a sequence must be (role string, template)". This is
    # what todo.md 1.5 recorded as "corrupt old history" -- it is not old
    # history. Module-level patch on the bridge, idempotent, no-op for
    # InMemorySaver threads (they never produce such a blob) -- see
    # checkpointer_delta_snapshot.py.
    patch_preserve_delta_snapshots()
    # Works around a race in AgentBaseMemoryEvents.get_tuple(): it discards its own
    # correct read-your-writes local cache whenever a remote read merely LOOKS fresh
    # enough (same-or-newer checkpoint id), even if that read is missing a sibling event
    # of that very checkpoint -- silently forgetting the conversation until the next
    # write happens to repopulate the cache. Own soak test against real GreenNode
    # AgentBase Memory: wrong on ~1 in 6 real, back-to-back turns, unrelated to elapsed
    # time. No-op for InMemorySaver (tests/notebooks). Idempotent -- see
    # checkpointer_local_cache_race.py.
    patch_merge_local_cache_into_fetch()
    # Works around AgentBaseEventClient.delete_events() advancing to the next page
    # number after deleting a page's worth of events -- since deleting shifts later
    # events back a page, that skips whatever just shifted into the page already
    # cleared. Own test against real GreenNode AgentBase Memory: a ~300-event thread
    # left 2 messages behind after "successful" deletion. No-op below one page (100
    # events) -- see checkpointer_delete_pagination.py.
    patch_delete_events_reads_page_one_every_time()
    return create_deep_agent(
        model=model or _default_model(),
        tools=tools if tools is not None else _default_tools(),
        middleware=[
            log_tool_calls,
            log_model_calls,
            SeedCustomerContext(),
            SeedUserPreferences(),
            *tool_call_limits(),
        ],
        system_prompt=instructions,
        checkpointer=checkpointer,
        # StateBackend stays the default for everything (per-thread, isolates
        # customers' data -- see SeedCustomerContext) so only /skills/ is
        # routed to a real-disk FilesystemBackend, scoped to the skills/ dir
        # with virtual_mode=True (blocks path traversal outside SKILLS_DIR).
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True)},
        ),
        skills=["/skills/project/"],
    )


agent = build_agent()

app = FastAPI(
    title="personal-card-agent (self-hosted)",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Jar proposals for screens that need no chat: its own route and agent, same process (jar_endpoint.py).
app.include_router(jar_router)
app.include_router(insight_router)
app.include_router(proactive_router)
app.include_router(goal_coach_router)
app.include_router(goal_suggest_router)
app.include_router(goal_price_router)
app.include_router(fraud_router)


class ChatRequest(BaseModel):
    message: str
    user_id: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    ui: dict | None = None


class HistoryMessage(BaseModel):
    role: str
    content: str
    ui: dict | None = None


class ChatHistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage]


def _delete_thread(checkpointer: BaseCheckpointSaver, thread_id: str, actor_id: str) -> None:
    """`AgentBaseMemoryEvents.delete_thread(thread_id, actor_id="")` (the production checkpointer)
    scopes the delete to one customer (thread_id alone is not enough: different actor_ids can share a
    thread_id). `InMemorySaver.delete_thread(self, thread_id)` (the local/test default) takes only the
    thread id and raises `TypeError` on a second positional argument. Inspect the real signature instead
    of assuming either shape, so this keeps working whichever checkpointer `agent` was built with."""
    if len(inspect.signature(checkpointer.delete_thread).parameters) >= 2:
        checkpointer.delete_thread(thread_id, actor_id)
    else:
        checkpointer.delete_thread(thread_id)


def _default_thread_id(user_id: str) -> str:
    """Frontend doesn't manage/pass thread_id yet -- every user_id gets one
    default (and, for now, only) conversation thread when thread_id is
    omitted, so /chat, GET /chat/history, and DELETE /chat/history all agree
    on the same thread for a given user without the caller tracking it."""
    return user_id


@app.get("/health")
def health() -> dict:
    """Liveness plus what this container really runs (model, skills found on disk, tools registered): compare with the repo
    when a deployment behaves differently from a local run. Nothing secret."""
    skills = sorted(p.parent.name for p in (SKILLS_DIR / "project").glob("*/SKILL.md"))
    return {"status": "ok", "model": chat_model_name(), "skills": skills, "tools": [t.name for t in _default_tools()]}


def _resume_after_content_filter(thread_id: str, actor_id: str, first_error: Exception) -> dict:
    """One retry when the model host's own content-safety filter rejects the model's OUTPUT (not our
    input) -- seen in production as GreenNode/VNG Cloud MaaS 403 "ModelArts.81011 Output text May contain
    sensitive information". Transient and non-deterministic (also fired during real-model test runs of
    unrelated jar-rebalance answers), not a bug here.

    Verified empirically (not assumed) that this never duplicates the customer's turn: by the time this
    exception can be raised, the customer's message is already checkpointed (LangGraph writes it in the
    entry superstep, before the model node runs) and the model node is the only pending task
    (`state.next == ("model",)`) -- so resuming with `agent.invoke(None, config=...)` re-runs exactly that
    step instead of appending the message again. Gives up after one retry (raises 503, which the frontend
    can retry) rather than making the customer wait through several more ~10-40s model calls.
    """
    logger.warning("agent.invoke rejected by the model provider's content filter for thread_id=%s, retrying: %s", thread_id, first_error)
    config = {"configurable": {"thread_id": thread_id, "actor_id": actor_id}}
    state = agent.get_state(config=config)
    if not state.next:
        # No safe resume point (should not normally happen for this exception) -- resuming with no
        # pending task would be a meaningless no-op call, not a real retry.
        raise HTTPException(status_code=503, detail="Model provider unavailable, try again shortly") from first_error
    try:
        return agent.invoke(None, config=config, durability=CHECKPOINT_DURABILITY)
    except ModelPermissionDeniedError as exc:
        logger.warning("agent.invoke rejected by the model provider's content filter again for thread_id=%s, giving up", thread_id)
        raise HTTPException(status_code=503, detail="Model provider unavailable, try again shortly") from exc


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    x_api_key: str | None = Header(default=None),
) -> ChatResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = request.thread_id or _default_thread_id(request.user_id)
    if contains_profanity(request.message):
        logger.warning("guardrail=profanity_input user_id=%s", request.user_id)
        return ChatResponse(answer=PROFANITY_REPLY, thread_id=thread_id, ui=None)
    message, masked_input = mask_sensitive_input(request.message)
    if masked_input:
        logger.warning("guardrail=sensitive_input user_id=%s", request.user_id)
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, request.user_id)
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": thread_id, "actor_id": request.user_id}},
            durability=CHECKPOINT_DURABILITY,
        )
    except ModelPermissionDeniedError as exc:
        result = _resume_after_content_filter(thread_id, request.user_id, exc)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("agent.invoke failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Agent failed to process the request") from exc

    answer = extract_final_text(result["messages"][-1].content)
    answer, ui = extract_ui_block(answer)
    ui = _with_plan_card(ui, read_turn_facts(result["messages"]).plan_cards)
    if ui is not None and not _ui_matches_turn(ui, result["messages"], request.user_id):
        # e.g. an edit_jar for a jar the model never read this turn (backend_docs/pfm-read-api.md C2.2): the
        # customer gets the answer text only, exactly like a shape-invalid ui.
        logger.warning("Dropping ui block: ids not among what get_jar_summary/get_categories returned this turn: %r", ui)
        if is_goal_form(ui):
            # the text still says "bạn xem lại và xác nhận": without the form the customer would wait for a card that never comes
            answer = f"{answer}\n\n{FORM_DROPPED_NOTE}"
        ui = None
    answer = strip_foreign_script(answer)  # after the ui block is split off: its strings are left alone
    verdict = sanitize_output(answer, request.user_id)
    if verdict.changed:
        logger.warning("guardrail=%s user_id=%s", ",".join(verdict.reasons), request.user_id)
        answer = verdict.text
        if "profanity" in verdict.reasons or "system_prompt_leak" in verdict.reasons:
            ui = None
    if masked_input:
        answer = f"{answer}\n\n{SENSITIVE_INPUT_NOTE}"
    return ChatResponse(answer=answer, thread_id=thread_id, ui=ui)


@app.get("/chat/history", response_model=ChatHistoryResponse)
def chat_history(
    user_id: str,
    thread_id: str | None = None,
    x_api_key: str | None = Header(default=None),
) -> ChatHistoryResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = thread_id or _default_thread_id(user_id)
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, user_id)
    try:
        state = agent.get_state(config={"configurable": {"thread_id": thread_id, "actor_id": user_id}})
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("agent.get_state failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to load conversation history") from exc

    history: list[HistoryMessage] = []
    turn_cards: list[dict] = []  # `build_goal_plan_card` artifacts of the turn being walked
    for message in state.values.get("messages", []):
        if isinstance(message, HumanMessage):
            turn_cards = []
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            # not shown, but a plan card built by the tool belongs to this turn's answer (see `_with_plan_card`)
            if getattr(message, "name", None) == "build_goal_plan_card" and isinstance(getattr(message, "artifact", None), dict):
                turn_cards.append(message.artifact)
            continue  # skip tool/system messages -- not meant for a chat UI transcript

        text = extract_final_text(message.content)
        text, ui = extract_ui_block(text)
        if role == "assistant" and not getattr(message, "tool_calls", None):
            ui = _with_plan_card(ui, turn_cards)
        if role == "assistant":
            text = strip_foreign_script(text)  # never rewrite what the user typed
        if not text and ui is None:
            continue  # e.g. an AIMessage whose only content was a tool call -- nothing to show at all

        history.append(HistoryMessage(role=role, content=text, ui=ui))

    return ChatHistoryResponse(thread_id=thread_id, messages=history)


class DeleteHistoryResponse(BaseModel):
    thread_id: str
    status: str


@app.delete("/chat/history", response_model=DeleteHistoryResponse)
def delete_chat_history(
    user_id: str,
    thread_id: str | None = None,
    x_api_key: str | None = Header(default=None),
) -> DeleteHistoryResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = thread_id or _default_thread_id(user_id)
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, user_id)
    try:
        _delete_thread(agent.checkpointer, thread_id, user_id)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("checkpointer.delete_thread failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete conversation history") from exc
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, user_id)
    return DeleteHistoryResponse(thread_id=thread_id, status="deleted")


def _user_preference_namespace(user_id: str) -> str:
    return f"/strategies/{USER_PREFERENCE_STRATEGY_ID}/actors/{user_id}"


def _list_user_preference_records(user_id: str) -> list[object]:
    response = memory_tools.memory_client.list_memory_records(
        id=MEMORY_ID,
        namespace=_user_preference_namespace(user_id),
    )
    return response if isinstance(response, list) else getattr(response, "list_data", None) or []


def _record_field(record: object, name: str) -> object:
    # MemoryClient.list_memory_records returns plain dicts; tolerate attribute-style objects too.
    return record.get(name) if isinstance(record, dict) else getattr(record, name, None)


class MemoryPreferenceRecord(BaseModel):
    id: str
    fact: str
    created_at: str | None = None


class MemoryPreferencesResponse(BaseModel):
    user_id: str
    records: list[MemoryPreferenceRecord]


@app.get("/memory/preferences", response_model=MemoryPreferencesResponse)
def memory_preferences(
    user_id: str,
    x_api_key: str | None = Header(default=None),
) -> MemoryPreferencesResponse:
    """What `remember_preference` has saved for this customer (GreenNode Long-Term Memory, "User
    Preference" strategy) -- so pfm can show the customer what the agent remembered about them. There
    was previously no way to read this back except via the model's own `recall_preference` tool call."""
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    try:
        raw_records = _list_user_preference_records(user_id)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("memory_client.list_memory_records failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to load remembered preferences") from exc

    records = [
        MemoryPreferenceRecord(
            id=_record_field(record, "id"),
            fact=_record_field(record, "memory"),
            created_at=_record_field(record, "created_at"),
        )
        for record in raw_records
        if _record_field(record, "id") and _record_field(record, "memory")
    ]
    return MemoryPreferencesResponse(user_id=user_id, records=records)


class DeleteMemoryPreferenceResponse(BaseModel):
    user_id: str
    record_id: str
    status: str


@app.delete("/memory/preferences/{record_id}", response_model=DeleteMemoryPreferenceResponse)
def delete_memory_preference(
    record_id: str,
    user_id: str,
    x_api_key: str | None = Header(default=None),
) -> DeleteMemoryPreferenceResponse:
    """Let the customer delete one remembered preference fact. GreenNode's own delete API takes no
    actor/namespace scoping param (just a global record id) -- list this user's OWN records first and
    refuse with 404 if record_id isn't among them, so one customer can never delete another's fact."""
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    try:
        raw_records = _list_user_preference_records(user_id)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("memory_client.list_memory_records failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to load remembered preferences") from exc

    if record_id not in {_record_field(record, "id") for record in raw_records}:
        raise HTTPException(status_code=404, detail="Memory record not found for this user")

    try:
        memory_tools.memory_client.delete_memory_record(id=MEMORY_ID, memoryRecordId=record_id)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("memory_client.delete_memory_record failed for record_id=%s", record_id)
        raise HTTPException(status_code=500, detail="Failed to delete remembered preference") from exc

    return DeleteMemoryPreferenceResponse(user_id=user_id, record_id=record_id, status="deleted")
