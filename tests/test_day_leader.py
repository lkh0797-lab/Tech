"""10% 주도주 (단타 관찰) — chart_screener/patterns/day_leader.py.

부록 docs/2026-10-14-chart-techniques-addendum.md §6 · §13 '10% 주도주' (시가 대비 vs 전일 대비) + 공통(앞부분 불변 ·
당일 제외 기준선) + 스펙 §테스트(신호 · 비신호 · 경계 · 체크리스트 '모름')."""
import json

import numpy as np
import pandas as pd
import pytest

from chart_screener import techniques as tq
from chart_screener.config import Config
from chart_screener.patterns import REGISTRY
from chart_screener.patterns import day_leader as dl
from chart_screener.patterns.base import NEAR_PIVOT
from synthetic import add_value, make_context

P = 10000.0          # 신호 전날 종가


# ---------------------------------------------------------------- 도우미
def _base_df(n=60, seed=0, vol=1e6, start="2024-01-02"):
    """잔잔한 일봉(±1%) · 거래량 일정 — 마지막 전 봉 종가 = P."""
    rng = np.random.default_rng(seed)
    c = P * np.cumprod(1 + rng.normal(0, 0.01, n))
    c = c * (P / c[-2])
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * 1.005
    lo = np.minimum(o, c) * 0.995
    v = np.full(n, vol)
    return add_value(pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": v},
                                  index=pd.bdate_range(start, periods=n)))


def _put(df, i, **kw):
    df = df.copy()
    pos = i if i >= 0 else len(df) + i
    for k, v in kw.items():
        df.iloc[pos, df.columns.get_loc(k)] = v
    return add_value(df)


def _sig_df(o=P, h=11300.0, lo=9950.0, c=11200.0, v=5e6, **kw):
    """마지막 봉 = 신호 후보 (기본: 시가 · 전일 대비 +12%, 거래량 5배, 순서 명확)."""
    return _put(_base_df(**kw), -1, open=o, high=h, low=lo, close=c, volume=v)


def _run(df, cfg=None, **kw):
    ctx = make_context(df, cfg=Config(patterns={"day_leader": cfg}) if cfg else None, **kw)
    return REGISTRY["day_leader"][1](ctx)


def _ctx_partial(df, frac=1.0, **kw):
    ctx = make_context(df, **kw)
    ctx.partial = True
    ctx.session_frac = frac
    return ctx


def _junk_future(b: tq.Bars, t: int, seed: int = 0) -> tq.Bars:
    """봉 t 뒤를 엉뚱한 봉으로 — 앞부분 불변 시험용."""
    rng = np.random.default_rng(seed)
    o, h, lo, c, v = (x.copy() for x in (b.open, b.high, b.low, b.close, b.volume))
    k = b.n - t - 1
    if k > 0:
        c[t + 1:] = b.close[t] * rng.uniform(0.3, 3.0, k)
        o[t + 1:] = c[t + 1:] * rng.uniform(0.8, 1.2, k)
        h[t + 1:] = np.maximum(o[t + 1:], c[t + 1:]) * 1.2
        lo[t + 1:] = np.minimum(o[t + 1:], c[t + 1:]) * 0.8
        v[t + 1:] = rng.uniform(0, 1e9, k).round()
    return tq.Bars(o, h, lo, c, v, b.dates)


def _signal_series(n=320, seed=7):
    """무작위 걸음 + 신호 봉 몇 개(이어진 이틀 포함) + 거래량 0 행 하나."""
    rng = np.random.default_rng(seed)
    c = 5000 * np.cumprod(1 + rng.normal(0, 0.015, n))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.004, n))
    v = rng.lognormal(13, 0.3, n).round()
    for j, up in ((40, 0.12), (41, 0.11), (130, 0.15), (210, 0.10), (290, 0.20)):
        o[j] = c[j - 1]
        c[j] = o[j] * (1 + up)
        v[j] = v[j - 25:j].mean() * 6
    v[100] = 0
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)))
    return tq.Bars.from_arrays(o, h, lo, c, v, pd.bdate_range("2023-01-02", periods=n))


# ---------------------------------------------------------------- 등록 · 신호
def test_registered_with_exact_label_and_rule_id():
    assert REGISTRY["day_leader"][0] == "10% 주도주 (단타 관찰)"
    assert dl.LABEL == "10% 주도주 (단타 관찰)"
    assert dl.RULE_VERSION == "dlead_v1"


def test_signal_detected_with_fib_reference_and_no_pivot_or_stop():
    r = _run(_sig_df())
    m = r.metrics
    assert r.detected and r.stage == NEAR_PIVOT
    assert r.pivot is None and r.stop is None and r.breakout_date is None      # 진입 판정 안 함
    assert m["rule_version"] == "dlead_v1"
    assert m["up_open"] == pytest.approx(0.12) and m["up_prev"] == pytest.approx(0.12)
    assert m["vr"] == pytest.approx(5.0) and m["vol_base"] == pytest.approx(1e6)   # 당일 거래량은 기준선 밖
    H, L = 11300.0, 9950.0
    for r_, key in ((0.236, "fib_236"), (0.382, "fib_382"), (0.5, "fib_500"), (0.618, "fib_618")):
        assert m[key] == pytest.approx(H - r_ * (H - L))
    assert [f["buy"] for f in m["fib"]] == [True, True, True, False]               # 61.8 표시만
    assert m["order_ambiguous"] is False and m["basis_agree"] is True
    assert m["entry_note"] == "HTS 3분봉에서 반등 양봉 다음 봉 시가 진입 · 손절 기준선 이탈"
    assert r.start_date == r.end_date == m["signal_date"] == f"{_sig_df().index[-1]:%Y-%m-%d}"
    assert any("진입 판정 안 함" in x for x in r.reasons)
    assert any("과거 검증" in w for w in r.warnings)
    kinds = [a["kind"] for a in r.annotations]
    assert kinds.count("hline") == 6 and kinds.count("marker") == 1


def test_every_rule_records_its_origin():
    m = _run(_sig_df()).metrics
    org = m["origin"]
    for k in ("candidate", "white", "min_chg", "basis", "vol", "fib", "order", "valid", "no_entry", "stage", "score"):
        assert org[k]
    for k, s in org.items():
        assert "영상 [" in s or "http" in s or "구현 선택" in s or "스펙" in s, k
    assert "영상 [33:00–39:00]" in org["candidate"]
    assert "5110.htm" in org["min_chg"] and "tilnote.io" in org["basis"]
    assert org["vol"].startswith("구현 선택") and org["order"].startswith("구현 선택")
    assert "구현 선택" in m["stage_rule"]


def test_score_is_bounded_documented_and_monotone_in_volume():
    lo_v, hi_v, cap = (_run(_sig_df(v=x)) for x in (3e6, 1e7, 3e7))
    assert lo_v.metrics["score_parts"]["vol"] == pytest.approx(0.0)      # 3배 = 몫 0
    assert hi_v.metrics["score_parts"]["vol"] == pytest.approx(25.0)     # 10배 = 만점
    assert cap.score == pytest.approx(hi_v.score)                        # 상한
    assert lo_v.score < hi_v.score <= 100.0
    p = hi_v.metrics["score_parts"]
    assert hi_v.score == pytest.approx(sum(p.values()))
    assert any("확률 아님" in x for x in hi_v.reasons)


def test_result_is_json_serialisable():
    s = json.dumps(_run(_sig_df()).to_dict(), ensure_ascii=False, allow_nan=False)
    assert "dlead_v1" in s


def test_common_checklist_and_exit_plan_attached():
    m = _run(_sig_df()).metrics
    ck = m["checklist"]
    assert [c["no"] for c in ck] == list(range(1, 11))
    assert sum(m["checklist_counts"].values()) == 10
    assert "ma5" in m["exit_plan"] and "ma10" in m["exit_plan"]


# ---------------------------------------------------------------- 비신호
@pytest.mark.parametrize("kw, why", [
    ({"c": 10990.0, "h": 11000.0}, "< 10%"),                 # 시가 대비 +9.9%
    ({"v": 2.9e6}, "2.90배 < 3배"),                          # 거래량 부족
    ({"o": 11200.0, "c": 10000.0, "h": 11300.0, "lo": 9950.0}, "양봉 아님"),   # 음봉
])
def test_non_signal_explains_why(kw, why):
    r = _run(_sig_df(**kw))
    assert not r.detected and r.stage is None
    assert any(why in w for w in r.warnings), r.warnings


def test_doji_is_not_white():
    df = _put(_base_df(), -1, open=P, high=11300.0, low=9950.0, close=P, volume=5e6)
    r = _run(df)
    assert not r.detected and any("양봉 아님" in w for w in r.warnings)


# ---------------------------------------------------------------- 경계
def test_exactly_ten_percent_and_exactly_three_times_volume_pass():
    r = _run(_sig_df(c=11000.0, h=11050.0, v=3e6))
    assert r.detected
    # 부동소수: 3.3 / 3 − 1 = 0.0999…87 도 10% 로 본다(상대 1e-9)
    b = tq.Bars.from_arrays([3.0] * 22, [3.4] * 22, [2.9] * 22, [3.0] * 21 + [3.3], [1e6] * 21 + [3e6])
    assert 3.3 / 3.0 - 1 < 0.10
    assert dl.judge(b, 21)["ok"]


def test_order_ambiguity_boundary():
    # (O − L)/(H − L) = 0.3 정확히 → 불명 아님(> 엄격), 0.4 → 불명
    ok = _run(_sig_df(o=P, lo=9400.0, h=11400.0, c=11200.0))
    assert ok.detected and ok.metrics["order_pos"] == pytest.approx(0.3) and ok.metrics["order_ambiguous"] is False
    amb = _run(_sig_df(o=P, lo=9000.0, h=11500.0, c=11200.0))
    assert amb.detected and amb.metrics["order_ambiguous"] is True
    assert amb.metrics["score_parts"]["order"] == 0.0
    assert any("순서 불명" in w for w in amb.warnings)


def test_baseline_excludes_today_and_zero_volume_rows():
    df = _sig_df(v=4e6)
    df = _put(df, -5, volume=0)                     # 정지 행(거래량 0) — 평균에서 뺀다
    r = _run(df)
    assert r.metrics["vol_base"] == pytest.approx(1e6) and r.metrics["vr"] == pytest.approx(4.0)
    v = df["volume"].to_numpy()
    assert tq.prior_mean(v, 20)[-1] < 1e6          # volume 없이 부른 prior_mean 은 0 행을 넣어 기준선이 낮아짐
    assert tq.vol_ratio(v, 20)[-1] == pytest.approx(4.0)   # 코어 vol_ratio 도 이제 0 행을 뺀다(부록 §0.2)
    np.testing.assert_allclose(dl.vol_baseline(v, 20), tq.prior_mean(v, 20, volume=v), equal_nan=True)
    # 0 행이 없으면 core prior_mean 과 같다
    w = np.r_[np.full(49, 1e6), 1e9, 1e6, 3e6]
    np.testing.assert_allclose(dl.vol_baseline(w, 20), tq.prior_mean(w, 20), equal_nan=True)


# ---------------------------------------------------------------- 부록 §13 — 시가 대비 vs 전일 대비
def test_gap_up_then_small_rise_open_vs_prev_close():
    # 갭 +8% 뒤 시가 대비 +3% → 전일 대비 +11.24%
    o = P * 1.08
    df = _sig_df(o=o, c=o * 1.03, h=o * 1.035, lo=o * 0.998)
    r_open = _run(df)
    assert not r_open.detected and any("시가 대비 +3.0% < 10%" in w for w in r_open.warnings)
    r_prev = _run(df, cfg=dl.DayLeaderConfig(basis="prev_close"))
    assert r_prev.detected and r_prev.metrics["up_prev"] == pytest.approx(0.1124)
    assert r_prev.metrics["basis_agree"] is False
    assert any("시가 대비 +3.0% < 10%" in w and "후보 아님" in w for w in r_prev.warnings)


def test_gap_down_then_big_rise_open_vs_prev_close():
    # 갭 −5% 뒤 시가 대비 +11% → 전일 대비 +5.45%
    o = P * 0.95
    df = _sig_df(o=o, c=o * 1.11, h=o * 1.115, lo=o * 0.995)
    r_open = _run(df)
    assert r_open.detected and r_open.metrics["up_open"] == pytest.approx(0.11)
    assert r_open.metrics["up_prev"] == pytest.approx(0.0545)
    assert r_open.metrics["score_parts"]["agree"] == 0.0
    assert any(w.startswith("전일 대비 +5.") and "후보 아님" in w for w in r_open.warnings)
    assert not _run(df, cfg=dl.DayLeaderConfig(basis="prev_close")).detected


# ---------------------------------------------------------------- 앞부분 불변
def test_prefix_invariance_frame_judge_and_replay():
    b = _signal_series()
    full = dl.signal_frame(b)
    assert full["ok"].sum() >= 4
    for t in range(b.n):
        cut = dl.signal_frame(b.cut(t))
        pd.testing.assert_frame_equal(full.iloc[:t + 1], cut)
        jb = _junk_future(b, t, seed=t)
        j = dl.judge(b, t)
        assert dl._row(full, b, t, dl.DayLeaderConfig()) == j          # 탐지기가 쓰는 전체 표의 줄 = 잘라 낸 판정
        assert dl.judge(jb, t) == j
        assert dl.replay_signals(b, t) == dl.replay_signals(jb, t) == dl.replay_signals(b, t, fr=full)


def test_prefix_invariance_detect_on_truncated_frames():
    b = _signal_series()
    df = b.frame()
    df["value"] = df["close"] * df["volume"]
    ok = dl.signal_frame(b)["ok"].to_numpy()
    for t in sorted({30, 39, 40, 41, 42, 129, 130, 131, 209, 210, 211, 289, 290, 291, b.n - 1}):
        r = _run(df.iloc[:t + 1])                   # 봉 t 까지만 준 탐지 = 전체 표의 봉 t 판정
        assert r.detected == bool(ok[t]), t
        j = dl.judge(b, t)
        for k in ("up_open", "up_prev", "vr"):
            assert r.metrics[k] == j[k], (t, k)
        if ok[t]:
            assert r.score == pytest.approx(j["score"]) and r.metrics["fib_382"] == j["fib"][1]["price"]


def test_replay_uses_only_signals_twenty_bars_old():
    b = _signal_series()
    ok = np.flatnonzero(dl.signal_frame(b)["ok"].to_numpy())
    t = int(ok[2]) + 25
    rp = dl.replay_signals(b, t)
    assert [x["date"] for x in rp] == [b.date(int(j)) for j in ok if j + 20 <= t]
    j = int(ok[0])
    assert rp[0]["ret20"] == pytest.approx(b.close[j + 20] / b.open[j + 1] - 1)


# ---------------------------------------------------------------- 모름 처리
def test_short_history_is_unknown_not_signal():
    df = _sig_df(n=15)
    r = _run(df)
    assert not r.detected
    assert r.metrics["vr"] is None
    assert any("이력 부족" in w and "모름" in w for w in r.warnings)


def test_prev_close_basis_without_previous_bar_is_unknown():
    b = tq.Bars.from_arrays([100.0], [115.0], [99.0], [112.0], [1e6])
    j = dl.judge(b, 0, dl.DayLeaderConfig(basis="prev_close"))
    assert not j["known"] and not j["ok"] and j["up_prev"] is None
    assert any("전일 종가 없음" in x for x in j["fails"])


def test_checklist_unknown_items_without_external_data():
    ctx = make_context(_sig_df())
    ctx.market_state = None
    r = REGISTRY["day_leader"][1](ctx)
    ck = {c["no"]: c for c in r.metrics["checklist"]}
    for no in (1, 2, 5):                                 # 시장 국면 · 업종 · 업종 RS 자료 없음
        assert ck[no]["status"] == "unknown" and ck[no]["status_label"] == "모름"
    assert ck[4]["status"] == "unknown" and "표본 적음" in ck[4]["note"]
    assert ck[8]["status"] == "unknown"                  # 기법 손절 없음
    assert r.metrics["checklist_counts"]["unknown"] >= 5


def test_halt_in_volume_window_flags_and_drops_volume_points():
    df = _sig_df(v=1e7)
    halt = f"{df.index[-4]:%Y-%m-%d}"
    df = df.drop(df.index[-4])                       # 공용 로더처럼 정지일 행을 빼고 attrs 에 남긴다
    df.attrs["halt_dates"] = [halt]
    r = _run(df)
    assert r.detected and r.metrics["volume_unverified"] is True and r.metrics["halts"] == [halt]
    assert r.metrics["score_parts"]["vol"] == 0.0
    assert any("거래정지일" in w for w in r.warnings)


def test_pre_2015_price_limit_note():
    r = _run(_sig_df(start="2014-01-02"))
    assert r.detected and r.metrics["limit_regime"].startswith("±15%")
    assert any("±15%" in w for w in r.warnings)


# ---------------------------------------------------------------- 관찰일 · 장중 잠정
def test_signal_expires_after_observation_day():
    df = _sig_df()
    nxt = df.index[-1] + pd.offsets.BDay(1)
    row = pd.DataFrame({"open": 11100.0, "high": 11150.0, "low": 10700.0, "close": 10900.0, "volume": 2e6}, index=[nxt])
    r = _run(add_value(pd.concat([df[["open", "high", "low", "close", "volume"]], row])))
    assert not r.detected
    w = next(x for x in r.warnings if "직전 신호" in x)
    assert "지남" in w and "38.2% 라인까지" in w


def _with_today(df, o, h, lo, c, v):
    nxt = df.index[-1] + pd.offsets.BDay(1)
    row = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": v}, index=[nxt])
    return add_value(pd.concat([df[["open", "high", "low", "close", "volume"]], row]))


def test_intraday_observation_day_breaks_618_is_warning_only():
    df = _with_today(_sig_df(), 11000.0, 11050.0, 10300.0, 10400.0, 1e6)
    r = REGISTRY["day_leader"][1](_ctx_partial(df))
    assert r.detected and r.stage == NEAR_PIVOT                              # 일봉 EOD · 완성 봉만 — 장중 값은 단계를 안 바꿈
    it = r.metrics["intraday"]
    assert it["below_invalid"] is True and it["deepest"] == "61.8%"
    assert r.metrics["signal_date"] == f"{df.index[-2]:%Y-%m-%d}"            # 신호는 완성 봉
    assert any("장중 잠정" in w and "관찰 끝" in w for w in r.warnings)


def test_intraday_observation_day_holding_keeps_stage():
    df = _with_today(_sig_df(), 11350.0, 11400.0, 10800.0, 11000.0, 1e6)
    r = REGISTRY["day_leader"][1](_ctx_partial(df))
    assert r.detected and r.stage == NEAR_PIVOT
    it = r.metrics["intraday"]
    assert it["gap_above_high"] is True and it["deepest"] == "23.6%" and it["zone"] == "신호일 고가 ~ 23.6%"
    assert any("3분봉 판정 아님" in w for w in r.warnings)


def test_today_partial_bar_only_provisional_with_projected_volume():
    base = _base_df()
    df = _with_today(base, P, 11300.0, 9950.0, 11200.0, 1.5e6)
    r = REGISTRY["day_leader"][1](_ctx_partial(df, frac=0.25))       # 하루치 환산 6백만 = 6배
    # 일봉 EOD · 완성 봉만: 오늘 미완성 봉만 충족이면 탐지하지 않고 경고 줄 · 수치로만 알린다
    assert not r.detected and r.stage is None and r.metrics["provisional"] is True
    assert r.metrics["provisional_today"]["vr"] == pytest.approx(6.0)
    assert any("장중 잠정" in w and "완성 봉만" in w for w in r.warnings) and not r.annotations
    # 환산 없으면(체결 비율 모름) 1.5배 — 후보 아님, 미완성 봉은 완성 봉 판정에 안 쓴다
    r2 = REGISTRY["day_leader"][1](_ctx_partial(df, frac=1.0))
    assert not r2.detected
    assert any("장중 스캔" in w for w in r2.warnings)


def test_partial_bar_never_counts_as_completed_signal():
    # 어제 = 신호 아님, 오늘 미완성 봉이 거대 음봉이어도 아무것도 만들지 않음
    df = _with_today(_base_df(), 11500.0, 11600.0, 9000.0, 9100.0, 9e6)
    r = REGISTRY["day_leader"][1](_ctx_partial(df, frac=0.5))
    assert not r.detected
