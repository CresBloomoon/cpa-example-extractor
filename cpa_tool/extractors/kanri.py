import re
from .base import BaseExtractor


class KanriExtractor(BaseExtractor):
    """
    管理会計論向け（暫定）
    - まずヒットさせるために、例題/設例/演習/問題 を拾う
    - page_refも管理側の実表記に合わせて増やす前提
    """

    EXAMPLE_PATTERNS = [
        re.compile(
            r"(?:【?(?:例題|設例|演習|問題)】?|(?:例題|設例|演習|問題))\s*(?P<num>\d+)\s+(?P<title>.*?)(?=\n|$)"
        )
    ]

    PAGE_REF_PATTERNS = [
        re.compile(r"(?P<head>管)(?P<section>[^\s\-]+)-(?P<pageno>\d+)"),
        re.compile(r"(?P<head>管計)(?P<section>[^\s\-]+)-(?P<pageno>\d+)"),
        re.compile(r"(?P<head>原)(?P<section>[^\s\-]+)-(?P<pageno>\d+)"),
    ]
