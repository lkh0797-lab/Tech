"""빗각 추세선 돌파(trendline_break) — 합성 봉으로 신호 · 비신호 · 부록 §13 추세선 경계 · 앞부분 불변 · '모름' 처리.

선 모양 · 접점 · 관통 같은 공용 부품 경계는 tests/test_techniques_core.py 가 본다 — 여기는 패턴 상태 기계(돌파 · 안착 확인 ·
실패 · 동결 · 표시 창)와 Tech 결과(단계 · 피벗 · 손절 · 점수 · 출처 · 차트 표시)."""
import json

import numpy as np
import pandas as pd
import pytest

from chart_screener import techniques as tq
from chart_screener.config import Config
from chart_screener.journal import rule_of
from chart_screener.patterns import REGISTRY
from chart_screener.patterns import trendline_break as tb
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from synthetic import add_value, make_context, make_ohlcv


# ---------------------------------------------------------------- 도우미
def _tl_df(n=111, spikes=(10, 40, 70), slope=-0.004, prefix=0):
    """로그 직선 line = 100·e^(slope·(i − prefix)) 아래 봉(고가 0.93 · 종가 0.90) + spikes 봉 고가 = 선(접점).
    prefix > 0 이면 앞에 고가가 계속 낮아지는(소고점 없는) 하락 봉 prefix 개를 붙인다."""
    i = np.arange(n)
    line = 100.0 * np.exp(slope * (i - prefix))
    c = np.where(i < prefix, 90.0 * (1 + 0.002 * (prefix - i)), 0.90 * line)
    o, h, lo = c * (0.91 / 0.90), c * (0.93 / 0.90), c * (0.88 / 0.90)
    for p in spikes:
        h[p], c[p], o[p] = line[p], line[p] * 0.95, line[p] * 0.92
    v = np.linspace(2e6, 1e6, n)
    df = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": v},
                      index=pd.bdate_range("2024-01-02", periods=n))
    return add_value(df)


def _bar(df, i, close, vol=None, high=None, low=None, open_=None):
    o = close * 0.995 if open_ is None else open_
    h = max(o, close) * 1.002 if high is None else high
    lo = min(o, close) * 0.99 if low is None else low
    for k, v in (("open", o), ("high", h), ("low", lo), ("close", close)):
        df.iloc[i, df.columns.get_loc(k)] = v
    if vol is not None:
        df.iloc[i, df.columns.get_loc("volume")] = vol


def _line(df, t):
    """봉 t 를 시험하는 선 (t−1 까지 자료)."""
    return tq.fit_downtrend_line(tq.Bars.from_df(df), t)


def _seq(rel, vols=None, t0=110, **kw):
    """봉 t0 부터 rel[k] × (t0 시험선 = 돌파 때 동결될 선)의 그날 값으로 종가를 채운다. 거래량 기본: 첫 봉 3e6, 뒤 1.5e6."""
    df = _tl_df(t0 + len(rel), **kw)
    ln = _line(df, t0)
    for k, r in enumerate(rel):
        i = t0 + k
        _bar(df, i, r * ln.value(i), vol=vols[k] if vols else (3e6 if k == 0 else 1.5e6))
    return df, ln


def _det(df, **kw):
    return tb.detect(make_context(df, **kw))


def _junk(df, t, seed=0):
    """봉 t 뒤를 엉뚱한 봉으로 — 앞부분 불변 시험용."""
    rng = np.random.default_rng(seed)
    d = df.copy()
    k = len(d) - t - 1
    if k > 0:
        c = float(d["close"].iloc[t]) * rng.uniform(0.3, 3.0, k)
        o = c * rng.uniform(0.8, 1.2, k)
        for col, v in (("close", c), ("open", o), ("high", np.maximum(o, c) * 1.2), ("low", np.minimum(o, c) * 0.8),
                       ("volume", rng.uniform(1e3, 1e9, k))):
            d.iloc[t + 1:, d.columns.get_loc(col)] = v
    return d


# ---------------------------------------------------------------- 등록 · 규칙 id
def test_registered_label_and_rule_id():
    assert REGISTRY["trendline_break"][0] == "빗각 추세선 돌파" == tq.PATTERN_LABELS["trendline_break"]
    r = _det(_tl_df())
    assert r.metrics["rule_version"] == "tlbrk_v1" == r.metrics["rule_id"]
    assert rule_of(r) == "tlbrk_v1"                                    # 일지 rule 칸
    assert r.metrics["core_version"] == tq.CORE_VERSION


# ---------------------------------------------------------------- 비신호
def test_far_below_line_is_not_detected_but_explained():
    r = _det(_tl_df())                                                 # 종가 = 선 × 0.90 쯤
    assert not r.detected and r.metrics["phase"] == "far"
    assert r.metrics["line"]["touches"] == [10, 40, 70]
    assert any("돌파 임박은 선 아래 2% 안" in w for w in r.warnings)


def test_short_history_unknown():
    r = _det(_tl_df(30, spikes=(5, 18)))
    assert not r.detected and any("이력 부족" in w for w in r.warnings)


def test_two_touches_rejected():
    df = _tl_df(spikes=(10, 70))
    _bar(df, 110, _line_cand(df, 110).value(110) * 0.99)
    r = _det(df)
    assert not r.detected and r.metrics["phase"] is None
    assert any("접점 2개" in w for w in r.warnings)


def _line_cand(df, t):
    (c,) = tq.downtrend_line_candidates(tq.Bars.from_df(df), t)
    return c


def test_prior_close_above_line_is_stale():
    df = _tl_df()
    true_line = 100.0 * np.exp(-0.004 * 50)
    _bar(df, 50, true_line, high=true_line * 1.001)                   # 앵커 뒤 선 위 종가
    _bar(df, 110, _line_cand(df, 110).value(110) * 0.99)
    r = _det(df)
    assert not r.detected
    assert any("선 위 종가" in w for w in r.warnings)


# ---------------------------------------------------------------- 돌파 임박
def test_near_stage_pivot_is_next_bar_line_value():
    df = _tl_df()
    ln = _line(df, 110)
    _bar(df, 110, ln.value(110) * 0.99)
    r = _det(df)
    assert r.detected and r.stage == NEAR_PIVOT and r.metrics["phase"] == "near"
    assert r.metrics["tl_stage"] == "돌파 임박"
    b = tq.Bars.from_df(df)
    bx = tq.Bars(*(np.r_[a, a[-1]] for a in (b.open, b.high, b.low, b.close, b.volume)), None)
    nl = tq.fit_downtrend_line(bx, 111)
    assert r.pivot == pytest.approx(nl.value(111)) and r.pivot < ln.value(110)
    assert r.stop is None and r.breakout_date is None                 # 손절은 돌파 뒤
    assert r.start_date == "2024-01-16"                                # 앵커 봉 10
    assert any("돌파 임박" in s for s in r.reasons)
    assert r.metrics["score_parts"]["break_vol"]["na"]                # 돌파 전 — 해당 없음


def test_near_boundary_two_percent():
    df = _tl_df()
    lv = _line(df, 110).value(110)
    _bar(df, 110, lv * 0.98)
    assert _det(df).metrics["phase"] == "near"                       # 선 × 0.98 경계 포함
    _bar(df, 110, lv * 0.9799)
    assert _det(df).metrics["phase"] == "far"


def test_intraday_poke_is_not_breakout_and_next_line_rotates():
    df = _tl_df()
    ln = _line(df, 110)
    lv = ln.value(110)
    _bar(df, 110, lv * 0.99, high=lv * 1.03, vol=5e6)                 # 장중 고가만 선 위
    r = _det(df)
    assert r.metrics["phase"] == "near" and r.stage == NEAR_PIVOT and r.breakout_date is None
    nl = r.metrics["next_line"]
    assert nl["anchor_i"] == 10 and nl["slope_ln"] > ln.slope       # 오늘 고가를 품도록 선이 덜 가파르게 바뀜
    assert any("선이 바뀜" in s for s in r.reasons)


# ---------------------------------------------------------------- 돌파 · 안착 확인
def test_breakout_confirmed_same_day_at_three_percent():
    df, ln = _seq([1.04])
    r = _det(df)
    assert r.detected and r.stage == BREAKOUT and r.metrics["phase"] == "confirmed"
    br = r.metrics["break"]
    assert br["conf_how"] == "pct" and br["conf_date"] == br["date"] == r.breakout_date == f"{df.index[110]:%Y-%m-%d}"
    assert r.pivot == pytest.approx(ln.value(110))                    # 돌파가 = 돌파일 선 값
    assert r.stop == pytest.approx(ln.value(111))                     # 다음 봉 동결 선 값
    assert br["vol"] == "ok" and br["vol_ratio"] > 1.5
    assert r.metrics["tl_stage"] == "돌파 (안착 확인)"


def test_confirmation_measured_from_line_not_break_close():
    # 부록 §13 회귀: 돌파 종가 선 +2%, 다음 종가 그날 선 +3.1% → 둘째 날 안착 확인
    df, ln = _seq([1.02, 1.031])
    r1 = _det(df.iloc[:111])
    assert r1.metrics["phase"] == "pending" and r1.stage == NEAR_PIVOT and r1.breakout_date is None
    assert r1.metrics["tl_stage"] == "안착 확인 중"
    r2 = _det(df)
    assert r2.metrics["phase"] == "confirmed" and r2.stage == BREAKOUT
    assert r2.metrics["break"]["conf_how"] == "pct" and r2.metrics["break"]["conf_date"] == f"{df.index[111]:%Y-%m-%d}"
    assert 1.031 * ln.value(111) < 1.03 * df["close"].iloc[110]       # 스펙의 '돌파일 종가 +3%' 였다면 확인 안 됨


def test_three_closes_above_line_confirm():
    df, _ = _seq([1.01, 1.01, 1.01])
    assert _det(df.iloc[:112]).metrics["phase"] == "pending"
    r = _det(df)
    assert r.metrics["phase"] == "confirmed" and r.metrics["break"]["conf_how"] == "bars"
    assert r.metrics["break"]["conf_date"] == f"{df.index[112]:%Y-%m-%d}"


def test_extended_above_buy_range():
    df, _ = _seq([1.04, 1.10])
    r = _det(df)
    assert r.metrics["phase"] == "confirmed" and r.stage == EXTENDED


def test_throwback_above_line_kept_then_close_on_line_fails():
    df, ln = _seq([1.04, 1.01, 1.005, 1.0])
    r = _det(df.iloc[:113])                                            # 선 +0.5% 까지 되돌림
    assert r.metrics["phase"] == "confirmed" and r.stage == NEAR_PIVOT  # 돌파가 아래 · 선 위 = 되돌림
    assert any("되돌림" in s for s in r.reasons)
    r = _det(df)                                                       # 종가 = 선 (≤) → 실패
    assert r.detected and r.stage == FAILED and r.metrics["phase"] == "failed"
    assert r.metrics["tl_stage"] == "실패" and r.stop is None
    assert r.breakout_date == f"{df.index[110]:%Y-%m-%d}"              # 확인됐던 돌파
    assert r.metrics["break"]["fail_date"] == f"{df.index[113]:%Y-%m-%d}"


def test_fake_breakout_before_confirmation():
    df, _ = _seq([1.02, 0.99])
    r = _det(df)
    assert r.stage == FAILED and r.metrics["phase"] == "failed_fake"
    assert r.metrics["tl_stage"] == "실패(가짜 돌파)" and r.breakout_date is None


def test_failure_shown_for_five_bars_then_dropped():
    df, _ = _seq([1.04, 1.03, 0.99] + [0.90] * 6)                      # 112 실패 → 112..116 표시
    states = tb.timeline(df)
    assert [s.phase for s in states[112:117]] == ["failed"] * 5
    assert states[117].phase is None                                   # 옛 선은 선 위 종가로 낡음
    r = _det(df.iloc[:118])
    assert not r.detected and any("최근 돌파" in w for w in r.warnings)


# ---------------------------------------------------------------- 거래량
def test_low_volume_breakout_is_observation():
    base = float(np.mean(_tl_df(111)["volume"].iloc[60:110]))
    df, _ = _seq([1.04], vols=[base * 1.2])
    r = _det(df)
    assert r.detected and r.stage == FORMING and r.metrics["phase"] == "lowvol"
    assert r.metrics["tl_stage"].startswith("돌파(거래량 미달)") and r.breakout_date is None
    assert any("거래량" in w and "관찰" in w for w in r.warnings)
    cfg = Config()
    cfg.patterns["trendline_break"] = tb.TLBreakConfig(show_lowvol_break=False)
    assert not _det(df, cfg=cfg).detected


def test_break_volume_baseline_excludes_today():
    df = _tl_df(111)
    base = float(np.mean(df["volume"].iloc[60:110]))                   # 당일 뺀 직전 50봉
    ln = _line(df, 110)
    _bar(df, 110, ln.value(110) * 1.04, vol=1.5 * base)
    assert _det(df).metrics["break"]["vol"] == "ok"                  # 정확히 1.5배 = 통과
    assert 1.5 * base / float(np.mean(df["volume"].iloc[61:111])) < 1.5   # 당일을 넣었다면 미달
    _bar(df, 110, ln.value(110) * 1.04, vol=1.5 * base * 0.999)
    assert _det(df).metrics["break"]["vol"] == "low"


def test_halt_in_volume_window_is_not_volume_confirmation():
    df, _ = _seq([1.04])
    df.attrs["halt_dates"] = ["2024-05-01"]                           # 봉 60~109 구간 안
    r = _det(df)
    assert r.metrics["break"]["vol"] == "halt" and r.stage == FORMING and r.breakout_date is None
    assert any("거래정지" in w for w in r.warnings)


def test_unknown_volume_and_score_unknowns_with_short_history():
    df = _tl_df(46, spikes=(3, 15, 30))
    _bar(df, 45, _line(df, 45).value(45) * 1.04, vol=3e6)              # 직전 50봉 없음
    r = _det(df)
    assert r.detected and r.metrics["phase"] == "lowvol" and r.stage == FORMING
    assert r.metrics["break"]["vol"] == "unknown" and r.metrics["break"]["vol_ratio"] is None
    assert r.metrics["tl_stage"].startswith("돌파(거래량 모름)")
    parts = r.metrics["score_parts"]
    assert parts["slope"]["s"] is None and parts["entry_flat"]["s"] is None and parts["break_vol"]["s"] is None
    assert r.metrics["score_coverage"] < 1 and any("점수 모름 항목" in w for w in r.warnings)


# ---------------------------------------------------------------- 접점 · 소고점 지연
def test_touch_count_score_three_vs_five():
    df = _tl_df(spikes=(10, 25, 40, 55, 70))
    _bar(df, 110, _line(df, 110).value(110) * 0.99)
    r5 = _det(df)
    assert r5.metrics["line"]["touch_count"] == 5
    assert r5.metrics["score_parts"]["touches"]["s"] == 1.0 and "가점" in r5.metrics["score_parts"]["touches"]["note"]
    df3 = _tl_df()
    _bar(df3, 110, _line(df3, 110).value(110) * 0.99)
    r3 = _det(df3)
    assert r3.metrics["score_parts"]["touches"]["s"] == pytest.approx(1 / 3)
    assert r5.score > r3.score


def test_touch_gap_nine_rejected():
    df = _tl_df(spikes=(10, 40, 49, 70))
    _bar(df, 110, _line(df, 110).value(110) * 0.99)
    assert _det(df).metrics["line"]["touches"] == [10, 40, 70]


def test_pivot_needs_three_right_bars_before_touch():
    df = _tl_df(75)
    _bar(df, 73, _line_cand(df.iloc[:74], 73).value(73) * 0.99)
    r73 = _det(df.iloc[:74])                                           # 봉 70 소고점은 73 EOD 확정 → 72 까지로는 아직
    assert not r73.detected and any("접점 2개" in w for w in r73.warnings)
    _bar(df, 74, _line(df, 74).value(74) * 0.99)
    r74 = _det(df)
    assert r74.metrics["phase"] == "near" and r74.metrics["line"]["touches"] == [10, 40, 70]


# ---------------------------------------------------------------- 동결 · 표시 창
def test_frozen_line_ignores_later_higher_pivot():
    rel = [1.04] + [1.045] * 15
    df, ln = _seq(rel)
    i = 115
    _bar(df, i, df["close"].iloc[i], high=ln.anchor_price * 2.0)       # 앵커보다 높은 새 소고점 (118 확정)
    r = _det(df)
    assert r.metrics["phase"] == "confirmed"
    assert r.metrics["line"]["anchor_i"] == 10 and r.metrics["line"]["slope_ln"] == pytest.approx(ln.slope)
    assert r.metrics["line"]["touches"] == [10, 40, 70] and r.pivot == pytest.approx(ln.value(110))
    (c,) = tq.downtrend_line_candidates(tq.Bars.from_df(df), len(df) - 1)
    assert c.anchor_i == 115                                           # 다시 맞췄다면 다른 선 — 동결이라 그대로


def test_display_window_then_release():
    df, _ = _seq([1.04] + [1.045] * 21)                                # 110 확인 → 110..129 표시
    st = tb.timeline(df)
    assert all(s.phase == "confirmed" for s in st[110:130])
    assert st[130].phase is None                                       # 표시 끝 → 다시 탐색(옛 선은 낡음)
    r = _det(df)
    assert not r.detected and any("표시 끝" in w for w in r.warnings)


# ---------------------------------------------------------------- 바닥 망치형 꼬리표
def test_bottom_hammer_tag_before_breakout():
    df = _tl_df(311, spikes=(210, 240, 270), prefix=200)
    line = lambda i: 100.0 * np.exp(-0.004 * (i - 200))              # noqa: E731
    _bar(df, 300, 0.905 * line(300), open_=0.90 * line(300), high=0.906 * line(300), low=0.84 * line(300))
    b = tq.Bars.from_df(df)
    h = tq.hammer(b, 300)
    assert h["shape"] and h["bottom"] and h["label"] == "양봉 망치"
    _bar(df, 310, _line(df, 310).value(310) * 1.04, vol=3e6)
    r = _det(df)
    assert r.metrics["phase"] == "confirmed" and r.metrics["line"]["anchor_i"] == 210
    assert r.metrics["hammer"]["date"] == f"{df.index[300]:%Y-%m-%d}"
    assert r.metrics["score_parts"]["hammer"]["s"] == 1.0
    assert r.metrics["score_parts"]["entry_flat"]["s"] is not None   # 앵커 앞 20봉 있음
    assert any(a["kind"] == "marker" and a["text"] == "바닥 망치" for a in r.annotations)
    assert any("망치형" in s and tq.BULKOWSKI_LABEL in s for s in r.metrics["bulkowski"])


# ---------------------------------------------------------------- 기울기 기준 (다른 선 중앙값)
def test_slope_ref_uses_other_anchors_in_prior_window():
    cfg = tb.TLBreakConfig()
    slopes = [(10, 5, 0.020), (300, 5, 0.010), (320, 20, 0.004), (330, 30, 0.006), (340, 50, 0.001), (400, 30, 0.9)]
    ref, n = tb.slope_ref(slopes, 400, 50, cfg)                        # 앵커 50 = 지금 선 → 뺌, 400 봉 자신도 뺌
    assert n == 3 and ref == pytest.approx(0.006)                      # 앵커 5 는 창 안 마지막 값 0.010
    assert tb.slope_ref(slopes, 400, 30, cfg) == (pytest.approx(np.median([0.010, 0.004, 0.001])), 3)
    assert tb.slope_ref(slopes[:2], 400, 50, cfg) == (None, 1)         # 다른 선 1개 — 모름


# ---------------------------------------------------------------- 장중 미완성 봉
def test_partial_bar_only_for_provisional_note():
    df = _tl_df(112)
    ln = _line(df, 110)
    _bar(df, 110, ln.value(110) * 0.99)
    eod = _det(df.iloc[:111])
    _bar(df, 111, eod.pivot * 1.03, vol=1e6)                           # 오늘 장중: 다음 봉 선 위
    ctx = make_context(df)
    ctx.partial, ctx.session_frac = True, 0.5
    r = tb.detect(ctx)
    assert r.metrics["asof"] == f"{df.index[110]:%Y-%m-%d}"            # 판정은 어제까지
    assert (r.stage, r.pivot, r.score, r.metrics["phase"]) == (eod.stage, eod.pivot, eod.score, "near")
    pv = r.metrics["provisional"]
    assert pv["event"] == "above_line" and pv["line"] == pytest.approx(eod.pivot)
    base = float(np.mean(df["volume"].iloc[61:111]))
    assert pv["vol_ratio_est"] == pytest.approx(2e6 / base, rel=1e-3)   # 하루치 환산
    assert any("장중 잠정" in w for w in r.warnings)


# ---------------------------------------------------------------- 앞부분 불변
def _states_equal_on_prefix(df, ts):
    full = tb.timeline(df)
    for t in ts:
        assert tb.timeline(df.iloc[:t + 1]) == full[:t + 1], t
        assert tb.timeline(_junk(df, t, seed=t))[:t + 1] == full[:t + 1], t
    return full


def test_prefix_invariance_through_all_phases():
    df, _ = _seq([1.02, 1.031, 1.01, 1.005, 0.99] + [0.90] * 8)
    full = _states_equal_on_prefix(df, range(60, len(df)))
    assert {"far", "pending", "confirmed", "failed"} <= {s.phase for s in full}
    for t in (109, 110, 111, 113, 114):                               # 탐지기 결과도 그 봉의 상태와 같다
        r = _det(df.iloc[:t + 1])
        assert r.metrics["phase"] == full[t].phase
        assert _det(_junk(df, t).iloc[:t + 1]).to_dict() == r.to_dict()


@pytest.mark.parametrize("seed", [3, 11])
def test_prefix_invariance_random(seed):
    df = make_ohlcv([(0, 100), (150, 60), (300, 90), (420, 70)], seed=seed, noise=0.012)
    full = _states_equal_on_prefix(df, range(45, len(df), 9))
    assert len({s.phase for s in full} - {None}) >= 2                 # 의미 있는 시험인지


def test_stage_series_matches_detect_each_bar():
    # 백테스트용 한 번 돌리기 = 날마다 detect (앞부분 불변 덕분)
    df1, _ = _seq([1.02, 1.031, 1.01, 1.005, 0.99] + [0.90] * 3)
    df2 = _tl_df(112)
    _bar(df2, 110, _line(df2, 110).value(110) * 0.99)
    df3 = make_ohlcv([(0, 100), (150, 60), (300, 90), (420, 70)], seed=3, noise=0.012)
    seen = set()
    for df, ts in ((df1, range(100, len(df1))), (df2, (110,)), (df3, range(60, len(df3), 3))):
        ss = tb.stage_series(df)
        for t in ts:
            r = _det(df.iloc[:t + 1])
            s = ss[t]
            if s is None:
                assert not r.detected, t
                continue
            seen.add(s["phase"])
            assert (s["detected"], s["stage"], s["phase"]) == (r.detected, r.stage, r.metrics["phase"]), t
            assert s["pivot"] == pytest.approx(r.pivot) and (s["stop"] is None) == (r.stop is None), t
            if r.stop is not None:
                assert s["stop"] == pytest.approx(r.stop)
            bo = None if s["breakout_i"] is None else f"{df.index[s['breakout_i']]:%Y-%m-%d}"
            assert bo == r.breakout_date, t
    assert {"near", "pending", "confirmed", "failed", "lowvol"} <= seen


# ---------------------------------------------------------------- 출처 · 체크리스트 · 차트 · 직렬화
def test_every_tagged_line_has_origin_and_bulkowski_is_labelled():
    df, _ = _seq([1.04])
    r = _det(df)
    org = r.metrics["origin"]
    for s in r.reasons + r.warnings:
        if s.endswith("]") and "[" in s:
            assert s[s.rindex("[") + 1:-1] in org, s
    for k, v in tb.ORIGIN.items():
        if k not in tq.ORIGIN:                                         # 이 모듈의 규칙은 영상 · URL · 구현 선택 중 하나
            assert any(x in v for x in ("영상 [", "http", "구현 선택")), k
    for k in ("technique", "tl_break", "tl_conf_pct", "tl_freeze", "tl_stage_map", "tl_stop", "tl_pivot", "tl_weights",
              "tl_slope_ref", "tl_touch", "tl_anchor_highest"):
        assert org[k] == tb.ORIGIN[k]                                  # 이 결과가 쓴 규칙의 출처는 결과에 실림
    assert all(p["origin"] in org for p in r.metrics["score_parts"].values())
    assert "origin" not in r.metrics["features"]                       # 한곳(metrics['origin'])에만
    far = _det(_tl_df())
    assert "bulkowski" not in far.metrics and len(far.metrics["origin"]) < len(org)
    assert r.metrics["bulkowski"] and all(s.startswith(tq.BULKOWSKI_LABEL) for s in r.metrics["bulkowski"])
    stats = list(tq.BULKOWSKI_CONTEXT.values())
    assert not any(st in s for st in stats for s in r.reasons + r.warnings)   # 통계는 후보 줄에 안 씀
    assert "우리 데이터 아님" in r.metrics["targets"]["note"]


def test_checklist_unknowns_and_stop_item():
    df = _tl_df()
    _bar(df, 110, _line(df, 110).value(110) * 0.99)
    near = {c["no"]: c for c in _det(df).metrics["checklist"]}
    assert len(near) == 10
    assert near[1]["status"] == "pass"                                 # 시장 국면 상승 확인 (make_context 기본)
    assert all(near[k]["status"] == "unknown" and near[k]["status_label"] == "모름" for k in (2, 4, 5, 8))
    df2, _ = _seq([1.04])
    r = _det(df2)
    brk = {c["no"]: c for c in r.metrics["checklist"]}
    assert brk[8]["status"] != "unknown" and brk[8]["value"]["stop"] == pytest.approx(r.stop)
    assert r.metrics["exit_plan"]["entry_i"] == 110                    # 가정 진입 = 안착 확인 봉


def test_annotations_draw_frozen_line_and_events():
    df, ln = _seq([1.02, 1.031])
    r = _det(df)
    seg = next(a for a in r.annotations if a["kind"] == "segment")
    assert seg["label"] == "하향 추세선 (돌파 때 동결)"
    assert seg["points"][0] == (f"{df.index[10]:%Y-%m-%d}", pytest.approx(ln.anchor_price))
    assert seg["points"][-1][0] == f"{df.index[-1]:%Y-%m-%d}"
    texts = [a["text"] for a in r.annotations if a["kind"] == "marker"]
    assert {"앵커", "접점2", "접점3", "돌파", "안착 확인"} <= set(texts)
    labels = [a["label"] for a in r.annotations if a["kind"] == "hline"]
    assert "돌파가 (돌파일 선 값)" in labels and any("불코우스키" in x and "미국" in x for x in labels)


def test_result_is_plain_json():
    for df in (_seq([1.04])[0], _seq([1.02, 0.99])[0], _tl_df()):
        json.dumps(tb.detect(make_context(df)).to_dict(), ensure_ascii=False, allow_nan=False)
