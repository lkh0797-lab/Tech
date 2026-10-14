"""피보나치 눌림 반등(patterns/fib_pullback.py) — 합성 봉으로 신호 · 비신호 · 경계(부록 §13 피보) · 앞부분 불변 · '모름' 처리.

기본 그림: 0~39 평평한 바닥(몸통 0.3 · 거래량 1e6) → 40 장대양봉(+12.3%, 거래량 3배) → 43 고점 130 → 44 음봉(고점 확정)
→ 45 눌림 → 46 38.2% 라인 접촉 → 47 거래량 실린 반등 양봉(신호). L = 99.5 (확정 fractal 고점 없음 → 60봉 최저).
라인: 23.6% 122.802 · 38.2% 118.349 · 50% 114.75 · 61.8% 111.151."""
import json

import numpy as np
import pandas as pd
import pytest

from chart_screener import techniques as tq
from chart_screener.patterns import REGISTRY
from chart_screener.patterns import fib_pullback as fp
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from synthetic import add_value, make_context

H, L = 130.0, 99.5
LV = tq.fib_levels(H, L)


def _base(n=40):
    rows = []
    for k in range(n):
        c = 100.3 if k % 2 == 0 else 99.7
        rows.append([100.0, max(100.0, c) + 0.2, min(100.0, c) - 0.2, c, 1e6])
    return rows


UP = [[100, 112.5, 99.8, 112, 3e6], [112, 119, 111.5, 118, 2e6], [118, 125, 117.5, 124, 2e6],
      [124, 130, 123.5, 129, 2e6]]                                   # 40 장대양봉 ~ 43 고점
CONF = [129, 129.5, 125.5, 126, 1.5e6]                               # 44 음봉 → 고점 확정
DIP = [126, 126.2, 120.5, 121, 1.2e6]                                # 45 눌림 (접촉 없음, 38.2% 접근)
TOUCH = [121, 121.3, 118.0, 119, 0.8e6]                              # 46 38.2% 접촉
REB = [119, 122.5, 118.8, 122, 2.5e6]                                # 47 반등 양봉 (신호)
HOLDB = [122.5, 124, 122.2, 123.5, 1.2e6]                            # 신호 뒤 진입 ~ +5% 사이
QUIET = [118.5, 119.0, 117.0, 117.5, 0.7e6]                          # 접촉 없는 음봉 (저가 > 50% 밴드 · 종가 < 38.2%)
REB_NT = [120.5, 122.7, 120.3, 122.5, 3e6]                           # 접촉 없는 반등 양봉 (저가 > 38.2% 밴드)


def _df(rows, start="2024-01-02"):
    a = np.asarray(rows, dtype=float)
    idx = pd.bdate_range(start, periods=len(a))
    return add_value(pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3],
                                   "volume": a[:, 4]}, index=idx))


def _rows(*tail):
    return _base() + UP + [list(r) for r in tail]


def _bars(rows):
    return tq.Bars.from_df(_df(rows))


def _snaps(rows, cfg=None):
    return fp.run(_bars(rows), cfg, record=True).snaps


def _detect(rows, cfg=None, **kw):
    ctx = make_context(_df(rows), **kw)
    if cfg is not None:
        ctx.cfg.patterns[fp.NAME] = cfg
    return fp.detect(ctx)


SIGNAL_ROWS = _rows(CONF, DIP, TOUCH, REB)


# ---------------------------------------------------------------- 등록 · 신호
def test_registered_label_rule_id_and_origins():
    assert REGISTRY["fib_pullback"][0] == "피보나치 눌림 반등"
    assert fp.RULE_ID == "fibpb_v1" and fp.WINDOW == 5
    r = _detect(SIGNAL_ROWS)
    assert r.label == "피보나치 눌림 반등" and r.metrics["rule_version"] == "fibpb_v1"
    for k, v in r.metrics["origin"].items():         # 규칙마다 출처: 영상 [mm:ss] · URL · 구현 선택
        assert ("영상 [" in v) or ("http" in v) or ("구현 선택" in v) or ("스펙" in v), k
    assert any("영상 [" in x for x in r.reasons)
    json.dumps(r.to_dict(), ensure_ascii=False, allow_nan=False)    # 리포트로 그대로 나갈 수 있다


def test_signal_entry_close_stop_next_line():
    r = _detect(SIGNAL_ROWS)
    assert r.detected and r.stage == BREAKOUT and r.metrics["phase"] == "SIGNAL"
    assert r.pivot == 122.0 and r.stop == pytest.approx(LV[0.5])       # 38.2 접촉 → 손절 50% 라인
    assert r.breakout_date == r.end_date == "2024-03-07"
    m = r.metrics
    assert m["wave_low"] == L and m["wave_high"] == H and m["active_level"] == 0.382
    assert m["confirm_date"] == "2024-03-04" and m["trigger_date"] == "2024-02-27"
    assert m["stop_alt"] == pytest.approx(122 * 0.93) and m["l_mode"] == "min_lookback"
    assert m["fib_382"] == pytest.approx(LV[0.382]) and m["fib_618"] == pytest.approx(LV[0.618])
    assert 0 < r.score <= 100 and m["score_coverage"] == 1.0
    assert len(m["checklist"]) == 10 and m["exit_plan"]["entry_i"] == len(SIGNAL_ROWS) - 1
    kinds = {a["kind"] for a in r.annotations}
    assert {"segment", "hline", "marker"} <= kinds
    labels = [a.get("label", a.get("text")) for a in r.annotations]
    assert "피보 50% 관심 구간 · 손절" in labels and "61.8% 무효선" in labels and "신호" in labels


def test_phases_before_signal():
    s = _snaps(SIGNAL_ROWS)
    ph = [x["phase"] for x in s[38:48]]
    assert ph == ["NONE", "NONE", "CANDIDATE", "CANDIDATE", "CANDIDATE", "CANDIDATE",
                  "APPROACH", "APPROACH", "TOUCH", "SIGNAL"]
    r = _detect(_rows(CONF, DIP, TOUCH))
    assert r.detected and r.stage == NEAR_PIVOT and r.metrics["phase"] == "TOUCH"
    assert r.pivot is None and r.stop == pytest.approx(LV[0.5])       # 예정 손절 (신호 전)
    assert r.metrics["score_coverage"] == 0.75                         # 반등 거래량은 아직 모름


def test_intraday_pierce_below_618_is_warned_not_invalid():
    pierce = [121, 121.3, LV[0.618] * 0.995, 119, 0.8e6]   # 저가 61.8% 아래 · 종가 38.2% 위
    r = _detect(_rows(CONF, DIP, pierce))
    assert r.detected and r.metrics["phase"] != "INVALID"
    assert any("무효는 아님" in w for w in r.warnings)


def test_low_volume_rebound_is_not_signal():
    weak = [119, 122.5, 118.8, 122, 1.0e6]
    r = _detect(_rows(CONF, DIP, TOUCH, weak))
    assert r.detected and r.stage == NEAR_PIVOT and r.metrics["phase"] == "TOUCH" and r.pivot is None
    assert any("상향돌파하지 않음" in w for w in r.warnings)


# ---------------------------------------------------------------- 고점 확정
def test_high_needs_future_bar_and_trigger_day_is_not_high():
    s = _snaps(_rows(CONF))
    assert s[43]["phase"] == "CANDIDATE" and s[43]["c"] is None       # 43 고점 — 다음 봉이 있어야 확정
    assert s[44]["phase"] != "CANDIDATE" and s[44]["c"] == 44
    # 장대양봉 다음 날 바로 음봉이면 장대양봉 고가가 H (당일엔 확정 안 됨)
    rows = _base() + [UP[0], [112, 112.4, 109, 110, 1.5e6]]
    s = _snaps(rows)
    assert s[40]["phase"] == "CANDIDATE" and s[41]["c"] == 41 and s[41]["H"] == 112.5 and s[41]["h"] == 40


def test_fractal2_confirms_two_bars_later():
    cfg = fp.FibPullbackConfig(swing_confirm="fractal2")
    s = _snaps(_rows(CONF, DIP, TOUCH), cfg)
    assert s[44]["phase"] == "CANDIDATE" and s[45]["c"] == 45


def test_new_high_after_confirm_back_to_candidate():
    hi = [129, 131, 128, 130.5, 1.5e6]
    down = [130.5, 130.8, 127, 127.5, 1.2e6]
    s = _snaps(_rows(CONF, hi, down))
    assert s[44]["c"] == 44 and s[45]["phase"] == "CANDIDATE" and s[45]["H"] == 131 and s[45]["touch_bar"] is None
    assert s[46]["c"] == 46 and s[46]["H"] == 131


# ---------------------------------------------------------------- 접촉 경계
def test_touch_boundary_exact_tolerance_and_close_below_line():
    exact = [121, 121.3, LV[0.382] * 1.015, 120.5, 0.8e6]           # 저가 = 라인 × 1.015 정확히 → 접촉
    s = _snaps(_rows(CONF, DIP, exact))
    assert s[46]["phase"] == "TOUCH" and s[46]["active_r"] == 0.382
    over = [121, 121.3, LV[0.382] * 1.015 * (1 + 1e-6), 120.5, 0.8e6]  # 조금 위 → 접촉 아님(라인 접근)
    s = _snaps(_rows(CONF, DIP, over))
    assert s[46]["touch_bar"] is None and s[46]["phase"] == "APPROACH"
    below = [121, 121.3, 118.0, LV[0.382] * (1 - 0.0001), 0.8e6]   # 종가가 라인보다 0.01% 아래 → 접촉 아님
    s = _snaps(_rows(CONF, DIP, below))
    assert s[46]["touch_bar"] is None and s[46]["phase"] == "WAIT"


def test_wick_vs_band_two_percent_pierce():
    pierce = [126, 126.2, LV[0.236] * 0.98, 123.0, 1.2e6]
    w = _snaps(_rows(CONF, pierce))
    b = _snaps(_rows(CONF, pierce), fp.FibPullbackConfig(touch_mode="band"))
    assert w[45]["phase"] == "TOUCH" and w[45]["active_r"] == 0.236
    assert b[45]["touch_bar"] is None


# ---------------------------------------------------------------- 거래량 · 신호 창
def test_vol_ma5_includes_today_boundary():
    m4 = (2e6 + 1.5e6 + 1.2e6 + 0.8e6) / 4                             # V[43..46] 평균 = 1.375e6
    eq = [119, 122.5, 118.8, 122, m4]
    up = [119, 122.5, 118.8, 122, m4 + 1000]
    assert _snaps(_rows(CONF, DIP, TOUCH, eq))[47]["phase"] == "TOUCH"     # V = MA5V(오늘 포함) → 돌파 아님
    assert _snaps(_rows(CONF, DIP, TOUCH, up))[47]["phase"] == "SIGNAL"
    assert m4 + 1000 < np.mean([2e6, 2e6, 1.5e6, 1.2e6, 0.8e6])           # 오늘 뺀 직전 5봉 평균이면 미달이었을 값


def test_cross_vs_level_when_touch_day_volume_was_big():
    big_touch = [121, 121.3, 118.0, 119, 3e6]
    reb = [119, 122.5, 118.8, 122, 5e6]
    rows = _rows(CONF, DIP, big_touch, reb)
    assert _snaps(rows)[47]["phase"] == "TOUCH"                                       # cross: 전일이 이미 이평 위
    assert _snaps(rows, fp.FibPullbackConfig(vol_test="level"))[47]["phase"] == "SIGNAL"


def test_signal_window_third_bar_ok_fourth_rejected():
    ok = _snaps(_rows(CONF, DIP, TOUCH, QUIET, QUIET, REB_NT))
    assert ok[49]["phase"] == "SIGNAL" and ok[49]["touch_bar"] == 46 and ok[49]["stop"] == pytest.approx(LV[0.5])
    late = _snaps(_rows(CONF, DIP, TOUCH, QUIET, QUIET, QUIET, REB_NT))
    assert late[49]["phase"] == "TOUCH" and late[50]["phase"] == "WAIT" and late[50]["s"] is None


# ---------------------------------------------------------------- 신호 뒤
def test_after_signal_hold_extended_retest_and_window():
    s = _snaps(SIGNAL_ROWS + [HOLDB] * 5)
    assert [x["phase"] for x in s[47:53]] == ["SIGNAL", "HOLD", "HOLD", "HOLD", "HOLD", "STALE"]
    r = _detect(SIGNAL_ROWS + [HOLDB] * 4)
    assert r.stage == BREAKOUT and r.breakout_date == "2024-03-07" and r.metrics["bars_since_signal"] == 4
    r = _detect(SIGNAL_ROWS + [HOLDB] * 5)
    assert not r.detected and any("표시 창 5봉 지남" in w for w in r.warnings)
    r = _detect(SIGNAL_ROWS + [[122, 129, 121.8, 128.5, 2e6]])
    assert r.stage == EXTENDED and r.metrics["phase"] == "EXTENDED"
    r = _detect(SIGNAL_ROWS + [[122, 122.5, 119.5, 120, 1e6]])
    assert r.stage == NEAR_PIVOT and r.metrics["phase"] == "RETEST" and r.breakout_date == "2024-03-07"


def test_gap_down_stop_fill_and_failed_stage():
    gap = [110, 112, 109, 111, 3e6]
    r = _detect(SIGNAL_ROWS + [HOLDB, gap])
    assert r.stage == FAILED and r.metrics["phase"] == "STOPPED"
    assert r.metrics["stop_fill"] == 110.0                     # min(시가 110, 손절 114.75) — 갭 하락
    assert r.metrics["invalid_after_signal_date"] == r.metrics["stop_hit_date"]   # 61.8% 아래 종가도 같은 날(표시만)


# ---------------------------------------------------------------- 무효 · 만료
def test_close_below_618_invalid():
    crash = [126, 126.5, 110, 110.5, 2e6]
    s = _snaps(_rows(CONF, crash))
    assert s[45]["phase"] == "INVALID" and s[45]["end"] == 45
    r = _detect(_rows(CONF, crash))
    assert not r.detected and any("무효" in w and "61.8%" in w for w in r.warnings)


def test_setup_expiry_after_30_bars():
    side = [127.5, 128.5, 127, 128, 1e6]
    rows = _rows(CONF, *([side] * 31))
    s = _snaps(rows)
    assert s[74]["phase"] == "WAIT" and s[75]["phase"] == "EXPIRED"     # c=44: t−c = 30 유지, 31 만료
    assert _detect(rows[:75]).stage == FORMING and not _detect(rows).detected


def test_candidate_expires_without_confirmation():
    rise = [[112 + k, 113.2 + k, 111.8 + k, 113 + k, 1.2e6] for k in range(25)]   # 매일 신고가 · 종가 상승
    s = _snaps(_base() + [UP[0]] + rise)
    assert s[60]["phase"] == "CANDIDATE" and s[61]["phase"] == "EXPIRED"   # t−b > 20


# ---------------------------------------------------------------- 장대양봉 · 파동 저점
def test_gap_up_small_body_is_not_long_white():
    gap = [111.5, 112.5, 111.3, 112, 3e6]                    # 전일 대비 +12% 지만 몸통 0.5 < 0.3 × 3
    lw = tq.long_white(_bars(_base() + [gap]), 40)
    assert lw["chg_ok"] and not lw["body_ok"] and not lw["ok"]
    r = _detect(_base() + [gap])
    assert not r.detected and r.metrics["phase"] == "NONE"


def test_wave_low_since_swing_high_vs_min_lookback():
    rows = _base()
    rows[5] = [100.0, 100.5, 90.0, 100.3, 1e6]               # 오래된 깊은 저점
    rows[30] = [100.0, 102.0, 99.8, 100.3, 1e6]              # fractal-2 고점 (p+2 ≤ b)
    rows = rows + UP + [CONF]
    a = _snaps(rows)[44]
    b = _snaps(rows, fp.FibPullbackConfig(l_mode="min_lookback"))[44]
    assert a["L"] == 99.5 and a["l_i"] > 30                   # 30 뒤 최저
    assert b["L"] == 90.0 and b["l_i"] == 5
    r = _detect(rows)
    assert r.metrics["l_mode"] == "since_swing_high" and r.metrics["l_swing_high_date"] == "2024-02-13"


def test_long_white_during_candidate_is_absorbed():
    rows = _base() + [UP[0], [112, 126, 111.8, 125.5, 3e6], [125.5, 128, 125, 127.5, 2e6],
                      [127.5, 130, 127, 129, 2e6], CONF]
    s = _snaps(rows)
    assert s[44]["b"] == 40 and s[44]["L"] == L
    assert _detect(rows).metrics["absorbed"] == ["2024-02-28"]


# ---------------------------------------------------------------- 장중 잠정
def _partial_ctx(rows, frac=0.5):
    ctx = make_context(_df(rows))
    ctx.partial, ctx.session_frac = True, frac
    return ctx


def test_partial_bar_provisional_signal_uses_scaled_volume():
    half = [119, 122.5, 118.8, 122, 1.0e6]                   # 하루치 환산 2.0e6 > 이평 → 잠정 신호
    r = fp.detect(_partial_ctx(_rows(CONF, DIP, TOUCH, half)))
    # 일봉 EOD · 완성 봉만: 장중 잠정 신호는 경고 줄 · 수치에만, 단계 · 진입가는 어제까지 완성 봉(접촉)
    assert r.detected and r.stage == NEAR_PIVOT and r.pivot is None and r.metrics["phase"] == "TOUCH"
    assert r.metrics["provisional"] is True and r.metrics["provisional_phase"] == "SIGNAL"
    assert r.end_date == "2024-03-06" and "signal_date" not in r.metrics
    assert any("장중 잠정" in w and "'신호'" in w and "완성 봉" in w for w in r.warnings)
    full = _detect(_rows(CONF, DIP, TOUCH, half))            # 같은 봉을 완성 봉으로 보면 거래량 미달
    assert full.metrics["phase"] == "TOUCH"


def test_partial_bar_ignored_unless_signal():
    black = [119, 119.5, 118.6, 118.7, 0.3e6]
    r = fp.detect(_partial_ctx(_rows(CONF, DIP, TOUCH, black)))
    assert r.stage == NEAR_PIVOT and r.metrics["provisional"] is False
    assert r.end_date == "2024-03-06"                        # 판정 봉 = 마지막 완성 봉(46)
    assert any("장중 스캔" in w for w in r.warnings)


# ---------------------------------------------------------------- 모름 처리
def test_short_history_unknown():
    r = _detect(_base(15))
    assert not r.detected and r.metrics["phase"] == "UNKNOWN" and any("이력 부족" in w for w in r.warnings)


def test_zero_volume_no_trigger():
    rows = [r[:4] + [0.0] for r in SIGNAL_ROWS]
    r = _detect(rows)
    assert not r.detected and r.metrics["phase"] == "NONE"


def test_zero_volume_baseline_is_unknown_not_trigger():
    rows = [r[:4] + [0.0] for r in _base()] + [UP[0]]       # 직전 20봉 거래량 0 → 배수 inf
    b = _bars(rows)
    assert not fp.run(b).lw_ok[40]                          # 기준선 0 = 모름
    lw = tq.long_white(b, 40)                               # 공용 부품도 이제 모름(예전엔 배수 inf 를 통과로 봄)
    assert not lw["ok"] and not lw["known"] and not lw["vol_ok"]
    assert _detect(rows).metrics["phase"] == "NONE"


def test_checklist_unknown_without_external_data():
    ctx = make_context(_df(SIGNAL_ROWS), info={})
    ctx.market_state = None
    r = fp.detect(ctx)
    ck = {c["no"]: c for c in r.metrics["checklist"]}
    for no in (1, 2, 4, 5):
        assert ck[no]["status"] == "unknown" and ck[no]["status_label"] == "모름"
    assert ck[8]["value"]["stop"] == pytest.approx(LV[0.5])  # 기법 손절이 체크 8 로 들어감
    assert r.metrics["checklist_counts"]["unknown"] >= 4


def test_replay_only_signals_with_20_bars_passed():
    rows = SIGNAL_ROWS + [HOLDB] * 20
    rows += [[123.5, 136.5, 123.2, 136, 4e6], [136, 140, 135.5, 139.5, 2e6], [139.5, 139.8, 136.5, 137, 1.2e6],
             [137, 137.2, 134.4, 135, 0.8e6], [135, 137.5, 134.6, 137.2, 3e6]]
    m = fp.run(_bars(rows))
    T = len(rows) - 1
    assert [x.state for x in m.history].count("SIGNAL") == 2
    rep = fp._replay(m, T, fp.FibPullbackConfig())
    assert len(rep) == 1 and rep[0]["date"] == "2024-03-07"
    assert rep[0]["ret20"] == pytest.approx(123.5 / 122 - 1)
    assert fp._replay(m, 47 + 19, fp.FibPullbackConfig()) == []


def test_score_scale_and_coverage():
    cfg = fp.FibPullbackConfig()
    s, cov, _ = fp.score_parts(cfg, 3.0, 2.0, 0.236, 1.0)               # 모두 관문 값 → 50
    assert s == pytest.approx(50) and cov == 1.0
    assert fp.score_parts(cfg, 12.0, 20.0, 0.5, 3.0)[0] == pytest.approx(100)
    s, cov, parts = fp.score_parts(cfg, 6.0, None, None, None)          # 모르는 항목은 빼고 나눔
    assert cov == 0.25 and s == pytest.approx(100 * parts["body"]["s"]) and 50 < s < 100
    assert fp.score_parts(cfg, None, None, None, None)[:2] == (0.0, 0.0)


def test_bulkowski_numbers_only_with_label():
    r = _detect(SIGNAL_ROWS)
    for line in r.reasons + r.warnings:
        if "59%" in line or "58%" in line:
            assert tq.BULKOWSKI_LABEL in line
    assert all(x.startswith(tq.BULKOWSKI_LABEL) for x in r.metrics["bulkowski"])
    assert not any("확률" in x and "아님" not in x and "아니다" not in x for x in r.reasons + r.warnings)


# ---------------------------------------------------------------- 앞부분 불변
def _junk_future(df: pd.DataFrame, t: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = df.copy()
    k = len(df) - t - 1
    if k > 0:
        c = df["close"].iloc[t] * rng.uniform(0.3, 3.0, k)
        o = c * rng.uniform(0.8, 1.2, k)
        out.iloc[t + 1:, out.columns.get_loc("close")] = c
        out.iloc[t + 1:, out.columns.get_loc("open")] = o
        out.iloc[t + 1:, out.columns.get_loc("high")] = np.maximum(o, c) * 1.2
        out.iloc[t + 1:, out.columns.get_loc("low")] = np.minimum(o, c) * 0.8
        out.iloc[t + 1:, out.columns.get_loc("volume")] = rng.uniform(1e3, 1e9, k)
    return add_value(out)


def _random_df(seed: int, n: int = 420) -> pd.DataFrame:
    """무작위 보행 + 장대양봉 주입(+9~14%, 거래량 4배) — 설정 · 접촉 · 신호가 실제로 나오게."""
    rng = np.random.default_rng(seed)
    c = np.empty(n)
    o = np.empty(n)
    v = rng.lognormal(13.8, 0.35, n)
    c[0] = o[0] = 10000.0
    jumps = set(rng.choice(np.arange(30, n - 5), size=n // 25, replace=False).tolist())
    for i in range(1, n):
        o[i] = c[i - 1] * (1 + rng.normal(0, 0.004))
        if i in jumps:
            c[i] = c[i - 1] * rng.uniform(1.09, 1.14)
            v[i] *= 4
        else:
            c[i] = o[i] * (1 + rng.normal(-0.002, 0.018))
    hi = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
    idx = pd.bdate_range("2022-01-03", periods=n)
    return add_value(pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": v.round()}, index=idx))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_prefix_invariance_random(seed):
    df = _random_df(seed)
    b = tq.Bars.from_df(df)
    full = fp.run(b, record=True).snaps
    seen = {x["phase"] for x in full}
    assert {"CANDIDATE", "TOUCH"} <= seen                     # 시험이 기계를 실제로 지나간다
    for t in range(25, b.n, 3):
        cut = fp.evaluate(b, t)
        junk = fp.evaluate(tq.Bars.from_df(_junk_future(df, t, seed + t)), t)
        assert full[t] == cut == junk, t


def test_prefix_invariance_random_signals_seen():
    phases = set()
    for seed in (1, 2, 3, 4, 5, 6):
        phases |= {x["phase"] for x in fp.run(tq.Bars.from_df(_random_df(seed)), record=True).snaps}
    assert {"SIGNAL", "WAIT", "INVALID"} <= phases


def test_prefix_invariance_detect_level():
    df = _random_df(2)
    full = fp.run(tq.Bars.from_df(df), record=True).snaps
    for t in range(60, len(df), 9):
        r = fp.detect(make_context(df.iloc[:t + 1]))
        st = full[t]
        assert r.stage == st["stage"] and r.metrics["phase"] == st["phase"], t
        if r.detected:
            exp_pivot = st["entry"] if st["phase"] in fp.POST_PHASES else None
            assert r.pivot == exp_pivot
            if st["phase"] in fp.POST_PHASES:
                assert r.stop == st["stop"]


def test_prefix_invariance_scenario_every_bar():
    rows = _rows(CONF, DIP, TOUCH, QUIET, QUIET, REB_NT, HOLDB, HOLDB, [110, 112, 109, 111, 3e6]) + [HOLDB] * 6
    df = _df(rows)
    b = tq.Bars.from_df(df)
    full = fp.run(b, record=True).snaps
    for t in range(b.n):
        assert full[t] == fp.evaluate(b, t) == fp.evaluate(tq.Bars.from_df(_junk_future(df, t, t)), t), t


def test_config_override_via_ctx_cfg():
    r = _detect(_rows(CONF, DIP, TOUCH, [119, 122.5, 118.8, 122, 5e6]),
                cfg=fp.FibPullbackConfig(require_up_close=True, signal_window=0))
    assert r.metrics["phase"] == "SIGNAL"                     # 47 도 접촉 봉이라 창 0 에서도 신호
    r = _detect(_rows(CONF, DIP, TOUCH, QUIET, REB_NT), cfg=fp.FibPullbackConfig(signal_window=1))
    assert r.metrics["phase"] != "SIGNAL"
