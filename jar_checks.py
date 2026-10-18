"""The deterministic side of POST /jar-rebalance (jar_endpoint.py).

The LLM proposes; this module says what is true. It computes the numbers the model must not compute (the
shortfall, the pool) and checks a proposal against the `jar-summary` the server read for this very request.

Two grades of error, on purpose:
- `hard`: breaks a rule pfm enforces (a source gives more than it has, a made-up id, a wrong shortfall, a total
  that does not add up). The proposal must not be returned.
- `soft`: breaks only the preferred order (backend_docs/pfm-read-api.md B4: "gợi ý, không phải quy tắc cứng").
  Worth one retry with the correct plan, but a proposal that still has only this is acceptable.
"""

from dataclasses import dataclass, field

from text_utils import is_valid_ui
from ui_guard import TurnFacts, ui_matches_facts

POOL = "pool"


@dataclass
class Verdict:
    hard: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)


def _vnd(amount: float) -> str:
    return f"{round(amount):,}".replace(",", ".") + "đ"


def _jars(summary: dict) -> dict[str, dict]:
    return {j["id"]: j for j in summary.get("jars") or [] if isinstance(j, dict) and "id" in j}


def pool_available(summary: dict) -> int:
    """The "Chưa phân bổ" money that can be given away: never negative, never unknown-as-something."""
    unallocated = summary.get("unallocated")
    return max(0, unallocated) if isinstance(unallocated, (int, float)) else 0


def cover_shortfall(summary: dict, target_id: str, spend_amount: int | None) -> int | None:
    """VND the target jar is short. `None` when it cannot be covered at all (unknown jar, or no `budgetLimit`).

    (a) a planned spend: `spend_amount − spendable` (the formula of backend_docs B4);
    (b) no planned spend: a jar that "needs covering" (`remaining` < 0) is short by `−remaining`.
    0 means nothing to cover.
    """
    target = _jars(summary).get(target_id)
    if target is None or target.get("budgetLimit") is None:
        return None
    if spend_amount is not None:
        return max(0, spend_amount - (target.get("spendable") or 0))
    remaining = target.get("remaining")
    return -remaining if isinstance(remaining, (int, float)) and remaining < 0 else 0


def cover_plan(summary: dict, target_id: str, shortfall: int) -> list[tuple[str, int]] | None:
    """The preferred way to cover `shortfall`: the pool first, then the other jars by `spendable`, biggest first,
    each giving min(what it has, what is still missing). `None` when everything together is not enough."""
    plan: list[tuple[str, int]] = []
    missing = shortfall
    pool = pool_available(summary)
    if pool > 0:
        take = min(pool, missing)
        plan.append((POOL, take))
        missing -= take
    others = [j for j in _jars(summary).values() if j["id"] != target_id and (j.get("spendable") or 0) > 0]
    for jar in sorted(others, key=lambda j: j["spendable"], reverse=True):
        if missing <= 0:
            break
        take = min(jar["spendable"], missing)
        plan.append((jar["id"], take))
        missing -= take
    return plan if missing <= 0 else None


def check_cover(summary: dict, target_id: str, shortfall: int, ui: dict) -> Verdict:
    verdict = Verdict()
    if not is_valid_ui(ui) or ui.get("type") != "rebalance_jars":
        verdict.hard.append("Sai cấu trúc rebalance_jars (đủ field, amount > 0, không lặp nguồn, Σ moves phải bằng shortfall).")
        return verdict
    if ui["target_jar_id"] != target_id:
        verdict.hard.append(f"target_jar_id phải là {target_id!r}.")
    if ui["shortfall"] != shortfall:
        verdict.hard.append(f"shortfall phải đúng bằng {shortfall} ({_vnd(shortfall)}), không phải {ui['shortfall']}.")
    if not ui_matches_facts(ui, TurnFacts(jar_summary=summary, expense_category_ids=None)):
        verdict.hard.append("Có id hũ không nằm trong jar-summary.")
        return verdict
    jars = _jars(summary)
    for move in ui["moves"]:
        source, amount = move["from_jar_id"], move["amount"]
        if source == POOL:
            if amount > pool_available(summary):
                verdict.hard.append(f"pool chỉ cho tối đa {pool_available(summary)} ({_vnd(pool_available(summary))}), không phải {amount}.")
        elif jars[source].get("spendable") is None or amount > jars[source]["spendable"]:
            verdict.hard.append(f"hũ {source} chỉ cho tối đa spendable {jars[source].get('spendable')}, không phải {amount}.")
    if not verdict.hard:
        plan = cover_plan(summary, target_id, shortfall)
        given = {m["from_jar_id"]: m["amount"] for m in ui["moves"]}
        if plan is not None and given != dict(plan):
            verdict.soft.append(
                "Thứ tự ưu tiên là pool trước, rồi hũ có spendable lớn nhất, dừng khi đủ. Cách đúng: "
                + ", ".join(f"{source} {amount}" for source, amount in plan) + "."
            )
    return verdict


def receivers(summary: dict) -> list[dict]:
    """Jars that can receive money: only those with a `budgetLimit` (same rule as a rebalance target)."""
    return [j for j in _jars(summary).values() if j.get("budgetLimit") is not None]


def check_distribute(summary: dict, amount: int, ui: dict) -> Verdict:
    """`amount` is the customer's own money to share into the jars' balances. It is not taken from the pool or from
    any jar, so nothing about the pool limits it (only the shape, the jar ids and that the total is `amount`)."""
    verdict = Verdict()
    if not is_valid_ui(ui) or ui.get("type") != "distribute_amount":
        verdict.hard.append("Sai cấu trúc distribute_amount (allocations không rỗng, amount > 0, mỗi hũ một lần, có reason).")
        return verdict
    if not ui_matches_facts(ui, TurnFacts(jar_summary=summary, expense_category_ids=None)):
        verdict.hard.append("Có id hũ không nằm trong jar-summary.")
        return verdict
    can_receive = {j["id"] for j in receivers(summary)}
    for allocation in ui["allocations"]:
        if allocation["to_jar_id"] not in can_receive:
            verdict.hard.append(f"hũ {allocation['to_jar_id']} chưa đặt hạn mức nên không nhận được tiền.")
    total = sum(a["amount"] for a in ui["allocations"])
    if total > amount:
        verdict.hard.append(f"Tổng chia {total} vượt số tiền cần chia {amount} ({_vnd(amount)}).")
    elif total < amount:
        verdict.soft.append(f"Mới chia {total}, còn {amount - total} ({_vnd(amount - total)}) chưa chia; hãy chia hết {_vnd(amount)} (hoặc nói rõ lý do giữ lại trong reason).")
    return verdict


# --- what the customer reads ---------------------------------------------------------------------------------------
# `answer` and `reason` are shown to the customer, so the vocabulary of the API must not leak into them. Only ever a
# `soft` problem: a wording slip is worth one retry but must not throw away a proposal that is right.

_INTERNAL_WORDS = (
    "spendable", "remaining", "unallocated", "budgetLimit", "allocationHeadroom", "overLimit",
    "shortfall", "amount", "jar-summary", "jar_id", "pfm",
)
MAX_REASON_CHARS = 300


def wording_problems(answer: str, reason: str) -> list[str]:
    problems = []
    for name, text in (("answer", answer), ("reason", reason)):
        found = [w for w in _INTERNAL_WORDS if w.lower() in text.lower()]
        if found:
            problems.append(f"{name} không được nhắc tên nội bộ ({', '.join(found)}); dùng cách nói thường của khách.")
        if "`" in text:
            problems.append(f"{name} không được dùng dấu backtick.")
    if len(reason) > MAX_REASON_CHARS:
        problems.append(f"reason quá dài ({len(reason)} ký tự); viết 1–2 câu ngắn, đừng kể lại phép cộng.")
    return problems
