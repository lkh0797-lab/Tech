import numpy as np
import pandas as pd
import pytest

from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.flat_base import FlatBaseConfig, detect, krx_tick
from synthetic import make_context, make_ohlcv, set_bar

# 기본 시나리오: 0~260 Stage 2 상승(4000→10000), 260 좌측 고점, 260~300 플랫 베이스(저점 ~9100, -9~11%)
ADVANCE = [(0, 4000), (150, 6500), (230, 8000), (260, 10000)]
BASE = [(272, 9100), (285, 9800), (293, 9350)]
VOL = [(230, 260, 1.3), (260, 400, 0.6)]


def scenario(last_close: float = 9800, extra: list[tuple[int, float]] | None = None, *, advance=ADVANCE,
             base=BASE, vol=VOL, seed: int = 1, n: int | None = None) -> pd.DataFrame:
    wps = list(advance) + list(base) + [(300, last_close)] + list(extra or [])
    return make_ohlcv(wps, seed=seed, vol_segments=vol, n=n, noise=0.004, wick=0.005)


def run(df, rs=90, **kw):
    return detect(make_context(df, rs=rs, **kw))


def test_krx_tick():
    assert krx_tick(1_500) == 1 and krx_tick(4_990) == 5 and krx_tick(15_000) == 10
    assert krx_tick(30_000) == 50 and krx_tick(150_000) == 100 and krx_tick(300_000) == 500
    assert krx_tick(800_000) == 1_000


# ---------------------------------------------------------------- (a) 교과서적 양성
def test_textbook_flat_base_near_pivot():
    df = scenario(9800)
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT
    assert abs(r.pivot / 10000 - 1) < 0.03
    assert r.stop == pytest.approx(max(r.metrics["base_low"], r.pivot * 0.92))
    assert 25 <= r.metrics["base_bars"] <= 45
    assert 5 <= r.metrics["depth_pct"] <= 15
    assert r.metrics["base_vol_ratio"] < 0.8
    assert r.metrics["prior_advance_pct"] >= 20
    assert r.breakout_date is None and r.end_date == str(df.index[-1].date())
    assert 255 <= df.index.get_loc(pd.Timestamp(r.start_date)) <= 265  # 좌측 고점(260) 부근에서 시작
    assert 0 < r.score <= 100
    kinds = {a["kind"] for a in r.annotations}
    assert {"hline", "box", "segment"} <= kinds
    assert all(s.startswith("✔ ") for s in r.reasons) and all(w.startswith("✘ ") for w in r.warnings)


def test_metrics_are_flat_scalars():
    r = run(scenario(9800))
    for k, v in r.metrics.items():
        assert v is None or isinstance(v, (int, float, str, bool, np.integer, np.floating)), k
    assert r.to_dict()["stage_label"] == "피벗 근접"


# ---------------------------------------------------------------- (b) 단계별
def test_stage_forming():
    r = run(scenario(9350))
    assert r.detected, r.warnings
    assert r.stage == FORMING


def _breakout_df(post: list[tuple[float, float, float, float, float]]):
    """베이스(0~300) 후 301 봉부터 post=(open, high, low, close, volume) 덮어쓰기."""
    df = scenario(9800, n=301 + len(post))
    for k, (o, h, l, c, v) in enumerate(post):
        df = set_bar(df, 301 + k, open=o, high=h, low=l, close=c, volume=v)
    return df


def test_stage_breakout_with_volume():
    df = _breakout_df([(9800, 10500, 9780, 10450, 3e6)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    assert r.breakout_date == str(df.index[-1].date())
    assert r.metrics["breakout_vol_ratio"] >= 1.4
    assert any("돌파 거래량" in s for s in r.reasons)
    assert any(a["kind"] == "marker" for a in r.annotations)


def test_breakout_low_volume_warns():
    df = _breakout_df([(9800, 10500, 9780, 10450, 6e5)])
    r = run(df)
    assert r.detected and r.stage == BREAKOUT
    assert any("돌파 거래량 부족" in w for w in r.warnings)


def test_stage_extended():
    post = [(9800, 10500, 9780, 10450, 3e6), (10450, 10800, 10400, 10750, 2e6),
            (10750, 11200, 10700, 11150, 2e6)]
    r = run(_breakout_df(post))
    assert r.detected, r.warnings
    assert r.stage == EXTENDED


def test_stage_failed():
    post = [(9800, 10500, 9780, 10450, 3e6), (10400, 10450, 9900, 9950, 2e6),
            (9950, 9980, 9550, 9600, 2e6)]
    r = run(_breakout_df(post))
    assert r.detected, r.warnings
    assert r.stage == FAILED


# ---------------------------------------------------------------- (c) 음성
def test_reject_too_deep():
    r = run(scenario(9800, base=[(272, 8000), (285, 9800), (293, 9350)]))
    assert not r.detected


def test_reject_too_short():
    adv = [(0, 4000), (150, 6500), (255, 8000), (285, 10000)]
    r = run(scenario(9800, advance=adv, base=[(292, 9300)]))
    assert not r.detected


def test_reject_no_prior_advance():
    # 완만한 상승(8600→10000, 120봉 내 +18%) 뒤 횡보 → 선행 상승 부족
    adv = [(0, 4000), (100, 8000), (140, 8600), (200, 8900), (260, 10000)]
    r = run(scenario(9800, advance=adv))
    assert not r.detected
    assert any("선행 상승 부족" in w for w in r.warnings)


def test_prior_advance_rule_isolated():
    from chart_screener.config import Config
    cfg = Config(patterns={"flat_base": FlatBaseConfig(min_prior_advance=1.0)})
    r = detect(make_context(scenario(9800), cfg=cfg))
    assert not r.detected
    assert [w for w in r.warnings if "선행 상승 부족" in w]


def test_reject_not_stage2():
    # 1년 가까이 8000 부근 횡보 후 +25% 상승 → 52주 저점 +30% 미달, RS 40 → 트렌드 템플릿 6/8
    adv = [(0, 7800), (200, 8000), (235, 8000), (260, 10000)]
    r = run(scenario(9800, advance=adv), rs=40)
    assert not r.detected
    assert any("Stage 2 미충족" in w for w in r.warnings)
    assert not any("선행 상승 부족" in w for w in r.warnings)


def test_reject_heavy_base_volume():
    r = run(scenario(9800, vol=[(230, 260, 1.0), (260, 400, 2.5)]))
    assert not r.detected
    assert any("베이스 거래량 과다" in w for w in r.warnings)


def test_reject_long_box():
    # 상승 후 150봉 박스권 → 16주 초과 (장기 박스권은 플랫 베이스 아님)
    adv = [(0, 4000), (100, 8000), (140, 10000)]
    base = [(170, 9100), (200, 9800), (230, 9200), (260, 9800), (280, 9200)]
    r = run(scenario(9800, advance=adv, base=base))
    assert not r.detected


def test_right_side_wick_overshoot():
    df = scenario(9800)
    left = float(df["high"].iloc[250:270].max())
    small = run(set_bar(df, 285, high=left * 1.02))       # 장중 +2% 윗꼬리: 피벗만 상향
    assert small.detected and small.pivot == pytest.approx(left * 1.02 + krx_tick(left * 1.02))
    big = run(set_bar(df, 285, high=left * 1.05))          # 장중 +5% 윗꼬리: 베이스 상단 불명확
    assert not big.detected


def test_breakdown_below_base_low_not_detected():
    r = run(scenario(9800, extra=[(301, 9300), (303, 8500)], n=304))
    assert not r.detected


# ---------------------------------------------------------------- 미래 참조 없음: 잘린 데이터 = 그 시점 판정
def test_truncation_consistency():
    df = _breakout_df([(9800, 10500, 9780, 10450, 3e6), (10450, 10600, 10300, 10500, 1.5e6)])
    r_full = run(df)
    r_cut = run(df.iloc[:301])  # 돌파 전날까지
    assert r_cut.detected and r_cut.stage == NEAR_PIVOT and r_cut.breakout_date is None
    assert r_full.pivot == pytest.approx(r_cut.pivot)


def test_halt_date_inside_window_warns():
    df = scenario(9800)
    df.attrs["halt_dates"] = [str(df.index[280].date())]
    r = run(df)
    assert any("거래정지" in w for w in r.warnings)


def test_config_override():
    from chart_screener.config import Config
    cfg = Config(patterns={"flat_base": FlatBaseConfig(min_bars=60)})
    r = detect(make_context(scenario(9800), cfg=cfg))
    assert not r.detected


# ---------------------------------------------------------------- (d) 견고성
@pytest.mark.parametrize("kind", ["short", "flat", "random", "nan", "zero_vol", "const_vol", "zero_price"])
def test_robustness(kind):
    if kind == "short":
        df = make_ohlcv([(0, 100), (59, 120)])
    elif kind == "flat":
        idx = pd.bdate_range("2023-01-02", periods=400)
        df = pd.DataFrame({"open": 1e4, "high": 1e4, "low": 1e4, "close": 1e4, "volume": 1e5}, index=idx)
        df["value"] = df["close"] * df["volume"]
    elif kind == "random":
        rng = np.random.default_rng(7)
        c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.02, 500)))
        df = make_ohlcv([(i, float(x)) for i, x in enumerate(c)], noise=0.0, smooth=False)
    else:
        df = scenario(9800)
        if kind == "nan":
            df.iloc[280, df.columns.get_loc("close")] = np.nan
        elif kind == "zero_vol":
            df["volume"] = 0.0
            df["value"] = 0.0
        elif kind == "const_vol":
            df["volume"] = 1e5
        elif kind == "zero_price":
            df.iloc[-5:, :4] = 0.0
    r = run(df)
    assert isinstance(r.detected, bool)
    if not r.detected:
        assert r.warnings
    if kind in ("short", "flat", "nan", "zero_price"):
        assert not r.detected


def test_random_walks_rarely_detect():
    hits = 0
    for seed in range(20):
        rng = np.random.default_rng(100 + seed)
        c = 10000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 400)))
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


def test_halts_between_merges_zero_volume_bars_and_attrs():
    from chart_screener.patterns.flat_base import halt_mask, halts_between
    df = halt_bars(scenario(9800), 280, 282)
    df.attrs["halt_dates"] = ["2023-01-01", str((df.index[290] + pd.Timedelta(days=1)).date())]
    ctx = make_context(df)
    got = halts_between(ctx, 270, 299)
    assert got[:2] == [str(df.index[280].date()), str(df.index[281].date())] and len(got) == 3
    assert halt_mask(ctx)[280] and not halt_mask(ctx)[279]
    df2 = set_bar(scenario(9800), -1, volume=0)
    ctx2 = make_context(df2)
    ctx2.partial = True                                   # 장중 미완성 마지막 봉의 0 거래량은 정지로 보지 않음
    assert halts_between(ctx2, 290, 299) == []


def test_zero_volume_halt_bars_in_base_rejected():
    # 베이스 안 10봉이 거래정지(거래량 0, O=H=L=C) — attrs['halt_dates'] 없이도 잡아야 함
    r = run(halt_bars(scenario(9800), 270, 280))
    assert not r.detected
    assert any("거래정지" in w and "제외" in w for w in r.warnings)


def test_single_halt_bar_only_warns():
    r = run(halt_bars(scenario(9800), 285, 286))
    assert r.detected, r.warnings
    assert any("거래정지" in w for w in r.warnings)
    assert r.metrics["halt_days"] == 1


def test_nan_volume_not_detected():
    df = scenario(9800)
    df["volume"] = np.nan
    r = run(df)
    assert not r.detected
    assert any("거래량 정보 부족" in w for w in r.warnings)


def test_pinned_price_rejected():
    # 공개매수가 고정: 상승 후 40봉 동안 ±0.5% 안에서만 거래 → 최고 점수가 아니라 제외돼야 함
    df = make_ohlcv(list(ADVANCE) + [(262, 10000), (300, 10040)], seed=1, vol_segments=VOL, noise=0.0015, wick=0.001)
    r = run(df)
    assert not r.detected
    assert r.metrics["depth_pct"] < 5
    assert any("가격 고정" in w for w in r.warnings)


def test_cup_right_side_below_old_high_rejected():
    # 11500 고점 → 7500 (-35%) → 11000 회복(고점 대비 -4%) 후 횡보: 큰 컵의 우측·손잡이이지 플랫 베이스 아님
    adv = [(0, 5000), (150, 11500), (200, 7500), (260, 11000)]
    base = [(272, 10010), (285, 10780), (293, 10285)]
    r = run(scenario(10780, advance=adv, base=base))
    assert not r.detected
    assert any("컵의 우측" in w for w in r.warnings)


def test_far_below_52w_high_rejected():
    adv = [(0, 5000), (120, 14000), (200, 7500), (260, 10000)]
    r = run(scenario(9800, advance=adv))
    assert not r.detected
    assert any("신고가권 베이스 아님" in w for w in r.warnings)


def test_base_volume_above_pre_base_rejected():
    # 베이스 거래량이 직전 50일보다 많음(1.15배) → 매물 출회, ✔ 가 아니라 탈락
    r = run(scenario(9800, vol=[(260, 400, 1.15)]))
    assert not r.detected
    assert 1.0 < r.metrics["base_vol_ratio"] < 1.3
    assert any("베이스 거래량 과다" in w for w in r.warnings)
    assert not any("베이스 거래량" in s for s in r.reasons)


def test_heavy_base_volume_with_right_side_dryup_is_caveat():
    # 베이스 평균 1.1배(좌측 고점 부근 대량 거래)지만 마지막 2주 0.6배로 고갈 → 탈락이 아니라 경고
    r = run(scenario(9800, vol=[(260, 291, 1.25), (291, 400, 0.6)]))
    assert r.detected, r.warnings
    assert 1.0 < r.metrics["base_vol_ratio"] <= 1.2 and r.metrics["right_vol_ratio"] <= 1.0
    assert any("감소 미흡" in w and "고갈" in w for w in r.warnings)
    assert not any("베이스 거래량" in s for s in r.reasons)


def test_very_heavy_base_volume_rejected_even_with_dryup():
    r = run(scenario(9800, vol=[(260, 291, 1.5), (291, 400, 0.6)]))
    assert not r.detected
    assert r.metrics["base_vol_ratio"] > 1.2
    assert any("베이스 거래량 과다" in w for w in r.warnings)


def test_base_volume_mild_decline_is_caveat():
    r = run(scenario(9800, vol=[(260, 400, 0.93)]))
    assert r.detected, r.warnings
    assert 0.85 < r.metrics["base_vol_ratio"] <= 1.0
    assert any("감소 미흡" in w for w in r.warnings)


def test_long_base_after_gradual_advance_detected():
    # 60봉에 걸친 완만한 상승(7800→10000) 뒤 52봉 베이스: 상승 접근 구간은 박스권으로 세지 않음
    adv = [(0, 4000), (150, 6500), (200, 7800), (260, 10000)]
    df = make_ohlcv(adv + [(275, 9200), (290, 9850), (300, 9600), (311, 9750)], seed=0, noise=0.004, wick=0.005,
                    vol_segments=[(230, 260, 1.3), (260, 600, 0.65)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.metrics["base_bars"] >= 50 and not r.metrics["capped"]
    assert r.metrics["box_bars"] <= 80


def test_deep_base_reports_depth():
    # 실제 좌측 고점 대비 17% 조정 → '하락 중 구간'이 아니라 조정폭 초과로 안내
    adv = [(0, 4000), (150, 6500), (230, 8000), (260, 10000)]
    df = make_ohlcv(adv + [(272, 8600), (284, 9850), (292, 9300), (300, 9750)], seed=0, noise=0.006, wick=0.008,
                    vol_segments=[(230, 260, 1.3), (260, 600, 0.65)])
    r = run(df)
    assert not r.detected
    assert any("조정폭" in w and "깊음" in w for w in r.warnings), r.warnings
    assert not any("하락 중" in w for w in r.warnings)


def test_breakout_then_close_below_base_low_invalid():
    post = [(9800, 10500, 9780, 10450, 3e6), (10400, 10400, 9300, 9350, 2e6), (9350, 9360, 8700, 8750, 2e6)]
    df = _breakout_df(post)
    assert float(df["close"].iloc[-1]) < float(df["low"].iloc[260:301].min())
    r = run(df)
    assert not r.detected
    assert r.stage == FAILED
    assert any("베이스 저점" in w and "무효" in w for w in r.warnings)


def test_base_after_pinned_regime_rejected():
    # 공개매수 발표로 급등 후 50봉 가격 고정(일중 폭 0.2%) → 고정 해제 후 횡보: 선행 상승이 추세가 아님
    df = scenario(9800)
    rs = np.random.default_rng(0)
    for i in range(205, 258):
        c = 9300 * (1 + rs.normal(0, 0.0005))
        df.iloc[i, df.columns.get_indexer(["open", "high", "low", "close"])] = [c, c * 1.001, c * 0.999, c]
    from synthetic import add_value
    r = run(add_value(df))
    assert not r.detected
    assert r.metrics["pre_day_range_pct"] < 1
    assert any("가격 고정 국면" in w for w in r.warnings)
