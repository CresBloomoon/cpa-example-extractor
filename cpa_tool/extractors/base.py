from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, List

import fitz

from ..models import ExampleItem
from ..outline import parse_outline, find_chapter_section
from ..utils import normalize_dashes, normalize_rank


@dataclass
class FoundExample:
    example_no: int
    title: str
    rank_tanto: Optional[str]
    rank_ronbun: Optional[str]


class BaseExtractor:
    """
    科目別抽出器の共通基盤
    - iter_examples_on_page: ページテキストから例題候補を抽出
    - extract_page_ref: ページ番号表記を拾う（科目別正規表現）
    """

    EXAMPLE_PATTERNS: List[re.Pattern] = []
    PAGE_REF_PATTERNS: List[re.Pattern] = []

    def extract_page_ref(self, text: str) -> Optional[str]:
        for pat in self.PAGE_REF_PATTERNS:
            m = pat.search(text)
            if m:
                head = m.group("head")
                section = m.group("section")
                pageno = m.group("pageno")
                return f"{head}{section}-{pageno}"
        return None

    def iter_examples_on_page(self, text: str) -> Iterable[FoundExample]:
        for pat in self.EXAMPLE_PATTERNS:
            for m in pat.finditer(text):
                ex_no = int(m.group("num"))
                title = re.sub(r"\s+", " ", (m.group("title") or "").strip())

                rank_tanto = m.groupdict().get("rank_tanto")
                rank_ronbun = m.groupdict().get("rank_ronbun")
                rank = m.groupdict().get("rank")

                # タイトル末尾の（A）っぽい吸い込みを剥がす
                title = re.sub(r"\s*（[A-CＡ-Ｃ]）\s*$", "", title)

                # 互換：rank単独で取れたらronbun扱いへ寄せる
                if rank and not rank_ronbun:
                    rank_ronbun = rank

                yield FoundExample(
                    example_no=ex_no,
                    title=title,
                    rank_tanto=normalize_rank(rank_tanto),
                    rank_ronbun=normalize_rank(rank_ronbun),
                )

    def extract(self, pdf_bytes: bytes, subject_code: str, source_pdf: str) -> List[ExampleItem]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chapters = parse_outline(doc)

        results: List[ExampleItem] = []
        last_page_ref: Optional[str] = None

        for i in range(len(doc)):
            pdf_page = i + 1
            text = normalize_dashes(doc[i].get_text("text") or "").replace("\u00a0", " ")

            found_ref = self.extract_page_ref(text)
            page_ref = found_ref or last_page_ref
            if found_ref:
                last_page_ref = found_ref

            chapter, section = find_chapter_section(chapters, pdf_page)
            if not chapter or not section:
                continue

            for ex in self.iter_examples_on_page(text):
                compat_rank = ex.rank_ronbun  # 互換rankは基本ronbun

                results.append(
                    ExampleItem(
                        subject=subject_code,
                        chapter_no=chapter.no,
                        chapter_title=chapter.title,
                        section_no=section.no,
                        section_title=section.title,
                        example_no=ex.example_no,
                        title=ex.title,
                        rank=compat_rank,
                        rank_tanto=ex.rank_tanto,
                        rank_ronbun=ex.rank_ronbun,
                        page_ref=page_ref,
                        pdf_page=pdf_page,
                        source_pdf=source_pdf,
                    )
                )

        doc.close()
        return results
