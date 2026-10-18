"""The deterministic side of the two jar endpoints (jar_endpoint.py): `POST /jar-distribute` and `POST /jar-rebalance`.

The LLM proposes; this module says what is true. It reads the numbers the model must not compute (what the pool holds,
what the giving jar can give) from the `jar-summary` the server read for this very request, and checks a proposal
against them.

Two grades of error, on purpose:
- `hard`: breaks a rule pfm enforces (a source gives more than it has, a made-up id, more than the amount asked, a
  broken shape). The proposal must not be returned.
- `soft`: only incomplete (part of the amount is left over) or badly worded. Worth one retry, but a proposal that still
  has only this is acceptable.
"""

from dataclasses import dataclass, field

from text_utils import is_valid_ui
from ui_guard import TurnFacts, ui_matches_facts


@dataclass
class Verdict:
    hard: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)


def _vnd(amount: float) -> str:
    return f"{round(amount):,}".replace(",", ".") + "đ"


def _jars(summary: dict) -> dict[str, dict]:
    return {j["id"]: j for j in summary.get("jars") or [] if isinstance(j, dict) and "id" in j}


def pool_available(summary: dict) -> int:
    """The "Chưa phân bổ" money that can be handed out: never negative, never unknown-as-something."""
    unallocated = summary.get("unallocated")
    return max(0, unallocated) if isinstance(unallocated, (int, float)) else 0


def source_available(summary: dict, jar_id: str) -> int:
    """What a jar can give away: its `spendable`. 0 for an unknown jar or one with no balance yet (`null`)."""
    spendable = _jars(summary).get(jar_id, {}).get("spendable")
    return spendable if isinstance(spendable, (int, float)) else 0


def receivers(summary: dict) -> list[dict]:
    """Jars that can receive money: every jar. A jar with no balance yet (or no limit) can still be topped up --
    the deposit is how it gets its first balance (pfm's "Chia ngay" sheet lists every jar). Only a jar that is not in
    the summary (an invented id) cannot."""
    return list(_jars(summary).values())


def _known_ids(summary: dict, ui: dict) -> bool:
    return ui_matches_facts(ui, TurnFacts(jar_summary=summary, expense_category_ids=None))


def check_distribute(summary: dict, amount: int, ui: dict) -> Verdict:
    """`amount` of the unallocated money is shared into the jars' balances: the total may not exceed `amount` nor what
    the pool really holds."""
    verdict = Verdict()
    if not is_valid_ui(ui) or ui.get("type") != "distribute_amount":
        verdict.hard.append("Sai cấu trúc distribute_amount (allocations không rỗng, amount > 0, mỗi hũ một lần, không có pool, có reason).")
        return verdict
    if not _known_ids(summary, ui):
        verdict.hard.append("Có id hũ không nằm trong jar-summary.")
        return verdict
    total = sum(a["amount"] for a in ui["allocations"])
    if total > amount:
        verdict.hard.append(f"Tổng chia {total} vượt số tiền cần chia {amount} ({_vnd(amount)}).")
    elif total < amount:
        verdict.soft.append(f"Mới chia {total}, còn {amount - total} ({_vnd(amount - total)}) chưa chia; hãy chia hết {_vnd(amount)} (hoặc nói rõ lý do giữ lại trong reason).")
    if total > pool_available(summary):
        verdict.hard.append(f"Tiền chưa phân bổ chỉ còn {pool_available(summary)} ({_vnd(pool_available(summary))}), không đủ để chia {total}.")
    return verdict


def check_rebalance(summary: dict, from_jar_id: str, amount: int, ui: dict) -> Verdict:
    """One jar (`from_jar_id`) gives `amount` to one or more other jars: the total may not exceed `amount` nor what the
    giving jar really has (`spendable`); a giver with no balance yet has nothing to give."""
    verdict = Verdict()
    if not is_valid_ui(ui) or ui.get("type") != "rebalance_jars":
        verdict.hard.append("Sai cấu trúc rebalance_jars (from_jar_id là hũ thật, allocations không rỗng, amount > 0, mỗi hũ nhận một lần, không tự chuyển cho chính mình, có reason).")
        return verdict
    if ui["from_jar_id"] != from_jar_id:
        verdict.hard.append(f"from_jar_id phải là {from_jar_id!r}.")
    if not _known_ids(summary, ui):
        verdict.hard.append("Có id hũ không nằm trong jar-summary.")
        return verdict
    total = sum(a["amount"] for a in ui["allocations"])
    available = source_available(summary, ui["from_jar_id"])
    if total > available:
        verdict.hard.append(f"hũ {ui['from_jar_id']} chỉ cho tối đa spendable {available} ({_vnd(available)}), không phải {total}.")
    if total > amount:
        verdict.hard.append(f"Tổng chuyển {total} vượt số tiền cần chuyển {amount} ({_vnd(amount)}).")
    elif total < amount:
        verdict.soft.append(f"Mới chuyển {total}, còn {amount - total} ({_vnd(amount - total)}) chưa chuyển; hãy chuyển hết {_vnd(amount)} (hoặc nói rõ lý do giữ lại trong reason).")
    return verdict


# --- what the customer reads ---------------------------------------------------------------------------------------
# `answer` and `reason` are shown to the customer, so the vocabulary of the API must not leak into them. Only ever a
# `soft` problem: a wording slip is worth one retry but must not throw away a proposal that is right.

_INTERNAL_WORDS = (
    "spendable", "remaining", "unallocated", "budgetLimit", "allocationHeadroom", "overLimit",
    "balance", "initial_balance", "shortfall", "amount", "jar-summary", "jar_id", "pfm",
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
