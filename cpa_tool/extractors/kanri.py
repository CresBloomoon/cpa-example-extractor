# cpa_tool/extractors/kanri.py
from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

import pdfplumber

from ..models import ExampleItem


def _normalize_text(s: str) -> str:
    """テキストを正規化（全角スペース、記号など）"""
    if not s:
        return ""
    s = s.replace("\u3000", " ").replace("\u00a0", " ")
    # 全角ABCを半角に変換
    s = s.translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"}))
    # 全角コロンを半角に
    s = s.replace("：", ":")
    return s.strip()


def _normalize_rank(rank: Optional[str]) -> Optional[str]:
    """ランクを正規化（全角ABCを半角に変換、大文字化）"""
    if not rank:
        return None
    rank = rank.strip()
    # 全角ABCを半角に変換
    rank = rank.translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"}))
    rank = rank.upper()
    return rank if rank in ("A", "B", "C") else None


def _normalize_page_ref(s: str) -> Optional[str]:
    s = _normalize_text(s)
    if not s:
        return None
    s = re.sub(r"\s+", "", s)
    m = re.search(r"([①-⑳])[-－]?(\d+)", s)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def _clean_title(s: str) -> str:
    """
    title の先頭に混ざる「- 1」「－2」みたいなのを消す
    例: "- 1 材料副費の処理" -> "材料副費の処理"
    """
    s = _normalize_text(s)
    s = re.sub(r"^[\-－]\s*\d+\s*", "", s)
    return s.strip()


# ===== 目次行（例題目次） =====
# 例: "３－１ Ａ-Ｂ 材料副費の処理 ③- 7"
# 全角ABCにも対応
_TOC_LINE_RE = re.compile(
    r"(?P<ex_left>\d+)\s*[－\-]\s*(?P<ex_right>\d+)\s+"
    r"(?P<rank_t>[ABCＡＢＣ])\s*[-－]\s*(?P<rank_r>[ABCＡＢＣ])\s+"
    r"(?P<title>.+?)\s+"
    r"(?P<page_ref>[①-⑳]\s*[-－]\s*\d+)"
)

# ===== 本文の例題ヘッダ =====
# 例: "例題３－１ 材料副費の処理"
# ランクは目次から取得するため、本文からは抽出しない
_EX_HEADER_RE = re.compile(
    r"例題\s*(?P<ex_left>\d+)\s*[－\-]\s*(?P<ex_right>\d+)\s+"
    r"(?P<title>.+?)(?:\s|$)"
)

_BOTTOM_PAGE_RE = re.compile(r"－\s*(?P<page_ref>[①-⑳]\s*[－\-]\s*\d+)\s*－")


# 章タイトル抽出用の正規表現
# 例: "【第3章 材料費】" または "第3章 材料費"
# 全角・半角のブラケット、スペースに対応
_CHAPTER_HEADER_RE = re.compile(
    r"[【[]\s*第\s*(?P<chapter_no>\d+)\s*章\s*(?P<chapter_title>[^】\]]+?)[】\]]"
)

def _extract_toc_map(pdf: pdfplumber.PDF, max_pages: int = 40) -> Tuple[Dict[str, Dict[str, str]], Dict[int, str]]:
    """
    例題目次が前半にある前提で、最初の max_pages くらいから辞書を作る。
    key は "3-1" のようなフル番号。
    
    Returns:
        (toc_dict, chapter_title_map): 例題情報の辞書と、章番号→章タイトルのマッピング
    """
    toc: Dict[str, Dict[str, str]] = {}
    chapter_title_map: Dict[int, str] = {}

    for i in range(min(max_pages, len(pdf.pages))):
        text = _normalize_text(pdf.pages[i].extract_text() or "")
        if not text:
            continue

        for line in text.splitlines():
            line_orig = line.strip()  # 正規化する前に章ヘッダーを検索
            
            # 章ヘッダーの検索（例: "【第3章 材料費】"）
            # 正規化前のテキストで検索（全角ブラケットを保持）
            chapter_match = _CHAPTER_HEADER_RE.search(line_orig)
            if chapter_match:
                chapter_no = int(chapter_match.group("chapter_no"))
                chapter_title = chapter_match.group("chapter_title").strip()
                # 余分な空白や改行を削除
                chapter_title = re.sub(r"\s+", " ", chapter_title).strip()
                if chapter_title:
                    chapter_title_map[chapter_no] = chapter_title
                continue
            
            # 正規化したテキストで例題行を検索
            line_n = _normalize_text(line)
            
            # 例題行の検索
            m = _TOC_LINE_RE.search(line_n)
            if not m:
                continue

            left = int(m.group("ex_left"))
            right = int(m.group("ex_right"))
            ex_full = f"{left}-{right}"

            # 目次のランクも正規化
            rank_t_toc = _normalize_rank(m.group("rank_t"))
            rank_r_toc = _normalize_rank(m.group("rank_r"))
            
            toc[ex_full] = {
                "rank_tanto": rank_t_toc,
                "rank_ronbun": rank_r_toc,
                "page_ref": _normalize_page_ref(m.group("page_ref")) or "",
                "title_hint": _normalize_text(m.group("title")),
                "chapter_no": str(left),
                "example_no": str(right),
            }

    return toc, chapter_title_map


def _extract_bottom_page_ref(page: pdfplumber.page.Page) -> Optional[str]:
    t = _normalize_text(page.extract_text() or "")
    if not t:
        return None
    m = _BOTTOM_PAGE_RE.search(t)
    if not m:
        return None
    return _normalize_page_ref(m.group("page_ref"))


class KanriExtractor:
    """
    管理会計 extractor
    - 例題ヒット
    - タイトル抽出
    - ランク抽出（短答/論文）
    - テキストページ番号抽出（page_ref）
    """

    def extract(self, pdf_bytes: bytes, subject_code: str, source_pdf: str) -> List[ExampleItem]:
        results: List[ExampleItem] = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            toc_map, chapter_title_map = _extract_toc_map(pdf, max_pages=40)

            for idx, page in enumerate(pdf.pages, start=1):
                text = _normalize_text(page.extract_text() or "")
                if not text:
                    continue

                # 例題ヘッダの検索（複数行にまたがる可能性を考慮）
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    line_n = _normalize_text(line)
                    
                    # 例題番号のマッチを確認
                    m = _EX_HEADER_RE.search(line_n)
                    if not m:
                        continue

                    left = int(m.group("ex_left"))
                    right = int(m.group("ex_right"))
                    ex_full = f"{left}-{right}"

                    raw_title = _normalize_text(m.group("title"))
                    title = _clean_title(raw_title)

                    # ランクは目次から取得（短答-論文の順、例: A-B → 短答A, 論文B）
                    toc = toc_map.get(ex_full, {})
                    rank_t = _normalize_rank(toc.get("rank_tanto"))
                    rank_r = _normalize_rank(toc.get("rank_ronbun"))

                    # 章タイトルを目次から取得
                    chapter_title = chapter_title_map.get(left, "")

                    page_ref = toc.get("page_ref") or None
                    if not page_ref:
                        page_ref = _extract_bottom_page_ref(page)

                    results.append(
                        ExampleItem(
                            subject=subject_code,
                            chapter_no=left,
                            chapter_title=chapter_title,
                            section_no=0,  # 管理会計では節は使わない
                            section_title="",
                            example_no=right,
                            title=title,
                            rank=rank_r,  # 互換用：論文ランクを設定
                            rank_tanto=rank_t,
                            rank_ronbun=rank_r,
                            page_ref=page_ref,
                            pdf_page=idx,
                            source_pdf=source_pdf,
                        )
                    )

        return results
