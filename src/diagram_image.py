"""
金融ニュースを「構造を説明する図解」PNGに描画するモジュール。

LLM が news の内容から最適な type を選び、その type 用のJSONを返す。
このモジュールが type を見て対応する描画関数にディスパッチする。

type:
  "flow"     : 因果・波及（材料→見方→注目点 など）
  "compare"  : 強気 vs 弱気 / 2社比較
  "stat"     : 決算・指標など数字が主役
  "timeline" : 日程・順序・イベント列
"""

from PIL import Image, ImageDraw, ImageFont

# ===== テーマ（ダークターミナル調） =====
BG        = (13, 17, 23)
CARD      = (22, 27, 34)
CARD_LINE = (48, 54, 61)
ACCENT    = (45, 212, 191)   # ティール
ACCENT_DK = (35, 134, 122)
TEXT      = (230, 237, 243)
SUBTLE    = (139, 148, 158)
ARROW     = (88, 166, 255)   # ブルー
GREEN     = (63, 185, 80)    # 強気・上昇
RED       = (248, 81, 73)    # 弱気・下落
INK       = (8, 12, 14)

FONT_REG  = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BLK  = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"

W       = 1080
PAD     = 64
BOX_PAD = 32
RADIUS  = 20
CANVAS_H = 2400   # 一旦大きく描いて最後にクロップ

_CLOSING = set("。、）」』】〕》〉？！…ーぁぃぅぇぉっゃゅょゎ々：；,.)]}%")


import os as _os

def _f(size, bold=False):
    path = FONT_BLK if bold else FONT_REG
    if not _os.path.exists(path):
        for alt in (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ):
            if _os.path.exists(alt):
                path = alt
                break
    return ImageFont.truetype(path, size)


def _wrap(draw, text, font, max_w):
    """日本語対応 + 簡易禁則（閉じ記号を行頭に置かない）"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        elif ch in _CLOSING and cur:
            cur += ch
            lines.append(cur); cur = ""
        else:
            lines.append(cur); cur = ch
    if cur:
        lines.append(cur)
    return lines


def _block(d, x, y, text, font, fill, max_w, gap=10):
    lines = _wrap(d, text, font, max_w)
    asc, desc = font.getmetrics()
    lh = asc + desc + gap
    for i, ln in enumerate(lines):
        d.text((x, y + i * lh), ln, font=font, fill=fill)
    return len(lines) * lh


def _pill(d, x, y, text, font, fg, bg, h=44, padx=14, r=10):
    w = d.textlength(text, font=font)
    d.rounded_rectangle([x, y, x + w + padx * 2, y + h], radius=r, fill=bg)
    d.text((x + padx, y + (h - font.getmetrics()[0]) // 2 + 2), text, font=font, fill=fg)
    return w + padx * 2


def _header(d, data, y):
    inner = W - PAD * 2
    f_tag = _f(30, True)
    _pill(d, PAD, y, f"【{data.get('tag','市場メモ')}】", f_tag, ACCENT, (30, 41, 43), h=56, padx=18, r=12)
    y += 56 + 24
    y += _block(d, PAD, y, data["title"], _f(46, True), TEXT, inner, gap=12)
    return y + 44


def _footer(d, data, y):
    f = _f(28)
    y += 20
    foot = "　".join(data.get("hashtags", []))
    d.text((PAD, y), foot, font=f, fill=SUBTLE)
    handle = data.get("handle", "")
    if handle:
        hw = d.textlength(handle, font=f)
        d.text((W - PAD - hw, y), handle, font=f, fill=ACCENT)
    return y + 50


def _arrow_down(d, y, gap=40):
    cx = W // 2
    d.line([cx, y + 8, cx, y + gap - 14], fill=ARROW, width=4)
    d.polygon([(cx - 12, y + gap - 16), (cx + 12, y + gap - 16), (cx, y + gap - 4)], fill=ARROW)
    return y + gap


# ---------- type: flow ----------
def _flow(d, data, y):
    inner_w = W - PAD * 2
    tw = inner_w - BOX_PAD * 2
    f_lbl, f_body = _f(28, True), _f(34)
    nodes = data["nodes"]
    for i, node in enumerate(nodes):
        lines = _wrap(d, node["text"], f_body, tw)
        b_asc, b_desc = f_body.getmetrics()
        body_h = len(lines) * (b_asc + b_desc + 10)
        nh = BOX_PAD + 44 + 14 + body_h + BOX_PAD
        d.rounded_rectangle([PAD, y, W - PAD, y + nh], radius=RADIUS, fill=CARD, outline=CARD_LINE, width=2)
        _pill(d, PAD + BOX_PAD, y + BOX_PAD, node["label"], f_lbl, INK, ACCENT_DK)
        _block(d, PAD + BOX_PAD, y + BOX_PAD + 44 + 14, node["text"], f_body, TEXT, tw)
        y += nh
        if i < len(nodes) - 1:
            y = _arrow_down(d, y)
    return y


# ---------- type: compare ----------
def _compare(d, data, y):
    gap = 28
    col_w = (W - PAD * 2 - gap) // 2
    tw = col_w - BOX_PAD * 2
    f_h, f_body = _f(32, True), _f(30)
    cols = [("left", GREEN), ("right", RED)]
    # 各列の高さを測って高い方に揃える
    heights = []
    for key, _ in cols:
        c = data[key]
        h = BOX_PAD + 52 + 16
        for p in c["points"]:
            ls = _wrap(d, "・" + p, f_body, tw)
            a, de = f_body.getmetrics()
            h += len(ls) * (a + de + 8) + 12
        heights.append(h + BOX_PAD)
    box_h = max(heights)
    for idx, (key, col) in enumerate(cols):
        c = data[key]
        x0 = PAD + idx * (col_w + gap)
        d.rounded_rectangle([x0, y, x0 + col_w, y + box_h], radius=RADIUS, fill=CARD, outline=col, width=3)
        # ヘッダ帯
        d.rounded_rectangle([x0, y, x0 + col_w, y + 64], radius=RADIUS, fill=col)
        d.rectangle([x0, y + 32, x0 + col_w, y + 64], fill=col)
        d.text((x0 + BOX_PAD, y + 16), c["title"], font=f_h, fill=INK)
        yy = y + 64 + 20
        for p in c["points"]:
            yy += _block(d, x0 + BOX_PAD, yy, "・" + p, f_body, TEXT, tw, gap=8) + 12
    return y + box_h


# ---------- type: stat ----------
def _stat(d, data, y):
    stats = data["stats"]
    n = len(stats)
    gap = 24
    col_w = (W - PAD * 2 - gap * (n - 1)) // n
    box_h = 230
    f_val, f_unit, f_lab = _f(78, True), _f(34, True), _f(28)
    for i, s in enumerate(stats):
        x0 = PAD + i * (col_w + gap)
        col = GREEN if s.get("dir") == "up" else RED if s.get("dir") == "down" else ACCENT
        d.rounded_rectangle([x0, y, x0 + col_w, y + box_h], radius=RADIUS, fill=CARD, outline=CARD_LINE, width=2)
        val = s["value"]
        vw = d.textlength(val, font=f_val)
        uw = d.textlength(s.get("unit", ""), font=f_unit)
        cx = x0 + (col_w - vw - uw) // 2
        d.text((cx, y + 44), val, font=f_val, fill=col)
        if s.get("unit"):
            d.text((cx + vw + 6, y + 90), s["unit"], font=f_unit, fill=col)
        lab = s["label"]
        lw = d.textlength(lab, font=f_lab)
        d.text((x0 + (col_w - lw) // 2, y + 158), lab, font=f_lab, fill=SUBTLE)
    y += box_h + 32
    if data.get("context"):
        tw = W - PAD * 2 - BOX_PAD * 2
        lines = _wrap(d, data["context"], _f(32), tw)
        a, de = _f(32).getmetrics()
        ch = len(lines) * (a + de + 10) + BOX_PAD * 2
        d.rounded_rectangle([PAD, y, W - PAD, y + ch], radius=RADIUS, fill=CARD, outline=CARD_LINE, width=2)
        _block(d, PAD + BOX_PAD, y + BOX_PAD, data["context"], _f(32), TEXT, tw)
        y += ch
    return y


# ---------- type: timeline ----------
def _timeline(d, data, y):
    line_x = PAD + 20
    text_x = line_x + 44
    f_when, f_body = _f(30, True), _f(32)
    tw = W - PAD - text_x - 8
    events = data["events"]
    dots = []
    for ev in events:
        dots.append(y + 14)
        d.text((text_x, y), ev["when"], font=f_when, fill=ACCENT)
        y += f_when.getmetrics()[0] + 14
        y += _block(d, text_x, y, ev["text"], f_body, TEXT, tw) + 30
    # 縦線（テキストの左なので重ならない）→ 点を上に重ねる
    d.line([line_x, dots[0], line_x, dots[-1]], fill=CARD_LINE, width=4)
    for dy in dots:
        d.ellipse([line_x - 12, dy - 12, line_x + 12, dy + 12], fill=ACCENT)
    return y


_RENDERERS = {"flow": _flow, "compare": _compare, "stat": _stat, "timeline": _timeline}


def render_diagram(data: dict, out_path: str) -> str:
    img = Image.new("RGB", (W, CANVAS_H), BG)
    d = ImageDraw.Draw(img)
    y = PAD
    y = _header(d, data, y)
    renderer = _RENDERERS.get(data.get("type"), _flow)  # 不明typeはflowにフォールバック
    y = renderer(d, data, y)
    y = _footer(d, data, y)
    d.rectangle([0, 0, 8, y], fill=ACCENT)  # 左アクセント
    img = img.crop((0, 0, W, int(y) + PAD - 20))
    img.save(out_path)
    return out_path


# ===== サンプル描画 =====
if __name__ == "__main__":
    samples = {
        "flow": {
            "type": "flow", "tag": "市場メモ",
            "title": "FRBが政策金利を据え置き、年内利下げ観測は後退",
            "nodes": [
                {"label": "材料", "text": "FOMCが政策金利の据え置きを決定。声明でインフレの粘着性に改めて言及した。"},
                {"label": "市場の見方", "text": "早期利下げ期待が剥落し、米長期金利は上昇方向。ドル高・株式バリュエーションには逆風。"},
                {"label": "注目点", "text": "次のCPI・雇用統計でディスインフレ継続を確認できるか。金利感応度の高いグロース株の反応に注目。"},
            ],
            "hashtags": ["#米国株", "#金利"], "handle": "@singa9999",
        },
        "compare": {
            "type": "compare", "tag": "強気と弱気",
            "title": "エヌビディア決算後、市場の見方が二分",
            "left": {"title": "強気シナリオ", "points": [
                "データセンター需要は依然旺盛",
                "ガイダンスが市場予想を上回る",
                "AI設備投資サイクルは継続"]},
            "right": {"title": "弱気シナリオ", "points": [
                "成長率の鈍化が鮮明に",
                "高いバリュエーションに割高感",
                "在庫調整・競合の台頭リスク"]},
            "hashtags": ["#エヌビディア", "#米国株"], "handle": "@singa9999",
        },
        "stat": {
            "type": "stat", "tag": "決算速報",
            "title": "エヌビディア 第3四半期決算が市場予想を上回る",
            "stats": [
                {"value": "+62", "unit": "%", "label": "売上高 前年比", "dir": "up"},
                {"value": "351", "unit": "億$", "label": "四半期売上高", "dir": "up"},
                {"value": "+5.1", "unit": "%", "label": "時間外株価", "dir": "up"},
            ],
            "context": "データセンター部門が牽引。市場予想を上回る着地で、AI関連投資の持続性が改めて意識される展開。",
            "hashtags": ["#決算", "#エヌビディア"], "handle": "@singa9999",
        },
        "timeline": {
            "type": "timeline", "tag": "今週の予定",
            "title": "今週の重要イベント・経済指標カレンダー",
            "events": [
                {"when": "火曜", "text": "米10月CPI発表。コア指標の鈍化が続くかが最大の焦点。"},
                {"when": "水曜", "text": "FOMC議事要旨の公開。利下げ時期を巡る議論の温度感を確認。"},
                {"when": "木曜", "text": "新規失業保険申請件数。労働市場の減速度合いをチェック。"},
                {"when": "金曜", "text": "小売売上高。個人消費の底堅さが景気の鍵を握る。"},
            ],
            "hashtags": ["#経済指標", "#米国株"], "handle": "@singa9999",
        },
    }
    for name, data in samples.items():
        render_diagram(data, f"/home/claude/sample_{name}.png")
        print("rendered", name)
