# cpa_tool/outputs.py
from __future__ import annotations

import io
import zipfile
from typing import Dict

import pandas as pd

from .excel_export import build_excel


def build_zip(per_subject: Dict[str, pd.DataFrame]) -> io.BytesIO:
    """
    per_subject:
      {
        "zaimu": df_zaimu,
        "kanri": df_kanri,
        "zeimu": df_zeimu,
      }
    """
    zbuf = io.BytesIO()

    with zipfile.ZipFile(zbuf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        any_written = False

        for subj, df in (per_subject or {}).items():
            # dfがNoneでも build_excel が安全に1枚残すのでOK
            xlsx_buf = build_excel(df, subj)

            filename = f"{subj}.xlsx"
            zf.writestr(filename, xlsx_buf.getvalue())
            any_written = True

        # もし何も無かったら、zipが空で分かりづらいのでメモだけ入れる
        if not any_written:
            zf.writestr("README.txt", "No output. per_subject was empty.")

    zbuf.seek(0)
    return zbuf
