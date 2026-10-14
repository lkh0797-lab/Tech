"""빗각 돌파 + 피보 눌림 `trendline_fib` — 김정환 《차트의 기술》 영상 [47:00–54:00] · 스펙 docs/2026-10-14-chart-techniques-design.md
§4 · 부록 docs/2026-10-14-chart-techniques-addendum.md §5 (부록 알고리즘이 스펙의 '구현 선택' 추정보다 우선).

새 규칙을 만들지 않고 두 기법의 상태 기계를 그대로 잇는다.
  빗각    trendline_break.simulate — 확정 소고점 · 로그 눈금 · 접점 3개 이상 하향선, 첫 선 위 종가 = 돌파 t0, 그때 선을 동결,
          그날 선 +3% 종가 또는 돌파일 포함 3종가 선 위 = 안착 확인 t_conf (TLBreakConfig — 기본은 trendline_break 설정 그대로).
  피보    fib_pullback.Machine — 고점 확정 · 라인 · 접촉 · 반등 양봉 신호 · 손절 · 만료 (FibPullbackConfig — 기본은 fib_pullback 설정).

순서 (부록 §5 — 봉 t 판정은 [0..t] 자료만 → 앞부분 불변. 안착 확인 · 실패 같은 뒤 사건은 그 봉이 지난 뒤에만 본다)
  1 전제    빗각 돌파 t0 의 동결 선(앵커 A · 기울기 · 접점 T). 돌파 거래량 확인(직전 50봉 평균 × 1.5, 당일 제외)된 돌파만
            설정을 연다 — 스펙 §3 돌파 거래량 필수(미달 · 모름 · 거래정지 돌파는 이유만 적음, require_break_vol).
  2 파동 저점  L = min(저가[p_last..t0]), p_last = T 의 마지막 접점 (스펙 '돌파 직전 저점' · Bulkowski 측정 규칙과 같은 구간).
  3 피보 기계  trigger b := t0 — 장대양봉 조건 없음. H = max(고가[t0..t]) · 고점 확정 'video'(음봉 · 종가 하락 봉) · 확정 없이
            20봉 → 만료 · 라인 23.6 · 38.2 · 50 · 무효선 61.8 · 접촉 'wick' · 반등 양봉(양봉 · 전일보다 높은 종가 · 거래량이 5일
            거래량 이평 상향돌파) · 진입 = 신호 종가 · 손절 = 다음 깊은 라인 · 확정 뒤 30봉 만료 — 모두 부록 §3 그대로.
  4 신호 시점  안착 확인 봉 t_conf 이후(같은 봉 포함)만. 그 전 접촉은 그대로 두고 반등 양봉은 기록만(metrics.pre_signals).
            기본 설정(안착 3종가)에선 t_conf ≤ t0+2 라 거의 생기지 않는다 — conf_bars 를 늘리면 생긴다.
  5 추가 무효  동결 추세선 아래 종가(trendline_break '실패' — 종가 ≤ 선)면 설정 무효. 그 봉의 다른 판정보다 먼저 본다.
            trendline_break 는 안착 확인 20봉 뒤 선을 풀지만 이 설정은 끝날 때까지 동결 선을 그대로 연장해 본다(구현 선택).
  6 두 상태   61.8% 아래 마감으로 피보 설정이 무효여도 추세선은 살아 있을 수 있다 — metrics.trendline 에 같이 보인다.
  한 종목에 진행 중 설정은 하나 — 열려 있는 동안 생긴 새 돌파는 기록만, 설정이 끝난 봉 다음 봉부터 새 돌파로 새 설정.

Tech 단계 대응 (구현 선택 — fib_pullback 과 같음)
  신호 뒤 5봉 안   손절 = 돌파 실패 · 종가 > 진입 × 1.05 = 이격 과다 · 종가 < 진입 = 피벗 근접(재시험) · 그 밖 = 돌파
  고점 확정 뒤     접촉 뒤 3봉 안 · 라인 위 3% 안 = 피벗 근접 · 그 밖 = 형성 중 (안착 확인 전이면 신호를 못 내 모두 형성 중)
  그 밖           탐지 안 함 — 빗각 돌파 없음 · 고점 미확정 · 무효 · 만료 · 신호 뒤 5봉 지남 (이유는 경고로)
  pivot = 신호 종가(신호 뒤에만) · stop = 활성 라인의 다음 깊은 라인(접촉 · 접근 단계는 예정 손절) · breakout_date = 신호일.

점수 0~100 (구현 선택 — 확률 아님): 추세선 품질(trendline_break.score_line, 돌파일 동결) 50 · 라인 깊이(23.6 = 0.5 · 38.2 · 50 = 1)
25 · 반등 거래량(직전 4봉 평균의 1 → 3배) 25. 모르는 항목은 빼고 나눈다(관측 비중 표시).

출처: 근거 · 경고 줄 끝 [키] → metrics['origin'][키] ('영상 [mm:ss]' · URL · '구현 선택: 이유' — 전체 표는 ORIGIN, 결과에는
그 결과가 쓴 규칙과 이 기법의 규칙만). 불코우스키 수치는
tq.bulkowski_note 라벨로 metrics['bulkowski'] 에만. 일지 rule 칸 = metrics['rule_version'] = 'tlfib_v1'.
장중(ctx.partial): 판정 · 단계 · 진입가는 마지막 완성 봉까지(일봉 EOD 만). 오늘 미완성 봉(거래량 하루치 환산 추정)으로 본
'장중 잠정' 상태는 경고 줄과 metrics.provisional · provisional_phase 에만 — 단계를 바꾸지 않는다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from .. import techniques as tq
from . import fib_pullback as fp
from . import trendline_break as tb
from .base import FORMING, NEAR_PIVOT, PatternResult, StockContext, hline, marker, register, segment

NAME = "trendline_fib"
LABEL = tq.PATTERN_LABELS[NAME]            # '빗각 돌파 + 피보 눌림'
RULE_ID = tq.RULE_IDS[NAME]                # 'tlfib_v1' — 일지 rule 칸
VIDEO_TS = "47:00–54:00"


@dataclass
class TLFibConfig:
    tl: tb.TLBreakConfig | None = None     # None = ctx 의 trendline_break 설정(같은 선 · 같은 돌파 — 계산도 공유)
    fib: fp.FibPullbackConfig | None = None  # None = ctx 의 fib_pullback 설정 (장대양봉 상수는 안 씀)
    require_break_vol: bool = True         # 스펙 §3 돌파 거래량 필수 — 미달 · 모름 · 정지 돌파는 설정 안 엶
    w_line: float = 50.0                   # 점수 가중치 (구현 선택)
    w_depth: float = 25.0
    w_rebound: float = 25.0


def resolve_cfg(cfg: TLFibConfig | None = None, ctx: StockContext | None = None) -> TLFibConfig:
    """tl · fib 가 None 이면 ctx 의 trendline_break · fib_pullback 설정(없으면 기본값)으로 채운다."""
    cfg = cfg or TLFibConfig()
    tl, fib = cfg.tl, cfg.fib
    if tl is None:
        tl = ctx.cfg.pattern_cfg(tb.NAME, tb.TLBreakConfig) if ctx is not None else tb.TLBreakConfig()
    if fib is None:
        fib = ctx.cfg.pattern_cfg(fp.NAME, fp.FibPullbackConfig) if ctx is not None else fp.FibPullbackConfig()
    return replace(cfg, tl=tl, fib=fib)


# ---------------------------------------------------------------- 출처
_TD = "https://thepatternsite.com/trenddown.html"
_TL_KEYS = ("tl_break", "tl_conf_pct", "tl_conf_bars", "tl_freeze", "tl_break_vol", "tl_lowvol", "tl_halt_vol", "tl_touch",
            "tl_min_touches", "tl_min_gap", "tl_min_len", "tl_tol_cut", "tl_close_cut", "tl_anchor_highest",
            "tl_anchor_volume", "tl_log", "tl_lookback", "tl_fail", "tl_weights", "tl_slope_ref", "tl_bonus_touches",
            "tl_wide_gap", "tl_long_len", "tl_vol_trend", "tl_entry_flat", "tl_entry_trend", "tl_hammer_window", "swing",
            "baseline_excl_today", "cross")
_FIB_KEYS = ("confirm_video", "confirm_fractal2", "h_max", "fib_levels", "fib_buy", "fib_tol", "touch_wick", "touch_band",
             "approach", "signal_window", "vol_ma5", "vol_cross", "vol_level", "up_close", "entry_close", "stop", "stop_alt",
             "invalid_618", "invalid_L", "extended", "expiry", "stop_fill", "reset_checks", "line_depth", "evidence",
             "provisional", "fib_786", "intraday_final", "pre_stage_label")
ORIGIN: dict[str, str] = {k: tb.ORIGIN[k] for k in _TL_KEYS}
ORIGIN.update({k: fp.ORIGIN[k] for k in _FIB_KEYS})
ORIGIN.update(tq.HAMMER_ORIGIN)
ORIGIN.update({
    "technique": tq.video(VIDEO_TS) + " 빗각 추세선 돌파 + 피보나치 눌림 — 스펙 §4 · 부록 §5",
    "tl_technique": tb.ORIGIN["technique"],
    "precondition": ("부록 §5-1 전제 — trendline_break 의 동결 선(앵커 · 기울기 · 접점 · 돌파일 t0) · 안착 확인 t_conf · "
                     "스펙 §4 '3번 안착 확인 돌파 뒤'"),
    "break_vol_required": ("스펙 §3 돌파 거래량 필수 (O'Neil · Edwards & Magee — 반대 증거 Bulkowski "
                           "https://www.thepatternsite.com/VolumeStudy.html) · "
                           + tq.choice("거래량 미달 · 모름 · 거래정지 돌파는 피보 설정을 열지 않음 — trendline_break 는 관찰로 "
                                       "남기지만 이 기법은 '돌파' 뒤 눌림만 (require_break_vol)")),
    "wave_low": ("파동 저점 L = min(저가[p_last..t0]), p_last = 마지막 접점 — 부록 §5-2 · 스펙 §4 '돌파 직전 저점' · "
                 f"Bulkowski 측정 규칙도 마지막 접점 뒤 최저 ({_TD})"),
    "trigger": ("부록 §5-3 — 피보 기계를 trigger = 돌파일 t0 로 시작, 장대양봉 조건 안 씀 · H 후보 = max(고가[t0..t]) · "
                "고점 확정 · 20봉 만료 · 라인 · 접촉 · 손절 · 30봉 만료는 부록 §3 그대로"),
    "signal_after_conf": ("부록 §5-4 — 신호는 안착 확인 봉 t_conf 이후(같은 봉 포함)만, 그 전 접촉 · 반등 양봉은 기록만 · "
                          + tq.video("55:00–56:00") + " 진위 확인 뒤"),
    "tl_invalid": ("부록 §5-5 — 동결 추세선 아래 종가(trendline_break '실패', 종가 ≤ 선) = 설정 무효 · " + tq.video("54:00–56:00")
                   + " 선 아래 재하락 = 실패 · " + tq.choice("그 봉의 고점 · 접촉 · 신호 판정보다 먼저 본다")),
    "line_extend": tq.choice("trendline_break 는 안착 확인 20봉 뒤 선을 풀지만 이 설정은 끝날 때까지(고점 확정 ≤ 20봉 + 30봉) "
                             "돌파 때 동결한 선을 그대로 연장해 무효 검사 · 표시"),
    "both_states": (f"부록 §5-6 — 돌파 뒤 선 쪽 되돌림은 흔함(Bulkowski {_TD}): 61.8% 아래 마감이면 피보 설정은 무효여도 "
                    "추세선은 살아 있을 수 있어 두 상태를 같이 보임"),
    "one_setup": tq.choice("한 종목에 진행 중 설정 하나(부록 §3.2-5) — 열려 있는 동안 생긴 새 돌파는 기록만, 설정이 끝난 봉 "
                           "다음 봉부터 새 돌파로 새 설정"),
    "pending_stage": tq.choice("안착 확인 전에는 신호를 못 내므로 고점 확정 · 접근 · 접촉 단계도 형성 중"),
    "stage_map": tq.choice("Tech 단계 — fib_pullback 과 같음: 신호 뒤 5봉(base.classify_stage 돌파 창) 손절 = 돌파 실패 · 진입 "
                           "+5% 넘음 = 이격 과다 · 진입가 아래 = 피벗 근접(재시험) · 그 밖 돌파 / 접촉 뒤 3봉 · 라인 위 3% = "
                           "피벗 근접 / 고점 확정 뒤 대기 = 형성 중 / 고점 미확정 · 무효 · 만료 = 탐지 안 함"),
    "score": tq.choice("점수 = 추세선 품질(trendline_break 점수, 돌파일 동결) 50 · 라인 깊이(23.6 = 0.5, 38.2 · 50 = 1) 25 · "
                       "반등 거래량(직전 4봉 평균의 1 → 3배) 25, 모르는 항목은 빼고 나눔 — 확률 아님"),
    "replay": tq.choice("체크 4 — 이 기계의 지난 신호, 신호 종가 진입 · 20봉 뒤 종가, 20봉이 지난 신호만"),
})
AUTO_LINE = ("자동 작도 선 — 사람이 긋는 선과 다를 수 있음(장중 고가 · 로그 눈금 · 확정 소고점만, 영상의 손 작도 · 미세 조정 "
             "아님). 리포트 차트의 선으로 확인 [tl_technique]")
PHASE_KO = {k: v[0] for k, v in fp.PHASES.items()}
PHASE_KO.update({"NONE": "빗각 돌파 설정 없음", "CANDIDATE": "빗각 돌파 뒤 고점 확정 대기"})
PRE_PHASES = ("WAIT", "APPROACH", "TOUCH")      # 안착 확인 전이면 형성 중


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _won(x) -> str:
    return f"{x:,.0f}" if x is not None and x == x else "—"


def _pct(r: float) -> str:
    return f"{r * 100:g}%"


# ---------------------------------------------------------------- 상태 기계 (fib_pullback.Machine 위에)
@dataclass
class TLSetup(fp.Setup):
    brk: Any = None                 # trendline_break.Break — 동결 선 · 돌파일 t0 · 안착 확인일 t_conf
    pre: list = field(default_factory=list)   # 안착 확인 전 반등 양봉(신호 조건 충족 — 기록만, 부록 §5-4)
    tl_fail: int | None = None      # 동결 선 아래 종가로 설정이 무효가 된 봉 (부록 §5-5)


class Machine(fp.Machine):
    """fib_pullback 기계를 그대로 쓰고 세 곳만 바꾼다 — 설정 열기(장대양봉 → 거래량 확인된 빗각 돌파), 봉마다 동결 선 아래
    종가 검사(먼저), 신호는 안착 확인 뒤에만. step(t) 는 봉 t 까지 자료만 본다(빗각 돌파의 뒤 사건 t_conf 도 ≤ t 일 때만)."""

    def __init__(self, b: tq.Bars, cfg: TLFibConfig, sim: tb.Sim):
        super().__init__(b, cfg.fib)
        self.tcfg = cfg
        self.lw_ok = np.zeros(b.n, dtype=bool)            # 장대양봉 trigger · 흡수 안 씀 (부록 §5-3)
        self.sim = sim
        self.break_at = {x.t0: x for x in sim.breaks}
        self.events: list[tuple[int, str, Any]] = []       # (봉, 'open' | 'vol' | 'busy', Break)

    def conf_at(self, s: TLSetup, t: int) -> bool:
        """봉 t EOD 에 안착 확인을 알고 있나 (t_conf ≤ t)."""
        return s.brk.t_conf is not None and s.brk.t_conf <= t

    def step(self, t: int) -> None:
        s = self.cur
        brk = self.break_at.get(t)
        if s is None or s.state not in fp.OPEN:
            if brk is not None:
                if self.tcfg.require_break_vol and brk.vol != "ok":
                    self.events.append((t, "vol", brk))
                elif t > self.last_end:
                    self.cur = self._open_break(brk, t)
                    self.events.append((t, "open", brk))
                else:
                    self.events.append((t, "busy", brk))
            return
        if brk is not None:
            self.events.append((t, "busy", brk))          # 진행 중 설정 — 새 돌파는 기록만
        if tq.le(self.b.close[t], s.brk.line.value(t)):   # 부록 §5-5 — 먼저 본다
            s.tl_fail = t
            self._close(s, t, fp.INVALID, "동결 추세선 아래 종가 — 빗각 돌파 실패")
            return
        if s.state == fp.CANDIDATE:
            self._candidate(s, t)
        else:
            self._confirmed(s, t)

    def _open_break(self, brk, t: int) -> TLSetup:
        p = int(brk.line.touches[-1])
        j = p + int(np.argmin(self.b.low[p:t + 1]))
        return TLSetup(b=t, L=float(self.b.low[j]), l_i=j, l_mode="since_last_touch", p=p, H=float(self.b.high[t]), h=t,
                       brk=brk)

    def _signal(self, s: TLSetup, t: int) -> bool:
        if self.conf_at(s, t):
            return super()._signal(s, t)
        ok, _vr, why = self.rebound(s, t)                  # 안착 확인 전 — 기록만
        if ok:
            s.pre.append(t)
        elif why is not None:
            s.reject = (t, why)
        return False


def run(b: tq.Bars, cfg: TLFibConfig | None = None, sim: tb.Sim | None = None, df=None, record: bool = False) -> Machine:
    """봉 0 부터 끝까지. sim 이 없으면 trendline_break.simulate(b, cfg.tl, df) 를 돌린다(df = 거래정지일 확인용).
    record=True 면 봉마다 snapshot(judge) 를 m.snaps 에 — 앞부분 불변 시험 · stage_series 용."""
    cfg = resolve_cfg(cfg)
    sim = sim if sim is not None else tb.simulate(b, cfg.tl, df)
    m = Machine(b, cfg, sim)
    for t in range(b.n):
        m.step(t)
        if record:
            m.snaps.append(snapshot(m, judge(m, t)))
    return m


def first_below(line: tq.TrendLine, b: tq.Bars, i0: int, t: int) -> int | None:
    """[i0, t] 에서 처음으로 종가 ≤ 동결 선인 봉 (없으면 None) — 봉 t 까지만."""
    if t < i0:
        return None
    k = np.arange(i0, t + 1)
    hit = np.flatnonzero(tq.le(b.close[k], line.value(k)))
    return int(k[hit[0]]) if hit.size else None


def judge(m: Machine, t: int) -> dict:
    """봉 t 판정 — fib_pullback.judge + 안착 확인 여부 · Tech 단계 · 피벗 · (예정) 손절."""
    j = fp.judge(m, t)
    s, ph = j["setup"], j["phase"]
    j["tl_conf"] = bool(s is not None and m.conf_at(s, t))
    stage = fp.PHASES[ph][1]
    if ph in PRE_PHASES and not j["tl_conf"]:
        stage = FORMING                                    # 안착 확인 전 — 신호 못 냄 (pending_stage)
    j["stage"] = stage
    pivot = stop = stop_r = None
    if ph in fp.POST_PHASES:
        pivot, stop, stop_r = s.entry, s.stop, s.stop_r
    elif ph in ("TOUCH", "APPROACH"):
        r0 = s.active_r if ph == "TOUCH" else s.approach[1]
        stop_r = tq.next_deeper(r0, m.ratios)
        stop = float(s.lv[stop_r]) if stop_r is not None else None
    j.update(pivot=pivot, stop=stop, stop_r=stop_r)
    return j


def snapshot(m: Machine, j: dict) -> dict:
    """판정 요약(원시 값만) — 같은 봉 판정 비교용."""
    d = fp.snapshot(j)
    t, s = j["t"], j["setup"]
    d.update(stage=j["stage"], tl_conf=j["tl_conf"], pivot=j["pivot"], plan_stop=j["stop"])
    if s is not None:
        brk = s.brk
        d.update(t0=brk.t0, anchor=brk.line.anchor_i, slope=brk.line.slope, touches_tl=tuple(brk.line.touches),
                 t_conf=brk.t_conf if m.conf_at(s, t) else None, tl_fail=s.tl_fail, pre=tuple(s.pre),
                 tl_below=first_below(brk.line, m.b, brk.t0 + 1, t))
    d["events"] = tuple((e, k) for e, k, _ in m.events)
    return d


def evaluate(b: tq.Bars, t: int | None = None, cfg: TLFibConfig | None = None) -> dict:
    """봉 t 판정 요약 — b 를 t 까지 잘라 돌린다(미래 봉을 볼 수 없다)."""
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    bc = b.cut(t)
    m = run(bc, cfg)
    return snapshot(m, judge(m, t))


def stage_series(df, cfg: TLFibConfig | None = None) -> list[dict | None]:
    """백테스트용 — 한 번 돌려 봉마다 detect(df.iloc[:t+1]) 와 같은 {phase, detected, stage, pivot, stop, breakout_i}
    (탐지 안 되면 None). 점수 · 근거 · 체크리스트는 없다(detect 로). 앞부분 불변이라 날마다 다시 돌릴 필요가 없다."""
    b = tq.Bars.from_df(df)
    m = run(b, cfg, df=df, record=True)
    out: list[dict | None] = []
    for sn in m.snaps:
        if sn["stage"] is None:
            out.append(None)
            continue
        post = sn["phase"] in fp.POST_PHASES
        out.append({"phase": sn["phase"], "detected": True, "stage": sn["stage"], "pivot": sn["pivot"],
                    "stop": sn["plan_stop"], "breakout_i": sn["s"] if post else None})
    return out


# ---------------------------------------------------------------- 점수
def score_parts(cfg: TLFibConfig, line_score: float | None, depth_r: float | None,
                rebound_x: float | None) -> tuple[float, float, dict]:
    """(점수 0~100, 관측 비중, 항목) — 구현 선택, 확률 아님. ORIGIN['score']."""
    reb = None if rebound_x is None else 0.5 + 0.5 * min(1.0, max(0.0, (rebound_x - 1.0) / 2.0))
    parts = {
        "line": {"name": "추세선 품질 (돌파일 동결 점수)", "w": cfg.w_line, "x": line_score,
                 "s": None if line_score is None else line_score / 100.0},
        "depth": {"name": "라인 깊이", "w": cfg.w_depth, "x": depth_r,
                  "s": None if depth_r is None else (0.5 if depth_r < 0.3 else 1.0)},
        "rebound": {"name": "반등 거래량 배수(직전 4봉 평균)", "w": cfg.w_rebound, "x": rebound_x, "s": reb},
    }
    known = [p for p in parts.values() if p["s"] is not None and p["w"] > 0]
    tot = sum(p["w"] for p in parts.values() if p["w"] > 0)
    wk = sum(p["w"] for p in known)
    if not known or tot <= 0:
        return 0.0, 0.0, parts
    return float(100 * sum(p["w"] * p["s"] for p in known) / wk), float(wk / tot), parts


# ---------------------------------------------------------------- 결과
def _bars_with_partial(ctx: StockContext) -> tq.Bars:
    """오늘 미완성 봉 포함 — 마지막 봉 거래량은 ctx.vol(하루치 환산 추정)."""
    bp = tq.Bars.from_df(ctx.df)
    v = bp.volume.copy()
    v[-1] = float(ctx.vol.iloc[-1])
    return bp._replace(volume=v)


def _replay(m: Machine, T: int, fib: fp.FibPullbackConfig) -> list[dict]:
    C = m.b.close
    return [{"date": m.b.date(s.s), "ret20": float(C[s.s + fib.replay_bars] / s.entry - 1)}
            for s in m.history if s.state == fp.SIGNAL and s.s + fib.replay_bars <= T]


def _tl_info(m: Machine, s: TLSetup, t: int) -> dict:
    """봉 t 의 빗각 쪽 상태 (부록 §5-6 — 피보 설정과 따로) · 동결 선 기준, t 까지 자료만."""
    b, d = m.b, m.b.date
    brk, line = s.brk, s.brk.line
    conf = brk.t_conf if m.conf_at(s, t) else None
    below = first_below(line, b, brk.t0 + 1, t)
    lv = line.value(t)
    if below is not None:
        state = "실패" if conf is not None and conf < below else "실패(가짜 돌파)"
    else:
        state = "돌파 (안착 확인)" if conf is not None else "안착 확인 중"
    return {"anchor_date": d(line.anchor_i), "anchor_price": float(line.anchor_price), "touch_dates": [d(i) for i in line.touches],
            "touch_count": len(line.touches), "slope_pct": _f(line.slope_pct), "length": int(line.length),
            "break_date": d(brk.t0), "break_price": float(line.value(brk.t0)), "break_close": float(b.close[brk.t0]),
            "vol_ratio": _f(brk.vr), "vol": brk.vol, "vol_label": tb.VOL_KO[brk.vol], "halts": list(brk.halts),
            "conf_date": d(conf) if conf is not None else None, "conf_how": brk.conf_how if conf is not None else None,
            "line_today": float(lv), "line_next": float(line.value(t + 1)), "close_vs_line": float(b.close[t] / lv - 1),
            "alive": below is None, "below_date": d(below) if below is not None else None, "state_label": state}


def _why(s) -> str:
    """fib_pullback 기계의 종료 사유 — 이 기법의 trigger 는 장대양봉이 아니라 빗각 돌파."""
    return s.why.replace("장대양봉", "빗각 돌파")


def _event_text(m: Machine, t: int, kind: str, brk) -> str:
    d = m.b.date
    if kind == "vol":
        vr = f"{brk.vr:.2f}배" if brk.vr is not None else "모름"
        return (f"빗각 돌파 {d(t)} — {tb.VOL_KO[brk.vol]} ({vr}, 기준 직전 {m.tcfg.tl.vol_n}봉 평균 × {m.tcfg.tl.vol_mult}) · "
                "돌파 거래량 필수라 피보 설정 안 엶 [break_vol_required]")
    return f"빗각 돌파 {d(t)} — 진행 중 설정이 있어 새 설정 안 엶(기록만) [one_setup]"


def _why_not(m: Machine, j: dict, T: int) -> list[str]:
    s, ph, d = j["setup"], j["phase"], m.b.date
    fib = m.cfg
    after = s.end if s is not None and s.end is not None else (s.b if s is not None else -1)
    late = [(t, k, x) for t, k, x in m.events if k != "open" and t > after]
    out = [_event_text(m, t, k, x) for t, k, x in late[-2:]]   # 마지막 설정 뒤 열지 않은 돌파 (최근 2건)
    if ph == "NONE":
        st = m.sim.states[T].phase
        now = tb.PHASE_KO.get(st, "유효한 하향 추세선 없음") if st is not None else "유효한 하향 추세선 없음"
        out.insert(0, f"거래량 확인된 빗각 추세선 돌파가 아직 없음 — 지금 빗각 상태: {now} [precondition]")
        return out
    if ph == "CANDIDATE":
        how = ("고점 봉 다음에 음봉 또는 종가 하락 봉이 나와야 확정 [confirm_video]" if fib.swing_confirm == "video"
               else "좌우 2봉(fractal)으로 확정 [confirm_fractal2]")
        out.insert(0, f"빗각 돌파 {d(s.b)} 뒤 고점 {_won(s.H)} ({d(s.h)}) 미확정 — {how}. 라인은 확정 뒤 고정 [trigger]")
    elif ph == "STALE":
        out.insert(0, f"신호 {d(s.s)} (진입 {_won(s.entry)}) 뒤 {T - s.s}봉 — 표시 창 {fib.report_window}봉 지남 [stage_map]")
    elif ph == "INVALID":
        if s.tl_fail is not None:
            lv = s.brk.line.value(s.tl_fail)
            out.insert(0, f"{d(s.tl_fail)} 빗각 돌파 실패 — 종가 {_won(m.b.close[s.tl_fail])} ≤ 동결 선 {_won(lv)} → 피보 설정 "
                          f"무효 (빗각 돌파 {d(s.b)}) [tl_invalid]")
        else:
            key = "invalid_618" if "61.8" in s.why else "invalid_L"
            out.insert(0, f"피보 설정 무효: {_why(s)} ({d(s.end)}, 빗각 돌파 {d(s.b)}) [{key}]")
            ti = _tl_info(m, s, T)
            if ti["alive"]:
                out.append(f"추세선은 살아 있음 — 오늘 종가 {_won(m.b.close[T])} 가 동결 선 {_won(ti['line_today'])} 위 "
                           f"({ti['close_vs_line']:+.1%}) · 두 상태를 같이 봄 [both_states]")
            else:
                out.append(f"추세선도 {ti['below_date']} 선 아래 종가 — {ti['state_label']} [both_states]")
    elif ph == "EXPIRED":
        key = "h_max" if s.c is None else "expiry"
        out.insert(0, f"설정 만료: {_why(s)} ({d(s.end)}, 빗각 돌파 {d(s.b)}) [{key}]")
    return out


_TAG = re.compile(r"\[([a-z0-9_]+)\]$")
# 탐지된 결과에는 근거 줄에 안 나와도 이 기법의 규칙 출처를 늘 싣는다 (리포트 크기 때문에 전체 표 대신)
_RULE_KEYS = ("technique", "precondition", "break_vol_required", "wave_low", "trigger", "signal_after_conf", "tl_invalid",
              "line_extend", "both_states", "one_setup", "pending_stage", "stage_map", "score", "replay", "tl_technique",
              "tl_break", "tl_freeze", "tl_fail", "tl_touch", "tl_min_touches", "tl_min_len", "fib_levels", "fib_buy",
              "fib_tol", "invalid_618", "invalid_L", "h_max", "expiry", "reset_checks", "signal_window", "vol_ma5",
              "up_close", "entry_close", "stop", "stop_alt", "extended", "approach", "evidence")


def _used_origins(res: PatternResult, detected: bool = False) -> dict[str, str]:
    """이 결과가 쓴 규칙의 출처만 — 근거 · 경고 줄 끝 [키] (+ 탐지면 이 기법 규칙 · 추세선 점수 항목)."""
    keys = {"technique", "precondition"}
    for x in res.reasons + res.warnings:
        g = _TAG.search(x)
        if g:
            keys.add(g.group(1))
    if detected:
        keys.update(_RULE_KEYS)
        if res.metrics.get("stage_label") and not res.metrics.get("intraday_final"):
            keys.add("pre_stage_label")
        keys.update(p["origin"] for p in (res.metrics.get("line_score_parts") or {}).values())
        keys.add("tl_weights")
        if res.metrics.get("vol_test") == "level":
            keys.add("vol_level")
        else:
            keys.add("vol_cross")
        keys.add("confirm_video" if res.metrics.get("confirm_mode") == "video" else "confirm_fractal2")
    return {k: ORIGIN[k] for k in sorted(keys) if k in ORIGIN}


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = resolve_cfg(ctx.cfg.pattern_cfg(NAME, TLFibConfig), ctx)
    res = PatternResult(name=NAME, label=LABEL)
    mt = res.metrics
    mt.update(rule_version=RULE_ID, rule_id=RULE_ID, core_version=tq.CORE_VERSION)
    eod = tq.eod_frame(ctx)
    partial = len(eod) < len(ctx.df)
    T = len(eod) - 1
    if T < cfg.tl.min_len:
        res.warnings.append(f"이력 부족 ({T + 1}봉 — 추세선 길이 최소 {cfg.tl.min_len}봉) [tl_min_len]")
        mt.update(phase="UNKNOWN", phase_label=PHASE_KO["UNKNOWN"])
        mt["origin"] = _used_origins(res)
        return res
    b, sim = tb.simulate_ctx(ctx, cfg.tl)                   # trendline_break 와 같은 계산(종목마다 한 번)
    m = run(b, cfg, sim)
    j = judge(m, T)
    mt["asof"] = b.date(T)
    prov = None                                            # 장중 잠정 결과는 단계 · 진입가에 쓰지 않는다(완성 봉만)
    prov_sig = False
    # 열린 설정(고점 확정 대기 · 확정 뒤 대기 · 신호 뒤 창)이 없으면 오늘 봉 하나로는 신호가 날 수 없다(새 돌파 → 고점 확정 →
    # 접촉 · 반등이 한 봉에 다 일어날 수 없음) — 그때는 오늘 봉을 붙인 추세선 재계산(종목당 ~20 ms)을 생략한다
    if partial and j["phase"] in ("CANDIDATE",) + PRE_PHASES + fp.POST_PHASES:
        bp = _bars_with_partial(ctx)                       # 순차 기계 — 봉 T 까지 상태는 위와 같다
        mp = run(bp, cfg, tb.simulate(bp, cfg.tl, ctx.df))
        jp = judge(mp, T + 1)
        mt["provisional_phase"] = jp["phase"]
        if jp["phase"] != j["phase"]:
            prov_sig = jp["phase"] == "SIGNAL"
            what = "신호" if prov_sig else PHASE_KO[jp["phase"]]
            res.warnings.append(f"장중 잠정: 오늘 미완성 봉(거래량 하루치 환산 추정)까지 보면 '{what}' — 판정 · 단계 · 진입가는 "
                                "어제까지 완성 봉, 마감 뒤 다시 볼 것 [provisional]")
    ph, stage, s = j["phase"], j["stage"], j["setup"]
    label = PHASE_KO[ph] + (" · 추세선 안착 확인 대기" if ph in PRE_PHASES and not j["tl_conf"] else "")
    mt.update(phase=ph, phase_label=label, provisional=prov_sig, tl_conf=j["tl_conf"])
    if s is not None:
        mt["trendline"] = _tl_info(m, s, j["t"])           # 빗각 쪽 상태 — 피보 설정과 따로 (부록 §5-6)
    if stage is None:
        res.warnings += _why_not(m, j, T)
        if partial:
            res.warnings.append("장중 스캔 — 판정은 어제까지 완성 봉 [provisional]")
        mt["origin"] = _used_origins(res)
        return res
    _detected(res, ctx, cfg, m, j, b, T, sim, prov is not None, partial)
    mt["origin"] = _used_origins(res, detected=True)
    return res


def _detected(res: PatternResult, ctx: StockContext, cfg: TLFibConfig, m: Machine, j: dict, b: tq.Bars, T: int,
              sim: tb.Sim, provisional: bool, partial: bool) -> None:
    mt, R, W = res.metrics, res.reasons, res.warnings
    fib = cfg.fib
    s, ph, tt = j["setup"], j["phase"], j["t"]           # tt = 판정 봉 (장중 잠정이면 오늘)
    bb, d = m.b, m.b.date
    brk, line = s.brk, s.brk.line
    lv, post = s.lv, j["post"] or {}
    signaled = ph in fp.POST_PHASES
    res.detected, res.stage = True, j["stage"]
    if ph in fp.PRE_STAGE_LABEL and res.stage == NEAR_PIVOT:      # 신호 전 접촉 · 접근 — 피벗 없음 [pre_stage_label]
        mt["stage_label"], mt["stage_short"] = fp.PRE_STAGE_LABEL[ph]
    entry, stop, stop_r = j["pivot"], j["stop"], j["stop_r"]
    res.pivot, res.stop = entry, stop
    if signaled:
        res.breakout_date = d(s.s)
    res.start_date = d(line.anchor_i)
    res.end_date = d(s.s) if signaled else d(tt)
    depth_r = s.active_r if (signaled or ph == "TOUCH") else (s.approach[1] if ph == "APPROACH" else None)
    # 점수 — 추세선 품질은 돌파일(t0) 자료로 잰 trendline_break 점수(동결)
    hf = tq.hammer_frame(b)
    sc = tb.score_line(b, line, cfg.tl, sim.slopes, hf, brk, T)
    reb_x = None
    if signaled and s.s >= 4:
        base4 = float(np.mean(bb.volume[s.s - 4:s.s]))
        reb_x = _f(bb.volume[s.s] / base4) if base4 > 0 else None
    line_score = float(sc["score"]) if sc["coverage"] > 0 else None
    res.score, cov, parts = score_parts(cfg, line_score, depth_r, reb_x)
    close_t = float(bb.close[tt])
    tl = mt.get("trendline") or _tl_info(m, s, tt)
    mt.update(
        state=s.state, break_date=d(s.b), wave_low=s.L, wave_low_date=d(s.l_i), l_mode=s.l_mode, l_last_touch_date=d(s.p),
        wave_high=s.H, wave_high_date=d(s.h), confirm_date=d(s.c), confirm_mode=fib.swing_confirm, resets=s.resets,
        **{f"fib_{r * 1000:.0f}": float(v) for r, v in sorted(lv.items())},
        retracement=_f(tq.retracement(s.H, s.L, close_t)), touch_mode=fib.touch_mode, active_level=s.active_r,
        touch_date=d(s.touch_bar) if s.touch_bar is not None else None,
        touches=[f"{d(i)} {_pct(r)}" for i, r in s.touches], approach_level=s.approach[1] if ph == "APPROACH" else None,
        entry=entry, stop_level=stop_r, stop_pct=(1 - stop / entry) if (entry and stop) else None,
        stop_alt=entry * (1 - fib.stop_alt_pct) if entry else None, pre_signals=[d(i) for i in s.pre],
        score_coverage=cov, score_parts={k: {kk: (_f(vv) if kk in ("x", "s", "w") else vv) for kk, vv in p.items()}
                                         for k, p in parts.items()},
        line_score=sc["score"], line_score_coverage=sc["coverage"], line_score_parts=sc["parts"], line_features=sc["features"],
        stage_origin="stage_map",
    )
    if ph in PRE_PHASES:
        mt["expires_in"] = int(fib.setup_expiry - (tt - s.c))
        mt["expires_basis"] = d(tt)                   # 남은 봉을 센 완성 봉 (장중이면 오늘 진행 중인 봉이 그 첫 봉)
    if signaled:
        mt.update(signal_date=d(s.s), bars_since_signal=int(tt - s.s), signal_volume=_f(s.vr["volume"]),
                  signal_vol_ma5=_f(s.vr["vol_ma5"]), signal_vol_x=reb_x, vol_test=s.vr["test"],
                  stop_hit_date=d(post["stop_hit"]) if post.get("stop_hit") is not None else None,
                  stop_fill=post.get("stop_fill"),
                  extended_date=d(post["ext_i"]) if post.get("ext_i") is not None else None,
                  invalid_after_signal_date=d(post["broke_i"]) if post.get("broke_i") is not None else None)

    # ---- 근거
    R.append(f"규칙 {RULE_ID} — 빗각 추세선 '안착 확인' 돌파 → 돌파 뒤 고점 확정 → 피보 23.6 · 38.2 · 50% 관심 구간 접촉 → "
             "거래량 실린 반등 양봉 종가 [technique]")
    R.append(f"하향 추세선(돌파 때 동결): 앵커 {tl['anchor_date']} 고가 {_won(tl['anchor_price'])} · 접점 {tl['touch_count']}개 "
             f"({', '.join(tl['touch_dates'])}) · 길이 {tl['length']}봉 · 기울기 {tl['slope_pct']:+.2%}/봉 (로그 눈금) [tl_freeze]")
    vtxt = (f"거래량 {tl['vol_ratio']:.2f}배 {'≥' if brk.vol == 'ok' else '<'} {cfg.tl.vol_mult}" if tl["vol_ratio"] is not None
            else "거래량 모름")
    R.append(f"{tl['break_date']} 빗각 돌파: 종가 {_won(tl['break_close'])} > 선 {_won(tl['break_price'])} "
             f"({tl['break_close'] / tl['break_price'] - 1:+.1%}) · {vtxt} (직전 {cfg.tl.vol_n}봉 평균, 당일 제외 · "
             f"{tb.VOL_KO[brk.vol]}) [break_vol_required]")
    if tl["conf_date"]:
        how = (f"그날 선 +{cfg.tl.conf_pct:.0%} 이상 종가 [tl_conf_pct]" if tl["conf_how"] == "pct"
               else f"돌파일 포함 {cfg.tl.conf_bars}종가 연속 선 위 [tl_conf_bars]")
        R.append(f"안착 확인 {tl['conf_date']} — {how}")
    else:
        R.append("안착 확인 전 — 신호는 안착 확인 뒤에만 (접촉은 그대로 두고 반등 양봉은 기록만) [signal_after_conf]")
    cm = "음봉 · 종가 하락 봉" if fib.swing_confirm == "video" else "좌우 2봉"
    R.append(f"기준 파동 L {_won(s.L)} ({d(s.l_i)}, 마지막 접점 {d(s.p)} ~ 돌파일 최저) → H {_won(s.H)} ({d(s.h)}) · "
             f"고점 확정 {d(s.c)} ({cm}) [wave_low]")
    R.append("관심 구간 " + " · ".join(f"{_pct(r)} {_won(lv[r])}" for r in fib.levels_buy)
             + f" · 무효선 {_pct(fib.level_invalid)} {_won(lv[fib.level_invalid])} (확률 아님) [fib_buy]")
    if s.touches:
        t1, r1 = s.touches[-1]
        mode = "아래꼬리 허용 'wick'" if fib.touch_mode == "wick" else "밴드 'band'"
        R.append(f"접촉: {d(t1)} 저가 {_won(bb.low[t1])} 가 {_pct(r1)} 라인 {_won(lv[r1])} 에 닿고 종가 {_won(bb.close[t1])} 가 "
                 f"라인 위 ({mode}, 허용 {fib.tol:.1%}) [touch_{fib.touch_mode}]")
    if ph == "APPROACH":
        R.append(f"눌림 진행: 종가 {_won(close_t)} 가 {_pct(s.approach[1])} 라인 {_won(lv[s.approach[1]])} 위 "
                 f"{fib.approach_pct:.0%} 안 [approach]")
    if ph == "TOUCH":
        left = fib.signal_window - (tt - s.touch_bar)
        when = f"{d(tt)} 완성 봉 기준 남은 봉 {left} (오늘 진행 중인 봉 포함)" if partial else f"남은 봉 {left}"
        R.append(f"반등 양봉 대기 — {when} (양봉 · 전일보다 높은 종가 · 거래량이 5일 거래량 이평 상향돌파면 종가 신호) "
                 "[signal_window]")
    if signaled:
        R.append(f"신호 {d(s.s)}: 양봉 · 전일보다 높은 종가 · 거래량 {_won(s.vr['volume'])} > 5일 거래량 이평 "
                 f"{_won(s.vr['vol_ma5'])} (오늘 포함, {'상향돌파' if s.vr['test'] == 'cross' else '수준 비교'}) — 종가 "
                 f"{_won(entry)} 진입 [entry_close]")
    if stop is not None:
        rel = f" (진입가 대비 −{1 - stop / entry:.1%})" if entry else ""
        nm = f"다음 라인 {_pct(stop_r)}" if stop_r is not None else "파동 저점 L (더 깊은 라인 없음)"
        R.append(f"손절 {_won(stop)} = {nm}{rel} · 함께 보기: 파동 저점 {_won(s.L)}"
                 + (f" · 진입가 −{fib.stop_alt_pct:.0%} {_won(entry * (1 - fib.stop_alt_pct))}" if entry else "")
                 + ("" if signaled else " (예정 — 신호 전)") + " [stop]")
    R.append(f"동결 추세선 오늘 {_won(tl['line_today'])} · 종가 {tl['close_vs_line']:+.1%} — 빗각 상태: {tl['state_label']}"
             + (" · 신호 전 종가가 선 이하면 설정 무효" if not signaled else "") + " [tl_invalid]")
    R.append(f"품질 점수 {res.score:.0f} (관측 비중 {cov:.0%}) — 추세선 품질 {sc['score']:.0f}(돌파일 동결) · 라인 깊이 · 반등 거래량, "
             "확률 아님 [score]")

    # ---- 경고
    if s.pre:
        W.append("안착 확인 전 반등 양봉 " + ", ".join(d(i) for i in s.pre) + " — 신호 조건은 채웠지만 기록만 [signal_after_conf]")
    if ph in PRE_PHASES and not j["tl_conf"]:
        W.append("추세선 안착 확인 전 — 신호를 낼 수 없어 형성 중 [pending_stage]")
    if ph == "STOPPED":
        W.append(f"손절: {d(post['stop_hit'])} 저가가 손절 {_won(stop)} 아래 (재현 체결 {_won(post['stop_fill'])}) [stop_fill]")
    if ph == "RETEST":
        W.append(f"종가 {_won(close_t)} 가 진입가 {_won(entry)} 아래 — 손절 {_won(stop)} 위에서 재시험 [stage_map]")
    if ph == "EXTENDED":
        W.append(f"이격: 종가 {_won(close_t)} > 진입가 × {1 + fib.extended_pct:g} — 추격 구간 [extended]")
    if post.get("broke_i") is not None:
        W.append(f"무효 규칙(61.8% 아래 종가 · L 붕괴) {d(post['broke_i'])} — 신호 뒤라 표시만 [invalid_618]")
    if signaled and not tl["alive"]:
        W.append(f"{tl['below_date']} 동결 추세선 아래 종가 — 빗각 돌파 실패(신호 뒤라 표시만, 손절은 피보 라인) [both_states]")
    if not signaled:
        lo_t, inv = float(bb.low[tt]), lv[fib.level_invalid]
        bar = f"마지막 완성 봉({d(tt)}) 저가" if partial else "오늘 저가"
        if tq.lt(lo_t, inv):
            W.append(f"{bar} {_won(lo_t)} 가 {_pct(fib.level_invalid)} 무효선 {_won(inv)} 아래 — 종가가 선 위라 무효는 "
                     "아님(종가 기준) [invalid_618]")
        elif stop is not None and tq.lt(lo_t, stop):
            W.append(f"{bar} {_won(lo_t)} 가 예정 손절 {_won(stop)} 아래 — 장중 이탈(신호 전이라 손절 판정은 안 함) [stop]")
    if ph == "TOUCH" and s.reject is not None and s.reject[0] >= s.touch_bar:
        W.append(f"{d(s.reject[0])} 반등 양봉이었지만 {s.reject[1]} [vol_cross]")
    shallow = depth_r is not None and depth_r < 0.45
    if shallow:
        W.append(fp.SHALLOW_CAUTION + " [line_depth]")
    if j.get("other") is not None:
        o = j["other"]
        W.append(f"같은 종목의 새 설정(빗각 돌파 {d(o.b)}, {o.state}) — 신호 표시 창 동안 대표는 지난 신호 [one_setup]")
    for t, kind, x in m.events:
        if kind == "busy" and t > s.b:
            W.append(_event_text(m, t, kind, x))
    if signaled:
        h2 = tq.window_halts(ctx.df, s.s - 5, s.s)
        if h2:
            W.append(f"신호 거래량 5일 이평 구간에 거래정지 {', '.join(h2)} — 비교가 틀릴 수 있음 [vol_ma5]")
    W.append(fp.EVIDENCE + " [evidence]")
    W.append(AUTO_LINE)
    W.append(tb.VOL_RAW)
    if provisional:
        W.append("장중 잠정 신호 — 오늘 봉 미완성(거래량은 하루치 환산 추정). 종가가 확정된 뒤 다시 볼 것 · 진입가는 지금 값 "
                 "[provisional]")
    elif partial:
        W.append("장중 스캔 — 판정은 어제까지 완성 봉 [provisional]")

    # ---- 체크리스트 · 청산 · 재현 — 완성 봉(b, T)으로만
    rep = _replay(m, T, fib)
    ck = tq.run_checklist(b, T, tq.inputs_from_ctx(ctx, entry=entry, stop=stop, replay=rep))
    cnt = tq.checklist_counts(ck)
    mt.update(checklist=[c.to_dict() for c in ck], checklist_counts=cnt, replay_n=len(rep), replay=rep)
    R.append(f"체크리스트 10 (검증 전): 통과 {cnt[tq.PASS]} · 경고 {cnt[tq.WARN]} · 모름 {cnt[tq.UNKNOWN]} [replay]")
    if signaled and not provisional:
        mt["exit_plan"] = tq.exit_plan(b, T, entry_i=s.s)
    mt["bulkowski"] = [tq.bulkowski_note("trendline_down"), tq.bulkowski_note("fib")] + ([fp.RISK_SHALLOW] if shallow else [])
    if sc["hammer"]:
        mt["bulkowski"].append(tq.bulkowski_note("hammer"))
    mt["history"] = [{"break": d(x.b), "state": x.state, "end": d(x.end), "why": _why(x),
                      "signal": d(x.s) if x.s is not None else None} for x in m.history[-5:]]
    res.annotations = _annotations(m, s, j, fib, stop_r, tt, provisional)
    fin = fp.intraday_final(ctx, j, PRE_PHASES) if partial else None    # 저가 규칙은 장중 저가로 이미 정해짐
    if fin:
        fp.apply_intraday_final(res, fin)
        res.warnings[0] += " [intraday_final]"


def _annotations(m: Machine, s: TLSetup, j: dict, fib: fp.FibPullbackConfig, stop_r: float | None, tt: int,
                 provisional: bool) -> list[dict]:
    b, d = m.b, m.b.date
    if b.dates is None:
        return []
    line, brk = s.brk.line, s.brk
    idx = sorted({line.anchor_i, *line.touches, tt, *range(line.anchor_i, tt + 1, 5)})
    out = [segment([(b.dates[i], line.value(i)) for i in idx if 0 <= i <= tt], "하향 추세선 (돌파 때 동결)", "#ff6d00")]
    out += [marker(b.dates[i], "앵커" if k == 0 else f"접점{k + 1}", "above", "#ff6d00", "circle")
            for k, i in enumerate(line.touches)]
    out.append(marker(d(brk.t0), "빗각 돌파", "below", "#e91e63", "arrowUp"))
    if m.conf_at(s, tt) and brk.t_conf != brk.t0:
        out.append(marker(d(brk.t_conf), "안착 확인", "below", "#ad1457", "circle"))
    out.append(segment([(d(s.l_i), s.L), (d(s.h), s.H)], "기준 파동", "#7e57c2"))
    for r in fib.levels_buy:
        st = r == stop_r
        out.append(hline(s.lv[r], f"피보 {_pct(r)} 관심 구간" + (" · 손절" if st else ""),
                         "#1e88e5" if st else "#7e57c2", "solid" if st else "dashed"))
    inv = fib.level_invalid
    out.append(hline(s.lv[inv], f"{_pct(inv)} 무효선" + (" · 손절" if stop_r == inv else ""), "#ef5350",
                     "solid" if stop_r == inv else "dotted"))
    out.append(marker(d(s.h), "고점", "above", "#ef5350", "arrowDown"))
    if s.c is not None and s.c != s.h:
        out.append(marker(d(s.c), "고점 확정", "above", "#9e9e9e", "circle"))
    if s.touches:
        t1, r1 = s.touches[-1]
        out.append(marker(d(t1), f"접촉 {_pct(r1)}", "below", "#7e57c2", "arrowUp"))
    for i in s.pre:
        out.append(marker(d(i), "안착 전 반등(기록)", "below", "#9e9e9e", "circle"))
    if s.s is not None:
        out.append(hline(s.entry, "진입 (신호 종가)", "#e91e63", "solid"))
        out.append(marker(d(s.s), "신호" + (" (장중 잠정)" if provisional else ""), "below", "#e91e63", "arrowUp"))
        post = j["post"] or {}
        if post.get("stop_hit") is not None:
            out.append(marker(d(post["stop_hit"]), "손절", "above", "#1e88e5", "arrowDown"))
    return out
