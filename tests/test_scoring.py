import pandas as pd
import pytest

from chart_screener import scoring
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from synthetic import confirmed_market

DATES = pd.bdate_range("2026-01-01", periods=200)


def _d(i: int) -> str:
    return f"{DATES[i]:%Y-%m-%d}"


def _pr(name, score=80.0, stage=BREAKOUT, pivot=100.0, stop=93.0, start=None, end=None, bo=None,
        metrics=None, detected=True):
    return PatternResult(name=name, label=name, detected=detected, score=score, stage=stage, pivot=pivot,
                         stop=stop, start_date=start, end_date=end, breakout_date=bo, metrics=metrics or {})


def _ctx_patterns(tt=80.0, cs=80.0):
    return {"trend_template": _pr("trend_template", score=tt, stage=None, pivot=None, stop=None),
            "canslim": _pr("canslim", score=cs, stage=None, pivot=None, stop=None, detected=False)}


# ---------------------------------------------------------------- 공식·단계 가중치
def test_base_patterns_include_big_value_pullback():
    assert "big_value_pullback" in scoring.BASE_PATTERNS


def test_stage_weight_multiplies_whole_composite():
    res = {"vcp": _pr("vcp", score=80, stage=BREAKOUT)} | _ctx_patterns(80, 80)
    a = scoring.compute(res, rs=90)
    assert a.composite == pytest.approx(0.55 * 80 + 0.25 * 80 + 0.20 * 90, abs=0.05)
    res["vcp"] = _pr("vcp", score=80, stage=EXTENDED)
    b = scoring.compute(res, rs=90)
    assert b.stage_weight == 0.45
    assert b.composite == pytest.approx(0.45 * a.composite, abs=0.1)
    assert b.pattern_part == 80  # 패턴 점수는 W 적용 전 값


@pytest.mark.parametrize("stage,w", [(BREAKOUT, 1.0), (NEAR_PIVOT, 0.95), (FORMING, 0.7), (EXTENDED, 0.45),
                                     (FAILED, 0.15)])
def test_stage_weights(stage, w):
    sb = scoring.compute({"vcp": _pr("vcp", stage=stage)}, rs=80)
    assert sb.stage_weight == w


def test_extended_cannot_outrank_actionable_on_trend_and_rs():
    near = scoring.compute({"vcp": _pr("vcp", score=60, stage=NEAR_PIVOT)} | _ctx_patterns(60, 60), rs=75)
    ext = scoring.compute({"vcp": _pr("vcp", score=95, stage=EXTENDED)} | _ctx_patterns(98, 98), rs=99)
    failed = scoring.compute({"vcp": _pr("vcp", score=95, stage=FAILED)} | _ctx_patterns(98, 98), rs=99)
    assert near.composite > ext.composite > failed.composite


def test_retest_after_breakout_weight():
    r = _pr("vcp", stage=NEAR_PIVOT, pivot=100, stop=93, bo=_d(-3))
    sb = scoring.compute({"vcp": r}, rs=80, close=99.0, dates=DATES)
    assert sb.stage_weight == 0.6
    assert any("재시험" in n for n in sb.notes)
    # 종가를 모르면 단계 기본값
    assert scoring.compute({"vcp": r}, rs=80).stage_weight == 0.95


def test_stale_breakout_weight():
    old = _pr("vcp", stage=NEAR_PIVOT, pivot=100, stop=93, bo=_d(-9))
    sb = scoring.compute({"vcp": old}, rs=80, close=102.0, dates=DATES)
    assert sb.stage_weight == 0.7
    assert any("묵은 돌파" in n for n in sb.notes)
    fresh = _pr("vcp", stage=BREAKOUT, pivot=100, stop=93, bo=_d(-2))
    assert scoring.compute({"vcp": fresh}, rs=80, close=102.0, dates=DATES).stage_weight == 1.0
    # 매수 범위(+5%) 위면 묵은 돌파 규칙 대상 아님 → 이격 과다 가중치
    ext = _pr("vcp", stage=EXTENDED, pivot=100, stop=93, bo=_d(-9))
    assert scoring.compute({"vcp": ext}, rs=80, close=110.0, dates=DATES).stage_weight == 0.45


def test_long_base_limit_up_breakout_weight():
    for m in ({"limit_up": True}, {"candle_class": "limit_up"}):
        r = _pr("long_base_breakout", stage=BREAKOUT, metrics=m)
        assert scoring.compute({"long_base_breakout": r}, rs=80).stage_weight == 0.6
    r = _pr("long_base_breakout", stage=BREAKOUT, metrics={"limit_up": False})
    assert scoring.compute({"long_base_breakout": r}, rs=80).stage_weight == 1.0


def test_big_value_pullback_near_pivot_weight():
    # 50%선 눌림(재돌파 전: breakout_date 없음) — 종가가 지지선 아래여도 W 1.0
    r = _pr("big_value_pullback", stage=NEAR_PIVOT, pivot=100, stop=96, metrics={"support": 100.0})
    sb = scoring.compute({"big_value_pullback": r}, rs=80, close=98.0, dates=DATES)
    assert sb.stage_weight == 1.0
    assert sb.best_pattern == "big_value_pullback"
    # 진입 손절폭은 매수 구간 상단(50%선 × 1.03) 기준 (max(피벗, 현재가)가 아님)
    sb = scoring.compute({"big_value_pullback": r}, rs=80, close=104.0, dates=DATES)
    assert sb.entry_risk == pytest.approx(1 - 96 / 103, abs=1e-3)   # ScoreBreakdown 은 소수 3자리 반올림
    # 재돌파 후 5봉 넘게 매수 범위에서 머문 near_pivot(rebreak_hold)은 50%선 눌림이 아니라 묵은 돌파
    r = _pr("big_value_pullback", stage=NEAR_PIVOT, pivot=100, stop=90, bo=_d(-7))
    sb = scoring.compute({"big_value_pullback": r}, rs=80, close=102.0, dates=DATES)
    assert sb.stage_weight == 0.7


def test_canslim_lead_without_base():
    cs = _pr("canslim", score=85, stage=EXTENDED, pivot=100, stop=93)
    sb = scoring.compute({"canslim": cs, "trend_template": _pr("trend_template", score=85, stage=None)}, rs=95)
    assert sb.stage_weight == 0.35
    assert sb.pattern_part == 0 and sb.best_pattern is None
    cs.stage = BREAKOUT
    assert scoring.compute({"canslim": cs}, rs=95).stage_weight == 1.0


# ---------------------------------------------------------------- 중복 구조
def test_same_pivot_same_start_counted_once():
    res = {"vcp": _pr("vcp", score=79, stage=NEAR_PIVOT, pivot=30900, start=_d(100), end=_d(-10)),
           "cup_handle": _pr("cup_handle", score=91, stage=NEAR_PIVOT, pivot=30900, start=_d(100), end=_d(-10))}
    sb = scoring.compute(res, rs=85, dates=DATES)
    assert sb.structures == 1
    assert not any("복수 패턴" in n for n in sb.notes)
    assert any("같은 구조" in n for n in sb.notes)
    assert sb.best_pattern == "cup_handle"  # 높은 점수를 남김


def test_contained_base_with_same_pivot_counted_once():
    res = {"vcp": _pr("vcp", pivot=10690, start=_d(50), end=_d(-1)),
           "three_weeks_tight": _pr("three_weeks_tight", score=65, pivot=10700, start=_d(-18), end=_d(-4))}
    assert scoring.compute(res, rs=90, dates=DATES).structures == 1


def test_same_span_different_pivot_counted_once():
    res = {"cup_handle": _pr("cup_handle", score=44, stage=FORMING, pivot=302000, start=_d(90), end=_d(-1)),
           "double_bottom": _pr("double_bottom", score=73, stage=NEAR_PIVOT, pivot=272500, start=_d(90),
                                end=_d(-1))}
    sb = scoring.compute(res, rs=81, dates=DATES)
    assert sb.structures == 1 and sb.best_pattern == "double_bottom"


def test_distinct_structures_get_bonus():
    res = {"long_base_breakout": _pr("long_base_breakout", pivot=100, start=_d(0), end=_d(-1)),
           "vcp": _pr("vcp", pivot=112, start=_d(120), end=_d(-1)),
           "flat_base": _pr("flat_base", pivot=125, start=_d(60), end=_d(110))}
    sb = scoring.compute(res, rs=80, dates=DATES)
    assert sb.structures == 3
    assert "복수 패턴 중첩 +8" in sb.notes
    two = scoring.compute({k: res[k] for k in ("long_base_breakout", "vcp")}, rs=80, dates=DATES)
    assert "복수 패턴 중첩 +4" in two.notes and two.bonus == 4


def test_unknown_dates_are_distinct_and_busday_fallback():
    a, b = _pr("vcp"), _pr("cup_handle")
    assert not scoring.same_structure(a, b)
    a = _pr("vcp", start="2026-03-02", end="2026-06-30")
    b = _pr("cup_handle", start="2026-03-10", end="2026-06-30")
    assert scoring.same_structure(a, b)  # dates 없이 영업일 수로 근사


# ---------------------------------------------------------------- 보너스·감점
def test_entry_risk_penalty():
    def run(stop, close=99.0):
        return scoring.compute({"vcp": _pr("vcp", stage=NEAR_PIVOT, pivot=100, stop=stop)}, rs=80, close=close)
    base = run(93)
    assert base.bonus == 0 and base.entry_risk == pytest.approx(0.07)
    r12 = run(88)                       # 12%: 감점 대신 W 상한 0.7 ('눌림 대기')
    assert r12.bonus == 0 and r12.stage_weight == 0.7
    assert run(84).bonus == -10         # 16%
    assert run(93, close=110).bonus == -10   # 진입가 = 현재가 110 → 15.5%


def test_leader_without_base():
    tt = _pr("trend_template", score=90, stage=None, pivot=None, stop=None,
             metrics={"passed": 8, "rs": 92, "from_52w_high": -0.08})
    res = {"trend_template": tt}
    sb = scoring.compute(res, rs=92)
    assert sb.leader and scoring.LEADER_TAG in sb.notes
    assert sb.stage_weight == 0.6 and sb.pattern_part == 0
    assert sb.composite == pytest.approx(0.6 * (0.25 * 90 + 0.20 * 92), abs=0.05)
    assert scoring.is_candidate(res, 92)
    assert not scoring.is_leader(res, rs=85)
    tt.metrics["from_52w_high"] = -0.2
    assert not scoring.is_leader(res, rs=95)
    tt.metrics["from_52w_high"] = -0.05
    assert not scoring.is_leader(res | {"vcp": _pr("vcp")}, rs=95)  # 베이스가 있으면 주도주 태그 없음
    tt.detected = False
    assert not scoring.is_candidate(res, 95)


def test_sector_bonus():
    res = {"vcp": _pr("vcp")}
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": 0.9}).bonus == 5
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": 0.1}).bonus == -3
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": 0.5}).bonus == 0
    assert scoring.compute(res, rs=80, groups={"best_rank_pct": None}).bonus == 0
    assert scoring.compute(res, rs=80, groups=None).bonus == 0


def test_signal_bonuses_and_market_penalty():
    res = {"vcp": _pr("vcp"), "pocket_pivot": _pr("pocket_pivot", stage=BREAKOUT)}
    sb = scoring.compute(res, rs=80, recent_big_value=True)
    assert sb.bonus == 10
    ms = confirmed_market()
    ms.state = "correction"
    worse = scoring.compute(res, rs=80, recent_big_value=True, market_state=ms)
    assert worse.bonus == 0 and "시장 조정 국면 -10" in worse.notes
