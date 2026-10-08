"""워크포워드 이벤트 스터디: 과거 각 시점까지의 데이터만 잘라 탐지기를 돌리고, 신호 이후 수익률을 측정.

    python -m chart_screener backtest vcp                    # 돌파 당일 신호 (기본)
    python -m chart_screener backtest vcp --mode stage --stages near_pivot --step 5

방법
- 각 종목의 일봉을 시점 t 까지 잘라(df.iloc[:t+1]) StockContext 를 만들고 탐지기를 실행한다.
  RS 레이팅·지수·시장 상태·거래정지일도 t 시점까지만 쓴다 → 미래 참조 없음.
- 신호 (mode='breakout_day', 기본): 매 거래일(step=1) 탐지기를 실행해, 그날이 곧 돌파일
  (result.breakout_date == t) 인 경우만 집계. 돌파 당일 바로 이격 과다(+5% 초과)가 된 강한 돌파도 포함된다.
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


# 돌파일 사전 필터 — 각 패턴 규칙상 돌파일이 될 수 없는 날은 탐지기를 생략한다(속도 최적화).
#  종류: 'chg'(등락률 ≥ x) · 'up'(상승 마감) · 'near_high_up'(상승 마감 & 종가 ≥ 직전 20봉 최고가 × x)
#        · 'near_high'(종가 ≥ 직전 20봉 최고가 × x, 상승 마감 불필요) · 'none'(필터 없음, 매일 실행)
#  - 장기횡보 돌파: 전일 대비 +7% 이상이 필수 규칙 → 등락률 ≥ +6.9%
#  - 포켓 피벗: 상승 마감이 필수 → 상승일
#  - VCP: 피벗(최종 수축 고점)은 베이스 고점 대비 -15% 이내 → 상승 & 종가 ≥ 최근 20봉 최고가 × 0.84
#  - 컵앤핸들·CAN SLIM: 돌파 거래량 미달 봉은 돌파로 치지 않으므로, 거래량을 갖춘 '첫' 돌파봉이
#    하락 마감일 수 있다 → 상승 마감 조건 없이 고점 근접만 본다
#  - 그 밖의 베이스: 피벗이 베이스 상단 근처(찌르기·스파이크 여유 포함) → 상승 & 종가 ≥ 최근 20봉 최고가 × 0.85
#  - 300억 장대양봉 눌림목: 돌파가 아닌 눌림 매수 셋업 → 필터 없음
#  - 표에 없는 패턴: 가장 느슨한 고점 근접(0.85)만 적용
# scripts_validate_prefilter.py: 표본 45종목×9패턴에서 필터 유무의 신호 집합이 동일함을 확인했다.
# (컵앤핸들·CAN SLIM 은 상승 마감 조건을 뺀 뒤 재검증: 14/14·118/118 동일. 전 종목 컵앤핸들에서
#  구 필터가 놓친 하락 마감 돌파 5건이 복구됨.)
PREFILTER: dict[str, tuple[str, float | None]] = {
    "long_base_breakout": ("chg", 0.069),
    "pocket_pivot": ("up", None),
    "vcp": ("near_high_up", 0.84),
    "cup_handle": ("near_high", 0.85),
    "canslim": ("near_high", 0.85),
    "flat_base": ("near_high_up", 0.85),
    "double_bottom": ("near_high_up", 0.85),
    "three_weeks_tight": ("near_high_up", 0.85),
    "high_tight_flag": ("near_high_up", 0.85),
    "big_value_pullback": ("none", None),
}
DEFAULT_PREFILTER: tuple[str, float | None] = ("near_high", 0.85)


def _maybe_breakout_day(pattern: str, h: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = len(c)
    kind, x = PREFILTER.get(pattern, DEFAULT_PREFILTER)
    if kind == "none":
        return np.ones(n, bool)
    prev = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "chg":
            return c / prev - 1 >= x
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
    cand = _maybe_breakout_day(bt.pattern, h, c) if use_pf else np.ones(n, bool)
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
            if r.breakout_date != df.index[t].strftime("%Y-%m-%d"):
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
        # 손절 전 +target 도달 여부 (최대 마지막 horizon 까지)
        horizon_end = min(n, t + 1 + max(bt.horizons))
        outcome = "open"
        for j in range(t + 1, horizon_end):
            if r.stop and l[j] <= r.stop:
                outcome = "stop"
                break
            if h[j] >= entry * (1 + bt.target):
                outcome = "target"
                break
        ev["outcome"] = outcome
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

    눌림목형 패턴(예: 300억 장대양봉 눌림목)은 같은 장대양봉에 대해 지지선·피벗이 매일 조금씩 달라져
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
        oc = events["outcome"].value_counts(normalize=True)
        out.attrs["outcome"] = {k: round(v * 100, 1) for k, v in oc.items()}
    return out
