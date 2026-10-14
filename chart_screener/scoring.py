"""패턴 결과들을 종합 점수로 합산.

2026-10-14 패턴 초기화: 옛 탐지기(VCP · 옛 컵앤핸들 · CAN SLIM · 트렌드 템플릿 · 300억 눌림목 · 장기횡보 등 13개)를 지우고
사용자 식 컵 앤 핸들(cup_with_handle)만 남겼다. 옛 점수의 '기술적 체력'(트렌드 템플릿 · CAN SLIM 평균) 항,
추세·RS 약함 감점, 주도주(베이스 없음), 패턴별 단계 가중치 덮어쓰기(장기횡보 · 눌림목 · CAN SLIM)는 그 탐지기들이 근거라 함께 뺐다.
같은 날 《차트의 기술》 영상 기법 6개를 더했다(docs/2026-10-14-chart-techniques-*.md) — 아래 패턴 묶음.

패턴 묶음 (구현 선택 — 왜 그 묶음인지)
    BASE_PATTERNS   가격 구조 + 피벗(매수 기준가) — 종합 점수 · 매수 계획(손절가가 있으면) · 후보.
                    컵 앤 핸들(사용자 식) · 빗각 추세선 돌파 · 피보나치 눌림 반등 · 빗각 돌파 + 피보 눌림.
                    피벗이 없는 결과(피보 계열의 신호 전 단계 — 접촉 · 접근 · 대기: 진입가는 반등 양봉 종가로 나중에 정해진다)는
                    W 를 매길 기준가가 없어 대표 · 점수 · 중첩 보너스에 쓰지 않고 혼자 후보도 만들지 않는다(다른 후보의 꼬리표로만 보임).
    SIGNAL_PATTERNS 손절 규칙 없는 사건 신호 — 후보 · 칩 · 일지는 되지만 종합 점수 · 매수 계획 · 실시간 감시에는 안 쓴다.
                    60일선 수급 돌파(피벗 = 날마다 움직이는 60일선) · 월봉 적삼병(월 단위, 확정 저점은 구조 무효선일 뿐 손절 아님).
                    혼자 후보가 되는 단계는 SIGNAL_CANDIDATE_STAGES (적삼병 '형성 중 · 피벗 근접'은 아직 신호가 아니라 꼬리표로만).
    OBSERVE_PATTERNS 관찰 전용 — 10% 주도주(분봉 진입이라 일봉 진입 판정 없음) · 보컬(과거 검증 손실). 혼자서도 후보(관찰 칩).
    INFO_PATTERNS   외부 목록 정보 칩 — 저평가 종목.
    LIVE_PATTERNS   실시간 감시(live)에 쓰는 베이스 — 컵 앤 핸들만. 새 기법은 검증 전이고 피벗 뜻이 달라(피보 신호 뒤 피벗 = 진입가,
                    빗각 돌파 확인은 종가) 장중 '돌파' 알림이 기법 규칙과 맞지 않는다.

종합 점수 (0~100)
    = W × (0.55 × 베이스 패턴 점수 + 0.20 × RS 레이팅) ÷ 0.75 + 보너스
      (옛 가중치 패턴 0.55 · RS 0.20 에서 빠진 기술적 체력 0.25 를 덜어내고 합이 1 이 되게 다시 나눔 — 약 0.73 · 0.27.
       검증된 가중치가 아니다. 새 식이 더 들어오면 다시 정한다.)

    베이스 패턴 점수 : 대표 베이스 패턴의 품질 점수(0~100). 대표 = 위 괄호식 × W 가 가장 큰 베이스(피벗이 있는 결과만).
                       컵 앤 핸들은 식의 quality_score, 새 기법은 모듈마다 정한 점수 — 모두 성공 확률 아님(관측된 항목만으로 계산).
                       체크리스트 10(검증 전)은 표시만 하고 점수에 넣지 않는다.
    W (단계 가중치) : 대표 패턴의 단계로 '지금 행동 가능한가'를 반영해 합계 전체에 곱한다.
        돌파 1.0 · 피벗 근접 0.95 · 형성 중 0.7 · 이격 과다 0.45 · 돌파 실패 0.15 (단계 없음 0.6)
        덮어쓰기 — 돌파 후 피벗 아래 재시험(breakout_date 있음 & 종가 < 피벗) 0.6,
                   돌파 후 5봉 이상 지났는데 아직 매수 범위(피벗~+5%) 안(묵은 돌파) 0.7
    베이스 없이 보컬만 걸린 종목(관찰용 후보): 베이스 패턴 점수 0, W = 0.6.

보너스·감점 (W 밖에서 더함)
    + 복수 베이스 중첩: 같은 구조를 먼저 하나로 묶은 뒤 (서로 다른 구조 수 − 1) × 4, 최대 +8 (피벗 있는 베이스만 —
      빗각 추세선 돌파와 빗각 돌파 + 피보 눌림은 같은 동결 선에서 나와 늘 같은 구조로 본다, SAME_STRUCTURE)
    + 최근 5일 내 거래대금 300억↑ +5
    ± 업종·테마 강도 (StockScan.groups): 소속 그룹 최고 순위 상위 10% +5, 하위 20% -3
    − 진입 손절폭 (planned_entry 기준 1 − 손절가/진입가) 10% 초과 → W 상한 0.7, 15% 초과 추가 -10
      (손절가가 있는 패턴만 — 컵 앤 핸들 식에는 손절 규칙이 없어 해당 없음). 메모는 피벗 기준 손절폭도 10% 를 넘으면
      '관망'(진입가 바닥이 피벗이라 눌림으로 줄지 않음), 아니면 '눌림 대기'(피벗 쪽으로 눌리면 줄어듦).

장중 스캔 (EOD_PATTERNS — 완성 봉만으로 판정하는 《차트의 기술》 기법)
    단계가 어제 완성 봉 기준이라 W 덮어쓰기 · 손절폭 · 매수 계획도 같은 봉(어제 종가 · 그 봉까지 날짜)으로 잰다(compute 의
    eod_close · eod_dates). 컵 앤 핸들 식 · 보컬은 오늘 미완성 봉까지 쓰므로 지금가 그대로.
    − 시장 조정 국면 -10
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult

BASE_PATTERNS = ("cup_with_handle", "trendline_break", "fib_pullback", "trendline_fib")
# 손절 규칙 없는 사건 신호 — 후보 · 칩 · 일지(rule 칸)는 되지만 종합 점수 · 매수 계획 · 실시간 감시에는 쓰지 않는다.
SIGNAL_PATTERNS = ("ma60_supply", "red_three_monthly")
# 신호 패턴이 혼자 후보가 되는 단계 (구현 선택 — 2026-10-13 캐시 860종목: 적삼병 형성 중 202 · 피벗 근접(잠정 셋째) 145 는
# 아직 신호가 아니고, 60일선 돌파 실패 31 은 끝난 신호라 꼬리표로만)
SIGNAL_CANDIDATE_STAGES = {
    "ma60_supply": (BREAKOUT, NEAR_PIVOT, EXTENDED),      # 돌파 · 60일선 재시험 · 이격 (5봉 안 돌파)
    "red_three_monthly": (BREAKOUT, EXTENDED),            # 신호 (셋째 양봉 월 = 가장 최근 완성 월)
}
# 관찰 전용 — 종합 점수 · 매수 계획 · 실시간 감시에 쓰지 않는다. 혼자서도 후보가 된다(관찰 칩).
# 10% 주도주 = 분봉 진입(일봉으로는 진입 판정 없음 · 피벗 · 손절 없음), 보컬 = 과거 검증 손실.
OBSERVE_PATTERNS = ("day_leader", "vocal")
# 외부 목록 정보 칩 (관찰용) — 기업추적 저평가 목록(value_list). 차트 패턴이 아니며 점수 · 매수 계획에 쓰지 않고
# 혼자서 후보가 되지 않는다. 후보 목록 칩 순서: 베이스 · 신호 · 관찰(10% 주도주 · 보컬) · 저평가 종목.
INFO_PATTERNS = ("undervalued",)
# 실시간 감시(live)에 쓰는 베이스 — 위 docstring 'LIVE_PATTERNS'
LIVE_PATTERNS = ("cup_with_handle",)
# 늘 같은 구조로 보는 짝 (중첩 보너스 중복 방지) — 빗각 돌파 + 피보 눌림은 빗각 추세선 돌파의 동결 선 위에서 시작한다
SAME_STRUCTURE = (frozenset({"trendline_break", "trendline_fib"}),)
# 손절가가 없을 때 그 이유 (리포트 · 표의 '진입계획' 문구) — 식 · 기법마다 다르다
NO_STOP_REASON = {
    "cup_with_handle": "식에 손절 규칙이 없어",
    "trendline_break": "돌파 전 — 손절(다음 봉 동결 선 값)은 돌파 뒤에 생겨",
    "ma60_supply": "기법(영상 [57:00–01:00:00])에 손절 규칙이 없어",
    "red_three_monthly": "기법에 손절 규칙이 없어(확정 저점은 구조 무효선일 뿐)",
    "fib_pullback": "반등 양봉 신호 전이라 진입가 · 손절이 아직 없어",
    "trendline_fib": "반등 양봉 신호 전이라 진입가 · 손절이 아직 없어",
}

# 피벗 · 손절가는 있지만 기법상 아직 사지 않는 상태 (metrics['phase']) — 매수 계획은 수량 0 · 이 문구 (구현 선택)
PLAN_HOLD = {
    "trendline_break": {
        "lowvol": "돌파 거래량 미달 — 관찰만 (스펙: 돌파 거래량 필수, 직전 50봉 평균 × 1.5)",
        "pending": "안착 확인 대기 — 선 +3% 종가 또는 돌파일 포함 3종가 선 위가 된 뒤 매수 검토",
    },
}

# 완성 봉(tq.eod_frame)만으로 판정하는 패턴 — 장중 스캔에서 단계와 함께 쓰는 값(피벗 대비 · W · 손절폭 · 계획)도 어제 종가로
EOD_PATTERNS = ("trendline_break", "fib_pullback", "trendline_fib", "ma60_supply", "red_three_monthly", "day_leader")
# 손절이 저가 기준인 패턴 (backtest.STOP_RULE 'low' 와 같아야 한다 — 시험) — 장중 저가가 손절가 아래면 마감 뒤에도 손절
LOW_STOP_PATTERNS = ("fib_pullback", "trendline_fib")

STAGE_WEIGHT = {BREAKOUT: 1.0, NEAR_PIVOT: 0.95, FORMING: 0.7, EXTENDED: 0.45, FAILED: 0.15, None: 0.6}
ACTIONABLE = (BREAKOUT, NEAR_PIVOT)


def plan_hold(r: PatternResult | None) -> str | None:
    """기법상 아직 사지 않는 상태면 그 문구 (PLAN_HOLD), 아니면 None."""
    if r is None:
        return None
    return PLAN_HOLD.get(r.name, {}).get(str((r.metrics or {}).get("phase") or ""))


def no_stop_reason(r: PatternResult | None) -> str:
    """손절가 없는 결과의 이유 문구 (모르는 패턴은 일반 문구)."""
    return NO_STOP_REASON.get(r.name if r is not None else "", "손절 규칙이 없어")


def has_pivot(r: PatternResult | None) -> bool:
    """피벗(매수 기준가)이 있는 탐지 결과 — 베이스의 대표 · W · 혼자 후보 자격."""
    if r is None or not r.detected or r.pivot is None:
        return False
    try:
        p = float(r.pivot)
    except (TypeError, ValueError):
        return False
    return p == p and p > 0


def signal_candidate(name: str, r: PatternResult | None) -> bool:
    """신호 패턴 결과가 혼자 후보를 만드는가 (SIGNAL_CANDIDATE_STAGES)."""
    return r is not None and r.detected and r.stage in SIGNAL_CANDIDATE_STAGES.get(name, ())


@dataclass
class ScoringConfig:
    # ---- 합계 가중치 (합으로 나눠 0~100 유지)
    w_pattern: float = 0.55
    w_rs: float = 0.20
    # ---- 단계 가중치 W (합계 전체에 곱함)
    stage_weight: dict = field(default_factory=lambda: dict(STAGE_WEIGHT))
    retest_weight: float = 0.6            # 돌파 후 피벗 아래 재시험
    stale_weight: float = 0.7             # 묵은 돌파 (돌파 후 stale_bars 봉 이상, 매수 범위 안)
    stale_bars: int = 5
    buy_range: float = 0.05               # 매수 범위 = 피벗 ~ 피벗 × (1 + 5%)
    # ---- 같은 구조 판정 (중복 패턴 묶기)
    same_pivot_pct: float = 0.02          # 피벗 차이 2% 이내
    same_bars: int = 15                   # 시작일(종료일) 차이 15봉 이내
    # ---- 보너스·감점
    multi_bonus_each: float = 4.0
    multi_bonus_max: float = 8.0
    big_value_bonus: float = 5.0
    sector_top_pct: float = 0.9           # 그룹 순위 백분위(1=최강) 이상이면 가산 (0.8~0.9 구간은 초과수익 없음)
    sector_top_bonus: float = 5.0
    sector_bottom_pct: float = 0.2        # 이하이면 감점
    sector_bottom_penalty: float = -3.0
    risk_warn: float = 0.10               # 진입 손절폭 > 10% → W 상한 unactionable_weight (지금 매수 불가 = 눌림 대기)
    risk_warn_penalty: float = 0.0
    unactionable_weight: float = 0.7
    risk_max: float = 0.15                # > 15% → -10
    risk_max_penalty: float = -10.0
    correction_penalty: float = -10.0     # 시장 조정 국면

    def weights(self) -> tuple[float, float]:
        """(패턴, RS) 가중치 — 합이 1."""
        s = self.w_pattern + self.w_rs
        return (self.w_pattern / s, self.w_rs / s) if s > 0 else (0.0, 0.0)


DEFAULT = ScoringConfig()


@dataclass
class ScoreBreakdown:
    composite: float
    pattern_part: float                    # 대표 베이스 패턴 점수 (W 적용 전)
    rs_part: float
    bonus: float
    best_pattern: str | None
    best_stage: str | None
    detected_bases: list[str]
    notes: list[str]
    stage_weight: float = 1.0              # 합계에 곱한 W
    structures: int = 0                    # 중복을 묶은 서로 다른 베이스 구조 수
    entry_risk: float | None = None        # 대표 결과의 진입 손절폭
    w_pattern: float = 0.0                 # 실제로 쓴 가중치 (리포트 표시용)
    w_rs: float = 0.0


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
    if frozenset({a.name, b.name}) in SAME_STRUCTURE:
        return True
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
    return float(w), why


def planned_entry(r: PatternResult | None, close: float | None) -> float | None:
    """계획 진입가 = max(피벗, 현재가): 돌파 전엔 피벗 매수, 돌파 후엔 현재가 매수."""
    if r is None or close is None or not r.pivot:
        return None
    return max(float(r.pivot), float(close))


def pivot_risk(r: PatternResult | None) -> float | None:
    """피벗 진입 기준 손절폭 1 − 손절가/피벗 — planned_entry 의 바닥(진입가 ≥ 피벗)이라 눌림으로는 이보다 줄지 않는다."""
    if r is None or not r.pivot or not r.stop:
        return None
    return 1 - float(r.stop) / float(r.pivot)


def entry_risk(r: PatternResult | None, close: float | None) -> float | None:
    """계획 진입가(planned_entry) 대비 손절가까지의 거리 (음수 = 이미 손절가 아래). 손절가가 없으면 None."""
    if r is None or not r.pivot or not r.stop or close is None:
        return None
    entry = planned_entry(r, close)
    return 1 - float(r.stop) / entry if entry else None


# ---------------------------------------------------------------- 후보
def is_candidate(results: dict[str, PatternResult], rs: float | None = None) -> bool:
    """리포트에 올릴 후보: 피벗 있는 베이스 결과 하나 이상, 신호 패턴의 신호 단계(SIGNAL_CANDIDATE_STAGES),
    또는 관찰 칩(10% 주도주 · 보컬 깔때기). 피벗 없는 베이스 결과(피보 신호 전 접촉 · 대기)와 신호 패턴의 그 밖 단계는
    다른 이유로 후보가 된 종목의 꼬리표로만 보인다. 저평가 종목(undervalued, INFO_PATTERNS)은 혼자 후보가 되지 않는다."""
    if any(has_pivot(results.get(n)) for n in BASE_PATTERNS):
        return True
    if any(signal_candidate(n, results.get(n)) for n in SIGNAL_PATTERNS):
        return True
    # 관찰 칩(10% 주도주 · 보컬) — 종합 점수에는 넣지 않는다
    return any(results.get(n) is not None and results[n].detected for n in OBSERVE_PATTERNS)


# ---------------------------------------------------------------- 종합 점수
def compute(results: dict[str, PatternResult], rs: float | None, market_state=None,
            recent_big_value: bool = False, *, close: float | None = None,
            dates: pd.DatetimeIndex | None = None, groups: dict | None = None,
            cfg: ScoringConfig | None = None, eod_close: float | None = None,
            eod_dates: pd.DatetimeIndex | None = None) -> ScoreBreakdown:
    """종합 점수. close(현재가)·dates(일봉 인덱스)·groups(업종·테마 순위)는 있으면 해당 규칙에 쓴다.
    eod_close · eod_dates(장중 스캔의 마지막 완성 봉 종가 · 그 봉까지 날짜)를 주면 EOD_PATTERNS 결과의 W 덮어쓰기 ·
    손절폭은 그 값으로 — 단계를 정한 봉과 같은 봉."""
    cfg = cfg or DEFAULT

    def basis(name: str | None) -> tuple[float | None, pd.DatetimeIndex | None]:
        r0 = results.get(name) if name else None
        final = bool(r0 is not None and (r0.metrics or {}).get("intraday_final"))   # 장중 저가로 이미 확정 — 오늘 봉 기준
        if eod_close is not None and name in EOD_PATTERNS and not final:
            return eod_close, (eod_dates if eod_dates is not None else dates)
        return close, dates

    wp, wr_ = cfg.weights()
    detected = [n for n in BASE_PATTERNS if n in results and results[n].detected]
    # 대표 · W · 중첩 보너스는 피벗(매수 기준가)이 있는 결과만 — 피보 신호 전 단계는 W 를 매길 기준가가 없다
    bases = [(n, results[n]) for n in detected if has_pivot(results[n])]
    rs_part = float(rs or 0)
    common = wr_ * rs_part

    notes: list[str] = []
    best_name, best_stage, best_r = None, None, None
    pattern_part, w, w_why, best_val = 0.0, cfg.stage_weight.get(None, 0.6), None, -1.0
    for name, r in bases:
        c, d = basis(name)
        wr, why = stage_weight(name, r, c, d, cfg)
        rk = entry_risk(r, c)
        if rk is not None and rk > cfg.risk_warn and r.stage in ACTIONABLE and wr > cfg.unactionable_weight:
            wr = cfg.unactionable_weight
            pr = pivot_risk(r)
            hold = (f"관망(피벗 기준도 {pr:.1%} — 눌림으로 안 줄어듦)" if pr is not None and pr > cfg.risk_warn
                    else "눌림 대기")
            why = ((why + " · ") if why else "") + f"손절폭 {rk:.1%} — {hold}"
        val = wr * (wp * _score(r) + common)
        if val > best_val:
            best_name, best_stage, best_r, pattern_part, w, w_why, best_val = name, r.stage, r, _score(r), wr, why, val
    notes.append(f"단계 가중치 ×{w:.2f}" + (f" ({w_why})" if w_why else ""))
    if eod_close is not None and best_name in EOD_PATTERNS and basis(best_name)[0] == eod_close:
        notes.append("장중 스캔 — 이 기법은 완성 봉만 판정: 단계 · W · 손절폭은 어제 종가 기준")

    bonus = 0.0
    structures = count_structures(bases, dates, cfg) if bases else []
    merged = [g for g in structures if len(g) > 1]
    if merged:
        notes.append("같은 구조 중복 제외: " + ", ".join("=".join(g) for g in merged))
    if len(structures) > 1:
        b = min(cfg.multi_bonus_max, cfg.multi_bonus_each * (len(structures) - 1))
        bonus += b
        notes.append(f"복수 패턴 중첩 +{b:.0f}")
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
    risk = entry_risk(best_r, basis(best_name)[0])
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

    composite = w * (wp * pattern_part + common) + bonus
    return ScoreBreakdown(
        composite=round(max(0.0, min(100.0, composite)), 1), pattern_part=round(pattern_part, 1),
        rs_part=rs_part, bonus=bonus, best_pattern=best_name,
        best_stage=best_stage, detected_bases=detected, notes=notes,
        stage_weight=round(w, 2), structures=len(structures),
        entry_risk=round(risk, 4) if risk is not None else None,
        w_pattern=round(wp, 3), w_rs=round(wr_, 3),
    )
