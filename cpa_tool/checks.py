from typing import Dict, Tuple
import pandas as pd


def count_none_cells(df: pd.DataFrame) -> Tuple[int, Dict[str, int]]:
    na_mask = df.isna()
    none_str_mask = df.applymap(lambda x: isinstance(x, str) and x.strip().lower() == "none")
    mask = na_mask | none_str_mask
    total = int(mask.to_numpy().sum())
    per_col = mask.sum().astype(int).to_dict()
    return total, {k: int(v) for k, v in per_col.items()}
