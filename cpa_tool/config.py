SUBJECT_LABELS = {
    "zeimu": "租税",
    "zaimu": "財務",
    "kanri": "管理",
    "unknown": "不明",
}
LABEL_TO_CODE = {v: k for k, v in SUBJECT_LABELS.items()}

SUBJECT_CODES = ["zeimu", "zaimu", "kanri", "unknown"]
SUBJECT_LABEL_OPTIONS = [SUBJECT_LABELS[c] for c in SUBJECT_CODES]
