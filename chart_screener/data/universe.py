"""KOSPI/KOSDAQ 종목 목록 (네이버 모바일 증권 API).

반환 컬럼:
    code, name, market, close, change_pct, volume, value(원), market_cap(원),
    traded_at(그 종목의 마지막 체결 시각, KST), market_open(bool),
    fetched_at(이 스냅샷을 받은 시각, tz-aware KST — 전 종목 동일)

장중 미완성 봉 판정은 fetched_at 으로 한다. traded_at 은 종목별 마지막 체결 시각이라
거래가 뜸한 종목은 장 마감 후에도 12:02 같은 장중 시각이 남는다. market_open 도
시간외 거래 시간까지 OPEN 으로 내려오므로 판정에 쓰지 않는다.
"""
from __future__ import annotations

import re

import pandas as pd

from ..config import DataConfig
from . import http
from .ohlcv import now_kst

_URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100"
_SPAC_RE = re.compile(r"스팩|\d+호$")


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return float("nan")


def fetch_universe(cfg: DataConfig | None = None) -> pd.DataFrame:
    cfg = cfg or DataConfig()
    fetched_at = pd.Timestamp(now_kst())
    rows: list[dict] = []
    for market in cfg.markets:
        page = 1
        while True:
            js = http.get(_URL.format(market=market, page=page)).json()
            stocks = js.get("stocks") or []
            for s in stocks:
                rows.append({
                    "code": s["itemCode"],
                    "name": s["stockName"],
                    "market": market,
                    "end_type": s.get("stockEndType"),
                    "trading": (s.get("tradeStopType") or {}).get("name") == "TRADING",
                    "close": _num(s.get("closePriceRaw")),
                    "change_pct": _num(s.get("fluctuationsRatio")),
                    "volume": _num(s.get("accumulatedTradingVolumeRaw")),
                    "value": _num(s.get("accumulatedTradingValueRaw")),
                    "market_cap": _num(s.get("marketValueRaw")),
                    "traded_at": s.get("localTradedAt"),
                    "market_open": s.get("marketStatus") == "OPEN",
                })
            if not stocks or page * 100 >= int(js.get("totalCount", 0)):
                break
            page += 1

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[df["end_type"] == "stock"]
    if cfg.exclude_preferred:
        df = df[df["code"].str.endswith("0")]
    if cfg.exclude_spac:
        df = df[~df["name"].str.contains(_SPAC_RE)]
    if cfg.exclude_reits:
        df = df[~df["name"].str.contains(r"리츠|리얼티\d*$|REIT", regex=True)]  # 맵스리얼티1 등 이름에 '리츠' 없는 리츠
    df = df[df["trading"]]
    df = df.drop(columns=["end_type", "trading"]).drop_duplicates("code")
    df["traded_at"] = pd.to_datetime(df["traded_at"], errors="coerce")
    df["fetched_at"] = fetched_at
    return df.reset_index(drop=True)
