"""테스트용 합성 OHLCV 생성기.

    df = make_ohlcv([(0, 100), (120, 160), (150, 128), (200, 158)], seed=1)
    df = set_bar(df, -1, open=158, high=172, low=157, close=171, volume=8e6)
    ctx = make_context(df, rs=92)

waypoints 는 (거래일 인덱스, 종가) 목록이며 사이를 코사인 보간한다. 노이즈는 경로 주변
i.i.d. 로 더해져 웨이포인트 형태가 보존된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from chart_screener.config import Config
from chart_screener.market import CONFIRMED, MarketState
from chart_screener.patterns.base import StockContext


def _interp(waypoints: list[tuple[int, float]], n: int, smooth: bool) -> np.ndarray:
    xs = np.array([w[0] for w in waypoints], dtype=float)
    ys = np.array([w[1] for w in waypoints], dtype=float)
    out = np.empty(n)
    for i in range(n):
        if i <= xs[0]:
            out[i] = ys[0]
            continue
        if i >= xs[-1]:
            out[i] = ys[-1]
            continue
        k = np.searchsorted(xs, i, side="right") - 1
        t = (i - xs[k]) / (xs[k + 1] - xs[k])
        if smooth:
            t = (1 - np.cos(np.pi * t)) / 2
        out[i] = ys[k] + (ys[k + 1] - ys[k]) * t
    return out


def make_ohlcv(
    waypoints: list[tuple[int, float]],
    *,
    n: int | None = None,
    start: str = "2023-01-02",
    noise: float = 0.006,
    wick: float = 0.008,
    seed: int = 0,
    vol_base: float = 1_000_000,
    vol_segments: list[tuple[int, int, float]] | None = None,
    smooth: bool = True,
) -> pd.DataFrame:
    """vol_segments: [(시작 인덱스, 끝 인덱스(포함X), 배수)] 로 구간별 거래량 배수 지정."""
    rng = np.random.default_rng(seed)
    n = n or int(waypoints[-1][0]) + 1
    path = _interp(waypoints, n, smooth)
    close = path * (1 + rng.normal(0, noise, n))
    prev = np.concatenate([[close[0]], close[:-1]])
    open_ = prev * (1 + rng.normal(0, noise / 2, n))
    hi = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, wick, n)))
    lo = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, wick, n)))
    vol = vol_base * rng.lognormal(0, 0.25, n)
    for s, e, m in vol_segments or []:
        vol[s:e] *= m
    idx = pd.bdate_range(start, periods=n)
    df = pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close, "volume": vol.round()}, index=idx)
    return add_value(df)


def add_value(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["value"] = (df["high"] + df["low"] + df["close"]) / 3.0 * df["volume"]
    return df


def set_bar(df: pd.DataFrame, i: int, **kw) -> pd.DataFrame:
    """i 번째 봉의 open/high/low/close/volume 일부를 덮어쓰고 OHLC 정합성·거래대금 재계산."""
    df = df.copy()
    pos = i if i >= 0 else len(df) + i
    for k, v in kw.items():
        df.iloc[pos, df.columns.get_loc(k)] = v
    row = df.iloc[pos]
    df.iloc[pos, df.columns.get_loc("high")] = max(row["open"], row["high"], row["low"], row["close"])
    df.iloc[pos, df.columns.get_loc("low")] = min(row["open"], row["high"], row["low"], row["close"])
    return add_value(df)


def flat_index(n: int, start: str = "2023-01-02", drift: float = 0.0002) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    c = 1000 * (1 + drift) ** np.arange(n)
    return pd.DataFrame({"open": c, "high": c * 1.003, "low": c * 0.997, "close": c, "volume": 1e6}, index=idx)


def confirmed_market(date: str = "2024-01-01") -> MarketState:
    return MarketState(
        name="KOSPI", state=CONFIRMED, label="상승 확인", date=date, close=1000.0,
        above_21ema=True, above_50sma=True, above_200sma=True, sma50_rising=True, sma200_rising=True,
        distribution_days=1,
    )


def make_context(df: pd.DataFrame, *, rs: float | None = 90, code: str = "TEST", name: str = "테스트",
                 market: str = "KOSPI", index_df: pd.DataFrame | None = None, cfg: Config | None = None,
                 market_state: MarketState | None = None, info: dict | None = None) -> StockContext:
    if index_df is None:
        index_df = flat_index(len(df), start=str(df.index[0].date()) if len(df) else "2023-01-02")
    rs_hist = pd.Series(rs, index=df.index) if rs is not None else None
    return StockContext(
        code=code, name=name, market=market, df=df, cfg=cfg or Config(), index_df=index_df,
        rs_rating=rs, rs_rating_hist=rs_hist, market_state=market_state or confirmed_market(),
        info=info or {"market_cap": 1e12},
    )
