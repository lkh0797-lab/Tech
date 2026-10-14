"""차트 발굴 기법 공용 부품(chart_screener/techniques.py) — 합성 봉으로 경계 · 미래 금지(앞부분 불변) · '모름' 처리.

부록 docs/2026-10-14-chart-techniques-addendum.md §13 의 공용 부품 몫 (스윙 · 월봉 · 피보 · 추세선 · 망치 · 장대양봉 ·
5일 거래량 이평 · 청산 · 체크리스트 · 시장 맥락)."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from chart_screener import techniques as tq
from chart_screener.market import CORRECTION, PRESSURE
from synthetic import confirmed_market, make_context, make_ohlcv


# ---------------------------------------------------------------- 도우미
def _bars(o, h, lo, c, v=None, start="2024-01-02"):
    n = len(c)
    return tq.Bars.from_arrays(o, h, lo, c, np.full(n, 1e6) if v is None else v, pd.bdate_range(start, periods=n))


def _flat_bars(closes, rng=2.0, v=None, start="2024-01-02"):
    """시가 = 종가, 고가 = 종가 + rng/2, 저가 = 종가 − rng/2."""
    c = np.asarray(closes, dtype=float)
    return _bars(c.copy(), c + rng / 2, c - rng / 2, c, v, start)


def _junk_future(b: tq.Bars, t: int, seed: int = 0) -> tq.Bars:
    """봉 t 뒤를 엉뚱한 봉으로 바꾼다 — 앞부분 불변 시험용."""
    rng = np.random.default_rng(seed)
    o, h, lo, c, v = (x.copy() for x in (b.open, b.high, b.low, b.close, b.volume))
    k = b.n - t - 1
    if k > 0:
        c[t + 1:] = b.close[t] * rng.uniform(0.3, 3.0, k)
        o[t + 1:] = c[t + 1:] * rng.uniform(0.8, 1.2, k)
        h[t + 1:] = np.maximum(o[t + 1:], c[t + 1:]) * 1.2
        lo[t + 1:] = np.minimum(o[t + 1:], c[t + 1:]) * 0.8
        v[t + 1:] = rng.uniform(1e3, 1e9, k)
    return tq.Bars(o, h, lo, c, v, b.dates)


def _rand_bars(seed=3):
    return tq.Bars.from_df(make_ohlcv([(0, 100), (150, 60), (300, 90), (420, 70)], seed=seed, noise=0.012))


# ---------------------------------------------------------------- 이평 · 거래량
def test_prior_mean_excludes_today_and_vol_ma5_includes_today():
    v = np.r_[np.full(49, 1e6), 1e9, 1e6]
    r = tq.vol_ratio(v, 49)
    assert r[49] == pytest.approx(1000.0)            # 기준선에 당일 거대 거래량이 안 들어감
    assert tq.prior_mean(v, 49)[50] > 1e6            # 다음 날 기준선에는 들어감
    m5 = tq.vol_ma(v, 5)
    assert m5[49] == pytest.approx(np.mean(v[45:50]))
    assert np.isnan(m5[3])


def test_prior_mean_skips_zero_volume_rows_when_volume_given():
    # 부록 §0.2: 거래량 0(정지) 행은 평균에서 뺀다 — 직전 '거래 봉' n개 평균, 당일 제외
    v = np.r_[np.full(10, 1e6), 0.0, 1e6, 0.0, 4e6]
    x = np.arange(len(v), dtype=float)
    pm = tq.prior_mean(x, 3, volume=v)
    assert pm[13] == pytest.approx(np.mean([8.0, 9.0, 11.0]))          # 10 · 12 (정지) 건너뜀
    assert pm[12] == pytest.approx(np.mean([8.0, 9.0, 11.0]))          # 정지 봉 자신도 같은 기준선
    assert np.isnan(tq.prior_mean(x[:4], 3, volume=np.r_[0.0, 0.0, 1e6, 1e6])[3])   # 거래 봉 2개뿐 → NaN
    assert tq.vol_ratio(v, 3)[13] == pytest.approx(4.0)                # 0 행이 부풀리지 않음
    assert tq.prior_mean(v, 3)[13] < 1e6                               # volume 없이 부르면 예전 그대로(0 포함)
    w = np.r_[np.full(49, 1e6), 1e9, 1e6, 3e6]                         # 0 행 없음 → volume 줘도 똑같다
    np.testing.assert_array_equal(tq.prior_mean(w, 20, volume=w), tq.prior_mean(w, 20))
    for t in range(len(v)):                                            # 앞부분 불변
        np.testing.assert_array_equal(tq.prior_mean(x[:t + 1], 3, volume=v[:t + 1]), pm[:t + 1])


def test_public_comparators_share_core_boundaries():
    assert tq.ge is tq._ge and tq.le is tq._le and tq.gt is tq._gt and tq.lt is tq._lt
    assert bool(tq.ge(1.0 - 5e-10, 1.0)) and not bool(tq.gt(1.0 + 5e-10, 1.0))


def test_cross_above_previous_equal_counts_today_equal_does_not():
    x, ref = [1.0, 2.0, 3.0, 2.5], [1.0, 2.0, 2.5, 2.5]
    assert not tq.cross_above(x, ref, 1)              # 오늘 같음 → 돌파 아님
    assert tq.cross_above(x, ref, 2)                  # 어제 같음(≤) → 돌파
    assert not tq.cross_above(x, ref, 3)
    assert not tq.cross_above(x, ref, 0)


def test_ma_snapshot_names_and_unknown():
    c = np.linspace(100, 150, 100)
    s = tq.ma_snapshot(c, 99)
    assert s[60]["name"] == "60일선(수급선)" and s[120]["name"] == "120일선(경기선)" and s[20]["name"] == "20일선(생명선)"
    assert s[20]["above"] is True
    assert s[120]["value"] is None and s[120]["above"] is None     # 이력 부족 = 모름


def test_count_up_and_streak():
    c = [10, 11, 12, 11, 12, 13, 14, 15]
    assert tq.up_streak(c, 7) == 4
    assert tq.count_up(c, 7, 5) == 4


# ---------------------------------------------------------------- 스윙
def test_swing_high_needs_k_bars_and_confirm_index():
    h = [1, 2, 3, 10, 3, 2, 1, 1, 1]
    s = tq.swing_highs(h, k=3)
    assert [(x.i, x.confirm_i) for x in s] == [(3, 6)]
    assert tq.swing_highs(h[:6], k=3) == []           # 오른쪽 2봉뿐 → 아직 확정 아님
    assert tq.swing_highs(h[:7], k=3)[0].i == 3


def test_swing_tie_later_bar_wins_and_fractal2_strict():
    h = [1, 2, 3, 10, 10, 3, 2, 1, 0]
    assert [x.i for x in tq.swing_highs(h, k=3)] == [4]          # 부록 식: 왼쪽 같음 허용 · 오른쪽 엄격
    assert tq.swing_highs(h, k=2, strict_left=True) == []         # fractal2 는 양쪽 엄격
    lo = [5, 4, 3, 1, 3, 4, 5, 6]
    assert [(x.i, x.kind, x.confirm_i) for x in tq.swing_lows(lo, k=3)] == [(3, "L", 6)]


def test_swings_prefix_invariant():
    b = _rand_bars()
    full_h, full_l = tq.swing_highs(b.high), tq.swing_lows(b.low)
    assert full_h and full_l
    for T in range(10, b.n, 7):
        assert tq.swing_highs(b.high[:T]) == tq.swings_known_at(full_h, T - 1)
        assert tq.swing_lows(b.low[:T]) == tq.swings_known_at(full_l, T - 1)


# ---------------------------------------------------------------- 월봉 · 주봉
def _daily(start="2024-01-02", end="2024-05-20"):
    idx = pd.bdate_range(start, end)
    i = np.arange(len(idx), dtype=float)
    return pd.DataFrame({"open": 100 + i, "high": 101.5 + i, "low": 99 + i, "close": 100.5 + i,
                         "volume": 1000 + i}, index=idx)


def test_monthly_aggregation_and_partial_month():
    df = _daily()
    m = tq.monthly_bars(df)
    jan = df.loc["2024-01"]
    r = m.loc[pd.Period("2024-01", "M")]
    assert (r.open, r.high, r.low, r.close) == (jan.open.iloc[0], jan.high.max(), jan.low.min(), jan.close.iloc[-1])
    assert r.volume == jan.volume.sum() and r.v_avg == pytest.approx(jan.volume.mean()) and r.days == len(jan)
    assert m["complete"].tolist() == [True, True, True, True, False]    # 진행 중 달(5월)은 미완성


def test_month_end_eod_is_still_partial_unless_calendar_rule():
    df = _daily().loc[:"2024-01-31"]
    assert not tq.monthly_bars(df)["complete"].iloc[-1]                  # 다음 달 봉이 와야 확정
    assert tq.monthly_bars(df, complete_rule="calendar")["complete"].iloc[-1]
    assert not tq.monthly_bars(df.loc[:"2024-01-30"], complete_rule="calendar")["complete"].iloc[-1]


def test_calendar_rule_weekend_month_end_no_deprecation_warning():
    # 2024-03-31 은 일요일 — _last_session 이 하루씩 거슬러 감(예전 pd.Timedelta(days=1) 은 pandas 2.3 · numpy 2.5 경고)
    import warnings
    df = _daily(end="2024-04-03")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert tq._last_session(pd.Period("2024-03", "M")) == pd.Timestamp("2024-03-29")
        m = tq.monthly_bars(df.loc[:"2024-03-29"], complete_rule="calendar")
        assert m["complete"].iloc[-1]                                  # 3월 마지막 거래일(금) EOD 에 완성
        assert not tq.monthly_bars(df.loc[:"2024-03-28"], complete_rule="calendar")["complete"].iloc[-1]


def test_monthly_zero_volume_row_dropped():
    df = _daily()
    d0 = df.loc["2024-02"].index[0]
    df.loc[d0, ["open", "low", "volume"]] = [50.0, 40.0, 0.0]
    m = tq.monthly_bars(df).loc[pd.Period("2024-02", "M")]
    assert m.open == df.loc["2024-02"].open.iloc[1] and m.low > 40
    raw = tq.monthly_bars(df, drop_zero_volume=False).loc[pd.Period("2024-02", "M")]
    assert raw.open == 50.0 and raw.low == 40.0


def test_monthly_gap_before_missing_month():
    df = _daily()
    df = df[~df.index.to_period("M").isin([pd.Period("2024-04", "M")])]
    m = tq.monthly_bars(df)
    assert m.loc[pd.Period("2024-05", "M"), "gap_before"] and not m.loc[pd.Period("2024-03", "M"), "gap_before"]


def test_monthly_prefix_invariant():
    df = _daily()
    full = tq.monthly_bars(df)
    for T in range(5, len(df), 6):
        part = tq.monthly_bars(df.iloc[:T])
        done = part[part["complete"]]
        pd.testing.assert_frame_equal(done, full.loc[done.index])


def test_weekly_trend_uses_completed_weeks_only():
    idx = pd.bdate_range("2024-01-01", periods=63)            # 월요일 시작 · 마지막 주는 3일(진행 중)
    c = np.linspace(100, 160, 63)
    c[-1] = 10.0                                               # 진행 중 주의 폭락은 주봉 판정에 안 들어감
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1e6}, index=idx)
    w = tq.weekly_trend(df)
    assert w["weeks"] == 12 and w["week"] == str(pd.Period(idx[-4], "W-SUN"))
    assert w["above"] is True
    assert tq.weekly_trend(df.iloc[:40])["sma"] is None        # 완성 주 7개 → 모름


# ---------------------------------------------------------------- 피보
LV = tq.fib_levels(200.0, 100.0)


def test_fib_levels_and_next_deeper():
    assert LV == pytest.approx({0.236: 176.4, 0.382: 161.8, 0.5: 150.0, 0.618: 138.2})
    assert tq.next_deeper(0.236) == 0.382 and tq.next_deeper(0.5) == 0.618 and tq.next_deeper(0.618) is None
    assert tq.retracement(200, 100, 150) == pytest.approx(0.5)


def test_fib_touch_boundaries():
    lv = LV[0.382]
    assert tq.fib_touch(lv * 1.015, 162.0, lv, LV[0.5])            # 정확히 lv × 1.015 = 접촉
    assert not tq.fib_touch(lv * 1.0151, 162.0, lv, LV[0.5])
    assert not tq.fib_touch(155.0, lv * 0.9999, lv, LV[0.5])         # 종가가 라인 0.01% 아래
    assert not tq.fib_touch(149.0, 162.0, lv, LV[0.5])               # 다음 깊은 라인까지 내려감


def test_fib_wick_vs_band_two_percent_pierce():
    lv = LV[0.5]
    assert tq.fib_touch(lv * 0.98, 151.0, lv, LV[0.618], mode="wick")
    assert not tq.fib_touch(lv * 0.98, 151.0, lv, LV[0.618], mode="band")
    assert tq.fib_touch(lv * 0.99, 151.0, lv, mode="band")


def test_fib_touch_level_deepest_first_and_approach():
    assert tq.fib_touch_level(163.0, 177.0, LV) == 0.382           # 23.6 도 맞지만 깊은 쪽 먼저
    assert tq.fib_touch_level(149.0, 152.0, LV) == 0.5
    assert tq.fib_touch_level(170.0, 172.0, LV) is None
    assert tq.fib_approach(153.0, 150.0) and not tq.fib_approach(155.0, 150.0) and not tq.fib_approach(150.0, 150.0)


# ---------------------------------------------------------------- 하향 추세선
def _tl(n=130, spikes=(10, 40, 70), slope=-0.004):
    i = np.arange(n)
    line = 100.0 * np.exp(slope * i)
    o, h, lo, c = line * 0.91, line * 0.93, line * 0.88, line * 0.90
    for p in spikes:
        h[p], c[p], o[p] = line[p], line[p] * 0.95, line[p] * 0.92
    v = np.linspace(2e6, 1e6, n)                    # 거래량 감소
    return _bars(o, h, lo, c, v), line


def test_trendline_three_touches_valid():
    b, _ = _tl()
    ln = tq.fit_downtrend_line(b, 110)
    assert ln is not None and ln.valid
    assert ln.touches == (10, 40, 70) and ln.anchor_i == 10 and ln.length == 100
    b_star = -0.004 - np.log1p(0.005) / 60          # 70 봉 고가 = 선 × 1.005 에서 멈춤
    assert ln.slope == pytest.approx(b_star)
    assert ln.slope_pct == pytest.approx(np.expm1(b_star))
    assert ln.value(70) * 1.005 == pytest.approx(b.high[70])
    assert all(b.high[i] <= ln.value(i) * 1.005 * (1 + 1e-12) for i in range(10, 110))
    f = tq.line_features(ln, b)
    assert f["touch_count"] == 3 and not f["touch_bonus"] and f["long"] and f["vol_declining"]
    assert f["entry_trend_pct"] is None              # 앵커 앞 20봉 없음 = 모름
    assert "tl_break_vol" in f["origin"]


def test_trendline_two_touches_rejected():
    b, _ = _tl(spikes=(10, 70))
    assert tq.fit_downtrend_line(b, 110) is None
    (c,) = tq.downtrend_line_candidates(b, 110)
    assert c.touches == (10, 70) and any("접점 2개" in r for r in c.reasons)


def test_trendline_touch_gap_nine_rejected():
    b, _ = _tl(spikes=(10, 40, 49, 70))
    ln = tq.fit_downtrend_line(b, 110)
    assert ln.touches == (10, 40, 70)                # 49 는 40 과 9봉 — 접점 아님


def test_trendline_close_above_line_is_stale():
    b, line = _tl()
    c, h = b.close.copy(), b.high.copy()
    c[50], h[50] = line[50], line[50] * 1.001
    b2 = tq.Bars(b.open, h, b.low, c, b.volume, b.dates)
    assert tq.fit_downtrend_line(b2, 110) is None
    assert any("선 위 종가" in r for r in tq.downtrend_line_candidates(b2, 110)[0].reasons)


def test_trendline_pivot_delay_and_min_len():
    b, _ = _tl()
    c73 = tq.downtrend_line_candidates(b, 73)[0]
    assert c73.touches == (10, 40) and not c73.valid           # 70 은 73 EOD 에 확정 → t−1=72 로는 아직
    assert tq.fit_downtrend_line(b, 74).touches == (10, 40, 70)
    c45 = tq.downtrend_line_candidates(b, 45)[0]
    assert any("길이 35봉" in r for r in c45.reasons)


def test_trendline_break_close_vs_intraday():
    b, _ = _tl()
    ln = tq.fit_downtrend_line(b, 110)
    lv = ln.value(110)
    o, h, lo, c, v = (x.copy() for x in (b.open, b.high, b.low, b.close, b.volume))
    h[110], c[110] = lv * 1.03, lv * 0.99                      # 장중만 관통
    assert not tq.line_cross(ln, tq.Bars(o, h, lo, c, v, b.dates), 110)
    c[110], h[110], v[110] = lv * 1.02, lv * 1.03, 3e6
    b2 = tq.Bars(o, h, lo, c, v, b.dates)
    assert tq.line_cross(ln, b2, 110)
    assert tq.fit_downtrend_line(b2, 110) == ln               # 돌파 봉은 선 맞춤에 안 들어감
    f = tq.line_features(ln, b2)
    assert f["break_vol_ok"] is True and f["close_vs_line"] == pytest.approx(0.02)
    tg = tq.line_targets(ln, b2, 110)
    assert tg["t1"] == pytest.approx(b.high[10]) and tg["t2"] > lv and "우리 데이터 아님" in tg["note"]


def test_trendline_next_bar_line_and_exact_anchor_price():
    # t = b.n: 아직 없는 다음 봉을 시험할 선 — 오늘까지 자료로 맞춤(예전 자리표시 봉을 붙인 결과와 같다)
    b, _ = _tl(111)
    ln = tq.fit_downtrend_line(b, b.n)
    bx = tq.Bars(*(np.r_[a, a[-1]] for a in (b.open, b.high, b.low, b.close, b.volume)), None)
    old = tq.fit_downtrend_line(bx, b.n)
    assert ln is not None and ln.to_dict() == old.to_dict() and ln.t == 111
    assert tq.downtrend_line_candidates(b, b.n + 1) == []
    assert ln.anchor_price == b.high[10]                       # exp(log(고가)) 부동소수 잡음 없이 그대로
    assert ln.value(10) == pytest.approx(b.high[10])


def test_trendline_prefix_invariant_random():
    b = _rand_bars()
    sw = tq.swing_highs(b.high)
    hits = 0
    for t in range(40, b.n, 4):
        ln = tq.fit_downtrend_line(b, t)
        d = None if ln is None else ln.to_dict()
        hits += ln is not None
        for other in (tq.fit_downtrend_line(b.cut(t), t), tq.fit_downtrend_line(_junk_future(b, t), t),
                      tq.fit_downtrend_line(b, t, swings=sw)):
            assert (None if other is None else other.to_dict()) == d
    assert hits > 5                                            # 의미 있는 시험인지


# ---------------------------------------------------------------- 망치형
def _hammer_bars(last, n_prior=12, after=()):
    """직전 봉: 시가 100 · 종가 100.5 · 고가 101 · 저가 99 (범위 2). last = (O, H, L, C)."""
    rows = [(100, 101, 99, 100.5)] * n_prior + [last] + list(after)
    o, h, lo, c = (np.array(x, dtype=float) for x in zip(*rows))
    return _bars(o, h, lo, c)


def test_hammer_shape_boundaries():
    j = 12
    b = _hammer_bars((100, 101.2, 97, 101))          # 몸통 1 · 아래꼬리 3 · 위꼬리 0.2 = 0.1 × 평균범위 2 (경계)
    r = tq.hammer(b, j)
    assert r["shape"] is True and r["label"] == "양봉 망치" and r["upper_ratio"] == pytest.approx(0.1)
    assert not tq.is_hammer(_hammer_bars((100, 101.21, 97, 101)), j)   # 위꼬리 0.105
    assert not tq.is_hammer(_hammer_bars((100, 100.22, 99.5, 100.2)), j)  # 범위 < 평균
    d = tq.hammer(_hammer_bars((100.8, 100.9, 97, 100.8)), j)
    assert d["shape"] is True and d["label"] == "doji-hammer"
    assert tq.hammer(_hammer_bars((100, 101.2, 97, 101), n_prior=5), 5)["shape"] is None   # 직전 10봉 없음 = 모름


def test_hammer_confirm_within_three_bars_only():
    j = 12
    after = [(100.5, 101, 100, 100.5), (100.5, 102, 100, 101.5), (101, 102, 100, 101)]
    b = _hammer_bars((100, 101.2, 97, 101), after=after)
    assert tq.hammer_confirm(b, j, upto=b.n - 1) == j + 2
    assert tq.hammer_confirm(b, j, upto=j + 1) is None        # 아직 오지 않은 봉은 안 본다
    late = [(100.5, 101, 100, 100.5)] * 3 + [(101, 103, 101, 102.5)]
    assert tq.hammer_confirm(_hammer_bars((100, 101.2, 97, 101), after=late), j, upto=j + 4) is None


def test_hammer_bottom_context():
    n = 270
    c = np.linspace(200, 100, n)
    o, cl = c + 0.5, c - 0.5
    h, lo = o + 0.5, cl - 0.5
    p = c[-1]
    o[-1], h[-1], lo[-1], cl[-1] = p, p + 1.2, p - 3, p + 1
    r = tq.hammer(_bars(o, h, lo, cl), n - 1)
    assert r["shape"] and r["prior_decline"] is True and r["yearly_pos"] < 1 / 3 and r["bottom"] is True
    short = _bars(o[-30:], h[-30:], lo[-30:], cl[-30:])
    assert tq.hammer(short, 29)["bottom"] is None              # 252봉 없음 = 모름


# ---------------------------------------------------------------- 장대양봉 · 반등 양봉
def _lw(last, v_last=3e6, n=25):
    rows = [(99.8, 100.3, 99.6, 100.0)] * n + [last]
    o, h, lo, c = (np.array(x, dtype=float) for x in zip(*rows))
    v = np.r_[np.full(n, 1e6), v_last]
    return _bars(o, h, lo, c, v)


def test_long_white_rules():
    t = 25
    assert tq.long_white(_lw((100.5, 108.5, 100.2, 108.0)), t)["ok"]
    gap = tq.long_white(_lw((107.0, 107.8, 106.9, 107.5)), t)          # +7.5% 갭 · 몸통 0.5 < 3 × 0.2
    assert gap["chg_ok"] and not gap["body_ok"] and not gap["ok"]
    assert not tq.long_white(_lw((100.5, 116.0, 100.2, 108.0)), t)["shadows_ok"]
    assert tq.long_white(_lw((100.5, 108.5, 100.2, 108.0), v_last=2e6), t)["vol_ok"]   # 기준선에 당일 미포함 → 정확히 2배
    short = tq.long_white(_lw((100.5, 108.5, 100.2, 108.0), n=10), 10)
    assert not short["known"] and not short["ok"]


def test_long_white_zero_baseline_is_unknown_and_halt_rows_skipped():
    last = (100.5, 108.5, 100.2, 108.0)
    assert tq.long_white(_lw(last, v_last=3e6), 25)["ok"]
    # 직전 거래량이 모두 0 → 기준선 없음 = 모름 (배수 inf 를 통과로 보지 않음)
    b = _lw(last)
    b0 = tq.Bars(b.open, b.high, b.low, b.close, np.r_[np.zeros(25), 3e6], b.dates)
    r = tq.long_white(b0, 25)
    assert not r["ok"] and not r["known"] and not r["vol_ok"] and r["vol_ratio"] is None
    assert "lw_zero_base" in r["origin"] and "http" in tq.ORIGIN["lw_shadow"]
    # 직전 몸통이 모두 0(보합 봉) → 몸통 기준선 0 = 모름
    o = np.r_[np.full(25, 100.0), 100.5]
    c = np.r_[np.full(25, 100.0), 108.0]
    rf = tq.long_white(tq.Bars(o, b.high, b.low, c, b.volume, b.dates), 25)
    assert not rf["ok"] and not rf["known"] and not rf["body_ok"]
    # 정지 행(거래량 0)은 거래량 기준선에서 빠진다 — 0 을 넣었다면 1.9배짜리가 2배를 넘어 보였을 것
    v = np.r_[np.full(25, 1e6), 1.9e6]
    v[20] = 0.0
    rh = tq.long_white(tq.Bars(b.open, b.high, b.low, b.close, v, b.dates), 25)
    assert rh["vol_ratio"] == pytest.approx(1.9) and not rh["vol_ok"]
    assert 1.9e6 / np.mean(v[5:25]) >= 2.0


def test_volume_reversal_cross_vs_level_and_up_close():
    c = np.r_[np.full(8, 100.0), 99.0, 100.5]
    o = np.r_[np.full(8, 100.0), 99.5, 99.2]
    v = np.r_[np.full(8, 1e6), 3e6, 4e6]
    b = _bars(o, np.maximum(o, c) + 0.5, np.minimum(o, c) - 0.5, c, v)
    assert tq.volume_reversal(b, 9, test="level")["ok"]
    assert not tq.volume_reversal(b, 9, test="cross")["ok"]          # 어제 이미 5일 이평 위 → 상향돌파 아님
    v2 = np.r_[np.full(9, 1e6), 3e6]
    b2 = tq.Bars(b.open, b.high, b.low, b.close, v2, b.dates)
    r = tq.volume_reversal(b2, 9)
    assert r["ok"] and r["vol_ma5"] == pytest.approx(np.mean(v2[5:10]))
    c3 = c.copy()
    c3[8] = 101.0                                                     # 전일보다 낮은 종가 = 반등 아님
    b3 = tq.Bars(b.open, np.maximum(b.high, c3), b.low, c3, v2, b.dates)
    assert not tq.volume_reversal(b3, 9)["ok"] and tq.volume_reversal(b3, 9, require_up_close=False)["ok"]


def test_candle_frames_prefix_invariant():
    b = _rand_bars()
    hf, lf = tq.hammer_frame(b), tq.long_white_frame(b)
    for T in (30, 120, 260, b.n - 2):
        pd.testing.assert_frame_equal(tq.hammer_frame(b.cut(T)), hf.iloc[:T + 1])
        pd.testing.assert_frame_equal(tq.long_white_frame(b.cut(T)), lf.iloc[:T + 1])


# ---------------------------------------------------------------- 청산
def _arm_case(after):
    """30봉 100 → d=30 종가 98 · 저가 97 (10일선 무장) → after = [(종가, 저가), ...]."""
    rows = [(100.0, 99.0)] * 30 + [(98.0, 97.0)] + list(after)
    c, lo = (np.array(x) for x in zip(*rows))
    return _bars(c.copy(), np.maximum(c, lo) + 1, lo, c), 30


def test_ma10_violation_next_day_equal_low_is_not():
    b, d = _arm_case([(98.5, 97.0)])
    m10 = tq.sma(b.close, 10)
    assert tq.arm_days(b.close, m10) == [d]
    assert tq.ma_violation(d, b.close, b.low, m10, b.n - 1) is None
    b2, _ = _arm_case([(98.5, 96.9)])
    assert tq.ma_violation(d, b2.close, b2.low, tq.sma(b2.close, 10), b2.n - 1) == d + 1


def test_ma10_until_reclaim_catches_third_day_and_stops_on_reclaim():
    b, d = _arm_case([(98.5, 97.5), (98.6, 97.2), (98.0, 96.5)])
    m10 = tq.sma(b.close, 10)
    assert tq.ma_violation(d, b.close, b.low, m10, b.n - 1, "next_day") is None
    assert tq.ma_violation(d, b.close, b.low, m10, b.n - 1, "until_reclaim") == d + 3
    b2, _ = _arm_case([(101.0, 97.5), (95.0, 90.0)])
    assert tq.ma_violation(d, b2.close, b2.low, tq.sma(b2.close, 10), b2.n - 1, "until_reclaim") is None


def test_exit_plan_today_messages():
    b, d = _arm_case([])
    p = tq.exit_plan(b)
    assert p["ma10_arm_today"] and p["ma5_break_today"]
    assert any("내일 저가 97 하회 시 10일선 위반(모랄레스)" in s for s in p["notes"])
    assert p["ma10_pending"]["d"] == d
    b2, _ = _arm_case([(98.5, 96.0)])
    assert tq.exit_plan(b2)["ma10_violation_today"]
    assert "우리 데이터 아님" in p["bulkowski"] and "exit_ma10" in p["origin"]


def _seven_week_case():
    c = np.r_[np.full(61, 100.0), np.arange(101.0, 110.0), 104.0, 104.5, np.arange(105.0, 134.0), 126.0, 125.0]
    lo = c - 1
    lo[71], lo[102] = 102.0, 124.0          # 무장일(70 · 101) 저가 103 · 125 아래
    return _bars(c.copy(), c + 1, lo, c), 60


def test_seven_week_rule_boundaries():
    e = tq.ExitConfig()
    bk = tq.ExitConfig(seven_week_mode="bulkowski")
    assert tq.seven_week_rule(34, False, bk) == "50일선" and tq.seven_week_rule(35, False, bk) == "10일선"
    assert tq.seven_week_rule(35, False, e) == "50일선" and tq.seven_week_rule(36, False, e) == "10일선"
    assert tq.seven_week_rule(36, True, e) == "50일선"


def test_exit_plan_seven_week_modes_differ():
    b, e = _seven_week_case()
    pe = tq.exit_plan(b, entry_i=e)
    assert [v["i"] for v in pe["ma10_violations"]] == [71, 102]
    assert pe["ma50_violations"] == []
    assert pe["rule_exit"] is None and pe["active_rule"] == "50일선"      # 35봉 안 위반 → 50일선 기준
    pb = tq.exit_plan(b, entry_i=e, cfg=tq.ExitConfig(seven_week_mode="bulkowski"))
    assert pb["rule_exit"]["i"] == 102 and pb["rule_exit"]["rule"] == "10일선"
    assert pb["rule_exit"]["fill"] == pytest.approx(min(b.open[102], 125.0 - 1))
    assert pe["first_ma5_exit"]["i"] == 70


def test_violation_fill_price_tick():
    assert tq.violation_fill_price(5100, 5000) == 4995      # 5,000 아래 호가 5원
    assert tq.violation_fill_price(4980, 5000) == 4980      # 갭 하락이면 시가


def test_exit_plan_prefix_invariant():
    b = _rand_bars()
    for t in range(80, b.n, 23):
        a = tq.exit_plan(b, t, entry_i=t - 50)
        assert tq.exit_plan(b.cut(t), t, entry_i=t - 50) == a
        assert tq.exit_plan(_junk_future(b, t), t, entry_i=t - 50) == a


# ---------------------------------------------------------------- 체크리스트
def _item(items, no):
    return next(i for i in items if i.no == no)


def test_checklist_all_unknown_inputs_and_origins():
    b = _flat_bars(np.full(300, 100.0))
    items = tq.run_checklist(b)
    assert [i.no for i in items] == list(range(1, 11))
    assert all(i.status in ("pass", "warn", "unknown") and i.origin for i in items)
    for no in (1, 2, 4, 5, 8):
        assert _item(items, no).status == "unknown"
    assert _item(items, 4).note == "재현 안 함"
    assert tq.checklist_counts(items)["unknown"] == 5
    assert _item(items, 1).to_dict()["status_label"] == "모름"


def test_checklist_market_state():
    b = _flat_bars(np.full(60, 100.0))
    ok = tq.run_checklist(b, inputs=tq.ChecklistInputs(market_state=confirmed_market()))
    assert _item(ok, 1).status == "pass" and "기준일" in _item(ok, 1).note    # 국면 날짜와 봉 날짜가 다르면 메모
    for st in (CORRECTION, PRESSURE):
        ms = replace(confirmed_market(), state=st, label="x")
        assert _item(tq.run_checklist(b, inputs=tq.ChecklistInputs(market_state=ms)), 1).status == "warn"


def test_checklist_sector_and_industry_rs():
    b = _flat_bars(np.full(60, 100.0))

    def run(**kw):
        return tq.run_checklist(b, inputs=tq.ChecklistInputs(**kw))
    assert _item(run(sector={"group": "반도체", "rank_pct": 0.9, "pos52": 0.9}), 2).status == "pass"   # 주도 우선
    assert _item(run(sector={"group": "반도체", "rank_pct": 0.3, "pos52": 0.8}), 2).status == "warn"   # 고점권
    assert "바닥권" in _item(run(sector={"group": "반도체", "rank_pct": 0.3, "pos52": 0.2}), 2).note
    assert _item(run(sector={"group": "반도체", "rank_pct": 0.3}), 2).status == "unknown"
    assert _item(run(industry_rs={"group": "A", "rank_pct": 0.8, "members": 5}), 5).status == "pass"
    assert _item(run(industry_rs={"group": "A", "rank_pct": 0.5, "members": 5}), 5).status == "warn"
    assert _item(run(industry_rs={"group": "A", "rank_pct": 0.9, "members": 2}), 5).status == "unknown"


def test_checklist_replay_sample_size():
    b = _flat_bars(np.full(60, 100.0))
    few = tq.run_checklist(b, inputs=tq.ChecklistInputs(replay=[{"ret20": 0.1}, {"ret20": -0.02}, {"ret20": None}]))
    assert _item(few, 4).status == "unknown" and _item(few, 4).note == "표본 적음 (2건)"
    ok = tq.run_checklist(b, inputs=tq.ChecklistInputs(replay=[{"ret20": 0.1}, {"ret20": -0.02}, {"ret20": 0.03}]))
    assert _item(ok, 4).status == "pass" and _item(ok, 4).value["n"] == 3 and "확률 아님" in _item(ok, 4).note


def test_checklist_weekly_daily_and_uptrend():
    c = np.linspace(100, 160, 80)
    items = tq.run_checklist(_flat_bars(c))
    assert _item(items, 3).status == "pass" and _item(items, 6).status == "pass"
    down = tq.run_checklist(_flat_bars(c[::-1]))
    assert _item(down, 3).status == "warn" and _item(down, 6).status == "warn"
    assert _item(tq.run_checklist(_flat_bars(c[:40])), 3).status == "unknown"


def test_checklist_resistance():
    c = np.full(60, 100.0)
    assert _item(tq.run_checklist(_flat_bars(np.r_[c, 105.0])), 7).note == "위 저항 없음(신고가)"
    peak = np.r_[c[:30], 103.0, 104.0, 105.0, 104.0, 103.0, c[:26]]        # 33봉 고가 106 소고점
    r = _item(tq.run_checklist(_flat_bars(peak), inputs=tq.ChecklistInputs(stop=95.0)), 7)
    assert r.status == "warn" and r.value["resistance"] == pytest.approx(106.0) and "먹을 폭 작음" in r.note
    assert r.value["dist_to_stop_ratio"] == pytest.approx(0.06 / 0.05)
    far = np.r_[c[:30], 110.0, 115.0, 120.0, 115.0, 110.0, c[:26]]
    assert _item(tq.run_checklist(_flat_bars(far)), 7).status == "pass"


def test_checklist_stop_vs_volatility_stop():
    b = _flat_bars(np.full(60, 100.0))                  # 범위 2 → 변동성 손절 = 99 − 2 × 2 = 95
    near = _item(tq.run_checklist(b, inputs=tq.ChecklistInputs(stop=97.0)), 8)
    assert near.status == "warn" and near.value["vstop"] == pytest.approx(95.0)
    assert _item(tq.run_checklist(b, inputs=tq.ChecklistInputs(stop=94.0)), 8).status == "pass"


def _dcb(drop_close, at_from_end, n=300, start="2024-01-02"):
    c = np.full(n, 100.0)
    j = n - 1 - at_from_end
    c[j:] = drop_close
    return _flat_bars(c, start=start)


def test_checklist_deadcat_thresholds_and_window():
    assert _item(tq.run_checklist(_dcb(85.0, 10)), 9).status == "warn"           # −15.0% 정확히 = 사건
    assert _item(tq.run_checklist(_dcb(85.1, 10)), 9).status == "pass"           # −14.9%
    assert _item(tq.run_checklist(_dcb(85.0, 125)), 9).status == "warn"          # t−125 = 6개월 창 안
    old = _item(tq.run_checklist(_dcb(85.0, 126)), 9)
    assert old.status == "pass" and "참고: 6~12개월 전 급락" in old.note
    assert _item(tq.run_checklist(_flat_bars(np.full(100, 100.0))), 9).status == "unknown"   # 126봉 미만


def test_checklist_deadcat_pre_2015_limit_regime():
    pre = _dcb(85.5, 40, n=200, start="2014-06-02")                              # −14.5%, 2015-06-15 전
    assert pre.dates[-1] < pd.Timestamp("2015-06-15")
    assert _item(tq.run_checklist(pre), 9).status == "warn"
    assert _item(tq.run_checklist(_dcb(85.5, 40, n=200)), 9).status == "pass"    # 같은 낙폭이 2015 뒤면 사건 아님


def test_checklist_risk_tags_warn():
    b = _flat_bars(np.full(200, 100.0))
    r = _item(tq.run_checklist(b, inputs=tq.ChecklistInputs(risk={"level": "작전주 꼴", "ref": [{"cat": "자본잠식"}]})), 9)
    assert r.status == "warn" and "공시 위험: 작전주 꼴" in r.note and "자본잠식" in r.note
    v = _item(tq.run_checklist(b, inputs=tq.ChecklistInputs(value_row={"risk": "감사"})), 9)
    assert v.status == "warn" and "공시 위험: 감사" in v.note


def test_checklist_runup():
    base = np.full(30, 100.0)
    hot = _item(tq.run_checklist(_flat_bars(np.r_[base, 106, 112, 111, 118, 126])), 10)
    assert hot.status == "warn" and "단기 급등 — 되돌림 뒤 진입 고려" in hot.note and "추격 금지" not in hot.note
    calm = _item(tq.run_checklist(_flat_bars(np.r_[base, 101, 102, 103, 104])), 10)
    assert calm.status == "pass" and calm.note.endswith(" · 연속 상승 4일") and "상승 4일" in calm.note
    assert _item(tq.run_checklist(_flat_bars(np.r_[base, 101, 100, 101, 100, 101])), 10).note == "5일 +1.0% · 상승 3일"


def test_checklist_prefix_invariant():
    b = _rand_bars()
    x = tq.ChecklistInputs(stop=60.0, market_state=confirmed_market())
    for t in range(130, b.n, 37):
        a = [i.to_dict() for i in tq.run_checklist(b, t, x)]
        assert [i.to_dict() for i in tq.run_checklist(b.cut(t), t, x)] == a
        assert [i.to_dict() for i in tq.run_checklist(_junk_future(b, t), t, x)] == a


def test_inputs_from_ctx():
    df = make_ohlcv([(0, 100), (80, 120)], seed=1)
    ctx = make_context(df, info={"groups": {"sector": "반도체", "sector_rank_pct": 0.8}, "sector_pos52": 0.4,
                                 "risk": {"level": "작전주 꼴"}, "undervalued": None})
    x = tq.inputs_from_ctx(ctx, stop=110.0)
    assert x.sector == {"group": "반도체", "rank_pct": 0.8, "pos52": 0.4, "rank_partial": False}
    assert x.market_state is ctx.market_state and x.risk["level"] == "작전주 꼴" and x.stop == 110.0
    assert x.industry_rs is None and x.replay is None


def test_sector_check_ignores_intraday_strength():
    """장중: 업종 강도(스냅샷 그대로 — 오늘 미완성 봉 포함)는 2번 판정에 안 쓴다. 연중 위치로 통과면 통과, 고점권이면 모름."""
    b = tq.Bars.from_df(make_ohlcv([(0, 100), (80, 120)], seed=1))
    t, cfg = b.n - 1, tq.ChecklistConfig()

    def ck(rank, pos, partial):
        x = tq.ChecklistInputs(sector={"group": "반도체", "rank_pct": rank, "pos52": pos, "rank_partial": partial})
        return tq._ck_sector(b, t, x, cfg)
    assert ck(0.9, 0.8, False).status == tq.PASS                    # 완성 봉: 주도 → 통과
    it = ck(0.9, 0.8, True)
    assert it.status == tq.UNKNOWN and "장중" in it.note             # 장중: 고점권 + 장중 강도 → 모름
    assert ck(0.9, 0.5, True).status == tq.PASS                     # 중간권은 강도와 무관하게 통과 (완성 봉 판정도 통과)
    assert ck(0.5, 0.8, False).status == tq.WARN and ck(None, 0.8, True).status == tq.WARN


def test_industry_rs_table():
    idx = pd.bdate_range("2024-01-01", periods=300)

    def s(r):
        return pd.Series(100 * (1 + r) ** np.arange(300), index=idx)
    closes = {"a1": s(0.002), "a2": s(0.003), "a3": s(0.001), "b1": s(-0.001), "b2": s(0.0), "b3": s(-0.002),
              "c1": s(0.01), "c2": s(0.01)}
    groups = {k: k[0].upper() for k in closes}
    t = tq.industry_rs_table(closes, groups)
    assert t.loc["A", "rank_pct"] == 1.0 and t.loc["B", "rank_pct"] == 0.0
    assert np.isnan(t.loc["C", "rank_pct"]) and t.loc["C", "members"] == 2          # 구성 2개 = 순위 없음
    assert t.loc["A", "rs"] == pytest.approx(np.mean([(1 + r) ** 126 - 1 for r in (0.002, 0.003, 0.001)]))
    assert t.loc["A", "pos52"] == pytest.approx(1.0)
    early = tq.industry_rs_table(closes, groups, asof=idx[100])
    assert early.empty                                                               # 126봉 전에는 아무도 없음


# ---------------------------------------------------------------- 시장 맥락
def _index(end_close):
    c = np.r_[np.linspace(3000, 2293.70, 50), np.linspace(2293.70, 9114.55, 300)[1:], np.linspace(9114.55, end_close, 101)[1:]]
    idx = pd.bdate_range("2025-01-02", periods=len(c))
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e8}, index=idx)


def test_market_context_retracement_zones():
    m = tq.market_context(_index(6035.35), "KOSPI")
    cl = m["close"]
    assert cl["low"] == pytest.approx(2293.70) and cl["high"] == pytest.approx(9114.55)
    assert cl["retr"] == pytest.approx(0.4514, abs=1e-4) and cl["zone"] is None        # 부록 §10 2026-10-13 종가 기준 45.1%
    assert cl["dd"] == pytest.approx(6035.35 / 9114.55 - 1)
    assert m["intraday"]["low"] == pytest.approx(2293.70 * 0.99) and m["intraday"]["price"] == pytest.approx(6035.35 * 0.99)
    assert m["above_ma120"] is False and m["red3_monthly"] is None
    assert tq.market_context(_index(5500.0))["zone"] == "50~61.8% 구간"
    assert tq.market_context(_index(4500.0))["zone"] == "61.8% 넘음"
    assert "김종봉" in m["origin"]["mkt_retr"]
    assert cl["prev_leg"] is None


def test_market_context_bounce_becomes_last_leg_prev_leg_kept():
    """2026-10-13 KOSPI 꼴: 큰 파동 뒤 −38% 급락 → +26.6% 반등(ZigZag 20% 확정) → 다시 하락.
    마지막 파동 = 반등(되돌림 70% '61.8% 넘음'), 직전 큰 파동 = 부록 §10 사례 45.1%."""
    c = np.r_[np.linspace(3000, 2293.70, 50), np.linspace(2293.70, 9114.55, 300)[1:],
              np.linspace(9114.55, 5593.56, 30)[1:], np.linspace(5593.56, 7080.92, 40)[1:],
              np.linspace(7080.92, 6035.35, 15)[1:]]
    idx = pd.bdate_range("2025-01-02", periods=len(c))
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1e8}, index=idx)
    cl = tq.market_context(df, "KOSPI")["close"]
    assert cl["low"] == pytest.approx(5593.56) and cl["high"] == pytest.approx(7080.92)
    assert cl["retr"] == pytest.approx((7080.92 - 6035.35) / (7080.92 - 5593.56)) and cl["zone"] == "61.8% 넘음"
    pl = cl["prev_leg"]
    assert pl["low"] == pytest.approx(2293.70) and pl["high"] == pytest.approx(9114.55)
    assert pl["retr"] == pytest.approx(0.4514, abs=1e-4) and pl["zone"] is None


def test_market_context_red3_hook_and_prefix_invariance():
    df = _index(6035.35)
    seen = {}

    def red3(monthly):
        seen["last"] = monthly.index[-1]
        return {"detected": False}
    m = tq.market_context(df, "KOSPI", t=200, red3=red3)
    assert m["red3_monthly"] == {"detected": False} and seen["last"] == df.index[200].to_period("M")
    for t in (120, 300, 420):
        a = tq.market_context(df, "KOSPI", t=t)
        assert tq.market_context(df.iloc[:t + 1], "KOSPI") == a
    allm = tq.market_context_all({"KOSPI": df, "KOSDAQ": None})
    assert list(allm) == ["KOSPI"]


def test_market_context_no_confirmed_low_is_unknown():
    idx = pd.bdate_range("2025-01-02", periods=60)
    c = np.linspace(100, 110, 60)
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0}, index=idx)
    m = tq.market_context(df)
    assert m["close"] is None and m["zone"] is None and m["above_ma120"] is None


# ---------------------------------------------------------------- 자료 · 공통
def test_eod_frame_drops_partial_bar_and_window_halts():
    df = make_ohlcv([(0, 100), (30, 110)], seed=2)
    df.attrs["halt_dates"] = [f"{df.index[10]:%Y-%m-%d}", "2001-01-01"]
    ctx = make_context(df)
    assert len(tq.eod_frame(ctx)) == len(df)
    ctx.partial = True
    assert len(tq.eod_frame(ctx)) == len(df) - 1
    assert tq.window_halts(df, 5, 15) == [f"{df.index[10]:%Y-%m-%d}"]
    assert tq.window_halts(df, 11, 20) == []


def test_labels_rule_ids_and_bulkowski_label():
    assert tq.PATTERN_LABELS == {
        "red_three_monthly": "월봉 적삼병", "fib_pullback": "피보나치 눌림 반등", "trendline_break": "빗각 추세선 돌파",
        "trendline_fib": "빗각 돌파 + 피보 눌림", "day_leader": "10% 주도주 (단타 관찰)", "ma60_supply": "60일선 수급 돌파"}
    assert set(tq.RULE_IDS) == set(tq.PATTERN_LABELS) and tq.RULE_IDS["red_three_monthly"] == "red3m_v1"
    assert tq.bulkowski_note("hammer").startswith("참고 — 불코우스키 미국 통계(우리 데이터 아님)")
    assert tq.video("51:00") == "영상 [51:00]" and tq.choice("x") == "구현 선택: x"


def test_every_core_origin_names_its_source():
    # 규칙마다 출처: '영상 [mm:ss]' · 출처 URL · '구현 선택: 이유' 중 하나는 있어야 한다(이름만 있는 출처 금지)
    for k, v in tq.ORIGIN.items():
        assert any(x in v for x in ("영상 [", "http", "구현 선택")), k
