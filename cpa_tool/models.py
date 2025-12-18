from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chapter:
    no: int
    title: str
    start_page: int
    sections: List["Section"]


@dataclass
class Section:
    no: int
    title: str
    start_page: int


@dataclass
class ExampleItem:
    subject: str
    chapter_no: int
    chapter_title: str
    section_no: int
    section_title: str
    example_no: int
    title: str

    # --- rank拡張 ---
    # 租税: rank_ronbunのみ
    # 財務/管理: tanto + ronbun
    rank: Optional[str]              # 互換用（基本はronbunを入れる）
    rank_tanto: Optional[str]        # 短答
    rank_ronbun: Optional[str]       # 論文

    page_ref: Optional[str]
    pdf_page: int
    source_pdf: str
