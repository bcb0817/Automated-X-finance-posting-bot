# リファクタ後の構成

```
src/
  common/            # 共通処理（切り出し）
    x_client.py        ← X投稿（tweepy v1.1/v2、post_tweet, post_tweet_with_image）
    openai_client.py   ← OpenAI（get_openai_client, generate_by_openai, review_tweet_with_openai, モデル定数）
    safety.py          ← NGワード, JST夜間ガード, 文字数/安全チェック
  news_bot/          # 通常ニュースBot
    post.py            ← エントリ（python news_bot/post.py <mode>）
    news.py
    diagram_post.py
    diagram_image.py
    posted_history.py
  weekly_bot/        # 週次イベントBot
    weekly_post.py     ← エントリ（python weekly_bot/weekly_post.py [post]）
    weekly_normalizer.py
    weekly_selector.py
    weekly_renderer.py
    weekly_events.py
  narrative_bot/     # 編集長レイヤー（市場ナラティブ）
    narrative_post.py  ← エントリ（python narrative_bot/narrative_post.py [post]）
    market_narrative.py
    narrative_renderer.py
    reddit_signals.py
  scheduler/
    generate_schedule.py  ← post.yml を再生成
data/
  posted_history.json   # リポジトリ直下のまま（移動しない）
.github/workflows/
  post.yml      # 通常Bot（generate_scheduleが再生成）
  reset.yml     # 毎日 generate_schedule を実行
  weekly.yml    # 週次Bot
  narrative.yml # 編集長レイヤー
```

## 仕組み（import が壊れない理由）
- 各エントリ（post.py / weekly_post.py / narrative_post.py / generate_schedule.py）の先頭に
  「src配下の全機能ディレクトリを sys.path に追加するブートストラップ」を入れている。
  → 移動後も `from posted_history import ...` `from news import ...` 等が無修正で動く。
- post.py は common/ の関数を再エクスポートするので、weekly/narrative の `from post import ...` も従来通り動く。

## 変更したファイル
- 【新規】common/x_client.py, common/openai_client.py, common/safety.py
- 【改修】news_bot/post.py（共通処理を common から import、ブートストラップ追加）
- 【1行修正】news_bot/posted_history.py（parent.parent → parent.parent.parent）
- 【2点修正】scheduler/generate_schedule.py（同上のパス修正＋テンプレを python news_bot/post.py に）
- 【先頭にブートストラップ追加】weekly_bot/weekly_post.py, narrative_bot/narrative_post.py
- 【ワークフロー】post.yml / reset.yml / weekly.yml / narrative.yml を新パスに

## 変更なしで「移動だけ」したファイル
news_bot/{news.py, diagram_post.py, diagram_image.py}
weekly_bot/{weekly_normalizer.py, weekly_selector.py, weekly_renderer.py, weekly_events.py}
narrative_bot/{market_narrative.py, narrative_renderer.py, reddit_signals.py}
