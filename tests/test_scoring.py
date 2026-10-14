"""종합 점수 (2026-10-14 패턴 초기화 뒤): 베이스 = 컵 앤 핸들 하나, 기술적 체력 · 주도주 · 패턴별 덮어쓰기 없음.

여러 베이스를 묶는 장치(같은 구조 판정 · 중첩 보너스)는 앞으로 들어올 식을 위해 남아 있어, 시험용 키를
scoring.BASE_PATTERNS 에 잠시 더해(monkeypatch — 등록은 안 함) 잰다."""
import pandas as pd
import pytest

from chart_screener import scoring
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from synthetic import confirmed_market

DATES = pd.bdate_range("2026-01-01", periods=200)
CWH = "cup_with_handle"


def _d(i: int) -> str:
    return f"{DATES[i]:%Y-%m-%d}"


def _pr(name=CWH, score=80.0, stage=BREAKOUT, pivot=100.0, stop=93.0, start=None, end=None, bo=None,
        metrics=None, detected=True):
    return PatternResult(name=name, label=name, detected=detected, score=score, stage=stage, pivot=pivot,
                         stop=stop, start_date=start, end_date=end, breakout_date=bo, metrics=metrics or {})


@pytest.fixture
def two_bases(monkeypatch):
    monkeypatch.setattr(scoring, "BASE_PATTERNS", (CWH, "t_base"))
    return "t_base"


# ---------------------------------------------------------------- 구성
def test_pattern_sets_after_reset():
    # 2026-10-14 초기화 뒤 《차트의 기술》 기법 6개를 묶음마다 더했다 (SIGNAL_PATTERNS 는 옛 이름과 다른 새 묶음 —
    # 손절 규칙 없는 사건 신호: 후보 · 칩 · 일지만, 종합 점수 · 매수 계획 · 실시간 감시 밖)
    assert scoring.BASE_PATTERNS == (CWH, "trendline_break", "fib_pullback", "trendline_fib")
    assert scoring.SIGNAL_PATTERNS == ("ma60_supply", "red_three_monthly")
    assert scoring.OBSERVE_PATTERNS == ("day_leader", "vocal") and scoring.INFO_PATTERNS == ("undervalued",)
    assert scoring.LIVE_PATTERNS == (CWH,)
    groups = [scoring.BASE_PATTERNS, scoring.SIGNAL_PATTERNS, scoring.OBSERVE_PATTERNS, scoring.INFO_PATTERNS]
    names = [n for g in groups for n in g]
    assert len(names) == len(set(names))                                  # 한 패턴은 한 묶음에만
    for gone in ("is_leader", "LEADER_TAG", "pullback_limit", "pullback_zone_top", "CONTEXT_PATTERNS"):
        assert not hasattr(scoring, gone)


def test_weights_renormalized_without_tech_term():
    wp, wr = scoring.DEFAULT.weights()
    assert wp == pytest.approx(0.55 / 0.75) and wr == pytest.approx(0.20 / 0.75) and wp + wr == pytest.approx(1)
    a = scoring.compute({CWH: _pr(score=80, stage=BREAKOUT)}, rs=90)
    assert a.composite == pytest.approx((0.55 * 80 + 0.20 * 90) / 0.75, abs=0.05)
    assert a.w_pattern == pytest.approx(0.733, abs=1e-3) and a.w_rs == pytest.approx(0.267, abs=1e-3)
    assert not hasattr(a, "tech_part")


def test_stage_weight_multiplies_whole_composite():
    a = scoring.compute({CWH: _pr(score=80, stage=BREAKOUT)}, rs=90)
    b = scoring.compute({CWH: _pr(score=80, stage=EXTENDED)}, rs=90)
    assert b.stage_weight == 0.45
    assert b.composite == pytest.approx(0.45 * a.composite, abs=0.1)
    assert b.pattern_part == 80  # 패턴 점수는 W 적용 전 값


@pytest.mark.parametrize("stage,w", [(BREAKOUT, 1.0), (NEAR_PIVOT, 0.95), (FORMING, 0.7), (EXTENDED, 0.45),
                                     (FAILED, 0.15)])
def test_stage_weights(stage, w):
    assert scoring.compute({CWH: _pr(stage=stage)}, rs=80).stage_weight == w


def test_extended_cannot_outrank_actionable_on_rs():
    near = scoring.compute({CWH: _pr(score=60, stage=NEAR_PIVOT)}, rs=75)
    ext = scoring.compute({CWH: _pr(score=95, stage=EXTENDED)}, rs=99)
    failed = scoring.compute({CWH: _pr(score=95, stage=FAILED)}, rs=99)
    assert near.composite > ext.composite > failed.composite


def test_retest_after_breakout_weight():
    r = _pr(stage=NEAR_PIVOT, pivot=100, stop=93, bo=_d(-3))
    sb = scoring.compute({CWH: r}, rs=80, close=99.0, dates=DATES)
    assert sb.stage_weight == 0.6
    assert any("재시험" in n for n in sb.notes)
    assert scoring.compute({CWH: r}, rs=80).stage_weight == 0.95      # 종가를 모르면 단계 기본값


def test_stale_breakout_weight():
    old = _pr(stage=NEAR_PIVOT, pivot=100, stop=93, bo=_d(-9))
    sb = scoring.compute({CWH: old}, rs=80, close=102.0, dates=DATES)
    assert sb.stage_weight == 0.7 and any("묵은 돌파" in n for n in sb.notes)
    fresh = _pr(stage=BREAKOUT, pivot=100, stop=93, bo=_d(-2))
    assert scoring.compute({CWH: fresh}, rs=80, close=102.0, dates=DATES).stage_weight == 1.0
    ext = _pr(stage=EXTENDED, pivot=100, stop=93, bo=_d(-9))   # 매수 범위(+5%) 위면 이격 과다 가중치
    assert scoring.compute({CWH: ext}, rs=80, close=110.0, dates=DATES).stage_weight == 0.45


def test_no_stop_pattern_has_no_entry_risk():
    # 컵 앤 핸들 식에는 손절 규칙이 없다 → 손절폭 감점 · '눌림 대기' 상한이 걸리지 않는다
    sb = scoring.compute({CWH: _pr(stage=NEAR_PIVOT, pivot=100, stop=None)}, rs=80, close=99.0)
    assert sb.entry_risk is None and sb.bonus == 0 and sb.stage_weight == 0.95


def test_candidates_base_or_vocal_only():
    assert scoring.is_candidate({CWH: _pr()})
    assert not scoring.is_candidate({CWH: _pr(detected=False)})
    assert scoring.is_candidate({"vocal": _pr("vocal", stage=FORMING)})
    assert not scoring.is_candidate({"undervalued": _pr("undervalued", stage=None)})       # 정보 칩은 혼자 후보 아님
    assert not scoring.is_candidate({"trend_template": _pr("trend_template", stage=None)})  # 옛 키는 아무 뜻 없음
    vocal_only = scoring.compute({"vocal": _pr("vocal", score=85, stage=BREAKOUT)}, rs=90)
    assert vocal_only.best_pattern is None and vocal_only.pattern_part == 0 and vocal_only.stage_weight == 0.6


# ---------------------------------------------------------------- 중복 구조 (여러 베이스 장치)
def test_same_pivot_same_start_counted_once(two_bases):
    res = {CWH: _pr(score=91, stage=NEAR_PIVOT, pivot=30900, start=_d(100), end=_d(-10)),
           two_bases: _pr(two_bases, score=79, stage=NEAR_PIVOT, pivot=30900, start=_d(100), end=_d(-10))}
    sb = scoring.compute(res, rs=85, dates=DATES)
    assert sb.structures == 1
    assert not any("복수 패턴" in n for n in sb.notes) and any("같은 구조" in n for n in sb.notes)
    assert sb.best_pattern == CWH  # 높은 점수를 남김


def test_distinct_structures_get_bonus(two_bases):
    res = {CWH: _pr(pivot=100, start=_d(0), end=_d(-1)), two_bases: _pr(two_bases, pivot=125, start=_d(60), end=_d(110))}
    sb = scoring.compute(res, rs=80, dates=DATES)
    assert sb.structures == 2 and "복수 패턴 중첩 +4" in sb.notes and sb.bonus == 4


def test_unknown_dates_are_distinct_and_busday_fallback():
    a, b = _pr(), _pr("t_base")
    assert not scoring.same_structure(a, b)
    a = _pr(start="2026-03-02", end="2026-06-30")
    b = _pr("t_base", start="2026-03-10", end="2026-06-30")
    assert scoring.same_structure(a, b)  # dates 없이 영업일 수로 근사


# ---------------------------------------------------------------- 보너스·감점
def test_entry_risk_penalty():
    def run(stop, close=99.0):
        return scoring.compute({CWH: _pr(stage=NEAR_PIVOT, pivot=100, stop=stop)}, rs=80, close=close)
    base = run(93)
    assert base.bonus == 0 and base.entry_risk == pytest.approx(0.07)
    r12 = run(88)                       # 12%: 감점 대신 W 상한 0.7 ('눌림 대기')
    assert r12.bonus == 0 and r12.stage_weight == 0.7
    assert run(84).bonus == -10         # 16%
    assert run(93, close=110).bonus == -10   # 진입가 = 현재가 110 → 15.5%


def test_sector_bonus():
    res = {CWH: _pr()}
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": 0.9}).bonus == 5
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": 0.1}).bonus == -3
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": 0.5}).bonus == 0
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": None}).bonus == 0
    assert scoring.compute(res, rs=80, groups=None).bonus == 0


def test_big_value_bonus_and_market_penalty():
    res = {CWH: _pr()}
    sb = scoring.compute(res, rs=80, recent_big_value=True)
    assert sb.bonus == 5
    ms = confirmed_market()
    ms.state = "correction"
    worse = scoring.compute(res, rs=80, recent_big_value=True, market_state=ms)
    assert worse.bonus == -5 and "시장 조정 국면 -10" in worse.notes
