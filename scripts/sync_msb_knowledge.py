"""Snapshot MSB's retail product site into data/msb_knowledge/ (offline knowledge base).

Why: answering "MSB có thẻ nào hoàn tiền?" live meant 5-10 tool calls and 40s+ of
network + model round-trips, and the answer did not carry its source. The agent
now answers from this snapshot (tools/msb_knowledge_tools.py: ONE local lookup,
milliseconds) and every passage it returns carries the page URL and the date it
was fetched here.

What it does
- Crawls https://www.msb.com.vn/khach-hang-ca-nhan/ breadth-first (retail pages
  only, same allowlist as the runtime tools), via TinyFish Fetch.
- Adds the text-layer PDFs that matter for customers (loan-rate schedule, fee
  schedules, limits). Promotion/"thể lệ" PDFs are skipped on purpose: they are
  time-bound and go stale. Scanned PDFs (e.g. the deposit-rate decisions) yield
  no text; a person transcribes them into data/msb_knowledge/curated/*.md (this
  script never writes or deletes that directory). Here we only WATCH them: each
  transcription records the sha256 of the PDF it came from, and the manifest gets
  a status per transcription (current / changed / gone / unchecked) plus
  `unreviewed_scans` -- scanned PDFs that are neither transcribed nor listed in
  curated/reviewed.json, i.e. possibly a NEW rate decision nobody has read yet.
  The runtime tool turns both into warnings next to the transcribed numbers.
- Writes data/msb_knowledge/pages/*.md (front matter: title, source_url,
  fetched_at, kind, category) and data/msb_knowledge/manifest.json.

Run it on a schedule (daily is sensible) and commit the result -- the agent warns
the customer when the snapshot is older than MSB_KB_MAX_AGE_DAYS:

    uv run python scripts/sync_msb_knowledge.py            # needs TINYFISH_API_KEY in .env
    uv run python scripts/sync_msb_knowledge.py --dry-run  # crawl, print, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.market_news_tools import FETCH_URL, _looks_garbled  # noqa: E402

# Crawl scope. Only MSB's retail site and its PDFs are ever fetched; paths are normalised
# before checking so `/khach-hang-ca-nhan/../x` and look-alike hosts (msb.com.vn.evil.com)
# are rejected.
MSB_HOSTS = ("msb.com.vn", "www.msb.com.vn")
MSB_PATH_PREFIX = "/khach-hang-ca-nhan"
MSB_DOC_PREFIXES = ("/msb-website/", "/documents/")

KB_DIR = REPO_ROOT / "data" / "msb_knowledge"
PAGES_DIR = KB_DIR / "pages"
CURATED_DIR = KB_DIR / "curated"
REVIEWED_FILE = CURATED_DIR / "reviewed.json"  # {scan pdf url: why nobody transcribes it}
ROOT_URL = "https://www.msb.com.vn/khach-hang-ca-nhan/"
DOC_LISTING_PAGES = {
    "lai_suat_vay": "https://www.msb.com.vn/khach-hang-ca-nhan/lai-suat-vay/",
    "bieu_phi": "https://www.msb.com.vn/khach-hang-ca-nhan/bieu-mau-bieu-phi/",
    "lai_suat_tiet_kiem": "https://www.msb.com.vn/khach-hang-ca-nhan/lai-suat-tiet-kiem/",
}
VIETNAM_TZ = timezone(timedelta(hours=7))  # no DST

MAX_DEPTH = 3
MAX_PAGES = 200
BATCH = 10
MIN_PAGE_CHARS = 100
MAX_PAGE_CHARS = 20000
MAX_PDF_CHARS = 80000  # layout text is padded with spaces to keep table columns aligned
# Dynamic (client-rendered) or off-topic pages: nothing useful to snapshot.
SKIP_PATH_PARTS = ("/ty-gia", "/apple-pay")
# PDFs worth keeping (fees, limits, loan rates) vs time-bound promo terms.
# Matched on the accent-folded file name (see _fold): Vietnamese file names come in mixed Unicode forms.
PDF_KEEP = re.compile(r"(bieu|phi|lai[-_ ]?suat|han[-_ ]?muc)", re.IGNORECASE)
PDF_SKIP = re.compile(r"(khuyen[-_ ]?mai|the[-_ ]?le|ctkm|fansign|livestream|mkt)", re.IGNORECASE)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


# The savings pages embed an interest calculator (empty maturity dropdown, "Gốc + lãi dự kiến
# 0 VND", "Lãi suất cập nhật lúc <date>"). Without the rate table it belongs to it is pure noise
# and actively misleading -- the model quoted that widget timestamp as if it were the
# snapshot date -- so the whole "Công cụ tính toán" section is dropped.
_WIDGET_SECTION = re.compile(r"^## Công cụ tính toán\b.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
_WIDGET_LINE = re.compile(r"^.*Lãi suất cập nhật lúc.*$\n?", re.MULTILINE)


def _strip_widgets(body: str) -> str:
    body = _WIDGET_LINE.sub("", _WIDGET_SECTION.sub("", body))
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _now() -> datetime:
    return datetime.now(VIETNAM_TZ).replace(microsecond=0)


def _is_msb_retail_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in MSB_HOSTS:
        return False
    path = posixpath.normpath(unquote(parsed.path or "/"))
    return path == MSB_PATH_PREFIX or path.startswith(MSB_PATH_PREFIX + "/")


def _is_msb_document_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in MSB_HOSTS:
        return False
    path = posixpath.normpath(unquote(parsed.path or "/"))
    return path.lower().endswith(".pdf") and path.startswith(MSB_DOC_PREFIXES)


def _document_title(url: str) -> str:
    name = unquote(posixpath.basename(urlparse(url).path)).rsplit(".", 1)[0]
    return " ".join(name.replace("-", " ").replace("_", " ").replace("+", " ").split())


def _trim_site_chrome(text: str) -> str:
    # Pages open with header/footer boilerplate ("Quay lại", "Đăng nhập", "MSB Digital Bank",
    # address...) before the product's own "# Title".
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[i:])
    return text


def _canonical(url: str) -> str | None:
    """Drop query/fragment, force https + www + trailing slash; None if not a retail page."""
    parsed = urlparse(url.split("#")[0])
    if not parsed.scheme.startswith("http") or (parsed.hostname or "").lower() not in ("msb.com.vn", "www.msb.com.vn"):
        return None
    path = parsed.path if parsed.path.endswith("/") else parsed.path + "/"
    canonical = f"https://www.msb.com.vn{path}"
    return canonical if _is_msb_retail_url(canonical) else None


def _slug(url: str) -> str:
    path = unquote(urlparse(url).path)
    if path.lower().endswith(".pdf"):
        return "doc__" + re.sub(r"[^a-z0-9]+", "-", _fold(path.rsplit("/", 1)[-1][:-4])).strip("-")
    rel = path[len(MSB_PATH_PREFIX):].strip("/")
    return re.sub(r"[^a-z0-9_]+", "-", rel.replace("/", "__").lower()).strip("-") or "index"


def _category(url: str) -> str:
    rel = urlparse(url).path[len(MSB_PATH_PREFIX):].strip("/")
    return rel.split("/")[0] if rel else "tong-quan"


def fetch_batch(urls: list[str], key: str, *, links: bool) -> tuple[dict[str, dict], dict[str, str]]:
    response = httpx.post(
        FETCH_URL,
        json={"urls": urls, "format": "markdown", "links": links, "ttl": 0, "per_url_timeout_ms": 60000},
        headers={"X-API-Key": key},
        timeout=170,
    )
    response.raise_for_status()
    payload = response.json()
    results = {item.get("url"): item for item in payload.get("results") or []}
    errors = {item.get("url"): item.get("error", "error") for item in payload.get("errors") or []}
    return results, errors


def crawl_pages(key: str, max_pages: int) -> tuple[dict[str, dict], list[dict]]:
    pages: dict[str, dict] = {}
    failed: list[dict] = []
    seen = {ROOT_URL}
    frontier = [ROOT_URL]
    for depth in range(MAX_DEPTH + 1):
        if not frontier or len(pages) >= max_pages:
            break
        next_frontier: list[str] = []
        for i in range(0, len(frontier), BATCH):
            batch = frontier[i : i + BATCH]
            results, errors = fetch_batch(batch, key, links=depth < MAX_DEPTH)
            for url in batch:
                item = results.get(url)
                if item is None:
                    failed.append({"url": url, "reason": errors.get(url, "no result")})
                    continue
                pages[url] = item
                for link in item.get("links") or []:
                    canon = _canonical(link)
                    if canon and canon not in seen and not any(p in canon for p in SKIP_PATH_PARTS):
                        seen.add(canon)
                        next_frontier.append(canon)
        print(f"depth {depth}: fetched {len(frontier)}, discovered {len(next_frontier)} new")
        frontier = next_frontier[: max(0, max_pages - len(pages))]
    return pages, failed


def find_pdf_urls(key: str) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    results, _ = fetch_batch(list(DOC_LISTING_PAGES.values()), key, links=True)
    for topic, page in DOC_LISTING_PAGES.items():
        for link in (results.get(page) or {}).get("links") or []:
            if _is_msb_document_url(link) and link not in found:
                found[link] = topic
    return list(found.items())


def build_records(pages: dict[str, dict], now: datetime) -> tuple[list[dict], set[str]]:
    records, seen_hash = [], set()
    for url, item in pages.items():
        text = item.get("text")
        if not isinstance(text, str) or _looks_garbled(text):
            continue
        body = _strip_widgets(_trim_site_chrome(text))[:MAX_PAGE_CHARS]
        digest = hashlib.sha256(body.encode()).hexdigest()
        if len(body) < MIN_PAGE_CHARS or digest in seen_hash:
            continue
        seen_hash.add(digest)
        title = (item.get("title") or "").strip() or next(
            (l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("#")), _slug(url)
        )
        records.append(
            {"id": _slug(url), "title": title, "url": url, "kind": "page", "category": _category(url),
             "fetched_at": now.isoformat(), "sha256": digest, "body": body}
        )
    return records, seen_hash


def download_pdf(url: str) -> bytes | None:
    """The PDF's bytes, or None (not an MSB document URL, network error, redirected off-site, not a PDF)."""
    if not _is_msb_document_url(url):
        return None
    try:
        response = httpx.get(url, timeout=60, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    if (response.url.host or "").lower() not in MSB_HOSTS or not response.content.startswith(b"%PDF"):
        return None
    return response.content


def layout_text(url: str) -> str | None:
    """Column-preserving text of an MSB PDF via poppler's `pdftotext -layout`, or None.

    Fetch's PDF extraction (markdown, html and json alike) flattens tables into one string
    with no column boundaries; a run then paired two debit cards' annual fees the wrong way
    round. `-layout` keeps the columns aligned under their headers. Needs the poppler
    binary on the machine that runs this script (not in the production image); without it
    the caller falls back to the flattened text and the runtime tool warns about it.
    """
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    content = download_pdf(url)
    if content is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(content)
        try:
            proc = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, text=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            return None
    if proc.returncode != 0:
        return None
    text = "\n".join(line.rstrip() for line in proc.stdout.splitlines()).strip()
    return text if len(text) >= 50 and not _looks_garbled(text) else None


def build_pdf_records(key: str, now: datetime, seen_hash: set[str]) -> tuple[list[dict], list[dict]]:
    records, unreadable = [], []
    candidates = [
        (u, t) for u, t in find_pdf_urls(key) if PDF_KEEP.search(_fold(unquote(u))) and not PDF_SKIP.search(_fold(unquote(u)))
    ]
    texts: dict[str, tuple[str, str]] = {}  # url -> (text, extraction)
    for url, _ in candidates:
        layout = layout_text(url)
        if layout:
            texts[url] = (layout, "layout")
    missing = [(u, t) for u, t in candidates if u not in texts]
    errors: dict[str, str] = {}
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        results, batch_errors = fetch_batch([u for u, _ in batch], key, links=False)
        errors.update(batch_errors)
        for url, _ in batch:
            text = (results.get(url) or {}).get("text")
            if isinstance(text, str) and len(text.strip()) >= 50 and not _looks_garbled(text):
                texts[url] = (text.strip(), "flattened")
    for url, topic in candidates:
        title = _document_title(url)
        if url not in texts:
            unreadable.append({"url": url, "title": title, "topic": topic,
                               "reason": errors.get(url) or "PDF là bản scan (không có lớp chữ)"})
            continue
        text, extraction = texts[url]
        body = text[:MAX_PDF_CHARS]
        digest = hashlib.sha256(body.encode()).hexdigest()
        if digest in seen_hash:
            continue
        seen_hash.add(digest)
        records.append({"id": _slug(url), "title": title, "url": url, "kind": "pdf", "category": topic,
                        "extraction": extraction, "fetched_at": now.isoformat(), "sha256": digest, "body": body})
    return records, unreadable


def _front_matter(path: Path) -> dict[str, str]:
    meta = {}
    for line in path.read_text(encoding="utf-8").split("---", 2)[1].strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        meta[key.strip()] = json.loads(value) if value.startswith('"') else value
    return meta


def review_curated(scan_urls: set[str], unreadable: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Watch the hand-transcribed decisions. Returns (statuses, still-unreadable, unreviewed scans).

    status: "current" (URL still listed and the PDF is byte-identical to the transcribed one),
    "changed" (same URL, different bytes -- MSB replaced the file), "gone" (no longer listed),
    "unchecked" (could not download to compare).
    """
    statuses, covered = [], set()
    for path in sorted(CURATED_DIR.glob("*.md")):
        meta = _front_matter(path)
        url, expected = meta["source_url"], meta.get("source_sha256", "")
        covered.add(url)
        content = download_pdf(url) if url in scan_urls else None
        if url not in scan_urls:
            status = "gone"
        elif content is None:
            status = "unchecked"
        else:
            status = "current" if hashlib.sha256(content).hexdigest() == expected else "changed"
        statuses.append({"id": path.stem, "url": url, "status": status})
    try:
        reviewed = json.loads(REVIEWED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        reviewed = {}
    pending = [u for u in unreadable if u["url"] not in covered]
    unreviewed = [u for u in pending if u["url"] not in reviewed]
    return statuses, pending, unreviewed


def write_kb(
    records: list[dict],
    unreadable: list[dict],
    failed: list[dict],
    now: datetime,
    curated: list[dict] | None = None,
    unreviewed_scans: list[dict] | None = None,
) -> None:
    assert PAGES_DIR.resolve() == (REPO_ROOT / "data" / "msb_knowledge" / "pages").resolve()
    if PAGES_DIR.exists():
        shutil.rmtree(PAGES_DIR)  # drop pages MSB has since removed
    PAGES_DIR.mkdir(parents=True)
    manifest_pages = []
    for rec in records:
        front = (
            f"---\ntitle: {json.dumps(rec['title'], ensure_ascii=False)}\nsource_url: {rec['url']}\n"
            f"fetched_at: {rec['fetched_at']}\nkind: {rec['kind']}\ncategory: {rec['category']}\n"
            + (f"extraction: {rec['extraction']}\n" if rec.get("extraction") else "")
            + "---\n\n"
        )
        (PAGES_DIR / f"{rec['id']}.md").write_text(front + rec["body"] + "\n", encoding="utf-8")
        manifest_pages.append({k: rec[k] for k in ("id", "title", "url", "kind", "category", "fetched_at", "sha256")}
                               | {"chars": len(rec["body"])}
                               | ({"extraction": rec["extraction"]} if rec.get("extraction") else {}))
    manifest = {
        "fetched_at": now.isoformat(),
        "source": ROOT_URL,
        "pages": manifest_pages,
        "unreadable": unreadable,
        "curated": curated or [],
        "unreviewed_scans": unreviewed_scans or [],
        "failed": failed,
    }
    (KB_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="crawl and report, write nothing")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("TINYFISH_API_KEY")
    if not key:
        print("TINYFISH_API_KEY is not set (put it in .env)", file=sys.stderr)
        return 1

    now = _now()
    pages, failed = crawl_pages(key, args.max_pages)
    records, seen_hash = build_records(pages, now)
    pdf_records, unreadable = build_pdf_records(key, now, seen_hash)
    records += pdf_records
    scan_urls = {r["url"] for r in records if r["kind"] == "pdf"} | {u["url"] for u in unreadable}
    curated, unreadable, unreviewed = review_curated(scan_urls, unreadable)
    print(f"pages kept: {len(records) - len(pdf_records)} | pdfs kept: {len(pdf_records)} | "
          f"unreadable pdfs: {len(unreadable)} | failed fetches: {len(failed)}")
    for item in curated:
        print(f"  transcription {item['id']}: {item['status']}")
    for item in unreviewed:
        print(f"  !! UNREVIEWED SCAN (transcribe it into curated/ or add it to curated/reviewed.json): {item['url']}")
    if not records:
        print("nothing usable fetched -- refusing to overwrite the existing snapshot", file=sys.stderr)
        return 1
    if args.dry_run:
        for rec in records:
            print(f"  [{rec['kind']}] {rec['id']:60s} {len(rec['body']):6d} chars  {rec['title'][:50]}")
        return 0
    write_kb(records, unreadable, failed, now, curated, unreviewed)
    print(f"wrote {len(records)} files to {KB_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
