import re
import io
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import pdfplumber

from ..models import ExampleItem


# =========================
# 正規化ユーティリティ
# =========================

FULLWIDTH_ABC = str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"})

def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u00a0", " ")
    s = s.translate(FULLWIDTH_ABC)
    s = s.replace("：", ":").replace("／", "/")
    s = s.replace("−", "-").replace("ー", "-").replace("－", "-").replace("―", "-")
    return s.strip()


def _clean_rank(x: Optional[str]) -> Optional[str]:
    if not x:
        return None
    x = _norm(x).upper()
    return x if x in ("A", "B", "C") else None


# =========================
# タイトルからランク表記を除去
# =========================

RANK_IN_TITLE_RE = re.compile(
    r"(?:短答|短)\s*[: ]\s*[ABCＡ-Ｃ]|(?:論文|論)\s*[: ]\s*[ABCＡ-Ｃ]"
)

def clean_title(title: str) -> str:
    """
    例題タイトルから「短答:A 論文:C」等を除去
    また、冒頭の「-1」「-2」のような例題番号も除去
    """
    t = _norm(title)
    t = RANK_IN_TITLE_RE.sub("", t)
    # タイトル冒頭の「-数字」や「-数字 」（ハイフン + 数字）を削除
    t = re.sub(r"^[\-－]\s*\d+\s+", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


# =========================
# アウトライン（章・節）
# =========================

def _parse_outline(doc: fitz.Document):
    toc = doc.get_toc(simple=True) or []
    chapters = []

    chap_re = re.compile(r"第\s*(\d+)\s*章\s*(.*)")
    sec_re = re.compile(r"第\s*(\d+)\s*節\s*(.*)")

    current = None
    for _, title, page in toc:
        t = _norm(title)
        p = int(page)

        m = chap_re.search(t)
        if m:
            current = {
                "no": int(m.group(1)),
                "title": m.group(2).strip(),
                "start": p,
                "sections": [],
            }
            chapters.append(current)
            continue

        m = sec_re.search(t)
        if m and current:
            current["sections"].append({
                "no": int(m.group(1)),
                "title": m.group(2).strip(),
                "start": p,
            })

    chapters.sort(key=lambda x: x["start"])
    for c in chapters:
        c["sections"].sort(key=lambda x: x["start"])
    return chapters


def _find_chapter_section(chapters, page):
    chap = None
    for c in chapters:
        if c["start"] <= page:
            chap = c
        else:
            break

    if not chap:
        return None, None

    sec = None
    for s in chap["sections"]:
        if s["start"] <= page:
            sec = s
        else:
            break

    return chap, sec or {"no": 0, "title": ""}


# =========================
# 財務：目次からの抽出
# =========================

# 章タイトル抽出用の正規表現
# 例: "【第1章 現金預金】"
_CHAPTER_HEADER_RE = re.compile(
    r"[【[]\s*第\s*(?P<chapter_no>\d+)\s*章\s*(?P<chapter_title>[^】\]]+?)[】\]]"
)

# 目次行（例題目次）
# 例: "1 A C 現金過不足① ①-6"
# または: "1 Ａ Ｃ 現金過不足① ①-6"
# 形式: 例題番号 短答 論文 題目 テキスト参照
_TOC_LINE_RE = re.compile(
    r"^(?P<ex_no>\d+)\s+"
    r"(?P<rank_t>[ABCＡＢＣ])\s+"
    r"(?P<rank_r>[ABCＡＢＣ])\s+"
    r"(?P<title>.+?)\s+"
    r"(?P<page_ref>[①-⑩]\s*[-－]\s*\d+)",
    re.MULTILINE
)


def _extract_toc_map(pdf: pdfplumber.PDF, max_pages: int = 40) -> Tuple[Dict[str, Dict], Dict[int, str]]:
    """
    例題目次が前半にある前提で、最初の max_pages くらいから辞書を作る。
    key は "章番号-例題番号" の形式（例: "1-1", "2-3"）。
    
    Returns:
        (toc_dict, chapter_title_map): 例題情報の辞書と、章番号→章タイトルのマッピング
    """
    toc: Dict[str, Dict] = {}
    chapter_title_map: Dict[int, str] = {}
    current_chapter = 0

    for i in range(min(max_pages, len(pdf.pages))):
        text = pdf.pages[i].extract_text() or ""
        if not text:
            continue

        for line in text.splitlines():
            line_orig = line.strip()
            
            # 章ヘッダーの検索
            chapter_match = _CHAPTER_HEADER_RE.search(line_orig)
            if chapter_match:
                current_chapter = int(chapter_match.group("chapter_no"))
                chapter_title = chapter_match.group("chapter_title").strip()
                chapter_title = re.sub(r"\s+", " ", chapter_title).strip()
                if chapter_title:
                    chapter_title_map[current_chapter] = chapter_title
                continue
            
            # 例題行の検索（正規化前のテキストで）
            m = _TOC_LINE_RE.search(line_orig)
            if not m:
                continue
            
            if current_chapter == 0:
                continue  # 章が特定できていない場合はスキップ

            ex_no = int(m.group("ex_no"))
            ex_key = f"{current_chapter}-{ex_no}"
            
            rank_t = _clean_rank(m.group("rank_t"))
            rank_r = _clean_rank(m.group("rank_r"))
            
            # ページ参照の正規化
            page_ref_raw = m.group("page_ref")
            page_ref = _norm(page_ref_raw).replace(" ", "")
            
            title = _norm(m.group("title")).strip()
            
            toc[ex_key] = {
                "chapter_no": current_chapter,
                "example_no": ex_no,
                "rank_tanto": rank_t,
                "rank_ronbun": rank_r,
                "page_ref": page_ref,
                "title": title,
            }

    return toc, chapter_title_map


# =========================
# 財務：本文からの例題抽出
# =========================

EX_HEADER_RE = re.compile(
    r"(?:^|\n)\s*例題\s*(\d+)\s*([^\n]{1,80})",
    re.MULTILINE
)


def _split_blocks(text: str):
    hits = list(EX_HEADER_RE.finditer(text))
    blocks = []
    for i, m in enumerate(hits):
        s = m.start()
        e = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        blocks.append(text[s:e])
    return blocks


# =========================
# ページ下部番号
# =========================

_CIRCLED = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5, "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9, "⑩": 10}

PAGE_REF_RE = re.compile(r"([①-⑩]|\d+)\s*-\s*(\d+)")


def extract_page_ref(page: pdfplumber.page.Page):
    """
    下部の「①-23」「4-2」みたいなページ表記を拾う
    """
    h = page.height
    crop = page.crop((0, h * 0.85, page.width, h))
    txt = _norm(crop.extract_text() or "")

    m = PAGE_REF_RE.search(txt)
    if not m:
        return None

    g1 = m.group(1)
    g2 = m.group(2)

    # ★ここが今回の修正ポイント（dict.getのdefault評価罠を回避）
    if g1 in _CIRCLED:
        left = _CIRCLED[g1]
    else:
        left = int(g1)

    right = int(g2)
    return f"{left}-{right}"


# =========================
# Extractor
# =========================

class ZaimuExtractor:
    subject = "zaimu"

    def extract(self, pdf_bytes: bytes, subject_code: str, source_pdf: str) -> List[ExampleItem]:
        results: List[ExampleItem] = []

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chapters = _parse_outline(doc)
        doc.close()

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # 目次からランク情報を取得
            toc_map, chapter_title_map = _extract_toc_map(pdf, max_pages=40)

            for i, page in enumerate(pdf.pages):
                pdf_page = i + 1
                page_ref = extract_page_ref(page)

                text = _norm(page.extract_text() or "")
                blocks = _split_blocks(text)
                if not blocks:
                    continue

                chap, sec = _find_chapter_section(chapters, pdf_page)
                chap = chap or {"no": 0, "title": ""}
                sec = sec or {"no": 0, "title": ""}

                # 章タイトルは目次から優先的に取得
                chapter_title = chapter_title_map.get(chap["no"], chap["title"])

                for b in blocks:
                    m = EX_HEADER_RE.search(b)
                    if not m:
                        continue

                    # 本文から抽出した例題番号（目次がない場合のフォールバック用）
                    ex_no_from_text = int(m.group(1))
                    raw_title = m.group(2).strip()
                    title = clean_title(raw_title)

                    # 目次から情報を取得（例題番号、ランク、page_refなど）
                    # まず、本文から抽出した例題番号で検索を試みる
                    ex_key = f"{chap['no']}-{ex_no_from_text}"
                    toc_info = toc_map.get(ex_key, {})
                    
                    # 目次から例題番号を取得（あればそれを使用）
                    ex_no = toc_info.get("example_no", ex_no_from_text)
                    rank_t = toc_info.get("rank_tanto")
                    rank_r = toc_info.get("rank_ronbun")
                    
                    # 目次にpage_refがある場合はそれを使用
                    toc_page_ref = toc_info.get("page_ref")
                    if toc_page_ref:
                        page_ref = toc_page_ref
                    
                    # 目次からタイトルを取得（あればそれを使用、より正確な可能性がある）
                    toc_title = toc_info.get("title")
                    if toc_title:
                        title = toc_title

                    results.append(
                        ExampleItem(
                            subject=subject_code,
                            chapter_no=chap["no"],
                            chapter_title=chapter_title,
                            section_no=sec["no"],
                            section_title=sec["title"],
                            example_no=ex_no,
                            title=title,
                            rank=rank_r,  # 互換用：論文ランクを設定
                            rank_tanto=rank_t,
                            rank_ronbun=rank_r,
                            page_ref=page_ref,
                            pdf_page=pdf_page,
                            source_pdf=source_pdf,
                        )
                    )

        return results
