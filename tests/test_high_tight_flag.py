import numpy as np
import pandas as pd
import pytest

from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.high_tight_flag import HighTightFlagConfig, detect
from synthetic import make_context, make_ohlcv, set_bar

# 기본 시나리오: 0~200 바닥(10000 부근) → 200~230 깃대(+110%) → 230~250 깃발(-12% 내외)
BASE = [(0, 9500), (120, 10300), (200, 10000)]
POLE = [(230, 21000)]
FLAG = [(238, 18600), (245, 19900)]
VOL = [(200, 231, 3.0), (231, 400, 0.8)]


def scenario(last_close: float = 19500, *, base=BASE, pole=POLE, flag=FLAG, vol=VOL, n=None, seed=2):
    wps = list(base) + list(pole) + list(flag) + [(250, last_close)]
    return make_ohlcv(wps, seed=seed, vol_segments=vol, n=n, noise=0.004, wick=0.005)


def run(df, rs=95, **kw):
    return detect(make_context(df, rs=rs, **kw))


def _post(df, bars):
    for k, (o, h, l, c, v) in enumerate(bars):
        df = set_bar(df, 251 + k, open=o, high=h, low=l, close=c, volume=v)
    return df


# ---------------------------------------------------------------- (a) 교과서적 양성
def test_textbook_htf_forming():
    df = scenario(19500)
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == FORMING
    assert abs(r.pivot / 21000 - 1) < 0.03
    m = r.metrics
    assert m["pole_gain_pct"] >= 100 and m["pole_close_gain_pct"] >= 90
    assert 25 <= m["pole_bars"] <= 40
    assert 15 <= m["flag_bars"] <= 25
    assert 8 <= m["flag_depth_pct"] <= 20
    assert m["flag_vol_ratio"] < 0.5 and m["pole_vol_mult"] > 2
    assert r.stop == pytest.approx(max(m["flag_low"], r.pivot * 0.92))
    assert r.end_date == str(df.index[-1].date()) and r.breakout_date is None
    assert {"hline", "segment", "box"} <= {a["kind"] for a in r.annotations}
    assert all(s.startswith("✔ ") for s in r.reasons) and all(w.startswith("✘ ") for w in r.warnings)
    assert 0 < r.score <= 100


# ---------------------------------------------------------------- (b) 단계별
def test_stage_near_pivot():
    r = run(scenario(20400))
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT


def test_stage_breakout():
    df = _post(scenario(20400, n=252), [(20500, 22000, 20400, 21900, 6e6)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT and r.breakout_date == str(df.index[-1].date())
    assert r.metrics["breakout_vol_ratio"] >= 1.4


def test_stage_extended():
    df = _post(scenario(20400, n=254), [(20500, 22000, 20400, 21900, 6e6), (21900, 23000, 21800, 22900, 4e6),
                                        (22900, 24000, 22800, 23800, 4e6)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == EXTENDED


def test_stage_failed():
    df = _post(scenario(20400, n=254), [(20500, 22000, 20400, 21900, 6e6), (21800, 21900, 20500, 20600, 3e6),
                                        (20600, 20700, 19800, 19900, 3e6)])
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == FAILED


# ---------------------------------------------------------------- (c) 음성
def test_reject_small_pole():
    r = run(scenario(15600 * 0.93, pole=[(230, 16000)], flag=[(238, 14500), (245, 15500)]))
    assert not r.detected


def test_reject_slow_pole():
    # 120봉에 걸친 +110% (8주 이내 아님)
    r = run(scenario(19500, base=[(0, 9500), (80, 10000)], pole=[(230, 21000)]))
    assert not r.detected


def test_reject_deep_flag():
    r = run(scenario(16000, flag=[(238, 14200), (245, 15800)]))
    assert not r.detected


def test_reject_long_flag():
    # 깃발 45봉 (5주 초과)
    df = make_ohlcv(BASE + POLE + [(245, 18600), (260, 19900), (275, 19500)], seed=2, noise=0.004, wick=0.005,
                    vol_segments=[(200, 231, 3.0), (231, 400, 0.8)])
    assert not run(df).detected


def test_reject_heavy_flag_volume():
    r = run(scenario(19500, vol=[(200, 231, 1.6), (231, 400, 2.5)]))
    assert not r.detected
    assert any("깃발 거래량" in w for w in r.warnings)


def test_reject_weak_pole_volume():
    r = run(scenario(19500, vol=[(231, 400, 0.5)]))
    assert not r.detected
    assert any("깃대 구간 거래량" in w for w in r.warnings)


def test_reject_two_leg_pole():
    # 깃대 중간 22% 되돌림 (10000→16000→12500→21000)
    r = run(scenario(19500, pole=[(212, 16000), (218, 12500), (230, 21000)]))
    assert not r.detected
    assert any("되돌림" in w for w in r.warnings)


def test_reject_v_recovery():
    # 20000 → 10000 급락 후 21000 회복: 직전 고점 대비 순상승 미미
    base = [(0, 15000), (150, 20000), (185, 10000), (200, 10000)]
    r = run(scenario(19500, base=base))
    assert not r.detected
    assert any("V자" in w or "최고가 아님" in w for w in r.warnings)


def test_reject_wick_made_pole():
    # 종가는 +65% 뿐이고 장중 윗꼬리 한 번으로 +95%
    df = scenario(15800, pole=[(230, 16500)], flag=[(238, 15600), (245, 16000)])
    df = set_bar(df, 230, high=19500)
    r = run(df)
    assert not r.detected
    assert any("윗꼬리" in w for w in r.warnings)


def test_reject_halt_inside_pole():
    df = scenario(19500)
    df.attrs["halt_dates"] = [str(df.index[215].date())]
    r = run(df)
    assert not r.detected
    assert any("거래정지" in w for w in r.warnings)


def test_reject_price_limit_violation():
    # 215봉 이전 가격이 미수정(1/1.4 수준) → 215봉에서 하루 +40% 는 가격제한폭 초과 → 왜곡 의심
    df = scenario(19500)
    df.iloc[:215, :4] /= 1.4
    df["value"] = df[["high", "low", "close"]].mean(axis=1) * df["volume"]
    r = run(df)
    assert not r.detected
    assert any("가격제한폭" in w for w in r.warnings)


def test_pole_still_running_no_flag():
    r = run(scenario(21000, flag=[], pole=[(250, 21000)]))
    assert not r.detected
    assert any("깃발 미형성" in w for w in r.warnings)


# ---------------------------------------------------------------- 미래 참조 없음
def test_truncation_consistency():
    df = _post(scenario(20400, n=253), [(20500, 22000, 20400, 21900, 6e6), (21900, 22300, 21700, 22100, 3e6)])
    cut = run(df.iloc[:251])
    full = run(df)
    assert cut.detected and cut.stage == NEAR_PIVOT and cut.breakout_date is None
    assert full.detected and full.stage == BREAKOUT
    assert full.pivot == pytest.approx(cut.pivot)


def test_new_listing_short_history():
    # 상장 80일차 신규주: 깃대 이전 이력 부족 → 경고만 남기고 판정
    df = make_ohlcv([(0, 10000), (10, 9600), (40, 20500), (48, 18300), (60, 19600), (70, 19300)], seed=3,
                    noise=0.004, wick=0.005, vol_segments=[(10, 41, 3.0), (41, 100, 0.7)])
    r = run(df)
    assert isinstance(r.detected, bool)
    assert r.warnings or r.reasons


def test_config_override():
    from chart_screener.config import Config
    cfg = Config(patterns={"high_tight_flag": HighTightFlagConfig(min_pole_gain=1.5)})
    assert not detect(make_context(scenario(19500), cfg=cfg)).detected


# ---------------------------------------------------------------- (d) 견고성
@pytest.mark.parametrize("kind", ["tiny", "short", "flat", "random", "nan", "zero_vol", "zero_price"])
def test_robustness(kind):
    if kind == "tiny":
        df = make_ohlcv([(0, 100), (20, 120)])
    elif kind == "short":
        df = make_ohlcv([(0, 100), (59, 120)])
    elif kind == "flat":
        idx = pd.bdate_range("2023-01-02", periods=300)
        df = pd.DataFrame({"open": 1e4, "high": 1e4, "low": 1e4, "close": 1e4, "volume": 1e5}, index=idx)
        df["value"] = df["close"] * df["volume"]
    elif kind == "random":
        rng = np.random.default_rng(11)
        c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.03, 400)))
        df = make_ohlcv([(i, float(x)) for i, x in enumerate(c)], noise=0.0, smooth=False)
    else:
        df = scenario(19500)
        if kind == "nan":
            df.iloc[240, df.columns.get_loc("low")] = np.nan
        elif kind == "zero_vol":
            df["volume"] = 0.0
            df["value"] = 0.0
        elif kind == "zero_price":
            df.iloc[-3:, :4] = 0.0
    r = run(df)
    assert isinstance(r.detected, bool)
    if not r.detected:
        assert r.warnings
    if kind in ("tiny", "flat", "nan", "zero_vol", "zero_price"):
        assert not r.detected


def test_random_walks_rarely_detect():
    hits = 0
    for seed in range(30):
        rng = np.random.default_rng(500 + seed)
        c = 10000 * np.exp(np.cumsum(rng.normal(0.001, 0.03, 300)))
        df = make_ohlcv([(i, float(x)) for i, x in enumerate(c)], noise=0.0, smooth=False, seed=seed)
        hits += run(df).detected
    assert hits <= 2


# ---------------------------------------------------------------- 리뷰 회귀 테스트
def _late_volume(df, v, k=5, end=250):
    for i in range(end - k + 1, end + 1):
        df = set_bar(df, i, volume=v)
    return df


def test_reject_late_flag_volume_surge():
    # 깃발 평균은 깃대의 0.45배지만 마지막 5봉이 깃대 수준(약 3e6) → 고갈 아님
    r = run(_late_volume(scenario(19500), 3e6))
    assert not r.detected
    assert r.metrics["flag_vol_ratio"] <= 0.8 and r.metrics["late_flag_vol_ratio"] > 0.8
    assert any("후반 거래량 재증가" in w for w in r.warnings)


def test_late_flag_volume_caveat_and_score():
    base = run(scenario(19500))
    mild = run(_late_volume(scenario(19500), 2.1e6))      # 깃대 대비 약 0.7배, 깃대 이전 평균의 2.1배
    assert mild.detected, mild.warnings
    assert 0.6 < mild.metrics["late_flag_vol_ratio"] <= 0.8
    assert any("고갈 미흡" in w for w in mild.warnings)
    assert any("아직 거래 과열" in w for w in mild.warnings)
    assert mild.score < base.score


def test_reject_zero_volume_halt_in_flag():
    # attrs['halt_dates'] 없이 거래량 0·O=H=L=C 봉으로만 남은 거래정지
    df = scenario(19500)
    c = float(df["close"].iloc[239])
    for i in range(240, 243):
        df = set_bar(df, i, open=c, high=c, low=c, close=c, volume=0)
    r = run(df)
    assert not r.detected
    assert any("거래정지" in w for w in r.warnings)
