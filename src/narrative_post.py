"""
narrative_post.py
編集長レイヤーの実行・投稿。

フロー:
  1. 4ソース集約（gather_signals）
  2. 編集長AIで①〜④生成（analyze_market）
  3. ④ post_value < 7 なら投稿しない（ゲート）
  4. ①②を画像化（render_narrative）
  5. ③ X投稿案をレビュー（review_tweet_with_openai）
  6. 画像＋③で投稿（post_tweet_with_image）

  画像生成のみ: python narrative_post.py
  実投稿:       python narrative_post.py post
"""

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


def run_narrative(post: bool = False, out_path: str = OUT_PATH):
    signals = gather_signals()
    if not any(signals.values()):
        logger.warning("シグナルが空。分析を中止します。")
        return None

    analysis = analyze_market(signals)
    _log_analysis(analysis)

    # ===== ④ 投稿価値ゲート =====
    pv = int(analysis.get("post_value", 0))
    if pv < POST_VALUE_THRESHOLD:
        logger.info(f"post_value {pv} < {POST_VALUE_THRESHOLD}。投稿不要のためスキップします。")
        # 画像だけは残す（確認用）
        render_narrative(analysis, out_path)
        return None

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
