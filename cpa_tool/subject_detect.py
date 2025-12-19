from typing import Dict, Tuple
import fitz

from .utils import normalize_dashes

SUBJECT_KEYWORDS: Dict[str, Dict[str, int]] = {
    "zeimu": {  # 租税
        "法人税": 6, "法人税法": 6, "租税": 5, "租税公課": 6, "税効果会計": 4,
        "申告": 3, "課税所得": 4, "別表": 4, "受取配当": 3, "完全支配関係": 3,
        "寄附金": 3, "交際費": 3, "減価償却": 3,
    },
    "zaimu": {  # 財務会計
        "財務会計": 6, "連結": 5, "企業結合": 5, "金融商品": 4, "退職給付": 4,
        "包括利益": 3, "キャッシュ・フロー": 3, "会計方針": 3, "減損": 3,
        "収益認識": 3, "資産除去債務": 3, "リース": 3,
    },
    "kanri": {  # 管理会計
        "管理会計": 6, "CVP": 6, "標準原価": 5, "差異分析": 5, "直接原価": 5,
        "予算": 4, "意思決定": 4, "設備投資": 4, "原価計算": 4, "原価企画": 4,
        "部門別": 3, "内部振替": 3,
    },
}

FILENAME_HINTS: Dict[str, Dict[str, int]] = {
    "zeimu": {"租税": 6, "税法": 6, "法人税": 6, "法人税法": 6, "消費税": 6, "所得税": 6},
    "zaimu": {"財務": 6, "財務会計": 6, "会計基準": 4, "連結": 4, "企業結合": 4},
    "kanri": {"管理": 6, "管理会計": 6, "原価": 4, "CVP": 6, "差異": 4, "予算": 4},
}

#ファイル名は人間が答えを書いてくれているので重みを高くする
FILENAME_WEIGHT = 3.0


def _score_text(text: str, weights: Dict[str, Dict[str, int]], base_factor: float = 1.0) -> Dict[str, int]:
    scores = {k: 0 for k in ["zeimu", "zaimu", "kanri"]}
    t = text or ""
    for subj, kws in weights.items():
        s = 0
        for kw, w in kws.items():
            if kw and kw in t:
                s += w
        scores[subj] += int(round(s * base_factor))
    return scores


def detect_subject_from_doc(doc: fitz.Document, file_name: str) -> Tuple[str, Dict[str, int]]:
    # TOC
    try:
        toc_text = " ".join([t for _, t, _ in doc.get_toc() if t]) or ""
    except Exception:
        toc_text = ""

    # 先頭ページ本文
    head_text = ""
    for i in range(min(8, len(doc))):
        try:
            head_text += (doc[i].get_text("text") or "") + "\n"
        except Exception:
            pass

    toc_text = normalize_dashes(toc_text).replace("\u00a0", " ")
    head_text = normalize_dashes(head_text).replace("\u00a0", " ")
    fname = normalize_dashes(file_name or "").replace("\u00a0", " ")

    scores = {k: 0 for k in ["zeimu", "zaimu", "kanri"]}
    s1 = _score_text(toc_text, SUBJECT_KEYWORDS, 1.0)
    s2 = _score_text(head_text, SUBJECT_KEYWORDS, 1.0)
    s3 = _score_text(fname, FILENAME_HINTS, FILENAME_WEIGHT)
    for k in scores:
        scores[k] = s1[k] + s2[k] + s3[k]

    best = max(scores, key=scores.get)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_score = ordered[0][1]
    second_score = ordered[1][1]

    if top_score < 6 or (top_score - second_score) < 2:
        return "unknown", scores

    return best, scores


def detect_subject_scores(pdf_bytes: bytes, filename: str) -> Dict[str, int]:
    """
    PDFバイト列とファイル名から科目スコアを計算する
    app.pyとのインターフェース用（科目コードは"zei"/"zaimu"/"kanri"形式で返す）
    注意: app.pyでは"zeimu"形式に統一されているため、この関数は"zei"形式で返すが、
    detect_subject_for_file内で"zeimu"に変換される
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        _, scores_raw = detect_subject_from_doc(doc, filename)
        doc.close()
        
        # "zeimu" -> "zei" にマッピング（app.pyとの互換性のため）
        scores = {
            "zei": scores_raw.get("zeimu", 0),
            "zaimu": scores_raw.get("zaimu", 0),
            "kanri": scores_raw.get("kanri", 0),
        }
        return scores
    except Exception:
        # エラー時は空のスコアを返す
        return {"zei": 0, "zaimu": 0, "kanri": 0}