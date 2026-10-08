"""기술적 지표 · 스윙 포인트 공용 함수.

모든 함수는 '그 날까지의 데이터'만 사용한다(미래 참조 없음). 단, 스윙 포인트
(fractal) 는 정의상 오른쪽 ``right`` 봉이 지나야 확정되므로 확정 여부를 함께 반환한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_YEAR = 252


# ---------------------------------------------------------------- 이동평균 / 변동성
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1)
    return tr.max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR."""
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return atr(df, n) / df["close"]


def bb_width(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    """볼린저 밴드 폭 (상단-하단)/중심선."""
    m = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return (2 * k * sd) / m


def slope_pct(s: pd.Series, n: int) -> float:
    """최근 n개 값의 선형회귀 기울기를 '평균 대비 하루 %'로 반환."""
    y = s.dropna().iloc[-n:].to_numpy(dtype=float)
    if len(y) < max(3, n // 2):
        return float("nan")
    x = np.arange(len(y), dtype=float)
    b = np.polyfit(x, y, 1)[0]
    return float(b / np.mean(y))


def is_rising(s: pd.Series, lookback: int) -> bool:
    """s 가 lookback 일 전보다 높은지 (이동평균 상승 추세 판정용)."""
    s = s.dropna()
    if len(s) <= lookback:
        return False
    return bool(s.iloc[-1] > s.iloc[-1 - lookback])


# ---------------------------------------------------------------- 거래량
def volume_ratio(vol: pd.Series, n: int = 50) -> pd.Series:
    """당일 거래량 / '전일까지' n일 평균 거래량."""
    return vol / sma(vol, n).shift(1)


def up_down_volume_ratio(df: pd.DataFrame, n: int = 50, vol: pd.Series | None = None) -> float:
    """최근 n일 상승일 거래량 합 / 하락일 거래량 합 (O'Neil U/D ratio, >1 매집 우위)."""
    vol = (df["volume"] if vol is None else vol).iloc[-n:]
    chg = df["close"].diff().iloc[-n:]
    up = vol[chg > 0].sum()
    down = vol[chg < 0].sum()
    return float(up / down) if down > 0 else float("inf")


# ---------------------------------------------------------------- 캔들
def candle_frame(df: pd.DataFrame) -> pd.DataFrame:
    """캔들 형태 통계: 등락률, 몸통비율, 종가 위치, 윗꼬리 비율, 갭."""
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    prev_close = df["close"].shift(1)
    out = pd.DataFrame(index=df.index)
    out["chg"] = df["close"] / prev_close - 1                    # 전일 대비 등락률
    out["body"] = (df["close"] - df["open"]) / df["open"]          # 시가 대비 몸통 (+ 양봉)
    out["body_ratio"] = (df["close"] - df["open"]).abs() / rng      # 몸통 / 전체 범위
    out["close_pos"] = (df["close"] - df["low"]) / rng              # 0=저가 마감, 1=고가 마감
    out["upper_wick"] = (df["high"] - df[["open", "close"]].max(axis=1)) / rng
    out["gap"] = df["open"] / prev_close - 1
    out["range_pct"] = (df["high"] - df["low"]) / prev_close
    return out


# ---------------------------------------------------------------- 상대강도 (RS)
RS_PERIODS = (63, 126, 189, 252)
RS_WEIGHTS = (0.4, 0.2, 0.2, 0.2)  # IBD 방식: 최근 분기 가중 2배


def rs_raw_score(close: pd.Series) -> pd.Series:
    """IBD 스타일 가중 수익률 점수 시계열. 상장 1년 미만이면 가능한 기간만 재가중."""
    parts = []
    weights = []
    for p, w in zip(RS_PERIODS, RS_WEIGHTS):
        parts.append((close / close.shift(p) - 1) * w)
        weights.append(pd.Series(w, index=close.index).where(close.shift(p).notna()))
    num = pd.concat(parts, axis=1).sum(axis=1, min_count=1)
    den = pd.concat(weights, axis=1).sum(axis=1, min_count=1)
    score = num / den
    # 최소 3개월 이력이 있어야 점수 산출
    return score.where(close.shift(RS_PERIODS[0]).notna())


def rs_rating_table(closes: dict[str, pd.Series], min_universe: int = 50) -> pd.DataFrame:
    """종목별 일자별 RS 레이팅(1~99) 표. 행=날짜, 열=종목코드."""
    raw = pd.DataFrame({c: rs_raw_score(s) for c, s in closes.items()})
    raw = raw.sort_index()
    counts = raw.notna().sum(axis=1)
    pct = (raw.rank(axis=1) - 1).div((counts - 1).clip(lower=1), axis=0)  # 0~1
    rating = (pct * 98 + 1).round()
    rating[counts < min_universe] = np.nan
    return rating


def rs_line(close: pd.Series, index_close: pd.Series) -> pd.Series:
    """종목 / 지수 비율 (상대강도선). 지수 휴장일 차이는 ffill."""
    idx = index_close.reindex(close.index).ffill()
    return close / idx


# ---------------------------------------------------------------- 스윙 포인트
@dataclass(frozen=True)
class Pivot:
    i: int            # 정수 위치 (df.iloc 기준)
    price: float
    kind: str         # 'H' (고점) | 'L' (저점)
    confirmed: bool = True


def zigzag(high, low, pct: float) -> list[Pivot]:
    """고가/저가 기반 지그재그. pct (예: 0.05) 이상 되돌림이 나와야 전환.

    반환 리스트는 H/L 이 교대로 나타나며, 마지막 원소는 아직 확정되지 않은
    현재 진행 중 극값(confirmed=False)이다.
    """
    H = np.asarray(high, dtype=float)
    L = np.asarray(low, dtype=float)
    n = len(H)
    if n == 0:
        return []
    piv: list[Pivot] = []
    trend = 0
    hi_i = lo_i = 0
    for i in range(1, n):
        if trend == 0:
            if H[i] > H[hi_i]:
                hi_i = i
            if L[i] < L[lo_i]:
                lo_i = i
            if lo_i < hi_i and H[hi_i] >= L[lo_i] * (1 + pct):
                piv.append(Pivot(lo_i, L[lo_i], "L"))
                trend, lo_i = 1, hi_i
            elif hi_i < lo_i and L[lo_i] <= H[hi_i] * (1 - pct):
                piv.append(Pivot(hi_i, H[hi_i], "H"))
                trend, hi_i = -1, lo_i
        elif trend == 1:
            if H[i] >= H[hi_i]:
                hi_i = i
            elif L[i] <= H[hi_i] * (1 - pct):
                piv.append(Pivot(hi_i, H[hi_i], "H"))
                trend, lo_i = -1, i
        else:
            if L[i] <= L[lo_i]:
                lo_i = i
            elif H[i] >= L[lo_i] * (1 + pct):
                piv.append(Pivot(lo_i, L[lo_i], "L"))
                trend, hi_i = 1, i
    if trend == 1:
        piv.append(Pivot(hi_i, H[hi_i], "H", confirmed=False))
    elif trend == -1:
        piv.append(Pivot(lo_i, L[lo_i], "L", confirmed=False))
    return piv


def fractal_pivots(high, low, left: int = 5, right: int = 5) -> list[Pivot]:
    """프랙탈 스윙: 좌우 각각 left/right 봉보다 높은(낮은) 봉. H/L 교대 강제.

    마지막 ``right`` 봉 이내의 극값은 확정되지 않으므로 포함하지 않는다.
    """
    H = np.asarray(high, dtype=float)
    L = np.asarray(low, dtype=float)
    n = len(H)
    raw: list[Pivot] = []
    for i in range(left, n - right):
        wh = H[i - left:i + right + 1]
        wl = L[i - left:i + right + 1]
        if H[i] == wh.max() and np.argmax(wh) == left:
            raw.append(Pivot(i, H[i], "H"))
        if L[i] == wl.min() and np.argmin(wl) == left:
            raw.append(Pivot(i, L[i], "L"))
    raw.sort(key=lambda p: (p.i, 0 if p.kind == "H" else 1))
    out: list[Pivot] = []
    for p in raw:
        if out and out[-1].kind == p.kind:
            better = (p.price > out[-1].price) if p.kind == "H" else (p.price < out[-1].price)
            if better:
                out[-1] = p
        else:
            out.append(p)
    return out


# ---------------------------------------------------------------- 기타 유틸
def pct_change(a: float, b: float) -> float:
    """a → b 변화율."""
    return b / a - 1 if a else float("nan")


def rolling_high(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).max()


def rolling_low(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).min()


def bars_since(mask: pd.Series) -> pd.Series:
    """마지막으로 mask 가 True 였던 이후 경과 봉 수 (없으면 NaN)."""
    idx = np.arange(len(mask), dtype=float)
    last = pd.Series(np.where(mask.to_numpy(), idx, np.nan), index=mask.index).ffill()
    return pd.Series(idx, index=mask.index) - last
