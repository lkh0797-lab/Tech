"""시장 폭(breadth): 지수 밑에서 종목 다수가 함께 오르는지.

    b = compute_breadth(ud.ohlcv, cfg.big_value_threshold, markets)   # {'ALL','KOSPI','KOSDAQ'}
    b["KOSDAQ"]["nh_nl_10d"], b["ALL"]["pct_above_50"]

정의 (일자별, 전 종목 일봉 캐시를 날짜 × 종목 표로 펼쳐 벡터 연산)
- 대상(유동 종목): 그날 20일 평균 거래대금 ≥ ``min_avg_value``(기본 Config.universe.min_avg_value_20d = 10억)
  이고 종가 ≥ ``min_price``(1,000원). 동전주·무거래 종목이 신저가 수를 부풀리지 않게 한다.
- 52주 신고가/신저가: 종가가 직전 252 거래일 종가 최고/최저를 넘어선 종목 수. 거래정지 등으로 빈 날이
  있어도 252일 창 안에 240일 이상 있으면 인정(신규 상장 1년 미만은 제외).
- nh_nl = 신고가 - 신저가, nh_nl_10d = 그 10일 평균.
- pct_above_50 / pct_above_200: 종가 > 50일/200일 이동평균인 유동 종목 비율(%, 0~100).
- big_value_up: 거래대금 ≥ big_value(300억) 이면서 상승 마감한 종목 수 (유동성 조건과 무관).
일자 축은 지수(KOSPI) 거래일이 있으면 그것을, 없으면 전 종목 날짜의 합집합을 쓴다.
장중에 받은 데이터면 마지막 날의 거래대금 기반 값(big_value_up, 유동성 판정)은 그 시각까지의 누적치다.
과거 각 날짜 값은 그날까지의 데이터만 쓰므로(롤링·shift) 백테스트에서 그대로 써도 미래 참조가 없다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config

GROUPS = ("ALL", "KOSPI", "KOSDAQ")
NH_WINDOW = 252          # 52주
NH_MIN_PERIODS = 240     # 52주 창 안 최소 유효 봉 수
COLUMNS = ["universe", "new_highs", "new_lows", "nh_nl", "nh_nl_10d", "pct_above_50", "pct_above_200",
           "big_value_up"]


def _wide(ohlcv: dict[str, pd.DataFrame], col: str, dates: pd.DatetimeIndex | None) -> pd.DataFrame:
    cols = {c: d[col][~d.index.duplicated(keep="last")] for c, d in ohlcv.items() if d is not None and len(d)}
    if not cols:
        return pd.DataFrame()
    frame = pd.concat(cols, axis=1)
    frame = frame.sort_index()
    if dates is not None:
        frame = frame.reindex(dates)
    return frame.astype(float)


def breadth_history(ohlcv: dict[str, pd.DataFrame], big_value: float,
                    markets: dict[str, str] | None = None, *, min_avg_value: float | None = None,
                    min_price: float | None = None,
                    dates: pd.DatetimeIndex | None = None) -> dict[str, pd.DataFrame]:
    """시장별 일자 × 지표 표 {'ALL','KOSPI','KOSDAQ': DataFrame(COLUMNS)}.

    markets: 종목코드 → 'KOSPI'|'KOSDAQ' (없으면 ALL 만 의미 있음; 시장별 표는 빈 표)."""
    uf = Config().universe
    min_avg_value = uf.min_avg_value_20d if min_avg_value is None else min_avg_value
    min_price = uf.min_price if min_price is None else min_price
    empty = {g: pd.DataFrame(columns=COLUMNS, dtype=float) for g in GROUPS}
    if not ohlcv:
        return empty
    close = _wide(ohlcv, "close", dates)
    value = _wide(ohlcv, "value", dates)
    if close.empty:
        return empty

    prev_close = close.ffill().shift(1)          # 정지일 다음 날도 직전 거래일 종가와 비교
    hi52 = close.rolling(NH_WINDOW, min_periods=NH_MIN_PERIODS).max().shift(1)
    lo52 = close.rolling(NH_WINDOW, min_periods=NH_MIN_PERIODS).min().shift(1)
    sma50 = close.rolling(50, min_periods=45).mean()
    sma200 = close.rolling(200, min_periods=180).mean()
    val20 = value.rolling(20, min_periods=15).mean()

    liquid = (val20 >= min_avg_value) & (close >= min_price)
    nh = liquid & (close > hi52)
    nl = liquid & (close < lo52)
    has50, has200, has52 = liquid & sma50.notna(), liquid & sma200.notna(), liquid & hi52.notna()
    a50, a200 = has50 & (close > sma50), has200 & (close > sma200)
    big = (value >= big_value) & (close > prev_close)

    codes = close.columns
    mk = pd.Series(markets or {}, dtype=object).reindex(codes)
    out: dict[str, pd.DataFrame] = {}
    for g in GROUPS:
        cols = np.ones(len(codes), bool) if g == "ALL" else (mk == g).to_numpy()

        def cnt(m: pd.DataFrame) -> pd.Series:
            return pd.Series(m.to_numpy()[:, cols].sum(axis=1), index=close.index, dtype=float)

        if not cols.any():
            out[g] = pd.DataFrame(columns=COLUMNS, dtype=float)
            continue
        n_liq, n_h, n_l = cnt(liquid), cnt(nh), cnt(nl)
        d50, d200, d52 = cnt(has50), cnt(has200), cnt(has52)
        n_h, n_l = n_h.where(d52 > 0), n_l.where(d52 > 0)   # 52주 이력이 아직 없는 초기 구간은 결측
        t = pd.DataFrame({
            "universe": n_liq, "new_highs": n_h, "new_lows": n_l, "nh_nl": n_h - n_l,
            "pct_above_50": (cnt(a50) / d50.where(d50 > 0)) * 100,
            "pct_above_200": (cnt(a200) / d200.where(d200 > 0)) * 100,
            "big_value_up": cnt(big),
        })
        t["nh_nl_10d"] = t["nh_nl"].rolling(10, min_periods=5).mean()
        out[g] = t[t["universe"] > 0][COLUMNS]
    return out


def _round(x, nd: int = 1):
    return None if x is None or x != x else round(float(x), nd)


def _int(x):
    return None if x is None or x != x else int(x)


def _row_dict(t: pd.DataFrame, k: int) -> dict:
    r = t.iloc[k]
    return {
        "date": f"{t.index[k]:%Y-%m-%d}", "universe": _int(r["universe"]),
        "new_highs": _int(r["new_highs"]), "new_lows": _int(r["new_lows"]), "nh_nl": _int(r["nh_nl"]),
        "nh_nl_10d": _round(r["nh_nl_10d"]), "pct_above_50": _round(r["pct_above_50"]),
        "pct_above_200": _round(r["pct_above_200"]), "big_value_up": _int(r["big_value_up"]),
    }


def summarize_history(hist: dict[str, pd.DataFrame], days: int = 60) -> dict:
    """breadth_history → compute_breadth 형식 (마지막 날 값 + 최근 days 일 시계열)."""
    out = {}
    for g in GROUPS:
        t = hist.get(g)
        if t is None or t.empty:
            continue
        d = _row_dict(t, len(t) - 1)
        tail = t.iloc[-days:]
        d["series"] = {
            "dates": [f"{x:%Y-%m-%d}" for x in tail.index],
            "nh_nl": [_int(x) for x in tail["nh_nl"]],
            "pct_above_50": [_round(x) for x in tail["pct_above_50"]],
        }
        out[g] = d
    return out


def compute_breadth(ohlcv: dict[str, pd.DataFrame], big_value: float, markets: dict[str, str] | None = None,
                    days: int = 60, **kw) -> dict:
    """시장 폭 요약: {'ALL'|'KOSPI'|'KOSDAQ': {'date','universe','new_highs','new_lows','nh_nl','nh_nl_10d',
    'pct_above_50','pct_above_200','big_value_up','series': {'dates','nh_nl','pct_above_50'}}}.

    pct_* 는 0~100 퍼센트. 데이터가 없는 시장 키는 빠진다. kw 는 breadth_history 로 전달."""
    return summarize_history(breadth_history(ohlcv, big_value, markets, **kw), days)


def breadth_at(hist: dict[str, pd.DataFrame], market: str, date) -> dict | None:
    """breadth_history 표에서 date(포함) 시점의 마지막 값 (시계열 없이). 백테스트용."""
    t = hist.get(market) if hist else None
    if t is None or t.empty:
        return None
    k = int(t.index.searchsorted(pd.Timestamp(date), side="right")) - 1
    return _row_dict(t, k) if k >= 0 else None
