"""패턴 결과들을 종합 점수로 합산.

종합 점수 (0~100)
    = W × (0.55 × 베이스 패턴 점수 + 0.25 × 기술적 체력 + 0.20 × RS 레이팅) + 보너스

    베이스 패턴 점수 : 대표 베이스 패턴의 품질 점수(0~100). 대표 = 위 괄호식 × W 가 가장 큰 베이스.
    기술적 체력     : 트렌드 템플릿·CAN SLIM 점수 평균.
    W (단계 가중치) : 대표 패턴의 단계로 '지금 행동 가능한가'를 반영한다. 패턴 부분만이 아니라 합계 전체에
                      곱하므로 이격 과다·돌파 실패 종목이 추세·RS 만으로 매수 가능 종목을 앞지르지 못한다.
        돌파 1.0 · 피벗 근접 0.95 · 형성 중 0.7 · 이격 과다 0.45 · 돌파 실패 0.15 (단계 없음 0.6)
        상황별 덮어쓰기 (아래로 갈수록 우선)
          - 돌파 후 피벗 아래로 되밀린 재시험 (breakout_date 있음 & 종가 < 피벗)          0.6
          - 돌파 후 5봉 이상 지났는데 아직 매수 범위(피벗~+5%) 안 (묵은 돌파)              0.7
          - 장기횡보 돌파가 상한가권 장대양봉(metrics.limit_up)으로 돌파 단계              0.6  (백테스트 60일 -5.2%)
          - 300억 장대양봉 후 눌림목의 피벗 근접(50%선 눌림, 재돌파 전)                    1.0  (20일 +3.46% vs 추격 +0.07%)
          - CAN SLIM 대표(베이스 없음)의 이격 과다                                         0.35 (돌파일 이격 60일 -0.3%)
    CAN SLIM 만 충족(베이스 없음): 베이스 패턴 점수 0, W = CAN SLIM 단계 가중치.
    주도주(베이스 없음): 베이스 패턴·CAN SLIM 없이 트렌드 템플릿 8/8 · RS ≥ 90 · 52주 고점 -15% 이내
        → 후보에 포함('주도주(베이스 없음)'), W = 0.6 · 베이스 패턴 점수 0.

보너스·감점 (W 밖에서 더함)
    + 복수 패턴 중첩: 같은 구조를 먼저 하나로 묶은 뒤 (서로 다른 구조 수 − 1) × 4, 최대 +8.
        같은 구조 = 피벗 2% 이내이면서 [시작일 15봉 이내 또는 한쪽 시작일이 다른 쪽 구간 안],
                   또는 시작일·종료일이 모두 15봉 이내 (같은 구간을 다른 패턴으로 해석한 경우)
    + 최근 포켓 피벗 +5, 최근 5일 내 거래대금 300억↑ +5
    ± 업종·테마 강도 (StockScan.groups): 소속 그룹 최고 순위 상위 10% +5, 하위 20% -3
        (sector.py 검증: 최고 순위 상위 10% 20일 +1.87%, 0.8~0.9 +0.09% ≈ 전체 +0.06%, 하위 20% -3.36%.
         best_rank_pct 는 업종·소속 테마 중 최고값이라 0.8 기준이면 후보 대부분이 가산됨)
    − 진입 손절폭 (planned_entry 기준 1 − 손절가/진입가) 10% 초과 → W 상한 0.7('눌림 대기'), 15% 초과 추가 -10
    × 추세·RS 약함 (RS < 70 또는 트렌드 템플릿 6/8 미만): 베이스 패턴 W × 0.6 (장기횡보 돌파 제외)
    × CAN SLIM 대표: 베이스 결함 품질 배수(V자·50%↑ 깊이·돌파 실패)를 W 에 곱함
    · 주도주가 50일선 대비 +50% 초과(클라이맥스형 급등)면 W 0.4
        진입가 = max(피벗, 현재가). 300억 장대양봉 눌림목은 재돌파 전이면 min(현재가, 50%선 지정가)
        — scanner.position_plan 의 진입 계획과 같은 값.
    − 시장 조정 국면 -10
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from .patterns.flat_base import krx_tick

BASE_PATTERNS = (
    "long_base_breakout", "vcp", "cup_handle", "flat_base", "double_bottom",
    "high_tight_flag", "three_weeks_tight", "big_value_pullback",
)
SIGNAL_PATTERNS = ("pocket_pivot",)
CONTEXT_PATTERNS = ("trend_template", "canslim")

STAGE_WEIGHT = {BREAKOUT: 1.0, NEAR_PIVOT: 0.95, FORMING: 0.7, EXTENDED: 0.45, FAILED: 0.15, None: 0.6}
ACTIONABLE = (BREAKOUT, NEAR_PIVOT)
LEADER_TAG = "주도주(베이스 없음)"


@dataclass
class ScoringConfig:
    # ---- 합계 가중치
    w_pattern: float = 0.55
    w_tech: float = 0.25
    w_rs: float = 0.20
    # ---- 단계 가중치 W (합계 전체에 곱함)
    stage_weight: dict = field(default_factory=lambda: dict(STAGE_WEIGHT))
    retest_weight: float = 0.6            # 돌파 후 피벗 아래 재시험
    stale_weight: float = 0.7             # 묵은 돌파 (돌파 후 stale_bars 봉 이상, 매수 범위 안)
    stale_bars: int = 5
    buy_range: float = 0.05               # 매수 범위 = 피벗 ~ 피벗 × (1 + 5%)
    limit_up_long_base_weight: float = 0.6  # 상한가권 장기횡보 돌파
    pullback_weight: float = 1.0          # 300억 장대양봉 50%선 눌림 (피벗 근접)
    canslim_extended_weight: float = 0.35
    leader_weight: float = 0.6            # 주도주(베이스 없음)
    # ---- 주도주 판정
    leader_rs: float = 90.0               # RS 레이팅 이상
    leader_from_high: float = 0.15        # 52주 고점 대비 이 이내
    # ---- 같은 구조 판정 (중복 패턴 묶기)
    same_pivot_pct: float = 0.02          # 피벗 차이 2% 이내
    same_bars: int = 15                   # 시작일(종료일) 차이 15봉 이내
    # ---- 보너스·감점
    multi_bonus_each: float = 4.0
    multi_bonus_max: float = 8.0
    pocket_pivot_bonus: float = 5.0
    big_value_bonus: float = 5.0
    sector_top_pct: float = 0.9           # 그룹 순위 백분위(1=최강) 이상이면 가산 (0.8~0.9 구간은 초과수익 없음)
    sector_top_bonus: float = 5.0
    sector_bottom_pct: float = 0.2        # 이하이면 감점
    sector_bottom_penalty: float = -3.0
    risk_warn: float = 0.10               # 진입 손절폭 > 10% → W 상한 unactionable_weight (지금 매수 불가 = 눌림 대기)
    risk_warn_penalty: float = 0.0
    unactionable_weight: float = 0.7
    # ---- 추세·리더십 게이트 (2차 검증: RS 56·TT 2/8 종목의 '형성 중' 베이스가 주도주를 앞지름)
    weak_trend_rs: float = 70.0           # RS 이 미만이거나
    weak_trend_tt: int = 6                # 트렌드 템플릿 통과 이 미만이면
    weak_trend_mult: float = 0.6          # W × 0.6 (장기횡보 돌파는 바닥권 정의상 제외)
    # ---- 주도주 과열 (50일선 대비 +50% 초과 = 클라이맥스형 급등)
    leader_overheat: float = 0.50
    leader_overheat_weight: float = 0.4
    risk_max: float = 0.15                # > 15% → -10
    risk_max_penalty: float = -10.0
    correction_penalty: float = -10.0     # 시장 조정 국면


DEFAULT = ScoringConfig()


@dataclass
class ScoreBreakdown:
    composite: float
    pattern_part: float                    # 대표 베이스 패턴 점수 (W 적용 전)
    tech_part: float
    rs_part: float
    bonus: float
    best_pattern: str | None
    best_stage: str | None
    detected_bases: list[str]
    notes: list[str]
    stage_weight: float = 1.0              # 합계에 곱한 W
    leader: bool = False                   # 주도주(베이스 없음)
    structures: int = 0                    # 중복을 묶은 서로 다른 베이스 구조 수
    entry_risk: float | None = None        # 대표 결과의 진입 손절폭


def _score(r: PatternResult | None) -> float:
    return float(r.score) if r is not None and r.score == r.score else 0.0


# ---------------------------------------------------------------- 날짜·봉 계산
def _bars_between(a, b, dates: pd.DatetimeIndex | None = None) -> int:
    ta, tb = pd.Timestamp(a), pd.Timestamp(b)
    if dates is not None and len(dates):
        return abs(int(dates.searchsorted(tb)) - int(dates.searchsorted(ta)))
    return abs(int(np.busday_count(ta.date(), tb.date())))


def _bars_since(d, dates: pd.DatetimeIndex) -> int:
    return len(dates) - 1 - int(dates.searchsorted(pd.Timestamp(d)))


def _span(r: PatternResult) -> tuple[pd.Timestamp, pd.Timestamp]:
    s = pd.Timestamp(r.start_date)
    e = pd.Timestamp(r.end_date) if r.end_date else s
    return s, max(s, e)


def same_structure(a: PatternResult, b: PatternResult, dates: pd.DatetimeIndex | None = None,
                   cfg: ScoringConfig = DEFAULT) -> bool:
    """두 베이스 결과가 같은 가격 구조를 다르게 해석한 것인지 (중첩 보너스 중복 방지)."""
    if not (a.start_date and b.start_date):
        return False  # 구간을 모르면 다른 구조로 본다
    (sa, ea), (sb, eb) = _span(a), _span(b)
    pa, pb = a.pivot, b.pivot
    same_pivot = bool(pa and pb and abs(pa - pb) / max(pa, pb) <= cfg.same_pivot_pct)
    d_start = _bars_between(sa, sb, dates)
    if same_pivot and (d_start <= cfg.same_bars or sb <= sa <= eb or sa <= sb <= ea):
        return True
    return d_start <= cfg.same_bars and _bars_between(ea, eb, dates) <= cfg.same_bars


def count_structures(bases: list[tuple[str, PatternResult]], dates: pd.DatetimeIndex | None = None,
                     cfg: ScoringConfig = DEFAULT) -> list[list[str]]:
    """같은 구조끼리 묶은 그룹 목록 (union-find)."""
    parent = list(range(len(bases)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(bases)):
        for j in range(i + 1, len(bases)):
            if same_structure(bases[i][1], bases[j][1], dates, cfg):
                parent[find(j)] = find(i)
    groups: dict[int, list[str]] = {}
    for i, (n, _) in enumerate(bases):
        groups.setdefault(find(i), []).append(n)
    return list(groups.values())


# ---------------------------------------------------------------- 단계 가중치
def stage_weight(name: str, r: PatternResult, close: float | None = None,
                 dates: pd.DatetimeIndex | None = None, cfg: ScoringConfig = DEFAULT) -> tuple[float, str | None]:
    """(W, 덮어쓴 이유). close·dates 가 없으면 재시험·묵은 돌파 규칙은 건너뛴다."""
    w = cfg.stage_weight.get(r.stage, cfg.stage_weight.get(None, 0.6))
    why = None
    if r.breakout_date and r.pivot and close is not None and r.stage != FAILED:
        if close < r.pivot:
            w, why = cfg.retest_weight, "돌파 후 피벗 아래 재시험"
        elif close <= r.pivot * (1 + cfg.buy_range) and dates is not None and len(dates):
            bars = _bars_since(r.breakout_date, dates)
            if bars >= cfg.stale_bars:
                w, why = cfg.stale_weight, f"돌파 {bars}봉 경과(묵은 돌파)"
    m = r.metrics or {}
    if name == "long_base_breakout" and r.stage == BREAKOUT and (
            bool(m.get("limit_up")) or m.get("candle_class") == "limit_up"):
        w, why = cfg.limit_up_long_base_weight, "상한가권 장대양봉 돌파"
    if name == "big_value_pullback" and r.stage == NEAR_PIVOT and not r.breakout_date:  # 재돌파 뒤 횡보는 제외
        w, why = cfg.pullback_weight, "300억 장대양봉 50%선 눌림"
    if name == "canslim" and r.stage == EXTENDED:
        w, why = cfg.canslim_extended_weight, "CAN SLIM 이격 과다"
    return float(w), why


def pullback_limit(r: PatternResult | None) -> float | None:
    """300억 장대양봉 눌림목이 재돌파 전(형성 중·피벗 근접·눌림 없는 이격 과다)이면 50%선 지정가, 아니면 None.
    metrics.support(몸통 50%선)를 가장 가까운 KRX 호가 단위로 맞춘 값 (= 탐지기의 재돌파 전 피벗).
    support 가 없으면 피벗."""
    if r is None or r.name != "big_value_pullback" or r.breakout_date or r.stage not in (NEAR_PIVOT, FORMING, EXTENDED):
        return None
    for x in ((r.metrics or {}).get("support"), r.pivot):
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if np.isfinite(v) and v > 0:
            t = krx_tick(v)
            return float(math.floor(v / t + 0.5) * t)
    return None


def pullback_zone_top(r: PatternResult | None) -> float | None:
    """눌림 매수 구간 상단 = metrics.buy_zone_top (50%선 +3%, 백테스트 체결 기준). 없으면 50%선 × 1.03."""
    lim = pullback_limit(r)
    if lim is None:
        return None
    try:
        z = float((r.metrics or {}).get("buy_zone_top"))
    except (TypeError, ValueError):
        z = float("nan")
    if not (np.isfinite(z) and z >= lim):
        z = lim * 1.03
        t = krx_tick(z)
        z = float(math.floor(z / t) * t)
    return z


def planned_entry(r: PatternResult | None, close: float | None) -> float | None:
    """계획 진입가: 눌림목이면 min(현재가, 매수 구간 상단), 아니면 max(피벗, 현재가).
    백테스트(눌림 신호 다음날 시가 진입, 체결 ≈ min(시가, 50%선×1.03))와 같은 기준."""
    if r is None or close is None:
        return None
    zt = pullback_zone_top(r)
    if zt is not None:
        return min(float(close), zt)
    return max(float(r.pivot), float(close)) if r.pivot else None


def entry_risk(r: PatternResult | None, close: float | None) -> float | None:
    """계획 진입가(planned_entry) 대비 손절가까지의 거리 (음수 = 이미 손절가 아래)."""
    if r is None or not r.pivot or not r.stop or close is None:
        return None
    entry = planned_entry(r, close)
    return 1 - float(r.stop) / entry if entry else None


# ---------------------------------------------------------------- 주도주·후보
def is_leader(results: dict[str, PatternResult], rs: float | None = None, cfg: ScoringConfig = DEFAULT) -> bool:
    """베이스 없는 Stage 2 주도주: 트렌드 템플릿 8/8 · RS ≥ 90 · 52주 고점 -15% 이내."""
    if any(results.get(n) is not None and results[n].detected for n in (*BASE_PATTERNS, "canslim")):
        return False
    tt = results.get("trend_template")
    if tt is None or not tt.detected or (tt.metrics or {}).get("passed", 8) < 8:
        return False
    m = tt.metrics or {}
    rs_v = rs if rs is not None else m.get("rs")
    fh = m.get("from_52w_high")
    if rs_v is None or fh is None or fh != fh:
        return False
    return float(rs_v) >= cfg.leader_rs and float(fh) >= -cfg.leader_from_high


def is_candidate(results: dict[str, PatternResult], rs: float | None = None) -> bool:
    """리포트에 올릴 후보: 베이스 패턴 하나 이상, CAN SLIM 충족, 보컬 깔때기, 또는 주도주(베이스 없음)."""
    if any(results.get(n) is not None and results[n].detected for n in BASE_PATTERNS):
        return True
    cs = results.get("canslim")
    if cs is not None and cs.detected:
        return True
    vc = results.get("vocal")          # 보컬 깔때기(관찰용 칩) — 종합 점수에는 넣지 않는다
    if vc is not None and vc.detected:
        return True
    return is_leader(results, rs)


# ---------------------------------------------------------------- 종합 점수
def compute(results: dict[str, PatternResult], rs: float | None, market_state=None,
            recent_big_value: bool = False, *, close: float | None = None,
            dates: pd.DatetimeIndex | None = None, groups: dict | None = None,
            cfg: ScoringConfig | None = None) -> ScoreBreakdown:
    """종합 점수. close(현재가)·dates(일봉 인덱스)·groups(업종·테마 순위)는 있으면 해당 규칙에 쓴다."""
    cfg = cfg or DEFAULT
    bases = [(n, results[n]) for n in BASE_PATTERNS if n in results and results[n].detected]
    tech = [_score(results.get(n)) for n in CONTEXT_PATTERNS if n in results]
    tech_part = sum(tech) / len(tech) if tech else 0.0
    rs_part = float(rs or 0)
    common = cfg.w_tech * tech_part + cfg.w_rs * rs_part

    notes: list[str] = []
    best_name, best_stage, best_r = None, None, None
    pattern_part, w, w_why, best_val = 0.0, cfg.stage_weight.get(None, 0.6), None, -1.0
    tt = results.get("trend_template")
    tt_m = (tt.metrics or {}) if tt is not None else {}
    tt_pass = tt_m.get("passed")
    weak_trend = (rs is not None and rs < cfg.weak_trend_rs) or (tt_pass is not None and tt_pass < cfg.weak_trend_tt)
    for name, r in bases:
        wr, why = stage_weight(name, r, close, dates, cfg)
        if weak_trend and name != "long_base_breakout":
            wr *= cfg.weak_trend_mult
            why = ((why + " · ") if why else "") + f"추세·RS 약함(RS {rs or 0:.0f}, TT {tt_pass}/8)"
        rk = entry_risk(r, close)
        if rk is not None and rk > cfg.risk_warn and r.stage in ACTIONABLE and wr > cfg.unactionable_weight:
            wr = cfg.unactionable_weight
            why = ((why + " · ") if why else "") + f"손절폭 {rk:.1%} — 눌림 대기"
        val = wr * (cfg.w_pattern * _score(r) + common)
        if val > best_val:
            best_name, best_stage, best_r, pattern_part, w, w_why, best_val = name, r.stage, r, _score(r), wr, why, val

    leader = is_leader(results, rs, cfg)
    lead_r = best_r
    if best_r is None:
        cs = results.get("canslim")
        if cs is not None and cs.detected:
            lead_r = cs
            w, w_why = stage_weight("canslim", cs, close, dates, cfg)
            q = (cs.metrics or {}).get("quality_mult")
            if q is not None and q == q and q < 1:  # V자·과도한 깊이·실패 베이스 결함 반영
                w *= float(q)
                w_why = ((w_why + " · ") if w_why else "") + f"베이스 결함 ×{float(q):.2f}"
        elif leader:
            w, w_why = cfg.leader_weight, None
            c50, s50 = tt_m.get("close"), tt_m.get("sma50")
            if c50 and s50 and s50 == s50 and c50 / s50 - 1 > cfg.leader_overheat:
                w = cfg.leader_overheat_weight
                w_why = f"과열: 50일선 대비 +{c50 / s50 - 1:.0%}"
    if leader:
        notes.append(LEADER_TAG)
    notes.append(f"단계 가중치 ×{w:.2f}" + (f" ({w_why})" if w_why else ""))

    bonus = 0.0
    structures = count_structures(bases, dates, cfg) if bases else []
    merged = [g for g in structures if len(g) > 1]
    if merged:
        notes.append("같은 구조 중복 제외: " + ", ".join("=".join(g) for g in merged))
    if len(structures) > 1:
        b = min(cfg.multi_bonus_max, cfg.multi_bonus_each * (len(structures) - 1))
        bonus += b
        notes.append(f"복수 패턴 중첩 +{b:.0f}")
    pp = results.get("pocket_pivot")
    if pp is not None and pp.detected and pp.stage in ACTIONABLE:
        bonus += cfg.pocket_pivot_bonus
        notes.append(f"최근 포켓 피벗 +{cfg.pocket_pivot_bonus:.0f}")
    if recent_big_value:
        bonus += cfg.big_value_bonus
        notes.append(f"최근 5일 내 거래대금 300억+ +{cfg.big_value_bonus:.0f}")
    best_rank = (groups or {}).get("best_rank_pct")
    if best_rank is not None and best_rank == best_rank:
        if best_rank >= cfg.sector_top_pct:
            bonus += cfg.sector_top_bonus
            notes.append(f"주도 업종·테마(상위 {max(0.01, 1 - best_rank):.0%}) +{cfg.sector_top_bonus:.0f}")
        elif best_rank <= cfg.sector_bottom_pct:
            bonus += cfg.sector_bottom_penalty
            notes.append(f"약세 업종·테마 {cfg.sector_bottom_penalty:+.0f}")
    risk = entry_risk(lead_r, close)
    if risk is not None:
        if risk > cfg.risk_max:
            bonus += cfg.risk_max_penalty
            notes.append(f"손절폭 {risk:.1%} > {cfg.risk_max:.0%} {cfg.risk_max_penalty:+.0f}")
        elif risk > cfg.risk_warn and cfg.risk_warn_penalty:
            bonus += cfg.risk_warn_penalty
            notes.append(f"손절폭 {risk:.1%} > {cfg.risk_warn:.0%} {cfg.risk_warn_penalty:+.0f}")
    if market_state is not None and getattr(market_state, "state", None) == "correction":
        bonus += cfg.correction_penalty
        notes.append(f"시장 조정 국면 {cfg.correction_penalty:+.0f}")

    composite = w * (cfg.w_pattern * pattern_part + common) + bonus
    return ScoreBreakdown(
        composite=round(max(0.0, min(100.0, composite)), 1), pattern_part=round(pattern_part, 1),
        tech_part=round(tech_part, 1), rs_part=rs_part, bonus=bonus, best_pattern=best_name,
        best_stage=best_stage, detected_bases=[n for n, _ in bases], notes=notes,
        stage_weight=round(w, 2), leader=leader, structures=len(structures),
        entry_risk=round(risk, 4) if risk is not None else None,
    )
