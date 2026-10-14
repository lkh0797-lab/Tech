"""빗각 돌파 + 피보 눌림(patterns/trendline_fib.py) — 합성 봉으로 신호 · 비신호 · 부록 §5 경계 · 앞부분 불변 · '모름' 처리.

기본 그림 (tests/test_trendline_break.py 와 같은 하향선): 봉 0..109 = 선 100·e^(−0.004 i) 아래 봉, 접점 10 · 40 · 70 →
봉 110 돌파(선 +4% 종가 → 당일 안착 확인, 거래량 3e6) → 112 고점 1.20 → 113 음봉(고점 확정, 23.6% 접근) → 114 눌림 →
115 38.2% 접촉 → 116 거래량 실린 반등 양봉(신호). 값은 lv = 돌파일(110) 동결 선 값의 배수.
L = 봉 109 저가(마지막 접점 70 ~ 돌파일 최저) ≈ 0.891 lv. 라인 23.6% ≈ 1.127 · 38.2% ≈ 1.082 · 50% ≈ 1.045 · 61.8% ≈ 1.009 lv."""
import json

import numpy as np
import pandas as pd
import pytest

from chart_screener import techniques as tq
from chart_screener.config import Config
from chart_screener.journal import rule_of
from chart_screener.patterns import REGISTRY
from chart_screener.patterns import fib_pullback as fp
from chart_screener.patterns import trendline_break as tb
from chart_screener.patterns import trendline_fib as tf
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from synthetic import add_value, make_context

T0 = 110


# ---------------------------------------------------------------- 도우미
def _tl_df(n, spikes=(10, 40, 70), slope=-0.004):
    """로그 직선 line = 100·e^(slope·i) 아래 봉(고가 0.93 · 종가 0.90 · 저가 0.88) + spikes 봉 고가 = 선(접점)."""
    i = np.arange(n)
    line = 100.0 * np.exp(slope * i)
    c = 0.90 * line
    o, h, lo = c * (0.91 / 0.90), c * (0.93 / 0.90), c * (0.88 / 0.90)
    for p in spikes:
        h[p], c[p], o[p] = line[p], line[p] * 0.95, line[p] * 0.92
    v = np.linspace(2e6, 1e6, n)
    df = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": v},
                      index=pd.bdate_range("2024-01-02", periods=n))
    return add_value(df)


def _scen(tail, n_before=T0):
    """봉 n_before.. 를 tail 의 (시가, 고가, 저가, 종가, 거래량)으로 — 가격은 lv(돌파일 시험선 값) 배수."""
    df = _tl_df(n_before + len(tail))
    ln = tq.fit_downtrend_line(tq.Bars.from_df(df.iloc[:n_before + 1]), n_before)
    lv = ln.value(n_before)
    for k, (o, h, lo, c, v) in enumerate(tail):
        i = n_before + k
        for col, x in (("open", o * lv), ("high", h * lv), ("low", lo * lv), ("close", c * lv), ("volume", v)):
            df.iloc[i, df.columns.get_loc(col)] = x
    return add_value(df), ln, lv


BRK = (0.96, 1.05, 0.95, 1.04, 3e6)            # 110 돌파 · 당일 안착 확인(선 +4%)
UP1 = (1.04, 1.12, 1.03, 1.11, 1.5e6)
UP2 = (1.11, 1.20, 1.10, 1.19, 1.5e6)          # 112 고점 1.20
CONF = (1.19, 1.195, 1.15, 1.16, 1.2e6)        # 113 음봉 → 고점 확정 (23.6% 접근)
DIP = (1.16, 1.165, 1.10, 1.105, 1.0e6)        # 114 눌림 (38.2% 접근)
TOUCH = (1.10, 1.105, 1.075, 1.085, 0.8e6)     # 115 38.2% 접촉
REB = (1.085, 1.12, 1.08, 1.115, 2.5e6)        # 116 반등 양봉 → 신호
HOLDB = (1.115, 1.14, 1.11, 1.13, 1.2e6)       # 진입 ~ +5% 사이
A = [BRK, UP1, UP2, CONF, DIP, TOUCH, REB]


def _det(df, cfg=None, **kw):
    ctx = make_context(df, **kw)
    if cfg is not None:
        ctx.cfg.patterns[tf.NAME] = cfg
    return tf.detect(ctx)


def _bars(df):
    return tq.Bars.from_df(df)


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
    return add_value(d)


def _rand_df(seed, n=520):
    """하락 다리 → 거래량 실린 급등 → 눌림 을 되풀이하는 무작위 봉 — 빗각 돌파 · 피보 설정이 실제로 나오게."""
    rng = np.random.default_rng(seed)
    c, o = np.empty(n), np.empty(n)
    v = rng.lognormal(13.8, 0.3, n)
    c[0] = o[0] = 10000.0
    mode, left = "down", int(rng.integers(60, 120))
    for i in range(1, n):
        if left <= 0:
            mode = {"down": "up", "up": "pull", "pull": "down"}[mode]
            left = {"down": int(rng.integers(60, 120)), "up": int(rng.integers(4, 9)), "pull": int(rng.integers(5, 15))}[mode]
        left -= 1
        o[i] = c[i - 1] * (1 + rng.normal(0, 0.003))
        if mode == "down":
            c[i] = o[i] * (1 + rng.normal(-0.004, 0.015) + (0.03 if i % 17 == 0 else 0))
        elif mode == "up":
            c[i] = o[i] * (1 + abs(rng.normal(0.03, 0.02)))
            v[i] *= rng.uniform(2.0, 4.0)
        else:
            c[i] = o[i] * (1 + rng.normal(-0.008, 0.012))
    hi = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.008, n)))
    idx = pd.bdate_range("2022-01-03", periods=n)
    return add_value(pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": v.round()}, index=idx))


# ---------------------------------------------------------------- 등록 · 출처
def test_registered_label_rule_id_and_origins():
    assert REGISTRY["trendline_fib"][0] == "빗각 돌파 + 피보 눌림" == tf.LABEL
    df, _, _ = _scen(A)
    r = _det(df)
    assert r.metrics["rule_version"] == "tlfib_v1" == tq.RULE_IDS["trendline_fib"] and rule_of(r) == "tlfib_v1"
    assert r.metrics["core_version"] == tq.CORE_VERSION
    org = r.metrics["origin"]
    for k, v in tf.ORIGIN.items():                     # 규칙마다 출처: 영상 [mm:ss] · URL · 구현 선택 · 스펙 · 부록
        assert any(x in v for x in ("영상 [", "http", "구현 선택", "스펙", "부록")), k
    for s in r.reasons + r.warnings:                   # 근거 · 경고 줄 끝 [키] 는 결과의 출처 표에 있다
        if s.endswith("]") and "[" in s:
            assert s[s.rindex("[") + 1:-1] in org, s
    for p in r.metrics["line_score_parts"].values():
        assert p["origin"] in org
    for k in ("technique", "precondition", "wave_low", "trigger", "signal_after_conf", "tl_invalid", "both_states",
              "stage_map", "score", "vol_cross", "confirm_video"):              # 이 기법 규칙은 늘 실림
        assert org[k] == tf.ORIGIN[k], k
    assert len(org) < len(tf.ORIGIN)                                            # 전체 표가 아니라 쓴 규칙만
    assert any("영상 [47:00–54:00]" in v for v in org.values())
    json.dumps(r.to_dict(), ensure_ascii=False, allow_nan=False)


def test_bulkowski_only_labelled():
    df, _, _ = _scen(A)
    r = _det(df)
    assert r.metrics["bulkowski"] and all(x.startswith(tq.BULKOWSKI_LABEL) for x in r.metrics["bulkowski"])
    stats = list(tq.BULKOWSKI_CONTEXT.values())
    assert not any(st in s for st in stats for s in r.reasons + r.warnings)   # 통계 문장은 후보 줄에 안 씀
    for s in r.reasons + r.warnings:
        if "59%" in s or "51%" in s:
            assert tq.BULKOWSKI_LABEL in s
    assert not any("확률" in s and "아님" not in s and "아니다" not in s for s in r.reasons + r.warnings)


# ---------------------------------------------------------------- 신호
def test_signal_after_confirmed_breakout():
    df, ln, lv = _scen(A)
    r = _det(df)
    assert r.detected and r.stage == BREAKOUT and r.metrics["phase"] == "SIGNAL"
    b = _bars(df)
    H, L = b.high[112], b.low[109]
    lvs = tq.fib_levels(H, L)
    assert r.metrics["wave_low"] == L and r.metrics["wave_low_date"] == f"{df.index[109]:%Y-%m-%d}"
    assert r.metrics["l_last_touch_date"] == f"{df.index[70]:%Y-%m-%d}" and r.metrics["l_mode"] == "since_last_touch"
    assert r.metrics["wave_high"] == H and r.metrics["active_level"] == 0.382
    assert r.pivot == pytest.approx(b.close[116]) and r.stop == pytest.approx(lvs[0.5])   # 38.2 접촉 → 손절 50%
    assert r.breakout_date == r.end_date == f"{df.index[116]:%Y-%m-%d}"
    assert r.start_date == f"{df.index[10]:%Y-%m-%d}"                                      # 추세선 앵커
    tl = r.metrics["trendline"]
    assert tl["break_date"] == tl["conf_date"] == f"{df.index[T0]:%Y-%m-%d}" and tl["conf_how"] == "pct"
    assert tl["alive"] and tl["state_label"] == "돌파 (안착 확인)" and tl["break_price"] == pytest.approx(lv)
    assert tl["touch_count"] == 3 and tl["vol"] == "ok"
    assert r.metrics["score_coverage"] == 1.0 and 0 < r.score <= 100
    assert len(r.metrics["checklist"]) == 10 and r.metrics["exit_plan"]["entry_i"] == 116
    labels = [a.get("label", a.get("text")) for a in r.annotations]
    assert {"하향 추세선 (돌파 때 동결)", "빗각 돌파", "기준 파동", "접촉 38.2%", "신호", "고점", "고점 확정"} <= set(labels)
    assert "피보 50% 관심 구간 · 손절" in labels and "61.8% 무효선" in labels


def test_phases_before_signal_and_stage_mapping():
    df, _, _ = _scen(A)
    snaps = tf.run(_bars(df), record=True).snaps
    assert [s["phase"] for s in snaps[109:117]] == ["NONE", "CANDIDATE", "CANDIDATE", "CANDIDATE", "APPROACH",
                                                     "APPROACH", "TOUCH", "SIGNAL"]
    assert [s["stage"] for s in snaps[110:117]] == [None, None, None, NEAR_PIVOT, NEAR_PIVOT, NEAR_PIVOT, BREAKOUT]
    r = _det(df.iloc[:113])                                            # 고점 미확정 — 탐지 안 함, 이유
    assert not r.detected and r.metrics["phase"] == "CANDIDATE"
    assert any("미확정" in w and "[trigger]" in w for w in r.warnings)
    assert r.metrics["trendline"]["state_label"] == "돌파 (안착 확인)"   # 빗각 쪽 상태는 같이 보임
    r = _det(df.iloc[:116])
    assert r.detected and r.stage == NEAR_PIVOT and r.metrics["phase"] == "TOUCH"
    assert r.pivot is None and r.stop == pytest.approx(r.metrics["fib_500"])                # 예정 손절
    assert r.metrics["score_coverage"] == 0.75                                               # 반등 거래량 모름


def test_post_signal_stages():
    df, _, lv = _scen(A + [HOLDB])
    assert _det(df).stage == BREAKOUT and _det(df).metrics["phase"] == "HOLD"
    df, _, _ = _scen(A + [(1.13, 1.19, 1.12, 1.18, 1.5e6)])              # 진입 × 1.05 위
    r = _det(df)
    assert r.stage == EXTENDED and any("이격" in w for w in r.warnings)
    df, _, _ = _scen(A + [(1.11, 1.12, 1.09, 1.10, 1.0e6)])              # 진입가 아래 · 손절 위
    assert _det(df).stage == NEAR_PIVOT and _det(df).metrics["phase"] == "RETEST"
    df, _, _ = _scen(A + [(1.10, 1.105, 1.03, 1.06, 1.5e6)])             # 저가 < 50% 손절
    r = _det(df)
    assert r.stage == FAILED and r.metrics["phase"] == "STOPPED" and r.metrics["stop_hit_date"]
    df, _, _ = _scen(A + [HOLDB] * 5)                                    # 신호 뒤 5봉 지남
    r = _det(df)
    assert not r.detected and r.metrics["phase"] == "STALE" and any("표시 창" in w for w in r.warnings)


# ---------------------------------------------------------------- 부록 §5-2 파동 저점
def test_wave_low_since_last_touch_ignores_older_lower_low():
    df, _, _ = _scen(A)
    i50 = df.columns.get_loc("low")
    df.iloc[50, i50] = df["low"].iloc[50] * 0.5                         # 마지막 접점(70) 앞의 더 깊은 저점
    df = add_value(df)
    r = _det(df)
    assert r.metrics["wave_low"] == df["low"].iloc[109]                 # min(저가[70..110])
    assert r.metrics["wave_low"] > df["low"].iloc[50]
    fp_low = fp.Machine(_bars(df), fp.FibPullbackConfig(l_mode="min_lookback"))._wave_low(T0)
    assert fp_low[1] == 50                                              # fib_pullback 의 60봉 최저였다면 봉 50


# ---------------------------------------------------------------- 부록 §5-5 · §5-6 무효 · 두 상태
def test_close_below_frozen_line_invalidates_first():
    df, ln, lv = _scen([BRK, UP1, UP2, CONF, (1.0, 1.0, 0.90, 0.95, 1.5e6)])   # 114 종가 < 동결 선 (61.8% 보다도 아래)
    b = _bars(df)
    assert b.close[114] <= ln.value(114) and b.close[114] < tq.fib_levels(b.high[112], b.low[109])[0.618]
    m = tf.run(b)
    s = m.history[-1]
    assert s.state == fp.INVALID and s.tl_fail == 114 and "추세선" in s.why          # 61.8% 보다 먼저 봄
    r = _det(df)
    assert not r.detected and r.metrics["phase"] == "INVALID"
    assert any("빗각 돌파 실패" in w and w.endswith("[tl_invalid]") for w in r.warnings)
    assert r.metrics["trendline"]["state_label"] == "실패" and not r.metrics["trendline"]["alive"]


def test_fake_breakout_invalidates_before_confirmation():
    df, _, _ = _scen([(0.99, 1.02, 0.985, 1.01, 3e6), (1.0, 1.005, 0.95, 0.96, 1.5e6)])   # 확인 전 선 아래 종가
    r = _det(df)
    assert not r.detected and r.metrics["phase"] == "INVALID"
    assert r.metrics["trendline"]["state_label"] == "실패(가짜 돌파)" and r.metrics["trendline"]["conf_date"] is None
    assert tb.timeline(df)[111].phase == "failed_fake"                  # trendline_break 의 '실패' 와 같은 봉


def test_fib_invalid_while_trendline_alive_shows_both_states():
    df, ln, _ = _scen([BRK, UP1, UP2, CONF, DIP, (1.10, 1.10, 0.995, 1.0, 1.0e6)])   # 115 종가 < 61.8% · 선 위
    b = _bars(df)
    assert b.close[115] > ln.value(115)
    r = _det(df)
    assert not r.detected and r.metrics["phase"] == "INVALID"
    assert any("61.8" in w and w.endswith("[invalid_618]") for w in r.warnings)
    assert any("추세선은 살아 있음" in w and w.endswith("[both_states]") for w in r.warnings)
    assert r.metrics["trendline"]["alive"] and r.metrics["trendline"]["state_label"] == "돌파 (안착 확인)"


# ---------------------------------------------------------------- 전제: 돌파 거래량 · 안착 확인
def test_low_volume_break_opens_no_setup():
    base = float(np.mean(_tl_df(T0 + len(A))["volume"].iloc[60:110]))
    tail = [BRK[:4] + (base * 1.2,)] + A[1:]
    df, _, _ = _scen(tail)
    r = _det(df)
    assert not r.detected and r.metrics["phase"] == "NONE"
    assert any("거래량 미달" in w and w.endswith("[break_vol_required]") for w in r.warnings)
    loose = _det(df, cfg=tf.TLFibConfig(require_break_vol=False))       # 플래그를 끄면 같은 눌림이 신호
    assert loose.detected and loose.metrics["phase"] == "SIGNAL"


# 안착 4종가(conf_bars=4)면 봉 113 에 안착 확인 — 112 반등 양봉은 신호 조건을 채워도 기록만 (부록 §5-4)
E_TAIL = [(0.99, 1.10, 0.985, 1.01, 3e6),       # 110 돌파(선 +1%) · 고점 1.10
          (1.05, 1.06, 0.99, 1.00, 1.2e6),       # 111 음봉 → 고점 확정 · 50% 접촉
          (1.00, 1.02, 0.998, 1.015, 2.5e6),     # 112 반등 양봉 (안착 확인 전)
          (1.015, 1.02, 1.00, 1.005, 1.0e6),     # 113 음봉 · 4종가째 → 안착 확인
          (1.005, 1.03, 1.00, 1.025, 3e6)]       # 114 반등 양봉 → 신호
E_CFG = tf.TLFibConfig(tl=tb.TLBreakConfig(conf_bars=4))


def test_signal_waits_for_trendline_confirmation():
    df, _, _ = _scen(E_TAIL)
    snaps = tf.run(_bars(df), E_CFG, record=True).snaps
    assert snaps[111]["phase"] == "TOUCH" and snaps[111]["stage"] == FORMING and not snaps[111]["tl_conf"]
    assert snaps[112]["pre"] == (112,) and snaps[112]["phase"] == "TOUCH" and snaps[112]["stage"] == FORMING
    assert snaps[113]["t_conf"] == 113 and snaps[113]["stage"] == NEAR_PIVOT
    assert snaps[114]["phase"] == "SIGNAL" and snaps[114]["s"] == 114
    r = _det(df.iloc[:113], cfg=E_CFG)
    assert r.detected and r.stage == FORMING and "안착 확인 대기" in r.metrics["phase_label"]
    assert any(w.endswith("[pending_stage]") for w in r.warnings)
    assert r.metrics["pre_signals"] == [f"{df.index[112]:%Y-%m-%d}"]
    assert any("기록만" in w and w.endswith("[signal_after_conf]") for w in r.warnings)
    r = _det(df, cfg=E_CFG)
    assert r.stage == BREAKOUT and r.breakout_date == f"{df.index[114]:%Y-%m-%d}"
    assert r.metrics["trendline"]["conf_how"] == "bars" and r.stop == pytest.approx(r.metrics["fib_618"])   # 50% → 61.8%
    # 기본(안착 3종가)이면 112 가 안착 확인 봉 — 같은 봉 신호 허용
    d3 = _det(df.iloc[:113])
    assert d3.metrics["phase"] == "SIGNAL" and d3.breakout_date == f"{df.index[112]:%Y-%m-%d}"
    assert d3.metrics["pre_signals"] == []


def test_new_break_while_setup_open_is_recorded_only():
    df, _, _ = _scen(A)
    b = _bars(df)
    sim = tb.simulate(b, tb.TLBreakConfig(), df)
    (brk,) = sim.breaks
    extra = tb.Break(brk.line, 113, brk.vr, "ok", [])                  # 진행 중 설정에 끼어든 돌파(가짜로 넣음)
    sim2 = tb.Sim(sim.states, [brk, extra], sim.slopes, sim.swings, sim.line, sim.brk)
    m = tf.run(b, None, sim2)
    assert [(t, k) for t, k, _ in m.events] == [(110, "open"), (113, "busy")]
    assert m.sig is not None and m.sig.b == 110                         # 신호는 첫 설정 그대로


def test_unconfirmed_high_expires_after_twenty_bars():
    tail = [BRK] + [(1.04 * 1.02 ** k, 1.04 * 1.02 ** (k + 1) * 1.003, 1.04 * 1.02 ** k * 0.998, 1.04 * 1.02 ** (k + 1),
                     1.5e6) for k in range(21)]                         # 21봉 연속 양봉 · 종가 상승 — 고점 확정 없음
    df, _, _ = _scen(tail)
    snaps = tf.run(_bars(df), record=True).snaps
    assert snaps[130]["phase"] == "CANDIDATE" and snaps[131]["phase"] == "EXPIRED"
    r = _det(df)
    assert not r.detected and any("만료" in w and w.endswith("[h_max]") for w in r.warnings)


# ---------------------------------------------------------------- 모름 · 장중 · 체크리스트 · 설정
def test_short_history_unknown():
    r = _det(_tl_df(30, spikes=(5, 18)))
    assert not r.detected and r.metrics["phase"] == "UNKNOWN" and any("이력 부족" in w for w in r.warnings)
    r = _det(_tl_df(T0))                                                 # 선은 있지만 돌파 없음
    assert not r.detected and r.metrics["phase"] == "NONE"
    assert any("빗각 추세선 돌파가 아직 없음" in w and w.endswith("[precondition]") for w in r.warnings)


def test_partial_bar_only_provisional():
    df, _, _ = _scen(A)
    df.iloc[-1, df.columns.get_loc("volume")] = 1.25e6                 # 장중 절반 · 하루치 환산 2.5e6
    ctx = make_context(df)
    ctx.partial, ctx.session_frac = True, 0.5
    r = tf.detect(ctx)
    assert r.metrics["asof"] == f"{df.index[115]:%Y-%m-%d}"            # 판정 기준은 어제까지
    # 일봉 EOD · 완성 봉만: 장중 잠정 신호는 경고 줄 · 수치에만 — 단계 · 진입가는 어제까지(접촉)
    assert r.metrics["provisional"] and r.metrics["provisional_phase"] == "SIGNAL"
    assert r.metrics["phase"] == "TOUCH" and r.stage != BREAKOUT and r.pivot is None and "exit_plan" not in r.metrics
    assert any("장중 잠정" in w and "'신호'" in w for w in r.warnings) and any("장중 스캔" in w for w in r.warnings)
    weak = df.copy()
    weak.iloc[-1, weak.columns.get_loc("volume")] = 0.2e6               # 환산 0.4e6 — 신호 아님 → 어제 판정
    ctx = make_context(weak)
    ctx.partial, ctx.session_frac = True, 0.5
    r = tf.detect(ctx)
    assert r.metrics["phase"] == "TOUCH" and not r.metrics["provisional"]
    assert any("장중 스캔" in w for w in r.warnings)


def test_checklist_unknowns_without_external_data():
    df, _, _ = _scen(A)
    ctx = make_context(df, info={})
    ctx.market_state = None
    r = tf.detect(ctx)
    ck = {c["no"]: c for c in r.metrics["checklist"]}
    for no in (1, 2, 4, 5):
        assert ck[no]["status"] == "unknown" and ck[no]["status_label"] == "모름"
    assert ck[8]["value"]["stop"] == pytest.approx(r.stop)


def test_config_follows_trendline_break_and_shares_simulation():
    df, _, _ = _scen(E_TAIL)
    cfg = Config()
    cfg.patterns["trendline_break"] = tb.TLBreakConfig(conf_bars=4)
    ctx = make_context(df, cfg=cfg)
    rb, rf = tb.detect(ctx), tf.detect(ctx)
    assert rf.metrics["phase"] == "SIGNAL" and rf.metrics["trendline"]["conf_how"] == "bars"   # trendline_break 설정 그대로
    assert rf.breakout_date == f"{df.index[114]:%Y-%m-%d}"
    keys = [k for k in ctx._cache if isinstance(k, tuple) and k and k[0] == "trendline_break.simulate"]
    assert len(keys) == 1                                               # 두 탐지기가 같은 계산을 한 번만
    assert rb.metrics["break"]["date"] == rf.metrics["trendline"]["break_date"]


def test_score_parts_unknown_excluded():
    cfg = tf.TLFibConfig()
    s, cov, parts = tf.score_parts(cfg, 80.0, 0.382, 2.0)
    assert cov == 1.0 and s == pytest.approx((50 * 0.8 + 25 * 1.0 + 25 * 0.75) / 100 * 100)
    s, cov, _ = tf.score_parts(cfg, None, 0.236, None)
    assert cov == 0.25 and s == pytest.approx(50.0)
    assert tf.score_parts(cfg, None, None, None)[:2] == (0.0, 0.0)


# ---------------------------------------------------------------- 앞부분 불변
def _check_prefix(df, ts, cfg=None):
    b = _bars(df)
    full = tf.run(b, cfg, record=True).snaps
    for t in ts:
        cut = tf.evaluate(b, t, cfg)
        junk = tf.evaluate(_bars(_junk(df, t, seed=t)), t, cfg)
        assert full[t] == cut == junk, t
    return full


def test_prefix_invariance_scenarios_every_bar():
    for tail, cfg in ((A + [HOLDB, (1.10, 1.105, 1.03, 1.06, 1.5e6)] + [HOLDB] * 3, None),
                      (E_TAIL + [HOLDB] * 3, E_CFG),
                      ([BRK, UP1, UP2, CONF, DIP, (1.10, 1.10, 0.995, 1.0, 1.0e6)] + [HOLDB] * 3, None)):
        df, _, _ = _scen(tail)
        _check_prefix(df, range(100, len(df)), cfg)


@pytest.mark.parametrize("seed", [1, 7, 12])
def test_prefix_invariance_random(seed):
    df = _rand_df(seed)
    full = _check_prefix(df, range(60, len(df), 5))
    seen = {s["phase"] for s in full}
    assert len(seen - {"NONE"}) >= 3                                    # 시험이 기계를 실제로 지나간다


def test_prefix_invariance_random_phases_seen():
    phases, tl_fail = set(), 0
    for seed in (1, 7, 12):
        m = tf.run(_bars(_rand_df(seed)), record=True)
        phases |= {s["phase"] for s in m.snaps}
        tl_fail += sum(1 for x in m.history if x.tl_fail is not None)
    assert {"CANDIDATE", "TOUCH", "SIGNAL", "STOPPED", "INVALID", "EXPIRED"} <= phases and tl_fail >= 1


def test_detect_matches_snapshots_and_stage_series():
    for df, ts in ((_scen(A + [HOLDB] * 2)[0], range(105, T0 + len(A) + 2)), (_rand_df(7), range(60, 520, 4))):
        full = tf.run(_bars(df), df=df, record=True).snaps
        ss = tf.stage_series(df)
        for t in ts:
            r = _det(df.iloc[:t + 1])
            st = full[t]
            assert (r.detected, r.stage, r.metrics.get("phase")) == (st["stage"] is not None, st["stage"], st["phase"]), t
            assert r.pivot == st["pivot"] and r.stop == st["plan_stop"], t
            x = ss[t]
            assert (x is None) == (not r.detected), t
            if x is not None:
                assert (x["stage"], x["pivot"], x["stop"]) == (r.stage, r.pivot, r.stop), t
                bo = None if x["breakout_i"] is None else f"{df.index[x['breakout_i']]:%Y-%m-%d}"
                assert bo == r.breakout_date, t


def test_results_are_plain_json():
    for tail in (A, A + [HOLDB], E_TAIL[:2], [BRK, UP1, UP2, CONF, (1.0, 1.0, 0.90, 0.95, 1.5e6)]):
        df, _, _ = _scen(tail)
        json.dumps(tf.detect(make_context(df)).to_dict(), ensure_ascii=False, allow_nan=False)
