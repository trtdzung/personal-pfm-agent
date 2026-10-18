import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_msb_knowledge.py"
spec = importlib.util.spec_from_file_location("sync_msb_knowledge", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=sync.VIETNAM_TZ)
BASE = "https://www.msb.com.vn/khach-hang-ca-nhan/"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://www.msb.com.vn/khach-hang-ca-nhan/the/", BASE + "the/"),
        ("https://www.msb.com.vn/khach-hang-ca-nhan/the", BASE + "the/"),
        ("http://msb.com.vn/khach-hang-ca-nhan/the/#top", BASE + "the/"),
        ("https://www.msb.com.vn/khach-hang-ca-nhan/the/?utm_source=x", BASE + "the/"),
    ],
)
def test_canonical_normalises_retail_urls(raw, expected):
    assert sync._canonical(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.msb.com.vn/khach-hang-doanh-nghiep/",
        "https://www.msb.com.vn/ve-chung-toi/",
        "https://tuoitre.vn/khach-hang-ca-nhan/",
        "https://msb.com.vn.evil.com/khach-hang-ca-nhan/",
        "mailto:x@msb.com.vn",
    ],
)
def test_canonical_rejects_non_retail_or_foreign_urls(raw):
    assert sync._canonical(raw) is None


def test_slug_and_category():
    assert sync._slug(BASE) == "index"
    assert sync._slug(BASE + "the/the-msb-visa-signature/") == "the__the-msb-visa-signature"
    assert sync._slug("https://www.msb.com.vn/msb-website/Hạn-mức-giao-dịch-Web.pdf") == "doc__han-muc-giao-dich-web"
    assert sync._category(BASE + "the/x/") == "the"
    assert sync._category(BASE) == "tong-quan"


@pytest.mark.parametrize(
    "name, keep",
    [
        ("Bieu-phi-The-ghi-no.pdf", True),
        ("LAI-SUAT-TIN-DUNG-TAI-NGAN-HANG-MSB-2026.pdf", True),
        ("Hạn-mức-giao-dịch-Web.pdf", True),
        ("THE-LE-CTKM-HOAN-TIEN-CHUONG-TRINH-DOI-TAC.pdf", False),  # time-bound promotion
        ("Thong-bao-Khuyen-Mai-Dien-TH-062026.pdf", False),
        ("MSBCDRB2609.pdf", False),
        ("LAI-SUAT-TIN-DUNG-TAI-NGAN-HANG-MSB-gui-MKT.pdf", False),  # marketing copy
    ],
)
def test_pdf_filter_keeps_fees_limits_and_rates_but_drops_promotions(name, keep):
    folded = sync._fold(name)
    assert bool(sync.PDF_KEEP.search(folded) and not sync.PDF_SKIP.search(folded)) is keep


def test_build_records_trims_boilerplate_dedupes_and_drops_junk():
    body = "### Quay lại\n\nĐăng nhập\n\n# Thẻ X\n\n" + "Nội dung sản phẩm. " * 20
    pages = {
        BASE + "the/x/": {"title": "Thẻ X - Ngân hàng", "text": body},
        BASE + "the/x-copy/": {"title": "Bản sao", "text": body},  # same content
        BASE + "the/short/": {"title": "Ngắn", "text": "# Ngắn\n\nquá ngắn"},
        BASE + "the/bin/": {"title": "Rác", "text": "�\x00\x1c" * 300},
        BASE + "the/none/": {"title": "Không có", "text": None},
    }
    records, _ = sync.build_records(pages, NOW)
    assert [r["url"] for r in records] == [BASE + "the/x/"]
    rec = records[0]
    assert rec["body"].startswith("# Thẻ X") and "Quay lại" not in rec["body"]
    assert rec["fetched_at"] == NOW.isoformat() and rec["category"] == "the"


def test_write_kb_replaces_old_pages_and_writes_a_manifest(tmp_path, monkeypatch):
    kb = tmp_path / "data" / "msb_knowledge"
    monkeypatch.setattr(sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync, "KB_DIR", kb)
    monkeypatch.setattr(sync, "PAGES_DIR", kb / "pages")
    (kb / "pages").mkdir(parents=True)
    (kb / "pages" / "stale-page-msb-removed.md").write_text("old")
    rec = {"id": "the__x", "title": 'Thẻ "X"', "url": BASE + "the/x/", "kind": "page", "category": "the",
           "fetched_at": NOW.isoformat(), "sha256": "abc", "body": "# Thẻ X\n\nnội dung"}
    sync.write_kb([rec], [{"url": "u", "title": "t", "topic": "x", "reason": "scan"}], [], NOW)
    assert not (kb / "pages" / "stale-page-msb-removed.md").exists()
    text = (kb / "pages" / "the__x.md").read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: ") and f"source_url: {BASE}the/x/" in text
    import json

    manifest = json.loads((kb / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pages"][0]["id"] == "the__x" and manifest["pages"][0]["chars"] == len(rec["body"])
    assert manifest["unreadable"][0]["reason"] == "scan"


def test_strip_widgets_drops_the_empty_interest_calculator_and_its_misleading_timestamp():
    body = (
        "# Tiết kiệm Ong vàng\n\n## Thông tin sản phẩm\n\nKỳ hạn linh hoạt.\n\n"
        "## Công cụ tính toán\n\n### Ước tính lãi\n\n01 Tháng\n\n36 Tháng\n\nGốc + lãi dự kiến\n\n0 VND\n\n"
        "Lãi suất cập nhật lúc 15:28 08/09/2026\n\n(\\*) Bảng tính chỉ mang tính chất tham khảo.\n\n"
        "## Câu hỏi thường gặp\n\nMở sổ thế nào?"
    )
    out = sync._strip_widgets(body)
    assert "Công cụ tính toán" not in out and "08/09/2026" not in out and "0 VND" not in out
    assert "Kỳ hạn linh hoạt." in out and "## Câu hỏi thường gặp" in out and "Mở sổ thế nào?" in out


def test_strip_widgets_also_removes_a_stray_timestamp_line_outside_the_section():
    assert "cập nhật lúc" not in sync._strip_widgets("# T\n\nNội dung.\n\nLãi suất cập nhật lúc 10:00 01/01/2026\n\nHết.")


# --- URL allowlists and page cleaning (moved here from the removed live-lookup tools) ---


@pytest.mark.parametrize(
    "url",
    [
        BASE,
        BASE + "tiet-kiem/tiet-kiem-ong-vang/",
        "https://msb.com.vn/khach-hang-ca-nhan/the/",
        "http://www.msb.com.vn/khach-hang-ca-nhan/vay/",
        "https://WWW.MSB.COM.VN/khach-hang-ca-nhan/the/?utm=1",
        "https://www.msb.com.vn/khach-hang-ca-nhan",
    ],
)
def test_retail_allowlist_accepts_msb_retail_urls(url):
    assert sync._is_msb_retail_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.msb.com.vn/khach-hang-doanh-nghiep/",
        "https://www.msb.com.vn/",
        "https://www.msb.com.vn/documents/20121/1/x.pdf",
        "https://msb.com.vn.evil.com/khach-hang-ca-nhan/",
        "https://evilmsb.com.vn/khach-hang-ca-nhan/",
        "https://www.msb.com.vn/khach-hang-ca-nhan/../khach-hang-doanh-nghiep/",
        "https://www.msb.com.vn/khach-hang-ca-nhan/%2e%2e/tuyen-dung",
        "https://www.msb.com.vn/khach-hang-ca-nhanx/",
        "https://tuoitre.vn/khach-hang-ca-nhan/",
        "file:///etc/passwd",
        "",
    ],
)
def test_retail_allowlist_rejects_everything_else(url):
    assert not sync._is_msb_retail_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.msb.com.vn/msb-website/2026/04/QD-4144-x.pdf",
        "https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf",
        "https://msb.com.vn/documents/20121/595178/x.PDF",
        "https://www.msb.com.vn/msb-website/2026/04/Hạn-mức-giao-dịch-Web.pdf",
    ],
)
def test_document_allowlist_accepts_msb_pdfs(url):
    assert sync._is_msb_document_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.msb.com.vn/khach-hang-ca-nhan/the/x.pdf",
        "https://www.msb.com.vn/msb-website/notes.html",
        "https://www.msb.com.vn/msb-website/../khach-hang-doanh-nghiep/x.pdf",
        "https://www.msb.com.vn/msb-website/%2e%2e/tuyen-dung/x.pdf",
        "https://msb.com.vn.evil.com/msb-website/x.pdf",
        "https://evil.com/msb-website/x.pdf",
        "file:///msb-website/x.pdf",
        "",
    ],
)
def test_document_allowlist_rejects_non_msb_or_non_pdf_urls(url):
    assert not sync._is_msb_document_url(url)


def test_document_title_is_readable_from_the_file_name():
    assert sync._document_title("https://www.msb.com.vn/msb-website/2026/04/QD-4144-Ban-hanh-bieu-lai-suat.pdf") == (
        "QD 4144 Ban hanh bieu lai suat"
    )
    assert sync._document_title("https://www.msb.com.vn/documents/a/QD+1975+ban+hanh_x.pdf") == "QD 1975 ban hanh x"


def test_trim_site_chrome_starts_at_the_products_own_title():
    text = "### Quay lại\n\nĐăng nhập\n\n### MSB Digital Bank\n\n# MSB Mastercard Hybrid\n\nThẻ 2 trong 1"
    assert sync._trim_site_chrome(text) == "# MSB Mastercard Hybrid\n\nThẻ 2 trong 1"
    assert sync._trim_site_chrome("### Chỉ có tiêu đề cấp 3\n\nnội dung") == "### Chỉ có tiêu đề cấp 3\n\nnội dung"


# --- layout extraction of PDFs ---

PDF_URL = "https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf"


def _fake_get_factory(url, content, final_url=None):
    def _get(u, timeout=None, follow_redirects=None):
        return sync.httpx.Response(200, content=content, request=sync.httpx.Request("GET", final_url or u))

    return _get


def test_layout_text_returns_none_without_pdftotext(monkeypatch):
    monkeypatch.setattr(sync.shutil, "which", lambda name: None)
    assert sync.layout_text(PDF_URL) is None


def test_layout_text_refuses_urls_outside_the_msb_allowlist_without_downloading(monkeypatch):
    monkeypatch.setattr(sync.shutil, "which", lambda name: "/usr/bin/pdftotext")

    def _boom(*a, **k):
        raise AssertionError("no download for a foreign URL")

    monkeypatch.setattr(sync.httpx, "get", _boom)
    assert sync.layout_text("https://evil.com/x.pdf") is None
    assert sync.layout_text("https://www.msb.com.vn/khach-hang-ca-nhan/the/") is None


def test_layout_text_runs_pdftotext_layout_and_strips_trailing_spaces(monkeypatch):
    monkeypatch.setattr(sync.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(PDF_URL, b"%PDF-1.7 fake"))
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        text = "Loại thẻ     A     B   \n2. Phí thường niên   50.000   Miễn phí   \n" + "x" * 60
        return sync.subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")

    monkeypatch.setattr(sync.subprocess, "run", _run)
    out = sync.layout_text(PDF_URL)
    assert seen["cmd"][1] == "-layout"
    assert out.splitlines()[0] == "Loại thẻ     A     B" and "50.000   Miễn phí" in out


@pytest.mark.parametrize(
    "content, final_url, stdout",
    [
        (b"<html>not a pdf</html>", None, "y" * 80),  # not a PDF
        (b"%PDF-1.7", "https://evil.com/x.pdf", "y" * 80),  # redirected off-site
        (b"%PDF-1.7", None, "   \n  "),  # scanned PDF: no text layer
    ],
)
def test_layout_text_returns_none_for_non_pdf_offsite_redirect_or_empty_text(monkeypatch, content, final_url, stdout):
    monkeypatch.setattr(sync.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(PDF_URL, content, final_url))
    monkeypatch.setattr(
        sync.subprocess, "run", lambda cmd, **k: sync.subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
    )
    assert sync.layout_text(PDF_URL) is None


def test_build_pdf_records_prefers_layout_text_and_falls_back_to_flattened(monkeypatch):
    urls = [
        ("https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf", "bieu_phi"),
        ("https://www.msb.com.vn/msb-website/LAI-SUAT-TIN-DUNG-2026.pdf", "lai_suat_vay"),
        ("https://www.msb.com.vn/msb-website/QD-4144-bieu-lai-suat.pdf", "lai_suat_tiet_kiem"),  # scan
    ]
    monkeypatch.setattr(sync, "find_pdf_urls", lambda key: urls)
    monkeypatch.setattr(sync, "layout_text", lambda url: "BẢNG   phí   cột A   cột B\n" + "z" * 60 if "Bieu-phi" in url else None)

    def _fetch(batch, key, *, links):
        results = {u: {"text": "BIỂU LÃI SUẤT " + "n" * 60} for u in batch if "LAI-SUAT" in u}
        return results, {}

    monkeypatch.setattr(sync, "fetch_batch", _fetch)
    records, unreadable = sync.build_pdf_records("key", NOW, set())
    by_id = {r["id"]: r for r in records}
    assert by_id["doc__bieu-phi-the-ghi-no"]["extraction"] == "layout"
    assert by_id["doc__lai-suat-tin-dung-2026"]["extraction"] == "flattened"
    assert [u["url"] for u in unreadable] == [urls[2][0]] and "scan" in unreadable[0]["reason"]


def test_write_kb_records_the_extraction_mode_for_pdfs(tmp_path, monkeypatch):
    kb = tmp_path / "data" / "msb_knowledge"
    monkeypatch.setattr(sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync, "KB_DIR", kb)
    monkeypatch.setattr(sync, "PAGES_DIR", kb / "pages")
    rec = {"id": "doc__x", "title": "X", "url": PDF_URL, "kind": "pdf", "category": "bieu_phi", "extraction": "layout",
           "fetched_at": NOW.isoformat(), "sha256": "abc", "body": "cột A   cột B"}
    sync.write_kb([rec], [], [], NOW)
    import json

    assert "extraction: layout" in (kb / "pages" / "doc__x.md").read_text(encoding="utf-8")
    assert json.loads((kb / "manifest.json").read_text(encoding="utf-8"))["pages"][0]["extraction"] == "layout"


# --- curated (hand-transcribed) decisions are watched, never overwritten ---------------------------

SCAN_URL = "https://www.msb.com.vn/msb-website/2026/04/QD-4144-bieu-lai-suat.pdf"
PDF_BYTES = b"%PDF-1.4 scan"


def _curated_kb(tmp_path, monkeypatch, sha=None):
    kb = tmp_path / "data" / "msb_knowledge"
    (kb / "curated").mkdir(parents=True)
    monkeypatch.setattr(sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync, "KB_DIR", kb)
    monkeypatch.setattr(sync, "PAGES_DIR", kb / "pages")
    monkeypatch.setattr(sync, "CURATED_DIR", kb / "curated")
    monkeypatch.setattr(sync, "REVIEWED_FILE", kb / "curated" / "reviewed.json")
    sha = sha or hashlib.sha256(PDF_BYTES).hexdigest()
    (kb / "curated" / "qd-4144.md").write_text(
        f'---\ntitle: "QĐ 4144"\nsource_url: {SCAN_URL}\nsource_sha256: {sha}\n---\n\n## Bảng\n\n| a |\n',
        encoding="utf-8",
    )
    return kb


def _unreadable(url):
    return {"url": url, "title": "t", "topic": "lai_suat_tiet_kiem", "reason": "PDF là bản scan (không có lớp chữ)"}


def test_download_pdf_only_fetches_msb_documents_and_real_pdfs(monkeypatch):
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(SCAN_URL, PDF_BYTES))
    assert sync.download_pdf(SCAN_URL) == PDF_BYTES
    assert sync.download_pdf("https://evil.com/x.pdf") is None
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(SCAN_URL, b"<html>"))
    assert sync.download_pdf(SCAN_URL) is None
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(SCAN_URL, PDF_BYTES, "https://evil.com/x.pdf"))
    assert sync.download_pdf(SCAN_URL) is None


def test_review_curated_marks_an_unchanged_pdf_current_and_removes_it_from_unreadable(tmp_path, monkeypatch):
    _curated_kb(tmp_path, monkeypatch)
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(SCAN_URL, PDF_BYTES))
    statuses, pending, unreviewed = sync.review_curated({SCAN_URL}, [_unreadable(SCAN_URL)])
    assert statuses == [{"id": "qd-4144", "url": SCAN_URL, "status": "current"}]
    assert pending == [] and unreviewed == []


@pytest.mark.parametrize(
    "scan_urls, body, expected",
    [
        ({SCAN_URL}, b"%PDF-1.4 replaced by MSB", "changed"),
        (set(), PDF_BYTES, "gone"),
        ({SCAN_URL}, None, "unchecked"),
    ],
)
def test_review_curated_flags_a_replaced_removed_or_unverifiable_pdf(tmp_path, monkeypatch, scan_urls, body, expected):
    _curated_kb(tmp_path, monkeypatch)
    if body is None:
        def _fail(*a, **k):
            raise sync.httpx.ConnectError("down")

        monkeypatch.setattr(sync.httpx, "get", _fail)
    else:
        monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(SCAN_URL, body))
    statuses, _, _ = sync.review_curated(scan_urls, [])
    assert statuses[0]["status"] == expected


def test_a_new_scan_nobody_transcribed_or_reviewed_is_reported_as_unreviewed(tmp_path, monkeypatch):
    kb = _curated_kb(tmp_path, monkeypatch)
    monkeypatch.setattr(sync.httpx, "get", _fake_get_factory(SCAN_URL, PDF_BYTES))
    known = "https://www.msb.com.vn/msb-website/2021/QD-6895-ngoai-te.pdf"
    new = "https://www.msb.com.vn/msb-website/2026/09/QD-9999-bieu-lai-suat-moi.pdf"
    (kb / "curated" / "reviewed.json").write_text(json.dumps({known: "ngoại tệ"}), encoding="utf-8")
    _, pending, unreviewed = sync.review_curated(
        {SCAN_URL, known, new}, [_unreadable(SCAN_URL), _unreadable(known), _unreadable(new)]
    )
    assert [u["url"] for u in pending] == [known, new]
    assert [u["url"] for u in unreviewed] == [new]


def test_write_kb_never_touches_the_curated_directory_and_records_the_review(tmp_path, monkeypatch):
    kb = _curated_kb(tmp_path, monkeypatch)
    (kb / "pages").mkdir()
    (kb / "pages" / "stale.md").write_text("old", encoding="utf-8")
    curated_file = kb / "curated" / "qd-4144.md"
    before = curated_file.read_text(encoding="utf-8")
    rec = {"id": "a", "title": "A", "url": BASE + "a/", "kind": "page", "category": "x",
           "fetched_at": NOW.isoformat(), "sha256": "h", "body": "b" * 120}
    review = [{"id": "qd-4144", "url": SCAN_URL, "status": "current"}]
    sync.write_kb([rec], [], [], NOW, review, [{"url": "u"}])
    assert not (kb / "pages" / "stale.md").exists()
    assert curated_file.read_text(encoding="utf-8") == before
    manifest = json.loads((kb / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["curated"] == review and manifest["unreviewed_scans"] == [{"url": "u"}]
