"""전 종목 스캔: 모든 탐지기 실행 → 종합 점수 → 후보 정렬 → 포지션 계획·300억 레이더·업종 강도.

포지션 계획 (position_plan, Config 의 계좌 설정)
    진입가 = max(피벗, 현재가), 손절가 = 대표 패턴 손절가 — 손절가가 없는 패턴(컵 앤 핸들 식 · 빗각 돌파 임박)은 계획을 내지 않는다.
    수량 = floor(계좌 × 1회 위험 ÷ (진입가 − 손절가)) 를 계좌 × 최대 비중·20일 평균 거래대금 × 2% 로 제한.
    손절폭 > max_entry_risk(10%) 면 수량 0 — 피벗 기준 손절폭(진입가 바닥)도 넘으면 '관망'(눌림으로 줄지 않음),
    아니면 '눌림 대기'(피벗 쪽으로 눌리면 줄어듦). 돌파 실패 · 손절가 이탈은 '관망'(수량 0).
    '피벗 X 재돌파 매수'(돌파 뒤 피벗 아래)는 Tech 공통 규칙(구현 선택) — 《차트의 기술》 기법에는 재진입 규칙이 없어 그렇게 적는다.
    장중 스캔에서 완성 봉만 판정하는 기법(scoring.EOD_PATTERNS)은 단계와 같은 봉(어제 종가)으로 진입가 · 손절폭 · 계획을 잰다
    (StockScan.basis). 저가 기준 손절(scoring.LOW_STOP_PATTERNS)이 오늘 장중 저가로 이미 깨졌으면 '손절가 이탈 — 관망'.
    대표(lead)는 베이스 패턴의 피벗 있는 결과만 — 신호 · 관찰 패턴만 걸린 후보는 계획 없음(plan_text 가 이유를 적는다).

기법 공통 칸 (technique_panel — 《차트의 기술》 영상 기법, 표시만)
    탐지 전에 ctx.info 에 업종 · 테마 강도(groups) · 업종 RS · 공시위험을 넣어 패턴 모듈의 체크리스트도 2 · 5 · 9 번을 채우고,
    후보마다 StockScan.panel(체크리스트 10 '검증 전' · 청산 계획) · badges(저평가 등급 · 공시위험), 스캔마다
    ScanResult.market_ctx(지수 120일선 · 낙폭 · 되돌림 · 월봉 적삼병). 수급을 붙인 뒤에는 refresh_flow_patterns 로
    60일선 수급 돌파의 수급 라벨을 다시 잰다.
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import scoring, technique_panel
from .config import Config
from .data import now_kst
from .patterns import REGISTRY, PatternResult, StockContext, run_all
from .patterns.base import EXTENDED, FAILED
from .universe_data import UniverseData, iter_contexts, passes_universe_filter

TOP_GROUPS = 15
NO_STOP_PLAN = "손절 규칙 없는 식 — 매수 계획(수량) 없음"   # 피벗은 있으나 손절가가 없는 대표 패턴 (컵 앤 핸들)
# 돌파 뒤 피벗 아래로 되밀린 기법 결과의 '재돌파 매수' — 기법(영상 · 부록)에 재진입 규칙이 없어 Tech 공통 규칙임을 적는다
RETRY_ORIGIN = " (Tech 공통 규칙 · 구현 선택 — 기법 규칙 아님)"
STAGE_SHORT = {"breakout": "돌파", "near_pivot": "근접", "forming": "형성", "extended": "이격", "failed": "실패"}


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
    kst: list = field(default_factory=list)   # 증권사(KIS) 종목 상태 태그: 관리종목 · 투자경고 · 단기과열 …
    kis: dict | None = None            # 증권사 목표가 · 투자의견 · 추정실적 요약 (kis_scan.stock_kis)
    thin: str | None = None            # 저평가 목록 종목이 유동성 문턱 밑이라 '패턴만' 잰 경우 그 사유(후보 · 레이더에는 안 넣는다)
    panel: dict | None = None          # 기법 공통 칸 (technique_panel.stock_panel): 체크리스트 10(검증 전) · 청산 계획 — 후보만
    badges: dict | None = None         # 저평가 등급 · 공시위험 꼬리표 (technique_panel.badges)
    eod_close: float | None = None     # 장중 스캔: 마지막 완성 봉 종가 (EOD_PATTERNS 의 단계 · 계획 기준)
    eod_date: str | None = None        # 그 봉 날짜

    def basis(self, r: PatternResult | None) -> tuple[float, bool]:
        """(r 의 단계와 같은 봉의 종가, 어제 완성 봉 기준인가). 장중 스캔의 EOD_PATTERNS 결과는 어제 종가, 그 밖은 지금가.
        단 장중 저가로 이미 확정된 결과(metrics['intraday_final'] — 단계가 오늘 봉으로 정해짐)는 지금가."""
        if (r is not None and self.partial and self.eod_close is not None
                and r.name in scoring.EOD_PATTERNS and not (r.metrics or {}).get("intraday_final")):
            return float(self.eod_close), True
        return self.close, False

    def today_low(self) -> float | None:
        """오늘(마지막 봉) 저가 — ctx 가 없으면 None."""
        if self.ctx is None or "low" not in self.ctx.df or not len(self.ctx.df):
            return None
        return _num(self.ctx.df["low"].iloc[-1])

    @property
    def actionable(self) -> bool:
        return self.score.best_stage in scoring.ACTIONABLE

    def best(self) -> PatternResult | None:
        return self.results.get(self.score.best_pattern) if self.score.best_pattern else None

    def lead(self) -> PatternResult | None:
        """대표 결과: 종합 점수가 고른 베이스 패턴 (피벗 있는 결과, 없으면 None)."""
        return self.best()

    @property
    def lead_name(self) -> str | None:
        r = self.lead()
        return r.name if r is not None else None

    def display_lead(self) -> PatternResult | None:
        """표시용 대표 (점수 · 매수 계획 · 실시간 감시에는 lead() 만 쓴다). 순서: lead() → 후보를 만든 신호 패턴 결과
        (SIGNAL_CANDIDATE_STAGES) → 관찰 칩(10% 주도주 · 보컬) → 피벗 없는 베이스 결과(피보 신호 전) → 그 밖 신호 패턴 결과."""
        r = self.lead()
        if r is not None:
            return r
        res = self.results
        order = ([n for n in scoring.SIGNAL_PATTERNS if scoring.signal_candidate(n, res.get(n))]
                 + list(scoring.OBSERVE_PATTERNS) + list(scoring.BASE_PATTERNS) + list(scoring.SIGNAL_PATTERNS))
        for n in order:
            x = res.get(n)
            if x is not None and x.detected:
                return x
        return None

    def live_lead(self) -> PatternResult | None:
        """실시간 감시용 대표 — LIVE_PATTERNS(컵 앤 핸들)의 피벗 있는 결과만 (lead() 가 그것이면 lead())."""
        r = self.lead()
        if r is not None and r.name in scoring.LIVE_PATTERNS:
            return r
        for n in scoring.LIVE_PATTERNS:
            x = self.results.get(n)
            if scoring.has_pivot(x):
                return x
        return None

    def entry_risk(self) -> tuple[float | None, float | None]:
        """(진입 기준가, 손절폭). 진입가 = max(피벗, 현재가): 돌파 전엔 피벗 매수, 돌파 후엔 현재가 매수
        (scoring.planned_entry, position_plan 과 같은 값). 손절가가 없으면 손절폭 None, 음수면 이미 손절가 이탈."""
        r = self.lead()
        if r is None or not r.pivot:
            return None, None
        entry = scoring.planned_entry(r, self.basis(r)[0])
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
    dropped: list[dict] = field(default_factory=list)   # 직전 스캔 후보 중 이번에 빠진 종목 (journal) + 상태 제외(reason)
    excluded: list[dict] = field(default_factory=list)  # 증권사 상태(거래정지 · 정리매매 · 관리종목 · 투자위험)로 뺀 후보
    kis: dict | None = None                             # 증권사 자료 요약 (kis_scan.KISScan.report_info) — 없으면 네이버만
    value: object | None = None                         # 기업추적 저평가 목록 (value_list.ValueList) — 없으면 탭 · 칩 없음
    value_scans: dict = field(default_factory=dict)     # {code: StockScan} 목록 종목 중 분석한 것 (후보 아니어도, ctx 유지)
    value_skipped: dict = field(default_factory=dict)   # {code: value_list.skipped_entry} 분석 대상 밖 목록 종목
    include_all: bool = False                           # run_scan(include_all=True) — 후보 조건 없이 전부 담은 스캔
    market_ctx: dict | None = None                      # 시장 맥락 칸 (technique_panel.market_panel) — 지수 120일선 · 낙폭 · 되돌림 · 월봉 적삼병
    tech_info: dict | None = None                       # 기법 공통 입력 요약 (공시위험 파일 · 업종 RS 기준일 — technique_panel.ScanInputs.summary)


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
    close, eod = s.basis(r) if hasattr(s, "basis") else (s.close, False)
    entry = max(pivot, close)
    at = f"{getattr(s, 'eod_date', None) or '어제'} 종가" if eod else "현재가"
    if r.name in ("fib_pullback", "trendline_fib") and (r.metrics or {}).get("phase") == "SIGNAL":
        plan = f"신호 종가 {pivot:,.0f} 매수 (기법 진입 — 반등 양봉 종가)"      # 신호 봉 = 진입가 그대로 (영상 [27:00, 51:00])
    elif close > pivot or (r.breakout_date and close >= pivot):
        plan = f"돌파 확인 — {at} {close:,.0f} 매수 (피벗 {pivot:,.0f})"
    elif r.breakout_date:
        plan = f"피벗 {pivot:,.0f} 재돌파 매수" + ("" if r.name == "cup_with_handle" else RETRY_ORIGIN)
    else:
        plan = f"피벗 {pivot:,.0f} 돌파 매수"
    if eod:
        plan += " · 장중 — 이 기법은 완성 봉으로만 판정(오늘 미완성 봉 안 씀)"
    risk = 1 - stop / entry if entry > 0 else None
    out = {"entry": round(entry, 2), "stop": round(stop, 2), "risk_pct": round(risk, 4) if risk is not None else None,
           "shares": 0, "amount": 0.0, "max_loss": 0.0, "plan": plan, "cap": None}
    fin = (r.metrics or {}).get("intraday_final")
    if isinstance(fin, dict):         # 장중 저가로 이미 확정된 손절 · 무효 (저가는 내려가기만 — 마감 뒤에도 그대로)
        out["plan"] = f"손절가 이탈 — 관망 ({fin.get('text') or '장중 확정(저가)'})"
        return out
    if r.stage == FAILED:
        out["plan"] = "돌파 실패 — 관망"
        return out
    if r.stage == EXTENDED:           # 단계가 '매수 범위 밖'인데 '돌파 확인 — 매수' 수량을 내면 서로 어긋난다
        # 매수 범위 기준은 패턴마다 다르다(컵 앤 핸들 식 = 진입가 × 1.05, 빗각 = 돌파가 × 1.05) — 퍼센트는 패턴 이유 줄에
        out["plan"] = (f"이격 과다 — 추격 매수 안 함 ({at} {close:,.0f} · 피벗 {pivot:,.0f} · 패턴의 매수 범위 밖) "
                       f"· 피벗 쪽으로 눌리면 다시 계산 — 눌림 대기")
        if eod:
            out["plan"] += " · 장중 — 이 기법은 완성 봉으로만 판정(오늘 미완성 봉 안 씀)"
        return out
    hold = scoring.plan_hold(r)       # 기법상 아직 사지 않는 상태 (빗각 거래량 미달 돌파 · 안착 확인 대기)
    if hold:
        out["plan"] = hold
        return out
    # 돌파 전 피벗 매수(역지정가)는 지금 가격이 손절가 아래여도 유효 — 진입 후에만 손절가가 의미 있다
    entered = bool(r.breakout_date)
    low = s.today_low() if hasattr(s, "today_low") and s.partial else None
    if entered and r.name in scoring.LOW_STOP_PATTERNS and low is not None and low <= stop:
        out["plan"] = f"손절가 이탈 — 관망 (오늘 장중 저가 {low:,.0f} ≤ 손절 {stop:,.0f} · 저가 기준 손절은 마감 뒤에도 그대로)"
        return out
    if risk is None or risk <= 0 or (entered and close <= stop):
        out["plan"] = "손절가 이탈 — 관망"
        return out
    if risk > cfg.max_entry_risk:
        pr = 1 - stop / pivot
        if pr > cfg.max_entry_risk:   # 진입가 바닥 = 피벗 — 눌림으로 손절폭이 줄지 않는다
            what = ("진입가 = 신호 종가" if r.name in ("fib_pullback", "trendline_fib") and entered
                    else "진입가 = 돌파가" if entered else "피벗 진입 기준")
            out["plan"] = f"관망 — 손절폭 {pr:.1%} > {cfg.max_entry_risk:.0%} ({what} {pivot:,.0f} · 눌림으로 줄지 않음)"
        else:
            out["plan"] = (f"눌림 대기 (손절폭 {risk:.1%} > {cfg.max_entry_risk:.0%} — 피벗 {pivot:,.0f} 쪽으로 눌리면 "
                           f"다시 계산 · 피벗 기준 {pr:.1%})")
        return out
    per_share = entry - stop
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
    """결과·업종 정보가 바뀐 뒤 종합 점수·포지션 계획을 다시 계산."""
    ctx = s.ctx
    cfg = cfg or (ctx.cfg if ctx is not None else Config())
    eod = getattr(s, "eod_close", None) if s.partial else None
    s.score = scoring.compute(
        s.results, s.rs, ctx.market_state if ctx is not None else None,
        recent_big_value=bool(s.max_value_5 >= cfg.big_value_threshold), close=s.close,
        dates=ctx.df.index if ctx is not None else None, groups=s.groups,
        eod_close=eod, eod_dates=ctx.df.index[:-1] if (ctx is not None and eod is not None) else None,
    )
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
        eod_close=float(ctx.close.iloc[-2]) if ctx.partial and ctx.n > 1 else None,
        eod_date=ctx.date(ctx.n - 2) if ctx.partial and ctx.n > 1 else None,
    )
    rescore(s, ctx.cfg)
    if not keep_ctx:
        s.ctx = None
    return s


# ---------------------------------------------------------------- 300억 장대양봉 레이더
def radar_entry(ctx: StockContext, s: StockScan | None = None) -> dict | None:
    """최근 radar_days 거래일 안의 가장 최근 '거래대금 300억↑ & +7%↑' 양봉. 없으면 None.

    지지선(support) = 몸통 50% 선 (상한가권 +25%↑ 갭 상승은 min(시가, 전일 종가)와 종가의 중간).
    s 는 예전 호출 모양을 위해 받기만 한다 (2026-10-14 까지는 300억 눌림목 탐지기의 지지선으로 덮어썼다 — 그 탐지기 제거).
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


def _vocal_prepare(ud: UniverseData, cfg: Config, offline: bool, sector_map, verbose: bool, kis=None):
    """(테마 분류표, 보컬 단면 {code: 깔때기}, 못 셌을 때 이유) — 분류표가 없거나 실패하면 단면은 None."""
    sm = sector_map
    if sm is None:
        try:
            from .data.sector import load_sector_map
            sm = load_sector_map(offline=offline)
        except Exception as e:
            if verbose:
                print(f"  테마 분류표 생략: {type(e).__name__}: {e}", file=sys.stderr)
            return None, None, f"보컬 판정 안 함 — 테마 분류표를 읽지 못했다({type(e).__name__})"
    if sm is None or len(sm) == 0:
        return sm, None, "보컬 판정 안 함 — 테마 분류표가 없다(온라인으로 한 번 scan 하면 받는다)"
    try:
        from .vocal import VocalConfig, prepare
        vcfg = cfg.pattern_cfg("vocal", VocalConfig)
        # 스캔 대상(120봉↑)보다 짧은 신규 상장(60봉↑)도 순위 · 테마 · 대장에는 넣는다(원본 보컬과 같게)
        extra = {}
        try:
            from .data import OHLCVCache
            cache = OHLCVCache()
            for c in ud.universe.index:
                if c not in ud.ohlcv:
                    d = cache.load(c)
                    if d is not None and vcfg.min_bars <= len(d) < cfg.data.min_history_days:
                        extra[c] = d
        except Exception:
            extra = {}
        if extra and kis is not None and hasattr(kis, "turnover_for"):
            # 스캔 대상 일봉은 prepare 단계에서 KIS 실제 거래대금으로 바뀌었다 — 순위 단면이 섞이지 않게 신규 상장도 같게
            try:
                extra = kis.turnover_for(extra)
            except Exception:
                pass
        return sm, prepare(ud, sm, vcfg, offline=offline, extra_ohlcv=extra), None
    except Exception as e:
        if verbose:
            print(f"  보컬 단면 생략: {type(e).__name__}: {e}", file=sys.stderr)
        return sm, None, f"보컬 판정 안 함 — 단면 계산 실패({type(e).__name__}: {e})"


def excluded_entry(s: StockScan, why: str) -> dict:
    """증권사 상태로 후보에서 뺀 종목 → ScanResult.dropped 행 (리포트 '탈락' 표와 같은 모양, reason 있음)."""
    r = s.display_lead()
    return {"code": s.code, "name": s.name, "market": s.market, "pattern": r.name if r is not None else None,
            "stage": r.stage if r is not None else None, "composite": s.score.composite, "close": s.close,
            "reason": f"증권사 상태 제외: {why}"}


def run_scan(ud: UniverseData, cfg: Config | None = None, patterns: list[str] | None = None,
             include_all: bool = False, verbose: bool = True, *, offline: bool = True,
             sector_map: pd.DataFrame | None = None, kis=None, value=None) -> ScanResult:
    """전 종목 스캔. offline=False 면 업종·테마 지도가 없거나 오래됐을 때 새로 받는다(기본은 캐시만).

    kis(kis_scan.KISScan, 상태를 받은 것)가 있으면 종목마다 상태 태그(StockScan.kst)를 붙이고, 후보가 될 종목 중
    거래정지 · 정리매매 · 관리종목 · 투자위험은 후보에서 빼 ScanResult.excluded · dropped 에 사유와 함께 남긴다.

    value(value_list.ValueList, 기업추적 저평가 목록)가 있으면 종목마다 ctx.info["undervalued"] 에 목록 행(없으면 None)을
    넣고('저평가 종목' 정보 칩), 목록 종목은 후보가 아니어도 결과를 ScanResult.value_scans 에 남긴다(ctx 유지 — 리포트
    '저평가 종목' 탭의 패턴 · 미니차트 · 짧은 차트). 분석 대상 밖 목록 종목은 value_skipped 에 사유 · 종가만."""
    cfg = cfg or Config()
    t0 = time.perf_counter()
    out: list[StockScan] = []
    radar: list[dict] = []
    excluded: list[dict] = []
    errors: dict[str, str] = {}
    # 저평가 목록 종목은 유동성 문턱(20일 평균 거래대금 · 주가 · 시총) 밑이어도 패턴은 잰다 — 저평가 종목은 소형주가 많아
    # 문턱으로 자르면 등급 종목의 ⅓이 '패턴 미판정'이 된다(2026-10-08: 127곳 중 44곳). 후보 · 300억 레이더에는 넣지 않는다.
    vcodes = set(value.codes()) if value is not None and hasattr(value, "codes") else set()
    ctxs, thin = [], {}
    for ctx in iter_contexts(ud, cfg, apply_filter=False):
        ok, why = passes_universe_filter(ctx)
        if ok:
            ctxs.append(ctx)
        elif ctx.code in vcodes:
            thin[ctx.code] = " · ".join(why)
            ctxs.append(ctx)
    n_filtered = len(ctxs) - len(thin)
    vocal_res, vocal_skip = None, None
    if patterns is None or "vocal" in patterns:
        # 보컬은 거래대금 순위 · 테마 강도가 전 시장 단면이라 종목마다 따로 셀 수 없다 — 한 번 세어 넣는다
        sector_map, vocal_res, vocal_skip = _vocal_prepare(ud, cfg, offline, sector_map, verbose, kis)
    # 업종 · 테마 강도 · 업종 RS · 공시위험은 탐지 전에 — 체크리스트 2 · 5 · 9 번(패턴 모듈이 붙이는 것 포함)이 쓴다
    sm, strength, stock_groups = _group_strength(ud, offline, sector_map, verbose)
    si = technique_panel.scan_inputs(ud, sm, strength, stock_groups, cfg, verbose=verbose)
    value_scans: dict[str, StockScan] = {}
    for k, ctx in enumerate(ctxs, 1):
        vrow = value.get(ctx.code) if value is not None else None
        if value is not None:
            ctx.info["undervalued"] = vrow          # 'value' 키는 당일 거래대금 — 다른 키를 쓴다
        if vocal_res is not None:
            ctx.info["vocal"] = vocal_res.get(ctx.code)
        elif vocal_skip:
            ctx.info["vocal_skip"] = vocal_skip
        technique_panel.fill_info(ctx, si)
        try:
            s = scan_one(ctx, patterns)
        except Exception as e:  # 한 종목 오류로 전체 스캔이 멈추지 않게
            errors[ctx.code] = f"{type(e).__name__}: {e}"
            continue
        for name, r in s.results.items():
            for w in r.warnings:
                if w.startswith("탐지 오류"):
                    errors[f"{ctx.code}:{name}"] = w
        low = ctx.code in thin
        if low:
            s.thin = thin[ctx.code]
        try:
            rd = None if low else radar_entry(ctx, s)
        except Exception as e:
            rd = None
            errors[f"{ctx.code}:radar"] = f"{type(e).__name__}: {e}"
        if rd is not None:
            radar.append(rd)
        if kis is not None:
            s.kst = kis.tags(ctx.code)
        why = kis.exclude(ctx.code) if kis is not None else None
        keep = vrow is not None                     # 저평가 목록 종목은 후보가 아니어도 ctx 를 남긴다
        if not low and (include_all or scoring.is_candidate(s.results, s.rs)):
            if why and not include_all:
                excluded.append(excluded_entry(s, why))
                s.ctx = s.ctx if keep else None
            else:
                out.append(s)
        elif not keep:
            s.ctx = None
        if keep:
            value_scans[ctx.code] = s
        if verbose and (k % 50 == 0 or k == len(ctxs)):
            print(f"\r  패턴 분석 {k}/{len(ctxs)}", end="" if k < len(ctxs) else "\n", file=sys.stderr, flush=True)

    top_groups: list[dict] = []
    if strength is not None:
        ids = {id(s) for s in out}
        for s in out + [v for v in value_scans.values() if id(v) not in ids and v.ctx is not None]:
            g = s.ctx.info.get("groups") if s.ctx is not None else None
            if g is None:
                try:
                    g = stock_groups(s.code, sm, strength)
                except Exception:
                    g = None
            s.groups = g
            if s.ctx is not None:
                rescore(s, cfg)
        top_groups = strength.head(TOP_GROUPS).to_dict("records")
    for s in out:          # 기법 공통 칸 — 표시만 (체크리스트 '검증 전' · 청산 계획 · 저평가/공시위험 배지)
        attach_panel(s, cfg, errors)
    if sm is not None and len(sm) and radar:
        themes = {c: list(t) if isinstance(t, (list, tuple, np.ndarray)) else []
                  for c, t in zip(sm["code"], sm["themes"])}
        for rd in radar:
            rd["themes"] = themes.get(rd["code"], [])
    radar.sort(key=lambda d: (d["days_ago"], -d["value"]))
    out.sort(key=lambda s: -s.score.composite)
    excluded.sort(key=lambda d: -(d["composite"] or 0))
    return ScanResult(
        asof=ud.asof, generated_at=pd.Timestamp(now_kst().replace(tzinfo=None)),
        market=ud.market, stocks=out, scanned=n_filtered, elapsed=time.perf_counter() - t0,
        patterns=list(patterns or REGISTRY), errors=errors, radar=radar, groups=top_groups,
        breadth=getattr(ud, "breadth", None) or None, account=_account(cfg),
        dropped=list(excluded), excluded=excluded,
        value=value, value_scans=value_scans, value_skipped=_value_skipped(value, value_scans, ud, cfg, errors, kis),
        include_all=include_all, market_ctx=_market_ctx(ud, errors), tech_info=si.summary(),
    )


def _market_ctx(ud: UniverseData, errors: dict) -> dict | None:
    try:
        return technique_panel.market_panel(ud)
    except Exception as e:      # 시장 맥락 칸은 표시만 — 실패해도 스캔은 그대로
        errors["market_ctx"] = f"{type(e).__name__}: {e}"
        return None


def attach_panel(s: StockScan, cfg: Config | None = None, errors: dict | None = None) -> None:
    """후보 하나에 기법 공통 칸(체크리스트 10 · 청산 계획)과 배지를 붙인다 — 표시만, 점수에 안 넣는다."""
    try:
        s.badges = technique_panel.badges(s.ctx) if s.ctx is not None else None
        s.panel = technique_panel.stock_panel(s, cfg)
    except Exception as e:
        s.panel = None
        if errors is not None:
            errors[f"{s.code}:panel"] = f"{type(e).__name__}: {e}"


FLOW_PATTERNS = ("ma60_supply",)    # 수급(기관 · 외국인) 자료로 라벨이 바뀌는 패턴 — 수급을 붙인 뒤 다시 잰다


def refresh_flow_patterns(scan: ScanResult, cfg: Config | None = None) -> int:
    """수급 자료(증권사 kis_flows · 네이버 investor)를 붙인 뒤 FLOW_PATTERNS 를 다시 판정한다 — 탐지 때는 자료가 없어
    '수급 미확인'이던 라벨을 채운다(점수 · 후보 여부는 바뀌지 않는다: 60일선 수급 돌파는 신호 패턴이라 종합 점수 밖이고
    돌파 탐지 자체는 수급과 무관). 반환: 다시 잰 종목 수."""
    n = 0
    for s in scan.stocks:
        ctx = s.ctx
        if ctx is None or not (ctx.info.get("kis_flows") is not None or ctx.info.get("investor") is not None):
            continue
        hit = False
        for name in FLOW_PATTERNS:
            r = s.results.get(name)
            if name not in REGISTRY or r is None or not r.detected:
                continue
            label, fn = REGISTRY[name]
            try:
                s.results[name] = fn(ctx)
            except Exception as e:
                s.results[name] = PatternResult(name=name, label=label, warnings=[f"탐지 오류: {type(e).__name__}: {e}"])
            hit = True
        if hit:
            rescore(s, cfg or ctx.cfg)
            attach_panel(s, cfg or ctx.cfg, scan.errors)
            n += 1
    return n


def _value_skipped(value, scans: dict, ud: UniverseData, cfg: Config, errors: dict, kis) -> dict:
    """분석하지 못한 저평가 목록 종목 → {code: value_list.skipped_entry} (유동성 필터 · 기간 부족 · 분석 오류)."""
    if value is None:
        return {}
    from .value_list import skipped_entry
    out = {}
    for code in value.codes():
        if code not in scans:
            why = f"분석 오류: {errors[code]}" if code in errors else None
            out[code] = skipped_entry(code, ud, cfg, why, kis)
    return out


def enrich_investor(scan: ScanResult, top: int = 60, offline: bool = False, verbose: bool = True,
                    only_missing: bool = False) -> int:
    """상위 후보에만 기관·외국인 순매매(네이버)를 붙인다 — 리포트 '수급 20일' 표시용(점수에는 안 쓴다). 반환: 붙인 종목 수.
    only_missing=True 면 이미 수급이 붙은 종목(증권사 자료)은 건너뛴다 — KIS 실패 종목의 대체용."""
    from .data.investor import attach_investor

    done = 0
    targets = [s for s in scan.stocks[:top] if s.ctx is not None
               and not (only_missing and s.ctx.info.get("investor") is not None)]
    for k, s in enumerate(targets, 1):
        try:
            got = attach_investor(s.ctx, offline=offline)
        except Exception:
            got = None
        if got is not None:
            done += 1
        if verbose and (k % 10 == 0 or k == len(targets)):
            print(f"\r  수급(기관·외국인) {k}/{len(targets)}", end="" if k < len(targets) else "\n",
                  file=sys.stderr, flush=True)
    return done


def _kis_flow_summary(fl, inv, days: int) -> dict | None:
    """증권사(KIS) 수급 → 최근 n일 기관·외국인 순매수 금액(원, 체결 금액 합 — 주식수 × 종가 근사가 아님)."""
    n = min(days, len(fl.dates))
    if n == 0:
        return None
    s = lambda xs: float(sum(x for x in xs[-n:] if x is not None)) * 1e8  # noqa: E731  (억원 → 원)
    fr = None
    if inv is not None and "foreign_ratio" in inv and len(inv):
        v = inv["foreign_ratio"].iloc[-1]
        fr = float(v) if v == v else None
    d = str(fl.dates[-1])
    return {"days": n, "asof": f"{d[:4]}-{d[4:6]}-{d[6:]}", "inst": s(fl.orgn), "foreign": s(fl.frgn),
            "foreign_ratio": fr, "src": "KIS"}


def investor_summary(s: StockScan, days: int = 20) -> dict | None:
    """최근 n일 기관·외국인 순매수 금액(원). 증권사 수급(ctx.info['kis_flows'])이 있으면 그 체결 금액 합,
    없으면 순매매 주식수 × 종가 근사(네이버)."""
    info = s.ctx.info if s.ctx is not None else {}
    inv = info.get("investor")
    fl = info.get("kis_flows")
    if fl is not None and getattr(fl, "dates", None):
        return _kis_flow_summary(fl, inv, days)
    if inv is None or len(inv) == 0:
        return None
    t = inv.iloc[-days:]
    px = t["close"].where(t["close"] > 0, s.close)
    return {
        "days": int(len(t)), "asof": f"{t.index[-1]:%Y-%m-%d}",
        "inst": float((t["inst_net"] * px).sum()), "foreign": float((t["foreign_net"] * px).sum()),
        "foreign_ratio": float(t["foreign_ratio"].iloc[-1]) if "foreign_ratio" in t else None,
        "src": "네이버",
    }


# ---------------------------------------------------------------- 표 변환
FRAME_COLUMNS = [
    "종목코드", "종목명", "시장", "종가", "등락률", "종합점수", "배지", "RS", "대표패턴", "단계", "피벗", "피벗대비",
    "손절가", "손절폭%", "진입계획", "권장수량", "투입금액(만원)", "최대손실(만원)", "업종", "테마", "탐지패턴",
    "20일평균거래대금(억)", "당일거래대금(억)", "시가총액(억)", "기관20일순매수(억)", "외국인20일순매수(억)",
    "관찰패턴", "종목상태", "목표가괴리%", "목표가상향30일", "EPS(E)성장%",
    "체크리스트(검증 전)", "저평가등급", "공시위험",
]
OBSERVE_PLAN = {
    "vocal": "보컬 관찰용 — 매수 계획 없음 (과거 검증 손실)",
    "day_leader": "10% 주도주 관찰용 — 다음 날 HTS 3분봉에서 사람이 판단 · 매수 계획 없음 (과거 검증 없음)",
}


def plan_text(s: StockScan, best: PatternResult | None = None) -> str:
    """표 · 리포트의 '진입계획' 문구 — 매수 계획(수량)이 없는 경우 그 이유를 패턴마다."""
    best = best if best is not None else s.display_lead()
    if best is None:
        return (s.position or {}).get("plan", "")
    if best.name in scoring.OBSERVE_PATTERNS:
        return OBSERVE_PLAN.get(best.name, f"{best.label} 관찰용 — 매수 계획 없음")
    if best.name == "cup_with_handle" and best.pivot and not best.stop:
        return NO_STOP_PLAN
    if best is not s.lead() or not best.stop:
        return f"{best.label} — {scoring.no_stop_reason(best)} 매수 계획(수량) 없음"
    return (s.position or {}).get("plan", "")


def _check_text(s: StockScan) -> str:
    p = s.panel or {}
    c = p.get("counts")
    if not c:
        return ""
    return f"통과 {c.get('pass', 0)} · 경고 {c.get('warn', 0)} · 모름 {c.get('unknown', 0)}"


def stage_short(r: PatternResult | None) -> str:
    """단계 줄임말 — 기법이 metrics['stage_short'] 를 주면 그것(피벗 없는 결과: '관찰일' · '접촉' · '접근')."""
    if r is None:
        return "-"
    return str((r.metrics or {}).get("stage_short") or STAGE_SHORT.get(r.stage or "", "-"))


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
        best = s.display_lead()
        _, risk = s.entry_risk()
        pos = s.position or {}
        g = s.groups or {}
        themes = [t[0] if isinstance(t, (list, tuple)) else str(t) for t in (g.get("themes") or [])][:3]
        label = best.label if best else ""
        observe = best is not None and best.name in scoring.OBSERVE_PATTERNS   # 관찰 칩만 걸린 종목(매수 계획 없음)
        bclose, eod = s.basis(best) if hasattr(s, "basis") else (s.close, False)
        row = {
            "종목코드": s.code, "종목명": s.name, "시장": s.market, "종가": s.close,
            "등락률": round(s.change_pct * 100, 2), "종합점수": s.score.composite, "배지": s.badge or "",
            "RS": s.rs, "대표패턴": label,
            "단계": ("관찰 · " if observe else "") + (best.stage_label if best else "")
                    + (f" ({s.eod_date or '어제'} 종가 기준 · 장중 미완성 봉 안 씀)" if eod else ""),
            "피벗": best.pivot if best else None,
            "피벗대비": round((bclose / best.pivot - 1) * 100, 2) if best and best.pivot else None,
            "손절가": best.stop if best else None,
            "손절폭%": round(risk * 100, 2) if risk is not None else None,
            "진입계획": plan_text(s, best),
            "권장수량": pos.get("shares") if pos else None,
            "투입금액(만원)": _round(pos.get("amount"), 1e4) if pos else None,
            "최대손실(만원)": _round(pos.get("max_loss"), 1e4) if pos else None,
            "업종": g.get("sector") or "", "테마": ", ".join(themes),
            # 이름(단계) — 신호 전 꼬리표(적삼병 형성 · 피보 접촉 등)와 신호를 가른다 (리포트 tagLbl 과 같은 줄임말)
            "탐지패턴": ", ".join(f"{REGISTRY[n][0]}({stage_short(s.results[n])})"
                              for n in list(s.score.detected_bases) + list(scoring.SIGNAL_PATTERNS)
                              if n in REGISTRY and n in s.results and s.results[n].detected),
            "20일평균거래대금(억)": _round(s.avg_value_20, 1e8, 1),
            "당일거래대금(억)": _round(s.value_today, 1e8, 1),
            "시가총액(억)": _round(s.market_cap, 1e8),
        }
        inv = investor_summary(s)
        row["기관20일순매수(억)"] = round(inv["inst"] / 1e8, 1) if inv else None
        row["외국인20일순매수(억)"] = round(inv["foreign"] / 1e8, 1) if inv else None
        k = s.kis or {}
        row["관찰패턴"] = ", ".join(REGISTRY[n][0] for n in scoring.OBSERVE_PATTERNS + scoring.INFO_PATTERNS
                                 if n in s.results and s.results[n].detected and n in REGISTRY)
        row["종목상태"] = ", ".join(s.kst or [])
        row["목표가괴리%"] = k.get("tp_gap")
        row["목표가상향30일"] = k.get("tp_up30")
        row["EPS(E)성장%"] = k.get("fwd_eps_g")
        bg = s.badges or {}
        row["체크리스트(검증 전)"] = _check_text(s)
        row["저평가등급"] = bg.get("tier") or ""
        row["공시위험"] = ", ".join(t for t, _ in bg.get("risk") or [])
        for name, r in s.results.items():
            row[f"{name}_점수"] = round(r.score, 1) if r.detected else None
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=FRAME_COLUMNS)
    df = pd.DataFrame(rows)
    df["권장수량"] = df["권장수량"].astype("Int64")
    return df
