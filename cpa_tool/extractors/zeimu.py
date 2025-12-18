import re
from .base import BaseExtractor


class ZeimuExtractor(BaseExtractor):
    EXAMPLE_PATTERNS = [
        re.compile(
            r"例題\s*(?P<num>\d+)\s+(?P<title>.*?)(?:\s*（(?P<rank>[A-CＡ-Ｃ])）)?\s*(?=\n|$)"
        )
    ]

    PAGE_REF_PATTERNS = [
        re.compile(r"(?P<head>法)(?P<section>[^\s\-]+)-(?P<pageno>\d+)"),
    ]
