from io import BytesIO
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from .utils import sort_df


def build_excel(df: pd.DataFrame, subject_code: str) -> BytesIO:
    wb = Workbook()
    wb.remove(wb.active)

    used_names = set()
    df_sorted = sort_df(df.copy())

    if "subject" in df_sorted.columns:
        df_sorted = df_sorted[df_sorted["subject"] == subject_code]

    if df_sorted.empty:
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    for (chap_no, chap_title), chap_df in df_sorted.groupby(["chapter_no", "chapter_title"], sort=True):
        chap_no_int = int(chap_no) if pd.notna(chap_no) else 0
        base_name = f"{chap_no_int}章 {chap_title}"[:31]
        sheet_name = base_name

        idx = 2
        while sheet_name in used_names:
            suffix = f"_{idx}"
            sheet_name = (base_name[:31 - len(suffix)] + suffix)
            idx += 1

        used_names.add(sheet_name)
        ws = wb.create_sheet(title=sheet_name)

        row = 1
        for (sec_no, sec_title), sec_df in chap_df.groupby(["section_no", "section_title"], sort=True):
            sec_no_int = int(sec_no) if pd.notna(sec_no) else 0
            ws.cell(row=row, column=1, value=f"第{sec_no_int}節")
            ws.cell(row=row, column=2, value=sec_title)
            row += 1

            counter = 1
            for _, r in sec_df.iterrows():
                ws.cell(row=row, column=1, value=counter)
                ws.cell(row=row, column=2, value=r.get("title"))     # B: title
                ws.cell(row=row, column=3, value=r.get("rank"))      # C: rank
                ws.cell(row=row, column=4, value=r.get("page_ref"))  # D: page_ref
                counter += 1
                row += 1

            row += 1

        widths = {1: 10, 2: 46, 3: 10, 4: 14}
        for col, w in widths.items():
            ws.column_dimensions[get_column_letter(col)].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
