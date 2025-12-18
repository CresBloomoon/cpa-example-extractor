from io import BytesIO
import json
import zipfile
from typing import Dict

import pandas as pd

from .config import SUBJECT_LABELS
from .excel_export import build_excel
from .utils import sort_df


def build_zip(per_subject_dfs: Dict[str, pd.DataFrame]) -> BytesIO:
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for subj in ["zeimu", "zaimu", "kanri"]:
            df = per_subject_dfs.get(subj)
            if df is None or df.empty:
                continue

            label = SUBJECT_LABELS[subj]
            xlsx_buf = build_excel(df, subj)
            zf.writestr(f"{label}_examples.xlsx", xlsx_buf.getvalue())

            j = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, indent=2)
            zf.writestr(f"{label}_examples.json", j)

        unk = per_subject_dfs.get("unknown")
        if unk is not None and not unk.empty:
            j = json.dumps(unk.to_dict(orient="records"), ensure_ascii=False, indent=2)
            zf.writestr("不明_examples.json", j)

        all_df = pd.concat([d for d in per_subject_dfs.values() if d is not None], ignore_index=True)
        all_df = sort_df(all_df)
        zf.writestr("ALL_examples.json", json.dumps(all_df.to_dict(orient="records"), ensure_ascii=False, indent=2))

    zip_buf.seek(0)
    return zip_buf
