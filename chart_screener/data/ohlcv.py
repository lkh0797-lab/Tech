"""일봉 OHLCV 수집 + 디스크 캐시 (네이버 fchart).

주의 사항
- 가격은 수정주가(액면분할/무상증자 반영), 거래량은 '원 거래량'(미수정)이다.
  분할 이전 구간의 거래량 비교는 왜곡될 수 있어, 거래정지일이 있으면
  ``df.attrs["halt_dates"]`` 에 기록해 경고에 활용한다.
- 일별 거래대금은 API가 제공하지 않으므로 ``(고+저+종)/3 × 거래량`` 으로 추정한다.
  당일 값은 종목목록 API의 실제 거래대금으로 덮어쓸 수 있다(scanner 참고).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from ..config import CACHE_DIR, DataConfig
from . import http

KST = timezone(timedelta(hours=9))
_URL = "https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0"
_ITEM_RE = re.compile(r'data="([^"]+)"')

SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(15, 30)
DATA_FINAL = time(15, 45)  # 종가 확정 이후 캐시를 '확정'으로 간주

# 장중 누적 거래량 비율(경험적 U자형 프로파일): (경과 분, 하루 거래량 대비 누적 비율)
_INTRADAY_PROFILE = [
    (0, 0.0), (30, 0.22), (60, 0.32), (120, 0.46), (180, 0.56),
    (240, 0.65), (300, 0.76), (360, 0.90), (380, 0.95), (390, 1.0),
]


def now_kst() -> datetime:
    return datetime.now(KST)


def session_fraction(at: datetime | None = None) -> float:
    """현재 시각까지 하루 거래량 중 체결된 비율의 추정치 (0~1)."""
    at = at or now_kst()
    start = at.replace(hour=9, minute=0, second=0, microsecond=0)
    minutes = (at - start).total_seconds() / 60
    if minutes <= 0:
        return 0.0
    if minutes >= 390:
        return 1.0
    xs, ys = zip(*_INTRADAY_PROFILE)
    return float(np.interp(minutes, xs, ys))


def _last_final_close(at: datetime) -> datetime:
    """가장 최근 '확정 종가' 시각 (공휴일은 무시 — 무해한 재요청만 발생)."""
    d = at
    if d.weekday() < 5 and d.time() >= DATA_FINAL:
        return d.replace(hour=15, minute=45, second=0, microsecond=0)
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.replace(hour=15, minute=45, second=0, microsecond=0)


def parse_fchart(text: str) -> pd.DataFrame:
    recs = []
    for item in _ITEM_RE.findall(text):
        parts = item.split("|")
        if len(parts) < 6:
            continue
        d, o, h, l, c, v = parts[:6]
        recs.append((d, float(o), float(h), float(l), float(c), float(v)))
    df = pd.DataFrame(recs, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df.set_index("date").sort_index()


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """거래정지일 제거, 결측 시가 보정, 추정 거래대금 추가.

    거래량 0 인 봉은 거래정지(또는 무체결)로 보고 제거한 뒤 ``attrs['halt_dates']`` 에 기록한다.
    네이버는 정지일을 O=H=L=0 또는 O=H=L=C=전일종가·거래량 0 두 가지로 내려준다.
    제거하지 않으면 50일 평균 거래량이 낮아져 돌파 거래량 배수가 부풀려진다.
    """
    if df.empty:
        return df
    prior = list(df.attrs.get("halt_dates", []))
    halt = (df["volume"] <= 0) | (df["close"] <= 0)
    halt_dates = sorted(set(prior) | set(df.index[halt].strftime("%Y-%m-%d")))
    df = df[~halt].copy()
    # 과거 데이터 중 시가/고가/저가 0 인 행 보정
    for col in ("open", "high", "low"):
        bad = df[col] <= 0
        df.loc[bad, col] = df.loc[bad, "close"]
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    df["value"] = (df["high"] + df["low"] + df["close"]) / 3.0 * df["volume"]
    df.attrs["halt_dates"] = halt_dates
    return df


def fetch_ohlcv(code: str, count: int = 750) -> pd.DataFrame:
    r = http.get(_URL.format(code=code, count=count))
    r.encoding = "euc-kr"
    df = clean(parse_fchart(r.text))
    df.attrs["requested"] = int(count)  # 요청한 봉 수 (상장 기간이 짧으면 실제 행 수는 더 적다)
    return df


def _tail(df: pd.DataFrame, count: int) -> pd.DataFrame:
    """캐시가 요청보다 길면 최근 count 봉만 (attrs 유지)."""
    return df.iloc[-count:] if count and len(df) > count else df


class OHLCVCache:
    """종목별 pickle 캐시. 확정 종가 이후에 받은 데이터면 재사용."""

    def __init__(self, root: Path | None = None, intraday_ttl_min: float = 20):
        self.root = Path(root or CACHE_DIR / "ohlcv")
        self.root.mkdir(parents=True, exist_ok=True)
        self.intraday_ttl = timedelta(minutes=intraday_ttl_min)

    def _path(self, code: str) -> Path:
        return self.root / f"{code}.pkl"

    def is_fresh(self, code: str, at: datetime | None = None) -> bool:
        """캐시 재사용 가능 여부 (장 상황 기준).

        - 평일 장중(09:00 ≤ 지금 < 15:45): 오늘 09:00 이후에 받았고 받은 지 intraday_ttl 이내일 때만.
          (어제 장 마감 후 받은 캐시는 '확정 종가 이후'라도 오늘 장중에는 낡은 데이터다.)
        - 그 밖(장 전·장 마감 후·주말): 가장 최근 확정 종가(15:45) 이후에 받았으면 신선.
        """
        p = self._path(code)
        if not p.exists():
            return False
        at = at or now_kst()
        at = at.replace(tzinfo=KST) if at.tzinfo is None else at.astimezone(KST)
        fetched = datetime.fromtimestamp(p.stat().st_mtime, KST)
        if at.weekday() < 5 and SESSION_OPEN <= at.time() < DATA_FINAL:
            today_open = at.replace(hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0)
            return fetched >= today_open and at - fetched < self.intraday_ttl
        return fetched >= _last_final_close(at)

    def load(self, code: str) -> pd.DataFrame | None:
        p = self._path(code)
        if not p.exists():
            return None
        try:
            df = pd.read_pickle(p)
        except Exception:
            return None
        if len(df) and (df["volume"] <= 0).any():  # 구버전 캐시: 거래량 0 정지일 정리
            halts = list(df.attrs.get("halt_dates", []))
            requested = df.attrs.get("requested")
            raw = df[["open", "high", "low", "close", "volume"]].copy()
            raw.attrs["halt_dates"] = halts
            df = clean(raw)
            if requested:
                df.attrs["requested"] = requested
        return df

    def save(self, code: str, df: pd.DataFrame) -> None:
        df.to_pickle(self._path(code))

    def get(self, code: str, count: int = 750, refresh: bool = False, offline: bool = False) -> pd.DataFrame | None:
        """캐시 우선. 캐시가 낡았거나, 캐시에 담긴 기간이 요청(count)보다 짧으면 다시 받는다.
        offline 이면 캐시에 있는 만큼만 돌려준다."""
        if offline or not refresh:
            df = self.load(code)
            if df is not None:
                enough = int(df.attrs.get("requested", len(df))) >= count
                if offline or (enough and self.is_fresh(code)):
                    return _tail(df, count)
            elif offline:
                return None
        df = fetch_ohlcv(code, count)
        self.save(code, df)
        return df


def fetch_many(
    codes: Iterable[str],
    cfg: DataConfig | None = None,
    cache: OHLCVCache | None = None,
    refresh: bool = False,
    offline: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, pd.DataFrame]:
    cfg = cfg or DataConfig()
    cache = cache or OHLCVCache()
    codes = list(dict.fromkeys(codes))
    out: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
        futs = {ex.submit(cache.get, c, cfg.history_days, refresh, offline): c for c in codes}
        for i, fut in enumerate(as_completed(futs), 1):
            code = futs[fut]
            try:
                df = fut.result()
                if df is not None and not df.empty:
                    out[code] = df
            except Exception as e:  # 개별 종목 실패는 건너뜀
                errors[code] = str(e)
            if progress:
                progress(i, len(codes))
    LAST_ERRORS.clear()
    LAST_ERRORS.update(errors)
    return out


LAST_ERRORS: dict[str, str] = {}  # 직전 fetch_many 의 실패 종목 → 사유


INDEX_SYMBOLS = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}


def fetch_index(name: str, count: int = 750, cache: OHLCVCache | None = None, refresh: bool = False,
                offline: bool = False) -> pd.DataFrame:
    cache = cache or OHLCVCache()
    df = cache.get(INDEX_SYMBOLS[name], count, refresh=refresh, offline=offline)
    if df is None:
        raise RuntimeError(f"지수 데이터 없음: {name} (offline 모드에서는 캐시가 필요)")
    return df
