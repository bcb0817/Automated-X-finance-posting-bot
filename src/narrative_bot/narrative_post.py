"""
narrative_post.py
編集長レイヤーの実行・投稿。

フロー:
  1. 4ソース集約（gather_signals）
  2. 編集長AIで①〜④生成（analyze_market）
  3. ④ post_value < 8 なら投稿しない（ゲート）
  4. ①②を画像化（render_narrative）
  5. ③ X投稿案をレビュー（review_tweet_with_openai）
  6. 画像＋③で投稿（post_tweet_with_image）

  画像生成のみ: python narrative_post.py
  実投稿:       python narrative_post.py post
"""

import os
import sys

# --- パス・ブートストラップ: src 配下の各機能ディレクトリを import 可能にする ---
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../src
for _sub in ("common", "news_bot", "weekly_bot", "narrative_bot", "scheduler"):
    _p = os.path.join(_SRC_DIR, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import sys
import json
import logging

from market_narrative import gather_signals, analyze_market, POST_VALUE_THRESHOLD, X_POST_MAX
from narrative_renderer import render_narrative

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUT_PATH = "/tmp/narrative.png"


def _log_analysis(a: dict) -> None:
    logger.info("post_value=%s（閾値=%d）", a.get("post_value"), POST_VALUE_THRESHOLD)
    for i, n in enumerate(a.get("narratives", []), 1):
        logger.info("narrative#%d: %s / stance=%s / impact=%s / tickers=%s",
                    i, n.get("theme"), n.get("stance"), n.get("impact"),
                    ",".join(n.get("tickers", []) or []))
    logger.info("top_theme=%s", (a.get("top_theme", {}) or {}).get("conclusion", ""))
    logger.info("x_post=%r (len=%d)", a.get("x_post", ""), len(a.get("x_post", "")))


from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# 米国市場（NYSE/NASDAQ）の全休場日。出所: NYSE/ICE 公式カレンダー。
# 半日立会い（早期クローズ）は通常営業扱いとし、ここには含めない。
# ※ AIの推測ではなく公式日程の転記。年に1回、翌年分を更新すること。
US_MARKET_HOLIDAYS = {
    # 2026年（10日）
    "2026-01-01",  # 元日
    "2026-01-19",  # キング牧師記念日
    "2026-02-16",  # ワシントン誕生日（大統領の日）
    "2026-04-03",  # グッドフライデー
    "2026-05-25",  # メモリアルデー
    "2026-06-19",  # ジューンティーンス
    "2026-07-03",  # 独立記念日の振替（7/4が土曜のため）
    "2026-09-07",  # レイバーデー
    "2026-11-26",  # サンクスギビング
    "2026-12-25",  # クリスマス
}


def _is_us_market_holiday() -> tuple[bool, str]:
    """米国東部時間(ET)の「今日」が市場の祝日休場日か判定。
    （週末はcronが平日のみ=1-5のため対象外。手動テストは週末でも可能にする）"""
    try:
        et_today = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        # zoneinfoが無い環境向けフォールバック（夏時間 -4h 固定で近似）
        et_today = (datetime.now(timezone.utc) - timedelta(hours=4)).date()
    iso = et_today.isoformat()
    if iso in US_MARKET_HOLIDAYS:
        return True, f"米国市場の休場日（ET {iso}）"
    return False, ""


def run_narrative(post: bool = False, out_path: str = OUT_PATH):
    # 米国市場の休場日（週末・祝日）は実行しない
    is_holiday, holiday_reason = _is_us_market_holiday()
    if is_holiday:
        logger.info(f"{holiday_reason} のため市場ナラティブは実行しません。")
        return None

    signals = gather_signals()
    if not any(signals.values()):
        logger.warning("シグナルが空。分析を中止します。")
        return None

    analysis = analyze_market(signals)
    _log_analysis(analysis)

    # ===== ④ 投稿価値ゲート（早期スキップ：画像生成より前で判定しコスト削減）=====
    post_value = int(analysis.get("post_value", 0))
    should_post = post_value >= POST_VALUE_THRESHOLD
    skip_reason = "" if should_post else "投稿価値が基準未満"
    logger.info(
        f"post_value={post_value} / threshold={POST_VALUE_THRESHOLD} / "
        f"should_post={str(should_post).lower()} / skip_reason={skip_reason or '-'}"
    )
    if not should_post:
        logger.info(
            f"post_value={post_value}（閾値={POST_VALUE_THRESHOLD}）のため投稿スキップ"
        )
        return None   # 画像生成・X投稿に進まず即終了（OpenAIコスト削減）

    image_path = render_narrative(analysis, out_path)

    if not post:
        logger.info("画像生成のみ（postモードではないため投稿しません）")
        return image_path

    # ===== ③ X投稿（レビュー後）=====
    from post import review_tweet_with_openai, post_tweet_with_image, NG_WORDS

    caption = analysis.get("x_post", "").strip()
    if len(caption) > X_POST_MAX:
        caption = caption[:X_POST_MAX - 1].rstrip() + "…"
    if not caption:
        logger.warning("X投稿案が空のため投稿中止")
        return None

    for w in NG_WORDS:
        if w in caption:
            logger.warning(f"NGワード検出のため投稿中止: {w}")
            return None

    review = review_tweet_with_openai(caption, "市場ナラティブ（編集長レイヤー）", "複数ソース集約")
    logger.info("review_result=%s", json.dumps(review, ensure_ascii=False))
    if not review.get("ok_to_post", False):
        logger.warning(f"AIレビューにより投稿中止: {review.get('reason','理由なし')}")
        return None

    tweet_id = post_tweet_with_image(caption, image_path)
    logger.info(f"市場ナラティブ投稿成功: {tweet_id}")
    return tweet_id


if __name__ == "__main__":
    run_narrative(post=(len(sys.argv) > 1 and sys.argv[1] == "post"))
