"""MSB product knowledge, answered from an offline snapshot -- no network at request time.

`scripts/sync_msb_knowledge.py` snapshots MSB's retail site (and its text-layer
PDFs) into data/msb_knowledge/. This tool ranks passages of that snapshot for a
question and returns them WITH their source URL and the date they were fetched, so
the model answers in one fast local call and can always cite where a fact came from.

Why offline: answering a simple product question live took 5-10 tool calls, several
model round-trips and 40s+, and the answer carried no source. Here it is one call
(milliseconds), and the source travels with the text.

Freshness is explicit rather than assumed: every passage carries its fetch date, and
if the snapshot is older than MSB_KB_MAX_AGE_DAYS (default 7) the output says so and
tells the model to state the date and send the customer to the app/advisor.

Deposit-rate decisions are scanned images with no text layer, so their tables are
transcribed by hand into data/msb_knowledge/curated/*.md (a person read the scan and
typed the tables). The sync script never touches that directory; it only checks each
transcription's source PDF hash and flags scans nobody has reviewed yet, and this tool
turns those flags into warnings next to the numbers.

Ranking is plain BM25 over passages, in pure Python (the corpus is ~100 pages, so no
search dependency is worth adding). Vietnamese is matched with diacritics first
(thẻ vs thế vs thể mean different things) and diacritic-folded second, so a query
typed without accents still finds the page.
"""

import json
import math
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from middleware import seed_customer_context

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "msb_knowledge"
DEFAULT_MAX_AGE_DAYS = 7
TOP_K = 3
MAX_PER_PAGE = 2
CHUNK_MIN_CHARS = 350
CHUNK_MAX_CHARS = 900
FOLDED_WEIGHT = 0.35
BIGRAM_BOOST = 1.0
MIN_SCORE = 1.0
RATES_PAGE = "https://www.msb.com.vn/khach-hang-ca-nhan/lai-suat-tiet-kiem/"
# PDF text extraction (checked 2026-09-19: markdown, html and json all return the same string)
# flattens tables, so column boundaries are gone. A run paired the fees of two debit cards the
# wrong way round, so every PDF passage carries this warning next to its source.
# Layout extraction (`pdftotext -layout`, see scripts/sync_msb_knowledge.py) keeps the columns
# aligned, so a whole PDF page stays ONE passage (header row + fee rows together) instead of
# being cut into 900-char pieces that would separate the rows from their column titles.
PDF_PAGE_CHUNK_MAX = 7000
MAX_OUTPUT_CHARS = 10000
PDF_LAYOUT_NOTE = (
    "Lưu ý: bảng PDF giữ bố cục cột (chữ cố định). Đọc mỗi giá trị theo cột nằm ngay dưới đúng tiêu đề cột "
    "ở đầu bảng (tên thẻ/sản phẩm/hạng khách hàng); trang sau của bảng có thể không lặp lại tiêu đề. "
    "Nếu vẫn không chắc giá trị thuộc cột nào thì đừng ghép — dẫn link tài liệu."
)
CURATED_LEGEND = (
    "Bản chép lại thủ công từ PDF scan của MSB; dấu — là ô trống trong bản gốc (không có hình thức/kỳ hạn đó). "
    "Khi trả lời nêu tên quyết định + ngày hiệu lực, nói rõ lãi suất TẠI QUẦY hay TRỰC TUYẾN (hai bảng khác nhau), "
    "và nhắc khách xác nhận mức lãi hiện hành tại app MSB/quầy vì MSB có thể điều chỉnh sau ngày hiệu lực. "
    "Bảng chỉ áp dụng cho hình thức nêu trong tiêu đề — không dùng cho chứng chỉ tiền gửi, tài khoản sinh lời hay lãi vay."
)
PDF_TABLE_WARNING = (
    "Lưu ý: đoạn này lấy từ PDF, bảng đã bị làm phẳng thành chữ nên KHÔNG còn ranh giới cột. Đừng tự ghép "
    "từng số với từng loại thẻ/sản phẩm/hạng khách hàng nếu không chắc chắn — nêu các mức phí có trong "
    "đoạn và dẫn link tài liệu để khách xem đúng bảng."
)
_TITLE_SUFFIX = re.compile(r"\s*-\s*(MSB\s*-\s*)?Ngân hàng TMCP Hàng Hải Việt Nam\s*$")
_STOPWORDS = frozenset(
    "là và của có cho nào không được bao nhiêu gì như ở về với các một những tôi mình bạn "
    "thế hiện nay đang này đó thì cần muốn hỏi xin hãy vậy nhé ạ msb".split()
)  # "msb" is in every page's title/text, so the model adding it to a query only adds noise

# Folding "thế"/"vậy" (stopwords) gives "the"/"vay" -- which are the content words "thẻ" (card)
# and "vay" (loan) once accents are dropped. Never treat those two as stopwords when folded.
_FOLD_COLLISIONS = frozenset({"the", "vay"})
_FOLDED_STOPWORDS = (
    frozenset(unicodedata.normalize("NFD", w.replace("đ", "d")).encode("ascii", "ignore").decode() for w in _STOPWORDS)
    - _FOLD_COLLISIONS
)
TITLE_BOOST = 1.5

_kb_cache: dict | None = None


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


# "không" is a stopword, which turned "không kỳ hạn" (demand deposit) into "kỳ hạn" (term deposit): the
# opposite product. Keep the phrase as one token so it survives on both channels.
_NO_TERM = re.compile(r"không\s+kỳ\s+hạn")
_NO_TERM_FOLDED = re.compile(r"khong\s+ky\s+han")


def _tokens(text: str) -> list[str]:
    text = _NO_TERM.sub("khongkyhan", unicodedata.normalize("NFC", text.lower()))
    return [t for t in re.findall(r"\w+", text) if t not in _STOPWORDS]


def _folded_tokens(text: str) -> list[str]:
    text = _NO_TERM_FOLDED.sub("khongkyhan", _fold(text))
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in _FOLDED_STOPWORDS]


def _parse_page(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    _, front, body = raw.split("---", 2)
    meta = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        meta[key.strip()] = json.loads(value) if value.startswith('"') else value
    return meta, body.strip()


def _split_chunks(body: str) -> list[str]:
    """Group blank-line separated blocks into ~350-900 char passages; split oversized blocks."""
    pieces: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        while len(block) > CHUNK_MAX_CHARS:
            cut = block.rfind("\n", 0, CHUNK_MAX_CHARS)
            cut = cut if cut > CHUNK_MAX_CHARS // 2 else block.rfind(" ", 0, CHUNK_MAX_CHARS)
            cut = cut if cut > 0 else CHUNK_MAX_CHARS
            pieces.append(block[:cut].strip())
            block = block[cut:].strip()
        if block:
            pieces.append(block)
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > CHUNK_MAX_CHARS:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}".strip()
        if len(current) >= CHUNK_MIN_CHARS and piece.startswith("#"):
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _load_kb() -> dict | None:
    global _kb_cache
    manifest_path = KB_DIR / "manifest.json"
    if not manifest_path.is_file():
        return None
    curated_stamp = tuple((f.name, f.stat().st_mtime_ns) for f in sorted((KB_DIR / "curated").glob("*.md")))
    stamp = (manifest_path.resolve(), manifest_path.stat().st_mtime_ns, curated_stamp)
    if _kb_cache and _kb_cache["stamp"] == stamp:
        return _kb_cache
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = []
    for entry in manifest["pages"]:
        page = KB_DIR / "pages" / f"{entry['id']}.md"
        if not page.is_file():
            continue
        meta, body = _parse_page(page)
        title = _TITLE_SUFFIX.sub("", meta.get("title", entry["title"]))
        kind = meta.get("kind", entry.get("kind", "page"))
        extraction = meta.get("extraction", entry.get("extraction", "flattened" if kind == "pdf" else ""))
        # (display text, text used for ranking): a layout PDF page is ranked by its small pieces
        # (BM25 punishes one long passage) but returned whole, so the column titles travel with
        # the fee rows; every other passage is displayed as ranked.
        units: list[tuple[str, str, object]] = []
        if kind == "pdf" and extraction == "layout":
            for page_no, pdf_page in enumerate(part.strip("\n") for part in body.split("\f") if part.strip()):
                fine = _split_chunks(pdf_page) if len(pdf_page) > CHUNK_MAX_CHARS else [pdf_page]
                whole = len(pdf_page) <= PDF_PAGE_CHUNK_MAX  # too large to return whole: return the matching piece
                units += [
                    (pdf_page if whole else piece, piece, (entry["id"], page_no, 0 if whole else i))
                    for i, piece in enumerate(fine)
                ]
        else:
            units = [(piece, piece, None) for piece in _split_chunks(body)]
        for text, ranked, page_key in units:
            indexed = f"{title} {title} {ranked}"
            chunks.append(
                {
                    "title": title,
                    "kind": kind,
                    "extraction": extraction,
                    "url": meta.get("source_url", entry["url"]),
                    "fetched_at": meta.get("fetched_at", entry["fetched_at"]),
                    "text": text,
                    "page_key": page_key or (entry["id"], id(text)),
                    "lower": unicodedata.normalize("NFC", indexed.lower()),
                    "title_folded": set(_folded_tokens(title)),
                    "tokens": _tokens(indexed),
                    "folded": _folded_tokens(indexed),
                }
            )
    for path in sorted((KB_DIR / "curated").glob("*.md")):
        meta, body = _parse_page(path)
        title = meta.get("title", path.stem)
        sections = [part.strip() for part in re.split(r"(?m)^(?=## )", body) if part.strip().startswith("## ")]
        for i, section in enumerate(sections):
            # Ranked by title + heading only: a full rate table is long, and BM25 would let the short
            # tables (1-3 weeks, ALMA) outrank the main counter/online tables for "lãi suất 12 tháng".
            heading = section.splitlines()[0]
            indexed = f"{title} {title} {heading}"
            chunks.append(
                {
                    "title": title,
                    "kind": "transcribed",
                    "extraction": "transcribed",
                    "id": path.stem,
                    "url": meta["source_url"],
                    "fetched_at": meta["transcribed_at"],
                    "decision": meta.get("decision", ""),
                    "effective_from": meta.get("effective_from", ""),
                    "text": section,
                    "page_key": (path.stem, i, 0),
                    "lower": unicodedata.normalize("NFC", indexed.lower()),
                    "title_folded": set(_folded_tokens(title)),
                    "tokens": _tokens(indexed),
                    "folded": _folded_tokens(indexed),
                }
            )
    n = len(chunks)
    avg_len = sum(len(c["tokens"]) for c in chunks) / max(1, n)
    avg_folded = sum(len(c["folded"]) for c in chunks) / max(1, n)
    df, df_folded = {}, {}
    for c in chunks:
        for t in set(c["tokens"]):
            df[t] = df.get(t, 0) + 1
        for t in set(c["folded"]):
            df_folded[t] = df_folded.get(t, 0) + 1
    _kb_cache = {
        "stamp": stamp,
        "manifest": manifest,
        "chunks": chunks,
        "avg_len": avg_len,
        "avg_folded": avg_folded,
        "df": df,
        "df_folded": df_folded,
    }
    return _kb_cache


def _bm25(query_tokens: list[str], doc_tokens: list[str], df: dict, n: int, avg_len: float) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    k1, b = 1.5, 0.75
    counts: dict[str, int] = {}
    for t in doc_tokens:
        counts[t] = counts.get(t, 0) + 1
    score = 0.0
    for t in set(query_tokens):
        tf = counts.get(t, 0)
        if not tf:
            continue
        idf = math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
        score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc_tokens) / avg_len))
    return score


def _score(kb: dict, chunk: dict, q_tokens: list[str], q_folded: list[str], accent_free: bool) -> float:
    n = len(kb["chunks"])
    # An accent-free query would match accent-free text (PDF titles from file names) exactly AND
    # folded, i.e. twice, and accented pages only folded -- so it is scored on the folded
    # channel alone, at full weight, and both kinds of page compete on equal terms.
    exact = 0.0 if accent_free else _bm25(q_tokens, chunk["tokens"], kb["df"], n, kb["avg_len"])
    folded = _bm25(q_folded, chunk["folded"], kb["df_folded"], n, kb["avg_folded"])
    score = exact + (1.0 if accent_free else FOLDED_WEIGHT) * folded
    # Titles derived from PDF file names have no diacritics ("Bieu phi The ghi no"), so
    # match them on the folded form and weight it: a title hit is a strong relevance signal.
    score += TITLE_BOOST * len(chunk["title_folded"].intersection(q_folded))
    for first, second in zip(q_tokens, q_tokens[1:]):
        if f"{first} {second}" in chunk["lower"]:
            score += BIGRAM_BOOST
    return score


def _date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y")


PDF_PREFERENCE_RATIO = 0.6
CURATED_PREFERENCE_RATIO = 0.5


def _asks_fee_or_loan_rate(q_folded: list[str]) -> bool:
    """Fee schedules and loan-rate schedules are authoritative in the PDFs; product pages only
    mention fees in passing (FAQ lines), so for these questions the best PDF page must not lose
    its place to a marketing page that happens to score a little higher."""
    words = set(q_folded)
    return "phi" in words or {"han", "muc"} <= words or {"lai", "suat", "vay"} <= words


def _asks_about_deposit_rates(query: str) -> bool:
    folded = _fold(query)
    return "lai suat" in folded and any(w in folded for w in ("tiet kiem", "tien gui", "gui", "ky han", "chung chi"))


@tool
def search_msb_knowledge(query: str) -> str:
    """Look up MSB retail-product information (savings, certificates of deposit,
    cards, loans, insurance, accounts, fees, loan rates) in the offline snapshot of
    MSB's official website and PDFs. ONE call is enough: it returns the best 1-3
    passages, each with its source URL and the date it was fetched -- cite them.
    Instant (no network). Use short product keywords, e.g. "thẻ tín dụng hoàn
    tiền", "chứng chỉ tiền gửi", "tiết kiệm Ong vàng", "phí thường niên thẻ ghi nợ",
    "lãi suất vay".

    Deposit-rate tables (savings, online, non-term) come from the MSB rate decisions,
    hand-transcribed from scans; the output names the decision and effective date --
    quote them with that date, distinguish counter vs online rates, and never guess a
    rate that is not in the returned table.

    Args:
        query: What the customer wants to know, in Vietnamese (short keywords work best).
    """
    kb = _load_kb()
    if kb is None:
        return (
            "Chưa có dữ liệu sản phẩm MSB đã lưu (chạy scripts/sync_msb_knowledge.py). Đừng tự bịa: "
            "báo khách xem https://www.msb.com.vn/khach-hang-ca-nhan/ hoặc hỏi tư vấn viên MSB."
        )
    query = (query or "").strip()
    if not query:
        return "Cần có từ khoá tìm kiếm."

    q_tokens, q_folded = _tokens(query), _folded_tokens(query)
    accent_free = _fold(query) == unicodedata.normalize("NFC", query.lower())
    scored = sorted(
        ((_score(kb, c, q_tokens, q_folded, accent_free), c) for c in kb["chunks"]),
        key=lambda pair: pair[0],
        reverse=True,
    )
    picked, per_page, seen_pages = [], {}, set()
    for score, chunk in scored:
        if score < MIN_SCORE or len(picked) >= TOP_K:
            break
        if chunk["page_key"] in seen_pages or per_page.get(chunk["url"], 0) >= MAX_PER_PAGE:
            continue  # a whole PDF page is returned once, however many of its pieces matched
        seen_pages.add(chunk["page_key"])
        per_page[chunk["url"]] = per_page.get(chunk["url"], 0) + 1
        picked.append(chunk)

    if picked and _asks_fee_or_loan_rate(q_folded) and not any(c["kind"] == "pdf" for c in picked):
        top = scored[0][0]
        best_pdf = next(
            (c for score, c in scored if c["kind"] == "pdf" and score >= max(MIN_SCORE, PDF_PREFERENCE_RATIO * top)), None
        )
        if best_pdf is not None:
            picked = [best_pdf] + picked[: TOP_K - 1]

    asks_deposit = _asks_about_deposit_rates(query)
    if asks_deposit:
        # The scanned rate decisions are only available as hand-typed tables; a marketing page must
        # not outrank them for "lãi suất tiết kiệm ...".
        # Only when a table is a real match (not a stray hit while the answer is another product's page,
        # e.g. certificates of deposit, whose rates are not in these decisions).
        floor = max(MIN_SCORE, CURATED_PREFERENCE_RATIO * scored[0][0])
        tables, seen_tables = [], set()
        for score, chunk in scored:
            if score < floor or len(tables) >= MAX_PER_PAGE:
                break
            if chunk["kind"] == "transcribed" and chunk["page_key"] not in seen_tables:
                seen_tables.add(chunk["page_key"])
                tables.append(chunk)
        if tables:
            picked = tables + [c for c in picked if c["kind"] != "transcribed"][: TOP_K - len(tables)]

    snapshot_at = datetime.fromisoformat(kb["manifest"]["fetched_at"])
    age_days = (seed_customer_context._today().date() - snapshot_at.date()).days
    try:
        max_age = int(os.environ.get("MSB_KB_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS))
    except ValueError:
        max_age = DEFAULT_MAX_AGE_DAYS

    if not picked:
        lines = [
            "Không tìm thấy nội dung phù hợp trong dữ liệu sản phẩm MSB đã lưu. Đừng tự bịa: báo khách "
            "xem https://www.msb.com.vn/khach-hang-ca-nhan/ hoặc hỏi tư vấn viên MSB."
        ]
    else:
        lines = [f"Nguồn: website chính thức MSB, dữ liệu lưu ngày {_date(kb['manifest']['fetched_at'])}."]
        for i, chunk in enumerate(picked, start=1):
            text = chunk["text"]
            note = ""
            if chunk["kind"] == "transcribed":
                effective = f", hiệu lực từ {_date(chunk['effective_from'])}" if chunk["effective_from"] else ""
                block = (
                    f"\n[{i}] {chunk['title']}\n{text}\nNguồn: {chunk['url']} ({chunk['decision']}{effective}; "
                    f"bản chép lại ngày {_date(chunk['fetched_at'])})\n{CURATED_LEGEND}"
                )
                if i > 1 and sum(len(l) for l in lines) + len(block) > MAX_OUTPUT_CHARS:
                    break
                lines.append(block)
                continue
            if chunk["kind"] == "pdf":
                if chunk["extraction"] == "layout":
                    text, note = f"```\n{text}\n```", f"\n{PDF_LAYOUT_NOTE}"
                else:
                    note = f"\n{PDF_TABLE_WARNING}"
            block = f"\n[{i}] {chunk['title']}\n{text}\nNguồn: {chunk['url']} (lấy ngày {_date(chunk['fetched_at'])}){note}"
            if i > 1 and sum(len(l) for l in lines) + len(block) > MAX_OUTPUT_CHARS:
                break  # a wide PDF table can be several thousand characters; never bury the reader
            lines.append(block)
    if age_days > max_age:
        lines.append(
            f"\nCẢNH BÁO: dữ liệu đã lưu cách đây {age_days} ngày (quá {max_age} ngày) — có thể đã thay đổi. "
            "Nêu rõ ngày cập nhật và nhắc khách xác nhận trên app MSB/tư vấn viên."
        )
    curated_picked = [c for c in picked if c["kind"] == "transcribed"]
    if curated_picked:
        status = {e["id"]: e["status"] for e in kb["manifest"].get("curated", [])}
        if any(status.get(c["id"], "unchecked") != "current" for c in curated_picked):
            lines.append(
                "\nCẢNH BÁO: lần đồng bộ gần nhất không xác nhận được bản PDF gốc của biểu lãi suất này còn nguyên "
                "(đã đổi, bị gỡ hoặc chưa kiểm tra) — số liệu có thể đã lỗi thời. Nêu rõ điều đó và dẫn "
                f"{RATES_PAGE} hoặc app MSB."
            )
        if kb["manifest"].get("unreviewed_scans"):
            lines.append(
                "\nCẢNH BÁO: trang lãi suất MSB có quyết định lãi suất mới chưa được chép vào dữ liệu — mức lãi có thể "
                f"đã đổi. Nêu rõ ngày hiệu lực của quyết định đã dẫn và gửi khách xem {RATES_PAGE} hoặc app MSB."
            )
    elif asks_deposit:
        lines.append(
            "\nLƯU Ý: dữ liệu này không có bảng lãi suất tiền gửi khớp câu hỏi (website tải động, PDF biểu lãi "
            f"suất là bản scan). Chỉ nêu con số nếu nó nằm trong đoạn trên; biểu lãi suất đầy đủ xem {RATES_PAGE} hoặc app MSB."
        )
    return "\n".join(lines)
