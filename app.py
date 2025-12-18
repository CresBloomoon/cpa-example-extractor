import json
from dataclasses import asdict, is_dataclass
from typing import Dict

import fitz
import pandas as pd
import streamlit as st

from cpa_tool.config import SUBJECT_CODES, SUBJECT_LABELS, SUBJECT_LABEL_OPTIONS, LABEL_TO_CODE
from cpa_tool.subject_detect import detect_subject_from_doc
from cpa_tool.extract import extract_examples
from cpa_tool.utils import sort_df
from cpa_tool.checks import count_none_cells
from cpa_tool.outputs import build_zip


st.set_page_config(page_title="CPA 例題抽出（科目自動判定→科目別出力）", layout="wide")
st.title("CPAテキスト 例題抽出ツール（科目自動判定 → 不明のみ手修正 → 科目別xlsx）")

uploaded_files = st.file_uploader(
    "PDFをドラッグ＆ドロップ（複数OK）",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    # 1) 科目判定（軽い）
    file_rows = []
    file_bytes_map: Dict[str, bytes] = {}

    with st.spinner("科目判定中…（ファイル名も加点）"):
        for uf in uploaded_files:
            b = uf.read()
            file_bytes_map[uf.name] = b

            doc = fitz.open(stream=b, filetype="pdf")
            subj_code, scores = detect_subject_from_doc(doc, uf.name)
            doc.close()

            file_rows.append({
                "file_name": uf.name,
                "detected_subject": SUBJECT_LABELS[subj_code],
                "score_租税": scores.get("zeimu", 0),
                "score_財務": scores.get("zaimu", 0),
                "score_管理": scores.get("kanri", 0),
                "final_subject": SUBJECT_LABELS[subj_code],
            })

    st.success(f"アップロード：{len(uploaded_files)} ファイル")
    file_df = pd.DataFrame(file_rows)

    st.subheader("科目判定結果（不明だけ直せばOK）")
    with st.form("subject_form", clear_on_submit=False):
        edited_file_df = st.data_editor(
            file_df,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "final_subject": st.column_config.SelectboxColumn(
                    "final_subject",
                    options=SUBJECT_LABEL_OPTIONS
                ),
                "detected_subject": st.column_config.TextColumn("detected_subject", disabled=True),
                "file_name": st.column_config.TextColumn("file_name", disabled=True),
                "score_租税": st.column_config.NumberColumn("score_租税", disabled=True),
                "score_財務": st.column_config.NumberColumn("score_財務", disabled=True),
                "score_管理": st.column_config.NumberColumn("score_管理", disabled=True),
            },
            key="subject_editor"
        )
        run_extract = st.form_submit_button("解析実行（ここで抽出スタート）")

    # 2) 抽出（重い）
    if run_extract:
        all_items = []
        with st.spinner("例題抽出中…（少し待ってね）"):
            for _, r in edited_file_df.iterrows():
                fname = r["file_name"]
                subj_label = r["final_subject"]
                subj_code = LABEL_TO_CODE.get(subj_label, "unknown")

                b = file_bytes_map[fname]
                items = extract_examples(b, subj_code, fname)
                all_items.extend([x if isinstance(x, dict) else asdict(x) for x in items])

        if not all_items:
            st.warning("例題が抽出できませんでした。例題の表記ゆれがあるかも。")
            st.stop()

        base_df = sort_df(pd.DataFrame(all_items))
        st.session_state["edited_df"] = base_df.copy()

    # 3) 編集 → チェック → 出力
    if "edited_df" in st.session_state:
        st.divider()
        st.subheader("編集（最終チェック）")

        with st.form("edit_form", clear_on_submit=False):
            edited_df = st.data_editor(
                st.session_state["edited_df"],
                use_container_width=True,
                num_rows="fixed",
                column_config={
                    "rank": st.column_config.SelectboxColumn("rank(互換)", options=[None, "A", "B", "C"]),
                    "rank_tanto": st.column_config.SelectboxColumn("rank_短答", options=[None, "A", "B", "C"]),
                    "rank_ronbun": st.column_config.SelectboxColumn("rank_論文", options=[None, "A", "B", "C"]),
                    "title": st.column_config.TextColumn("title"),
                    "page_ref": st.column_config.TextColumn("page_ref"),
                    "source_pdf": st.column_config.TextColumn("source_pdf", disabled=True),
                },
                key="main_editor"
            )
            update_check = st.form_submit_button("チェック更新（ここで集計）")

        if update_check:
            st.session_state["edited_df"] = sort_df(edited_df)

        current_df = st.session_state["edited_df"]

        st.subheader("チェック結果（現在）")
        total_none, per_col = count_none_cells(current_df)
        st.metric("全セルの未入力（None）件数", f"{total_none} 個")

        st.caption("列別の未入力（None）件数")
        per_col_df = (
            pd.DataFrame([{"column": k, "none_count": int(v)} for k, v in per_col.items()])
            .sort_values("none_count", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(per_col_df, use_container_width=True)

        if total_none == 0:
            st.success("🎉 未入力はありません。出力してOKです。")

        st.divider()
        st.subheader("最終出力")

        per_subject = {s: current_df[current_df["subject"] == s].copy() for s in SUBJECT_CODES}
        zip_buf = build_zip(per_subject)

        st.download_button(
            "科目別ZIPをダウンロード（xlsx + json）",
            data=zip_buf,
            file_name="CPA_examples_by_subject.zip",
            mime="application/zip"
        )

        st.download_button(
            "ALL_examples.json（まとめ）をダウンロード",
            data=json.dumps(sort_df(current_df).to_dict(orient="records"), ensure_ascii=False, indent=2),
            file_name="ALL_examples.json",
            mime="application/json"
        )
