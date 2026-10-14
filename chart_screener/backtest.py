"""워크포워드 이벤트 스터디: 과거 각 시점까지의 데이터만 잘라 탐지기를 돌리고, 신호 이후 수익률을 측정.

    python -m chart_screener backtest cup_with_handle        # 돌파 당일 신호 (기본, 매일 판정 — 오래 걸림)
    python -m chart_screener backtest cup_with_handle --mode stage --stages near_pivot --step 5

방법
- 각 종목의 일봉을 시점 t 까지 잘라(df.iloc[:t+1]) StockContext 를 만들고 탐지기를 실행한다.
  RS 레이팅·지수·시장 상태·거래정지일도 t 시점까지만 쓴다 → 미래 참조 없음.
- 신호 (mode='breakout_day', 기본): 매 거래일(step=1) 탐지기를 실행해, 그날이 곧 신호일
  (event_date(패턴, 결과) == t) 인 경우만 집계. 돌파 당일 바로 이격 과다(+5% 초과)가 된 강한 돌파도 포함된다.
  신호일 = 그 판정이 처음 알려지는 봉 — 대부분 breakout_date, 빗각 추세선 돌파는 안착 확인 봉(metrics.break.conf_date —
  breakout_date 는 돌파일 t0 이라 확인이 늦으면 그날 알 수 없다), 월봉 적삼병은 확정 봉(metrics.known_date — 다음 달 첫 거래일).
  10% 주도주는 돌파일이 없는 관찰 칩이라 stage 모드(--stages near_pivot = 신호 봉)만 된다.
- 손절 (has_stop · outcome 'stop') 은 STOP_RULE: 피보 계열 = 저가 ≤ 고정 손절(다음 깊은 라인), 빗각 추세선 돌파 =
  종가 ≤ 그날 동결 선 값(움직이는 선 — '선 아래 재하락 = 실패'), 컵 앤 핸들 · 60일선 · 적삼병 · 10% 주도주 = 손절 규칙 없음.
  (mode='stage'): step 간격으로 실행해 stage ∈ stages 이면 신호. 같은 패턴(키 = (돌파일 또는 패턴 시작일,
  반올림 피벗))은 종목당 1회만 집계한다 — 형성 중 패턴은 end_date 가 매일 바뀌므로 키에 쓰지 않는다.
  눌림목형 패턴(피벗이 매일 움직일 수 있음)은 ``first_entries`` 로 (종목, 시작일)당 첫 신호만 남겨 요약한다.
- 진입 = 신호 다음 날 시가. 보유 수익률 = h 거래일 후 종가 / 진입가 - 1.
  지수 대비 초과수익의 지수 수익률도 같은 구간(t+1 시가 → h 거래일 후 종가)으로 잰다(시가 없으면 t 종가).
- '+20% 선도달' = 손절가 이탈 전에 진입가 +20% 고가 도달 (오닐의 20~25% 익절 규칙 참고).
- t 시점 유동성 필터(20일 평균 거래대금·주가)를 적용한다. 시가총액 필터는 과거값이 없어 생략.

한계: 현재 상장 종목만 대상(상장폐지 종목 누락 → 생존 편향), 거래비용·슬리피지 미반영.
"""
from __future__ import annotations

import bisect
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .breadth import breadth_at
from .config import Config
from .market import analyze_market
from .patterns import REGISTRY
from .patterns.base import StockContext
from .universe_data import UniverseData, load_universe_data

_UD: UniverseData | None = None
_MKT: dict | None = None


@dataclass
class BacktestConfig:
    pattern: str
    mode: str = "breakout_day"               # 'breakout_day' | 'stage'
    step: int = 1
    since: str | None = None                 # 이 날짜 이후 신호만 (기본: 데이터 시작 + 260봉)
    horizons: tuple[int, ...] = (5, 20, 60)
    stages: tuple[str, ...] = ("breakout",)
    min_bars: int = 260                      # 신호 시점에 필요한 최소 이력
    target: float = 0.20
    history_days: int | None = None          # 캐시에서 쓸 일봉 수 (None = Config 기본 3년). 더 긴 검증: --years
    prefilter: bool = True                   # 돌파일 사전 필터 (breakout_day 모드)
    until: str | None = None                 # 이 날짜(포함)까지의 봉만 — 그 뒤 봉(장중 미완성 봉 등)은 신호 · 수익 계산에서 뺀다


def market_states_by_date(ud: UniverseData, since: pd.Timestamp) -> dict[str, dict[pd.Timestamp, object]]:
    """시장별 {날짜: 그날까지의 지수와 시장 폭(breadth_hist 의 그날 값)으로 판정한 MarketState}."""
    hist = getattr(ud, "breadth_hist", None)
    out: dict[str, dict] = {}
    for name, idx in ud.index.items():
        d = {}
        for k in range(len(idx)):
            if idx.index[k] >= since and k >= 60:
                d[idx.index[k]] = analyze_market(name, idx.iloc[:k + 1],
                                                 breadth=breadth_at(hist, name, idx.index[k]))
        out[name] = d
    return out


class _Static:
    """종목별로 한 번만 계산해 두는 값 (시점마다 반복 조회하지 않도록)."""

    def __init__(self, code: str, ud: UniverseData, mkt: dict):
        info = ud.universe.loc[code].to_dict() if code in ud.universe.index else {}
        self.name = info.get("name", code)
        self.market = info.get("market", "KOSPI")
        self.mcap = info.get("market_cap")
        self.idx = ud.index.get(self.market)
        self.rs = ud.rs[code].dropna() if code in ud.rs.columns else None
        ms = mkt.get(self.market, {})
        self.ms_dates = sorted(ms)
        self.ms = ms

    def state_at(self, date):
        st = self.ms.get(date)
        if st is None and self.ms_dates:
            k = bisect.bisect_right(self.ms_dates, date) - 1
            st = self.ms[self.ms_dates[k]] if k >= 0 else None
        return st


def _context_at(code: str, df: pd.DataFrame, t: int, ud: UniverseData, cfg: Config, mkt: dict,
                st: "_Static | None" = None) -> StockContext:
    st = st or _Static(code, ud, mkt)
    date = df.index[t]
    rs_hist = st.rs.iloc[:st.rs.index.searchsorted(date, side="right")] if st.rs is not None else None
    cut = df.iloc[:t + 1]
    # pandas 는 iloc 슬라이스에도 attrs 를 그대로 넘기므로, 미래의 거래정지일을 잘라낸다
    day = date.strftime("%Y-%m-%d")
    cut.attrs = {**df.attrs, "halt_dates": [d for d in df.attrs.get("halt_dates", []) if d <= day]}
    idx = st.idx.iloc[:st.idx.index.searchsorted(date, side="right")] if st.idx is not None else None
    return StockContext(
        code=code, name=st.name, market=st.market, df=cut, cfg=cfg, index_df=idx,
        rs_rating=float(rs_hist.iloc[-1]) if rs_hist is not None and len(rs_hist) else None,
        rs_rating_hist=rs_hist, market_state=st.state_at(date), info={"market_cap": st.mcap},
    )


# 돌파일 사전 필터 — 패턴 규칙상 돌파일이 될 수 없는 날은 탐지기를 생략한다(속도 최적화).
#  종류: 'chg'(등락률 ≥ x) · 'up'(상승 마감) · 'near_high_up'(상승 마감 & 종가 ≥ 직전 20봉 최고가 × x)
#        · 'near_high'(종가 ≥ 직전 20봉 최고가 × x, 상승 마감 불필요) · 'none'(필터 없음, 매일 실행)
#  필터는 '그 패턴의 신호를 하나도 놓치지 않는다'를 검증한 뒤에만 넣는다. 2026-10-14 패턴 초기화로 옛 패턴의 검증된 필터는
#  패턴과 함께 지웠고, 검증 전 패턴(표에 없는 패턴 포함)은 필터 없이 매일 판정한다(느리지만 신호를 놓치지 않는다).
#  - 컵 앤 핸들(사용자 식): 돌파 시도 = 그날 고가가 확인된 우측 림 위 — 직전 20봉 최고가 기준 필터는 우측 림이 20봉보다
#    앞이거나 컵 안 고가가 림보다 높은 경우를 놓칠 수 있어 쓰지 않는다.
#  《차트의 기술》 기법(2026-10-14) — 규칙상 꼭 성립하는 조건만 쓴 '상위 집합' 필터(신호를 놓치지 않음, 시험 test_technique_integration):
#   'white'       양봉 C > O — 피보 반등 신호 봉은 늘 양봉(부록 §3.1, 장대양봉 · 반등 양봉 모두)
#   'series'      패턴 모듈의 stage_series(df)(상태 기계 한 번 — 봉마다 detect(df[:t+1]) 와 같음을 패턴 시험이 확인)에서
#                 돌파 · 신호 뒤 단계(breakout_i 있음)인 날만. 빗각 · 빗각+피보는 날마다 봉 0 부터 다시 돌면 O(n²)
#   'ma_cross'    종가가 x일 SMA 를 아래에서 위로(상대 1e-6 여유 — tq.cross_above 의 1e-9 경계를 품음)
#   'month_first' 그 달의 첫 거래 봉(앞선 같은 달 봉이 모두 거래량 0 이면 그다음 봉까지) — 월봉 적삼병 신호가 처음 보이는 봉
#                 ('next_bar' 완성 규칙일 때만 — 'calendar' 설정이면 필터 없음)
PREFILTER: dict[str, tuple[str, float | None]] = {
    "cup_with_handle": ("none", None),
    "trendline_break": ("series", None),
    "fib_pullback": ("white", None),
    "trendline_fib": ("series", None),
    "ma60_supply": ("ma_cross", 60),
    "red_three_monthly": ("month_first", None),
}
DEFAULT_PREFILTER: tuple[str, float | None] = ("none", None)
# breakout_day 모드를 쓸 수 없는 패턴 — 돌파일(breakout_date)이 없다
NO_BREAKOUT_DAY = {
    "day_leader": "10% 주도주는 피벗 · 돌파일이 없는 관찰 칩(분봉 진입) — --mode stage --stages near_pivot 로 신호 봉"
                  "(다음 날 시가 진입)만 잴 수 있다. 영상의 분봉 단타 진입이 아니다.",
}
# 손절 판정 — 'low' 저가 ≤ 고정 손절가(r.stop) · 'close_line' 종가 ≤ 그날 동결 추세선 값(metrics.line) · None 손절 규칙 없음.
# 표에 없는 패턴은 손절가가 있으면 'low'.
STOP_RULE: dict[str, str | None] = {
    "cup_with_handle": None,          # 식에 손절 규칙 없음
    "trendline_break": "close_line",  # '선 아래 재하락 = 실패' (영상 [55:00–56:00] · 부록 §4.4) — 종가 기준, 선은 날마다 내려감
    "fib_pullback": "low",            # 다음 깊은 라인 (BabyPips · 부록 §3.1) — 기계의 손절과 같은 저가 기준
    "trendline_fib": "low",
    "ma60_supply": None,              # 영상의 이 부분은 손절을 말하지 않는다
    "red_three_monthly": None,        # 확정 저점은 구조 무효선 — 손절 규칙 아님
    "day_leader": None,               # 분봉 기준선 이탈(HTS) — 일봉 손절 없음
}


def event_date(pattern: str, r) -> str | None:
    """breakout_day 모드의 신호일 — 그 판정이 처음 알려지는 봉 (위 docstring)."""
    m = getattr(r, "metrics", None) or {}
    if pattern == "trendline_break":
        return (m.get("break") or {}).get("conf_date") if r.breakout_date else None
    if pattern == "red_three_monthly":
        return m.get("known_date") if r.breakout_date else None
    return r.breakout_date


def stop_rule(pattern: str, r) -> str | None:
    rule = STOP_RULE.get(pattern, "low")
    if rule == "close_line":
        ln = (getattr(r, "metrics", None) or {}).get("line") or {}
        ok = all(_finite(ln.get(k)) for k in ("anchor_i", "anchor_price", "slope_ln"))
        return "close_line" if ok else ("low" if r.stop and r.stop > 0 else None)
    if rule == "low":
        return "low" if r.stop and r.stop > 0 else None
    return None


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _line_value(ln: dict, i: int) -> float:
    """동결 추세선의 봉 i 값 (tq.TrendLine.value 와 같은 로그 직선)."""
    return float(ln["anchor_price"]) * math.exp(float(ln["slope_ln"]) * (i - int(ln["anchor_i"])))


def _prefilter_kind(pattern: str) -> tuple[str, float | None]:
    kind, x = PREFILTER.get(pattern, DEFAULT_PREFILTER)
    if kind == "month_first":
        try:
            from .patterns import red_three_monthly as rtm
            if Config().pattern_cfg(rtm.NAME, rtm.RedThreeConfig).complete_rule != "next_bar":
                return "none", None
        except Exception:
            return "none", None
    return kind, x


def _series_mask(pattern: str, df: pd.DataFrame) -> np.ndarray | None:
    import importlib
    try:
        mod = importlib.import_module(REGISTRY[pattern][1].__module__)
        ser = mod.stage_series(df)
    except Exception:
        return None
    if len(ser) != len(df):
        return None
    return np.array([x is not None and x.get("breakout_i") is not None for x in ser], bool)


def _maybe_breakout_day(pattern: str, h: np.ndarray, c: np.ndarray, df: pd.DataFrame | None = None) -> np.ndarray:
    """돌파 · 신호일이 될 수 있는 날 (True). df 가 필요한 필터(white · series · month_first)는 df 가 없으면 필터 없음."""
    n = len(c)
    kind, x = _prefilter_kind(pattern)
    if kind == "none":
        return np.ones(n, bool)
    prev = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "chg":
            return c / prev - 1 >= x
        if kind == "ma_cross":
            sma = pd.Series(c).rolling(int(x or 60)).mean().to_numpy()
            ps = np.r_[np.nan, sma[:-1]]
            return (c > sma * (1 - 1e-6)) & (prev <= ps * (1 + 1e-6))
        if kind in ("white", "series", "month_first"):
            if df is None or len(df) != n:
                return np.ones(n, bool)
            if kind == "white":
                return c > df["open"].to_numpy(float)
            if kind == "series":
                m = _series_mask(pattern, df)
                return m if m is not None else np.ones(n, bool)
            per = df.index.to_period("M")
            nz = pd.Series(df["volume"].to_numpy(float) > 0, index=df.index)
            before = nz.groupby(per).cumsum() - nz          # 같은 달 앞선 봉 중 거래량 > 0 인 수
            return (before == 0).to_numpy()
        up = c > prev
        if kind == "up":
            return up
        hh = pd.Series(h).rolling(20, min_periods=1).max().shift(1).to_numpy()
        near = c >= np.nan_to_num(hh, nan=np.inf) * (x if x is not None else 0.85)
        return up & near if kind == "near_high_up" else near


def _dedupe_key(r, date: pd.Timestamp) -> tuple:
    """같은 패턴 신호를 한 번만 세기 위한 안정적인 키: (돌파일 또는 패턴 시작일, 반올림 피벗)."""
    anchor = r.breakout_date or r.start_date or date.strftime("%Y-%m-%d")
    piv = r.pivot if r.pivot is not None and r.pivot == r.pivot else 0
    return anchor, round(piv)


def _events_for(code: str, bt: BacktestConfig, cfg: Config, ud: UniverseData, mkt: dict) -> list[dict]:
    df = ud.ohlcv[code]
    if bt.until:
        df = df.loc[:pd.Timestamp(bt.until)]
    n = len(df)
    fn = REGISTRY[bt.pattern][1]
    since = pd.Timestamp(bt.since) if bt.since else None
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    val20 = df["value"].rolling(20).mean().to_numpy()
    market = ud.universe.loc[code, "market"] if code in ud.universe.index else "KOSPI"
    idx_df = ud.index[market]
    idx_close = idx_df["close"].reindex(df.index).ffill().to_numpy(float)
    # 지수 시가는 ffill 하지 않는다: 그날 지수 봉이 없으면 t 종가 기준으로 대체
    idx_open = (idx_df["open"].reindex(df.index).to_numpy(float) if "open" in idx_df
                else np.full(n, np.nan))
    st = _Static(code, ud, mkt)
    use_pf = bt.mode == "breakout_day" and bt.prefilter
    cand = _maybe_breakout_day(bt.pattern, h, c, df) if use_pf else np.ones(n, bool)
    seen: set = set()
    events = []
    for t in range(bt.min_bars, n - 1, bt.step):
        if not cand[t] or (since is not None and df.index[t] < since):
            continue
        if c[t] < cfg.universe.min_price or not (val20[t] >= cfg.universe.min_avg_value_20d):
            continue
        r = fn(_context_at(code, df, t, ud, cfg, mkt, st))
        if not r.detected:
            continue
        if bt.mode == "breakout_day":
            if event_date(bt.pattern, r) != df.index[t].strftime("%Y-%m-%d"):
                continue
        elif r.stage not in bt.stages:
            continue
        key = _dedupe_key(r, df.index[t])
        if key in seen:
            continue
        seen.add(key)
        entry = o[t + 1] if o[t + 1] > 0 else c[t + 1]
        ib = idx_open[t + 1] if np.isfinite(idx_open[t + 1]) and idx_open[t + 1] > 0 else idx_close[t]
        ev = {"code": code, "date": df.index[t].strftime("%Y-%m-%d"), "stage": r.stage,
              "score": round(r.score, 1), "pivot": r.pivot, "stop": r.stop, "entry": entry,
              "start_date": r.start_date, "breakout_date": r.breakout_date,
              "rs": _ctx_rs(ud, code, df.index[t])}
        for hz in bt.horizons:
            j = t + 1 + hz - 1
            if j < n:
                ev[f"ret_{hz}"] = c[j] / entry - 1
                ev[f"idx_{hz}"] = idx_close[j] / ib - 1 if ib > 0 else np.nan
                ev[f"mae_{hz}"] = l[t + 1:j + 1].min() / entry - 1
            else:
                ev[f"ret_{hz}"] = ev[f"idx_{hz}"] = ev[f"mae_{hz}"] = np.nan
        # 손절 전 +target 도달 여부 (최대 마지막 horizon 까지). 손절 규칙 없는 식(컵 앤 핸들 등)은 'stop' 이 나올 수 없으므로
        # has_stop=False 로 따로 표시 — summarize 가 손절 비율을 손절가 있는 신호로만 낸다(0% 로 섞지 않게).
        # 손절 판정은 패턴마다(STOP_RULE): 저가 ≤ 고정 손절가, 또는 종가 ≤ 그날 동결 추세선 값.
        rule = stop_rule(bt.pattern, r)
        has_stop = rule is not None
        ln = (r.metrics or {}).get("line") if rule == "close_line" else None
        horizon_end = min(n, t + 1 + max(bt.horizons))
        outcome = "open"
        for j in range(t + 1, horizon_end):
            if (rule == "low" and l[j] <= r.stop) or (rule == "close_line" and c[j] <= _line_value(ln, j)):
                outcome = "stop"
                break
            if h[j] >= entry * (1 + bt.target):
                outcome = "target"
                break
        ev["outcome"] = outcome
        ev["has_stop"] = has_stop
        ev["stop_rule"] = rule or ""
        ev["event_date"] = event_date(bt.pattern, r) if bt.mode == "breakout_day" else None
        events.append(ev)
    return events


def _ctx_rs(ud: UniverseData, code: str, date) -> float | None:
    if code not in ud.rs.columns:
        return None
    s = ud.rs[code].loc[:date].dropna()
    return float(s.iloc[-1]) if len(s) else None


def _cfg(history_days: int | None) -> Config:
    cfg = Config()
    if history_days:
        cfg.data.history_days = int(history_days)
    return cfg


def _init_worker(since: str, history_days: int | None = None) -> None:
    global _UD, _MKT
    _UD = load_universe_data(_cfg(history_days), offline=True, verbose=False)
    _MKT = market_states_by_date(_UD, pd.Timestamp(since))


def _worker(args) -> list[dict]:
    codes, bt = args
    cfg = Config()
    out = []
    for code in codes:
        try:
            out.extend(_events_for(code, bt, cfg, _UD, _MKT))
        except Exception as e:  # 개별 종목 오류는 기록만
            print(f"[backtest] {code}: {type(e).__name__}: {e}", file=sys.stderr)
    return out


def run_backtest(bt: BacktestConfig, workers: int | None = None, codes: list[str] | None = None) -> pd.DataFrame:
    if bt.pattern not in REGISTRY:
        raise ValueError(f"알 수 없는 패턴: {bt.pattern}")
    if bt.pattern == "vocal":
        raise ValueError("보컬은 날마다 전 시장 단면(거래대금 순위 · 테마 강도 · 대장)이 필요해 이 백테스트로는 잴 수 없다 — "
                         "검증은 기업추적 도구/보컬_백테스트.py (README '보컬 눌림목' 참고)")
    if bt.mode == "breakout_day" and bt.pattern in NO_BREAKOUT_DAY:
        raise ValueError(NO_BREAKOUT_DAY[bt.pattern])
    if bt.pattern == "undervalued":
        raise ValueError("저평가 종목은 기업추적 저평가 목록(외부 파일, 그날 하루치)을 붙이는 정보 칩이라 과거 날짜로 잴 수 없다 — "
                         "검증은 기업추적 도구/저평가V2_백테스트.py")
    ud = load_universe_data(_cfg(bt.history_days), offline=True, verbose=False)
    first = min(d.index[0] for d in ud.ohlcv.values())
    since = bt.since or str((first + pd.tseries.offsets.BDay(bt.min_bars)).date())
    bt = BacktestConfig(**{**bt.__dict__, "since": since})
    all_codes = [c for c in (codes or ud.ohlcv) if c in ud.ohlcv and len(ud.ohlcv[c]) > bt.min_bars]
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    if workers == 1 or len(all_codes) < 20:
        mkt = market_states_by_date(ud, pd.Timestamp(since))
        events = []
        for code in all_codes:
            events.extend(_events_for(code, bt, Config(), ud, mkt))
    else:
        chunks = [all_codes[i::workers * 4] for i in range(workers * 4)]
        events = []
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                 initargs=(since, bt.history_days)) as ex:
            for k, part in enumerate(ex.map(_worker, [(ch, bt) for ch in chunks]), 1):
                events.extend(part)
                print(f"\r  백테스트 {k}/{len(chunks)}", end="" if k < len(chunks) else "\n", file=sys.stderr, flush=True)
    df = pd.DataFrame(events)
    if not df.empty:
        names = ud.universe["name"].to_dict()
        df.insert(1, "name", df["code"].map(names))
        df = df.sort_values(["date", "code"]).reset_index(drop=True)
    return df


def first_entries(events: pd.DataFrame) -> pd.DataFrame:
    """stage 모드 보조: (종목, 패턴 시작일)마다 가장 이른 신호 1건만 남긴다.

    눌림목형 패턴(예: 2026-10-14 제거된 300억 장대양봉 눌림목)은 같은 기준봉에 대해 지지선·피벗이 매일 조금씩 달라져
    dedupe 키가 여러 번 생길 수 있다 → '처음 진입 가능했던 날' 한 번만 성과에 넣는다.
    start_date 가 없으면 돌파일, 그것도 없으면 신호일을 시작일로 본다."""
    if events.empty:
        return events
    ev = events.copy()
    anchor = ev["start_date"] if "start_date" in ev else pd.Series(None, index=ev.index, dtype=object)
    if "breakout_date" in ev:
        anchor = anchor.fillna(ev["breakout_date"])
    ev["_anchor"] = anchor.fillna(ev["date"])
    ev = ev.sort_values(["code", "date"]).drop_duplicates(["code", "_anchor"], keep="first")
    return ev.drop(columns="_anchor").sort_values(["date", "code"]).reset_index(drop=True)


def summarize_first_entries(events: pd.DataFrame, horizons=(5, 20, 60)) -> pd.DataFrame:
    """stage 모드 눌림목형 패턴 요약: ``first_entries`` 후 ``summarize``."""
    out = summarize(first_entries(events), horizons)
    out.attrs["first_entry"] = True
    return out


def summarize(events: pd.DataFrame, horizons=(5, 20, 60)) -> pd.DataFrame:
    """horizon 별 신호 수·평균/중앙 수익률·승률·지수 대비 초과수익·평균 최대역행."""
    rows = []
    for hz in horizons:
        col = f"ret_{hz}"
        if events.empty or col not in events:
            continue
        r = events[col].dropna()
        ex = (events[col] - events[f"idx_{hz}"]).dropna()
        rows.append({
            "보유일": hz, "신호수": len(r),
            "평균수익률%": round(r.mean() * 100, 2) if len(r) else math.nan,
            "중앙수익률%": round(r.median() * 100, 2) if len(r) else math.nan,
            "승률%": round((r > 0).mean() * 100, 1) if len(r) else math.nan,
            "지수대비초과%": round(ex.mean() * 100, 2) if len(ex) else math.nan,
            "평균최대역행%": round(events[f"mae_{hz}"].dropna().mean() * 100, 2) if len(r) else math.nan,
        })
    out = pd.DataFrame(rows)
    if not events.empty and "outcome" in events:
        # 손절 비율은 손절가가 있는 신호로만 — 손절 규칙 없는 식의 신호를 '손절 0%' 로 섞지 않는다
        hs = (events["has_stop"].fillna(True).astype(bool) if "has_stop" in events
              else pd.Series(True, index=events.index))
        if hs.any():
            oc = events.loc[hs, "outcome"].value_counts(normalize=True)
            out.attrs["outcome"] = {k: round(v * 100, 1) for k, v in oc.items()}
            out.attrs["outcome_n"] = int(hs.sum())
        if (~hs).any():
            tg = (events.loc[~hs, "outcome"] == "target").mean()
            out.attrs["no_stop"] = {"n": int((~hs).sum()), "target": round(tg * 100, 1)}
    return out
