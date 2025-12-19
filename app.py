from __future__ import annotations

import io
from dataclasses import asdict, is_dataclass
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

# ====== cpa_tool imports（環境差異に強くする）======
try:
    # 例題抽出本体
    from cpa_tool.extract import extract_examples
except Exception:
    extract_examples = None  # type: ignore

try:
    # zip生成（科目別xlsxをzipにまとめる）
    from cpa_tool.outputs import build_zip
except Exception:
    build_zip = None  # type: ignore

# 科目判定（あれば使う、なければ簡易）
try:
    from cpa_tool.subject_detect import detect_subject_scores  # (pdf_bytes, filename) -> dict
except Exception:
    detect_subject_scores = None  # type: ignore


# ====== 表示用ラベル ======
SUBJECT_LABEL = {
    "zeimu": "租税法",
    "zaimu": "財務会計",
    "kanri": "管理会計",
    "unknown": "不明",
}

SUBJECT_OPTIONS = ["zeimu", "zaimu", "kanri"]


# ====== 科目ごとの「表示列」設定 ======
SUBJECT_COLUMNS = {
    # 租税法：章節は必要（例）
    "zeimu": [
        "subject",
        "chapter_no", "chapter_title",
        "section_no", "section_title",
        "example_no", "title",
        "rank",              # 租税法が論文のみなら rank でOK（今の実装に合わせる）
        "page_ref",
        "pdf_page",
        "source_pdf",
    ],
    # 財務：短答/論文/交換など
    "zaimu": [
        "subject",
        "chapter_no", "chapter_title",
        "section_no", "section_title",
        "example_no", "title",
        "rank_tanto", "rank_ronbun", "rank_koukan",
        "page_ref",
        "pdf_page",
        "source_pdf",
    ],
    # 管理：章節いらない運用なら最小にする
    "kanri": [
        "subject",
        "example_no", "title",
        "rank_tanto", "rank_ronbun",
        "page_ref",
        "pdf_page",
        "source_pdf",
    ],
}


# ====== ユーティリティ ======
def _safe_to_dict(x) -> dict:
    """dataclass / dict / pydanticっぽい / その他をdict化"""
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    if is_dataclass(x):
        return asdict(x)
    # pydantic v1/v2
    if hasattr(x, "model_dump"):
        return x.model_dump()
    if hasattr(x, "dict"):
        return x.dict()
    # 最後の手段
    try:
        return dict(x)
    except Exception:
        return {"value": str(x)}


def _simple_subject_score_from_filename(filename: str) -> Dict[str, int]:
    """subject_detectが無い場合の超簡易スコア（ファイル名ヒント）"""
    name = (filename or "").lower()
    score = {"zeimu": 0, "zaimu": 0, "kanri": 0}

    # ありがちな単語を雑に加点
    if "租税" in filename or "法人税" in filename or "所得税" in filename or "消費税" in filename:
        score["zeimu"] += 50
    if "財務" in filename or "会計" in filename or "計算" in filename:
        score["zaimu"] += 50
    if "管理" in filename or "原価" in filename or "意思決定" in filename:
        score["kanri"] += 50

    # さらに微調整
    if "kanri" in name:
        score["kanri"] += 10
    if "zaimu" in name:
        score["zaimu"] += 10
    if "zeimu" in name or "zei" in name or "tax" in name:
        score["zeimu"] += 10

    return score


def detect_subject_for_file(pdf_bytes: bytes, filename: str) -> Tuple[str, Dict[str, int]]:
    """科目自動判定：cpa_toolがあればそれ、なければファイル名ヒント"""
    if detect_subject_scores is not None:
        try:
            scores_raw = detect_subject_scores(pdf_bytes, filename)  # type: ignore
            # detect_subject_scoresは"zei"形式で返すが、内部では"zeimu"にマッピング
            # ここでは"zeimu"形式に変換
            scores = {
                "zeimu": scores_raw.get("zei", 0),
                "zaimu": scores_raw.get("zaimu", 0),
                "kanri": scores_raw.get("kanri", 0),
            }
        except Exception:
            scores = _simple_subject_score_from_filename(filename)
    else:
        scores = _simple_subject_score_from_filename(filename)

    best = max(scores.items(), key=lambda kv: kv[1])[0] if scores else "unknown"
    return best, scores


def render_final_check_by_subject(df_all: pd.DataFrame) -> pd.DataFrame:
    """
    編集（最終チェック）を科目別expanderで表示し、編集結果を結合して返す。
    """
    if df_all is None or df_all.empty:
        st.info("抽出結果がありません。")
        return df_all

    if "subject" not in df_all.columns:
        st.warning("subject列がないため、科目別表示できません。")
        return df_all

    st.subheader("編集（最終チェック）")

    edited_chunks = []

    # 表示順
    order = ["zeimu", "zaimu", "kanri", "unknown"]
    subjects = [s for s in order if s in set(df_all["subject"].astype(str))]
    subjects += [s for s in sorted(set(df_all["subject"].astype(str))) if s not in subjects]

    for subj in subjects:
        df_sub = df_all[df_all["subject"].astype(str) == subj].copy()
        label = SUBJECT_LABEL.get(subj, subj)

        cols = SUBJECT_COLUMNS.get(subj, list(df_sub.columns))
        cols = [c for c in cols if c in df_sub.columns]  # 存在しない列は落とす

        with st.expander(f"{label}（{len(df_sub)}件）", expanded=False):
            df_view = df_sub[cols].copy()

            edited = st.data_editor(
                df_view,
                use_container_width=True,
                hide_index=True,
                key=f"final_check_{subj}",  # ★科目ごとにユニーク
            )

            # 表示列だけ差し戻し
            for c in edited.columns:
                df_sub.loc[:, c] = edited[c].values

        edited_chunks.append(df_sub)

    out = pd.concat(edited_chunks, axis=0).sort_index()
    return out


# ====== UI ======
st.set_page_config(page_title="CPAテキスト 例題抽出ツール", layout="wide")
st.title("CPAテキスト 例題抽出ツール（科目自動判定→不明のみ手修正→科目別xlsx）")

uploaded_files = st.file_uploader(
    "PDFをドラッグ＆ドロップ（複数OK）",
    type=["pdf"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.stop()

st.success(f"アップロード：{len(uploaded_files)}ファイル")

# ====== 科目判定結果 ======
rows = []
file_bytes_map: Dict[str, bytes] = {}

for f in uploaded_files:
    b = f.read()
    file_bytes_map[f.name] = b

    detected, scores = detect_subject_for_file(b, f.name)
    row = {
        "file_name": f.name,
        "detected_subject": SUBJECT_LABEL.get(detected, detected),
        "score_租税": scores.get("zeimu", 0),
        "score_財務": scores.get("zaimu", 0),
        "score_管理": scores.get("kanri", 0),
        "final_subject": SUBJECT_LABEL.get(detected, detected),
        "_final_subject_code": detected,
    }
    rows.append(row)

df_subj = pd.DataFrame(rows)

st.subheader("科目判定結果（不明だけ直せばOK）")

# ユーザが編集できる列（final_subjectだけ）
# 表示は日本語、内部はコードに戻す
label_to_code = {v: k for k, v in SUBJECT_LABEL.items()}
code_to_label = {k: v for k, v in SUBJECT_LABEL.items()}

# final_subject の選択肢（日本語）
final_choices = [SUBJECT_LABEL[c] for c in SUBJECT_OPTIONS]

# data_editor用：表示列
df_view = df_subj[["file_name", "detected_subject", "score_租税", "score_財務", "score_管理", "final_subject"]].copy()

edited = st.data_editor(
    df_view,
    use_container_width=True,
    hide_index=True,
    column_config={
        "final_subject": st.column_config.SelectboxColumn(
            "final_subject",
            help="科目が違うならここだけ直してOK",
            options=final_choices,
        )
    },
    key="subject_table",
)

# 編集結果をコードに戻す
final_code_map = {}
for i, r in edited.iterrows():
    fname = r["file_name"]
    subj_label = r["final_subject"]
    subj_code = label_to_code.get(subj_label, "unknown")
    final_code_map[fname] = subj_code

# ====== 実行 ======
st.divider()
run = st.button("解析実行（ここで抽出スタート）", type="primary", disabled=False)

if not run:
    st.stop()

if extract_examples is None:
    st.error("cpa_tool.extract.extract_examples が見つかりません。cpa_tool の実装を確認してね。")
    st.stop()

# unknownファイルを事前に警告
unknown_files = [fname for fname, subj_code in final_code_map.items() if subj_code not in SUBJECT_OPTIONS]
if unknown_files:
    for fname in unknown_files:
        st.warning(f"科目が不明のためスキップ: {fname}")

# 処理対象ファイルをフィルタリング（unknownを除外）
valid_files = [(fname, subj_code) for fname, subj_code in final_code_map.items() if subj_code in SUBJECT_OPTIONS]
total_files = len(valid_files)

if total_files == 0:
    st.warning("処理対象のファイルがありません。科目が不明のファイルはスキップされます。")
    st.stop()

# ローディングリングとステータス表示
all_items: List[dict] = []
with st.spinner("🔍 解析処理を実行中..."):
    for idx, (fname, subj_code) in enumerate(valid_files, 1):
        b = file_bytes_map[fname]
        items = extract_examples(b, subj_code, fname)  # 既存のシグネチャに合わせる（pdf_bytes, subject_code, source_pdf）
        # itemsがdataclassでもdictでもOKにする
        all_items.extend([_safe_to_dict(x) for x in items])

st.success(f"✅ 処理完了: {total_files}ファイル、{len(all_items)}件の例題を抽出しました")

if not all_items:
    st.warning("例題が抽出できませんでした。例題の表記ゆれがあるかも。")
    st.stop()

df_all = pd.DataFrame(all_items)

# ====== 編集（最終チェック）科目別 ======
df_all = render_final_check_by_subject(df_all)

# ここで「チェック更新（ここで集計）」ボタンを置くなら、df_all確定後にやる
st.button("チェック更新（ここで集計）", key="refresh_dummy")

# ====== 出力 ======
st.subheader("チェック結果（現在）")
st.dataframe(df_all, use_container_width=True, hide_index=True)

st.divider()
st.subheader("最終出力")

# 科目別に分けてzip出力
per_subject: Dict[str, pd.DataFrame] = {}
for subj in SUBJECT_OPTIONS:
    d = df_all[df_all.get("subject", "").astype(str) == subj].copy()
    if not d.empty:
        per_subject[subj] = d

if not per_subject:
    st.warning("科目別に分けられませんでした（subject列を確認してね）。")
    st.stop()

if build_zip is None:
    st.error("cpa_tool.outputs.build_zip が見つかりません。cpa_tool の実装を確認してね。")
    st.stop()

zip_buf: io.BytesIO = build_zip(per_subject)  # type: ignore

st.download_button(
    label="科目別xlsx（zip）をダウンロード",
    data=zip_buf.getvalue(),
    file_name="cpa_examples_by_subject.zip",
    mime="application/zip",
)
