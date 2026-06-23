"""見出し(headline)と投稿文(caption)の生成。"""
from __future__ import annotations

import pandas as pd


def format_usd(value: float) -> str:
    """数値を $1.5T / $850B / $120M 形式に整形(絶対値)。"""
    v = abs(value)
    if v >= 1e12:
        return f"${v / 1e12:.1f}T"
    if v >= 1e9:
        return f"${v / 1e9:.0f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"


def make_headline(total_change: float) -> str:
    """画像上部・投稿冒頭用の見出しを生成。

    例: JUST IN: $1.5T erased from the S&P 500 at the open
    """
    verb = "erased from" if total_change < 0 else "added to"
    return f"JUST IN: {format_usd(total_change)} {verb} the S&P 500 at the open"


def make_caption(
    df: pd.DataFrame,
    total_change: float,
    sector_summary: pd.DataFrame,
    n_movers: int = 5,
) -> str:
    """投稿文を生成する。

    含める要素:
        - 全体の時価総額変化
        - 売り/買いの中心セクター
        - 主な下落銘柄
        - ハッシュタグ少なめ
    """
    amount = format_usd(total_change)
    direction = "wiped off" if total_change < 0 else "added to"

    # 売り/買いの中心セクター(sector_summary は昇順)
    worst_sector = sector_summary.iloc[0]
    best_sector = sector_summary.iloc[-1]

    # 主な下落銘柄(下落率の大きい順)
    decliners = (
        df[df["percent_change"] < 0]
        .sort_values("percent_change")
        .head(n_movers)
    )
    mover_lines = ", ".join(
        f"${r.ticker} {r.percent_change * 100:+.1f}%" for r in decliners.itertuples()
    )

    lines = [
        f"{amount} {direction} the S&P 500 at the open.",
        "",
        f"Selling led by {worst_sector['sector']} "
        f"({format_usd(worst_sector['market_cap_change'])}).",
        f"Buying led by {best_sector['sector']} "
        f"({format_usd(best_sector['market_cap_change'])}).",
    ]
    if mover_lines:
        lines += ["", f"Biggest drags: {mover_lines}"]
    lines += ["", "#stocks #SP500"]

    return "\n".join(lines)
