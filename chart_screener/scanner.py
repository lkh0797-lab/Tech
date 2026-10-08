"""전 종목 스캔: 모든 탐지기 실행 → 종합 점수 → 후보 정렬 → 포지션 계획·300억 레이더·업종 강도.

포지션 계획 (position_plan, Config 의 계좌 설정)
    진입가 = max(피벗, 현재가) (300억 장대양봉 눌림목은 50%선 지정가), 손절가 = 대표 패턴 손절가.
    수량 = floor(계좌 × 1회 위험 ÷ (진입가 − 손절가)) 를 계좌 × 최대 비중·20일 평균 거래대금 × 2% 로 제한.
    손절폭 > max_entry_risk(10%) 면 '눌림 대기'(수량 0), 돌파 실패·손절가 이탈은 '관망'(수량 0).
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import scoring
from .config import Config
from .data import now_kst
from .patterns import REGISTRY, PatternResult, StockContext, run_all
from .patterns.base import FAILED
from .universe_data import UniverseData, iter_contexts

TOP_GROUPS = 15


@dataclass
class StockScan:
    code: str
    name: str
    market: str
    close: float
    change_pct: float
    market_cap: float | None
    rs: float | None
    value_today: float
    avg_value_20: float
    max_value_5: float
    partial: bool
    results: dict[str, PatternResult]
    score: scoring.ScoreBreakdown
    ctx: StockContext | None = field(default=None, repr=False)
    position: dict | None = None       # position_plan() 결과
    badge: str | None = None           # 직전 스캔 대비: '신규' | '단계상승' | '돌파' | '실패' (journal)
    prev_stage: str | None = None      # 직전 스캔의 대표 단계 (journal)
    groups: dict | None = None         # sector.stock_groups() 결과
    leader: bool = False               # 주도주(베이스 없음)

    @property
    def actionable(self) -> bool:
        return self.score.best_stage in scoring.ACTIONABLE

    def best(self) -> PatternResult | None:
        return self.results.get(self.score.best_pattern) if self.score.best_pattern else None

    def lead(self) -> PatternResult | None:
        """표시용 대표 결과: 최고 베이스 패턴, 없으면 CAN SLIM."""
        b = self.best()
        if b is not None:
            return b
        cs = self.results.get("canslim")
        return cs if cs is not None and cs.detected else None

    @property
    def lead_name(self) -> str | None:
        r = self.lead()
        return r.name if r is not None else None

    def entry_risk(self) -> tuple[float | None, float | None]:
        """(진입 기준가, 손절폭). 진입가 = max(피벗, 현재가): 돌파 전엔 피벗 매수, 돌파 후엔 현재가 매수.
        300억 장대양봉 눌림목(재돌파 전)은 min(현재가, 50%선 지정가) — scoring.planned_entry, position_plan 과 같은 값.
        손절폭이 음수면 이미 손절가를 이탈한 상태."""
        r = self.lead()
        if r is None or not r.pivot:
            return None, None
        entry = scoring.planned_entry(r, self.close)
        risk = (1 - float(r.stop) / entry) if r.stop and entry else None
        return entry, risk


def _account(cfg: Config) -> dict:
    return {"size": float(cfg.account_size), "risk_per_trade": float(cfg.risk_per_trade),
            "max_position_pct": float(cfg.max_position_pct), "max_entry_risk": float(cfg.max_entry_risk),
            "max_liquidity_pct": float(cfg.max_liquidity_pct)}


@dataclass
class ScanResult:
    asof: pd.Timestamp | None
    generated_at: pd.Timestamp
    market: dict
    stocks: list[StockScan]            # 후보만, 종합점수 내림차순
    scanned: int
    elapsed: float
    patterns: list[str]
    errors: dict[str, str] = field(default_factory=dict)
    radar: list[dict] = field(default_factory=list)     # 최근 10일 300억↑ +7%↑ 양봉 (유동성 필터 통과 전 종목)
    groups: list[dict] = field(default_factory=list)    # 업종·테마 강도 상위 15 (sector.group_strength 행, 점수순)
    breadth: dict | None = None                         # UniverseData.breadth (시장 폭)
    prev_asof: str | None = None                        # 비교한 직전 스캔 기준일 (journal)
    account: dict = field(default_factory=lambda: _account(Config()))
    dropped: list[dict] = field(default_factory=list)   # 직전 스캔 후보 중 이번에 빠진 종목 (journal)


# ---------------------------------------------------------------- 포지션 계획
def _num(x) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def position_plan(s: StockScan, cfg: Config | None = None) -> dict | None:
    """대표 패턴의 진입가·손절가로 계좌 위험 기준 수량을 계산. 대표 패턴(피벗·손절가)이 없으면 None.

    반환 {entry, stop, risk_pct(비율), shares, amount(원), max_loss(원), plan(한글), cap(수량을 묶은 한도:
    "위험"|"비중"|"유동성", 관망·눌림 대기면 None)}
    """
    cfg = cfg or Config()
    r = s.lead()
    pivot, stop = (_num(r.pivot), _num(r.stop)) if r is not None else (None, None)
    if r is None or not pivot or not stop:
        return None
    close = s.close
    # 300억 장대양봉 눌림목: 재돌파(breakout) 전에는 50%선 지정가(호가 단위로 맞춘 피벗)가 진입 계획
    support = scoring.pullback_limit(r)
    zone_top = scoring.pullback_zone_top(r) if support else None
    if support:
        entry = min(close, zone_top)
        plan = (f"50%선 {support:,.0f}~{zone_top:,.0f} 눌림 구간 지정가 대기" if close > zone_top
                else f"50%선 눌림 구간 — {entry:,.0f} 매수 (지지 {support:,.0f})")
        plan += f" · 손절: 종가 {stop:,.0f} 이탈"
    else:
        entry = max(pivot, close)
        if close > pivot:
            plan = f"돌파 확인 — 현재가 {close:,.0f} 매수 (피벗 {pivot:,.0f})"
        elif r.breakout_date:
            plan = f"피벗 {pivot:,.0f} 재돌파 매수"
        else:
            plan = f"피벗 {pivot:,.0f} 돌파 매수"
    risk = 1 - stop / entry if entry > 0 else None
    out = {"entry": round(entry, 2), "stop": round(stop, 2), "risk_pct": round(risk, 4) if risk is not None else None,
           "shares": 0, "amount": 0.0, "max_loss": 0.0, "plan": plan, "cap": None}
    if r.stage == FAILED:
        out["plan"] = "돌파 실패 — 관망"
        return out
    # 돌파 전 피벗 매수(역지정가)는 지금 가격이 손절가 아래여도 유효 — 진입 후에만 손절가가 의미 있다
    entered = bool(r.breakout_date) or support is not None
    if risk is None or risk <= 0 or (entered and close <= stop):
        out["plan"] = "손절가 이탈 — 관망"
        return out
    if risk > cfg.max_entry_risk:
        out["plan"] = f"눌림 대기 (손절폭 {risk:.1%} > {cfg.max_entry_risk:.0%})"
        return out
    per_share = entry - stop
    if support and s.ctx is not None:
        # 눌림목 손절은 종가 기준 → 장중 변동(ATR)만큼은 더 밀릴 수 있다고 보고 수량을 계산
        atr = float(s.ctx.atr(14).iloc[-1])
        if atr == atr and atr > per_share:
            per_share = atr
            out["plan"] += f" (수량은 ATR {atr:,.0f} 기준)"
    caps = {
        "위험": math.floor(cfg.account_size * cfg.risk_per_trade / per_share),
        "비중": math.floor(cfg.account_size * cfg.max_position_pct / entry),
        "유동성": math.floor(max(0.0, s.avg_value_20) * cfg.max_liquidity_pct / entry),
    }
    cap = min(caps, key=caps.get)
    shares = max(0, int(caps[cap]))
    out.update(shares=shares, amount=round(shares * entry), max_loss=round(shares * per_share), cap=cap)
    return out


# ---------------------------------------------------------------- 점수
def rescore(s: StockScan, cfg: Config | None = None) -> None:
    """결과·수급·업종 정보가 바뀐 뒤 종합 점수·주도주 여부·포지션 계획을 다시 계산."""
    ctx = s.ctx
    cfg = cfg or (ctx.cfg if ctx is not None else Config())
    s.score = scoring.compute(
        s.results, s.rs, ctx.market_state if ctx is not None else None,
        recent_big_value=bool(s.max_value_5 >= cfg.big_value_threshold), close=s.close,
        dates=ctx.df.index if ctx is not None else None, groups=s.groups,
    )
    s.leader = s.score.leader
    s.position = position_plan(s, cfg)


def scan_one(ctx: StockContext, names: list[str] | None = None, keep_ctx: bool = True) -> StockScan:
    results = run_all(ctx, names)
    vals = ctx.value
    close = float(ctx.close.iloc[-1])
    prev = float(ctx.close.iloc[-2]) if ctx.n > 1 else close
    s = StockScan(
        code=ctx.code, name=ctx.name, market=ctx.market, close=close, change_pct=close / prev - 1,
        market_cap=ctx.info.get("market_cap"), rs=ctx.rs_rating, value_today=float(vals.iloc[-1]),
        avg_value_20=float(vals.iloc[-20:].mean()), max_value_5=float(vals.iloc[-5:].max()),
        partial=ctx.partial, results=results, score=None, ctx=ctx,  # type: ignore[arg-type]
    )
    rescore(s, ctx.cfg)
    if not keep_ctx:
        s.ctx = None
    return s


# ---------------------------------------------------------------- 300억 장대양봉 레이더
def radar_entry(ctx: StockContext, s: StockScan | None = None) -> dict | None:
    """최근 radar_days 거래일 안의 가장 최근 '거래대금 300억↑ & +7%↑' 양봉. 없으면 None.

    지지선(support) = 몸통 50% 선 (상한가권 +25%↑ 갭 상승은 min(시가, 전일 종가)와 종가의 중간).
    300억 장대양봉 눌림목 결과가 같은 날 봉을 가리키면 그 metrics.support 를 쓴다.
    """
    cfg = ctx.cfg
    n = ctx.n
    if n < 2:
        return None
    c = ctx.close.to_numpy(dtype=float)
    o = ctx.df["open"].to_numpy(dtype=float)
    v = ctx.value.to_numpy(dtype=float)
    for i in range(n - 1, max(0, n - cfg.radar_days) - 1, -1):
        if i < 1 or not (c[i - 1] > 0):
            continue
        chg = c[i] / c[i - 1] - 1
        if v[i] < cfg.big_value_threshold or chg < cfg.radar_min_change:
            continue
        date = ctx.date(i)
        low_body = min(o[i], c[i - 1]) if chg >= 0.25 else o[i]
        support = (low_body + c[i]) / 2
        bvp = s.results.get("big_value_pullback") if s is not None else None
        if bvp is not None and (bvp.metrics or {}).get("candle_date") == date and _num(bvp.metrics.get("support")):
            support = float(bvp.metrics["support"])
        return {"code": ctx.code, "name": ctx.name, "market": ctx.market, "date": date, "days_ago": n - 1 - i,
                "change": round(float(chg), 4), "value": float(v[i]), "close": float(c[-1]),
                "support": round(float(support), 2), "holding": bool(c[-1] >= support), "themes": []}
    return None


# ---------------------------------------------------------------- 업종·테마 강도
def _group_strength(ud: UniverseData, offline: bool, sector_map, verbose: bool):
    """(sector_map, strength, stock_groups 함수) — 모듈·자료가 없으면 (None, None, None)."""
    try:
        from .data.sector import load_sector_map
        from .sector import group_strength, stock_groups
    except Exception:
        return None, None, None
    try:
        sm = sector_map if sector_map is not None else load_sector_map(offline=offline)
        if sm is None or len(sm) == 0:
            return None, None, None
        strength = group_strength(ud, sm)
        if strength is None or len(strength) == 0:
            return sm, None, None
        # 계약: group_strength 의 상위 행 = 점수 내림차순 (업종·테마 공통 척도). rank_pct 는 종류 안 백분위라
        # 정렬 기준으로 쓰면 업종 1위와 테마 1위가 점수와 무관하게 맨 앞에 온다.
        key = "score" if "score" in strength.columns else ("rank_pct" if "rank_pct" in strength.columns else None)
        if key:
            strength = strength.sort_values(key, ascending=False, kind="stable")
        return sm, strength, stock_groups
    except Exception as e:
        if verbose:
            print(f"  업종·테마 강도 생략: {type(e).__name__}: {e}", file=sys.stderr)
        return None, None, None


def run_scan(ud: UniverseData, cfg: Config | None = None, patterns: list[str] | None = None,
             include_all: bool = False, verbose: bool = True, *, offline: bool = True,
             sector_map: pd.DataFrame | None = None) -> ScanResult:
    """전 종목 스캔. offline=False 면 업종·테마 지도가 없거나 오래됐을 때 새로 받는다(기본은 캐시만)."""
    cfg = cfg or Config()
    t0 = time.perf_counter()
    out: list[StockScan] = []
    radar: list[dict] = []
    errors: dict[str, str] = {}
    ctxs = list(iter_contexts(ud, cfg, apply_filter=True))
    for k, ctx in enumerate(ctxs, 1):
        try:
            s = scan_one(ctx, patterns)
        except Exception as e:  # 한 종목 오류로 전체 스캔이 멈추지 않게
            errors[ctx.code] = f"{type(e).__name__}: {e}"
            continue
        for name, r in s.results.items():
            for w in r.warnings:
                if w.startswith("탐지 오류"):
                    errors[f"{ctx.code}:{name}"] = w
        try:
            rd = radar_entry(ctx, s)
        except Exception as e:
            rd = None
            errors[f"{ctx.code}:radar"] = f"{type(e).__name__}: {e}"
        if rd is not None:
            radar.append(rd)
        if include_all or scoring.is_candidate(s.results, s.rs):
            out.append(s)
        else:
            s.ctx = None
        if verbose and (k % 50 == 0 or k == len(ctxs)):
            print(f"\r  패턴 분석 {k}/{len(ctxs)}", end="" if k < len(ctxs) else "\n", file=sys.stderr, flush=True)

    sm, strength, stock_groups = _group_strength(ud, offline, sector_map, verbose)
    top_groups: list[dict] = []
    if strength is not None:
        for s in out:
            try:
                s.groups = stock_groups(s.code, sm, strength)
            except Exception:
                s.groups = None
            if s.ctx is not None:
                rescore(s, cfg)
        top_groups = strength.head(TOP_GROUPS).to_dict("records")
    if sm is not None and len(sm) and radar:
        themes = {c: list(t) if isinstance(t, (list, tuple, np.ndarray)) else []
                  for c, t in zip(sm["code"], sm["themes"])}
        for rd in radar:
            rd["themes"] = themes.get(rd["code"], [])
    radar.sort(key=lambda d: (d["days_ago"], -d["value"]))
    out.sort(key=lambda s: -s.score.composite)
    return ScanResult(
        asof=ud.asof, generated_at=pd.Timestamp(now_kst().replace(tzinfo=None)),
        market=ud.market, stocks=out, scanned=len(ctxs), elapsed=time.perf_counter() - t0,
        patterns=list(patterns or REGISTRY), errors=errors, radar=radar, groups=top_groups,
        breadth=getattr(ud, "breadth", None) or None, account=_account(cfg),
    )


def enrich_investor(scan: ScanResult, top: int = 60, offline: bool = False, verbose: bool = True) -> int:
    """상위 후보에만 기관·외국인 순매매를 붙이고 CAN SLIM(I)·종합점수를 다시 계산. 반환: 붙인 종목 수."""
    from .data.investor import attach_investor

    cs = REGISTRY.get("canslim")
    done = 0
    targets = [s for s in scan.stocks[:top] if s.ctx is not None]
    for k, s in enumerate(targets, 1):
        try:
            got = attach_investor(s.ctx, offline=offline)
        except Exception:
            got = None
        if got is not None:
            done += 1
            if cs is not None and "canslim" in s.results:
                try:
                    s.results["canslim"] = cs[1](s.ctx)
                    rescore(s)
                except Exception as e:
                    s.results["canslim"].warnings.append(f"수급 반영 재계산 실패: {type(e).__name__}: {e}")
        if verbose and (k % 10 == 0 or k == len(targets)):
            print(f"\r  수급(기관·외국인) {k}/{len(targets)}", end="" if k < len(targets) else "\n",
                  file=sys.stderr, flush=True)
    scan.stocks.sort(key=lambda s: -s.score.composite)
    return done


def investor_summary(s: StockScan, days: int = 20) -> dict | None:
    """최근 n일 기관·외국인 순매수 금액(원, 순매매 주식수 × 종가 근사)."""
    inv = s.ctx.info.get("investor") if s.ctx is not None else None
    if inv is None or len(inv) == 0:
        return None
    t = inv.iloc[-days:]
    px = t["close"].where(t["close"] > 0, s.close)
    return {
        "days": int(len(t)), "asof": f"{t.index[-1]:%Y-%m-%d}",
        "inst": float((t["inst_net"] * px).sum()), "foreign": float((t["foreign_net"] * px).sum()),
        "foreign_ratio": float(t["foreign_ratio"].iloc[-1]) if "foreign_ratio" in t else None,
    }


# ---------------------------------------------------------------- 표 변환
FRAME_COLUMNS = [
    "종목코드", "종목명", "시장", "종가", "등락률", "종합점수", "배지", "RS", "대표패턴", "단계", "피벗", "피벗대비",
    "손절가", "손절폭%", "진입계획", "권장수량", "투입금액(만원)", "최대손실(만원)", "업종", "테마", "탐지패턴",
    "20일평균거래대금(억)", "당일거래대금(억)", "시가총액(억)", "기관20일순매수(억)", "외국인20일순매수(억)",
]


def _round(x, div: float = 1.0, nd: int = 0):
    f = _num(x)
    if f is None:
        return None
    v = round(f / div, nd)
    return int(v) if nd == 0 else v


def to_frame(scan: ScanResult) -> pd.DataFrame:
    """요약 표 (CSV/엑셀 출력용). 후보가 없으면 열만 있는 빈 표."""
    rows = []
    for s in scan.stocks:
        best = s.lead()
        _, risk = s.entry_risk()
        pos = s.position or {}
        g = s.groups or {}
        themes = [t[0] if isinstance(t, (list, tuple)) else str(t) for t in (g.get("themes") or [])][:3]
        label = best.label if best else (scoring.LEADER_TAG if s.leader else "")
        row = {
            "종목코드": s.code, "종목명": s.name, "시장": s.market, "종가": s.close,
            "등락률": round(s.change_pct * 100, 2), "종합점수": s.score.composite, "배지": s.badge or "",
            "RS": s.rs, "대표패턴": label,
            "단계": best.stage_label if best else "", "피벗": best.pivot if best else None,
            "피벗대비": round((s.close / best.pivot - 1) * 100, 2) if best and best.pivot else None,
            "손절가": best.stop if best else None,
            "손절폭%": round(risk * 100, 2) if risk is not None else None,
            "진입계획": pos.get("plan", ""),
            "권장수량": pos.get("shares") if pos else None,
            "투입금액(만원)": _round(pos.get("amount"), 1e4) if pos else None,
            "최대손실(만원)": _round(pos.get("max_loss"), 1e4) if pos else None,
            "업종": g.get("sector") or "", "테마": ", ".join(themes),
            "탐지패턴": ", ".join(REGISTRY[n][0] for n in s.score.detected_bases if n in REGISTRY),
            "20일평균거래대금(억)": _round(s.avg_value_20, 1e8, 1),
            "당일거래대금(억)": _round(s.value_today, 1e8, 1),
            "시가총액(억)": _round(s.market_cap, 1e8),
        }
        inv = investor_summary(s)
        row["기관20일순매수(억)"] = round(inv["inst"] / 1e8, 1) if inv else None
        row["외국인20일순매수(억)"] = round(inv["foreign"] / 1e8, 1) if inv else None
        for name, r in s.results.items():
            row[f"{name}_점수"] = round(r.score, 1) if r.detected else None
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=FRAME_COLUMNS)
    df = pd.DataFrame(rows)
    df["권장수량"] = df["권장수량"].astype("Int64")
    return df
