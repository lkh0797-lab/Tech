"""컵 앤 핸들 탐지기 테스트 (합성 데이터)."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.cup_handle import CupHandleConfig, detect
from synthetic import make_context, make_ohlcv, set_bar

# 교과서형: 선행 상승 60→100 (150봉), 컵 150→262 (깊이 ~26%), 핸들 262→280 (깊이 ~7%, 상단 1/3)
PRIOR = [(0, 60), (40, 62), (150, 100)]
CUP = [(180, 80), (200, 74), (225, 76), (262, 98)]
HANDLE = [(270, 92), (280, 95)]
VOL = [(150, 200, 1.2), (200, 230, 0.7), (230, 262, 1.4), (263, 281, 0.5)]


def textbook(extra=(), seed=0, vol=None, noise=0.004, **kw):
    return make_ohlcv(PRIOR + CUP + HANDLE + list(extra), noise=noise, seed=seed,
                      vol_segments=VOL + list(vol or []), **kw)


def run(df, **kw):
    return detect(make_context(df, **kw))


def no_error(r):
    return not any("분석 오류" in w for w in r.warnings)


# ---------------------------------------------------------------- (a) 교과서형
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_textbook_cup_with_handle(seed):
    df = textbook(seed=seed)
    r = run(df)
    assert r.detected, r.warnings
    m = r.metrics
    assert m["variant"] == "cup_handle"
    assert r.stage == NEAR_PIVOT
    assert abs(r.pivot / 98 - 1) < 0.03            # 핸들 고점(오른쪽 립) ≈ 98
    assert 0.22 < m["cup_depth"] < 0.30
    assert 100 <= m["cup_days"] <= 125
    assert 5 <= m["handle_days"] <= 25
    assert m["handle_depth"] < 0.12 and m["handle_position"] > 0.5
    assert m["prior_advance"] > 0.5
    assert m["handle_vol_ratio"] < 1                  # 핸들 거래량 고갈
    assert r.stop == pytest.approx(max(m["stop_handle_low"], m["stop_8pct"]), rel=1e-3)
    assert r.stop < r.pivot
    assert abs(df.index.get_loc(pd.Timestamp(r.start_date)) - 150) <= 12  # 왼쪽 립 ≈ 150봉 (코사인 보간으로 고점 부근 평탄)
    assert r.breakout_date is None and r.end_date is not None
    kinds = [a["kind"] for a in r.annotations]
    assert {"segment", "box", "hline"} <= set(kinds)
    seg = next(a for a in r.annotations if a["kind"] == "segment")
    assert 5 <= len(seg["points"]) <= 9
    assert r.score >= 70
    assert all(x.startswith("✔ ") for x in r.reasons) and all(x.startswith("✘ ") for x in r.warnings)


# ---------------------------------------------------------------- (b) 단계
def test_stage_forming_inside_handle():
    df = make_ohlcv(PRIOR + CUP + [(270, 90), (280, 91)], noise=0.004, seed=1, vol_segments=VOL)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle"
    assert r.stage == FORMING


def test_stage_breakout():
    df = textbook(extra=[(281, 95)])
    df = set_bar(df, -1, open=95.5, high=103.0, low=95.0, close=102.5, volume=4e6)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle"
    assert r.stage == BREAKOUT
    assert r.breakout_date == str(df.index[-1].date())
    assert r.metrics["breakout_vol_ratio"] > 2
    assert any(a["kind"] == "marker" for a in r.annotations)


def test_stage_extended():
    df = textbook(extra=[(281, 102), (295, 112)], vol=[(281, 284, 3.0)])
    r = run(df)
    assert r.detected and r.stage == EXTENDED
    assert r.metrics["bars_since_breakout"] == 14


def test_stage_failed():
    df = textbook(extra=[(281, 102), (283, 103), (290, 93)], vol=[(281, 283, 3.0)])
    r = run(df)
    assert r.detected and r.stage == FAILED, (r.stage, r.metrics)


def test_variant_no_handle():
    df = make_ohlcv(PRIOR + CUP[:-1] + [(265, 99)], noise=0.004, seed=2, vol_segments=VOL[:3])
    r = run(df)
    assert r.detected, r.warnings
    assert r.metrics["variant"] == "cup_no_handle"
    assert abs(r.pivot / 100 - 1) < 0.03            # 피벗 = 왼쪽 립 고가
    assert r.stage in (NEAR_PIVOT, BREAKOUT)


def test_variant_forming():
    df = make_ohlcv(PRIOR + CUP[:-1] + [(250, 90)], noise=0.004, seed=3)
    r = run(df)
    assert r.detected, r.warnings
    assert r.metrics["variant"] == "cup_forming" and r.stage == FORMING
    assert abs(r.pivot / 100 - 1) < 0.03


def test_walk_forward_truncation():
    df = textbook(extra=[(281, 95)])
    df = set_bar(df, -1, open=95.5, high=103.0, low=95.0, close=102.5, volume=4e6)
    seen = {}
    for t in (170, 230, 252, 275, 281):
        r = run(df.iloc[:t + 1])
        seen[t] = (r.detected, r.metrics.get("variant"), r.stage)
    assert not seen[170][0]                          # 왼쪽 하락 중
    assert not seen[230][0]                          # 바닥 근처, 회복 50% 미만
    assert seen[252][:2] == (True, "cup_forming")
    assert seen[275][:2] == (True, "cup_handle")
    assert seen[281] == (True, "cup_handle", BREAKOUT)


# ---------------------------------------------------------------- (c) 부정 사례
def test_reject_sharp_v():
    df = make_ohlcv(PRIOR + [(170, 92), (176, 74), (182, 92), (205, 98), (213, 93), (223, 95)], noise=0.004)
    r = run(df)
    assert not r.detected
    assert no_error(r)


def test_reject_too_deep():
    df = make_ohlcv(PRIOR + [(180, 60), (200, 45), (225, 50), (262, 98)] + HANDLE, noise=0.004)
    assert not run(df).detected


def test_deep_cup_requires_market_correction():
    df = make_ohlcv(PRIOR + [(180, 70), (200, 60), (225, 62), (262, 98)] + HANDLE, noise=0.004)
    r = run(df)                                      # 지수 평탄 → 시장 조정 없음
    assert not r.detected
    idx = make_ohlcv([(0, 1000), (150, 1100), (190, 940), (262, 1080), (280, 1090)], noise=0.001, seed=9)
    r2 = run(df, index_df=idx)
    assert r2.detected and r2.metrics["cup_depth"] > 0.33
    assert any("시장 조정기" in w for w in r2.warnings)


def test_reject_too_shallow():
    df = make_ohlcv(PRIOR + [(180, 96), (200, 94), (225, 95), (262, 99), (270, 96.5), (280, 97.5)], noise=0.003)
    assert not run(df).detected


def test_reject_no_prior_uptrend():
    df = make_ohlcv([(0, 95), (40, 92), (150, 100)] + CUP + HANDLE, noise=0.004)
    r = run(df)
    assert not r.detected
    assert any("선행 상승" in w for w in r.warnings)


def test_reject_handle_too_deep():
    df = make_ohlcv(PRIOR + CUP + [(270, 83), (280, 85)], noise=0.004)
    assert not run(df).detected


def test_reject_handle_in_lower_half():
    df = make_ohlcv(PRIOR + [(180, 88), (200, 84), (225, 85), (262, 99), (272, 90.5), (280, 91)], noise=0.003)
    r = run(df)
    assert not (r.detected and r.metrics["variant"] == "cup_handle")


def test_reject_cup_too_short():
    df = make_ohlcv(PRIOR + [(160, 80), (165, 79), (175, 98), (180, 94), (188, 96)], noise=0.004)
    assert not run(df).detected


def test_reject_handle_too_long():
    df = make_ohlcv(PRIOR + CUP + [(275, 93), (300, 92), (310, 94)], noise=0.004)
    r = run(df)
    assert not r.detected


def test_reject_right_side_not_recovered():
    df = make_ohlcv(PRIOR + [(180, 80), (200, 70), (225, 72), (262, 84), (270, 79), (280, 80)], noise=0.004)
    assert not run(df).detected


def test_reject_stale_breakout():
    df = textbook(extra=[(281, 102), (285, 104), (320, 100)], vol=[(281, 283, 3.0)])
    r = run(df)
    assert not r.detected
    assert any("지난 구조" in w or "경과" in w for w in r.warnings)


def test_spike_left_lip_rejected():
    df = textbook()
    df = set_bar(df, 150, high=125.0)               # 립에 25% 윗꼬리 스파이크
    r = run(df)
    assert not (r.detected and r.metrics["left_lip"] > 110)


# ---------------------------------------------------------------- (d) 견고성
def test_short_history():
    df = make_ohlcv([(0, 100), (59, 110)])
    r = run(df)
    assert not r.detected and r.warnings and no_error(r)


def test_flat_line():
    idx = pd.bdate_range("2023-01-02", periods=400)
    df = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1e6}, index=idx)
    df["value"] = df["close"] * df["volume"]
    r = run(df)
    assert not r.detected and r.warnings and no_error(r)


@pytest.mark.parametrize("seed", range(6))
def test_random_walk(seed):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
    idx = pd.bdate_range("2023-01-02", periods=600)
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                       "volume": rng.lognormal(13, 0.5, 600)}, index=idx)
    df["value"] = df["close"] * df["volume"]
    r = run(df)
    assert no_error(r)
    if r.detected:
        assert r.pivot and r.stop and r.stage


def test_nan_and_zero_volume():
    df = textbook()
    df.iloc[100:103, df.columns.get_loc("close")] = np.nan
    df.iloc[:, df.columns.get_loc("volume")] = 0.0
    df["value"] = 0.0
    r = run(df)
    assert no_error(r)
    assert not any("nan" in w.lower() for w in r.warnings)  # 거래량 비율 NaN 은 'n/a' 로 표기


def test_constant_volume_and_no_index():
    df = textbook()
    df["volume"] = 1e6
    ctx = make_context(df)
    ctx.index_df = None
    ctx.rs_rating, ctx.rs_rating_hist = None, None
    r = detect(ctx)
    assert no_error(r) and r.detected


def test_config_override():
    from chart_screener.config import Config
    cfg = Config(patterns={"cup_handle": CupHandleConfig(min_cup_bars=130)})
    r = detect(make_context(textbook(), cfg=cfg))
    assert not r.detected


def test_registered():
    from chart_screener.patterns.base import REGISTRY
    import chart_screener.patterns.cup_handle  # noqa: F401
    assert REGISTRY["cup_handle"][0] == "컵 앤 핸들"


# ---------------------------------------------------------------- 추가: 사건 우선순위·경고
def test_right_side_poke_above_lip_then_handle():
    """오른쪽이 왼쪽 립을 살짝 넘긴(종가) 뒤 핸들 형성 → 무핸들 돌파가 아닌 컵 앤 핸들로 판정."""
    df = make_ohlcv(PRIOR + [(180, 80), (200, 74), (225, 76), (258, 101.5), (262, 102), (270, 96), (280, 98)],
                    noise=0.003, seed=4, vol_segments=VOL)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle", (r.metrics, r.warnings)
    assert r.metrics["right_lip_ratio"] > 1.0
    assert abs(r.pivot / 102 - 1) < 0.03


def test_halt_date_inside_pattern_warns():
    df = textbook()
    df.attrs["halt_dates"] = [str(df.index[200].date())]
    r = run(df)
    assert r.detected and any("거래정지" in w for w in r.warnings)


def test_partial_breakout_bar_flagged():
    df = textbook(extra=[(281, 95)])
    df = set_bar(df, -1, open=95.5, high=103.0, low=95.0, close=102.5, volume=2e6)
    ctx = make_context(df)
    ctx.partial, ctx.session_frac = True, 0.5          # 장중: 거래량 2배로 환산
    r = detect(ctx)
    assert r.detected and r.stage == BREAKOUT
    assert r.metrics["breakout_vol_ratio"] > 3
    assert any("장중" in w for w in r.warnings)


def test_annotations_well_formed():
    r = run(textbook())
    seg = next(a for a in r.annotations if a["kind"] == "segment")
    dates = [p[0] for p in seg["points"]]
    assert dates == sorted(dates)
    bx = next(a for a in r.annotations if a["kind"] == "box")
    assert bx["start"] < bx["end"] and bx["top"] > bx["bottom"]
    labels = {a.get("label") for a in r.annotations if a["kind"] == "hline"}
    assert {"피벗", "손절"} <= labels
    d = r.to_dict()
    assert d["metrics"]["variant"] == "cup_handle"


# ---------------------------------------------------------------- 리뷰 회귀: 핸들 중 장중 찌르기·동가
def _handle_setup(seed):
    """교과서형 + 핸들 2봉 연장. 282봉 직전까지의 피벗(핸들 고점)과 오른쪽 립 봉을 함께 반환."""
    df = textbook(extra=[(283, 95)], seed=seed)
    pre = run(df.iloc[:282])
    assert pre.detected and pre.metrics["variant"] == "cup_handle"
    rb = df.index.get_loc(pd.Timestamp(next(a for a in pre.annotations if a["kind"] == "box")["start"]))
    return df, pre, rb


def _breakout_bar(df, i, p):
    return set_bar(df, i, open=p * 0.995, high=p * 1.03, low=p * 0.99, close=p * 1.02, volume=4e6)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_intraday_poke_keeps_handle_and_pivot(seed):
    """핸들(6% 눌림) 진행 중 장중 피벗 +1.2% 찌르기 후 종가 피벗 아래 → 핸들·피벗 유지, 다음 봉 핸들 돌파."""
    df, pre, _ = _handle_setup(seed)
    p = pre.pivot
    df = set_bar(df, 282, open=p * 0.985, high=p * 1.012, low=p * 0.98, close=p * 0.99, volume=1.5e6)
    df = _breakout_bar(df, 283, p)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle", (r.metrics, r.warnings)
    assert r.pivot == pytest.approx(p)                      # 피벗은 찌르기 고가가 아닌 핸들 고점
    assert r.stage == BREAKOUT and r.breakout_date == str(df.index[283].date())
    assert r.metrics["handle_pokes"] == 1
    assert any("장중 피벗 상회" in w for w in r.warnings)


@pytest.mark.parametrize("seed", [0, 2])
def test_equal_tick_retest_keeps_handle(seed):
    """핸들 중 고가가 피벗과 같은 봉(동가 재시험)은 핸들을 끊지 않는다."""
    df, pre, rb = _handle_setup(seed)
    p = pre.pivot
    tie = set_bar(df, 282, open=p * 0.985, high=p, low=p * 0.98, close=p * 0.99, volume=1.5e6)
    tie = set_bar(tie, rb + 3, high=p)                     # 핸들 초반(5봉 이전) 동가도 마찬가지
    tie = _breakout_bar(tie, 283, p)
    r = run(tie)
    assert r.detected and r.metrics["variant"] == "cup_handle" and r.stage == BREAKOUT
    assert r.pivot == pytest.approx(p) and r.metrics["handle_pokes"] == 0
    assert r.metrics["handle_days"] == 283 - 1 - rb


def test_new_high_before_pullback_restarts_handle():
    """눌림 전(오른쪽 립 직후)의 소폭 신고가는 찌르기가 아니라 새 오른쪽 립 → 피벗 = 그 고가."""
    df, pre, rb = _handle_setup(0)
    p = pre.pivot
    d = set_bar(df.iloc[:282], rb + 1, high=p * 1.008, close=min(float(df["close"].iloc[rb + 1]), p * 0.995))
    r = run(d)
    assert r.detected and r.metrics["variant"] == "cup_handle"
    assert r.pivot == pytest.approx(p * 1.008)
    assert r.metrics["handle_days"] == pre.metrics["handle_days"] - 1


def _lip_cross_inside_handle(seed, after):
    """오른쪽 립 고가를 왼쪽 립 +1% 로 올린 뒤, 유효 핸들 중(277봉) 왼쪽 립 위·핸들 피벗 아래 종가."""
    df = make_ohlcv(PRIOR + CUP + [(270, 94), (276, 96), (277 + after, 96)], noise=0.004, seed=seed, vol_segments=VOL)
    pre = run(df.iloc[:277])
    lip = pre.metrics["left_lip"]
    rb = df.index.get_loc(pd.Timestamp(next(a for a in pre.annotations if a["kind"] == "box")["start"]))
    df = set_bar(df, rb, high=lip * 1.01)
    df = set_bar(df, 277, open=lip * 0.99, high=lip * 1.006, low=lip * 0.985, close=lip * 1.004, volume=4e6)
    for i in range(278, 278 + after):
        df = set_bar(df, i, open=lip * 0.995, high=lip * 1.003, low=lip * 0.985, close=lip * 0.996, volume=8e5)
    return df, lip


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_close_above_left_lip_below_handle_pivot_is_not_breakout(seed):
    """핸들 진행 중 '왼쪽 립 < 종가 ≤ 핸들 피벗' 은 무핸들 돌파가 아니다 (피벗은 핸들 고점)."""
    df, lip = _lip_cross_inside_handle(seed, after=0)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle" and r.breakout_date is None
    assert r.pivot == pytest.approx(lip * 1.01)
    df2, _ = _lip_cross_inside_handle(seed, after=12)      # 이후 핸들이 25봉을 넘겨도 무핸들 돌파로 둔갑하지 않음
    r2 = run(df2)
    assert not (r2.detected and r2.metrics["variant"] == "cup_no_handle")


# ---------------------------------------------------------------- 리뷰 회귀: V/L자 오른쪽
def _flat_bottom(seed):
    return make_ohlcv(PRIOR + [(170, 84), (185, 78), (215, 77)], noise=0.004, seed=seed)


def _append(df, k):
    out = pd.concat([df, df.iloc[-k:]])
    out.index = pd.bdate_range(df.index[0], periods=len(out))
    return out


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_reject_l_shape_spike_then_pause(seed):
    """직선 하락 + 평평한 바닥 + 하루 +26% 급등(립 97%) + 6봉 쉬기 + 돌파 → U자 아님."""
    base = _flat_bottom(seed)
    n0 = len(base)
    df = _append(base, 8)
    df = set_bar(df, n0, open=77.5, high=97.0, low=77.5, close=96.5, volume=2e7)
    for i, cl in enumerate([95.0, 93.5, 92.0, 93.0, 92.5, 93.5]):
        df = set_bar(df, n0 + 1 + i, open=cl + 0.3, high=cl + 1.0, low=cl - 0.8, close=cl, volume=3e5)
    df = set_bar(df, n0 + 7, open=94, high=98.5, low=93.8, close=98.2, volume=5e6)
    r = run(df)
    assert not r.detected
    assert any("스파이크" in w or "급등" in w for w in r.warnings)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_reject_limit_up_days_through_lip(seed):
    """평평한 바닥에서 상한가 2일로 립을 뚫음 → 립 부근 체류 없는 수직 돌파 (무핸들 돌파 아님)."""
    df = _append(_flat_bottom(seed), 2)
    df = set_bar(df, len(df) - 2, open=77.5, high=100.0, low=77.5, close=100.0, volume=2e7)
    df = set_bar(df, len(df) - 1, open=104, high=106, low=103, close=105, volume=3e7)
    r = run(df)
    assert not r.detected
    assert any("수직" in w for w in r.warnings)
    held = _append(df, 4)                                  # 뚫은 뒤 립 위에서 4일 버텨도 '립 부근 체류'로 치지 않음
    for i in range(len(df), len(held)):
        held = set_bar(held, i, open=104, high=105.5, low=103, close=104.5, volume=5e6)
    r2 = run(held)
    assert not (r2.detected and r2.metrics["variant"] == "cup_no_handle" and r2.breakout_date)


_CORR_IDX = make_ohlcv([(0, 1000), (150, 1100), (190, 940), (262, 1080), (300, 1090)], noise=0.001, seed=9)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_reject_deep_cup_vertical_right_leg(seed):
    """깊은 컵(약 40%, 시장 조정기)에서 10봉 만에 +35% 로 립에 붙는 오른쪽 → 범위 60%↑ & +25%↑ 결합 규칙 탈락."""
    from chart_screener.config import Config
    df = make_ohlcv(PRIOR + [(175, 75), (190, 61), (235, 62), (245, 95), (253, 90), (260, 92)], noise=0.003, seed=seed)
    idx = _CORR_IDX.iloc[:len(df)]
    r = run(df, index_df=idx)
    assert not r.detected
    assert any("오른쪽 급등" in w for w in r.warnings)
    loose = Config(patterns={"cup_handle": CupHandleConfig(steep_right_thrust=9.0)})
    r2 = detect(make_context(df, index_df=idx, cfg=loose))   # 결합 규칙만 끄면 탐지 → 이 규칙이 원인
    assert r2.detected and 0.6 < r2.metrics["right_thrust"] < 0.75 and r2.metrics["right_thrust_pct"] > 0.25


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_deep_cup_gradual_right_side_detected(seed):
    """대조군: 같은 깊이·바닥이라도 오른쪽이 35봉에 걸쳐 오르면 정상 탐지."""
    df = make_ohlcv(PRIOR + [(175, 80), (190, 71), (215, 72), (250, 94), (258, 89), (265, 91)], noise=0.003, seed=seed)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle"
    assert r.metrics["right_thrust"] < 0.4


# ---------------------------------------------------------------- 리뷰 회귀: 왼쪽 립 = 상승의 꼭지
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_reject_lower_high_lip(seed):
    """110 고점 → 80 조정 → 100 되돌림 고점(립 후보) → 컵: 되돌림 고점은 립이 될 수 없다."""
    from chart_screener.patterns import cup_handle as ch
    df = make_ohlcv([(0, 60), (40, 62), (120, 110), (160, 80), (190, 100), (215, 84), (235, 78), (255, 80),
                     (280, 98), (288, 93), (296, 95)], noise=0.003, seed=seed)
    r = run(df)
    assert not r.detected                                  # 110 고점 기준으로는 W자 → 컵 앤 핸들 아님
    ctx = make_context(df)
    cfg = CupHandleConfig()
    arr = ch._prep(ctx)
    atrp = (ctx.atr(14) / ctx.close).fillna(0).to_numpy()
    a = 170 + int(np.argmax(arr[0][170:210]))               # 되돌림 고점(≈100)
    out = ch._evaluate_lip(ctx, cfg, arr, a, np.full(len(df), 0.12), np.maximum(0.02, atrp))
    assert isinstance(out, tuple) and "되돌림" in out[1]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_prior_advance_measured_after_last_higher_close(seed):
    """1년 전 저점(70)이 아니라 립보다 높았던 마지막 종가(115 고점 이후) 뒤 저점(88)에서 선행 상승 측정."""
    df = make_ohlcv([(0, 70), (20, 115), (45, 92), (140, 88), (170, 100), (195, 82), (215, 76), (240, 78),
                     (277, 98), (285, 92), (295, 95)], noise=0.003, seed=seed)
    r = run(df)
    assert not r.detected
    assert any("선행 상승" in w for w in r.warnings)


# ---------------------------------------------------------------- 리뷰 회귀: W자 바닥
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_reject_w_shaped_base(seed):
    df = make_ohlcv(PRIOR + [(170, 86), (185, 75), (200, 90), (215, 75), (240, 86), (262, 98)] + HANDLE,
                    noise=0.003, seed=seed)
    r = run(df)
    assert not r.detected
    assert any("W자" in w for w in r.warnings)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_mild_bump_in_bottom_still_cup(seed):
    df = make_ohlcv(PRIOR + [(170, 86), (185, 75), (200, 80), (215, 75), (240, 86), (262, 98)] + HANDLE,
                    noise=0.003, seed=seed)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle"
    assert r.metrics["w_rally"] < 0.35


# ---------------------------------------------------------------- 리뷰 회귀: 돌파 거래량
def test_low_volume_breakout_is_unconfirmed():
    df = textbook(extra=[(281, 95)])
    df = set_bar(df, -1, open=95.5, high=103.0, low=95.0, close=102.5, volume=1.0e6)   # 50일 평균의 ~0.9배
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle"
    assert r.stage == NEAR_PIVOT and r.breakout_date is None
    assert r.metrics["unconfirmed_breakout"] == str(df.index[-1].date())
    assert any("미확인 돌파" in w for w in r.warnings)
    bv = r.metrics["breakout_vol_ratio"]
    msg = next(w for w in r.warnings if "거래량 부족" in w)
    assert f"{bv:.2f}배 < 1.40배" in msg                  # '1.4배 < 1.4배' 같은 자기모순 표기 금지


def test_low_volume_run_above_buy_range_is_extended_without_breakout_date():
    df = textbook(extra=[(281, 95), (283, 95)])
    p = run(df.iloc[:281]).pivot
    for i, k in ((281, 1.025), (282, 1.055), (283, 1.08)):
        df = set_bar(df, i, open=p * (k - 0.02), high=p * (k + 0.01), low=p * (k - 0.03), close=p * k, volume=1.0e6)
    r = run(df)
    assert r.detected and r.stage == EXTENDED
    assert r.breakout_date is None and r.metrics["unconfirmed_breakout"] == str(df.index[281].date())


# ---------------------------------------------------------------- 리뷰 회귀: 무핸들 돌파 후 늦게 생긴 핸들
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_handle_long_after_no_handle_crossing(seed):
    """오른쪽이 립을 넘은 뒤 20봉가량 립 +3~4% 까지 완만히 오른 다음 핸들 → 지난 구조가 아니라 컵 앤 핸들."""
    wp = PRIOR + [(180, 80), (200, 74), (225, 76), (252, 100.5), (258, 101.5), (276, 103.8), (281, 98), (286, 99.5)]
    df = make_ohlcv(wp, noise=0.002, wick=0.004, seed=seed)
    r = run(df)
    assert r.detected and r.metrics["variant"] == "cup_handle", r.warnings
    assert r.metrics["right_lip_ratio"] > 1.0


# ---------------------------------------------------------------- 리뷰 회귀: 후보 선택의 결정성
def _fake(score, m, lip, a, bo, base):
    from chart_screener.patterns.base import PatternResult
    return PatternResult(name="cup_handle", label="", detected=True, score=score), dict(
        m=m, lip=lip, a=a, bo=bo, base_score=base)


def test_select_same_cup_low_prefers_highest_lip():
    from chart_screener.patterns.cup_handle import _select
    hi, lo = _fake(60, 200, 105.0, 150, None, 60), _fake(80, 200, 100.0, 170, None, 80)
    assert _select([lo, hi])[1]["lip"] == 105.0             # 점수가 낮아도 같은 컵 저점이면 높은 립


def test_select_same_breakout_uses_stage_free_score():
    from chart_screener.patterns.cup_handle import _select
    a = _fake(90, 210, 105.0, 150, 290, 80)                 # 단계 조정 후 점수는 높지만 구조 점수는 낮음
    b = _fake(70, 230, 100.0, 190, 290, 95)                 # 이격 과다(−5)·실패 등으로 낮아졌어도 구조 점수 우위
    assert _select([a, b])[1]["lip"] == 100.0
    c = _fake(99, 240, 101.0, 200, None, 99)                # 다른 베이스(진행 중)는 최종 점수로 비교
    assert _select([a, b, c])[1]["lip"] == 101.0


def test_breakout_pivot_stable_in_walk_forward():
    """같은 돌파를 이후 날짜에서 다시 평가해도 피벗·돌파일이 바뀌지 않는다."""
    df = textbook(extra=[(281, 95), (286, 104)], vol=[(281, 287, 3.0)])
    df = set_bar(df, 281, open=95.5, high=103.0, low=95.0, close=102.5, volume=4e6)
    seen = {(r.pivot, r.breakout_date) for r in (run(df.iloc[:t + 1]) for t in range(281, 287))}
    assert len(seen) == 1 and next(iter(seen))[1] == str(df.index[281].date())
