"""
narrative_renderer.py
市場ナラティブTOP3＋今日の最重要テーマを1枚のPNG画像に描画する（Pillow/ダーク）。

入力 analysis dict:
  narratives: [{theme, whats_happening, why_market_cares, tickers[], stance, impact}]
  top_theme : {conclusion, rationale, tickers[]}
  post_value: int
"""

import os
from PIL import Image, ImageDraw, ImageFont

BG        = (13, 17, 23)
CARD_BG   = (22, 27, 34)
THEME_BG  = (24, 30, 40)
LINE      = (48, 54, 61)
TEXT      = (230, 237, 243)
SUBTLE    = (139, 148, 158)
ACCENT    = (45, 212, 191)
RED       = (248, 81, 73)
GREEN     = (63, 185, 80)
AMBER     = (210, 153, 34)
CHIP_BG   = (33, 38, 45)

STANCE = {
    "強気": (63, 185, 80),
    "弱気": (248, 81, 73),
    "中立": (139, 148, 158),
}

FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BLK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"

W = 1080
PAD = 48
CANVAS_H = 5000


def _f(size, bold=False):
    p = FONT_BLK if bold else FONT_REG
    if not os.path.exists(p):
        p = FONT_REG
    return ImageFont.truetype(p, size)


def _wrap(d, text, font, max_w):
    lines, cur = [], ""
    for ch in str(text):
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if d.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            lines.append(cur); cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _chip(d, x, y, text, font):
    w = d.textlength(text, font=font)
    d.rounded_rectangle([x, y, x + w + 22, y + 34], radius=8, fill=CHIP_BG)
    d.text((x + 11, y + 6), text, font=font, fill=ACCENT)
    return w + 22 + 10


def _impact_bar(d, x, y, impact, w=260, h=14):
    impact = max(0, min(10, int(impact)))
    d.rounded_rectangle([x, y, x + w, y + h], radius=7, fill=(40, 46, 54))
    fill_w = int(w * impact / 10)
    color = RED if impact >= 8 else AMBER if impact >= 5 else SUBTLE
    if fill_w > 0:
        d.rounded_rectangle([x, y, x + fill_w, y + h], radius=7, fill=color)


def render_narrative(analysis: dict, out_path: str) -> str:
    img = Image.new("RGB", (W, CANVAS_H), BG)
    d = ImageDraw.Draw(img)

    f_h1 = _f(46, True)
    f_meta = _f(26)
    f_theme = _f(34, True)
    f_label = _f(22, True)
    f_body = _f(27)
    f_chip = _f(22)
    f_small = _f(23)

    y = PAD
    d.text((PAD, y), "市場ナラティブ", font=f_h1, fill=TEXT)
    pv = analysis.get("post_value", "")
    meta = f"投稿価値 {pv}/10"
    mw = d.textlength(meta, font=f_meta)
    d.text((W - PAD - mw, y + 12), meta, font=f_meta, fill=SUBTLE)
    y += 66
    d.line([PAD, y, W - PAD, y], fill=ACCENT, width=3)
    y += 24

    body_w = W - PAD * 2 - 36

    # ===== ① ナラティブTOP3 =====
    for i, n in enumerate(analysis.get("narratives", [])[:3], 1):
        card_top = y
        inner = PAD + 18
        cy = y + 18

        # テーマ + スタンスバッジ
        stance = n.get("stance", "中立")
        scol = STANCE.get(stance, SUBTLE)
        theme = f'{i}. {n.get("theme","")}'
        for ln in _wrap(d, theme, f_theme, body_w - 140):
            d.text((inner, cy), ln, font=f_theme, fill=TEXT)
            cy += 44
        # スタンスバッジ（右上）
        bw = d.textlength(stance, font=f_label) + 28
        d.rounded_rectangle([W - PAD - 18 - bw, y + 18, W - PAD - 18, y + 18 + 36], radius=9, fill=scol)
        d.text((W - PAD - 18 - bw + 14, y + 24), stance, font=f_label, fill=(8, 12, 14))

        # 影響度バー
        d.text((inner, cy + 2), "影響度", font=f_small, fill=SUBTLE)
        _impact_bar(d, inner + 78, cy + 6, n.get("impact", 0))
        d.text((inner + 78 + 270, cy), f'{n.get("impact","-")}/10', font=f_small, fill=TEXT)
        cy += 38

        # 何が起きているか / なぜ気にするか
        for label, key in (("何が:", "whats_happening"), ("なぜ:", "why_market_cares")):
            d.text((inner, cy), label, font=f_small, fill=ACCENT)
            lines = _wrap(d, n.get(key, ""), f_body, body_w - 70)
            for j, ln in enumerate(lines):
                d.text((inner + 64, cy), ln, font=f_body, fill=TEXT)
                cy += 36
            cy += 4

        # 影響銘柄チップ
        tickers = n.get("tickers", []) or []
        if tickers:
            d.text((inner, cy + 4), "銘柄:", font=f_small, fill=ACCENT)
            cx = inner + 64
            for t in tickers[:8]:
                cx += _chip(d, cx, cy, str(t), f_chip)
                if cx > W - PAD - 120:
                    break
            cy += 42

        card_bottom = cy + 12
        # カード枠（背景を後ろに敷けないので枠線で表現）
        d.rounded_rectangle([PAD, card_top, W - PAD, card_bottom], radius=12, outline=LINE, width=1)
        y = card_bottom + 18

    # ===== ② 今日の最重要テーマ =====
    tt = analysis.get("top_theme", {}) or {}
    box_top = y
    inner = PAD + 18
    cy = y + 18
    d.text((inner, cy), "★ 今日の最重要テーマ", font=f_theme, fill=AMBER)
    cy += 48
    d.text((inner, cy), "結論:", font=f_small, fill=ACCENT)
    for ln in _wrap(d, tt.get("conclusion", ""), f_body, body_w - 70):
        d.text((inner + 64, cy), ln, font=f_body, fill=TEXT)
        cy += 36
    cy += 6
    d.text((inner, cy), "根拠:", font=f_small, fill=ACCENT)
    for ln in _wrap(d, tt.get("rationale", ""), f_body, body_w - 70):
        d.text((inner + 64, cy), ln, font=f_body, fill=TEXT)
        cy += 36
    cy += 6
    tickers = tt.get("tickers", []) or []
    if tickers:
        d.text((inner, cy + 4), "注目:", font=f_small, fill=ACCENT)
        cx = inner + 64
        for t in tickers[:8]:
            cx += _chip(d, cx, cy, str(t), f_chip)
            if cx > W - PAD - 120:
                break
        cy += 42
    box_bottom = cy + 12
    d.rounded_rectangle([PAD, box_top, W - PAD, box_bottom], radius=12, outline=AMBER, width=2)
    y = box_bottom + 24

    d.text((PAD, y), "※市場全体・主要セクターに影響する材料のみ抽出（出所:ニュース/指標/決算/Reddit）",
           font=f_small, fill=SUBTLE)
    y += 44

    img = img.crop((0, 0, W, int(y)))
    img.save(out_path)
    return out_path
