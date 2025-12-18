import re
import fitz
from typing import List, Optional, Tuple

from .models import Chapter, Section
from .utils import normalize_dashes


def parse_outline(doc: fitz.Document) -> List[Chapter]:
    chapters: List[Chapter] = []
    current: Optional[Chapter] = None

    for level, title, page in doc.get_toc():
        title = normalize_dashes(title or "")

        if level == 1:
            m = re.search(r"第(\d+)章\s*(.+)", title)
            if not m:
                continue
            current = Chapter(no=int(m.group(1)), title=m.group(2), start_page=page, sections=[])
            chapters.append(current)

        elif level == 2 and current:
            m = re.search(r"第(\d+)節\s*(.+)", title)
            if not m:
                continue
            current.sections.append(Section(no=int(m.group(1)), title=m.group(2), start_page=page))

    return chapters


def find_chapter_section(chapters: List[Chapter], pdf_page: int) -> Tuple[Optional[Chapter], Optional[Section]]:
    current_ch = None
    for ch in chapters:
        if pdf_page >= ch.start_page:
            current_ch = ch
    if not current_ch:
        return None, None

    current_sec = None
    for sec in current_ch.sections:
        if pdf_page >= sec.start_page:
            current_sec = sec

    return current_ch, current_sec
