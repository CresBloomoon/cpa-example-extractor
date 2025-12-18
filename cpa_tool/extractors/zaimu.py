import re
import io
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber


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
    """
    t = _norm(title)
    t = RANK_IN_TITLE_RE.sub("", t)
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
# 財務：例題抽出
# =========================

EX_HEADER_RE = re.compile(
    r"(?:^|\n)\s*例題\s*(\d+)\s*([^\n]{1,80})",
    re.MULTILINE
)

RANK_TANTO_RE = re.compile(r"(?:短答|短)\s*[: ]\s*([ABCＡ-Ｃ])")
RANK_RONBUN_RE = re.compile(r"(?:論文|論)\s*[: ]\s*([ABCＡ-Ｃ])")


def _split_blocks(text: str):
    hits = list(EX_HEADER_RE.finditer(text))
    blocks = []
    for i, m in enumerate(hits):
        s = m.start()
        e = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        blocks.append(text[s:e])
    return blocks


def _extract_ranks(block: str):
    t = _norm(block)
    m1 = RANK_TANTO_RE.search(t)
    m2 = RANK_RONBUN_RE.search(t)
    return (
        _clean_rank(m1.group(1)) if m1 else None,
        _clean_rank(m2.group(1)) if m2 else None,
    )


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

    def extract(self, pdf_bytes: bytes, subject_code: str, source_pdf: str):
        results = []

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chapters = _parse_outline(doc)
        doc.close()

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
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

                for b in blocks:
                    m = EX_HEADER_RE.search(b)
                    if not m:
                        continue

                    ex_no = int(m.group(1))
                    raw_title = m.group(2).strip()
                    title = clean_title(raw_title)

                    rank_t, rank_r = _extract_ranks(b)

                    results.append({
                        "subject": "zaimu",
                        "chapter_no": chap["no"],
                        "chapter_title": chap["title"],
                        "section_no": sec["no"],
                        "section_title": sec["title"],
                        "example_no": ex_no,
                        "title": title,
                        "rank_tantou": rank_t,
                        "rank_ronbun": rank_r,
                        "rank_koukan": rank_r,
                        "page_ref": page_ref,
                        "pdf_page": pdf_page,
                        "source_pdf": source_pdf,
                    })

        return results
