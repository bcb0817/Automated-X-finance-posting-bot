"""
weekly_post.py （MVP）
取得済みイベント（サンプル）→ 正規化 → 選別（出所確認・米株関連・上限）→ 画像生成。
すべて JST 基準。AIはイベントを創作しない（選別は決定論）。
"""

import logging
from collections import defaultdict
from datetime import datetime

from weekly_normalizer import normalize_events
from weekly_selector import select_weekly_events
from weekly_renderer import render_weekly

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUT_PATH = "/tmp/weekly_events.png"


# ===== MVP用サンプル（取得済み生データ想定。source_name/source_url を持つ）=====
# ※ 出所のある本物のイベントと、除外されるべきAI創作的イベントを混在させて挙動確認
SAMPLE_RAW_EVENTS = [
    # 米国マクロ（最優先）
    {"date": "2026-06-22", "country": "US", "category": "統計", "time_et": "10:00",
     "title": "米ISM製造業景況指数", "source_name": "ISM", "source_url": "https://www.ismworld.org/"},
    {"date": "2026-06-23", "country": "US", "category": "統計", "time_et": "08:30",
     "title": "米CPI（消費者物価指数）", "source_name": "BLS", "source_url": "https://www.bls.gov/"},
    {"date": "2026-06-24", "country": "US", "category": "統計", "time_et": "08:30",
     "title": "米耐久財受注", "source_name": "Census Bureau", "source_url": "https://www.census.gov/"},
    # 米国引け後（AMC）→ JST翌日 早朝
    {"date": "2026-06-24", "country": "US", "category": "企業", "timing": "after market close",
     "title": "Micron Technology 決算発表", "note": "ガイダンス次第で半導体全体に波及",
     "source_name": "Nasdaq Earnings", "source_url": "https://www.nasdaq.com/market-activity/earnings"},
    # ET 14:00 → JST翌日 03:00
    {"date": "2026-06-24", "country": "US", "category": "中銀", "time_et": "14:00",
     "title": "FOMC 議事要旨 公表", "source_name": "Federal Reserve", "source_url": "https://www.federalreserve.gov/"},
    # ET 8:30 → JST 21:30 同日
    {"date": "2026-06-25", "country": "US", "category": "統計", "time_et": "08:30",
     "title": "米PCEデフレーター（コア）", "note": "FRBが重視するインフレ指標",
     "source_name": "BEA", "source_url": "https://www.bea.gov/"},
    {"date": "2026-06-25", "country": "US", "category": "統計", "time_et": "08:30",
     "title": "米新規失業保険申請件数", "source_name": "DOL", "source_url": "https://www.dol.gov/"},
    # UTC 12:15 → JST 21:15（中優先）
    {"date": "2026-06-25", "country": "EU", "category": "中銀", "time_utc": "12:15",
     "title": "ECB理事会 政策金利発表", "source_name": "ECB", "source_url": "https://www.ecb.europa.eu/"},
    # 日銀（中優先）
    {"date": "2026-06-26", "country": "JP", "category": "中銀", "time_jst": "12:00",
     "title": "日銀 金融政策決定会合 結果公表", "source_name": "日本銀行", "source_url": "https://www.boj.or.jp/"},
    # 米国寄り前（BMO）一般消費決算（mid）
    {"date": "2026-06-26", "country": "US", "category": "企業", "timing": "before market open",
     "title": "ナイキ 決算発表", "source_name": "Nasdaq Earnings", "source_url": "https://www.nasdaq.com/market-activity/earnings"},

    # ↓↓↓ 除外されるべきサンプル ↓↓↓
    {"date": "2026-06-26", "country": "JP", "category": "統計", "time_jst": "08:30",
     "title": "東京都区部CPI", "source_name": "総務省", "source_url": "https://www.stat.go.jp/"},
    {"date": "2026-06-22", "country": "JP", "category": "市場", "time_jst": "未定",
     "title": "東京市場 連休明け（海外材料を消化）", "tentative": True},
    {"date": "2026-06-23", "country": "JP", "category": "企業", "time_jst": "10:00",
     "title": "トヨタ 定時株主総会", "source_name": "適時開示", "source_url": "https://www.release.tdnet.info/"},
]


def _range_label(date_strs: list[str]) -> str:
    ds = sorted(date_strs)
    a = datetime.strptime(ds[0], "%Y-%m-%d")
    b = datetime.strptime(ds[-1], "%Y-%m-%d")
    if a.month == b.month:
        return f"{a.year}年{a.month}月{a.day}日〜{b.day}日"
    return f"{a.year}年{a.month}月{a.day}日〜{b.month}月{b.day}日"


def _md(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{d.month}/{d.day}"


def _weekday(date_str: str) -> str:
    wd = ["月", "火", "水", "木", "金", "土", "日"]
    return wd[datetime.strptime(date_str, "%Y-%m-%d").weekday()]


def build_weekly_schedule(raw_events: list[dict]) -> dict:
    events = normalize_events(raw_events)

    # 変換結果ログ（要件9）
    for ev in events:
        logger.info(
            "event: source_date=%s / timing=%r / display_date_jst=%s / time_jst=%s / "
            "verified=%s / source=%s / title=%s",
            ev["source_date"], ev["timing"], ev["display_date_jst"], ev["time_jst"],
            ev["verified"], ev["source_name"] or ev["source_url"], ev["title"],
        )

    # 出所確認・米株関連・上限で選別（除外理由はログに出る）
    selected = select_weekly_events(events, max_total=10, max_per_day=3)

    if not selected:
        logger.warning("掲載できる確認済みイベントがありません")
        return {"title": "今週の注目イベント", "month_label": "", "days": []}

    by_day = defaultdict(list)
    for ev in selected:
        by_day[ev["display_date_jst"]].append(ev)

    days = []
    for date in sorted(by_day):
        days.append({"date": _md(date), "weekday": _weekday(date), "events": by_day[date]})

    return {
        "title": "今週の注目イベント",
        "month_label": _range_label(list(by_day.keys())),
        "days": days,
    }


def generate_weekly_image(raw_events: list[dict], out_path: str = OUT_PATH) -> str:
    schedule = build_weekly_schedule(raw_events)
    if not schedule["days"]:
        logger.warning("画像生成をスキップ（掲載イベント0件）")
        return ""
    n = sum(len(d["events"]) for d in schedule["days"])
    logger.info(f"週間スケジュール生成: {len(schedule['days'])}日 / {n}イベント / 期間={schedule['month_label']}")
    path = render_weekly(schedule, out_path)
    logger.info(f"画像を出力しました: {path}")
    return path


if __name__ == "__main__":
    generate_weekly_image(SAMPLE_RAW_EVENTS)
