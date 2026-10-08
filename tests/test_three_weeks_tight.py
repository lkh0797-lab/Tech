import numpy as np
import pandas as pd
import pytest

from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.three_weeks_tight import (ThreeWeeksTightConfig, detect, last_week_complete,
                                                       weekly_groups)
from synthetic import make_context, make_ohlcv, set_bar

# 2023-01-02(월) 시작 영업일 인덱스 → i % 5 == 4 가 금요일. 300봉이면 마지막 봉(299)이 금요일.
ADV = [(0, 5000), (200, 7500), (225, 7800)]


def scenario(fri_closes=(10020, 9980, 10050), *, n=300, adv=ADV, pre_close=9700, vol_mult=0.6, seed=3):
    """마지막 len(fri_closes) 주가 타이트 구간(금요일 종가 지정), 그 직전 금요일 종가는 범위 밖."""
    k = len(fri_closes)
    start = 300 - 5 * k
    wps = list(adv) + [(start - 5, 9600), (start, 10000), (max(n - 1, 300), 10000)]
    df = make_ohlcv(wps, n=n, noise=0.005, wick=0.007, seed=seed, vol_segments=[(start, 400, vol_mult)], smooth=False)
    df = set_bar(df, start - 1, close=pre_close)
    for w, c in enumerate(fri_closes):
        df = set_bar(df, start + 4 + 5 * w, close=c)
    return df


def post(df, bars, at=300):
    for k, (o, h, l, c, v) in enumerate(bars):
        df = set_bar(df, at + k, open=o, high=h, low=l, close=c, volume=v)
    return df


def run(df, rs=90, partial=False, **kw):
    ctx = make_context(df, rs=rs, **kw)
    if partial:
        ctx.partial, ctx.session_frac = True, 0.6
    return detect(ctx)


# ---------------------------------------------------------------- 주봉 변환 · 주 완성 판정
def test_weekly_groups_monday_start():
    idx = pd.bdate_range("2023-01-02", periods=12)  # 월~금, 월~금, 월~화
    s, e = weekly_groups(idx)
    assert list(s) == [0, 5, 10] and list(e) == [4, 9, 11]
    idx2 = pd.DatetimeIndex(["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-28", "2026-10-02"])
    s2, e2 = weekly_groups(idx2)
    assert list(s2) == [0, 3] and list(e2) == [2, 4]


@pytest.mark.parametrize("last,expected", [
    ("2026-10-02", True),    # 금요일
    ("2026-10-07", False),   # 수요일 (목요일 거래일 남음)
    ("2026-10-08", True),    # 목요일, 금요일 10-09 한글날 (고정 휴장)
    ("2026-09-23", True),    # 수요일, 목·금 추석 연휴 (비정기 휴장)
    ("2026-12-30", True),    # 수요일, 12-31(목) 연말 휴장 · 01-01(금) 신정
])
def test_last_week_complete_holidays(last, expected):
    idx = pd.bdate_range(end=last, periods=30)
    df = make_ohlcv([(0, 100), (29, 110)], n=30)
    df.index = idx
    ctx = make_context(df)
    assert last_week_complete(ctx) is expected


def test_partial_bar_week_not_complete():
    df = scenario()
    ctx = make_context(df)
    assert last_week_complete(ctx)
    ctx.partial = True
    assert not last_week_complete(ctx)


# ---------------------------------------------------------------- (a) 교과서적 양성
def test_textbook_3wt():
    df = scenario()
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT
    assert abs(r.pivot / 10000 - 1) < 0.03
    m = r.metrics
    assert m["weeks"] == 3 and m["last_week_complete"] is True and m["weeks_since_tight"] == 0
    assert m["close_spread_pct"] == pytest.approx((10050 - 9980) / 9980 * 100, abs=0.01)
    assert m["prior_advance_pct"] >= 20 and m["vol_ratio"] < 0.8
    assert r.stop == pytest.approx(max(m["tight_low"], r.pivot * 0.92))
    assert r.start_date == str(df.index[285].date()) and r.end_date == str(df.index[299].date())
    assert {"hline", "box", "segment"} <= {a["kind"] for a in r.annotations}
    assert all(s.startswith("✔ ") for s in r.reasons) and all(w.startswith("✘ ") for w in r.warnings)
    assert 0 < r.score <= 100


def test_longer_tight_run_scores_higher():
    r3 = run(scenario())
    r5 = run(scenario((10020, 9980, 10050, 10010, 10030)))
    assert r5.detected and r5.metrics["weeks"] == 5
    assert r5.score > r3.score


# ---------------------------------------------------------------- (b) 단계별
def test_stage_forming():
    # 첫 주 월요일 장중 +7% 윗꼬리 → 피벗이 높아 종가가 피벗 -5% 밖
    df = scenario()
    df = set_bar(df, 285, high=10700)
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == FORMING


def test_stage_breakout_partial_week():
    df = post(scenario(n=301), [(10050, 10500, 10040, 10450, 3e6)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    assert r.metrics["last_week_complete"] is False
    assert r.end_date == str(df.index[299].date())
    assert r.breakout_date == str(df.index[300].date())
    assert r.metrics["breakout_vol_ratio"] >= 1.4


def test_stage_extended():
    df = post(scenario(n=303), [(10050, 10500, 10040, 10450, 3e6), (10450, 10800, 10400, 10750, 2e6),
                                (10750, 11000, 10700, 10950, 2e6)])
    r = run(df)
    assert r.detected and r.stage == EXTENDED


def test_stage_failed():
    df = post(scenario(n=303), [(10050, 10500, 10040, 10450, 3e6), (10400, 10420, 10000, 10050, 2e6),
                                (10000, 10010, 9700, 9750, 2e6)])
    r = run(df)
    assert r.detected and r.stage == FAILED


def test_breakout_week_after_complete():
    # 다음 주(완성) 중 돌파 → 타이트 구간은 2주 전 완성 주까지
    df = post(scenario(n=305), [(10050, 10300, 10000, 10250, 2e6), (10250, 10500, 10200, 10450, 3e6),
                                (10450, 10500, 10300, 10400, 1e6), (10400, 10450, 10350, 10420, 1e6),
                                (10420, 10480, 10380, 10430, 1e6)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.metrics["weeks_since_tight"] == 1 and r.metrics["last_week_complete"] is True
    assert r.stage in (BREAKOUT, NEAR_PIVOT)


# ---------------------------------------------------------------- 진행 중인 주 처리
def test_partial_current_week_in_range_counts_complete_weeks_only():
    df = scenario(n=303)  # 월~수 3봉 추가, 종가 10000 부근 (범위 안)
    r = run(df)
    assert r.detected, r.warnings
    assert r.metrics["weeks"] == 3 and r.metrics["last_week_complete"] is False
    assert any("이번 주는 미완성" in w for w in r.warnings)
    assert any("이번 주 종가도 범위 안" in s for s in r.reasons)


def test_two_complete_weeks_plus_partial_not_detected():
    df = scenario((9980, 10050), n=303)
    r = run(df)
    assert not r.detected
    assert any("확정 시 3WT 성립 가능" in w for w in r.warnings)


def test_partial_flag_on_friday_bar():
    # 마지막 봉이 금요일이지만 장중 → 이번 주 미확정 → 완성 타이트 주는 2주 뿐
    r = run(scenario(), partial=True)
    assert not r.detected
    assert r.metrics.get("last_week_complete") is False


# ---------------------------------------------------------------- (c) 음성
def test_reject_wide_closes():
    assert not run(scenario((10000, 10250, 9950))).detected


def test_reject_only_two_weeks():
    assert not run(scenario((10000, 10050))).detected


def test_reject_no_prior_advance():
    adv = [(0, 9000), (150, 9300), (225, 9500)]
    r = run(scenario(adv=adv))
    assert not r.detected
    assert any("선행 상승 부족" in w for w in r.warnings)


def test_reject_not_stage2():
    adv = [(0, 20000), (200, 7000), (225, 7200)]
    r = run(scenario(adv=adv), rs=50)
    assert not r.detected
    assert any("Stage 2 미충족" in w for w in r.warnings)
    assert not any("선행 상승 부족" in w for w in r.warnings)


def test_reject_volatile_hold():
    df = set_bar(scenario(), 292, low=8700)  # 둘째 주 장중 -13% 급락 (종가는 유지)
    r = run(df)
    assert not r.detected
    assert any("고저폭" in w for w in r.warnings)


def test_reject_breakdown_after_tight():
    df = post(scenario(n=305), [(10000, 10020, 9700, 9750, 2e6), (9750, 9800, 9600, 9650, 1e6),
                                (9650, 9700, 9550, 9600, 1e6), (9600, 9650, 9550, 9620, 1e6),
                                (9620, 9650, 9550, 9600, 1e6)])
    assert not run(df).detected


def test_reject_stale_tight_area():
    # 타이트 구간 종료 후 완성 주 3주 경과 (max_weeks_after=2 초과) → 최근 패턴 아님
    bars = [(10000, 10200, 9900, 10150, 8e5) for _ in range(15)]
    df = post(scenario(n=315), bars)
    df = set_bar(df, 309, close=9850)
    assert not run(df).detected


# ---------------------------------------------------------------- 미래 참조 없음
def test_truncation_consistency():
    df = post(scenario(n=302), [(10050, 10500, 10040, 10450, 3e6), (10450, 10600, 10400, 10500, 1.5e6)])
    cut, full = run(df.iloc[:300]), run(df)
    assert cut.detected and cut.stage == NEAR_PIVOT and cut.breakout_date is None
    assert full.detected and full.stage == BREAKOUT
    assert full.pivot == pytest.approx(cut.pivot)


def test_halt_date_warns():
    df = scenario()
    df.attrs["halt_dates"] = [str(df.index[290].date())]
    assert any("거래정지" in w for w in run(df).warnings)


def test_config_override():
    from chart_screener.config import Config
    cfg = Config(patterns={"three_weeks_tight": ThreeWeeksTightConfig(tight_pct=0.005)})
    assert not detect(make_context(scenario(), cfg=cfg)).detected


# ---------------------------------------------------------------- (d) 견고성
@pytest.mark.parametrize("kind", ["short", "flat", "random", "nan", "zero_vol", "zero_price"])
def test_robustness(kind):
    if kind == "short":
        df = make_ohlcv([(0, 100), (59, 120)])
    elif kind == "flat":
        idx = pd.bdate_range("2023-01-02", periods=400)
        df = pd.DataFrame({"open": 1e4, "high": 1e4, "low": 1e4, "close": 1e4, "volume": 1e5}, index=idx)
        df["value"] = df["close"] * df["volume"]
    elif kind == "random":
        rng = np.random.default_rng(5)
        c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.02, 500)))
        df = make_ohlcv([(i, float(x)) for i, x in enumerate(c)], noise=0.0, smooth=False)
    else:
        df = scenario()
        if kind == "nan":
            df.iloc[290, df.columns.get_loc("close")] = np.nan
        elif kind == "zero_vol":
            df["volume"] = 0.0
            df["value"] = 0.0
        elif kind == "zero_price":
            df.iloc[-2:, :4] = 0.0
    r = run(df)
    assert isinstance(r.detected, bool)
    if not r.detected:
        assert r.warnings
    if kind in ("short", "flat", "nan", "zero_price"):
        assert not r.detected


def test_random_walks_rarely_detect():
    hits = 0
    for seed in range(30):
        rng = np.random.default_rng(900 + seed)
        c = 10000 * np.exp(np.cumsum(rng.normal(0.0008, 0.02, 400)))
        df = make_ohlcv([(i, float(x)) for i, x in enumerate(c)], noise=0.0, smooth=False, seed=seed)
        hits += run(df).detected
    assert hits <= 3


# ---------------------------------------------------------------- 리뷰 회귀 테스트
def halt_bars(df, i0, i1):
    """[i0, i1) 봉을 캐시 데이터의 거래정지 봉처럼(O=H=L=C=직전 종가, 거래량 0) 만든다 — attrs 에는 없음."""
    c = float(df["close"].iloc[i0 - 1])
    for i in range(i0, i1):
        df = set_bar(df, i, open=c, high=c, low=c, close=c, volume=0)
    return df


def test_halt_weeks_inside_tight_area_rejected():
    # 둘째·셋째 주가 거래정지 → 주간 종가가 직전 종가 그대로(스프레드 0%) — 완벽한 3WT 로 오인하면 안 됨
    df = halt_bars(scenario(), 290, 300)
    r = run(df)
    assert not r.detected
    assert any("거래정지" in w and "제외" in w for w in r.warnings)


def test_halt_before_tight_area_rejected():
    assert run(scenario()).detected
    r = run(halt_bars(scenario(), 250, 253))     # 타이트 구간 직전 13주 안의 3일 정지
    assert not r.detected
    assert any("직전 13주에 거래정지" in w for w in r.warnings)


def test_halt_excluded_from_volume_ratio():
    # 정지 봉(거래량 0)은 거래량 평균에서 빠져야 함: 직전 50일 기준 구간에 정지가 섞여도 비율이 부풀지 않음
    base = run(scenario()).metrics["vol_ratio"]
    df = halt_bars(scenario(), 260, 266)          # 50일 거래량 기준 구간 [235, 285) 안의 6일 정지
    r = run(df)
    assert not r.detected                          # 직전 13주 정지 → 제외
    assert r.metrics["vol_ratio"] == pytest.approx(base, rel=0.05)
    assert r.metrics["vol_ratio"] < base * 50 / 44 * 0.97   # 0 을 평균에 넣으면 약 50/44 배로 부풂


def _squeeze(df, i0, i1, rng=0.002):
    """[i0, i1) 봉의 장중 폭을 ±rng 로 줄인다 (종가 유지)."""
    df = df.copy()
    for i in range(i0, i1):
        c = float(df["close"].iloc[i])
        df.iloc[i, df.columns.get_indexer(["open", "high", "low"])] = [c, c * (1 + rng), c * (1 - rng)]
    from synthetic import add_value
    return add_value(df)


def test_pinned_price_rejected():
    # 공개매수 등으로 주간 고저폭이 1% 안팎 → 3WT 아님
    r = run(_squeeze(scenario(), 285, 300))
    assert not r.detected
    assert r.metrics["avg_week_range_pct"] < 2
    assert any("가격 고정" in w for w in r.warnings)


def _pin(df, i0, i1, price, rng=0.001):
    """[i0, i1) 봉을 price 부근에 고정 (종가 ±0.05%, 장중 ±rng) — 공개매수가 고정 국면."""
    df = df.copy()
    rs = np.random.default_rng(0)
    for i in range(i0, i1):
        c = price * (1 + rs.normal(0, 0.0005))
        df.iloc[i, df.columns.get_indexer(["open", "high", "low", "close"])] = [c, c * (1 + rng), c * (1 - rng), c]
    from synthetic import add_value
    return add_value(df)


def test_pinned_regime_rejected_even_if_area_moves():
    # 타이트 구간 앞 10주가 9700 에 고정(주간 폭 0.3%) 후 10000 으로 올라 3주 타이트 — SK디앤디 2026-02 유형
    r = run(_pin(scenario(), 235, 285, 9700))
    assert not r.detected
    assert r.metrics["regime_week_range_pct"] < 2 <= r.metrics["avg_week_range_pct"]
    assert any("가격 고정" in w for w in r.warnings)


def test_abnormally_long_tight_run_rejected():
    closes = (10020, 9980, 10050, 10010, 10030, 9990, 10040, 10000, 10020, 10010)
    r = run(scenario(closes))
    assert not r.detected
    assert r.metrics["weeks"] > 8
    assert any("가격 고정" in w for w in r.warnings)
    r7 = run(scenario(closes[:7]))
    assert r7.detected and r7.metrics["weeks"] == 7, r7.warnings


def test_wide_first_week_rejected():
    # 첫 주 장중 +25% 급등(종가만 범위 안) → 타이트 구간 고저폭 15% 초과
    r = run(set_bar(scenario(), 286, high=12500))
    assert not r.detected
    assert r.metrics["area_range_pct"] > 15
    assert any("주봉이 넓어" in w for w in r.warnings)


def test_heavy_volume_rejected_and_mild_is_caveat():
    heavy = run(scenario(vol_mult=1.6))
    assert not heavy.detected
    assert heavy.metrics["vol_ratio"] > 1.3
    assert any("손바뀜" in w for w in heavy.warnings)
    mild = run(scenario(vol_mult=1.12))
    assert mild.detected, mild.warnings
    assert 1.0 < mild.metrics["vol_ratio"] <= 1.3
    assert any("감소 아님" in w for w in mild.warnings)
