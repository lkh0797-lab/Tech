"""피보나치 눌림 반등 (fib_pullback) — 《차트의 기술》 영상 [19:00–24:00, 26:00–29:00, 50:00–52:00].

스펙 docs/2026-10-14-chart-techniques-design.md §2 · 부록 docs/2026-10-14-chart-techniques-addendum.md §3 (부록 수치 · 알고리즘 우선).
공용 부품 chart_screener/techniques.py (tq). 규칙 id 'fibpb_v1' → metrics['rule_version'] (일지 rule 칸).

상태 기계 (부록 §3.2 — 종목마다 봉 0 부터 순서대로, 봉 t 처리에 t 까지 자료만 → 앞부분 불변)
  NONE → CANDIDATE  장대양봉 b (tq.long_white_frame: 양봉 · 전일 대비 +7% · 몸통 ≥ 직전 15봉 평균 몸통 × 3 · 위아래 꼬리 < 몸통 ·
                    거래량 ≥ 직전 20봉 평균 × 2). 파동 저점 L 을 정해 고정 — 'since_swing_high'(기본): 확정된 가장 최근
                    fractal-2 고점 p (p+2 ≤ b, b−p ≤ 60) 뒤 최저 저가 · 그런 p 가 없으면 b−60..b 최저 ('min_lookback' = 스펙 원안).
  CANDIDATE         H = max(고가[b..t]), h = 처음 나온 봉(장대양봉 고가도 H 가 될 수 있다). 새 장대양봉은 흡수(H 갱신 · L 유지).
                    확정 'video'(기본): t > h 이고 음봉 또는 종가 하락 → CONFIRMED (장대양봉 당일은 고점 아님).
                    'fractal2': t = h+2 · 좌우 2봉 엄격. 확정 없이 t−b > 20 → EXPIRED. 저가 < L → INVALID.
  CONFIRMED (c)     라인 고정 lv(r) = H − r(H−L) · 매수 관심 구간 23.6 · 38.2 · 50 · 무효선 61.8. 봉마다 a→f:
                    a 고가 > H → CANDIDATE (H · h 갱신, 접촉 기록 지움)   b 종가 < lv(61.8) 또는 저가 < L → INVALID
                    c 접촉(깊은 라인부터 tq.fib_touch_level — 'wick' 기본)   d 신호(접촉 뒤 0~3봉 · 양봉 · 전일보다 높은 종가 ·
                    종가 ≥ 활성 라인 · 거래량이 5일 거래량 이평(오늘 포함)을 상향돌파) → SIGNAL, 진입 = 종가, 손절 = 다음 깊은 라인
                    e 라인 위 3% 안 = 눌림 진행   f t−c > 30 → EXPIRED
  SIGNAL 뒤         저가 < 손절 → 손절 (재현 체결 min(시가, 손절)) · 종가 > 진입 × 1.05 → 이격 · 무효 규칙은 표시만.
  설정이 끝난 봉(SIGNAL · INVALID · EXPIRED) 다음 봉부터 새 장대양봉으로 새 설정 — 한 종목에 진행 중 설정은 하나.

Tech 단계 대응 (구현 선택 — base.classify_stage 의 돌파 창 5봉과 같은 크기)
  신호 뒤 5봉 안   손절 닿음 = 돌파 실패 · 종가 > 진입 × 1.05 = 이격 과다 · 종가 < 진입 = 피벗 근접(재시험) · 그 밖 = 돌파
  CONFIRMED       접촉 뒤 3봉 안(반등 양봉 대기) · 라인 위 3% 안(눌림 진행) = 피벗 근접 · 그 밖 = 형성 중
  그 밖           탐지 안 함 — 고점 미확정 · 무효 · 만료 · 신호 뒤 5봉 지남 (이유는 경고로)
  pivot = 신호 종가(진입가, 신호 뒤에만). stop = 활성 라인의 다음 깊은 라인 (접촉 · 접근 단계는 예정 손절).

점수 0~100 (구현 선택 — 확률 아님): 기준봉 몸통 배수(3→12배) · 기준봉 거래량 배수(2→20배) · 라인 깊이 · 반등 거래량 배수
(1→3배) 각 25, 관문 통과 = 0.5 에서 시작해 강할수록 1 까지. 모르는 항목(접촉 전 라인 깊이 · 신호 전 반등 거래량)은 빼고
나눈다(관측 비중 표시). 단계는 점수에 넣지 않는다 — 종합 점수의 단계 가중치 W 가 맡는다.

화면 원칙 (부록 §3.0): 라인은 '관심 구간' — 확률을 쓰지 않는다. 불코우스키 수치는 tq.bulkowski_note 라벨로만.
장중(ctx.partial): 판정 · 단계 · 진입가는 마지막 완성 봉까지(일봉 EOD 만). 오늘 미완성 봉(거래량 하루치 환산 추정)으로 본
'장중 잠정' 상태는 경고 줄과 metrics.provisional · provisional_phase 에만 — 단계를 바꾸지 않는다.
단 저가 규칙은 예외(intraday_final): 저가는 마감까지 내려가기만 하므로 오늘 장중 저가가 신호 뒤 손절가 아래 · 신호 전 파동 저점
L 아래면 마감 뒤 판정도 그대로(손절 · 무효) — 그때는 단계를 '돌파 실패'로 두고 '장중 확정(저가)'를 적는다
(metrics.intraday_final). 종가 규칙(61.8% 아래 종가 · 진입가 아래 종가 등)은 마감 전엔 모르니 그대로 잠정.
신호 전 접촉 · 접근(피벗 없음)은 단계 값은 near_pivot 이지만 이름은 '라인 접촉 · 신호 전' 등(metrics.stage_label).
체크리스트 10 · 청산 계획(tq.run_checklist · tq.exit_plan)은 탐지된 결과에 metrics 로 붙인다. 이 종목 과거 신호(체크 4)는
이 기계의 지난 신호 — 신호 종가 진입 · 20봉 뒤 종가, 20봉이 지난 신호만.
"""
from __future__ import annotations

import bisect
import inspect
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import techniques as tq
from .base import (BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult, StockContext, classify_stage,
                   hline, marker, register, segment)

NAME = "fib_pullback"
LABEL = tq.PATTERN_LABELS[NAME]          # '피보나치 눌림 반등'
RULE_ID = tq.RULE_IDS[NAME]              # 'fibpb_v1'
_DEF = {k: p.default for k, p in inspect.signature(classify_stage).parameters.items()
        if p.default is not inspect.Parameter.empty}
WINDOW = _DEF["breakout_window"]         # 신호 뒤 Tech 단계로 보이는 봉 수 (5)

# 기계 상태
CANDIDATE, CONFIRMED, SIGNAL, INVALID, EXPIRED = "CANDIDATE", "CONFIRMED", "SIGNAL", "INVALID", "EXPIRED"
OPEN = (CANDIDATE, CONFIRMED)
# 화면 단계(phase) → (한글, Tech 단계 · None = 탐지 안 함)
PHASES = {
    "UNKNOWN": ("모름 (이력 부족)", None),
    "NONE": ("장대양봉 설정 없음", None),
    "CANDIDATE": ("장대양봉 뒤 고점 확정 대기", None),
    "WAIT": ("고점 확정 · 라인 접촉 대기", FORMING),
    "APPROACH": ("눌림 진행 (라인 접근)", NEAR_PIVOT),
    "TOUCH": ("관심 구간 접촉 · 반등 양봉 대기", NEAR_PIVOT),
    "SIGNAL": ("신호 — 반등 양봉 종가 진입", BREAKOUT),
    "HOLD": ("신호 뒤 · 진입가 ~ 이격 사이", BREAKOUT),
    "RETEST": ("신호 뒤 진입가 아래 (손절선 위)", NEAR_PIVOT),
    "EXTENDED": ("이격 (신호 종가에서 많이 오름)", EXTENDED),
    "STOPPED": ("손절 (다음 라인 아래 저가)", FAILED),
    "STALE": ("신호 뒤 표시 창 지남", None),
    "INVALID": ("무효", None),
    "EXPIRED": ("만료", None),
}
POST_PHASES = ("SIGNAL", "HOLD", "RETEST", "EXTENDED", "STOPPED")


def _pct(r: float) -> str:
    return f"{r * 100:g}%"


# ---------------------------------------------------------------- 설정 (부록 §3.1 상수)
@dataclass
class FibPullbackConfig:
    long_white: tq.LongWhiteConfig = field(default_factory=tq.LongWhiteConfig)   # LB_* (+7% · 몸통 3배/15 · 거래량 2배/20)
    swing_confirm: str = "video"          # FIB_SWING_CONFIRM 'video' | 'fractal2'
    h_max_bars: int = 20                  # FIB_H_MAX_BARS (구현 선택)
    l_mode: str = "since_swing_high"      # FIB_L_MODE | 'min_lookback' (스펙 원안)
    l_lookback: int = 60                  # FIB_L_LOOKBACK (구현 선택 — 스펙 값)
    levels_buy: tuple = tq.FIB_LEVELS_BUY  # FIB_LEVELS_BUY 23.6 · 38.2 · 50
    level_invalid: float = tq.FIB_LEVEL_INVALID   # 61.8 — 표시 + 무효선
    show_786: bool = False                # FIB_SHOW_786
    tol: float = tq.FIB_TOL               # FIB_TOL 1.5% (구현 선택 — 최적화 안 함)
    touch_mode: str = "wick"              # FIB_TOUCH_MODE 'wick' | 'band' (스펙 원안)
    signal_window: int = 3                # FIB_SIGNAL_WINDOW (접촉 봉 포함, 그 뒤 3봉까지)
    vol_test: str = "cross"               # FIB_VOL_TEST 'cross' | 'level' (스펙 원문)
    require_up_close: bool = True         # FIB_REQUIRE_UP_CLOSE (구현 선택)
    stop_alt_pct: float = 0.07            # FIB_STOP_ALT_PCT — 진입가 −7% 함께 표시
    approach_pct: float = tq.FIB_APPROACH_PCT   # FIB_APPROACH_PCT 3% (구현 선택)
    extended_pct: float = 0.05            # FIB_EXTENDED_PCT
    setup_expiry: int = 30                # FIB_SETUP_EXPIRY (구현 선택)
    report_window: int = WINDOW           # 신호 뒤 Tech 단계로 보이는 봉 수 (구현 선택 — classify_stage 돌파 창)
    replay_bars: int = 20                 # 체크 4 — 신호 뒤 20거래일 (구현 선택)
    # 점수 가중치 (구현 선택, 합 100 — 모르는 항목은 빼고 나눔)
    w_body: float = 25.0
    w_vol: float = 25.0
    w_depth: float = 25.0
    w_rebound: float = 25.0

    @property
    def ratios(self) -> tuple:
        return tuple(sorted(set(tq.FIB_RATIOS) | set(self.levels_buy) | {self.level_invalid}))


# ---------------------------------------------------------------- 출처 (영상 [mm:ss] · URL · 구현 선택)
_TILNOTE = "https://tilnote.io/pages/689b046edf13c4ef330e3e39"
_MSI = "https://tradingqna.com/t/why-you-should-pay-close-attention-to-the-5-buy-zone-after-a-breakout-updated/95357"
ORIGIN: dict[str, str] = {
    "long_white": tq.video("19:00–20:00") + " 대량 거래 장대양봉 → 고점이 기준 파동",
    "lw_white": tq.ORIGIN["white"],
    "lw_chg": tq.ORIGIN["lw_chg"],
    "lw_body": tq.ORIGIN["lw_body"],
    "lw_shadow": "위 · 아래 꼬리 각각 < 몸통 — Bulkowski Long White Day (https://thepatternsite.com/LongWhiteDay.html)",
    "lw_vol": tq.ORIGIN["lw_vol"],
    "baseline": tq.ORIGIN["baseline_excl_today"],
    "confirm_video": tq.video("19:00–20:00") + " 고점 확정 = 고점 봉 뒤 음봉 또는 종가 하락 봉 (장대양봉 당일은 고점 아님)",
    "confirm_fractal2": tq.ORIGIN["fractal2"],
    "h_max": tq.choice("고점 확정 없이 20봉 넘게 오르면 한 파동이 아니라 추세 — 설정 만료"),
    "l_since": f"파동 저점 = 직전 확정 fractal-2 고점 뒤 최저 — tilnote 영상 요약 '장대양봉 직전 저점' ({_TILNOTE})",
    "l_lookback": tq.choice("60봉 — 스펙 값 (그런 고점이 없을 때 · 'min_lookback')"),
    "fib_levels": tq.ORIGIN["fib_levels"],
    "fib_buy": tq.ORIGIN["fib_buy"],
    "fib_tol": tq.ORIGIN["fib_tol"],
    "touch_wick": tq.ORIGIN["fib_touch_wick"],
    "touch_band": tq.ORIGIN["fib_touch_band"],
    "approach": tq.ORIGIN["fib_approach"],
    "signal_window": ("접촉 뒤 3봉 안 반등 — ChartSchool 캔들 반전 1~3일 확인 "
                      "(https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/"
                      "candlestick-bullish-reversal-patterns)"),
    "vol_ma5": tq.ORIGIN["vol_ma5"],
    "vol_cross": tq.ORIGIN["vol_rev_cross"],
    "vol_level": tq.ORIGIN["vol_rev_level"],
    "up_close": tq.ORIGIN["vol_rev_upclose"],
    "entry_close": (tq.video("27:00, 51:00") + f" 종가 매수 · tilnote 신호 캔들 종가 ({_TILNOTE}) · 키움 시간외 종가 "
                    "(https://download.kiwoom.com/hero4_help_new/1337.htm)"),
    "stop": tq.ORIGIN["fib_stop"],
    "stop_alt": f"진입가 −7% 함께 표시 — O'Neil 7~8% 손절 (MarketSmith India {_MSI})",
    "invalid_618": tq.ORIGIN["fib_invalid"],
    "invalid_L": ("저가 < 파동 저점 L = 무효 — Elliott 2파는 1파를 100% 넘게 되돌리지 않음 (EWI 재게재 "
                  "https://www.marketcalls.in/trading-lessons/learn-how-to-apply-fibonacci-retracements-to-your-trading.html)"),
    "extended": f"신호 종가 +5% 넘으면 이격 — O'Neil/IBD 매수점 +5% (MarketSmith India {_MSI})",
    "expiry": tq.choice("고점 확정 뒤 30봉 안 신호 없으면 만료 — Bulkowski 용어집 되돌림(throwback) 30일과 같은 크기"),
    "stop_fill": tq.choice("재현 손절 체결가 min(시가, 손절가) — 갭 하락 반영"),
    "fib_786": ("78.6% 표시(기본 끔) — EWI 튜토리얼: 2파는 흔히 .618, 때로 .786 까지 (재게재 "
                "https://www.marketcalls.in/trading-lessons/learn-how-to-apply-fibonacci-retracements-to-your-trading.html)"),
    "new_setup": tq.choice("설정이 끝난 봉 다음 봉부터 새 장대양봉으로 새 설정 (부록 §3.2-5)"),
    "reset_checks": tq.choice("신고가로 CANDIDATE 에 돌아간 봉에도 만료(t−b > 20) · L 붕괴 검사"),
    "stage_map": tq.choice("Tech 단계 — 신호 뒤 5봉(base.classify_stage 돌파 창): 손절 = 돌파 실패 · 진입 +5% 넘음 = 이격 과다 · "
                           "진입가 아래 = 피벗 근접(재시험) · 그 밖 돌파 / 라인 접촉 뒤 3봉 · 라인 위 3% = 피벗 근접 / "
                           "고점 확정 뒤 대기 = 형성 중"),
    "line_depth": ("23.6 얕음 · 38.2~50 보통 — StockCharts mailbag 2009 "
                   "(https://stockcharts.com/articles/mailbag/2009/05/using-the-fibonacci-retracements-tool.html)"),
    "score": tq.choice("점수 = 기준봉 몸통(3→12배, 로그) · 기준봉 거래량(2→20배, 로그) · 라인 깊이(23.6=0.5, 38.2 · 50=1) · "
                       "반등 거래량(직전 4봉 평균의 1→3배) 각 25, 관문 통과 0.5 → 1, 모르는 항목 제외 — 확률 아님 · "
                       "상한은 캐시 장대양봉 분포 90분위에 맞춘 눈금(적중률로 고르지 않음)"),
    "replay": tq.choice("체크 4 — 이 기계의 지난 신호, 신호 종가 진입 · 20봉 뒤 종가, 20봉이 지난 신호만"),
    "evidence": ("라인은 관심 구간일 뿐 — ChartSchool: 다른 신호로 확인 "
                 "(https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/"
                 "fibonacci-retracements) · Tsinaslanidis 외 2022: 피보 구역 안 가격 행동이 다른 구역과 다르지 않음 "
                 "(https://doi.org/10.1016/j.eswa.2021.115893)"),
    "provisional": tq.choice("장중 잠정 — 오늘 미완성 봉(거래량 하루치 환산 추정)으로 본 상태는 경고 줄에만, "
                             "단계 · 진입가는 완성 봉(스펙: 일봉 EOD · 완성 봉만)"),
    "intraday_final": tq.choice("장중 확정(저가) — 저가 규칙(신호 뒤 손절 · 신호 전 L 붕괴)은 오늘 장중 저가로 이미 정해짐"
                                "(저가는 마감까지 내려가기만) → 단계 = 돌파 실패. 종가 규칙은 마감 뒤에"),
    "pre_stage_label": tq.choice("신호 전 접촉 · 접근은 피벗(진입가)이 아직 없어 '피벗 근접' 대신 '라인 접촉 · 신호 전' · "
                                 "'라인 접근 · 신호 전'으로 부른다 (단계 값은 점수용 near_pivot)"),
}
# 신호 전 near_pivot 단계의 이름 (피벗 없음) — (긴 이름, 꼬리표 줄임말)
PRE_STAGE_LABEL = {"TOUCH": ("라인 접촉 · 신호 전", "접촉"), "APPROACH": ("라인 접근 · 신호 전", "접근")}
EVIDENCE = ("피보 라인은 '관심 구간'일 뿐 확률이 아니다 — ChartSchool: 캔들 · 거래량 같은 다른 신호로 확인해야 함 · "
            "Tsinaslanidis 외(2022): 피보 구역 안 가격 행동이 다른 구역과 통계적으로 다르지 않았다")
RISK_SHALLOW = (f"{tq.BULKOWSKI_LABEL}: 손으로 고른 되돌림 중앙값 59% — 23.6 · 38.2% 라인 진입은 다음 라인 손절에 "
                "자주 걸릴 수 있음 (우위가 아니라 위험 표시)")          # 접히는 '참고' 줄(metrics['bulkowski'])에만 — 부록 §11
# 후보 옆(판정 근거 · 경고)에는 숫자 없는 주의만 — 미국 통계를 이 후보의 예측처럼 보이지 않게
SHALLOW_CAUTION = "얕은 라인(23.6 · 38.2%) 진입 — 되돌림이 더 깊어지면 다음 라인 손절에 걸릴 수 있음 (불코우스키 참고 줄 보기)"
VOL_RAW = ("거래량은 미수정 원 거래량(Tech 캐시) — 거래정지 없는 무상증자 · 분할이 최근 20봉 안에 있었다면 "
           "장대양봉 거래량 배수 · 5일 거래량 이평 비교가 틀릴 수 있음")


# ---------------------------------------------------------------- 비교 (tq 와 같은 부동소수 경계: 상대 1e-9)
def _tol(b: float) -> float:
    return tq.EPS * max(1.0, abs(b))


def _gt(a, b) -> bool:
    return bool(a > b + _tol(b))


def _lt(a, b) -> bool:
    return bool(a < b - _tol(b))


def _ge(a, b) -> bool:
    return bool(a >= b - _tol(b))


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------- 상태 기계
@dataclass
class Setup:
    b: int                         # 장대양봉(trigger)
    L: float                       # 파동 저점 (고정)
    l_i: int
    l_mode: str                    # 실제로 쓴 방식
    p: int | None                  # L 을 정한 fractal-2 고점
    H: float
    h: int
    state: str = CANDIDATE
    c: int | None = None           # 고점 확정 봉
    lv: dict | None = None         # {r: 가격}
    touch_bar: int | None = None
    touch_r: float | None = None
    active_r: float | None = None
    touches: list = field(default_factory=list)      # [(봉, r)]
    approach: tuple | None = None  # (봉, r) — 그 봉에 라인 위 3% 안
    reject: tuple | None = None    # (봉, 사유) — 접촉 창 안 반등 양봉이 거래량에서 탈락
    s: int | None = None           # 신호 봉
    entry: float | None = None
    stop: float | None = None
    stop_r: float | None = None
    vr: dict | None = None         # 신호 봉 거래량 판정 (tq.volume_reversal)
    end: int | None = None
    why: str = ""
    absorbed: list = field(default_factory=list)     # CANDIDATE 중 흡수한 장대양봉
    resets: int = 0                # CONFIRMED → 신고가 → CANDIDATE 횟수


class Machine:
    """순차 상태 기계 — step(t) 는 봉 t 까지 자료만 본다. 미리 계산하는 배열도 모두 '그 봉까지' 값(앞부분 불변)."""

    def __init__(self, b: tq.Bars, cfg: FibPullbackConfig):
        if cfg.swing_confirm not in ("video", "fractal2"):
            raise ValueError(f"swing_confirm: {cfg.swing_confirm!r}")
        if cfg.l_mode not in ("since_swing_high", "min_lookback"):
            raise ValueError(f"l_mode: {cfg.l_mode!r}")
        self.b, self.cfg = b, cfg
        self.ratios = cfg.ratios
        lw = tq.long_white_frame(b, cfg.long_white)
        self.lw_chg = lw["chg"].to_numpy(dtype=float)
        self.lw_body = lw["body"].to_numpy(dtype=float)
        self.lw_avg_body = lw["avg_body"].to_numpy(dtype=float)
        self.lw_vr = lw["vol_ratio"].to_numpy(dtype=float)
        # 기준선 0(직전 20봉 거래량 0 · 직전 15봉 몸통 0)이면 배수가 inf — 모름으로 보고 trigger 아님
        # (tq.long_white_frame 도 이제 모름으로 본다 — 아래 두 조건은 같은 결과의 이중 안전장치)
        with np.errstate(invalid="ignore"):
            self.lw_ok = lw["ok"].to_numpy(dtype=bool) & np.isfinite(self.lw_vr) & (self.lw_avg_body > 0)
        self.lw_known = lw["known"].to_numpy(dtype=bool)
        self.m5 = tq.vol_ma(b.volume, 5)
        self.fractals = tq.swing_highs(b.high, k=2, strict_left=True)   # fractal-2, confirm_i = p+2
        self._fr_conf = [s.confirm_i for s in self.fractals]
        self.cur: Setup | None = None
        self.sig: Setup | None = None          # 가장 최근 신호
        self.history: list[Setup] = []         # 끝난 설정 (신호 · 무효 · 만료)
        self.last_end = -1
        self.snaps: list[dict] = []

    # ---- 봉 하나
    def step(self, t: int) -> None:
        s = self.cur
        if s is None or s.state not in OPEN:
            if self.lw_ok[t] and t > self.last_end:
                self.cur = self._open(t)
            return
        if s.state == CANDIDATE:
            self._candidate(s, t)
        else:
            self._confirmed(s, t)

    def _open(self, t: int) -> Setup:
        L, l_i, mode, p = self._wave_low(t)
        return Setup(b=t, L=L, l_i=l_i, l_mode=mode, p=p, H=float(self.b.high[t]), h=t)

    def _wave_low(self, b: int) -> tuple[float, int, str, int | None]:
        cfg, low = self.cfg, self.b.low
        if cfg.l_mode == "since_swing_high":
            k = bisect.bisect_right(self._fr_conf, b)          # 확정(p+2 ≤ b)된 것 중 가장 최근
            if k:
                sw = self.fractals[k - 1]
                if b - sw.i <= cfg.l_lookback:
                    j = int(np.argmin(low[sw.i + 1:b + 1])) + sw.i + 1
                    return float(low[j]), j, "since_swing_high", sw.i
        i0 = max(0, b - cfg.l_lookback)
        j = int(np.argmin(low[i0:b + 1])) + i0
        return float(low[j]), j, "min_lookback", None

    def _confirm(self, s: Setup, t: int) -> bool:
        b = self.b
        if self.cfg.swing_confirm == "video":
            return t > s.h and (_lt(b.close[t], b.open[t]) or _lt(b.close[t], b.close[t - 1]))
        h = s.h
        return (t == h + 2 and h >= 2 and _lt(b.high[h + 1], s.H) and _lt(b.high[h + 2], s.H)
                and _gt(s.H, b.high[h - 1]) and _gt(s.H, b.high[h - 2]))

    def _candidate(self, s: Setup, t: int) -> None:
        b, cfg = self.b, self.cfg
        if t != s.b and self.lw_ok[t]:
            s.absorbed.append(t)                               # 흡수 — H 는 아래에서 갱신, L 유지
        if _gt(b.high[t], s.H):
            s.H, s.h = float(b.high[t]), t
        if self._confirm(s, t):
            s.state, s.c = CONFIRMED, t
            s.lv = tq.fib_levels(s.H, s.L, self.ratios)
            self._confirmed(s, t)
        elif t - s.b > cfg.h_max_bars:
            self._close(s, t, EXPIRED, f"고점 확정 없이 {cfg.h_max_bars}봉 넘게 오름 — 한 파동이 아니라 추세")
        elif _lt(b.low[t], s.L):
            self._close(s, t, INVALID, "고점 확정 전 저가 < 파동 저점 L")

    def _confirmed(self, s: Setup, t: int) -> None:
        b, cfg, lv = self.b, self.cfg, s.lv
        hi, lo, c = b.high[t], b.low[t], b.close[t]
        if _gt(hi, s.H):                                       # a 신고가 → CANDIDATE
            s.H, s.h, s.state, s.c, s.lv = float(hi), t, CANDIDATE, None, None
            s.touch_bar = s.touch_r = s.active_r = s.approach = s.reject = None
            s.touches = []
            s.resets += 1
            if t - s.b > cfg.h_max_bars:                       # 구현 선택: 돌아간 봉에도 CANDIDATE 검사
                self._close(s, t, EXPIRED, f"고점 확정 뒤 신고가 — 장대양봉 뒤 {cfg.h_max_bars}봉 넘음(추세)")
            elif _lt(lo, s.L):
                self._close(s, t, INVALID, "저가 < 파동 저점 L")
            return
        if _lt(c, lv[cfg.level_invalid]) or _lt(lo, s.L):     # b 무효
            why = (f"종가 < {_pct(cfg.level_invalid)} 무효선 {lv[cfg.level_invalid]:,.0f}"
                   if _lt(c, lv[cfg.level_invalid]) else f"저가 < 파동 저점 L {s.L:,.0f}")
            self._close(s, t, INVALID, why)
            return
        r = tq.fib_touch_level(lo, c, lv, cfg.tol, cfg.touch_mode, cfg.levels_buy)   # c 접촉 (깊은 라인부터)
        if r is not None:
            s.touch_bar, s.touch_r = t, r
            s.active_r = r if s.active_r is None else max(s.active_r, r)
            s.touches.append((t, r))
        if self._signal(s, t):                                 # d 신호
            return
        ap = [r for r in cfg.levels_buy if tq.fib_approach(c, lv[r], cfg.approach_pct)]   # e 라인 위 3% 안
        s.approach = (t, min(ap)) if ap else s.approach
        if t - s.c > cfg.setup_expiry:                         # f 만료
            self._close(s, t, EXPIRED, f"고점 확정 뒤 {cfg.setup_expiry}봉 안 신호 없음")

    def rebound(self, s: Setup, t: int) -> tuple[bool, dict | None, str | None]:
        """봉 t 가 신호 조건(부록 §3.2 3d)을 채우나 — 상태는 바꾸지 않는다(trendline_fib 가 '안착 확인 전 기록'에 쓴다).
        (통과, tq.volume_reversal 결과 | None, 거래량 탈락 사유 | None) — 사유는 반등 양봉이 거래량에서만 떨어졌을 때."""
        b, cfg = self.b, self.cfg
        if s.touch_bar is None or not 0 <= t - s.touch_bar <= cfg.signal_window:
            return False, None, None
        c = b.close[t]
        if not (_gt(c, b.open[t]) and _ge(c, s.lv[s.active_r])):
            return False, None, None
        if cfg.require_up_close and not (t >= 1 and _gt(c, b.close[t - 1])):
            return False, None, None
        vr = tq.volume_reversal(b, t, test=cfg.vol_test, require_up_close=cfg.require_up_close)
        if not vr["ok"]:
            return False, vr, ("거래량이 5일 거래량 이평을 상향돌파하지 않음" if cfg.vol_test == "cross"
                               else "거래량 ≤ 5일 거래량 이평")
        return True, vr, None

    def _signal(self, s: Setup, t: int) -> bool:
        ok, vr, why = self.rebound(s, t)
        if why is not None:
            s.reject = (t, why)
        if not ok:
            return False
        c = self.b.close[t]
        nr = tq.next_deeper(s.active_r, self.ratios)
        s.s, s.entry, s.stop_r = t, float(c), nr
        s.stop = float(s.lv[nr]) if nr is not None else float(s.L)
        s.vr = {k: vr[k] for k in ("volume", "vol_ma5", "vol_ma5_prev", "test")}
        self._close(s, t, SIGNAL, "반등 양봉 신호")
        self.sig = s
        return True

    def _close(self, s: Setup, t: int, state: str, why: str) -> None:
        s.state, s.end, s.why = state, t, why
        self.history.append(s)
        self.last_end = t


def run(b: tq.Bars, cfg: FibPullbackConfig | None = None, record: bool = False) -> Machine:
    """봉 0 부터 끝까지 기계를 돌린다. record=True 면 봉마다 judge 요약(snapshot)을 m.snaps 에 — 앞부분 불변 시험용."""
    m = Machine(b, cfg or FibPullbackConfig())
    n = b.n
    if record:
        for t in range(n):
            m.step(t)
            m.snaps.append(snapshot(judge(m, t)))
        return m
    starts = np.flatnonzero(m.lw_ok)
    t = 0
    while t < n:
        if m.cur is None or m.cur.state not in OPEN:          # 설정 없음 — 다음 장대양봉으로 건너뜀(결과 같음)
            k = int(np.searchsorted(starts, max(t, m.last_end + 1)))
            if k >= len(starts):
                break
            t = int(starts[k])
        m.step(t)
        t += 1
    return m


# ---------------------------------------------------------------- 봉 t 판정
def _post_signal(m: Machine, s: Setup, t: int) -> dict:
    """신호 뒤 (s, t] — 손절 · 이격 · 무효 규칙(표시만). 봉 t 까지만."""
    b, cfg = m.b, m.cfg
    out = {"stop_hit": None, "stop_fill": None, "ext_i": None, "broke_i": None}
    if t <= s.s:
        return out
    k = np.arange(s.s + 1, t + 1)
    hit = k[b.low[k] < s.stop - _tol(s.stop)]
    if len(hit):
        j = int(hit[0])
        out["stop_hit"], out["stop_fill"] = j, float(min(b.open[j], s.stop))
    lim = s.entry * (1 + cfg.extended_pct)
    ext = k[b.close[k] > lim + _tol(lim)]
    if len(ext):
        out["ext_i"] = int(ext[0])
    inv = s.lv[cfg.level_invalid]
    brk = k[(b.close[k] < inv - _tol(inv)) | (b.low[k] < s.L - _tol(s.L))]
    if len(brk):
        out["broke_i"] = int(brk[0])
    return out


def judge(m: Machine, t: int) -> dict:
    """기계가 봉 t 까지 처리한 상태에서 봉 t 의 단계. {'t', 'phase', 'setup', 'post', 'other'}."""
    cfg, C = m.cfg, m.b.close
    sg = m.sig if m.sig is not None and m.sig.s <= t else None
    if sg is not None and t - sg.s < cfg.report_window:
        post = _post_signal(m, sg, t)
        if post["stop_hit"] is not None:
            phase = "STOPPED"
        elif _gt(C[t], sg.entry * (1 + cfg.extended_pct)):
            phase = "EXTENDED"
        elif _lt(C[t], sg.entry):
            phase = "RETEST"
        else:
            phase = "SIGNAL" if t == sg.s else "HOLD"
        other = m.cur if m.cur is not None and m.cur is not sg and m.cur.state in OPEN else None
        return {"t": t, "phase": phase, "setup": sg, "post": post, "other": other}
    s = m.cur
    if s is not None and s.state == CONFIRMED:
        if s.touch_bar is not None and t - s.touch_bar <= cfg.signal_window:
            phase = "TOUCH"
        elif s.approach is not None and s.approach[0] == t:
            phase = "APPROACH"
        else:
            phase = "WAIT"
        return {"t": t, "phase": phase, "setup": s, "post": None, "other": None}
    if s is None:
        phase = "NONE"
    elif s.state == CANDIDATE:
        phase = "CANDIDATE"
    elif s.state == SIGNAL:
        phase = "STALE"
    else:
        phase = s.state
    return {"t": t, "phase": phase, "setup": s, "post": None, "other": None}


def snapshot(j: dict) -> dict:
    """판정 요약(원시 값만) — 같은 봉의 판정 비교용."""
    s, post = j["setup"], j["post"] or {}
    d = {"t": j["t"], "phase": j["phase"], "stage": PHASES[j["phase"]][1]}
    if s is not None:
        d.update(b=s.b, L=s.L, l_i=s.l_i, H=s.H, h=s.h, c=s.c, state=s.state, active_r=s.active_r,
                 touch_bar=s.touch_bar, approach=s.approach, s=s.s, entry=s.entry, stop=s.stop, end=s.end)
    d.update({k: post.get(k) for k in ("stop_hit", "stop_fill", "ext_i", "broke_i")})
    return d


def evaluate(b: tq.Bars, t: int | None = None, cfg: FibPullbackConfig | None = None) -> dict:
    """봉 t 판정 요약 — b 를 t 까지 잘라 돌린다(미래 봉을 볼 수 없다)."""
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    m = run(b.cut(t), cfg)
    return snapshot(judge(m, t))


# ---------------------------------------------------------------- 점수
def _lin(x: float | None, lo: float, hi: float) -> float | None:
    """관문 lo = 0.5 → hi 이상 = 1 (직선)."""
    if x is None:
        return None
    return 0.5 + 0.5 * min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _log(x: float | None, lo: float, hi: float) -> float | None:
    """관문 lo = 0.5 → hi 이상 = 1 (로그 — 배수는 꼬리가 길다)."""
    if x is None or x <= 0:
        return None
    return 0.5 + 0.5 * min(1.0, max(0.0, math.log(x / lo) / math.log(hi / lo)))


def score_parts(cfg: FibPullbackConfig, body_x: float | None, vol_x: float | None, depth_r: float | None,
                rebound_x: float | None) -> tuple[float, float, dict]:
    """(점수 0~100, 관측 비중, 항목). 구현 선택 — 확률 아님.

    몸통 3배 → 12배 · 거래량 2배 → 20배 (로그, 상한 ≈ 캐시 860종목 2023-08~2026-10 장대양봉 분포 90분위 — 눈금 맞춤일 뿐
    적중률로 고른 값 아님) · 라인 깊이 23.6 = 0.5, 38.2 · 50 = 1 · 반등 거래량 직전 4봉 평균의 1 → 3배(직선, 90분위 2.8)."""
    k, vm = cfg.long_white.body_rel_k, cfg.long_white.vol_mult
    depth = None if depth_r is None else (0.5 if depth_r < 0.3 else 1.0)
    parts = {
        "body": {"name": "기준봉 몸통 배수", "w": cfg.w_body, "x": body_x, "s": _log(body_x, k, 4 * k)},
        "vol": {"name": "기준봉 거래량 배수", "w": cfg.w_vol, "x": vol_x, "s": _log(vol_x, vm, 10 * vm)},
        "depth": {"name": "라인 깊이", "w": cfg.w_depth, "x": depth_r, "s": depth},
        "rebound": {"name": "반등 거래량 배수(직전 4봉 평균)", "w": cfg.w_rebound, "x": rebound_x,
                    "s": _lin(rebound_x, 1.0, 3.0)},
    }
    known = [p for p in parts.values() if p["s"] is not None and p["w"] > 0]
    tot = sum(p["w"] for p in parts.values() if p["w"] > 0)
    wk = sum(p["w"] for p in known)
    if not known or tot <= 0:
        return 0.0, 0.0, parts
    return float(100 * sum(p["w"] * p["s"] for p in known) / wk), float(wk / tot), parts


# ---------------------------------------------------------------- 결과
def _won(x) -> str:
    return f"{x:,.0f}" if x is not None and x == x else "—"


def _bars_with_partial(ctx: StockContext) -> tq.Bars:
    """오늘 미완성 봉 포함 — 마지막 봉 거래량은 ctx.vol(하루치 환산 추정)."""
    bp = tq.Bars.from_df(ctx.df)
    v = bp.volume.copy()
    v[-1] = float(ctx.vol.iloc[-1])
    return bp._replace(volume=v)


def _replay(m: Machine, T: int, cfg: FibPullbackConfig) -> list[dict]:
    C = m.b.close
    out = []
    for s in m.history:
        if s.state == SIGNAL and s.s + cfg.replay_bars <= T:
            out.append({"date": m.b.date(s.s), "ret20": float(C[s.s + cfg.replay_bars] / s.entry - 1)})
    return out


def intraday_final(ctx: StockContext, j: dict, pre_phases: tuple = ("WAIT", "APPROACH", "TOUCH")) -> dict | None:
    """장중 스캔 — 오늘 미완성 봉 저가로 이미 정해진 일 (저가는 마감까지 내려가기만 한다 → 마감 뒤 판정도 같다):
    신호 뒤(표시 창 안) 저가 < 손절 = 손절, 신호 전(고점 확정 뒤) 저가 < 파동 저점 L = 설정 끝(무효). 없으면 None.
    j = 완성 봉 판정(judge). trendline_fib 도 같은 규칙(손절 · L 은 피보 기계 그대로)이라 이 함수를 쓴다."""
    s, ph = j.get("setup"), j.get("phase")
    df = getattr(ctx, "df", None)
    if s is None or df is None or not len(df) or not getattr(ctx, "partial", False):
        return None
    lo = _f(df["low"].iloc[-1])
    if lo is None:
        return None
    day = f"{df.index[-1]:%Y-%m-%d}"
    if ph in POST_PHASES and ph != "STOPPED" and s.stop is not None and _lt(lo, s.stop):
        op = _f(df["open"].iloc[-1])
        return {"kind": "stop", "date": day, "low": lo, "level": float(s.stop),
                "fill": float(min(op, s.stop)) if op is not None else float(s.stop),
                "text": f"장중 확정(저가): 오늘({day}) 저가 {_won(lo)} < 손절 {_won(s.stop)} — 손절"}
    if ph in pre_phases and _lt(lo, s.L):
        return {"kind": "invalid_L", "date": day, "low": lo, "level": float(s.L),
                "text": f"장중 확정(저가): 오늘({day}) 저가 {_won(lo)} < 파동 저점 L {_won(s.L)} — 설정 무효"}
    return None


def apply_intraday_final(res: PatternResult, fin: dict | None) -> None:
    """intraday_final 결과를 단계에 — 돌파 실패 · 이름 '손절/무효 · 장중 확정(저가)' · 경고 줄."""
    if not fin:
        return
    res.stage = FAILED
    what = "손절" if fin["kind"] == "stop" else "무효"
    res.metrics.update(intraday_final=fin, stage_label=f"{what} · 장중 확정(저가)", stage_short=f"{what}(장중 확정)")
    res.warnings.insert(0, fin["text"] + " — 저가는 마감까지 내려가기만 해 마감 뒤 판정도 같다 · 단계 = 돌파 실패 "
                        "(종가 규칙은 마감 뒤에)")


def _why_not(m: Machine, j: dict, cfg: FibPullbackConfig) -> list[str]:
    s, ph, d = j["setup"], j["phase"], m.b.date
    lw = cfg.long_white
    base = (f"장대양봉(양봉 · 전일 대비 +{lw.min_chg:.0%} · 몸통 ≥ 직전 {lw.body_rel_n}봉 평균 × {lw.body_rel_k:g} · "
            f"꼬리 < 몸통 · 거래량 ≥ 직전 {lw.vol_n}봉 평균 × {lw.vol_mult:g})")
    if ph == "NONE":
        return [f"{base} 설정 없음"]
    if ph == "CANDIDATE":
        how = ("고점 봉 다음에 음봉 또는 종가 하락 봉이 나와야 확정 " + tq.video("19:00–20:00")
               if cfg.swing_confirm == "video" else "좌우 2봉(fractal)으로 확정")
        return [f"장대양봉 {d(s.b)} 뒤 고점 {_won(s.H)} ({d(s.h)}) 미확정 — {how}. 라인은 확정 뒤에 고정"]
    if ph == "STALE":
        return [f"신호 {d(s.s)} (진입 {_won(s.entry)}) 뒤 {j['t'] - s.s}봉 — 표시 창 {cfg.report_window}봉 지남"]
    if ph in ("INVALID", "EXPIRED"):
        return [f"마지막 설정(장대양봉 {d(s.b)}) {PHASES[ph][0]}: {s.why} ({d(s.end)}) — 다음 장대양봉 대기"]
    return []


def _touch_text(m: Machine, s: Setup, cfg: FibPullbackConfig) -> str:
    t, r = s.touches[-1]
    mode = "아래꼬리 허용 'wick'" if cfg.touch_mode == "wick" else "밴드 'band'"
    return (f"{m.b.date(t)} 저가 {_won(m.b.low[t])} 가 {_pct(r)} 라인 {_won(s.lv[r])} 에 닿고 종가 {_won(m.b.close[t])} 가 "
            f"라인 위 ({mode}, 허용 {cfg.tol:.1%})")


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, FibPullbackConfig)
    res = PatternResult(name=NAME, label=LABEL)
    mt = res.metrics
    mt.update(rule_version=RULE_ID, core_version=tq.CORE_VERSION)
    df = ctx.df
    partial = bool(getattr(ctx, "partial", False)) and len(df) > 0
    eod = tq.eod_frame(ctx)
    T = len(eod) - 1
    need = max(cfg.long_white.vol_n, cfg.long_white.body_rel_n)         # 장대양봉 기준선이 생기는 첫 봉
    if T < need:
        res.warnings.append(f"이력 부족 ({T + 1}봉) — 장대양봉 기준선(직전 {cfg.long_white.vol_n}봉 거래량 · "
                            f"{cfg.long_white.body_rel_n}봉 몸통)이 없어 판정 모름")
        mt.update(phase="UNKNOWN", phase_label=PHASES["UNKNOWN"][0])
        return res
    b = tq.Bars.from_df(eod)
    m = run(b, cfg)
    j = judge(m, T)
    prov = None                                       # 장중 잠정 결과는 단계 · 진입가에 쓰지 않는다(완성 봉만) — 경고 줄 · 수치만
    prov_sig = False
    if partial:
        mp = run(_bars_with_partial(ctx), cfg)        # 순차 기계 — 봉 T 까지 상태는 위와 같다
        jp = judge(mp, T + 1)
        mt["provisional_phase"] = jp["phase"]
        if jp["phase"] != j["phase"]:
            prov_sig = jp["phase"] == "SIGNAL"
            what = "신호" if prov_sig else PHASES[jp["phase"]][0]
            res.warnings.append(f"장중 잠정: 오늘 미완성 봉(거래량 하루치 환산 추정)까지 보면 '{what}' — 판정 · 단계 · 진입가는 "
                                "어제까지 완성 봉, 마감 뒤 다시 볼 것")
    ph = j["phase"]
    label, stage = PHASES[ph]
    if ph == "EXTENDED":
        label = f"이격 (신호 종가 +{cfg.extended_pct:.0%} 넘음)"
    mt.update(phase=ph, phase_label=label, provisional=prov_sig)
    s = j["setup"]
    if stage is None:
        res.warnings += _why_not(m, j, cfg)
        if s is not None and s.state == CANDIDATE:
            mt.update(trigger_date=m.b.date(s.b), wave_low=s.L, wave_high=s.H)
        if partial:
            res.warnings.append("장중 스캔 — 판정은 어제까지 완성 봉")
        res.metrics["origin"] = ORIGIN
        return res

    tt = j["t"]                                       # 판정 봉 (장중 잠정이면 오늘)
    bb, d = m.b, m.b.date
    lv, post = s.lv, j["post"] or {}
    res.detected, res.stage = True, stage
    signaled = ph in POST_PHASES
    if ph in PRE_STAGE_LABEL and stage == NEAR_PIVOT:
        mt["stage_label"], mt["stage_short"] = PRE_STAGE_LABEL[ph]
    # 손절 · 진입
    if signaled:
        entry, stop, stop_r = s.entry, s.stop, s.stop_r
        res.pivot, res.stop, res.breakout_date = entry, stop, d(s.s)
    else:
        r0 = s.active_r if ph == "TOUCH" else (s.approach[1] if ph == "APPROACH" else None)
        entry = None
        stop_r = tq.next_deeper(r0, m.ratios) if r0 is not None else None
        stop = float(lv[stop_r]) if stop_r is not None else None
        res.stop = stop
    res.start_date = d(s.l_i)
    res.end_date = d(s.s) if signaled else d(tt)
    depth_r = s.active_r if (signaled or ph == "TOUCH") else (s.approach[1] if ph == "APPROACH" else None)
    # 점수
    body_x = _f(m.lw_body[s.b] / m.lw_avg_body[s.b]) if m.lw_avg_body[s.b] > 0 else None
    vol_x = _f(m.lw_vr[s.b])
    reb_x = None
    if signaled and s.s >= 4:
        base4 = float(np.mean(bb.volume[s.s - 4:s.s]))
        reb_x = _f(bb.volume[s.s] / base4) if base4 > 0 else None
    res.score, cov, parts = score_parts(cfg, body_x, vol_x, depth_r, reb_x)
    # 수치
    close_t = float(bb.close[tt])
    mt.update(
        state=s.state, trigger_date=d(s.b), trigger_chg=_f(m.lw_chg[s.b]), trigger_body_x=body_x, trigger_vol_x=vol_x,
        absorbed=[d(i) for i in s.absorbed], wave_low=s.L, wave_low_date=d(s.l_i), l_mode=s.l_mode,
        l_swing_high_date=d(s.p) if s.p is not None else None, wave_high=s.H, wave_high_date=d(s.h),
        confirm_date=d(s.c), confirm_mode=cfg.swing_confirm, resets=s.resets,
        **{f"fib_{r * 1000:.0f}": float(v) for r, v in sorted(lv.items())},
        retracement=_f(tq.retracement(s.H, s.L, close_t)), touch_mode=cfg.touch_mode,
        active_level=s.active_r, touch_date=d(s.touch_bar) if s.touch_bar is not None else None,
        touches=[f"{d(i)} {_pct(r)}" for i, r in s.touches], approach_level=s.approach[1] if ph == "APPROACH" else None,
        entry=entry, stop_level=stop_r, stop_pct=(1 - stop / entry) if (entry and stop) else None,
        stop_alt=entry * (1 - cfg.stop_alt_pct) if entry else None,
        score_coverage=cov, score_parts={k: {kk: (_f(vv) if kk in ("x", "s", "w") else vv) for kk, vv in p.items()}
                                         for k, p in parts.items()},
    )
    if cfg.show_786:
        mt["fib_786"] = float(s.H - 0.786 * (s.H - s.L))
    if ph in ("WAIT", "APPROACH", "TOUCH"):
        mt["expires_in"] = int(cfg.setup_expiry - (tt - s.c))
        mt["expires_basis"] = d(tt)                   # 남은 봉을 센 완성 봉 (장중이면 오늘 진행 중인 봉이 그 첫 봉)
    if signaled:
        mt.update(signal_date=d(s.s), bars_since_signal=int(tt - s.s), signal_volume=_f(s.vr["volume"]),
                  signal_vol_ma5=_f(s.vr["vol_ma5"]), signal_vol_x=reb_x, vol_test=s.vr["test"],
                  stop_hit_date=d(post["stop_hit"]) if post.get("stop_hit") is not None else None,
                  stop_fill=post.get("stop_fill"),
                  extended_date=d(post["ext_i"]) if post.get("ext_i") is not None else None,
                  invalid_after_signal_date=d(post["broke_i"]) if post.get("broke_i") is not None else None)

    # 근거
    lwc = cfg.long_white
    R = res.reasons
    R.append(f"규칙 {RULE_ID} — 장대양봉 → 고점 확정 → 피보 23.6 · 38.2 · 50% 관심 구간 접촉 → 거래량 실린 반등 양봉 종가 "
             + tq.video("19:00–24:00, 26:00–29:00, 50:00–52:00"))
    R.append(f"장대양봉 {d(s.b)}: 전일 대비 {m.lw_chg[s.b]:+.1%} · 몸통 {body_x or 0:.1f}배(직전 {lwc.body_rel_n}봉 평균) · "
             f"거래량 {vol_x or 0:.1f}배(직전 {lwc.vol_n}봉 평균, 당일 제외) · 꼬리 < 몸통"
             + (f" · 흡수한 장대양봉 {len(s.absorbed)}개" if s.absorbed else ""))
    lm = (f"직전 확정 고점 {d(s.p)} 뒤 최저" if s.l_mode == "since_swing_high"
          else f"직전 {cfg.l_lookback}봉 최저" + (" (확정 고점 없음)" if cfg.l_mode == "since_swing_high" else ""))
    cm = "음봉 · 종가 하락 봉" if cfg.swing_confirm == "video" else "좌우 2봉"
    R.append(f"기준 파동 L {_won(s.L)} ({d(s.l_i)}, {lm}) → H {_won(s.H)} ({d(s.h)}) · 고점 확정 {d(s.c)} ({cm})")
    R.append("관심 구간 " + " · ".join(f"{_pct(r)} {_won(lv[r])}" for r in cfg.levels_buy)
             + f" · 무효선 {_pct(cfg.level_invalid)} {_won(lv[cfg.level_invalid])} (확률 아님)")
    if s.touches:
        R.append("접촉: " + _touch_text(m, s, cfg))
    if ph == "APPROACH":
        R.append(f"눌림 진행: 종가 {_won(close_t)} 가 {_pct(s.approach[1])} 라인 {_won(lv[s.approach[1]])} 위 "
                 f"{cfg.approach_pct:.0%} 안")
    if ph == "TOUCH":
        left = cfg.signal_window - (tt - s.touch_bar)
        when = f"{d(tt)} 완성 봉 기준 남은 봉 {left} (오늘 진행 중인 봉 포함)" if partial else f"남은 봉 {left}"
        R.append(f"반등 양봉 대기 — {when} (양봉 · 전일보다 높은 종가 · 거래량이 5일 거래량 이평 상향돌파면 종가 신호)")
    if signaled:
        R.append(f"신호 {d(s.s)}: 양봉 · 전일보다 높은 종가 · 거래량 {_won(s.vr['volume'])} > 5일 거래량 이평 "
                 f"{_won(s.vr['vol_ma5'])} (오늘 포함, {'상향돌파' if s.vr['test'] == 'cross' else '수준 비교'}) — "
                 f"종가 {_won(entry)} 진입 " + tq.video("27:00, 51:00"))
    if stop is not None:
        rel = f" (진입가 대비 −{1 - stop / entry:.1%})" if entry else ""
        nm = f"다음 라인 {_pct(stop_r)}" if stop_r is not None else "파동 저점 L (더 깊은 라인 없음)"
        R.append(f"손절 {_won(stop)} = {nm}{rel} · 함께 보기: 파동 저점 {_won(s.L)}"
                 + (f" · 진입가 −{cfg.stop_alt_pct:.0%} {_won(entry * (1 - cfg.stop_alt_pct))}" if entry else "")
                 + ("" if signaled else " (예정 — 신호 전)"))
    R.append(f"품질 점수 {res.score:.0f} (관측 비중 {cov:.0%}) — 확률 아님 · 구현 선택 가중치")
    # 경고
    W = res.warnings
    if ph == "STOPPED":
        W.append(f"손절: {d(post['stop_hit'])} 저가가 손절 {_won(stop)} 아래 (재현 체결 {_won(post['stop_fill'])})")
    if ph == "RETEST":
        W.append(f"종가 {_won(close_t)} 가 진입가 {_won(entry)} 아래 — 손절 {_won(stop)} 위에서 재시험")
    if ph == "EXTENDED":
        W.append(f"이격: 종가 {_won(close_t)} > 진입가 × {1 + cfg.extended_pct:g} — 추격 구간")
    if post.get("broke_i") is not None:
        W.append(f"무효 규칙(61.8% 아래 종가 · L 붕괴) {d(post['broke_i'])} — 표시만")
    if not signaled:
        lo_t, inv = float(bb.low[tt]), lv[cfg.level_invalid]
        bar = f"마지막 완성 봉({d(tt)}) 저가" if partial else "오늘 저가"
        if _lt(lo_t, inv):
            W.append(f"{bar} {_won(lo_t)} 가 {_pct(cfg.level_invalid)} 무효선 {_won(inv)} 아래 — 종가가 선 위라 무효는 "
                     "아님(종가 기준)")
        elif stop is not None and _lt(lo_t, stop):
            W.append(f"{bar} {_won(lo_t)} 가 예정 손절 {_won(stop)} 아래 — 장중 이탈(신호 전이라 손절 판정은 안 함)")
    if ph == "TOUCH" and s.reject is not None and s.reject[0] >= s.touch_bar:
        W.append(f"{d(s.reject[0])} 반등 양봉이었지만 {s.reject[1]}")
    shallow = depth_r is not None and depth_r < 0.45
    if shallow:
        W.append(SHALLOW_CAUTION)
    if j.get("other") is not None:
        o = j["other"]
        W.append(f"같은 종목의 새 설정(장대양봉 {d(o.b)}, {o.state}) — 신호 표시 창 동안 대표는 지난 신호")
    halts = tq.window_halts(df, s.b - lwc.vol_n, s.b)
    if halts:
        W.append(f"장대양봉 거래량 기준 구간(직전 {lwc.vol_n}봉)에 거래정지 {', '.join(halts)} — 분할 · 병합이면 배수가 틀림")
    if signaled:
        h2 = tq.window_halts(df, s.s - 5, s.s)
        if h2:
            W.append(f"신호 거래량 5일 이평 구간에 거래정지 {', '.join(h2)} — 비교가 틀릴 수 있음")
    W.append(EVIDENCE)
    W.append(VOL_RAW)
    if prov is not None:
        W.append("장중 잠정 신호 — 오늘 봉 미완성(거래량은 하루치 환산 추정). 종가가 확정된 뒤 다시 볼 것 · 진입가는 지금 값")
    elif partial:
        W.append("장중 스캔 — 판정은 어제까지 완성 봉")

    # 체크리스트 · 청산 · 재현 — 완성 봉(b, T)으로만
    rep = _replay(m, T, cfg)                          # 20봉이 지난 신호만 — 장중 봉은 쓰지 않는다
    ck = tq.run_checklist(b, T, tq.inputs_from_ctx(ctx, entry=entry, stop=stop, replay=rep))
    cnt = tq.checklist_counts(ck)
    mt.update(checklist=[c.to_dict() for c in ck], checklist_counts=cnt, replay_n=len(rep), replay=rep)
    R.append(f"체크리스트 10 (검증 전): 통과 {cnt[tq.PASS]} · 경고 {cnt[tq.WARN]} · 모름 {cnt[tq.UNKNOWN]}")
    if signaled and prov is None:
        mt["exit_plan"] = tq.exit_plan(b, T, entry_i=s.s)
    mt["bulkowski"] = [tq.bulkowski_note("fib"), tq.bulkowski_note("long_white_day")] + ([RISK_SHALLOW] if shallow else [])
    mt["history"] = [{"trigger": d(x.b), "state": x.state, "end": d(x.end), "why": x.why,
                      "signal": d(x.s) if x.s is not None else None} for x in m.history[-5:]]
    mt["origin"] = ORIGIN
    res.annotations = _annotations(m, s, j, cfg, stop_r, prov is not None)
    apply_intraday_final(res, intraday_final(ctx, j) if partial else None)
    return res


def _annotations(m: Machine, s: Setup, j: dict, cfg: FibPullbackConfig, stop_r: float | None,
                 provisional: bool = False) -> list[dict]:
    d = m.b.date
    if m.b.dates is None:
        return []
    out = [segment([(d(s.l_i), s.L), (d(s.h), s.H)], "기준 파동", "#ff6d00")]
    for r in cfg.levels_buy:
        stop = r == stop_r
        out.append(hline(s.lv[r], f"피보 {_pct(r)} 관심 구간" + (" · 손절" if stop else ""),
                         "#1e88e5" if stop else "#7e57c2", "solid" if stop else "dashed"))
    inv = cfg.level_invalid
    out.append(hline(s.lv[inv], f"{_pct(inv)} 무효선" + (" · 손절" if stop_r == inv else ""), "#ef5350",
                     "solid" if stop_r == inv else "dotted"))
    if cfg.show_786:
        out.append(hline(s.H - 0.786 * (s.H - s.L), "78.6% (표시만)", "#9e9e9e", "dotted"))
    out.append(marker(d(s.b), "장대양봉", "above", "#ff6d00", "circle"))
    out.append(marker(d(s.h), "고점", "above", "#ef5350", "arrowDown"))
    if s.c is not None and s.c != s.h:
        out.append(marker(d(s.c), "고점 확정", "above", "#9e9e9e", "circle"))
    if s.touches:
        t, r = s.touches[-1]
        out.append(marker(d(t), f"접촉 {_pct(r)}", "below", "#7e57c2", "arrowUp"))
    if s.s is not None:
        out.append(hline(s.entry, "진입 (신호 종가)", "#e91e63", "solid"))
        out.append(marker(d(s.s), "신호" + (" (장중 잠정)" if provisional else ""), "below", "#e91e63", "arrowUp"))
        post = j["post"] or {}
        if post.get("stop_hit") is not None:
            out.append(marker(d(post["stop_hit"]), "손절", "above", "#1e88e5", "arrowDown"))
    return out
