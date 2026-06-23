"""market_cap 重み付けの treemap ヒートマップ画像を生成する(squarify + Pillow)。

- タイルサイズ: market_cap
- カラー:       percent_change(下落=赤 / 上昇=緑)
- タイル内:     企業ロゴ(取得できた上位銘柄) + ticker + percent_change
- 上部:         見出し(headline、英語のまま)
- ロゴ:         Clearbit Logo API からベストエフォートで取得(失敗してもタイルは描画)

plotly ではタイル座標が取れずロゴを正確に貼れないため、squarify で配置を自前計算し
Pillow でピクセル単位に描画する方式に変更している。
"""
from __future__ import annotations

import logging
from io import BytesIO

import pandas as pd
import requests
import squarify
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

from .ticker_domains import TICKER_DOMAINS

# 色(RGB)
BG = (11, 15, 23)            # #0b0f17 背景
RED = (185, 28, 28)          # #b91c1c 下落
NEUTRAL = (31, 41, 55)       # #1f2937 中立
GREEN = (21, 128, 61)        # #15803d 上昇
WHITE = (255, 255, 255)

CLEARBIT = "https://logo.clearbit.com/{domain}"

_FONT_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_PATHS_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def _font(size: int, bold: bool = False):
    paths = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REG
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _color_for(pct: float, clip: float):
    """percent_change を 赤->中立->緑 に補間。"""
    p = max(-clip, min(clip, pct))
    t = (p + clip) / (2 * clip)  # 0..1
    if t < 0.5:
        return _lerp(RED, NEUTRAL, t / 0.5)
    return _lerp(NEUTRAL, GREEN, (t - 0.5) / 0.5)


def _fetch_logo(domain: str) -> Image.Image | None:
    """Clearbit からロゴ(RGBA)を取得。失敗時は None。"""
    try:
        url = CLEARBIT.format(domain=domain)
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200 or not resp.content:
            return None
        return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:  # noqa: BLE001
        logger.debug("logo fetch failed for %s: %s", domain, e)
        return None


def _text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def build_treemap(
    df: pd.DataFrame,
    headline: str,
    out_path: str = "market_map.png",
    color_clip: float = 0.04,
    label_top_n: int = 60,
    logo_top_n: int = 40,
    width: int = 1600,
    height: int = 900,
    header_h: int = 80,
) -> str:
    """treemap PNG を生成して out_path を返す。

    Args:
        color_clip:  色付けの上下限(±4%)
        label_top_n: ticker/percent ラベルを出す上位銘柄数(時価総額順)
        logo_top_n:  ロゴ取得を試みる上位銘柄数(時価総額順)
    """
    df = df.sort_values("market_cap", ascending=False).reset_index(drop=True)

    # 配置計算(squarify)。ヘッダ下の領域に敷き詰める
    area_x, area_y = 0, header_h
    area_w, area_h = width, height - header_h
    norm = squarify.normalize_sizes(df["market_cap"].tolist(), area_w, area_h)
    rects = squarify.squarify(norm, area_x, area_y, area_w, area_h)

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # ヘッダ見出し
    draw.text((20, 22), headline, font=_font(34, bold=True), fill=WHITE)

    for i, rect in enumerate(rects):
        row = df.iloc[i]
        x0, y0 = rect["x"], rect["y"]
        w, h = rect["dx"], rect["dy"]
        x1, y1 = min(x0 + w, width), min(y0 + h, height)

        draw.rectangle([x0, y0, x1, y1], fill=_color_for(row.percent_change, color_clip),
                       outline=BG, width=1)

        if w < 28 or h < 22:
            continue  # 小さすぎるタイルは何も描かない

        cx, cy = x0 + w / 2, y0 + h / 2
        pct_text = f"{row.percent_change * 100:+.1f}%"

        # ロゴ(上位 logo_top_n かつタイルが十分大きい場合のみ)
        logo_pasted = False
        if i < logo_top_n and w >= 64 and h >= 64:
            domain = row.logo_url or TICKER_DOMAINS.get(row.ticker)
            if domain:
                # logo_url がURLでなくドメイン文字列のときも許容
                domain = domain.replace("https://", "").replace("http://", "").strip("/")
                logo = _fetch_logo(domain)
                if logo is not None:
                    target = int(min(w, h) * 0.42)
                    logo.thumbnail((target, target))
                    lx = int(cx - logo.width / 2)
                    ly = int(cy - logo.height / 2 - h * 0.12)
                    img.paste(logo, (lx, ly), logo)
                    logo_pasted = True

        # テキスト(上位 label_top_n のみ)
        if i < label_top_n:
            fsize = max(10, min(20, int(w / 6)))
            tfont = _font(fsize, bold=True)
            pfont = _font(max(9, fsize - 2))

            tw, th = _text_size(draw, row.ticker, tfont)
            pw, ph = _text_size(draw, pct_text, pfont)

            if logo_pasted:
                ty = int(cy + h * 0.10)
            else:
                ty = int(cy - (th + ph) / 2)

            if tw <= w - 4 and (th + ph) <= h - 4:
                draw.text((cx - tw / 2, ty), row.ticker, font=tfont, fill=WHITE)
                draw.text((cx - pw / 2, ty + th + 2), pct_text, font=pfont, fill=WHITE)

    img.save(out_path)
    logger.info("treemap 画像を出力: %s", out_path)
    return out_path
