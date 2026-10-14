"""빗각(하향) 추세선 돌파 `trendline_break` — 김정환 《차트의 기술》 영상 [00:00–01:00, 21:00–22:00, 43:00–47:00,
49:00–50:00, 54:00–56:00] · 스펙 docs/2026-10-14-chart-techniques-design.md §3 · 부록 docs/2026-10-14-chart-techniques-addendum.md
§4 (부록의 수치 · 출처 · 알고리즘이 스펙의 '구현 선택' 추정보다 우선). 공용 부품 chart_screener/techniques.py (tq).

자료
  일봉 EOD 완성 봉만 (tq.eod_frame — 장중 미완성 봉은 판정에서 빼고 '장중 잠정' 확인 줄에만 쓴다). 수정주가 OHLC ·
  거래량은 Tech 캐시 원 거래량(미수정 — 거래정지 없는 분할 · 무상증자는 알아채지 못함, 경고로 적음).

선 (tq.fit_downtrend_line — 봉 t 종가를 시험할 선은 t−1 까지 자료로만 맞춘다)
  확정 소고점(좌우 3봉, p+3 ≤ t−1) · 앵커 = 최근 250봉 최고 소고점(Sperandeo) · 로그 눈금 · 앵커에서 내려 돌려 처음 닿는 선
  (고가 ≤ 선 × 1.005) · 앵커 뒤 선 위 종가 없음 · 접점(선 × 0.985 ~ × 1.005 의 확정 소고점, 이웃 10봉 이상) 3개 이상 · 길이 40봉 이상.

상태 기계 (부록 §4.4 — 봉 min_len 부터 차례로, 봉 t 판정은 [0..t] 만 → 앞부분 불변. simulate() 가 봉마다 BarState 를 남긴다)
  탐색  선이 있고 C[t] > 선(t) · C[t−1] ≤ 선(t−1) → 돌파 t0. 그때의 선(앵커 · 기울기 · 접점) · 거래량 비율을 동결 — 다시 그리지 않음.
        거래량 ≥ 직전 50봉 평균(당일 제외) × 1.5 → '안착 확인 중', 미달 → '돌파(거래량 미달)' 관찰.
        (50봉 이력 없음 → '돌파(거래량 모름)', 비교 구간에 거래정지일 → '돌파(거래량 확인 못 함(거래정지))' — 둘 다 미달처럼 관찰)
        돌파 아니고 선 × 0.98 ≤ C ≤ 선 → '돌파 임박'. 선은 있지만 더 아래 → 탐지 안 함(이유만 적음).
  동결  C ≤ 동결 선 → 확인 전이면 '실패(가짜 돌파)', 확인 뒤면 '실패' → 동결을 풀고 다음 봉부터 다시 탐색 (실패는 5봉 표시).
        확인 전이고 C ≥ 그날 선 × 1.03 또는 돌파일 포함 3종가 연속 선 위 → '안착 확인' (= 기법의 '돌파'). 돌파일 당일도 확인될 수 있다.
        확인 뒤 선 쪽 되돌림은 종가가 선 위면 실패 아님. '돌파' 표시 20봉 → 그 뒤 동결을 풀고 그 봉부터 다시 탐색.

Tech 단계 대응 (구현 선택 — base.classify_stage 뜻에 맞춤)
  돌파 임박                   피벗 근접   pivot = 다음 봉 시험선의 다음 봉 값(오늘까지 자료로 맞춘 선), stop 없음
  안착 확인 중                피벗 근접   기법상 '돌파'는 안착 확인 뒤 — 확인 대기. pivot = 돌파가(돌파일 선 값)
  안착 확인(돌파) · 매수 범위 돌파        종가 ≤ 돌파가 × 1.05 (Tech 공통 매수 범위)
                  · 그 위     이격 과다
                  · 돌파가 아래(선 위)  피벗 근접 (되돌림 — 실패 아님)
  돌파(거래량 미달 · 모름)    형성 중     스펙상 돌파 거래량 필수 → 매수 단계로 세지 않는 관찰
  실패 · 실패(가짜 돌파)      돌파 실패
  stop = 돌파 뒤 단계에서 다음 봉 동결 선 값 (종가가 그 아래면 실패 — 영상 '선 아래 재하락 = 실패').
  breakout_date = 거래량 확인 · 안착 확인된 돌파의 돌파일(t0) — 확인일은 metrics['break']['conf_date'].

점수 (0~100, 구현 선택 가중치 — 기울기 최대: Bulkowski 표본 효과 기울기 ≈10%p · 나머지 ≈2%p, 부록 §4.4)
  완만한 기울기 30 · 접점 수 15 (3개 ⅓ · 4개 ⅔ · 5개 이상 1) · 돌파 거래량 15 · 간격 중앙값 > 13봉 10 · 길이 > 48봉 10 ·
  돌파 전 거래량 감소 10 · 진입 추세 평평 5 · 바닥 망치형 5. 모름 · 해당 없음 항목은 빼고 다시 나눈다(관측 비중 함께 표시).
  돌파 단계 점수는 돌파일(t0) 자료로 잰 값(동결). 성공 확률이 아니다.

출처
  규칙마다 metrics['origin'][키] 에 '영상 [mm:ss]' · 출처 URL · '구현 선택: 이유' — 근거 줄 끝의 [키] 가 그 키다.
  불코우스키 미국 통계는 metrics['bulkowski'] 에 '참고 — 불코우스키 미국 통계(우리 데이터 아님)' 라벨로만. 확률로 쓰지 않는다.
  일지 rule 칸 = metrics['rule_version'] = 'tlbrk_v1' (규칙을 바꾸면 v 를 올린다).

다른 모듈에서 쓰기: simulate(Bars, cfg, df) → Sim(states · breaks · slopes · swings) — 동결 선 · 확인일이 필요한
trendline_fib 등이 같은 상태 기계를 다시 쓸 수 있다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from .. import techniques as tq
from .base import (BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult, StockContext, hline, marker,
                   register, segment)

NAME = "trendline_break"
LABEL = tq.PATTERN_LABELS[NAME]           # '빗각 추세선 돌파'
RULE_ID = tq.RULE_IDS[NAME]               # 'tlbrk_v1' — 일지 rule 칸
VIDEO_TS = "00:00–01:00, 21:00–22:00, 43:00–47:00, 49:00–50:00, 54:00–56:00"

# 점수 가중치 (구현 선택)
W_DEFAULT = {"slope": 30.0, "touches": 15.0, "break_vol": 15.0, "wide_gap": 10.0, "long": 10.0,
             "vol_declining": 10.0, "entry_flat": 5.0, "hammer": 5.0}
FACTOR_KO = {"slope": "완만한 기울기", "touches": "접점 수", "break_vol": "돌파 거래량", "wide_gap": "접점 간격",
             "long": "선 길이", "vol_declining": "돌파 전 거래량 감소", "entry_flat": "진입 추세 평평", "hammer": "바닥 망치형"}
FACTOR_ORIGIN = {"slope": "tl_slope_ref", "touches": "tl_bonus_touches", "break_vol": "tl_break_vol",
                 "wide_gap": "tl_wide_gap", "long": "tl_long_len", "vol_declining": "tl_vol_trend",
                 "entry_flat": "tl_entry_flat", "hammer": "tl_hammer_window"}


@dataclass
class TLBreakConfig(tq.TrendlineConfig):
    """선 상수(부록 §4.2 TL_*)는 tq.TrendlineConfig 그대로, 아래는 이 기법의 상태 · 점수 상수."""
    conf_pct: float = 0.03          # TL_CONF_PCT — 그날 선 값 대비 +3% 종가 = 안착 확인
    conf_bars: int = 3              # TL_CONF_BARS — 돌파일 포함 연속 3종가 선 위 = 안착 확인
    near_pct: float = 0.02          # TL_NEAR_PCT (구현 선택) — 선 아래 2% 안 = 돌파 임박
    hammer_window: int = 20         # TL_HAMMER_WINDOW (구현 선택) — 돌파 전 20봉 안 바닥 망치형
    display_bars: int = 20          # TL_DISPLAY_BARS (구현 선택) — 안착 확인 뒤 '돌파' 표시 봉 수
    fail_display_bars: int = 5      # 구현 선택 — 실패 표시 봉 수
    show_lowvol_break: bool = True  # TL_SHOW_LOWVOL_BREAK — 거래량 미달 돌파를 관찰로 남김
    slope_ref_window: int = 250     # 완만 기준: 그날 이전 250거래일 검출 선
    slope_ref_min: int = 2          # 구현 선택 — 비교할 다른 선 최소 개수
    entry_flat_pct: float = 0.0025  # 구현 선택 — |진입 추세| ≤ 0.25%/봉 = 평평
    buy_range: float = 0.05         # Tech 공통 매수 범위 (base.classify_stage 기본값)
    replay_bars: int = 20           # 체크리스트 4 — 안착 확인 뒤 20거래일 (구현 선택, 다른 기법과 같은 크기)
    weights: dict = field(default_factory=lambda: dict(W_DEFAULT))


# ---------------------------------------------------------------- 출처
_CORE_KEYS = ("tl_log", "tl_lookback", "tl_anchor_highest", "tl_anchor_volume", "tl_tol_cut", "tl_close_cut", "tl_touch",
              "tl_min_touches", "tl_bonus_touches", "tl_min_gap", "tl_wide_gap", "tl_min_len", "tl_long_len",
              "tl_vol_trend", "tl_entry_trend", "tl_break_vol", "tl_target", "swing", "baseline_excl_today", "cross")
ORIGIN: dict[str, str] = {k: tq.ORIGIN[k] for k in _CORE_KEYS}
ORIGIN.update(tq.HAMMER_ORIGIN)
ORIGIN.update({
    "technique": tq.video(VIDEO_TS) + " 빗각(하향) 추세선 돌파 — 부록 §4 (불코우스키 4원칙 " + tq.video("44:00–46:00") + ")",
    "tl_break": ("돌파 = 처음으로 선 위 종가 C[t] > 선(t) · C[t−1] ≤ 선(t−1), 장중 고가만 넘으면 돌파 아님 — Bulkowski "
                 "(https://thepatternsite.com/trenddown.html) · 키움 돌파 정의 · TigerShark "
                 "(http://www.tigersharktrading.com/articles/8406/1/When-Is-a-Trendline-Break-Valid/Page1.html) · 김정환 "
                 "(https://ebook-product.kyobobook.co.kr/dig/epd/sam/E000003218169)"),
    "tl_conf_pct": ("안착 확인 ① 그날 선 값 대비 +3% 이상 종가 — Murphy (Penteado https://arxiv.org/pdf/1302.1228) · "
                    "Edwards & Magee (Brandt https://www.peterlbrandt.com/?p=12076) · " + tq.video("55:00–56:00")
                    + " — 스펙의 '돌파일 종가 +3%' 대신 선 기준 (부록 §1 #8)"),
    "tl_conf_bars": ("안착 확인 ② 돌파일 포함 연속 3종가 선 위 — Penteado 3봉 (https://arxiv.org/pdf/1302.1228) · "
                     + tq.video("55:00–56:00") + " 3~4일"),
    "tl_near": "스펙 §3 단계 · " + tq.choice("선 아래 2% 안 = 돌파 임박 — 접점 허용치와 같은 크기 (영상 · 부록에 근거 없음, "
                                            "부록 §4.2 TL_NEAR_PCT)"),
    "tl_hammer_window": (tq.video("00:00") + " 바닥 망치형 관찰 · "
                         + tq.choice("돌파 전 20봉 안 — 바닥권 = 직전 종가 < EMA20 이고 연중 위치 ≤ ⅓ (부록 §4.3)")),
    "tl_display": tq.choice("안착 확인 뒤 20봉 '돌파' 표시 — 그 뒤 동결을 풀고 다시 탐색"),
    "tl_fail_display": tq.choice("실패는 그 뒤 5봉 표시 — Tech breakout_window 5봉과 같은 크기"),
    "tl_lowvol": ("돌파 거래량 필수(스펙 · Edwards & Magee · O'Neil) ↔ 반대 증거 Bulkowski 거래량 연구 "
                  "(https://www.thepatternsite.com/VolumeStudy.html) → 조용히 버리지 않고 '돌파(거래량 미달)' 관찰 "
                  "(부록 §1 #9 · TL_SHOW_LOWVOL_BREAK)"),
    "tl_fail": (tq.video("54:00–56:00") + " 선 아래 재하락 = 실패 · 동결 선 아래 종가 — 확인 뒤 선 위 되돌림은 실패 아님 "
                "(Bulkowski 표본에서 되돌림이 흔함 https://thepatternsite.com/trenddown.html) · 첫 종가 이탈 "
                "(https://thepatternsite.com/uptrendlines.html)"),
    "tl_freeze": ("돌파 때 앵커 · 기울기 · 접점 · 돌파일 · 거래량 비율 · 점수를 동결, 다시 그리지 않음 — 부록 §4.4 · "
                  "LuxAlgo 덧칠 함정 (https://www.luxalgo.com/library/indicator/trendlines-with-breaks/)"),
    "tl_slope_ref": ("완만 = 그날 이전 250거래일 검출 선들의 |기울기| 중앙값 이하 — Bulkowski 중앙값 분할 "
                     "(https://thepatternsite.com/trenddown.html) · "
                     + tq.choice("이 종목에서 앵커가 다른 선 2개 이상일 때만, 같은 앵커는 창 안 마지막 값 — 지금 선의 옛 값은 "
                                 "늘 더 가팔라 빼고 비교")),
    "tl_entry_flat": "진입 추세 평평 가점 — Bulkowski trenddown · " + tq.choice("앵커 전 20봉 ln 종가 기울기 |·| ≤ 0.25%/봉"),
    "tl_weights": tq.choice("점수 가중치 기울기 30 · 접점 15 · 돌파 거래량 15 · 간격 10 · 길이 10 · 거래량 감소 10 · 진입 추세 5 · "
                            "바닥 망치 5 — 기울기를 가장 크게(부록 §4.4), 모름 · 해당 없음 항목은 빼고 다시 나눔"),
    "tl_stage_map": tq.choice("Tech 단계 — 돌파 임박 · 안착 확인 중 = 피벗 근접(기법상 '돌파'는 안착 확인 뒤), 안착 확인 = 돌파, "
                              "돌파가 +5% 초과 = 이격 과다, 돌파가 아래 · 선 위 = 피벗 근접(되돌림), 거래량 미달 · 모름 = 형성 중(관찰), "
                              "실패 = 돌파 실패"),
    "tl_stop": (tq.video("54:00–56:00") + " 선 아래 재하락 = 실패 → 손절가 = 다음 봉 동결 선 값(종가 기준) · "
                + tq.choice("돌파 전 단계는 손절 없음")),
    "tl_pivot": tq.choice("피벗 — 돌파 뒤 = 돌파가(돌파일 선 값, Bulkowski 측정 규칙의 돌파가와 같음) · 돌파 임박 = 다음 봉 시험선의 "
                          "다음 봉 값(오늘까지 자료로 맞춘 선, 실시간 감시용)"),
    "tl_buy_range": tq.choice("이격 과다 = 종가 > 돌파가 × 1.05 — Tech 공통 매수 범위(base.classify_stage 기본값)"),
    "tl_halt_vol": tq.choice("돌파 거래량 비교 구간(직전 50봉)에 거래정지일이 있으면 거래량 확인으로 세지 않음 — Tech 거래량은 "
                             "미수정이라 분할 · 병합이면 몇 배로 틀림 (cup_with_handle 과 같은 처리)"),
    "tl_partial": tq.choice("장중엔 어제까지 완성 봉으로 판정, 오늘 미완성 봉은 '장중 잠정' 확인 줄에만 (거래량 하루치 환산 추정)"),
    "tl_replay": tq.choice("체크 4 — 이 종목의 지난 돌파 중 거래량 확인 · 안착 확인된 것만, 안착 확인 종가 진입(체크리스트 · "
                           "백테스트와 같은 진입) · 20봉 뒤 종가, 20봉이 지난 신호만 (우리 데이터 재현, 확률 아님)"),
})

# ---------------------------------------------------------------- 상태
FAR, NEAR, PENDING, CONFIRMED, LOWVOL, FAKE, FAIL = "far", "near", "pending", "confirmed", "lowvol", "failed_fake", "failed"
PHASE_KO = {FAR: "선 아래 (돌파 임박 밖)", NEAR: "돌파 임박", PENDING: "안착 확인 중", CONFIRMED: "돌파 (안착 확인)",
            LOWVOL: "돌파(거래량 미달)", FAKE: "실패(가짜 돌파)", FAIL: "실패"}
VOL_KO = {"ok": "거래량 확인", "low": "거래량 미달", "unknown": "거래량 모름", "halt": "거래량 확인 못 함(거래정지)"}
FROZEN = (PENDING, CONFIRMED, LOWVOL)
AUTO_LINE = ("자동 작도 선 — 사람이 긋는 선과 다를 수 있음(장중 고가 · 로그 눈금 · 확정 소고점만, 영상의 손 작도 · 미세 조정 아님). "
             "리포트 차트의 선으로 확인 [technique]")
VOL_RAW = ("거래량은 미수정 원 거래량(Tech 캐시) — 거래정지 없는 무상증자 · 분할이 직전 50봉 안에 있었다면 돌파 거래량 비율이 "
           "틀릴 수 있음 [tl_halt_vol]")

_EPS = tq.EPS


def _tl(b):
    return _EPS * max(1.0, abs(b))


def _le(a, b) -> bool:
    return bool(a <= b + _tl(b))


def _ge(a, b) -> bool:
    return bool(a >= b - _tl(b))


def _gt(a, b) -> bool:
    return bool(a > b + _tl(b))


def _r(x, nd: int = 6):
    return None if x is None or not math.isfinite(float(x)) else round(float(x), nd)


@dataclass
class Break:
    """돌파 사건 — t0 에 선을 동결한다. t_conf · t_fail · t_end 는 그 뒤 봉에서 채워진다(채운 봉 ≤ 지금 봉)."""
    line: tq.TrendLine            # 동결 선 (t0 시험용 — t0−1 까지 자료로 맞춤)
    t0: int
    vr: float | None              # 돌파일 거래량 / 직전 50봉 평균(당일 제외)
    vol: str                      # 'ok' | 'low' | 'unknown' | 'halt'
    halts: list[str]
    t_conf: int | None = None
    conf_how: str | None = None   # 'pct' | 'bars'
    t_fail: int | None = None
    t_end: int | None = None      # '돌파' 표시가 끝나 동결을 푼 봉

    @property
    def price(self) -> float:
        """돌파가 = 돌파일 선 값."""
        return self.line.value(self.t0)

    def phase(self) -> str:
        if self.t_fail is not None:
            return FAIL if self.t_conf is not None else FAKE
        if self.vol != "ok":
            return LOWVOL
        return CONFIRMED if self.t_conf is not None else PENDING

    def phase_label(self) -> str:
        p = self.phase()
        if p == LOWVOL:
            return f"돌파({VOL_KO[self.vol]})" + (" · 안착" if self.t_conf is not None else "")
        return PHASE_KO[p]


@dataclass(frozen=True)
class BarState:
    """봉 t EOD 의 판정 (그 봉까지 자료만) — 앞부분 불변 시험의 비교 단위."""
    phase: str | None = None      # None = 유효한 선 없음
    anchor_i: int | None = None
    slope: float | None = None
    touches: tuple = ()
    t0: int | None = None
    t_conf: int | None = None
    t_fail: int | None = None
    vol: str | None = None


def _snap(phase: str | None, brk: Break | None = None, line: tq.TrendLine | None = None) -> BarState:
    ln = brk.line if brk is not None else line
    if ln is None:
        return BarState(phase)
    if brk is None:
        return BarState(phase, ln.anchor_i, ln.slope, tuple(ln.touches))
    return BarState(phase, ln.anchor_i, ln.slope, tuple(ln.touches), brk.t0, brk.t_conf, brk.t_fail, brk.vol)


@dataclass
class Sim:
    states: list[BarState]
    breaks: list[Break]
    slopes: list[tuple[int, int, float]]   # (봉, 앵커, |기울기|) — 탐색 단계에서 유효했던 선
    swings: list
    line: tq.TrendLine | None              # 마지막 봉에서 탐색한 선 (동결 단계면 None)
    brk: Break | None                      # 마지막 봉의 동결 · 실패 표시 돌파


def _new_break(b: tq.Bars, t: int, line: tq.TrendLine, cfg: TLBreakConfig, df) -> Break:
    vr = None
    if t >= cfg.vol_n:
        base = float(np.mean(b.volume[t - cfg.vol_n:t]))          # 당일 제외 직전 50봉
        vr = float(b.volume[t] / base) if base > 0 else None
    halts = tq.window_halts(df, t - cfg.vol_n, t - 1) if df is not None else []
    if vr is None:
        vol = "unknown"
    elif halts:
        vol = "halt"
    else:
        vol = "ok" if _ge(vr, cfg.vol_mult) else "low"
    return Break(line, t, vr, vol, halts)


def _try_confirm(brk: Break, close: float, lv: float, t: int, cfg: TLBreakConfig) -> None:
    if _ge(close, lv * (1 + cfg.conf_pct)):
        brk.t_conf, brk.conf_how = t, "pct"
    elif t - brk.t0 + 1 >= cfg.conf_bars:
        brk.t_conf, brk.conf_how = t, "bars"


def simulate(b: tq.Bars, cfg: TLBreakConfig | None = None, df=None) -> Sim:
    """봉 min_len 부터 끝까지 상태 기계(부록 §4.4). 봉 t 의 판정은 [0..t] 자료만 쓴다 — states[t] 는 b.cut(t) 로 돌려도 같다.
    df 는 거래정지일(df.attrs['halt_dates']) 확인용(없으면 생략)."""
    cfg = cfg or TLBreakConfig()
    n = b.n
    sw = tq.swing_highs(b.high, k=cfg.pivot_k)
    states = [BarState()] * n
    breaks: list[Break] = []
    slopes: list[tuple[int, int, float]] = []
    cur: Break | None = None
    failed: Break | None = None
    line: tq.TrendLine | None = None
    last: Break | None = None
    C = b.close
    for t in range(min(cfg.min_len, n), n):
        line = None
        if cur is not None:                                   # 동결
            lv = cur.line.value(t)
            if _le(C[t], lv):
                cur.t_fail = t
                failed, cur, last = cur, None, cur
                states[t] = _snap(failed.phase(), failed)
                continue
            if cur.t_conf is None:
                _try_confirm(cur, C[t], lv, t, cfg)
            if cur.t_conf is None or t - cur.t_conf < cfg.display_bars:
                states[t], last = _snap(cur.phase(), cur), cur
                continue
            cur.t_end = t                                     # 표시 끝 — 동결을 풀고 이 봉부터 다시 탐색
            cur = None
        last = None
        line = tq.fit_downtrend_line(b, t, cfg, swings=sw)
        phase = None
        if line is not None:
            slopes.append((t, line.anchor_i, abs(line.slope)))
            if tq.line_cross(line, b, t):
                cur = _new_break(b, t, line, cfg, df)
                breaks.append(cur)
                _try_confirm(cur, C[t], line.value(t), t, cfg)
                states[t], last = _snap(cur.phase(), cur), cur
                continue
            phase = NEAR if _ge(C[t], line.value(t) * (1 - cfg.near_pct)) else FAR
        if failed is not None and t - failed.t_fail < cfg.fail_display_bars and phase in (None, FAR):
            states[t], last = _snap(failed.phase(), failed), failed
            continue
        states[t] = _snap(phase, None, line)
    return Sim(states, breaks, slopes, sw, line, last)


def simulate_ctx(ctx: StockContext, cfg: TLBreakConfig) -> tuple[tq.Bars, Sim]:
    """ctx 의 완성 봉(tq.eod_frame)으로 simulate — ctx 캐시에 메모해 같은 종목에서 trendline_fib 와 한 번만 돈다
    (설정 repr 이 같을 때만 공유 · Sim 은 읽기만 한다)."""
    df = tq.eod_frame(ctx)

    def run():
        b = tq.Bars.from_df(df)
        return b, simulate(b, cfg, df)
    return ctx._memo((NAME + ".simulate", len(df), repr(cfg)), run)


def timeline(df, cfg: TLBreakConfig | None = None) -> list[BarState]:
    """일봉 df → 봉마다 BarState (시험 · 다른 모듈용)."""
    return simulate(tq.Bars.from_df(df), cfg, df).states


def stage_series(df, cfg: TLBreakConfig | None = None) -> list[dict | None]:
    """백테스트용 — 상태 기계를 한 번 돌려 봉마다 detect(df.iloc[:t+1]) 와 같은 {phase, detected, stage, pivot, stop,
    breakout_i} (탐지 안 되면 None). 점수 · 근거 · 체크리스트는 없다(detect 로). detect 를 날마다 부르면 봉 0 부터 다시 돌아
    O(n²) 이라, states[t] 가 [0..t] 만 쓰는 성질(앞부분 불변 — 시험으로 확인)을 이용한다."""
    cfg = cfg or TLBreakConfig()
    b = tq.Bars.from_df(df)
    sim = simulate(b, cfg, df)
    out: list[dict | None] = []
    for t, st in enumerate(sim.states):
        if st.phase in (None, FAR):
            out.append(None)
            continue
        if st.phase == NEAR:
            nl = _next_line(b.cut(t), cfg, sim.swings)
            out.append({"phase": NEAR, "detected": True, "stage": NEAR_PIVOT, "breakout_i": None, "stop": None,
                        "pivot": float(nl.value(t + 1)) if nl is not None else None})
            continue
        ln0 = float(np.log(b.high[st.anchor_i]))
        line = tq.TrendLine(anchor_i=st.anchor_i, anchor_price=float(math.exp(ln0)), ln0=ln0, slope=st.slope,
                            touches=st.touches, t=st.t0)
        bp = line.value(st.t0)
        out.append({"phase": st.phase, "detected": st.phase != LOWVOL or cfg.show_lowvol_break,
                    "stage": _tech_stage(st.phase, bp, float(b.close[t]), cfg), "pivot": float(bp),
                    "stop": float(line.value(t + 1)) if st.phase in FROZEN else None,
                    "breakout_i": st.t0 if st.vol == "ok" and st.t_conf is not None else None})
    return out


# ---------------------------------------------------------------- 점수
def slope_ref(slopes: list[tuple[int, int, float]], t: int, anchor: int, cfg: TLBreakConfig) -> tuple[float | None, int]:
    """(|기울기| 중앙값 | None, 비교한 선 수) — [t − 250, t−1] 에 검출된 선 중 앵커가 다른 것(같은 앵커는 창 안 마지막 값)."""
    lo = t - cfg.slope_ref_window
    lastv: dict[int, float] = {}
    for ti, a, s in slopes:
        if lo <= ti < t and a != anchor:
            lastv[a] = s
    vals = list(lastv.values())
    if len(vals) < cfg.slope_ref_min:
        return None, len(vals)
    return float(np.median(vals)), len(vals)


def bottom_hammer(hf, b: tq.Bars, lo: int, hi: int, upto: int) -> tuple[dict | None, float | None]:
    """[lo, hi] 안 마지막 바닥권 망치형 → (정보 | None, 점수 1 · 0 · None=모름). upto = 확인 사건을 볼 마지막 봉."""
    lo, hi = max(0, lo), min(hi, b.n - 1)
    if hi < lo:
        return None, None
    w = hf.iloc[lo:hi + 1]
    shape, bottom = w["shape"].to_numpy(bool), w["bottom"].to_numpy(bool)
    hits = np.flatnonzero(shape & bottom)
    if hits.size:
        j = lo + int(hits[-1])
        r = hf.iloc[j]
        k = tq.hammer_confirm(b, j, upto)
        label = "doji-hammer" if r["doji"] else ("양봉 망치" if r["white"] else "음봉 망치")
        return {"i": j, "date": b.date(j), "label": label, "yearly_pos": _r(r["yearly_pos"], 4),
                "confirm_date": b.date(k) if k is not None else None}, 1.0
    unknown = (~np.isfinite(w["avg_range"].to_numpy(float))) | (shape & ~w["bottom_known"].to_numpy(bool))
    return None, (None if unknown.any() else 0.0)


def score_line(b: tq.Bars, line: tq.TrendLine, cfg: TLBreakConfig, slopes, hf, brk: Break | None = None,
               upto: int | None = None) -> dict:
    """품질 점수 — 선(line.t 시점 자료) · 돌파(brk) 기준. 돌파가 없으면 돌파 거래량은 '해당 없음'."""
    f = tq.line_features(line, b, cfg)
    upto = b.n - 1 if upto is None else upto
    parts: dict[str, dict] = {}

    def put(k, s, value, note, na=False):
        parts[k] = {"s": s, "w": float(cfg.weights.get(k, 0.0)), "label": FACTOR_KO[k], "value": value, "note": note,
                    "na": na, "origin": FACTOR_ORIGIN[k]}

    ref, nref = slope_ref(slopes, line.t, line.anchor_i, cfg)
    a = abs(line.slope)
    if ref is None:
        put("slope", None, _r(line.slope_pct), f"기울기 {line.slope_pct:+.2%}/봉 — 비교할 다른 선 {nref}개 "
                                                 f"(최소 {cfg.slope_ref_min}) · 모름")
    else:
        ok = _le(a, ref)
        put("slope", 1.0 if ok else 0.0, _r(line.slope_pct),
            f"기울기 {line.slope_pct:+.2%}/봉 {'완만' if ok else '가파름'} — 다른 선 {nref}개 중앙값 {math.expm1(-ref):+.2%}/봉")
    nt = len(line.touches)
    put("touches", min(1.0, (nt - 2) / max(1, cfg.bonus_touches - 2)), nt,
        f"접점 {nt}개" + (f" — {cfg.bonus_touches}개 이상 가점" if nt >= cfg.bonus_touches else ""))
    mg = f["median_gap"]
    put("wide_gap", 1.0 if f["wide_gap"] else 0.0, mg,
        f"간격 중앙값 {mg:.0f}봉 ({'>' if f['wide_gap'] else '≤'} {cfg.wide_gap})" if mg is not None else "간격 없음")
    put("long", 1.0 if f["long"] else 0.0, line.length, f"길이 {line.length}봉 ({'>' if f['long'] else '≤'} {cfg.long_len})")
    vt = f["vol_trend_pct"]
    if f["vol_declining"] is None:
        put("vol_declining", None, None, "돌파 전 거래량 추세 모름")
    else:
        put("vol_declining", 1.0 if f["vol_declining"] else 0.0, vt, f"앵커 ~ 돌파 전 거래량 추세 {vt:+.2%}/봉")
    e = f["entry_trend_pct"]
    if e is None:
        put("entry_flat", None, None, f"앵커 앞 {cfg.entry_trend_bars}봉 없음 · 모름")
    else:
        ok = abs(e) <= cfg.entry_flat_pct
        put("entry_flat", 1.0 if ok else 0.0, e,
            f"앵커 앞 {cfg.entry_trend_bars}봉 추세 {e:+.2%}/봉 ({'평평' if ok else '평평 아님'}, |·| ≤ {cfg.entry_flat_pct:.2%})")
    ref_t = brk.t0 if brk is not None else line.t + 1
    hm, hs = bottom_hammer(hf, b, ref_t - cfg.hammer_window, ref_t - 1, upto)
    if hm is not None:
        put("hammer", hs, hm["date"], f"바닥 망치형 {hm['date']} ({hm['label']})"
            + (f" · 망치 확인 {hm['confirm_date']}" if hm["confirm_date"] else ""))
    else:
        put("hammer", hs, None, f"돌파 전 {cfg.hammer_window}봉 안 바닥 망치형 " + ("없음" if hs == 0.0 else "모름(이력 부족)"))
    if brk is None:
        put("break_vol", None, None, "돌파 전 — 해당 없음", na=True)
    elif brk.vol in ("unknown", "halt"):
        put("break_vol", None, _r(brk.vr, 4), VOL_KO[brk.vol])
    else:
        put("break_vol", 1.0 if brk.vol == "ok" else 0.0, _r(brk.vr, 4),
            f"돌파 거래량 {brk.vr:.2f}배 ({'≥' if brk.vol == 'ok' else '<'} {cfg.vol_mult}, 직전 {cfg.vol_n}봉 평균 · 당일 제외)")
    known = [p for p in parts.values() if p["s"] is not None]
    wk = sum(p["w"] for p in known)
    wall = sum(p["w"] for p in parts.values())
    score = 100.0 * sum(p["w"] * p["s"] for p in known) / wk if wk > 0 else 0.0
    f = {k: v for k, v in f.items() if k != "origin"}            # 출처는 metrics['origin'] 한곳에
    return {"score": round(score, 1), "coverage": round(wk / wall, 3) if wall else 0.0, "parts": parts, "features": f,
            "slope_ref": ref, "slope_ref_n": nref, "hammer": hm}


def _score_lines(sc: dict) -> list[str]:
    out = [f"품질 점수 {sc['score']:.1f} (관측 비중 {sc['coverage']:.0%}) — 성공 확률 아님 · 모름 · 해당 없음 항목은 빼고 셈 [tl_weights]"]
    for k, p in sc["parts"].items():
        if p["na"]:
            mark = "—"
        elif p["s"] is None:
            mark = "?"
        else:
            mark = "✔" if p["s"] >= 1 else ("△" if p["s"] > 0 else "✘")
        out.append(f"{mark} {p['label']} (가중 {p['w']:.0f}): {p['note']} [{p['origin']}]")
    return out


# ---------------------------------------------------------------- 표시
def _line_desc(line: tq.TrendLine, b: tq.Bars, frozen: bool = False) -> str:
    ds = ", ".join(b.date(i) or str(i) for i in line.touches)
    mg = f" · 간격 중앙값 {line.median_gap:.0f}봉" if line.gaps else ""
    return (f"하향 추세선{'(돌파 때 동결)' if frozen else ''}: 앵커 {b.date(line.anchor_i)} 고가 {line.anchor_price:,.0f} · "
            f"접점 {len(line.touches)}개 ({ds}){mg} · 길이 {line.length}봉 · 기울기 {line.slope_pct:+.2%}/봉 (로그 눈금) "
            f"[{'tl_freeze' if frozen else 'tl_touch'}]")


def _line_ann(line: tq.TrendLine, b: tq.Bars, i_end: int, label: str, color: str = "#ff6d00") -> dict:
    """로그 직선을 5봉 간격 꺾은선으로 (선형 눈금 차트에서도 곡선 모양 그대로)."""
    idx = sorted({line.anchor_i, *line.touches, i_end, *range(line.anchor_i, i_end + 1, 5)})
    return segment([(b.dates[i], line.value(i)) for i in idx if 0 <= i <= i_end], label, color)


def _touch_marks(line: tq.TrendLine, b: tq.Bars) -> list[dict]:
    return [marker(b.dates[i], "앵커" if k == 0 else f"접점{k + 1}", "above", "#ff6d00", "circle")
            for k, i in enumerate(line.touches)]


def _tech_stage(phase: str, bp: float | None, close: float, cfg: TLBreakConfig) -> str:
    """기법 상태 → Tech 단계 (bp = 돌파가). ORIGIN['tl_stage_map']."""
    if phase == NEAR or phase == PENDING:
        return NEAR_PIVOT
    if phase in (FAIL, FAKE):
        return FAILED
    if phase == LOWVOL:
        return FORMING
    if _gt(close, bp * (1 + cfg.buy_range)):
        return EXTENDED
    if _le(close, bp):
        return NEAR_PIVOT                                    # 되돌림 — 종가가 선 위면 실패 아님
    return BREAKOUT


def _next_line(b: tq.Bars, cfg: TLBreakConfig, sw) -> tq.TrendLine | None:
    """다음 봉(E+1) 종가를 시험할 선 — 오늘(E)까지 자료로 맞춘다. tq.fit_downtrend_line 이 t = b.n(아직 없는 봉)을
    받는다(예전엔 마지막 봉을 복사한 자리표시 봉을 붙였다 — 선 맞춤은 [0..E] 만 써서 결과 같음)."""
    return tq.fit_downtrend_line(b, b.n, cfg, swings=sw)


def _break_info(brk: Break, b: tq.Bars, cfg: TLBreakConfig) -> dict:
    return {"t0": brk.t0, "date": b.date(brk.t0), "close": float(b.close[brk.t0]), "price": float(brk.price),
            "close_vs_line": float(b.close[brk.t0] / brk.price - 1), "vol_ratio": _r(brk.vr, 4), "vol": brk.vol,
            "vol_label": VOL_KO[brk.vol], "halts": list(brk.halts), "conf_date": b.date(brk.t_conf) if brk.t_conf is not None else None,
            "conf_how": brk.conf_how, "fail_date": b.date(brk.t_fail) if brk.t_fail is not None else None,
            "end_date": b.date(brk.t_end) if brk.t_end is not None else None, "phase": brk.phase(),
            "phase_label": brk.phase_label()}


def _conf_text(brk: Break, b: tq.Bars, cfg: TLBreakConfig) -> str:
    if brk.conf_how == "pct":
        lv = brk.line.value(brk.t_conf)
        return (f"안착 확인 {b.date(brk.t_conf)} — 종가 {b.close[brk.t_conf]:,.0f} ≥ 그날 선 {lv:,.0f} × {1 + cfg.conf_pct:.2f} "
                f"({b.close[brk.t_conf] / lv - 1:+.1%}) [tl_conf_pct]")
    return f"안착 확인 {b.date(brk.t_conf)} — 돌파일 포함 {cfg.conf_bars}종가 연속 선 위 [tl_conf_bars]"


def replay(sim: Sim, b: tq.Bars, E: int, cfg: TLBreakConfig) -> list[dict]:
    """체크리스트 4 — 이 종목의 지난 '돌파'(거래량 확인 · 안착 확인) → 안착 확인 종가 진입 · cfg.replay_bars 봉 뒤 종가.
    봉 E 까지 replay_bars 봉이 지난 신호만 (sim 은 완성 봉 E 까지 — 미래 봉 안 씀). 확인 뒤 실패한 돌파도 넣는다."""
    C, h = b.close, cfg.replay_bars
    return [{"date": b.date(x.t_conf), "break_date": b.date(x.t0), "ret20": float(C[x.t_conf + h] / C[x.t_conf] - 1)}
            for x in sim.breaks
            if x.vol == "ok" and x.t_conf is not None and x.t_conf + h <= E and C[x.t_conf] > 0]


def _checklist(res: PatternResult, ctx: StockContext, b: tq.Bars, E: int, entry: float | None, stop: float | None,
               sim: Sim, cfg: TLBreakConfig) -> None:
    rp = replay(sim, b, E, cfg)
    items = tq.run_checklist(b, E, tq.inputs_from_ctx(ctx, entry=entry, stop=stop, replay=rp))
    cnt = tq.checklist_counts(items)
    res.metrics["checklist"] = [it.to_dict() for it in items]
    res.metrics["checklist_counts"] = cnt
    res.metrics.update(replay=rp, replay_n=len(rp))
    res.reasons.append(f"체크리스트 10 (검증 전): 통과 {cnt[tq.PASS]} · 경고 {cnt[tq.WARN]} · 모름 {cnt[tq.UNKNOWN]} "
                       f"(4번 재현 {len(rp)}건) [tl_replay]")


def _recent_breaks(sim: Sim, b: tq.Bars, cfg: TLBreakConfig, k: int = 5) -> list[dict]:
    return [_break_info(x, b, cfg) for x in sim.breaks[-k:]]


def _provisional(res: PatternResult, ctx: StockContext, b: tq.Bars, E: int, cfg: TLBreakConfig, sim: Sim,
                 nl: tq.TrendLine | None) -> None:
    """장중(ctx.partial): 판정은 어제(E)까지 완성 봉. 오늘 미완성 봉은 잠정 확인 줄에만 — 거래량은 하루치 환산 추정(ctx.vol)."""
    px = float(ctx.df["close"].iloc[-1])
    vnow = float(ctx.vol.iloc[-1])
    n = cfg.vol_n
    base = float(np.mean(b.volume[E + 1 - n:E + 1])) if E + 1 >= n else float("nan")
    vr = vnow / base if base > 0 else None
    st = sim.states[E]
    pv: dict = {"date": f"{ctx.df.index[-1]:%Y-%m-%d}", "price": px, "vol_ratio_est": _r(vr, 4), "line": None, "event": None}
    note = "장중 스캔 — 판정은 어제까지 완성 봉, 오늘 봉은 잠정 확인에만 [tl_partial]"
    if st.phase in FROZEN and sim.brk is not None:
        lv = sim.brk.line.value(E + 1)
        pv["line"] = float(lv)
        if _le(px, lv):
            pv["event"] = "below_line"
            note = (f"장중 잠정: 현재가 {px:,.0f} ≤ 오늘 동결 선 {lv:,.0f} — 마감 종가도 선 아래면 "
                    f"{'실패' if sim.brk.t_conf is not None else '실패(가짜 돌파)'} (마감 뒤 다시 볼 것) [tl_partial]")
    elif nl is not None:
        lv = nl.value(E + 1)
        pv["line"] = float(lv)
        if _gt(px, lv):
            pv["event"] = "above_line"
            vtxt = f"거래량 하루치 환산 {vr:.2f}배" if vr is not None else "거래량 모름"
            note = (f"장중 잠정: 현재가 {px:,.0f} > 오늘 선 {lv:,.0f} ({px / lv - 1:+.1%}) · {vtxt} — 돌파 판정은 마감 봉으로 "
                    "(장중 고가만 넘으면 돌파 아님) [tl_partial]")
    res.metrics["provisional"] = pv
    res.warnings.append(note)


# ---------------------------------------------------------------- 탐지기
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, TLBreakConfig)
    res = PatternResult(name=NAME, label=LABEL)
    m = res.metrics
    m.update(rule_version=RULE_ID, rule_id=RULE_ID, core_version=tq.CORE_VERSION)
    df = tq.eod_frame(ctx)
    partial = len(df) < len(ctx.df)
    E = len(df) - 1
    if E < cfg.min_len:
        res.warnings.append(f"이력 부족 ({E + 1}봉 — 선 길이 최소 {cfg.min_len}봉) [tl_min_len]")
        m["origin"] = _used_origins(res, cfg)
        return res
    b, sim = simulate_ctx(ctx, cfg)                     # = simulate(Bars.from_df(df), cfg, df), 종목마다 한 번
    st = sim.states[E]
    m.update(asof=b.date(E), phase=st.phase, tl_stage=PHASE_KO.get(st.phase, "선 없음"))
    m["bulkowski"] = [tq.bulkowski_note("trendline_down"), tq.bulkowski_note("volume_breakout")]
    nl = _next_line(b, cfg, sim.swings)
    m["next_line"] = nl.to_dict(b.dates) if nl is not None else None
    close = float(b.close[E])

    if st.phase in (None, FAR):
        _not_detected(res, b, E, cfg, sim, nl)
    elif st.phase == NEAR:
        _near(res, ctx, b, E, cfg, sim, nl, close)
    else:
        _after_break(res, ctx, b, E, cfg, sim, close)
    if partial:
        _provisional(res, ctx, b, E, cfg, sim, nl)
    # 리포트 크기: 탐지 안 된 결과는 최근 돌파 1건 · 불코우스키 참고 없음, 출처는 이 결과가 쓴 규칙만
    m["recent_breaks"] = _recent_breaks(sim, b, cfg, 3 if res.detected else 1)
    if not res.detected:
        m.pop("bulkowski", None)
    m["origin"] = _used_origins(res, cfg)
    return res


_TAG = re.compile(r"\[([a-z0-9_]+)\]$")
_LINE_KEYS = ("technique", "tl_log", "tl_lookback", "tl_tol_cut", "tl_close_cut", "tl_touch", "tl_min_touches", "tl_min_gap",
              "tl_min_len", "swing")
_BREAK_KEYS = ("tl_break", "cross", "tl_break_vol", "baseline_excl_today", "tl_lowvol", "tl_freeze", "tl_conf_pct",
               "tl_conf_bars", "tl_fail", "tl_display", "tl_fail_display", "tl_buy_range", "tl_target")


def _used_origins(res: PatternResult, cfg: TLBreakConfig) -> dict[str, str]:
    """이 결과가 쓴 규칙의 출처만 — 근거 · 경고 줄 끝 [키] + 선 · 돌파 · 점수 · 단계 규칙."""
    m = res.metrics
    keys = {"technique"}
    for s in res.reasons + res.warnings:
        t = _TAG.search(s)
        if t:
            keys.add(t.group(1))
    if m.get("line") or m.get("next_line"):
        keys.update(_LINE_KEYS)
        keys.update({"highest": ("tl_anchor_highest",), "volume": ("tl_anchor_volume",)}.get(
            cfg.anchor_mode, ("tl_anchor_highest", "tl_anchor_volume")))
    if m.get("break"):
        keys.update(_BREAK_KEYS)
    for p in (m.get("score_parts") or {}).values():
        keys.add(p["origin"])
    if m.get("score_parts"):
        keys.update(("tl_weights", "tl_entry_trend"))
    if m.get("hammer"):
        keys.update(tq.HAMMER_ORIGIN)
    if res.detected:
        keys.update(("tl_stage_map", "tl_pivot", "tl_stop"))
    return {k: ORIGIN[k] for k in sorted(keys) if k in ORIGIN}


def _not_detected(res: PatternResult, b: tq.Bars, E: int, cfg: TLBreakConfig, sim: Sim, nl) -> None:
    m = res.metrics
    line = sim.line
    if line is not None:                                       # FAR
        lv = line.value(E)
        m.update(line=line.to_dict(b.dates), line_today=float(lv), close_vs_line=float(b.close[E] / lv - 1))
        res.reasons.append(_line_desc(line, b))
        res.warnings.append(f"유효한 하향 추세선은 있음 — 종가 {b.close[E]:,.0f} 가 오늘 선 {lv:,.0f} 아래 "
                            f"{1 - b.close[E] / lv:.1%} (돌파 임박은 선 아래 {cfg.near_pct:.0%} 안) [tl_near]")
        res.annotations = [_line_ann(line, b, E, "하향 추세선 (돌파 임박 밖)", "#9e9e9e")]
    else:
        cands = tq.downtrend_line_candidates(b, E, cfg, swings=sim.swings)
        if not cands:
            res.warnings.append(f"확정 소고점 없음 — 최근 {cfg.lookback}봉 안에 좌우 {cfg.pivot_k}봉 소고점이 확정되지 않음 [swing]")
        for c in cands:
            res.warnings.append(f"앵커 {b.date(c.anchor_i)} 고가 {c.anchor_price:,.0f} 선 무효 — " + " · ".join(c.reasons)
                                + " [technique]")
    if sim.breaks:
        x = sim.breaks[-1]
        res.warnings.append(f"최근 돌파 {b.date(x.t0)} — 지금 상태: {x.phase_label()}"
                            + (f" · 안착 확인 뒤 {cfg.display_bars}봉 표시 끝 {b.date(x.t_end)}" if x.t_end is not None else "")
                            + (f" · {b.date(x.t_fail)} 선 아래 종가" if x.t_fail is not None else ""))


def _near(res: PatternResult, ctx: StockContext, b: tq.Bars, E: int, cfg: TLBreakConfig, sim: Sim, nl, close: float) -> None:
    m = res.metrics
    line = sim.line
    lv = line.value(E)
    hf = tq.hammer_frame(b)
    sc = score_line(b, line, cfg, sim.slopes, hf, None, E)
    res.detected = True
    res.stage = NEAR_PIVOT
    res.score = float(sc["score"])
    res.start_date, res.end_date = b.date(line.anchor_i), b.date(E)
    res.stop = None
    nxt = nl.value(E + 1) if nl is not None else None
    res.pivot = float(nxt) if nxt is not None else None
    # 오늘 봉(새 소고점 확정 · 선 +0.5% 넘는 고가)으로 다음 봉 시험선이 바뀌었나 — 김정환: 옛 선과 새 선을 같이 그어 둔다
    same = nl is not None and nl.anchor_i == line.anchor_i and tuple(nl.touches) == tuple(line.touches) \
        and abs(nl.slope - line.slope) <= 1e-12
    m.update(line=line.to_dict(b.dates), line_today=float(lv), close_vs_line=float(close / lv - 1),
             line_next=_r(nxt, 4), line_changed=bool(nl is not None and not same), score_parts=sc["parts"],
             score_coverage=sc["coverage"], features=sc["features"], slope_ref=_r(sc["slope_ref"], 8),
             slope_ref_n=sc["slope_ref_n"], hammer=sc["hammer"], stage_origin="tl_stage_map")
    res.reasons.append(_line_desc(line, b))
    res.reasons.append(f"돌파 임박 — 종가 {close:,.0f} 가 오늘 선 {lv:,.0f} 아래 {1 - close / lv:.1%} "
                       f"(선 아래 {cfg.near_pct:.0%} 안) [tl_near]")
    if nl is not None:
        res.reasons.append(f"다음 봉 돌파 기준: 종가 > {nxt:,.0f} (다음 봉 선 값{'' if same else ' — 오늘 자료로 선이 바뀜'}) · "
                           f"거래량 ≥ 직전 {cfg.vol_n}봉 평균 × {cfg.vol_mult} [tl_pivot]")
    else:
        res.warnings.append("다음 봉에 시험할 유효한 선이 없음 — 오늘 봉으로 선이 무효가 됨(새 소고점 · 접점 부족 등) [tl_pivot]")
    res.reasons.append("손절은 돌파 뒤 정해짐 — 동결 선 아래 종가 = 실패 [tl_stop]")
    res.reasons += _score_lines(sc)
    unk = [p["label"] for p in sc["parts"].values() if p["s"] is None and not p["na"]]
    if unk:
        res.warnings.append("점수 모름 항목: " + " · ".join(unk) + " — 점수에서 빼고 셈")
    res.warnings.append(AUTO_LINE)
    if sc["hammer"]:
        m["bulkowski"].append(tq.bulkowski_note("hammer"))
    ann = [_line_ann(line, b, E, "하향 추세선")]
    if nl is not None and not same:
        ann.append(_line_ann(nl, b, E, "다음 봉 시험선", "#ffa726"))
    ann += _touch_marks(line, b)
    if res.pivot:
        ann.append(hline(res.pivot, "다음 봉 선 값 (돌파 기준)", "#2962ff"))
    if sc["hammer"]:
        ann.append(marker(sc["hammer"]["date"], "바닥 망치", "below", "#26a69a", "arrowUp"))
    res.annotations = ann
    _checklist(res, ctx, b, E, None, None, sim, cfg)


def _after_break(res: PatternResult, ctx: StockContext, b: tq.Bars, E: int, cfg: TLBreakConfig, sim: Sim,
                 close: float) -> None:
    m = res.metrics
    st = sim.states[E]
    brk = sim.brk
    line, t0, bp = brk.line, brk.t0, brk.price
    phase = st.phase
    lv_t, lv_n = line.value(E), line.value(E + 1)
    hf = tq.hammer_frame(b)
    sc = score_line(b, line, cfg, sim.slopes, hf, brk, E)      # 돌파일(t0) 자료로 잰 점수 — 동결
    stage = _tech_stage(phase, bp, close, cfg)
    confirmed = brk.t_conf is not None
    counted = brk.vol == "ok" and confirmed
    res.detected = phase != LOWVOL or cfg.show_lowvol_break
    res.stage = stage
    res.score = float(sc["score"])
    res.pivot = float(bp)
    res.stop = float(lv_n) if phase in FROZEN else None
    res.start_date, res.end_date = b.date(line.anchor_i), b.date(t0)
    res.breakout_date = b.date(t0) if counted else None
    targets = tq.line_targets(line, b, t0)
    m.update(line=line.to_dict(b.dates), line_today=float(lv_t), line_next=float(lv_n),
             close_vs_line=float(close / lv_t - 1), close_vs_pivot=float(close / bp - 1), tl_stage=brk.phase_label(),
             **{"break": _break_info(brk, b, cfg)}, targets=targets, score_parts=sc["parts"], score_coverage=sc["coverage"],
             features=sc["features"], slope_ref=_r(sc["slope_ref"], 8), slope_ref_n=sc["slope_ref_n"], hammer=sc["hammer"],
             stage_origin="tl_stage_map", score_frozen_at=b.date(t0))
    if phase in (FAIL, FAKE):
        m["fail_bars_ago"] = E - brk.t_fail

    R, W = res.reasons, res.warnings
    R.append(_line_desc(line, b, frozen=True))
    c0 = float(b.close[t0])
    R.append(f"{b.date(t0)} 돌파: 종가 {c0:,.0f} > 선 {bp:,.0f} ({c0 / bp - 1:+.1%}) — 처음으로 선 위 종가 [tl_break]")
    if brk.vol == "ok":
        R.append(f"돌파 거래량 {brk.vr:.2f}배 ≥ {cfg.vol_mult} (직전 {cfg.vol_n}봉 평균, 당일 제외) [tl_break_vol]")
    elif brk.vol == "low":
        W.append(f"돌파 거래량 {brk.vr:.2f}배 < {cfg.vol_mult} — 스펙상 돌파 거래량 필수라 '돌파'로 세지 않고 관찰 [tl_lowvol]")
    elif brk.vol == "unknown":
        W.append(f"돌파일 앞 {cfg.vol_n}봉 이력이 없어 돌파 거래량 모름 — '돌파'로 세지 않고 관찰 [tl_lowvol]")
    else:
        more = f" 등 {len(brk.halts)}일" if len(brk.halts) > 3 else ""
        W.append(f"돌파 거래량 {brk.vr:.2f}배 — 비교 구간(직전 {cfg.vol_n}봉)에 거래정지 {', '.join(brk.halts[:3])}{more}: "
                 "분할 · 병합이면 미수정 거래량이라 틀릴 수 있어 거래량 확인으로 세지 않음 [tl_halt_vol]")
    if confirmed:
        R.append(_conf_text(brk, b, cfg))
    elif phase in FROZEN:
        k = E - t0 + 1
        R.append(f"안착 확인 중 — 선 위 종가 {k}/{cfg.conf_bars} · 또는 그날 선 +{cfg.conf_pct:.0%} 종가면 확인 "
                 f"[tl_conf_bars]")
    if phase in (FAIL, FAKE):
        cf, lf = float(b.close[brk.t_fail]), brk.line.value(brk.t_fail)
        R.append(f"{b.date(brk.t_fail)} {PHASE_KO[phase]} — 종가 {cf:,.0f} ≤ 동결 선 {lf:,.0f} · 동결 풀고 다시 탐색 "
                 f"({E - brk.t_fail + 1}/{cfg.fail_display_bars}봉 표시) [tl_fail]")
    else:
        if phase == CONFIRMED:
            if stage == EXTENDED:
                R.append(f"이격 과다 — 종가 {close:,.0f} 가 돌파가 {bp:,.0f} 대비 {close / bp - 1:+.1%} "
                         f"(매수 범위 +{cfg.buy_range:.0%} 초과) [tl_buy_range]")
            elif stage == NEAR_PIVOT:
                R.append(f"되돌림 — 종가 {close:,.0f} 가 돌파가 {bp:,.0f} 아래지만 오늘 선 {lv_t:,.0f} 위 "
                         f"({close / lv_t - 1:+.1%}) · 실패 아님 [tl_fail]")
            else:
                R.append(f"매수 범위 — 종가 {close:,.0f} 가 돌파가 {bp:,.0f} 대비 {close / bp - 1:+.1%} "
                         f"(+{cfg.buy_range:.0%} 안) [tl_buy_range]")
            R.append(f"'돌파' 표시 {E - brk.t_conf + 1}/{cfg.display_bars}봉 [tl_display]")
        R.append(f"실패 기준(손절): 다음 봉 종가 ≤ 선 {lv_n:,.0f} · 오늘 선 {lv_t:,.0f} (종가 {close / lv_t - 1:+.1%}) [tl_stop]")
    R.append(f"목표(표시만 — 불코우스키 측정 규칙(미국)): T1 {targets['t1']:,.0f} (앵커 고가)"
             + (f" · T2 {targets['t2']:,.0f}" if targets.get("t2") is not None else "") + " [tl_target]")
    R.extend(_score_lines(sc))
    R.append(f"점수는 돌파일 {b.date(t0)} 자료로 잰 값(동결) [tl_freeze]")
    unk = [p["label"] for p in sc["parts"].values() if p["s"] is None and not p["na"]]
    if unk:
        W.append("점수 모름 항목: " + " · ".join(unk) + " — 점수에서 빼고 셈")
    if phase == LOWVOL and not cfg.show_lowvol_break:
        W.append("거래량 미달 돌파 관찰 끔(show_lowvol_break=False) — 탐지 안 함 [tl_lowvol]")
    W.append(AUTO_LINE)
    if brk.vr is not None:
        W.append(VOL_RAW)
    if sc["hammer"]:
        m["bulkowski"].append(tq.bulkowski_note("hammer"))

    # 차트 — 동결 선을 그대로 (다시 그리지 않음)
    ann = [_line_ann(line, b, E, "하향 추세선 (돌파 때 동결)")]
    ann += _touch_marks(line, b)
    ann.append(marker(b.dates[t0], "돌파" if brk.vol == "ok" else brk.phase_label().split(" · ")[0], "below", "#e91e63",
                      "arrowUp"))
    if confirmed:
        ann.append(marker(b.dates[brk.t_conf], "안착 확인", "below", "#ad1457", "circle"))
    if brk.t_fail is not None:
        ann.append(marker(b.dates[brk.t_fail], PHASE_KO[phase], "above", "#1e88e5", "arrowDown"))
    if sc["hammer"]:
        ann.append(marker(sc["hammer"]["date"], "바닥 망치", "below", "#26a69a", "arrowUp"))
    ann.append(hline(bp, "돌파가 (돌파일 선 값)", "#2962ff"))
    if res.stop:
        ann.append(hline(res.stop, "실패 기준 (다음 봉 선 값 · 종가)", "#1e88e5", "solid"))
    if phase in FROZEN:
        ann.append(hline(targets["t1"], "T1 앵커 고가 (불코우스키 측정 · 미국)", "#9e9e9e", "dotted"))
        if targets.get("t2") is not None:
            ann.append(hline(targets["t2"], "T2 (불코우스키 측정 · 미국)", "#bdbdbd", "dotted"))
    res.annotations = ann

    if phase in FROZEN:
        entry = float(b.close[brk.t_conf]) if confirmed else None
        _checklist(res, ctx, b, E, entry, res.stop, sim, cfg)
        m["exit_plan"] = tq.exit_plan(b, E, entry_i=brk.t_conf if confirmed else None)
