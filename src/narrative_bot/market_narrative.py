"""
market_narrative.py
機関投資家向けストラテジスト兼・金融メディア編集長レイヤー。

4ソース（米国株ニュース / 経済指標 / 決算 / Reddit議論）を集約し、
「投資家が今何を気にしているか」を抽出する。市場全体・主要セクターに
影響する材料だけを採用し、ローカル/話題性のみ/日本ローカルは無視する。

AIには取得済みシグナルだけを渡し、存在しないニュース・銘柄・数値を作らせない。
出力JSON:
  narratives : 市場ナラティブTOP3
    [{theme, whats_happening, why_market_cares, tickers[], stance, impact(1-10)}]
  top_theme  : 今日の最重要テーマ {conclusion, rationale, tickers[]}
  x_post     : X投稿案（120字以内・結論先・株価影響明記・平易・煽らない）
  post_value : 投稿価値(1-10)。7未満は投稿しない
"""

import json
import logging

logger = logging.getLogger(__name__)

POST_VALUE_THRESHOLD = 7
X_POST_MAX = 120


def _gather_news(limit: int = 15) -> list[dict]:
    """既存 news.py の仕組みで直近ニュースを集約（1件選定ではなく一覧）。"""
    try:
        from news import RSS_FEEDS, fetch_feed, deduplicate, is_recent, score_item
    except Exception as e:
        logger.warning(f"news読み込み失敗: {e}")
        return []
    items = []
    for name, cfg in RSS_FEEDS.items():
        try:
            items.extend(fetch_feed(name, cfg))
        except Exception as e:
            logger.warning(f"news取得失敗 {name}: {e}")
    items = [i for i in items if is_recent(i, hours=36)]
    items.sort(key=score_item, reverse=True)
    items = deduplicate(items)[:limit]
    return [{"title": i.title, "source": i.source, "group": i.source_group} for i in items]


def _gather_events(limit: int = 12) -> list[dict]:
    """今週の経済指標・決算（weekly_events）。"""
    try:
        from weekly_events import fetch_weekly_events
        from weekly_normalizer import normalize_events
        raw = fetch_weekly_events()
        evs = normalize_events(raw)
        out = []
        for e in evs[:limit]:
            out.append({
                "date_jst": e["display_date_jst"], "time_jst": e["time_jst"],
                "category": e["category"], "title": e["title"],
            })
        return out
    except Exception as e:
        logger.warning(f"events取得失敗: {e}")
        return []


def _gather_reddit(limit: int = 15) -> list[dict]:
    try:
        from reddit_signals import fetch_reddit_signals
        posts = fetch_reddit_signals(limit_total=limit)
        return [{"subreddit": p["subreddit"], "title": p["title"],
                 "score": p["score"], "comments": p["comments"]} for p in posts]
    except Exception as e:
        logger.warning(f"reddit取得失敗: {e}")
        return []


def gather_signals() -> dict:
    """4ソースを集約して返す。"""
    signals = {
        "news": _gather_news(),
        "events": _gather_events(),
        "reddit": _gather_reddit(),
    }
    logger.info(
        "signals: news=%d / events=%d / reddit=%d",
        len(signals["news"]), len(signals["events"]), len(signals["reddit"]),
    )
    return signals


def _build_prompt(signals: dict) -> str:
    news = "\n".join(f'- [{n["group"]}] {n["title"]}（{n["source"]}）' for n in signals["news"]) or "（なし）"
    events = "\n".join(f'- {e["date_jst"]} {e["time_jst"]} [{e["category"]}] {e["title"]}' for e in signals["events"]) or "（なし）"
    reddit = "\n".join(f'- {r["subreddit"]} ↑{r["score"]} 💬{r["comments"]}: {r["title"]}' for r in signals["reddit"]) or "（なし）"

    return f"""あなたは機関投資家向けのストラテジスト兼・金融メディア編集長です。
目的はニュースの要約ではなく、「投資家が今何を気にしているか」を抽出し、
米国株式市場に大きな影響を与える材料だけを選別することです。

【採用ルール】市場全体または主要セクターに影響する内容のみ。以下は無視：
地方経済指標 / 地域ニュース / 影響の小さい企業IR / 話題性だけのニュース / 日本ローカル情報。

【取得済みシグナル（この中だけを根拠にする。存在しないニュース・銘柄・数値を作らない）】
■ニュース:
{news}

■経済指標・決算（JST）:
{events}

■Reddit議論（話題性）:
{reddit}

以下のJSONのみを返す（説明文・Markdown禁止）。日本語で記述。
{{
  "narratives": [
    {{
      "theme": "テーマ名（簡潔に）",
      "whats_happening": "何が起きているか（取得シグナルに基づく）",
      "why_market_cares": "なぜ市場が気にしているか",
      "tickers": ["影響銘柄のティッカー（シグナルから読み取れる範囲。無ければ空配列）"],
      "stance": "強気" or "弱気" or "中立",
      "impact": 1〜10の整数
    }}
  ],
  "top_theme": {{
    "conclusion": "今日の最重要テーマの結論（1〜2文）",
    "rationale": "根拠（取得シグナルに基づく）",
    "tickers": ["注目銘柄"]
  }},
  "x_post": "X投稿案。120文字以内。結論から書く。株価への影響を明記。専門用語を減らす。煽らない。投資助言・断定的予測・『買え/売れ/爆益/暴落確定/確実』は禁止。",
  "post_value": 1〜10の整数
}}

【post_value 基準】
10: 市場全体を動かす / 8-9: 主要セクターを動かす / 5-7: 個別株レベル / 1-4: 投稿不要。
narratives は最大3件。impact/post_value は取得シグナルの実態に対して誠実に。
シグナルが弱い日は無理にテーマを作らず、post_value を低く（投稿不要）してよい。"""


def analyze_market(signals: dict | None = None) -> dict:
    """編集長AIで①〜④を生成して返す。"""
    from post import get_openai_client, OPENAI_GENERATE_MODEL

    if signals is None:
        signals = gather_signals()

    prompt = _build_prompt(signals)
    client = get_openai_client()
    resp = client.chat.completions.create(
        model=OPENAI_GENERATE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=3500,
        response_format={"type": "json_object"},
        reasoning_effort="minimal",
    )
    data = json.loads(resp.choices[0].message.content or "{}")

    # 正規化・防御
    data.setdefault("narratives", [])
    data["narratives"] = data["narratives"][:3]
    data.setdefault("top_theme", {"conclusion": "", "rationale": "", "tickers": []})
    data.setdefault("x_post", "")
    data.setdefault("post_value", 0)
    try:
        data["post_value"] = int(data["post_value"])
    except Exception:
        data["post_value"] = 0
    # X投稿は120字以内に
    if len(data["x_post"]) > X_POST_MAX:
        data["x_post"] = data["x_post"][:X_POST_MAX - 1].rstrip() + "…"
    return data
