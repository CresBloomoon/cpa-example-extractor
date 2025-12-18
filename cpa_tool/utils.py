import pandas as pd
from typing import Optional


def normalize_dashes(s: str) -> str:
    return (s or "").replace("－", "-").replace("―", "-").replace("−", "-")


def normalize_rank(rank: Optional[str]) -> Optional[str]:
    if not rank:
        return None
    return rank.translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"}))


def sort_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["chapter_no", "section_no", "example_no", "pdf_page"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    sort_cols = [c for c in ["subject", "chapter_no", "section_no", "pdf_page", "example_no"] if c in df.columns]
    return df.sort_values(by=sort_cols, kind="stable").reset_index(drop=True)
