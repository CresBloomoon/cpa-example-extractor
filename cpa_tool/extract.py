from typing import List

from .models import ExampleItem
from .extractors.zeimu import ZeimuExtractor
from .extractors.zaimu import ZaimuExtractor
from .extractors.kanri import KanriExtractor


_EXTRACTOR_REGISTRY = {
    "zeimu": ZeimuExtractor(),
    "zaimu": ZaimuExtractor(),
    "kanri": KanriExtractor(),
}


def extract_examples(pdf_bytes: bytes, subject_code: str, source_pdf: str) -> List[ExampleItem]:
    extractor = _EXTRACTOR_REGISTRY.get(subject_code)
    if extractor is None:
        return []
    return extractor.extract(pdf_bytes, subject_code, source_pdf)
