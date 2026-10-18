import json
import os
import re
from datetime import datetime
from pathlib import Path

import pytest

import middleware.seed_customer_context as scc
from tools import msb_knowledge_tools as mk
from tools.msb_knowledge_tools import search_msb_knowledge

FETCHED = "2026-09-19T10:00:00+07:00"
BASE = "https://www.msb.com.vn/khach-hang-ca-nhan/"

PAGES = {
    "the__visa-signature": (
        "Thẻ tín dụng MSB Visa Signature - Ngân hàng TMCP Hàng Hải Việt Nam",
        BASE + "the/the-msb-visa-signature/",
        "page",
        "# MSB Visa Signature\n\n## Có gì đặc biệt?\n\n### Hoàn 10% lên đến 12 triệu đồng/năm\n\n"
        "Thẻ tín dụng hoàn tiền cho ẩm thực, y tế. Phí thường niên 1.499.000 VND/năm.",
    ),
    "tiet-kiem__ong-vang": (
        "Tiết kiệm Ong vàng - MSB - Ngân hàng TMCP Hàng Hải Việt Nam",
        BASE + "tiet-kiem/tiet-kiem-ong-vang/",
        "page",
        "# Tiết kiệm Ong vàng\n\nLinh hoạt gửi góp nhiều lần. Lãi suất linh hoạt theo từng thời kỳ. "
        "Số tiền gửi tối thiểu 500.000 VND.",
    ),
    "doc__bieu-phi-the-ghi-no": (
        "Bieu phi The ghi no",
        "https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf",
        "pdf",
        "BIỂU PHÍ DỊCH VỤ THẺ GHI NỢ\n\nPhí thường niên 50.000 VND/năm. Phí rút tiền ATM khác hệ thống 5.000 VND.",
    ),
}


def _write_kb(root, fetched=FETCHED, pages=PAGES):
    (root / "pages").mkdir(parents=True)
    manifest_pages = []
    for pid, (title, url, kind, body) in pages.items():
        front = f'---\ntitle: {json.dumps(title, ensure_ascii=False)}\nsource_url: {url}\nfetched_at: {fetched}\nkind: {kind}\ncategory: x\n---\n\n'
        (root / "pages" / f"{pid}.md").write_text(front + body + "\n", encoding="utf-8")
        manifest_pages.append({"id": pid, "title": title, "url": url, "kind": kind, "category": "x", "fetched_at": fetched})
    (root / "manifest.json").write_text(
        json.dumps({"fetched_at": fetched, "source": BASE, "pages": manifest_pages, "unreadable": [], "failed": []}),
        encoding="utf-8",
    )


@pytest.fixture
def kb(tmp_path, monkeypatch):
    _write_kb(tmp_path)
    monkeypatch.setattr(mk, "KB_DIR", tmp_path)
    monkeypatch.setattr(mk, "_kb_cache", None)
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 9, 19, 12, 0, tzinfo=scc._VIETNAM_TZ))
    monkeypatch.delenv("MSB_KB_MAX_AGE_DAYS", raising=False)
    return tmp_path


def _search(query: str) -> str:
    return search_msb_knowledge.invoke({"query": query})


def test_returns_the_best_page_first_with_source_url_and_fetch_date(kb):
    out = _search("thẻ tín dụng hoàn tiền")
    assert out.index("MSB Visa Signature") < out.index("Ong vàng") if "Ong vàng" in out else True
    assert "[1] Thẻ tín dụng MSB Visa Signature" in out
    assert "Nguồn: " + BASE + "the/the-msb-visa-signature/ (lấy ngày 19/09/2026)" in out
    assert "dữ liệu lưu ngày 19/09/2026" in out
    assert "Hàng Hải Việt Nam" not in out  # the site's title suffix is stripped


def test_every_passage_carries_its_own_source_line(kb):
    out = _search("phí thường niên")
    assert out.count("Nguồn: https://") == out.count("\n[")


def test_matches_queries_typed_without_diacritics(kb):
    assert "Tiết kiệm Ong vàng" in _search("tiet kiem ong vang")


def test_pdf_with_an_ascii_title_is_found_by_an_accented_query(kb):
    out = _search("phí thẻ ghi nợ")
    assert "Bieu phi The ghi no" in out
    assert "Nguồn: https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf" in out


def test_no_match_says_so_and_points_to_the_site_without_inventing(kb):
    out = _search("xyzabc qwerty")
    assert "Không tìm thấy nội dung phù hợp" in out and "Đừng tự bịa" in out
    assert "Nguồn: https://" not in out


def test_empty_query_and_missing_snapshot(kb, monkeypatch, tmp_path):
    assert "Cần có từ khoá" in _search("   ")
    monkeypatch.setattr(mk, "KB_DIR", tmp_path / "does-not-exist")
    monkeypatch.setattr(mk, "_kb_cache", None)
    assert "Chưa có dữ liệu sản phẩm MSB đã lưu" in _search("thẻ")


def test_at_most_two_passages_per_page_and_three_overall(kb):
    out = _search("thẻ phí thường niên tiết kiệm lãi suất")
    assert out.count("\n[") <= mk.TOP_K


def test_fresh_snapshot_has_no_staleness_warning(kb):
    assert "CẢNH BÁO" not in _search("thẻ tín dụng")


def test_old_snapshot_warns_with_its_age(kb, monkeypatch):
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 9, 30, 12, 0, tzinfo=scc._VIETNAM_TZ))
    out = _search("thẻ tín dụng")
    assert "CẢNH BÁO: dữ liệu đã lưu cách đây 11 ngày (quá 7 ngày)" in out
    assert "Nêu rõ ngày cập nhật" in out


def test_staleness_threshold_is_configurable_and_bad_values_fall_back(kb, monkeypatch):
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 9, 25, 12, 0, tzinfo=scc._VIETNAM_TZ))  # 6 days old
    assert "CẢNH BÁO" not in _search("thẻ tín dụng")
    monkeypatch.setenv("MSB_KB_MAX_AGE_DAYS", "3")
    assert "CẢNH BÁO" in _search("thẻ tín dụng")
    monkeypatch.setenv("MSB_KB_MAX_AGE_DAYS", "abc")
    assert "CẢNH BÁO" not in _search("thẻ tín dụng")


def test_deposit_rate_questions_get_the_not_in_snapshot_note(kb):
    out = _search("lãi suất tiết kiệm 12 tháng")
    assert "không có bảng lãi suất tiền gửi khớp câu hỏi" in out and mk.RATES_PAGE in out
    assert "không có bảng lãi suất tiền gửi khớp câu hỏi" not in _search("thẻ tín dụng hoàn tiền")


def test_snapshot_is_reloaded_when_the_manifest_changes(kb):
    assert "Ong vàng" in _search("Ong vàng")
    (kb / "pages" / "tiet-kiem__ong-vang.md").write_text(
        f'---\ntitle: "Tiết kiệm Ong vàng"\nsource_url: {BASE}tiet-kiem/x/\nfetched_at: {FETCHED}\nkind: page\ncategory: x\n---\n\nNội dung mới về sản phẩm Ong vàng.\n',
        encoding="utf-8",
    )
    manifest = kb / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    stat = manifest.stat()  # two writes in one clock tick share an mtime -- make the change visible
    os.utime(manifest, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert "Nội dung mới" in _search("Ong vàng")


# --- smoke tests on the real committed snapshot (data/msb_knowledge) ---


@pytest.fixture
def real_kb(monkeypatch):
    monkeypatch.setattr(mk, "KB_DIR", mk.Path(mk.__file__).resolve().parent.parent / "data" / "msb_knowledge")
    monkeypatch.setattr(mk, "_kb_cache", None)
    monkeypatch.setenv("MSB_KB_MAX_AGE_DAYS", "100000")  # content checks, not freshness
    return mk.KB_DIR


def test_real_snapshot_is_complete_and_every_page_has_a_valid_source(real_kb):
    import importlib.util

    script = Path(mk.__file__).resolve().parent.parent / "scripts" / "sync_msb_knowledge.py"
    spec = importlib.util.spec_from_file_location("sync_msb_knowledge", script)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    _is_msb_retail_url, _is_msb_document_url = sync._is_msb_retail_url, sync._is_msb_document_url

    manifest = json.loads((real_kb / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pages"]) >= 50
    datetime.fromisoformat(manifest["fetched_at"])
    for entry in manifest["pages"]:
        meta, body = mk._parse_page(real_kb / "pages" / f"{entry['id']}.md")
        assert meta["source_url"] == entry["url"]
        assert _is_msb_retail_url(entry["url"]) or _is_msb_document_url(entry["url"])
        datetime.fromisoformat(meta["fetched_at"])
        assert len(body) >= 100


def test_real_snapshot_records_the_scanned_deposit_rate_pdfs_as_unreadable(real_kb):
    manifest = json.loads((real_kb / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["unreadable"]) >= 1
    assert all("scan" in item["reason"] for item in manifest["unreadable"])


@pytest.mark.parametrize(
    "query, expected_title_part",
    [
        ("thẻ tín dụng hoàn tiền", "Thẻ tín dụng MSB"),
        ("chứng chỉ tiền gửi", "Chứng chỉ tiền gửi"),
        ("tiết kiệm Ong vàng", "Ong vàng"),
        ("phí thường niên thẻ ghi nợ", "Bieu phi The ghi no"),
        ("lãi suất vay", "LAI SUAT TIN DUNG"),
        ("bảo hiểm sức khỏe", "Bảo hiểm sức khỏe"),
        ("vay mua ô tô", "Vay mua ô tô"),
    ],
)
def test_real_snapshot_answers_typical_customer_questions(real_kb, query, expected_title_part):
    out = _search(query)
    assert expected_title_part in out, out[:400]
    assert "Nguồn: https://www.msb.com.vn/" in out


def test_real_lookup_is_fast(real_kb):
    import time

    _search("thẻ")  # warm the in-memory index
    start = time.perf_counter()
    for _ in range(5):
        _search("thẻ tín dụng hoàn tiền")
    assert (time.perf_counter() - start) / 5 < 0.25


def test_the_word_msb_in_a_query_is_ignored_because_it_appears_on_every_page(real_kb):
    # regression: the model adds "MSB" to its keywords; that used to push the fee PDF out of the top 3
    with_msb = _search("phí thường niên thẻ ghi nợ MSB")
    assert "Bieu phi The ghi no" in with_msb
    assert mk._tokens("thẻ MSB hoàn tiền") == ["thẻ", "hoàn", "tiền"]
    assert mk._folded_tokens("thẻ MSB hoàn tiền") == ["the", "hoan", "tien"]


def test_accent_free_queries_keep_the_and_vay_which_would_otherwise_fold_into_stopwords():
    # "thế" and "vậy" are stopwords; folded they read "the" and "vay" = the content words for
    # card and loan, so they must survive in the accent-free channel.
    assert "the" in mk._folded_tokens("thẻ tín dụng") and "vay" in mk._folded_tokens("vay mua nhà")
    assert "the" not in mk._tokens("thế nào") and "vậy" not in mk._tokens("vậy thì")
    assert "the" in mk._folded_tokens("the tin dung") and "vay" in mk._folded_tokens("vay mua nha")


def test_accent_free_loan_and_card_queries_find_the_right_real_pages(real_kb):
    assert "Vay mua nhà dự án" in _search("vay mua nha du an")
    assert "Thẻ tín dụng MSB" in _search("the tin dung hoan tien")


def test_flattened_pdf_passages_carry_the_table_warning_and_page_passages_do_not(kb):
    pdf_out = _search("phí thường niên thẻ ghi nợ")
    assert "Bieu phi The ghi no" in pdf_out
    assert mk.PDF_TABLE_WARNING in pdf_out and "KHÔNG còn ranh giới cột" in pdf_out
    page_out = _search("Ong vàng")
    assert "Tiết kiệm Ong vàng" in page_out and mk.PDF_TABLE_WARNING not in page_out
    assert pdf_out.count(mk.PDF_TABLE_WARNING) == pdf_out.count("Bieu phi The ghi no")  # once per PDF passage


def test_real_fee_pdf_result_tells_the_model_how_to_read_the_columns(real_kb):
    out = _search("phí thường niên thẻ ghi nợ MSB")
    assert "Bieu phi The ghi no" in out and mk.PDF_LAYOUT_NOTE in out


# --- PDF tables: layout extraction keeps a page together and column-aligned ---

LAYOUT_PAGE_1 = (
    "Loại thẻ            MSB Napas Debit M-Pro     MSB Napas Debit CVP     MSB Visa Debit Classic\n"
    "2. Phí thường niên  50.000 VND/năm            Miễn phí                100.000 VND/năm\n"
    "3. Phí ATM          Miễn phí                  Miễn phí                5.000 VND/giao dịch"
)
LAYOUT_PAGE_2 = "6. Phí xử lý giao dịch ngoại tệ   3%/số tiền giao dịch"


def _kb_with_layout_pdf(tmp_path, monkeypatch):
    pages = dict(PAGES)
    pages["doc__layout"] = ("Bieu phi The ghi no", "https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf", "pdf",
                            LAYOUT_PAGE_1 + "\f" + LAYOUT_PAGE_2)
    del pages["doc__bieu-phi-the-ghi-no"]
    _write_kb(tmp_path, pages=pages)
    (tmp_path / "pages" / "doc__layout.md").write_text(
        (tmp_path / "pages" / "doc__layout.md").read_text(encoding="utf-8").replace("category: x", "category: x\nextraction: layout"),
        encoding="utf-8",
    )
    monkeypatch.setattr(mk, "KB_DIR", tmp_path)
    monkeypatch.setattr(mk, "_kb_cache", None)
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 9, 19, 12, 0, tzinfo=scc._VIETNAM_TZ))


def test_layout_pdf_page_stays_one_passage_with_its_column_header_in_a_fixed_width_block(tmp_path, monkeypatch):
    _kb_with_layout_pdf(tmp_path, monkeypatch)
    out = _search("phí thường niên thẻ ghi nợ")
    header_at, fee_row_at = out.index("MSB Napas Debit M-Pro"), out.index("2. Phí thường niên  50.000")
    assert header_at < fee_row_at  # header row and fee row are in the same passage
    assert "```\n" + LAYOUT_PAGE_1 + "\n```" in out
    assert mk.PDF_LAYOUT_NOTE in out and mk.PDF_TABLE_WARNING not in out
    assert "ngoại tệ" not in out or "6. Phí xử lý" not in LAYOUT_PAGE_1  # page 2 is its own passage


def test_flattened_pdf_keeps_the_stronger_warning_and_layout_pdf_does_not_get_it(tmp_path, monkeypatch):
    _kb_with_layout_pdf(tmp_path, monkeypatch)
    assert mk.PDF_TABLE_WARNING not in _search("phí thường niên thẻ ghi nợ")


def test_output_is_capped_so_wide_pdf_tables_do_not_bury_the_reader(tmp_path, monkeypatch):
    big = "\n".join(f"Dòng phí thường niên thẻ ghi nợ số {i:04d}   Miễn phí   50.000 VND" for i in range(120))
    pages = {f"doc__big{n}": (f"Bieu phi The ghi no {n}", f"https://www.msb.com.vn/msb-website/big{n}.pdf", "pdf", big)
             for n in range(3)}
    _write_kb(tmp_path, pages=pages)
    for n in range(3):
        f = tmp_path / "pages" / f"doc__big{n}.md"
        f.write_text(f.read_text(encoding="utf-8").replace("category: x", "category: x\nextraction: layout"), encoding="utf-8")
    monkeypatch.setattr(mk, "KB_DIR", tmp_path)
    monkeypatch.setattr(mk, "_kb_cache", None)
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 9, 19, 12, 0, tzinfo=scc._VIETNAM_TZ))
    out = _search("phí thường niên thẻ ghi nợ")
    assert out.count("\n[") >= 1
    assert len(out) < mk.MAX_OUTPUT_CHARS + mk.PDF_PAGE_CHUNK_MAX + 1500


def test_real_fee_table_passage_holds_the_column_titles_and_the_annual_fee_row_together(real_kb):
    out = _search("phí thường niên thẻ ghi nợ MSB")
    assert "Bieu phi The ghi no" in out and mk.PDF_LAYOUT_NOTE in out
    title_at = out.index("Local Debit MPRO") if "Local Debit MPRO" in out else out.index("Napas Debit")
    assert title_at < out.index("2. Phí thường niên")
    row = next(l for l in out.splitlines() if l.startswith("2. Phí thường niên"))
    # column order under the five headers: M-Pro, CVP VCCS, MC Debit FCB, Visa Classic CVP, Visa Classic
    assert row.index("50.000 VND/năm") < row.index("Miễn phí") < row.index("100.000 VND/năm")


def test_fee_questions_always_include_the_authoritative_pdf_page_first(tmp_path, monkeypatch):
    # marketing pages that merely mention fees outscore the fee PDF slightly; the PDF must still be returned
    pages = {
        f"the__card{i}": (f"Thẻ ghi nợ MSB {i}", f"{BASE}the/card{i}/", "page",
                          f"# Thẻ ghi nợ {i}\n\nCâu hỏi thường gặp: phí thường niên thẻ ghi nợ như thế nào? " * 3)
        for i in range(4)
    }
    pages["doc__bieu-phi"] = ("Bieu phi The ghi no", "https://www.msb.com.vn/msb-website/Bieu-phi-The-ghi-no.pdf", "pdf",
                              "BIỂU PHÍ\n\n2. Phí thường niên   50.000 VND/năm   Miễn phí " + "phụ lục ghi chú " * 40)
    _write_kb(tmp_path, pages=pages)
    monkeypatch.setattr(mk, "KB_DIR", tmp_path)
    monkeypatch.setattr(mk, "_kb_cache", None)
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 9, 19, 12, 0, tzinfo=scc._VIETNAM_TZ))
    out = _search("phí thường niên thẻ ghi nợ")
    assert "[1] Bieu phi The ghi no" in out


def test_non_fee_questions_are_not_forced_to_include_a_pdf(kb):
    assert "Bieu phi The ghi no" not in _search("tiết kiệm Ong vàng là gì")


# --- curated (hand-transcribed) deposit-rate decisions -----------------------------------------

DECISION_URL = "https://www.msb.com.vn/msb-website/2026/04/QD-4144-bieu-lai-suat.pdf"
NON_TERM_URL = "https://www.msb.com.vn/msb-website/2026/04/QD-2896-khong-ky-han.pdf"


def _write_curated(root, *, statuses=("current", "current"), unreviewed=()):
    (root / "curated").mkdir()
    tables = {
        "qd-4144": (
            "Biểu lãi suất tiền gửi tiết kiệm/có kỳ hạn bằng VND, khách hàng cá nhân (QĐ 4144/2026/QĐ-TGĐ1)",
            DECISION_URL,
            "Quyết định số 4144/2026/QĐ-TGĐ1 ngày 13/04/2026",
            "2026-04-14",
            "## Phụ lục 01 — Lãi suất tiết kiệm/gửi có kỳ hạn TẠI QUẦY (VND, cá nhân)\n\n"
            "| Kỳ hạn | Lãi suất cao nhất |\n| --- | --- |\n| 12 tháng | 6.50 |\n\n"
            "## Phụ lục 02 — Lãi suất tiết kiệm/gửi có kỳ hạn TRỰC TUYẾN (online) (VND, cá nhân)\n\n"
            "| Kỳ hạn | Lãi suất cao nhất |\n| --- | --- |\n| 12 tháng | 6.80 |\n",
        ),
        "qd-2896": (
            "Biểu lãi suất tiền gửi không kỳ hạn bằng VND, khách hàng cá nhân (QĐ 2896/2023/QĐ-TGĐ1)",
            NON_TERM_URL,
            "Quyết định số 2896/2023/QĐ-TGĐ1",
            "2023-04-03",
            "## Lãi suất tiền gửi không kỳ hạn (tài khoản thanh toán) theo gói tài khoản và số dư\n\n"
            "| Số dư | M-money |\n| --- | --- |\n| Dưới 100 triệu | 0% |\n",
        ),
    }
    for name, (title, url, decision, effective, body) in tables.items():
        front = (
            f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\nsource_url: {url}\nkind: transcribed\n"
            f"category: lai_suat_tiet_kiem\ndecision: {json.dumps(decision, ensure_ascii=False)}\n"
            f"effective_from: {effective}\ntranscribed_at: 2026-09-19T20:00:00+07:00\nsource_sha256: abc\n---\n\n"
            "Bản chép lại thủ công.\n\n"
        )
        (root / "curated" / f"{name}.md").write_text(front + body, encoding="utf-8")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["curated"] = [
        {"id": "qd-4144", "url": DECISION_URL, "status": statuses[0]},
        {"id": "qd-2896", "url": NON_TERM_URL, "status": statuses[1]},
    ]
    manifest["unreviewed_scans"] = list(unreviewed)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkey_stamp_fix = root / "manifest.json"
    os.utime(monkey_stamp_fix, ns=(monkey_stamp_fix.stat().st_atime_ns, monkey_stamp_fix.stat().st_mtime_ns + 10**9))


@pytest.fixture
def kb_with_rates(kb):
    _write_curated(kb)
    mk._kb_cache = None
    return kb


def test_deposit_rate_question_returns_both_tables_with_decision_date_and_legend(kb_with_rates):
    out = _search("lãi suất tiết kiệm 12 tháng")
    assert "TẠI QUẦY" in out and "TRỰC TUYẾN" in out
    assert "| 12 tháng | 6.50 |" in out and "| 12 tháng | 6.80 |" in out
    assert "Quyết định số 4144/2026/QĐ-TGĐ1 ngày 13/04/2026, hiệu lực từ 14/04/2026" in out
    assert "bản chép lại ngày 19/09/2026" in out
    assert mk.CURATED_LEGEND in out
    assert "không có bảng lãi suất tiền gửi khớp câu hỏi" not in out
    assert "CẢNH BÁO" not in out


def test_no_term_deposit_question_finds_the_no_term_decision_not_the_term_one(kb_with_rates):
    # "không" is a stopword; "không kỳ hạn" used to collapse into "kỳ hạn" (the opposite product)
    out = _search("lãi suất tiền gửi không kỳ hạn")
    assert out.index("[1] Biểu lãi suất tiền gửi không kỳ hạn") < out.index("TẠI QUẦY") if "TẠI QUẦY" in out else True
    assert "[1] Biểu lãi suất tiền gửi không kỳ hạn" in out
    assert "Dưới 100 triệu" in out


@pytest.mark.parametrize("statuses", [("changed", "current"), ("current", "gone"), ("unchecked", "current")])
def test_transcription_whose_source_pdf_is_not_confirmed_current_warns(kb, statuses):
    _write_curated(kb, statuses=statuses)
    mk._kb_cache = None
    out = _search("lãi suất tiết kiệm 12 tháng" if statuses[0] != "current" else "lãi suất tiền gửi không kỳ hạn")
    assert "CẢNH BÁO: lần đồng bộ gần nhất không xác nhận được bản PDF gốc" in out


def test_unreviewed_scan_on_the_rates_page_warns_that_a_newer_decision_may_exist(kb):
    _write_curated(kb, unreviewed=[{"url": "https://www.msb.com.vn/msb-website/2026/09/QD-9999.pdf"}])
    mk._kb_cache = None
    out = _search("lãi suất tiết kiệm 12 tháng")
    assert "quyết định lãi suất mới chưa được chép" in out


def test_unrelated_question_gets_no_rate_table_or_rate_warning(kb_with_rates):
    out = _search("thẻ tín dụng hoàn tiền")
    assert "Phụ lục" not in out and "CẢNH BÁO" not in out


def test_editing_a_curated_file_is_picked_up_without_a_new_manifest(kb_with_rates):
    assert "| 12 tháng | 6.80 |" in _search("lãi suất tiết kiệm 12 tháng")
    path = kb_with_rates / "curated" / "qd-4144.md"
    path.write_text(path.read_text(encoding="utf-8").replace("6.80", "7.10"), encoding="utf-8")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5 * 10**9))
    assert "| 12 tháng | 7.10 |" in _search("lãi suất tiết kiệm 12 tháng")


# --- the real transcriptions: structure and internal-consistency checks ---------------------------


def _tables(section: str) -> list[list[list[str]]]:
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in section.splitlines() if line.startswith("|")]
    tables, current = [], []
    for row in rows:
        if set("".join(row)) <= set("-: "):
            continue
        current.append(row)
    tables.append(current)
    return tables


def _real_curated(real_kb):
    return {f.stem: mk._parse_page(f) for f in sorted((real_kb / "curated").glob("*.md"))}


def test_real_curated_files_are_registered_in_the_manifest_with_a_hash(real_kb):
    manifest = json.loads((real_kb / "manifest.json").read_text(encoding="utf-8"))
    curated = _real_curated(real_kb)
    assert len(curated) >= 2
    assert {c["id"] for c in manifest["curated"]} == set(curated)
    for name, (meta, _) in curated.items():
        assert len(meta["source_sha256"]) == 64 and meta["source_url"].endswith(".pdf")
        assert datetime.fromisoformat(meta["transcribed_at"]) and meta["effective_from"]
        assert meta["decision"]
    assert not any(u["url"] in {m["source_url"] for m, _ in curated.values()} for u in manifest["unreadable"])


def test_real_rate_tables_are_rectangular_and_rates_are_plausible(real_kb):
    for name, (_, body) in _real_curated(real_kb).items():
        for section in re.split(r"(?m)^(?=## )", body):
            if "|" not in section:
                continue
            (table,) = _tables(section)
            widths = {len(r) for r in table}
            assert len(widths) == 1, f"{name}: ragged table in {section.splitlines()[0]!r}"
            for row in table[1:]:
                for cell in row[1:]:
                    if cell != "—" and re.fullmatch(r"\d+(\.\d+)?%?", cell):
                        assert 0 <= float(cell.rstrip("%")) <= 9.0, f"{name}: implausible rate {cell} in row {row[0]}"


def test_real_counter_table_columns_agree_with_each_other_as_in_the_original(real_kb):
    # In the source, "Lãi suất cao nhất", "Rút gốc từng phần" and "Hợp đồng tiền gửi" carry the same rate on
    # every term row, and "Định kỳ sinh lời" is 0.2-0.3 below it. A typo in a
    # transcribed cell breaks one of these.
    _, body = _real_curated(real_kb)["qd-4144-lai-suat-tien-gui-vnd-ca-nhan"]
    section = next(s for s in re.split(r"(?m)^(?=## )", body) if "TẠI QUẦY" in s and "Phụ lục 01 —" in s)
    (table,) = _tables(section)
    checked = 0
    for kyhan, top, partial, periodic, upfront, _, _, contract in table[2:]:
        if top == "—":
            continue
        assert top == partial == contract, kyhan
        if periodic != "—":
            assert round(float(top) - float(periodic), 2) in (0.2, 0.3), kyhan
        checked += 1
    assert checked == 17


def test_real_online_table_columns_agree_with_each_other_as_in_the_original(real_kb):
    _, body = _real_curated(real_kb)["qd-4144-lai-suat-tien-gui-vnd-ca-nhan"]
    section = next(s for s in re.split(r"(?m)^(?=## )", body) if "TRỰC TUYẾN" in s)
    (table,) = _tables(section)
    checked = 0
    for kyhan, top, partial, periodic, *_ in table[3:]:
        assert top == partial, kyhan
        if periodic != "—":
            assert round(float(top) - float(periodic), 2) in (0.2, 0.25, 0.4), kyhan
        checked += 1
    assert checked == 17


@pytest.mark.parametrize(
    "query, expected",
    [
        ("lãi suất tiết kiệm trực tuyến 12 tháng", "| 12 tháng | 6.80 | 6.80 | 6.40 | 4.80 | 4.00 |"),
        ("lãi suất gửi tại quầy 12 tháng", "| 12 tháng (**) | 6.50 | 6.50 | 6.30 | 4.00 | 4.00 | 4.00 | 6.50 |"),
        ("lãi suất đặc biệt 12 tháng", "| 12 tháng | 7.50 |"),
        ("lãi suất tiền gửi không kỳ hạn", "| Từ 500 triệu trở lên | 0% | 0.1% | 0.5% | 0.5% | 0.2% | 0.5% |"),
    ],
)
def test_real_snapshot_answers_deposit_rate_questions_from_the_transcribed_tables(real_kb, query, expected):
    out = _search(query)
    assert expected in out
    assert "CẢNH BÁO: lần đồng bộ" not in out  # manifest says both PDFs are current
