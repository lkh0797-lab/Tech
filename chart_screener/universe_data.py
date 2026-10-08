"""전 종목 데이터 적재 → StockContext 생성.

    ud = load_universe_data(Config(), offline=True)   # 캐시만 사용
    for ctx in iter_contexts(ud):
        ...
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import pandas as pd

from . import indicators as ind
from .config import CACHE_DIR, Config
from .data import OHLCVCache, fetch_index, fetch_many, fetch_universe, session_fraction
from .data.ohlcv import KST, SESSION_CLOSE, SESSION_OPEN
from .market import MarketState, analyze_market
from .patterns.base import StockContext

UNIVERSE_CACHE = CACHE_DIR / "universe.pkl"
REIT_RE = r"리츠|리얼티\d*$|REIT"


@dataclass
class UniverseData:
    universe: pd.DataFrame                       # 종목 메타 (code 인덱스)
    ohlcv: dict[str, pd.DataFrame]
    index: dict[str, pd.DataFrame]               # 'KOSPI' / 'KOSDAQ'
    market: dict[str, MarketState]
    rs: pd.DataFrame                             # 일자 × 종목 RS 레이팅
    asof: pd.Timestamp | None = None
    errors: dict[str, str] = field(default_factory=dict)
    breadth: dict = field(default_factory=dict)  # breadth.compute_breadth 결과 {'ALL','KOSPI','KOSDAQ'}
    breadth_hist: dict | None = None             # breadth.breadth_history 일별 표 (백테스트용)
    fetched_at: pd.Timestamp | None = None       # 종목목록 스냅샷을 받은 시각 (KST)


def _kst(ts) -> pd.Timestamp | None:
    if ts is None or pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    return ts.tz_localize(KST) if ts.tzinfo is None else ts.tz_convert(KST)


def snapshot_time(uni: pd.DataFrame) -> pd.Timestamp | None:
    """종목목록 스냅샷을 받은 시각. fetched_at 컬럼이 없는 구버전 캐시는 전 종목 traded_at 의 최댓값으로 대신."""
    for col in ("fetched_at", "traded_at"):
        if col in uni.columns:
            s = pd.to_datetime(uni[col], errors="coerce").dropna()
            if len(s):
                return _kst(s.max())
    return None


def partial_bar(last_date, fetched_at) -> tuple[bool, float]:
    """마지막 봉이 장중 미완성인지와 체결 비율: 마지막 봉 날짜 = 스냅샷 날짜 이고 스냅샷이 정규장
    (평일 09:00~15:30) 안에서 받아졌을 때만 미완성. 종목별 마지막 체결 시각은 쓰지 않는다."""
    at = _kst(fetched_at)
    if at is None or pd.Timestamp(last_date).date() != at.date():
        return False, 1.0
    if at.weekday() >= 5 or not (SESSION_OPEN <= at.time() < SESSION_CLOSE):
        return False, 1.0
    frac = session_fraction(at.to_pydatetime())
    return (True, frac) if frac < 1.0 else (False, 1.0)


def _progress(i: int, n: int) -> None:
    if i == n or i % 100 == 0:
        print(f"\r  일봉 수집 {i}/{n}", end="" if i < n else "\n", file=sys.stderr, flush=True)


def load_universe_data(cfg: Config | None = None, *, refresh: bool = False, offline: bool = False,
                       codes: list[str] | None = None, verbose: bool = True) -> UniverseData:
    cfg = cfg or Config()
    UNIVERSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    if offline:
        if not UNIVERSE_CACHE.exists():
            raise RuntimeError("오프라인 모드: 종목 목록 캐시가 없습니다. 먼저 온라인으로 한 번 실행하세요.")
        uni = pd.read_pickle(UNIVERSE_CACHE)
    else:
        uni = fetch_universe(cfg.data)
        uni.to_pickle(UNIVERSE_CACHE)
    full_uni = uni
    fetched_at = snapshot_time(uni)          # codes 로 거르기 전 전체 스냅샷 기준
    if cfg.data.exclude_reits and "name" in uni:  # 구버전 캐시에도 리츠 제외 규칙 적용
        uni = uni[~uni["name"].astype(str).str.contains(REIT_RE, regex=True)]
    uni = uni.set_index("code", drop=False)
    if codes:
        uni = uni[uni.index.isin(codes)]

    cache = OHLCVCache()
    from .data import ohlcv as _ohlcv
    data = fetch_many(uni.index, cfg.data, cache, refresh=refresh, offline=offline,
                      progress=_progress if verbose else None)
    errors = dict(_ohlcv.LAST_ERRORS)
    data = {c: d for c, d in data.items() if len(d) >= cfg.data.min_history_days}

    index = {m: fetch_index(m, cfg.data.history_days, cache, refresh=refresh, offline=offline)
             for m in ("KOSPI", "KOSDAQ")}

    # RS·시장 폭은 항상 '전 종목' 기준이어야 하므로, codes 로 일부만 요청한 경우에도
    # 캐시에 있는 전체 종목으로 계산을 시도한다.
    rs_source = data
    if codes:
        rs_source = dict(data)
        for c in full_uni["code"]:
            if c not in rs_source:
                d = cache.load(c)
                if d is not None and len(d) >= cfg.data.min_history_days:
                    rs_source[c] = d
    rs = ind.rs_rating_table({c: d["close"] for c, d in rs_source.items()})

    breadth, breadth_hist = {}, None
    try:
        from .breadth import breadth_history, summarize_history
        markets = dict(zip(full_uni["code"], full_uni["market"]))
        breadth_hist = breadth_history(rs_source, cfg.big_value_threshold, markets,
                                       min_avg_value=cfg.universe.min_avg_value_20d,
                                       min_price=cfg.universe.min_price, dates=index["KOSPI"].index)
        breadth = summarize_history(breadth_hist)
    except Exception as e:  # 시장 폭은 보조 지표 — 실패해도 스캔은 계속
        print(f"[breadth] 시장 폭 계산 생략: {type(e).__name__}: {e}", file=sys.stderr)

    market = {}
    for m, df in index.items():
        part, frac = partial_bar(df.index[-1], fetched_at)
        market[m] = analyze_market(m, df, partial_frac=frac if part else None, breadth=breadth.get(m))
    asof = max(d.index[-1] for d in data.values()) if data else None
    return UniverseData(uni, data, index, market, rs, asof, errors,
                        breadth=breadth, breadth_hist=breadth_hist, fetched_at=fetched_at)


def build_context(code: str, ud: UniverseData, cfg: Config | None = None) -> StockContext | None:
    cfg = cfg or Config()
    df = ud.ohlcv.get(code)
    if df is None or df.empty:
        return None
    row = ud.universe.loc[code] if code in ud.universe.index else None
    info = row.to_dict() if row is not None else {}
    market = info.get("market", "KOSPI")

    # 장중 미완성 봉 판정은 '스냅샷을 받은 시각'(fetched_at) 기준. 실행 시각(벽시계)을 쓰면 같은 캐시라도
    # 실행 시점마다 결과가 달라지고, 종목별 마지막 체결 시각(traded_at)을 쓰면 거래가 뜸한 종목이
    # 장 마감 후에도 미완성으로 잡힌다.
    last_date = df.index[-1]
    fetched = getattr(ud, "fetched_at", None)
    if fetched is None:
        fetched = snapshot_time(ud.universe)
    partial, frac = partial_bar(last_date, fetched)
    # 당일 실제 거래대금으로 마지막 봉 추정치를 교체 (그 종목의 마지막 체결일 = 마지막 봉 날짜일 때만)
    ts = _kst(info.get("traded_at")) if row is not None else None
    if ts is not None and ts.date() == last_date.date() and info.get("value", 0) > 0:
        df = df.copy()
        df.iloc[-1, df.columns.get_loc("value")] = float(info["value"])

    rs_hist = ud.rs[code].dropna() if code in ud.rs.columns else None
    rs_now = float(rs_hist.iloc[-1]) if rs_hist is not None and len(rs_hist) else None
    return StockContext(
        code=code, name=info.get("name", code), market=market, df=df, cfg=cfg,
        index_df=ud.index.get(market), rs_rating=rs_now, rs_rating_hist=rs_hist,
        market_state=ud.market.get(market), partial=partial, session_frac=frac, info=info,
    )


def passes_universe_filter(ctx: StockContext) -> tuple[bool, list[str]]:
    f = ctx.cfg.universe
    why = []
    c = float(ctx.close.iloc[-1])
    if c < f.min_price:
        why.append(f"주가 {c:,.0f}원 < {f.min_price:,.0f}원")
    avg_val = float(ctx.value.iloc[-20:].mean())
    if avg_val < f.min_avg_value_20d:
        why.append(f"20일 평균 거래대금 {avg_val / 1e8:,.0f}억 < {f.min_avg_value_20d / 1e8:,.0f}억")
    mcap = ctx.info.get("market_cap")
    if mcap and mcap == mcap and mcap < f.min_market_cap:
        why.append(f"시가총액 {mcap / 1e8:,.0f}억 < {f.min_market_cap / 1e8:,.0f}억")
    return (not why), why


def iter_contexts(ud: UniverseData, cfg: Config | None = None, apply_filter: bool = True):
    cfg = cfg or Config()
    for code in ud.ohlcv:
        ctx = build_context(code, ud, cfg)
        if ctx is None:
            continue
        if apply_filter and not passes_universe_filter(ctx)[0]:
            continue
        yield ctx
