# cpa_tool/debug_viewer.py
from __future__ import annotations

import io
import re
import hashlib
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any

import streamlit as st

# pdfplumber は「テキスト+座標」が取れるのでデバッグ向き
import pdfplumber

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None


@dataclass
class HitBox:
    label: str
    bbox: Tuple[float, float, float, float]  # (x0, top, x1, bottom)


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


@st.cache_data(show_spinner=False)
def _get_page_png(pdf_sha1: str, pdf_bytes: bytes, page_index: int, dpi: int) -> bytes:
    # cache key に sha1 を混ぜる（bytes 自体は大きいので sha1 を主キーにする）
    _ = pdf_sha1
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[page_index]
        im = page.to_image(resolution=dpi).original  # PIL image
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()


@st.cache_data(show_spinner=False)
def _get_page_words(pdf_sha1: str, pdf_bytes: bytes, page_index: int) -> List[Dict[str, Any]]:
    _ = pdf_sha1
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[page_index]
        # x_tolerance/y_tolerance で「単語の結合具合」が変わる
        words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
        return words


@st.cache_data(show_spinner=False)
def _get_page_chars(pdf_sha1: str, pdf_bytes: bytes, page_index: int) -> List[Dict[str, Any]]:
    _ = pdf_sha1
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[page_index]
        return page.chars


def _draw_boxes_on_png(png_bytes: bytes, boxes: List[HitBox]) -> bytes:
    if Image is None:
        return png_bytes
    im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(im, "RGBA")

    # 色は固定（見やすさ優先）。必要なら後でUIで変えられる
    for b in boxes:
        x0, top, x1, bottom = b.bbox
        draw.rectangle([x0, top, x1, bottom], outline=(255, 0, 0, 255), width=3)
        # ラベル
        draw.rectangle([x0, max(0, top - 18), x0 + 220, top], fill=(255, 0, 0, 160))
        draw.text((x0 + 4, max(0, top - 16)), b.label, fill=(255, 255, 255, 255))

    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def _boxes_from_words(words: List[Dict[str, Any]], limit: int = 400) -> List[HitBox]:
    boxes: List[HitBox] = []
    for i, w in enumerate(words[:limit]):
        txt = w.get("text", "")
        bbox = (w["x0"], w["top"], w["x1"], w["bottom"])
        boxes.append(HitBox(label=f"W{i}:{txt[:18]}", bbox=bbox))
    return boxes


def _boxes_from_chars(chars: List[Dict[str, Any]], limit: int = 800) -> List[HitBox]:
    boxes: List[HitBox] = []
    for i, c in enumerate(chars[:limit]):
        txt = c.get("text", "")
        bbox = (c["x0"], c["top"], c["x1"], c["bottom"])
        boxes.append(HitBox(label=f"C{i}:{txt}", bbox=bbox))
    return boxes


def _find_regex_hits_in_words(words: List[Dict[str, Any]], pattern: str) -> List[HitBox]:
    if not pattern:
        return []
    try:
        rx = re.compile(pattern)
    except re.error:
        return []

    boxes: List[HitBox] = []
    for i, w in enumerate(words):
        t = w.get("text", "")
        if rx.search(t):
            bbox = (w["x0"], w["top"], w["x1"], w["bottom"])
            boxes.append(HitBox(label=f"HIT:{t[:24]}", bbox=bbox))
    return boxes


def render_debug_panel(pdf_bytes: bytes, file_name: str):
    """
    Streamlit 用のデバッグパネル。
    - ページ画像
    - words/chars の bbox 可視化
    - regex ヒット位置可視化
    """
    st.subheader("デバッグ（抽出がなぜ崩れるかを目で見る）")

    pdf_sha1 = _sha1(pdf_bytes)

    # ページ数
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        n_pages = len(pdf.pages)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        page_index = st.number_input("ページ番号（0始まり）", min_value=0, max_value=max(0, n_pages - 1), value=0, step=1)
    with col2:
        dpi = st.selectbox("表示DPI", [120, 150, 200, 250], index=1)
    with col3:
        mode = st.selectbox("可視化モード", ["画像のみ", "words bbox", "chars bbox", "regexヒット(words)"], index=1)

    regex = ""
    if mode == "regexヒット(words)":
        regex = st.text_input("正規表現（例：^例題|短答|論文|—|③）", value=r"^例題|短答|論文|—")

    # ページ画像
    png = _get_page_png(pdf_sha1, pdf_bytes, int(page_index), int(dpi))

    boxes: List[HitBox] = []
    if mode == "words bbox":
        words = _get_page_words(pdf_sha1, pdf_bytes, int(page_index))
        boxes = _boxes_from_words(words)
        st.caption(f"words 件数: {len(words)}（先頭 {min(400, len(words))} 件を描画）")
    elif mode == "chars bbox":
        chars = _get_page_chars(pdf_sha1, pdf_bytes, int(page_index))
        boxes = _boxes_from_chars(chars)
        st.caption(f"chars 件数: {len(chars)}（先頭 {min(800, len(chars))} 件を描画）")
    elif mode == "regexヒット(words)":
        words = _get_page_words(pdf_sha1, pdf_bytes, int(page_index))
        boxes = _find_regex_hits_in_words(words, regex)
        st.caption(f"regex ヒット: {len(boxes)} 件 / words 総数 {len(words)} 件")

    # 描画
    if boxes:
        png2 = _draw_boxes_on_png(png, boxes)
        st.image(png2, caption=f"{file_name} / page={page_index}", use_container_width=True)
    else:
        st.image(png, caption=f"{file_name} / page={page_index}", use_container_width=True)

    # 下にテキスト確認（雑に見れるやつ）
    with st.expander("抽出テキスト（このページ）", expanded=False):
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[int(page_index)]
            st.code(page.extract_text() or "", language="text")

    with st.expander("words一覧（先頭200件）", expanded=False):
        words = _get_page_words(pdf_sha1, pdf_bytes, int(page_index))
        preview = [{"text": w.get("text"), "x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"]} for w in words[:200]]
        st.json(preview)

