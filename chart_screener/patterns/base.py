"""패턴 탐지기 공용 인터페이스.

모든 탐지기는 ``detect(ctx: StockContext) -> PatternResult`` 형태이며
``@register`` 로 등록한다. 탐지 실패 시에도 ``detected=False`` 와 함께 탈락 사유
(``reasons``/``warnings``)를 채워 반환한다 — 단일 종목 분석에서 "왜 아닌지"를 보여주기 위함.

단계(stage) 정의 — 모든 패턴 공통
    forming     : 패턴 구조는 갖췄으나 피벗까지 거리가 있음 (관심종목)
    near_pivot  : 피벗 아래 ``near_pct`` 이내 접근 (매수 대기)
    breakout    : 최근 ``breakout_window`` 봉 이내 피벗 돌파, 매수 범위(피벗+5%) 이내
    extended    : 돌파 후 매수 범위를 넘어 상승 (추격 매수 구간)
    failed      : 돌파 후 피벗 아래로 일정 이상 되밀림
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import Any, Callable

import numpy as np
import pandas as pd

from .. import indicators as ind
from ..config import Config

FORMING, NEAR_PIVOT, BREAKOUT, EXTENDED, FAILED = "forming", "near_pivot", "breakout", "extended", "failed"
STAGE_LABELS = {
    FORMING: "형성 중",
    NEAR_PIVOT: "피벗 근접",
    BREAKOUT: "돌파",
    EXTENDED: "이격 과다",
    FAILED: "돌파 실패",
}


# ---------------------------------------------------------------- 차트 주석 헬퍼
def _d(x) -> str:
    return pd.Timestamp(x).strftime("%Y-%m-%d")


def hline(price: float, label: str, color: str = "#2962ff", style: str = "dashed") -> dict:
    return {"kind": "hline", "price": float(price), "label": label, "color": color, "style": style}


def segment(points: list[tuple[Any, float]], label: str = "", color: str = "#ff6d00") -> dict:
    """꺾은선 (컵 윤곽, 추세선, 수축 구간 등). points = [(날짜, 가격), ...]"""
    return {"kind": "segment", "points": [(_d(d), float(p)) for d, p in points], "label": label, "color": color}


def box(start, end, top: float, bottom: float, label: str = "", color: str = "#7e57c2") -> dict:
    return {"kind": "box", "start": _d(start), "end": _d(end), "top": float(top), "bottom": float(bottom),
            "label": label, "color": color}


def marker(date, text: str, position: str = "above", color: str = "#e91e63", shape: str = "arrowDown") -> dict:
    """position: above|below|inBar, shape: arrowUp|arrowDown|circle|square"""
    return {"kind": "marker", "date": _d(date), "text": text, "position": position, "color": color, "shape": shape}


# ---------------------------------------------------------------- 결과 타입
@dataclass
class PatternResult:
    name: str                       # 'vcp', 'cup_handle', ...
    label: str                      # 한글 표시명
    detected: bool = False
    score: float = 0.0              # 0~100 품질 점수
    stage: str | None = None        # FORMING / NEAR_PIVOT / BREAKOUT / EXTENDED / FAILED
    pivot: float | None = None      # 매수 기준가 (돌파 기준)
    stop: float | None = None       # 제안 손절가
    start_date: str | None = None   # 패턴 시작일
    end_date: str | None = None     # 패턴 종료일(보통 마지막 봉 또는 돌파일)
    breakout_date: str | None = None
    metrics: dict = field(default_factory=dict)       # 패턴별 수치
    reasons: list[str] = field(default_factory=list)  # 충족 조건 설명(한글)
    warnings: list[str] = field(default_factory=list) # 경고/탈락 사유(한글)
    annotations: list[dict] = field(default_factory=list)

    @property
    def stage_label(self) -> str:
        return STAGE_LABELS.get(self.stage or "", "-")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stage_label"] = self.stage_label
        d["metrics"] = {k: _jsonable(v) for k, v in self.metrics.items()}
        return d


def _jsonable(v):
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return _d(v)
    return v


# ---------------------------------------------------------------- 종목 컨텍스트
@dataclass
class StockContext:
    code: str
    name: str
    market: str                          # 'KOSPI' | 'KOSDAQ'
    df: pd.DataFrame                     # open high low close volume value (DatetimeIndex 오름차순)
    cfg: Config = field(default_factory=Config)
    index_df: pd.DataFrame | None = None # 소속 시장 지수 일봉
    rs_rating: float | None = None       # 최신 RS 레이팅 (1~99)
    rs_rating_hist: pd.Series | None = None
    market_state: Any = None             # market.MarketState
    partial: bool = False                # 마지막 봉이 장중 미완성인지
    session_frac: float = 1.0            # 장중이면 하루 거래량 중 체결 비율 추정치
    info: dict = field(default_factory=dict)  # 시가총액 등 종목 메타
    _cache: dict = field(default_factory=dict, repr=False)

    # ---- 기본 시계열
    @property
    def close(self) -> pd.Series:
        return self.df["close"]

    @property
    def high(self) -> pd.Series:
        return self.df["high"]

    @property
    def low(self) -> pd.Series:
        return self.df["low"]

    @property
    def n(self) -> int:
        return len(self.df)

    @cached_property
    def vol(self) -> pd.Series:
        """유효 거래량: 장중이면 마지막 봉을 하루치로 환산(추정)."""
        v = self.df["volume"].astype(float).copy()
        if self.partial and 0.05 < self.session_frac < 1:
            v.iloc[-1] = v.iloc[-1] / self.session_frac
        return v

    @cached_property
    def value(self) -> pd.Series:
        """유효 거래대금(원): 장중이면 마지막 봉 환산(추정)."""
        v = self.df["value"].astype(float).copy()
        if self.partial and 0.05 < self.session_frac < 1:
            v.iloc[-1] = v.iloc[-1] / self.session_frac
        return v

    # ---- 메모이즈된 지표
    def sma(self, n: int) -> pd.Series:
        return self._memo(("sma", n), lambda: ind.sma(self.close, n))

    def ema(self, n: int) -> pd.Series:
        return self._memo(("ema", n), lambda: ind.ema(self.close, n))

    def vol_sma(self, n: int) -> pd.Series:
        return self._memo(("vsma", n), lambda: ind.sma(self.vol, n))

    def atr(self, n: int = 14) -> pd.Series:
        return self._memo(("atr", n), lambda: ind.atr(self.df, n))

    def candles(self) -> pd.DataFrame:
        return self._memo(("candles",), lambda: ind.candle_frame(self.df))

    def zigzag(self, pct: float) -> list[ind.Pivot]:
        return self._memo(("zz", pct), lambda: ind.zigzag(self.high, self.low, pct))

    @property
    def rs_line(self) -> pd.Series | None:
        if self.index_df is None:
            return None
        return self._memo(("rsline",), lambda: ind.rs_line(self.close, self.index_df["close"]))

    def date(self, i: int) -> str:
        return _d(self.df.index[i])

    def _memo(self, key, fn: Callable):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]


# ---------------------------------------------------------------- 단계 판정
def classify_stage(
    ctx: StockContext,
    pivot: float,
    base_end_i: int,
    near_pct: float = 0.05,
    buy_range: float = 0.05,
    breakout_window: int = 5,
    fail_pct: float = 0.03,
    breakout_vol_mult: float | None = None,
) -> tuple[str, int | None]:
    """피벗과 패턴 종료 위치를 기준으로 공통 단계를 판정.

    돌파 = 패턴 종료(base_end_i) 이후 '종가'가 피벗을 처음 넘은 봉.
    breakout_vol_mult 가 주어지면 돌파봉 거래량이 50일 평균의 해당 배수 이상이어야 돌파로 인정.
    반환: (stage, breakout_i)
    """
    close = ctx.close.to_numpy()
    last = len(close) - 1
    vavg = ctx.vol_sma(50).shift(1).to_numpy()
    vol = ctx.vol.to_numpy()
    bo_i = None
    for i in range(base_end_i + 1, last + 1):
        if close[i] > pivot:
            if breakout_vol_mult is not None and np.isfinite(vavg[i]) and vol[i] < vavg[i] * breakout_vol_mult:
                continue
            bo_i = i
            break
    c = close[last]
    if bo_i is None:
        # 거래량 미달로 돌파가 인정되지 않았는데 이미 매수 범위 위라면 '근접'이 아니라 이격 과다
        if c > pivot * (1 + buy_range):
            return EXTENDED, None
        if c >= pivot * (1 - near_pct):
            return NEAR_PIVOT, None
        return FORMING, None
    if c < pivot * (1 - fail_pct):
        return FAILED, bo_i
    if c > pivot * (1 + buy_range):
        return EXTENDED, bo_i
    if c <= pivot:
        # 돌파 후 피벗 아래로 되밀렸지만 실패 기준(-fail_pct) 이내: 재시험 구간
        return NEAR_PIVOT, bo_i
    if last - bo_i < breakout_window:
        return BREAKOUT, bo_i
    # 돌파 후 시간이 지났지만 피벗~매수범위 사이에서 버티는 경우: 재진입 관점에서 near_pivot 처리
    return NEAR_PIVOT, bo_i


# ---------------------------------------------------------------- 레지스트리
Detector = Callable[[StockContext], PatternResult]
REGISTRY: dict[str, tuple[str, Detector]] = {}


def register(name: str, label: str):
    def deco(fn: Detector) -> Detector:
        REGISTRY[name] = (label, fn)
        fn.pattern_name = name  # type: ignore[attr-defined]
        fn.pattern_label = label  # type: ignore[attr-defined]
        return fn
    return deco


def run_all(ctx: StockContext, names: list[str] | None = None) -> dict[str, PatternResult]:
    out: dict[str, PatternResult] = {}
    for name, (label, fn) in REGISTRY.items():
        if names and name not in names:
            continue
        try:
            out[name] = fn(ctx)
        except Exception as e:  # 탐지기 오류는 결과에 기록하고 계속
            out[name] = PatternResult(name=name, label=label, warnings=[f"탐지 오류: {type(e).__name__}: {e}"])
    return out
