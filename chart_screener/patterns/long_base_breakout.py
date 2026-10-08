"""장기 횡보 후 대량거래·대량 거래대금 장대양봉 돌파 (한국식 '장기 박스권 돌파').

장기간 박스권(바닥권 또는 추세 중간)에서 거래가 말라 있던 종목이, 거래량 폭증과
대량 거래대금(일 300억 이상)을 동반한 장대양봉으로 박스 상단을 뚫는 순간을 찾는다.

기준
 [베이스 — 돌파봉 직전까지 이어지는 연속 구간]
  1. 길이 60~500 거래일. 거친 길이 격자 + 5일 단위 보정으로 '가장 긴 유효 구간'을 고른다.
     각 구간은 앞머리의 박스 밖 종가(직전 추세의 꼬리 — 위쪽은 뒷부분 2/3 박스 상단 기준)를 잘라내
     '처음 박스에 들어온 봉'부터 센다.
  2. 견고한 박스: 상단 = 고가 95백분위, 하단 = 저가 5백분위 (일시적 꼬리·급등락 허용).
     박스 높이(상단/하단 - 1) ≤ 40%.
  3. 상단·하단 확인: 베이스 뒷부분 2/3 에서 고가가 상단 -3% 이내, 저가가 하단 +3% 이내에 다시 닿아야 한다.
     확인된 구간 중 가장 긴 것을 쓰고(직전 추세 꼬리가 피벗·하단을 만든 구간 배제), 확인된 구간이 없으면
     가장 짧은 유효 구간을 쓰며 경고한다 (돌파 전 관찰 단계는 확인 필수).
  4. 횡보: 종가 선형회귀로 본 베이스 전체 변화율 |drift| ≤ 15% 이고 ≤ 박스 높이의 60% (채널 배제),
     120일선의 최근 40일 변화율 |ma_drift| ≤ 10% (평탄).
  5. 순수 베이스: 베이스 안에 '그 박스 상단 위로 마감하고 실패하지 않은 1차 조건 통과 장대양봉'(이미 성공한
     돌파)이 없어야 한다. 그 뒤 실패선(상단 -3%·그 봉의 50%) 아래로 밀린 돌파 시도는 박스 안 사건으로 허용.
  6. 변동성 수축(ATR%·볼린저 폭이 자기 1년 중앙값보다 낮음)은 점수 가산.
  6b. 베이스 건전성(급등락 잔해): 5/95 백분위 박스는 펌프 앤 덤프 뒤의 거대한 실제 고저폭을 가릴 수 있다
     (녹십자엠에스 142280: 박스 38%, 실제 73%, 실패 스파이크 3회). 실제 고저폭(최고 고가/최저 저가 - 1)이
     100% 를 넘는 구간은 베이스가 아니고(더 짧은 구간을 찾음), 60% 이상이면 경고·감점.
     실패한 대량거래 스파이크(거래량 50일 평균 5배↑·거래대금 150억↑·고가가 상단 -3%↑ 까지 치솟았다 박스 안으로
     되돌아온 봉, 3봉 이내 연속은 1회)를 세어 2회 이상이면 경고·감점.
 [돌파봉 — 장대양봉]
  7. 종가 > 박스 상단 이고 > 베이스 구간 최고 종가. 첫 돌파: 직전 20봉 안에 상단 +3% 위 종가가 있었다면
     그 뒤 상단 -3% 아래로 복귀한 적이 있어야 한다 (이미 박스를 벗어나 달리는 중의 장대양봉 배제).
  8. 전일 대비 +7% 이상, 몸통 (종가-시가)/시가 ≥ 5%, 몸통비율 ≥ 0.6, 종가 위치 ≥ 0.7
     (윗꼬리 짧게 고가권 마감). 단 +25% 이상(상한가권)은 몸통·몸통비율 조건 면제(metrics.limit_up=True).
  9. 거래량 ≥ 직전 50일 평균 × 5 이고 ≥ 베이스 구간 최대 거래량.
 10. 거래대금 ≥ 300억 (Config.big_value_threshold) — 필수 (사용자 요구).
 [연속 장대양봉 = 하나의 돌파]
  서로 20봉 이내로 이어지는 돌파 이벤트들은 한 묶음으로 보고 '첫 장대양봉'을 돌파로 쓴다
  (피벗·손절·50% 기준·경과일 모두 첫 돌파 기준, 뒤의 것은 후속 장대양봉 metrics.legs).
  단 첫 돌파가 다음 장대양봉 전에 이미 실패(아래 failed 조건)했다면 다음 장대양봉은 새 돌파(재돌파)다.
 [최근성·단계 — 마지막 봉 기준 20봉 이내 돌파 묶음]
  지지선 = max(박스 상단, 장대양봉 50%).
  failed     : 종가 < 박스 상단 -3% 또는 < 장대양봉 50% ('장대양봉 50% 룰').
  near_pivot : 눌림목 — 돌파 2봉 이후 고점 대비 -5% 이상 되밀려 지지선 +5% 이내, 최근 3일 평균
               거래량 ≤ 돌파일의 40% (metrics.pullback=True).
  near_pivot : 재시험 — 종가가 박스 상단 이하로 되밀렸으나 실패선(상단 -3%·50%) 위.
  breakout   : 돌파 후 5봉 이내, 종가 > 박스 상단 이고 매수 한도 이내.
  near_pivot : 5봉이 지났고 지지선 +5% 이내에서 버티는 중 (재진입 관점).
  extended   : 위에 해당하지 않음 (5봉 이내 매수 한도 초과, 5봉 이후 지지선 +5% 초과).
  매수 한도(돌파 후 5봉 이내에만 적용) = max(박스 상단 +10%, 돌파 종가 +3%),
  단 손절가까지 위험이 15%를 넘는 가격은 제외.
  → 한국 장대양봉은 돌파 당일 이미 박스 상단을 10~30% 넘는 경우가 많아, 피벗 +5% 기준을 쓰면
    돌파 당일부터 '이격 과다'가 된다. 그래서 돌파 직후에는 박스 상단과 돌파 캔들 종가를 함께 기준으로 둔다.
    5봉이 지나면 지지선 근처(+5%)까지 되돌아온 경우만 매수 후보(near_pivot)로 본다.
 [돌파 전 관찰]
  전일까지 이어진 유효 90일 이상 장기 베이스(위 1~5 적용) 위에서 오늘 종가가 박스 상단 -8% ~ +3%,
  거래량 증가 시작(최근 5일 평균 ≥ 50일 평균 × 1.5 또는 양봉 당일 ≥ × 2.5) 이고 최근 10일
  상승일/하락일 거래량 비 ≥ 1.2 (매집 우위) → detected, pre_breakout=True.
  상단 -5% 이내면 near_pivot, 그 밖은 forming. 점수 상한 60.
 피벗 = 박스 상단을 KRX 호가 단위로 올림 (판정은 원래 상단 metrics.box_top 으로 한다).
 손절 = max(장대양봉 50%, 박스 상단 -8%) 를 호가 단위로 내림 — 진짜 돌파라면 장대양봉 절반 위에서 지지되어야
        하고(50% 룰), 몸통이 박스 안 깊이에서 시작된 경우에는 박스 상단 -8%(오닐 7~8% 손절)를 쓴다.
        장대양봉 50% = 몸통(시가~종가) 중간값. 상한가권은 (min(시가, 전일 종가) + 종가)/2.
        갭 상승·상한가처럼 50%선이 박스 상단보다 높으면 손절이 피벗 위에 놓인다(사유에 설명).
        돌파 전 관찰 단계는 박스 상단 -8%.
 metrics.support = max(박스 상단, 장대양봉 50%) 호가 올림 (눌림 지정가 기준선). 관찰 단계는 피벗.
 [맥락 지표 — 돌파봉 시점, 미래 참조 없음]
  ath_breakout  : 종가 > 돌파봉 이전 가용 이력(캐시 최대 약 3년) 최고 고가 (오닐: 신고가 매수)
  ma_stacked    : 종가 > 50일선 > 150일선 > 200일선 (이동평균 결측이면 False, ma_known=False)
  weekly_confirm: 돌파 주(월~금)의 주간 종가가 박스 상단 위이고 그 주 고저폭 위쪽 절반 마감 'yes'/'no',
                  주가 끝나지 않았으면 'pending' (detect 는 마지막 봉, find_breakouts 는 돌파봉 시점 기준)
  candle_class  : 'normal' +7~15% · 'strong' 15~25% · 'limit_up' 25%↑
  vol_class     : '<=15x' · '15-30x' · '>30x' (50일 평균 대비)
 점수(0~100) — 2024-09~2026-10 워크포워드(유동성 종목, 다음날 시가 매수) 장기횡보 돌파 n≈508 의 구간별
  성과에서 정한 굵은 단조 가감점 (점수 상수 PTS_* 옆 주석에 근거 수치). 옛 점수(베이스·거래량·캔들 강도 가점)는
  상위 3분위 60일 -2.2% vs 하위 +1.6% 로 거꾸로였다: 큰 거래량 배수·상한가·바닥권이 오히려 나빴다.
  돌파 시점: 기준 40 + 베이스 품질 0~10 (길이 4 · 박스 높이 3 · 평탄도 1 · 변동성 수축 2 — 표본에서 성과와
  뚜렷한 관계가 없어 작게) + RS 0~5 + 위치(2년 고점권 +12 / 바닥권 -8) + 신고가 +10 + 정배열 +8
  + 주간 확인(yes +4 / no -4) + 거래대금(<500억 -6 / 1000억↑ +5 / 3000억↑ +10)
  + 캔들(strong -3 / 상한가권 -12, 상한가 마감(종가 위치 > 0.95) 추가 -4) + 거래량(15~30배 -6 / 30배↑ -8)
  + 베이스 건전성(실제 고저폭 60%↑ -5, 실패 스파이크 2회째부터 회당 -5, 최대 -10).
  돌파 이후 상태(detect): breakout 0 · 눌림목·지지 중 -3 · 재시험·extended -5 · failed -20, 50% 이탈 이력 -5.
  (돌파 후 첫 눌림 진입은 표본에서 손절 도달 86% 로 돌파일보다 나빠 가점하지 않는다.)
  자가 점검(같은 표본, in-sample): 새 점수 3분위 60일 평균 -11.7% / -2.5% / +12.4%, 20일 -6.4% / -3.0% / +3.3%,
  기간 절반(2024-09~2025-09, 2025-10~2026-10) 모두 같은 방향. 각 가감 항목의 부호도 두 절반에서 같았다.
  돌파 전 관찰: 베이스 25 + RS 10 + 상단 근접 10 + 거래량 증가 10 + 거래대금 5, 상한 60, 베이스 건전성 감점 동일.
  metrics.score_parts = 항목별 점수 문자열 '기준 40 · 베이스 +7.1 · …' (0 항목 생략, 합 = 점수, 0~100 으로 자름;
  parse_score_parts() 로 dict 변환). metrics.failed_spike_dates 는 쉼표로 이은 날짜 문자열(없으면 None).
 find_breakouts(ctx) 는 가용 이력 전체의 돌파 이벤트(각 봉 시점 데이터만 사용, 연속 장대양봉은 첫 봉만)를
 돌려준다 (백테스트용). detect() 와 같은 판정 코드를 쓴다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import indicators as ind
from ..config import EOK
from ..market import CORRECTION
from .base import (BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult, StockContext, box, hline,
                   marker, register)
from .flat_base import krx_tick

NAME = "long_base_breakout"
LABEL = "장기횡보 후 대량거래 장대양봉 돌파"


@dataclass
class LongBaseBreakoutConfig:
    # ---- 베이스(장기 횡보)
    min_base: int = 60                    # 최소 횡보 기간(거래일) — 약 3개월
    max_base: int = 500                   # 최대 탐색 기간 — 약 2년
    base_grid: tuple = (60, 70, 80, 90, 100, 115, 130, 150, 170, 190, 210, 240, 270, 300, 340, 380, 420, 460, 500)
    refine_step: int = 5                  # 최장 유효 격자 ~ 다음 격자 사이 보정 단위
    box_hi_pct: float = 95.0              # 박스 상단 = 고가 95백분위 (일시 급등 꼬리 허용)
    box_lo_pct: float = 5.0               # 박스 하단 = 저가 5백분위 (일시 급락 허용)
    max_box_height: float = 0.40          # 박스 높이(상단/하단-1) 상한
    confirm_lead: float = 1 / 3           # 상단·하단 확인·앞머리 다듬기의 기준 = 베이스 앞 1/3 을 뺀 뒷부분
    touch_tol: float = 0.03               # 확인 = 뒷부분에서 고가가 상단 -3% / 저가가 하단 +3% 이내에 닿음
    max_drift: float = 0.15               # 베이스 전체 회귀 추세 변화율 상한 (횡보 판정)
    max_drift_ratio: float = 0.6          # |추세| / 박스 높이 상한 — 이를 넘으면 박스가 아니라 하락·상승 채널
    ma_len: int = 120                     # 평탄해야 하는 이동평균
    ma_lookback: int = 40                 # 120일선 변화율 측정 기간
    max_ma_drift: float = 0.10            # 120일선 40일 변화율 상한
    close_spike_tol: float = 0.05         # (관찰 단계) 베이스 내 종가가 박스 상단을 넘는 허용폭
    # ---- 돌파봉(장대양봉)
    min_chg: float = 0.07                 # 전일 대비 상승률 (실전은 +10~30% 다수)
    min_body: float = 0.05                # (종가-시가)/시가
    min_body_ratio: float = 0.6           # 몸통/고저폭
    min_close_pos: float = 0.7            # 고저폭 내 종가 위치 (윗꼬리 짧음)
    limit_up_chg: float = 0.25            # 이 이상(상한가권)은 몸통·몸통비율 조건 면제
    max_prev_above_top: float = 0.03      # 첫 돌파: 직전 first_lookback 봉 안에 상단 +3% 위 종가가 있었다면
    first_lookback: int = 20              #   그 뒤 상단 -fail_pct 아래로 복귀한 적이 있어야 함
    # ---- 거래량·거래대금
    vol_avg_len: int = 50                 # 평균 거래량 기간 (돌파일 제외 직전 50일)
    min_vol_mult: float = 5.0             # 돌파 거래량 ≥ 50일 평균 × 5
    vol_max_tol: float = 1.0              # 돌파 거래량 ≥ 베이스 최대 거래량 × tol
    min_value_eok: float | None = None    # None → Config.big_value_threshold (300억)
    # ---- 최근성·단계
    recent_window: int = 20               # 마지막 봉 기준 이 봉수 이내 돌파만 '현재 패턴'
    cluster_gap: int = 20                 # 이 봉수 이내로 이어지는 돌파 이벤트는 한 묶음(첫 봉이 돌파)
    breakout_window: int = 5              # 돌파 후 이 봉수 이내면 breakout
    buy_range_box: float = 0.10           # 매수 한도: 박스 상단 +10%
    buy_range_candle: float = 0.03        # 매수 한도: 돌파 종가 +3%
    max_entry_risk: float = 0.15          # 손절가까지 위험이 이를 넘는 가격은 매수 한도 밖
    hold_band: float = 0.05               # 5봉 이후 near_pivot: 지지선(max(상단, 50%)) +5% 이내
    fail_pct: float = 0.03                # 박스 상단 -3% 아래 종가 = 실패
    stop_below_top: float = 0.08          # 손절 후보: 박스 상단 -8%
    pullback_min_days: int = 2            # 눌림목은 돌파 2봉 이후부터
    pullback_band: float = 0.05           # 지지선 +5% 이내
    pullback_off_high: float = 0.05       # 돌파 후 고점 대비 -5% 이상 되밀림
    pullback_vol_max: float = 0.40        # 최근 3일 평균 거래량 ≤ 돌파일 × 0.4
    # ---- 돌파 전 관찰
    watch_min_base: int = 90              # 관찰 단계는 더 긴 베이스만 (실데이터: 60~90일 관찰 신호는 초과수익 없음)
    near_pct: float = 0.05                # 박스 상단 -5% 이내 → near_pivot
    watch_pct: float = 0.08               # 박스 상단 -8% 이내까지 관찰(forming)
    pre_above_max: float = 0.03           # 미확정 돌파 허용폭 (상단 +3%까지)
    vol_expand_5d: float = 1.5            # 최근 5일 평균 거래량 / 직전 50일 평균
    vol_expand_1d: float = 2.5            # 또는 당일(양봉) 거래량 / 직전 50일 평균
    ud_vol_min: float = 1.2               # 그리고 최근 10일 상승일/하락일 거래량 비 (매집 우위)
    ud_len: int = 10
    pre_score_cap: float = 60.0
    watch_min_avg_value: float = 20 * EOK  # 돌파 전 관찰: 20일 평균 거래대금 하한 (300억 = 평균의 15배 이내인 종목만)
    # ---- 베이스 건전성 (급등락 잔해: 5/95 백분위 박스가 실제 고저폭을 가리는 경우)
    max_true_range: float = 1.00          # 베이스 실제 고저폭(최고 고가/최저 저가 - 1) 상한 — 넘으면 횡보 베이스 아님
    warn_true_range: float = 0.60         # 이 이상이면 경고·감점 (녹십자엠에스 142280: 박스 38% · 실제 73%)
    spike_value_frac: float = 0.5         # 실패한 스파이크 거래대금 ≥ 300억 × 0.5 (위 실례의 스파이크 262~300억)
    spike_gap: int = 3                    # 이 봉수 이내로 이어진 스파이크 봉은 한 번으로 센다
    # ---- 위치·맥락
    range_len: int = 500                  # '2년' 범위 (위치 판정)
    high_zone: float = -0.15              # 박스 상단이 2년 고점 -15% 이내 → 'high'
    bottom_zone: float = -0.40            # 2년 고점 대비 -40% 이하 → 'bottom'
    compression_len: int = 250            # 변동성 비교 기준(자기 1년)
    ma_stack: tuple = (50, 150, 200)      # 정배열 판정: 종가 > 50일선 > 150일선 > 200일선 (돌파봉 기준)
    rs_floor: float = 50.0
    # ---- 점수 구간 (2024-09~2026-10 워크포워드 표본 근거 — 모듈 설명 '점수' 참고)
    strong_chg: float = 0.15              # 캔들 분류: +7~15% normal · 15~25% strong · 25%↑ limit_up
    climax_vol: tuple = (15.0, 30.0)      # 거래량 분류 경계: ≤15배 · 15~30배 · 30배 초과 (클라이맥스)
    value_steps_eok: tuple = (500, 1000, 3000)  # 거래대금 구간 경계(억): <500 감점 · 1000↑ · 3000↑ 가점
    hot_close_pos: float = 0.95           # 상한가권 캔들의 종가 위치가 이보다 높으면(상한가 마감) 추가 감점


# ====================================================================== 내부 배열
class _A:
    """numpy 배열 묶음 (탐지기 내부 전용)."""
    __slots__ = ("n", "o", "h", "l", "c", "v", "val", "chg", "body", "br", "cp", "vavg", "s0", "s1",
                 "ma", "atrp", "bbw", "cmax", "mid", "idx", "nan_fixed", "hprev", "mas", "wk")


def _arrays(ctx: StockContext, cfg: LongBaseBreakoutConfig) -> _A:
    key = (NAME, "arrays", cfg.vol_avg_len, cfg.ma_len, cfg.first_lookback, cfg.limit_up_chg, tuple(cfg.ma_stack))
    return ctx._memo(key, lambda: _build_arrays(ctx, cfg))


def _build_arrays(ctx: StockContext, cfg: LongBaseBreakoutConfig) -> _A:
    df = ctx.df
    A = _A()
    A.idx = df.index
    A.n = len(df)
    px = df[["open", "high", "low", "close"]].astype(float)
    A.nan_fixed = bool(px.isna().to_numpy().any())
    if A.nan_fixed:
        px = px.ffill().bfill()
    o, h, l, c = (px[k].to_numpy().copy() for k in ("open", "high", "low", "close"))
    # 시가·고가·저가 이상치(0·음수)는 종가로 보정 (정합성 유지)
    with np.errstate(invalid="ignore"):
        badp = ~(o > 0) | ~(h > 0) | ~(l > 0)
    if badp.any():
        A.nan_fixed = True
        o = np.where(o > 0, o, c)
        h = np.where(h > 0, h, np.maximum(o, c))
        l = np.where(l > 0, l, np.minimum(o, c))
    A.o, A.h, A.l, A.c = o, np.maximum.reduce([h, o, c]), np.minimum.reduce([l, o, c]), c
    A.v = np.nan_to_num(ctx.vol.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    A.val = np.nan_to_num(ctx.value.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pc = np.concatenate([[np.nan], A.c[:-1]])
        A.chg = A.c / pc - 1
        A.body = (A.c - A.o) / A.o
        rng = A.h - A.l
        A.br = np.where(rng > 0, np.abs(A.c - A.o) / rng, np.nan)
        # 고저폭 0(점상한가 등): 전일보다 높게 마감했으면 고가 마감으로 간주
        A.cp = np.where(rng > 0, (A.c - A.l) / rng, np.where(A.c > pc, 1.0, np.nan))
        # 장대양봉 50% 기준: 몸통(시가~종가) 중간값. 상한가권은 갭을 포함한 당일 상승분(전일 종가~종가)의 중간값.
        A.mid = np.where(A.chg >= cfg.limit_up_chg, (np.fmin(A.o, pc) + A.c) / 2, (A.o + A.c) / 2)
        vs = pd.Series(A.v)
        A.vavg = vs.rolling(cfg.vol_avg_len, min_periods=cfg.vol_avg_len).mean().shift(1).to_numpy()
        k = np.arange(A.n, dtype=float)
        A.s0 = np.concatenate([[0.0], np.cumsum(A.c)])
        A.s1 = np.concatenate([[0.0], np.cumsum(k * A.c)])
        cs = pd.Series(A.c)
        A.ma = cs.rolling(cfg.ma_len, min_periods=cfg.ma_len).mean().to_numpy()
        A.cmax = cs.rolling(max(cfg.first_lookback, 1), min_periods=1).max().to_numpy()
        pdf = pd.DataFrame({"high": A.h, "low": A.l, "close": A.c})
        A.atrp = (ind.atr(pdf, 14) / cs).to_numpy()
        A.bbw = ind.bb_width(cs, 20).to_numpy()
        # 직전 봉까지의 가용 이력 최고 고가 (첫 봉은 비교 대상 없음 → inf)
        A.hprev = np.concatenate([[np.inf], np.maximum.accumulate(A.h)[:-1]]) if A.n else A.h
        A.mas = [_sma(A.c, k) for k in cfg.ma_stack]
        # 월요일 시작 주 번호 (three_weeks_tight.weekly_groups 와 같은 규칙: 1970-01-01 목요일 기준)
        A.wk = (A.idx.values.astype("datetime64[D]").astype(np.int64) + 3) // 7
    return A


def _sma(x: np.ndarray, k: int) -> np.ndarray:
    """단순이동평균 (누적합, 앞 k-1 봉은 NaN) — pandas rolling 보다 빠름."""
    out = np.full(len(x), np.nan)
    if k >= 1 and len(x) >= k:
        cs = np.concatenate([[0.0], np.cumsum(x, dtype=float)])
        out[k - 1:] = (cs[k:] - cs[:-k]) / k
    return out


def _price_problem(A: _A) -> str | None:
    """판정 불가한 가격 데이터(보정 후에도 종가가 0·무한대)면 경고 문구 (detect·find_breakouts 공용)."""
    if not np.isfinite(A.c).all() or not (A.c > 0).all():
        return "✘ 가격 데이터 결측/0 — 판정 불가"
    return None


def _drift(A: _A, a: int, b: int) -> float:
    """[a, b] 구간 종가 선형회귀 기울기 × (L-1) / 평균 = 구간 전체 추세 변화율."""
    L = b - a + 1
    if L < 3:
        return float("nan")
    sy = A.s0[b + 1] - A.s0[a]
    sxy = (A.s1[b + 1] - A.s1[a]) - a * sy
    sx = L * (L - 1) / 2.0
    sxx = (L - 1) * L * (2 * L - 1) / 6.0
    den = L * sxx - sx * sx
    mean = sy / L
    if den <= 0 or not mean > 0:
        return float("nan")
    slope = (L * sxy - sx * sy) / den
    return float(slope * (L - 1) / mean)


def _pct(x: np.ndarray, q: float) -> float:
    """np.percentile(x, q) (선형 보간) 과 같은 값 — np.partition 으로 빠르게."""
    n = len(x)
    pos = q / 100.0 * (n - 1)
    lo = int(pos)
    if lo >= n - 1:
        return float(x.max())
    part = np.partition(x, (lo, lo + 1))
    return float(part[lo] + (part[lo + 1] - part[lo]) * (pos - lo))


def _box_stats(A: _A, e: int, L: int, cfg: LongBaseBreakoutConfig) -> dict:
    a = e - L + 1
    hs, ls = A.h[a:e + 1], A.l[a:e + 1]
    top, bot = _pct(hs, cfg.box_hi_pct), _pct(ls, cfg.box_lo_pct)
    height = top / bot - 1 if bot > 0 else float("inf")
    # 뒷부분(앞 1/3 제외): 상단·하단이 다시 시험되었는가 + 뒷부분 박스 상단(앞머리 다듬기 기준)
    k = int(L * cfg.confirm_lead)
    top_ok = bool((hs[k:] >= top * (1 - cfg.touch_tol)).any())
    bot_ok = bool((ls[k:] <= bot * (1 + cfg.touch_tol)).any())
    lmin = float(ls.min())
    true_range = float(hs.max()) / lmin - 1 if lmin > 0 else float("inf")
    return {"a": a, "e": e, "L": L, "top": top, "bottom": bot, "height": height, "true_range": true_range,
            "top_late": _pct(hs[k:], cfg.box_hi_pct),
            "drift": _drift(A, a, e), "max_close": float(A.c[a:e + 1].max()),
            "max_vol": float(A.v[a:e + 1].max()), "top_ok": top_ok, "bot_ok": bot_ok}


def _base_ok(b: dict, cfg: LongBaseBreakoutConfig) -> list[str]:
    """베이스 자체 조건 위반 사유 목록 (빈 리스트 = 통과)."""
    why = []
    if not b["height"] <= cfg.max_box_height:
        why.append(f"박스 높이 {b['height']:.0%} > {cfg.max_box_height:.0%}")
    if not abs(b["drift"]) <= cfg.max_drift:
        why.append(f"구간 추세 {b['drift']:+.0%} (|추세| > {cfg.max_drift:.0%}, 횡보 아님)")
    elif b["height"] > 0 and abs(b["drift"]) > cfg.max_drift_ratio * b["height"]:
        why.append(f"구간 추세 {b['drift']:+.0%} 가 박스 높이 {b['height']:.0%} 의 {cfg.max_drift_ratio:.0%} 초과 (채널형)")
    if not b["true_range"] <= cfg.max_true_range:
        why.append(f"베이스 실제 고저폭 {b['true_range']:.0%} > {cfg.max_true_range:.0%} (급등락 잔해 — 횡보 아님)")
    return why


def _confirm_why(b: dict) -> list[str]:
    """상단·하단 확인 실패 사유 (직전 추세 꼬리가 상단·하단을 만든 구간)."""
    why = []
    if not b["top_ok"]:
        why.append(f"박스 상단 {b['top']:,.0f} 이 베이스 앞부분(직전 추세 꼬리)에서만 형성")
    if not b["bot_ok"]:
        why.append(f"박스 하단 {b['bottom']:,.0f} 이 베이스 앞부분(직전 추세 꼬리)에서만 형성")
    return why


def _search_base(A: _A, e: int, cfg: LongBaseBreakoutConfig, extra, min_len: int | None = None,
                 strict_confirm: bool = False) -> tuple[dict | None, list[str]]:
    """e 에서 끝나는 '가장 긴' 유효 베이스. extra(b) 는 추가 조건 위반 사유 목록을 돌려준다.

    길이 격자의 각 길이마다 앞머리를 다듬은 박스(_trimmed_box)를 평가하고, 상단·하단이 확인된(_box_stats
    top_ok·bot_ok) 유효 구간 중 가장 긴 것을 고른 뒤 다음 격자까지 refine_step 단위로 보정한다.
    확인된 구간이 없으면 strict_confirm=False 일 때 가장 짧은 유효 구간(피벗이 가장 덜 부풀려진 박스)을 쓴다.
    반환: (베이스 dict 또는 None, 최단 길이에서의 탈락 사유)
    """
    min_len = min_len or cfg.min_base
    lim = min(cfg.max_base, e + 1)
    grid = [L for L in sorted(set(cfg.base_grid) | {min_len}) if min_len <= L <= lim]
    if not grid:
        return None, [f"베이스 탐색 이력 부족 ({e + 1}일 < {min_len}일)"]
    memo: dict[int, dict] = {}
    best, best_k, shortest, why0 = None, -1, None, []
    for k, L in enumerate(grid):
        b = _trimmed_box(A, e, L, cfg, min_len, memo)
        why = _base_ok(b, cfg) + extra(b)
        if why:
            if k == 0:
                why0 = why
            continue
        if b["top_ok"] and b["bot_ok"]:
            if best is None or b["L"] >= best["L"]:
                best = b
            best_k = k
        elif shortest is None:
            shortest = b
    if best is None:
        if shortest is None:
            return None, why0
        if strict_confirm:
            return None, _confirm_why(shortest)
        return shortest, []
    step = max(cfg.refine_step, 1)
    nxt = grid[best_k + 1] if best_k + 1 < len(grid) else lim + 1
    for L in range(grid[best_k] + step, min(nxt, lim + 1), step):
        b = _trimmed_box(A, e, L, cfg, min_len, memo)
        if b["L"] > best["L"] and b["top_ok"] and b["bot_ok"] and not (_base_ok(b, cfg) + extra(b)):
            best = b
    return best, []


def _trimmed_box(A: _A, e: int, L: int, cfg: LongBaseBreakoutConfig, min_len: int, memo: dict) -> dict:
    """길이 L 박스에서 앞머리의 박스 밖 종가(직전 하락·상승 추세의 꼬리)를 잘라낸 박스.

    긴 구간은 직전 추세의 끝자락을 포함하기 쉬워 백분위 상단이 부풀려지므로, 종가가 처음으로 박스 안
    (뒷부분 박스 상단과 전체 상단 중 낮은 값 ~ 전체 하단)에 들어온 봉부터를 베이스 시작으로 본다
    (수렴할 때까지 반복, 최소 길이 유지 시에만). 위쪽 기준에 뒷부분 상단을 쓰는 것은 서서히 내려오며
    박스에 진입한 하락 추세 꼬리가 상단(피벗)을 끌어올리는 것을 막기 위함.
    """
    def stats(n: int) -> dict:
        if n not in memo:
            memo[n] = _box_stats(A, e, n, cfg)
        return memo[n]

    b = stats(L)
    for _ in range(12):
        cl = A.c[b["a"]:e + 1]
        inside = (cl <= min(b["top"], b["top_late"])) & (cl >= b["bottom"])
        if not inside.any():
            break
        k = int(np.argmax(inside))
        if k == 0 or b["L"] - k < min_len:
            break
        b = stats(b["L"] - k)
    return b


def _prior_break(A: _A, cidx: np.ndarray, a: int, e: int, top: float, cfg: LongBaseBreakoutConfig) -> int | None:
    """[a, e] 안의 '이미 성공한 돌파' 위치: 1차 조건 통과 장대양봉 j 가 그 앞 구간의 박스 상단(= min(구간 상단,
    [a, j) 고가 95백분위))과 [a, j) 최고 종가를 종가로 넘었고(돌파봉 조건 7과 같은 기준), 그 뒤 e 까지
    실패선(max(그 상단 -3%, j 의 50%)) 아래로 밀린 적이 없음.

    앞 구간 상단을 함께 보는 것은 돌파 후 횡보(깃발)가 구간 상단을 끌어올려 이전 돌파를 가리는 것을 막기 위함.
    실패선 아래로 밀린 적이 있으면 실패한 돌파 시도(박스 안 사건)로 보고 무시한다.
    """
    lo, hi = np.searchsorted(cidx, a, "left"), np.searchsorted(cidx, e, "right")
    for j in cidx[lo:hi]:
        ref = min(top, _pct(A.h[a:j], cfg.box_hi_pct)) if j - a >= 10 else top
        if A.c[j] > ref and (j == a or A.c[j] > A.c[a:j].max()):
            line = max(ref * (1 - cfg.fail_pct), A.mid[j])
            if not (A.c[j + 1:e + 1] < line).any():
                return int(j)
    return None


def _not_first(A: _A, i: int, top: float, cfg: LongBaseBreakoutConfig) -> bool:
    """직전 first_lookback 봉 안에 박스 상단 +3% 위 종가가 있었고, 그 뒤 상단 -3% 아래로 되돌아온 적이 없으면
    (= 이미 박스를 벗어나 달리는 중) 첫 돌파가 아니다. 이탈 후 박스로 되돌아왔다면 실패한 이탈로 보고 허용."""
    hi_line = top * (1 + cfg.max_prev_above_top)
    if A.cmax[i - 1] <= hi_line:
        return False
    seg = A.c[max(0, i - cfg.first_lookback):i]
    k = int(np.flatnonzero(seg > hi_line)[-1])
    return not (seg[k + 1:] < top * (1 - cfg.fail_pct)).any()


def _ma_drift(A: _A, e: int, cfg: LongBaseBreakoutConfig) -> float:
    j = e - cfg.ma_lookback
    if j < 0 or not (np.isfinite(A.ma[e]) and np.isfinite(A.ma[j])) or A.ma[j] <= 0:
        return float("nan")
    return float(A.ma[e] / A.ma[j] - 1)


def _context_stats(A: _A, b: dict, cfg: LongBaseBreakoutConfig) -> dict:
    """베이스 종료 시점(e)까지 데이터만으로 계산하는 위치·수축 지표 (미래 참조 없음)."""
    e = b["e"]
    r0 = max(0, e - cfg.range_len + 1)
    hi2, lo2 = float(A.h[r0:e + 1].max()), float(A.l[r0:e + 1].min())
    mid = (b["top"] + b["bottom"]) / 2
    range_pos = (mid - lo2) / (hi2 - lo2) if hi2 > lo2 else 0.5
    dd = b["top"] / hi2 - 1 if hi2 > 0 else 0.0
    if dd >= cfg.high_zone:
        position = "high"
    elif dd <= cfg.bottom_zone and range_pos <= 0.4:
        position = "bottom"
    else:
        position = "mid"
    c0 = max(0, e - cfg.compression_len + 1)

    def _comp(x: np.ndarray) -> float:
        hist = x[c0:e + 1]
        hist = hist[np.isfinite(hist)]
        now = x[max(0, e - 9):e + 1]
        now = now[np.isfinite(now)]
        if len(hist) < 40 or not len(now):
            return float("nan")
        med = float(np.median(hist))
        return float(np.mean(now) / med) if med > 0 else float("nan")

    atr_c, bb_c = _comp(A.atrp), _comp(A.bbw)
    return {"position": position, "range_pos": float(range_pos), "dd_from_2y_high": float(dd),
            "high_2y": hi2, "low_2y": lo2, "atr_compression": atr_c, "bb_compression": bb_c,
            "ma120_drift": _ma_drift(A, e, cfg)}


def _failed_spikes(A: _A, b: dict, cfg: LongBaseBreakoutConfig, min_value: float) -> list[int]:
    """베이스 안의 실패한 대량거래 스파이크(첫 봉 위치 목록).

    스파이크 = 거래량 ≥ 50일 평균 × min_vol_mult, 거래대금 ≥ 300억 × spike_value_frac, 고가가 박스 상단 -3% 이상.
    그 봉이나 이후 베이스 안 종가가 박스 상단 이하로 되돌아왔으면 실패(공급 출회 흔적)로 센다.
    spike_gap 봉 이내로 이어진 스파이크 봉은 한 번으로 본다.
    """
    a, e, top = b["a"], b["e"], b["top"]
    seg_c = A.c[a:e + 1]
    back_in = np.minimum.accumulate(seg_c[::-1])[::-1] <= top     # 그 봉 이후 베이스 끝까지 최저 종가 ≤ 상단
    with np.errstate(invalid="ignore"):
        m = ((A.vavg[a:e + 1] > 0) & (A.v[a:e + 1] >= A.vavg[a:e + 1] * cfg.min_vol_mult)
             & (A.val[a:e + 1] >= min_value * cfg.spike_value_frac)
             & (A.h[a:e + 1] >= top * (1 - cfg.touch_tol)) & back_in)
    idx = np.flatnonzero(m) + a
    if not len(idx):
        return []
    keep = np.r_[True, np.diff(idx) > cfg.spike_gap]
    return [int(x) for x in idx[keep]]


def _ma_stacked(A: _A, i: int) -> tuple[bool, bool]:
    """(정배열 여부, 판정 가능 여부): 종가 > 50일선 > 150일선 > 200일선. 이동평균이 결측(이력 부족)이면 False."""
    vals = [float(m[i]) for m in A.mas]
    if not np.isfinite(vals).all():
        return False, False
    chain = [float(A.c[i])] + vals
    return all(x > y for x, y in zip(chain, chain[1:])), True


def _week_done(d) -> bool:
    """d 가 그 주의 마지막 거래일인지: 금요일(이후)이거나 같은 주 남은 평일이 모두 KRX 휴장일 (달력만 사용)."""
    # 지연 import: 모듈 로드 순서(레지스트리 등록 순서)를 바꾸지 않기 위함
    from .three_weeks_tight import FIXED_HOLIDAYS, KRX_EXTRA_HOLIDAYS
    d = pd.Timestamp(d)
    wd = d.weekday()
    for k in range(1, max(0, 5 - wd)):
        x = d + pd.Timedelta(days=k)
        if x.strftime("%m-%d") not in FIXED_HOLIDAYS and x.strftime("%Y-%m-%d") not in KRX_EXTRA_HOLIDAYS:
            return False
    return True


def _weekly_confirm(A: _A, i: int, top: float, upto: int, partial: bool) -> str:
    """돌파 주간 확인 ('yes'|'no'|'pending'): 돌파봉(i)이 속한 주의 주간 종가가 박스 상단 위이고 그 주
    고저폭의 위쪽 절반에서 마감했는가. upto 봉까지의 데이터만 쓴다(미래 참조 없음). 그 주가 upto 시점에
    아직 끝나지 않았으면(주 중간이거나 장중 미완성 봉) 'pending'."""
    w = A.wk[i]
    s, j = i, i
    while s > 0 and A.wk[s - 1] == w:
        s -= 1
    while j < upto and A.wk[j + 1] == w:
        j += 1
    if j == upto and (partial or not _week_done(A.idx[upto])):
        return "pending"
    hi, lo, c = float(A.h[s:j + 1].max()), float(A.l[s:j + 1].min()), float(A.c[j])
    return "yes" if c > top and c >= (hi + lo) / 2 else "no"


def _tick_up(p: float) -> float:
    """p 이상인 가장 가까운 KRX 호가 (피벗·지지선: 그 가격을 넘어야 의미가 있음)."""
    if not (np.isfinite(p) and p > 0):
        return float(p)
    t = krx_tick(p)
    return float(math.ceil(p / t - 1e-9) * t)


def _tick_down(p: float) -> float:
    """p 이하인 가장 가까운 KRX 호가 (손절가)."""
    if not (np.isfinite(p) and p > 0):
        return float(p)
    t = krx_tick(p)
    return float(max(t, math.floor(p / t + 1e-9) * t))


def _candle_class(chg: float, cfg: LongBaseBreakoutConfig) -> str:
    """'normal'(+7~15%) · 'strong'(15~25%) · 'limit_up'(25%↑, 몸통 조건 면제 플래그와 동일 기준)."""
    return "limit_up" if chg >= cfg.limit_up_chg else ("strong" if chg >= cfg.strong_chg else "normal")


def _vol_class(vm: float, cfg: LongBaseBreakoutConfig) -> str:
    lo, hi = cfg.climax_vol
    return f"<={lo:g}x" if vm <= lo else (f"{lo:g}-{hi:g}x" if vm <= hi else f">{hi:g}x")


def _min_value(ctx: StockContext, cfg: LongBaseBreakoutConfig) -> float:
    return cfg.min_value_eok * EOK if cfg.min_value_eok is not None else float(ctx.cfg.big_value_threshold)


def _candle_fail(A: _A, i: int, cfg: LongBaseBreakoutConfig, min_value: float) -> list[str]:
    """돌파봉 단독 조건(캔들·거래량 배수·거래대금) 위반 사유."""
    why = []
    chg, body, br, cp = A.chg[i], A.body[i], A.br[i], A.cp[i]
    if not chg >= cfg.min_chg:
        why.append(f"상승률 {chg:+.1%} < {cfg.min_chg:.0%}")
    if not chg >= cfg.limit_up_chg:  # 상한가권은 몸통 조건 면제
        if not body >= cfg.min_body:
            why.append(f"몸통 {body:+.1%} < {cfg.min_body:.0%}")
        if not br >= cfg.min_body_ratio:
            why.append(f"몸통비율 {br:.2f} < {cfg.min_body_ratio}")
    if not cp >= cfg.min_close_pos:
        why.append(f"종가 위치 {cp:.2f} < {cfg.min_close_pos} (윗꼬리 김)")
    vm = A.v[i] / A.vavg[i] if A.vavg[i] > 0 else float("nan")
    if not vm >= cfg.min_vol_mult:
        why.append(f"거래량 {vm:.1f}배 < 50일 평균 {cfg.min_vol_mult:.0f}배")
    if not A.val[i] >= min_value:
        why.append(f"거래대금 {A.val[i] / EOK:,.0f}억 < {min_value / EOK:,.0f}억")
    return why


def _breakout_extra(A: _A, i: int, cfg: LongBaseBreakoutConfig, cidx: np.ndarray):
    def extra(b: dict) -> list[str]:
        why = []
        top = b["top"]
        if not A.c[i] > top:
            why.append(f"종가 {A.c[i]:,.0f} ≤ 박스 상단 {top:,.0f}")
        elif not A.c[i] > b["max_close"]:
            why.append(f"종가 {A.c[i]:,.0f} ≤ 베이스 최고 종가 {b['max_close']:,.0f}")
        if not A.v[i] >= b["max_vol"] * cfg.vol_max_tol:
            why.append("돌파 거래량이 베이스 구간 최대 거래량 미만")
        if _not_first(A, i, top, cfg):
            why.append(f"직전 {cfg.first_lookback}봉 안에 박스 상단 +{cfg.max_prev_above_top:.0%} 위 마감 후 "
                       f"박스로 복귀하지 않음 (첫 돌파 아님)")
        j = _prior_break(A, cidx, b["a"], b["e"], top, cfg)
        if j is not None:
            why.append(f"베이스 안에 이미 박스 상단을 넘어 유지된 장대양봉({_date(A, j)}) 존재 (첫 돌파 아님)")
        return why
    return extra


def _eval_breakout(ctx: StockContext, A: _A, i: int, cfg: LongBaseBreakoutConfig, min_value: float,
                   cidx: np.ndarray) -> tuple[dict | None, list[str]]:
    """i 봉이 장기 베이스 돌파 장대양봉인지 평가. (이벤트 dict | None, 탈락 사유)"""
    if i < cfg.min_base + 1:
        return None, ["돌파봉 이전 이력 부족"]
    why = _candle_fail(A, i, cfg, min_value)
    if why:
        return None, why
    b, why = _search_base(A, i - 1, cfg, _breakout_extra(A, i, cfg, cidx))
    if b is None:
        return None, why
    st = _context_stats(A, b, cfg)
    if np.isfinite(st["ma120_drift"]) and abs(st["ma120_drift"]) > cfg.max_ma_drift:
        return None, [f"{cfg.ma_len}일선 {cfg.ma_lookback}일 변화 {st['ma120_drift']:+.0%} (평탄하지 않음)"]
    limit_up = bool(A.chg[i] >= cfg.limit_up_chg)  # 몸통 조건 면제 여부와 같은 플래그
    mid = float(A.mid[i])
    base_avg_vol = float(A.v[b["a"]:b["e"] + 1].mean())
    vm = float(A.v[i] / A.vavg[i])
    spikes = _failed_spikes(A, b, cfg, min_value)
    stacked, ma_known = _ma_stacked(A, i)
    ev = {
        "i": int(i), "date": _date(A, i),
        "base_start_i": int(b["a"]), "base_start": _date(A, b["a"]), "base_end": _date(A, b["e"]),
        "base_days": int(b["L"]), "box_top": b["top"], "box_bottom": b["bottom"], "box_height": b["height"],
        "base_drift": b["drift"], "base_max_close": b["max_close"],
        "top_confirmed": b["top_ok"], "bottom_confirmed": b["bot_ok"],
        "open": float(A.o[i]), "high": float(A.h[i]), "low": float(A.l[i]), "close": float(A.c[i]),
        "change": float(A.chg[i]), "body": float(A.body[i]), "body_ratio": float(np.nan_to_num(A.br[i])),
        "close_pos": float(A.cp[i]), "limit_up": limit_up, "candle_mid": float(mid),
        "volume": float(A.v[i]), "vol_mult_50d": vm,
        "vol_mult_base": float(A.v[i] / base_avg_vol) if base_avg_vol > 0 else float("inf"),
        "value_eok": float(A.val[i] / EOK),
        "close_above_top": float(A.c[i] / b["top"] - 1),
        # 맥락 (오닐: 신고가 매수·바닥 잡기 회피·클라이맥스 거래량 경계)
        "ath_breakout": bool(A.c[i] > A.hprev[i]), "prior_high": float(A.hprev[i]),
        "ma_stacked": bool(stacked), "ma_known": bool(ma_known),
        "weekly_confirm": _weekly_confirm(A, i, b["top"], i, ctx.partial and i == A.n - 1),
        "candle_class": _candle_class(float(A.chg[i]), cfg), "vol_class": _vol_class(vm, cfg),
        # 베이스 건전성
        "true_range": b["true_range"], "failed_spikes": len(spikes),
        "failed_spike_dates": [_date(A, j) for j in spikes],
        **st,
    }
    ev["rs"] = _rs_at(ctx, A, i)
    ev["score"] = _clip_score(_core_score(ev, cfg))
    return ev, []


def _date(A: _A, i: int) -> str:
    return pd.Timestamp(A.idx[i]).strftime("%Y-%m-%d")


def _rs_at(ctx: StockContext, A: _A, i: int) -> float | None:
    h = ctx.rs_rating_hist
    if h is None or not len(h):
        return ctx.rs_rating if i == A.n - 1 else None
    try:
        k = h.index.searchsorted(A.idx[i], side="right") - 1
    except TypeError:
        return None
    if k < 0:
        return None
    v = float(h.iloc[k])
    return v if np.isfinite(v) else None


class _Scan:
    """후보봉(1차 필터 통과) 평가 메모 + 연속 장대양봉 묶음 판정 (detect·find_breakouts 공용)."""

    def __init__(self, ctx: StockContext, A: _A, cfg: LongBaseBreakoutConfig, min_value: float):
        self.ctx, self.A, self.cfg, self.min_value = ctx, A, cfg, min_value
        self.cidx = _candidates(A, cfg, min_value)
        self.memo: dict[int, tuple[dict | None, list[str]]] = {}

    def eval(self, i: int) -> tuple[dict | None, list[str]]:
        if i not in self.memo:
            self.memo[i] = _eval_breakout(self.ctx, self.A, i, self.cfg, self.min_value, self.cidx)
        return self.memo[i]

    def between(self, lo: int, hi: int) -> np.ndarray:
        """[lo, hi] 안의 후보봉 위치 (오름차순)."""
        return self.cidx[np.searchsorted(self.cidx, lo, "left"):np.searchsorted(self.cidx, hi, "right")]

    def cluster(self, ev: dict) -> list[dict]:
        """ev 가 속한 연속 장대양봉 묶음 [첫 돌파, ..., ev].

        앞쪽으로 cluster_gap 이내 이벤트를 거슬러 사슬을 모은 뒤, 앞에서부터 다시 훑으며 묶음의 첫 돌파가
        다음 이벤트 전에 실패했으면(_anchor_failed) 그 이벤트부터 새 묶음으로 본다 (find_breakouts 와 같은 규칙).
        """
        chain, cur = [ev], ev["i"]
        while True:
            found = [e for j in self.between(cur - self.cfg.cluster_gap, cur - 1)
                     if (e := self.eval(int(j))[0]) is not None]
            if not found:
                break
            chain = found + chain
            cur = found[0]["i"]
        k0 = 0
        for k in range(1, len(chain)):
            if _anchor_failed(self.A, self.cfg, chain[k0], chain[k]["i"] - 1):
                k0 = k
        return chain[k0:]


def _anchor_failed(A: _A, cfg: LongBaseBreakoutConfig, anchor: dict, upto: int) -> bool:
    """첫 돌파(anchor) 이후 upto 봉까지 실패선(max(박스 상단 -3%, 장대양봉 50%)) 아래 종가가 있었는가."""
    line = max(anchor["box_top"] * (1 - cfg.fail_pct), anchor["candle_mid"])
    return bool((A.c[anchor["i"] + 1:upto + 1] < line).any())


# ====================================================================== 점수
def _clip01(x: float) -> float:
    return 0.0 if not np.isfinite(x) else float(min(1.0, max(0.0, x)))


def _base_points(L: int, height: float, drift: float, comp: float, cfg: LongBaseBreakoutConfig,
                 total: float = 25.0) -> float:
    """베이스 품질 (기본 25점, total 로 비례 축소): 길이 9 (60일→0, 250일↑→9) + 박스 높이 8 (40%→0, 15%↓→8)
    + 평탄도 4 (|추세| 15%→0, 0%→4) + 변동성 수축 4 (1.2배→0, 0.7배↓→4, 정보 없음 2)."""
    pl = 9 * _clip01((L - cfg.min_base) / 190)
    pt = 8 * _clip01((cfg.max_box_height - height) / max(cfg.max_box_height - 0.15, 1e-9))
    pf = 4 * _clip01(1 - abs(drift) / cfg.max_drift) if np.isfinite(drift) else 0.0
    pc = 4 * _clip01((1.2 - comp) / 0.5) if np.isfinite(comp) else 2.0
    return (pl + pt + pf + pc) * total / 25.0


def _rs_points(rs: float | None, cfg: LongBaseBreakoutConfig, total: float = 10.0) -> float:
    """RS (기본 10점): 50 이하 0 → 99 만점. 정보 없으면 절반."""
    return total / 2 if rs is None else total * _clip01((rs - cfg.rs_floor) / (99 - cfg.rs_floor))


def _comp_of(ev: dict) -> float:
    vals = [x for x in (ev.get("atr_compression"), ev.get("bb_compression")) if x is not None and np.isfinite(x)]
    return float(np.mean(vals)) if vals else float("nan")


def _clip_score(x: float) -> float:
    return float(min(100.0, max(0.0, x)))


# 점수 근거: 2024-09~2026-10 워크포워드, 유동성 종목, 다음날 시가 매수 (in-sample 통계 — 과최적화를 피하려
# 굵은 단조 구간 가감점만 쓴다). 돌파 전체 표본 n≈509: 20일 평균 -2.0% (중앙 -7.4%, 승률 34%), 60일 -0.6%,
# 손절이 +20% 보다 먼저 닿은 비율 72%.
SCORE_BASE = 40.0          # 기준점: '평균적인' 장기횡보 돌파 (표본 60일 평균 ≈ 0%)
PTS_POSITION = {"high": 12.0, "mid": 0.0, "bottom": -8.0}  # 60일 평균 +12.4% / -1.3% / -6.4%
PTS_ATH = 10.0             # 가용 이력 최고가 위 종가: 60일 중앙값 -1.6% vs -12.7%
PTS_MA_STACKED = 8.0       # 종가>50>150>200일선: 60일 중앙값 -4.8% vs -13.5%
# 돌파 주 확인: 다음날 시가 진입 기준 손절 도달 64% vs 91% 이지만, 그 차이 대부분은 돌파 주 안의 움직임이다.
# 주가 끝난 뒤 진입하면 20일 -0.6% vs -1.8% (중앙값 차이 없음) → 작은 가감점만.
PTS_WEEKLY = {"yes": 4.0, "pending": 0.0, "no": -4.0}
PTS_VALUE = (-6.0, 0.0, 5.0, 10.0)   # <500억 -7.2% · 500~1000억 +0.2% · 1000~3000억 +4.3% · 3000억↑ +7.8%
PTS_CANDLE = {"normal": 0.0, "strong": -3.0, "limit_up": -12.0}  # +7~15% +4~17% · 15~25% +1~3% · 상한가권 -5.0%
PTS_VOL = (0.0, -6.0, -8.0)          # ≤15배 +7~8% · 15~30배 -5.0% · 30배↑ -4.4% (클라이맥스 거래량)
# 종가 위치 > 0.95 전체 -4.0% 는 상한가 마감과 겹친 효과: 비상한가 n=35 는 60일 +9.2%, 상한가권 안에서는
# 고가(상한가) 마감 -6.2% vs 윗꼬리 +0.3% → 상한가권 캔들에만 추가 감점.
PTS_HOT_CLOSE = -4.0
PTS_TRUE_RANGE = -5.0      # 베이스 실제 고저폭 ≥ 60%: 60일 -5.8% (40% 미만 +4.7%)
# 실패한 대량거래 스파이크: 1회는 흔한 흔들기(60일 +1.7%), 2회↑ -3.5~-8.3% → 두 번째부터 회당 감점
PTS_SPIKE, MAX_SPIKE_PENALTY = -5.0, -10.0


def _score_parts(ev: dict, cfg: LongBaseBreakoutConfig) -> dict[str, float]:
    """돌파 시점에 알 수 있는 점수 구성 {항목: 점수}. 합계 = 돌파봉 점수 (0~100 자르기 전).

    기준 40 + 베이스 품질 0~10 + RS 0~5 + 위치 -8~+12 + 신고가 +10 + 정배열 +8 + 주간 확인 -4~+4
    + 거래대금 -6~+10 + 캔들 -12~0 + 거래량 -8~0 + 상한가 마감 -4 + 베이스 건전성 -15~0.
    """
    v1, v2, v3 = cfg.value_steps_eok
    val = ev["value_eok"]
    lo, hi = cfg.climax_vol
    vm = ev["vol_mult_50d"]
    parts = {
        "기준": SCORE_BASE,
        "베이스": _base_points(ev["base_days"], ev["box_height"], ev["base_drift"], _comp_of(ev), cfg, total=10.0),
        "RS": _rs_points(ev.get("rs"), cfg, total=5.0),
        "위치": PTS_POSITION.get(ev["position"], 0.0),
        "신고가": PTS_ATH if ev["ath_breakout"] else 0.0,
        "정배열": PTS_MA_STACKED if ev["ma_stacked"] else 0.0,
        "주간 확인": PTS_WEEKLY.get(ev["weekly_confirm"], 0.0),
        "거래대금": PTS_VALUE[0] if val < v1 else PTS_VALUE[1] if val < v2 else PTS_VALUE[2] if val < v3 else PTS_VALUE[3],
        "캔들": PTS_CANDLE.get(ev["candle_class"], 0.0),
        "거래량": PTS_VOL[0] if vm <= lo else PTS_VOL[1] if vm <= hi else PTS_VOL[2],
        "상한가 마감": PTS_HOT_CLOSE if (ev["limit_up"] and ev["close_pos"] > cfg.hot_close_pos) else 0.0,
        "베이스 건전성": ((PTS_TRUE_RANGE if ev["true_range"] >= cfg.warn_true_range else 0.0)
                    + max(MAX_SPIKE_PENALTY, PTS_SPIKE * max(0, ev["failed_spikes"] - 1))),
    }
    return {k: round(float(x), 1) for k, x in parts.items()}


def _core_score(ev: dict, cfg: LongBaseBreakoutConfig) -> float:
    """돌파 시점 점수 (돌파 후 상태 가감은 detect() 에서 더한다)."""
    return float(sum(_score_parts(ev, cfg).values()))


def format_score_parts(parts: dict[str, float]) -> str:
    """점수 구성 → 표시용 문자열 '기준 40 · 베이스 +7.1 · 거래대금 -6' (0 인 항목은 생략).
    리포트가 수치를 문자열 그대로 보여 주므로 metrics.score_parts 는 이 문자열로 둔다."""
    out = []
    for k, v in parts.items():
        if k != "기준" and abs(v) < 0.05:
            continue
        txt = f"{v:.1f}" if k == "기준" else f"{v:+.1f}"
        out.append(f"{k} {txt.rstrip('0').rstrip('.')}")
    return " · ".join(out)


def parse_score_parts(text: str | None) -> dict[str, float]:
    """format_score_parts 의 역변환 (생략된 0 항목은 없음)."""
    out: dict[str, float] = {}
    for item in (text or "").split(" · "):
        if " " in item:
            k, v = item.rsplit(" ", 1)
            out[k] = float(v)
    return out


# 돌파 이후 상태 가감 (scoring.py 단계 가중치와 별도로, 패턴 자체 점수에도 현재 상태를 반영)
# 눌림목은 가점하지 않는다: 표본에서 돌파 후 첫 눌림 진입은 손절 도달 86% 로 돌파일보다 나빴다.
POST_ADJ = {"breakout": 0.0, "pullback": -3.0, "holding": -3.0, "retest": -5.0, "extended": -5.0, "failed": -20.0}
PTS_LOST_MID = -5.0        # 돌파 이후 한때 장대양봉 50% 아래 종가


# ====================================================================== 공개 API
def find_breakouts(ctx: StockContext, cfg: LongBaseBreakoutConfig | None = None,
                   start: int | None = None) -> list[dict]:
    """가용 이력 전체(또는 ``start`` 이후)의 장기 베이스 돌파 장대양봉 이벤트 목록 (백테스트용).

    각 이벤트는 그 봉까지의 데이터만으로 판정된다(미래 참조 없음). 직전 cluster_gap 봉 안에 다른 돌파
    이벤트가 있고 그 묶음의 첫 돌파가 아직 실패하지 않았다면 같은 돌파의 후속 장대양봉이므로 제외한다
    (묶음의 첫 봉만 반환).
    키: i, date, base_start, base_days, box_top, box_bottom, box_height, base_drift, change, body,
        close_pos, vol_mult_50d, vol_mult_base, value_eok, candle_mid, position, atr_compression, rs, score,
        ath_breakout, ma_stacked, weekly_confirm(돌파봉 시점), candle_class, vol_class, true_range,
        failed_spikes, failed_spike_dates ... (score = 돌파 시점 점수, 돌파 후 상태 가감 없음)
    """
    cfg = cfg or ctx.cfg.pattern_cfg(NAME, LongBaseBreakoutConfig)
    if ctx.n < cfg.min_base + 2:
        return []
    A = _arrays(ctx, cfg)
    if _price_problem(A):
        return []
    S = _Scan(ctx, A, cfg, _min_value(ctx, cfg))
    events, prev, anchor = [], None, None
    for i in S.cidx:
        ev, _ = S.eval(int(i))
        if ev is None:
            continue
        if prev is None or ev["i"] - prev > cfg.cluster_gap or _anchor_failed(A, cfg, anchor, ev["i"] - 1):
            anchor = ev                                   # 새 돌파 (묶음의 첫 장대양봉)
            if start is None or ev["i"] >= start:
                events.append(ev)
        prev = ev["i"]
    return events


def _candidates(A: _A, cfg: LongBaseBreakoutConfig, min_value: float) -> np.ndarray:
    """캔들·거래량 배수·거래대금 1차 필터 (벡터화). 베이스 평가는 통과한 봉에만 수행."""
    with np.errstate(invalid="ignore", divide="ignore"):
        limit_up = A.chg >= cfg.limit_up_chg
        shape = ((A.body >= cfg.min_body) & (A.br >= cfg.min_body_ratio)) | limit_up
        m = ((A.chg >= cfg.min_chg) & shape & (A.cp >= cfg.min_close_pos)
             & (A.v >= A.vavg * cfg.min_vol_mult) & (A.vavg > 0) & (A.val >= min_value))
    m[: cfg.min_base + 1] = False
    return np.flatnonzero(m)


# ====================================================================== 탐지
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, LongBaseBreakoutConfig)
    res = PatternResult(name=NAME, label=LABEL)
    need = cfg.min_base + 2
    if ctx.n < need:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}일 < {need}일) — 장기 횡보 판정 불가")
        return res
    A = _arrays(ctx, cfg)
    bad = _price_problem(A)
    if bad:
        res.warnings.append(bad)
        return res
    if A.nan_fixed:
        res.warnings.append("✘ 가격 결측·이상치를 보정함 (직전 값/종가)")
    S = _Scan(ctx, A, cfg, _min_value(ctx, cfg))
    last = A.n - 1
    start = max(cfg.min_base + 1, last - cfg.recent_window + 1)

    newest = None
    for i in S.between(start, last)[::-1]:  # 가장 최근 돌파부터
        newest, _ = S.eval(int(i))
        if newest is not None:
            break
    if newest is not None:
        _fill_breakout(ctx, A, S.cluster(newest), cfg, res)
    elif not _fill_watch(ctx, A, cfg, S, res):
        _explain_miss(A, cfg, S, start, res)
    _common_warnings(ctx, A, cfg, res)
    res.score = float(round(min(100.0, max(0.0, res.score)), 1))
    return res


def _stop_and_limit(ev: dict, cfg: LongBaseBreakoutConfig) -> tuple[float, float]:
    top = ev["box_top"]
    stop = _tick_down(max(ev["candle_mid"], top * (1 - cfg.stop_below_top)))
    limit = max(top * (1 + cfg.buy_range_box), ev["close"] * (1 + cfg.buy_range_candle))
    limit = min(limit, stop / (1 - cfg.max_entry_risk))
    return float(stop), float(max(limit, top))


def _post_state(A: _A, ev: dict, cfg: LongBaseBreakoutConfig) -> dict:
    """돌파(묶음의 첫 장대양봉) 이후 마지막 봉의 상태와 단계."""
    last = A.n - 1
    bo = ev["i"]
    top, mid = ev["box_top"], ev["candle_mid"]
    c = float(A.c[last])
    days = last - bo
    stop, limit = _stop_and_limit(ev, cfg)
    post = A.c[bo:last + 1]
    peak = float(post.max())
    support = max(top, mid)
    hold_zone = support * (1 + cfg.hold_band)
    recent_vol = float(A.v[max(bo + 1, last - 2):last + 1].mean()) if days >= 1 else float(A.v[bo])
    vol_dry = bool(days >= 1 and recent_vol <= A.v[bo] * cfg.pullback_vol_max)

    if c < top * (1 - cfg.fail_pct) or c < mid:
        stage, state = FAILED, "failed"
    elif (days >= cfg.pullback_min_days and c <= support * (1 + cfg.pullback_band)
          and c <= peak * (1 - cfg.pullback_off_high) and vol_dry):
        stage, state = NEAR_PIVOT, "pullback"
    elif c <= top:                      # 박스 상단 아래로 되밀렸지만 실패선 위 → 재시험
        stage, state = NEAR_PIVOT, "retest"
    elif days <= cfg.breakout_window:
        stage, state = (BREAKOUT, "breakout") if c <= limit else (EXTENDED, "extended")
    elif c <= hold_zone:                # 5봉 이후 지지선 +5% 이내에서 버팀 → 재진입 관점
        stage, state = NEAR_PIVOT, "holding"
    else:
        stage, state = EXTENDED, "extended"
    return {"stage": stage, "state": state, "c": c, "days": days, "stop": stop, "limit": limit, "peak": peak,
            "support": support, "hold_zone": hold_zone, "recent_vol": recent_vol, "vol_dry": vol_dry,
            "hold_mid": bool((post >= mid).all()), "hold_top": bool((post >= top * (1 - cfg.fail_pct)).all())}


def _fill_breakout(ctx: StockContext, A: _A, legs: list[dict], cfg: LongBaseBreakoutConfig,
                   res: PatternResult) -> None:
    ev = legs[0]                        # 묶음의 첫 장대양봉 = 돌파
    last = A.n - 1
    bo = ev["i"]
    top, mid = ev["box_top"], ev["candle_mid"]
    P = _post_state(A, ev, cfg)
    stage, state, c, days = P["stage"], P["state"], P["c"], P["days"]
    stop, limit, peak, support = P["stop"], P["limit"], P["peak"], P["support"]
    recent_vol, hold_mid = P["recent_vol"], P["hold_mid"]
    pullback = state == "pullback"
    pivot = _tick_up(top)

    res.detected = True
    res.stage = stage
    res.pivot = pivot
    res.stop = stop
    res.start_date = ev["base_start"]
    res.end_date = _date(A, last)
    res.breakout_date = ev["date"]

    # 점수 = 돌파 시점 구성(주간 확인·RS 는 현재 값) + 돌파 이후 상태 가감
    weekly = _weekly_confirm(A, bo, top, last, ctx.partial)
    ev_now = dict(ev, weekly_confirm=weekly, rs=ctx.rs_rating if ctx.rs_rating is not None else ev.get("rs"))
    parts = _score_parts(ev_now, cfg)
    parts["돌파 후 상태"] = POST_ADJ[state] + (PTS_LOST_MID if state != "failed" and not hold_mid else 0.0)
    res.score = sum(parts.values())

    risk = (c - stop) / c if c > 0 else float("nan")
    res.metrics = {
        "base_days": ev["base_days"], "box_height": ev["box_height"], "breakout_change": ev["change"],
        "vol_mult_50d": ev["vol_mult_50d"], "value_eok": ev["value_eok"],
        "days_since_breakout": int(days), "position": ev["position"], "pullback": pullback,
        "post_state": state, "box_top": top, "box_bottom": ev["box_bottom"], "base_drift": ev["base_drift"],
        "ma120_drift": ev["ma120_drift"], "breakout_date": ev["date"], "body": ev["body"],
        "body_ratio": ev["body_ratio"], "close_pos": ev["close_pos"], "limit_up": ev["limit_up"],
        "vol_mult_base": ev["vol_mult_base"], "candle_mid": mid, "hold_above_mid": hold_mid,
        "hold_above_top": P["hold_top"], "pre_breakout": False, "range_pos": ev["range_pos"],
        "dd_from_2y_high": ev["dd_from_2y_high"], "atr_compression": ev["atr_compression"],
        "bb_compression": ev["bb_compression"], "close_above_top": ev["close_above_top"],
        "post_peak_gain": peak / top - 1, "dist_from_pivot": c / top - 1, "buy_limit": limit,
        "support": _tick_up(support), "hold_zone": P["hold_zone"], "risk_pct": risk,
        "recent_vol_vs_breakout": recent_vol / A.v[bo] if A.v[bo] > 0 else float("nan"),
        "legs": len(legs), "last_leg_date": legs[-1]["date"] if len(legs) > 1 else None,
        "top_confirmed": ev["top_confirmed"], "bottom_confirmed": ev["bottom_confirmed"],
        # 재보정 지표 (2024-26 표본 근거 — 모듈 설명 '점수')
        "ath_breakout": ev["ath_breakout"], "prior_high": ev["prior_high"], "ma_stacked": ev["ma_stacked"],
        "weekly_confirm": weekly, "candle_class": ev["candle_class"], "vol_class": ev["vol_class"],
        "true_range": ev["true_range"], "failed_spikes": ev["failed_spikes"],
        "failed_spike_dates": ", ".join(ev["failed_spike_dates"]) or None,
        "score_parts": format_score_parts(parts),
    }

    pos_txt = {"bottom": "바닥권(2년 고점 대비 {:.0%})", "mid": "중간 위치(2년 고점 대비 {:.0%})",
               "high": "2년 고점권(고점 대비 {:.0%})"}[ev["position"]].format(ev["dd_from_2y_high"])
    R = res.reasons
    R.append(f"✔ 장기 횡보 {ev['base_days']}일: 박스 {ev['box_bottom']:,.0f}~{top:,.0f} "
             f"(높이 {ev['box_height']:.0%}, 추세 {ev['base_drift']:+.0%}) · {pos_txt}")
    if np.isfinite(ev["ma120_drift"]):
        R.append(f"✔ {cfg.ma_len}일선 평탄 ({cfg.ma_lookback}일 변화 {ev['ma120_drift']:+.1%})")
    comp = _comp_of(ev)
    if np.isfinite(comp) and comp < 1:
        R.append(f"✔ 변동성 수축 (ATR% {ev['atr_compression']:.2f}·볼린저폭 {ev['bb_compression']:.2f}배, 1년 중앙값 대비)")
    if ev["limit_up"]:
        waived = not (ev["body"] >= cfg.min_body and ev["body_ratio"] >= cfg.min_body_ratio)
        candle = (f"상한가권(+{cfg.limit_up_chg:.0%}↑){' — 몸통 조건 면제' if waived else ''}, "
                  f"몸통 {ev['body']:+.1%}·몸통비율 {ev['body_ratio']:.2f}")
    else:
        candle = f"몸통 {ev['body']:+.1%}·몸통비율 {ev['body_ratio']:.2f}"
    R.append(f"✔ {ev['date']} 장대양봉 {ev['change']:+.1%} ({candle}, 종가 위치 {ev['close_pos']:.2f})")
    R.append(f"✔ 거래량 50일 평균 {ev['vol_mult_50d']:.1f}배 · 베이스 평균 {ev['vol_mult_base']:.1f}배 "
             f"(베이스 최대 거래량 경신)")
    big = (f" — {cfg.value_steps_eok[1]:,}억↑ 대형 수급 ({_SAMPLE} 60일 평균 +4~8%)"
           if ev["value_eok"] >= cfg.value_steps_eok[1] else "")
    R.append(f"✔ 거래대금 {ev['value_eok']:,.0f}억 (≥ {_min_value(ctx, cfg) / EOK:,.0f}억){big}")
    R.append(f"✔ 종가가 박스 상단 +{ev['close_above_top']:.1%}, 베이스 최고 종가 돌파")
    if ev["ath_breakout"]:
        R.append(f"✔ 가용 이력 최고가({ev['prior_high']:,.0f}) 위 종가 — 신고가 돌파 "
                 f"({_SAMPLE} 60일 중앙값 -2% vs 그 외 -12%)")
    if ev["ma_stacked"]:
        R.append(f"✔ 이동평균 정배열 (종가 > 50 > 150 > 200일선, {_SAMPLE} 60일 중앙값 -5% vs 그 외 -13%)")
    if weekly == "yes":
        R.append("✔ 돌파 주간 확인: 주간 종가가 피벗 위·그 주 고저폭 위쪽 절반에서 마감")
    if stop > pivot:
        R.append(f"✔ 손절 {stop:,.0f} 이 피벗 {pivot:,.0f} 위인 이유: 장대양봉 50%선 {mid:,.0f} 이 박스 상단보다 높아 "
                 f"'50% 룰'을 손절로 씀 (진짜 돌파라면 장대양봉 절반 위에서 지지되어야 함)")
    if len(legs) > 1:
        tail = ", ".join(f"{e['date']} {e['change']:+.1%}" for e in legs[1:])
        R.append(f"✔ 후속 장대양봉 {len(legs) - 1}개 ({tail}) — 같은 돌파의 연속 상승, 피벗·손절은 첫 돌파 기준")

    W = res.warnings
    if state == "failed":
        if c < mid:
            W.append(f"✘ 돌파 실패: 종가 {c:,.0f} < 장대양봉 50% {mid:,.0f} (50% 룰 이탈)")
        else:
            W.append(f"✘ 돌파 실패: 종가가 박스 상단 -{cfg.fail_pct:.0%} 아래로 복귀")
    elif state == "pullback":
        R.append(f"✔ 눌림목: 고점 대비 {c / peak - 1:.1%} 조정, 지지선 {support:,.0f} 부근, "
                 f"거래량 돌파일의 {recent_vol / A.v[bo]:.0%}로 감소")
    elif state == "retest":
        R.append(f"✔ 박스 상단 재시험: 종가 {c:,.0f} (피벗 대비 {c / top - 1:+.1%}), 장대양봉 50% {mid:,.0f} 위")
        W.append("✘ 종가가 피벗 아래 — 박스 상단 회복 확인 후 매수")
    elif state == "breakout":
        R.append(f"✔ 돌파 {days}봉 경과, 매수 한도 {limit:,.0f} 이내 (손절까지 위험 {risk:.1%})")
    elif state == "holding":
        R.append(f"✔ 돌파 후 {days}봉, 지지선 {support:,.0f} +{cfg.hold_band:.0%} 이내에서 지지 (재진입 관점)")
    elif days <= cfg.breakout_window:
        W.append(f"✘ 매수 한도 {limit:,.0f} 초과 (박스 상단 대비 {c / top - 1:+.0%}) — 추격 매수 주의, 눌림 대기")
    else:
        W.append(f"✘ 돌파 {days}봉 경과, 지지선 {support:,.0f} +{cfg.hold_band:.0%} 위 (박스 상단 대비 "
                 f"{c / top - 1:+.0%}) — 추격 매수 주의, 눌림 대기")
    if state != "failed" and not hold_mid:
        W.append("✘ 돌파 이후 한때 장대양봉 50% 아래 종가 기록")
    if (state != "failed" and days >= cfg.pullback_min_days and c <= peak * (1 - cfg.pullback_off_high)
            and not P["vol_dry"]):
        W.append(f"✘ 되밀림 중 거래량 감소 미흡 (최근 3일 돌파일의 {recent_vol / A.v[bo]:.0%}) — 매물 출회 가능성")
    if state != "failed" and np.isfinite(risk) and risk > cfg.max_entry_risk:
        W.append(f"✘ 현재가 기준 손절 위험 {risk:.0%} > {cfg.max_entry_risk:.0%}")
    if legs[-1]["i"] == last and ctx.partial:
        W.append("✘ 최근 장대양봉이 장중 미완성 봉 — 거래량·거래대금은 하루치 환산 추정치")
    W.extend(_evidence_warnings(ev_now, cfg))
    if not ev["top_confirmed"]:
        W.append("✘ 박스 상단이 베이스 앞부분(직전 추세 꼬리)에서만 형성 — 이후 상단 재시험 없음")
    if not ev["bottom_confirmed"]:
        W.append("✘ 박스 하단이 베이스 앞부분에서만 형성 — 박스 높이가 과대 표시될 수 있음")

    res.annotations = [
        box(A.idx[ev["base_start_i"]], A.idx[bo - 1], top, ev["box_bottom"],
            f"장기 박스 {ev['base_days']}일 (높이 {ev['box_height']:.0%})"),
        hline(pivot, "피벗(박스 상단)", "#2962ff"),
        hline(stop, "손절", "#d50000", "solid"),
        hline(mid, "장대양봉 50%", "#ff9800", "dotted"),
        marker(A.idx[bo], f"{ev['change']:+.1%} · {ev['vol_mult_50d']:.1f}x · {ev['value_eok']:,.0f}억",
               "below", "#e91e63", "arrowUp"),
    ]
    res.annotations += [marker(A.idx[e["i"]], f"후속 {e['change']:+.1%} · {e['value_eok']:,.0f}억", "below",
                               "#f48fb1", "circle") for e in legs[1:]]
    res.annotations += [marker(d, "실패 스파이크", "above", "#9e9e9e", "circle") for d in ev["failed_spike_dates"]]


# 경고 문구의 실증 수치: 2024-09~2026-10 워크포워드(유동성 종목, 다음날 시가 매수) 장기횡보 돌파 n≈508.
# 같은 표본에서 점수 규칙을 정했으므로 in-sample 통계다 (반올림).
_SAMPLE = "2024-26 표본"


def _evidence_warnings(ev: dict, cfg: LongBaseBreakoutConfig) -> list[str]:
    """돌파 맥락의 실증 위험 경고 (돌파 시점 지표 + 현재 주간 확인)."""
    W = []
    mid = ev["candle_mid"]
    if ev["limit_up"]:
        kind = "상한가 마감" if ev["close_pos"] > cfg.hot_close_pos else "상한가권"
        r60 = "-6%" if ev["close_pos"] > cfg.hot_close_pos else "-5%"
        W.append(f"✘ {kind} 장대양봉(+{ev['change']:.0%}): {_SAMPLE}(in-sample) 다음날 시가 매수 20일 평균 -4%·"
                 f"60일 {r60} (상한가권 아닌 돌파 0%·+3%) — 추격 금지, 50%선 {mid:,.0f} 눌림·지지 확인 권장")
    lo, hi = cfg.climax_vol
    vm = ev["vol_mult_50d"]
    if vm > hi:
        W.append(f"✘ 거래량 {vm:.0f}배 (50일 평균 {hi:g}배 초과, 클라이맥스): {_SAMPLE} 20일 평균 -4%·60일 -4% "
                 f"({lo:g}배 이하 +2%·+8%)")
    elif vm > lo:
        W.append(f"✘ 거래량 {vm:.0f}배 (50일 평균 {lo:g}~{hi:g}배, 과열): {_SAMPLE} 20일 평균 -2%·60일 -5% "
                 f"({lo:g}배 이하 +2%·+8%)")
    if ev["position"] == "bottom":
        W.append(f"✘ 바닥권 돌파: 상단에 장기 매물대(2년 고점 {ev['high_2y']:,.0f}) 존재 — {_SAMPLE} 20일 평균 -4%·"
                 f"60일 -6% (2년 고점권 +3%·+12%)")
    if ev["value_eok"] < cfg.value_steps_eok[0]:
        W.append(f"✘ 거래대금 {ev['value_eok']:,.0f}억 (< {cfg.value_steps_eok[0]:,}억): {_SAMPLE} 20일 평균 -4%·"
                 f"60일 -7% ({cfg.value_steps_eok[1]:,}억↑ 60일 +4~8%)")
    if not ev.get("ma_known", True):
        W.append("✘ 200일선 이력 부족 — 이동평균 정배열 판정 불가")
    elif not ev["ma_stacked"]:
        W.append(f"✘ 이동평균 정배열 아님 (종가 > 50 > 150 > 200일선 미충족): {_SAMPLE} 60일 중앙값 -13% (정배열 -5%)")
    wk = ev["weekly_confirm"]
    if wk == "no":
        W.append(f"✘ 돌파 주간 확인 실패 (주간 종가가 피벗 아래이거나 주간 고저폭 아래쪽 절반 마감): "
                 f"{_SAMPLE} 손절 도달 91% (확인된 주 64%)")
    elif wk == "pending":
        W.append(f"✘ 돌파 주 미완성 — 주간 종가가 피벗 위·주간 고저폭 위쪽 절반에서 마감하는지 확인 "
                 f"({_SAMPLE}: 확인 실패 주 손절 도달 91% vs 확인 주 64%)")
    if ev["true_range"] >= cfg.warn_true_range:
        W.append(f"✘ 베이스 실제 고저폭 {ev['true_range']:.0%} (5/95 백분위 박스 {ev['box_height']:.0%}): 박스가 급등락을 "
                 f"가림 — {_SAMPLE} 60% 이상 60일 평균 -6% (40% 미만 +5%)")
    if ev["failed_spikes"] >= 2:
        W.append(f"✘ 베이스 안 실패한 대량거래 스파이크 {ev['failed_spikes']}회 ({', '.join(ev['failed_spike_dates'])}): "
                 f"위쪽 매물 출회 흔적 — {_SAMPLE} 2회↑ 60일 평균 -6% (0~1회 +1%)")
    return W


def _fill_watch(ctx: StockContext, A: _A, cfg: LongBaseBreakoutConfig, S: _Scan, res: PatternResult) -> bool:
    """돌파 전 관찰: 전일에서 끝나는 유효 장기 베이스 + 오늘 종가 상단 근접 + 거래량 증가."""
    last = A.n - 1
    c = float(A.c[last])
    avg20 = float(ctx.value.iloc[-21:-1].mean()) if ctx.n > 21 else float("nan")
    if not avg20 >= cfg.watch_min_avg_value:
        res.metrics["watch_fail"] = (f"20일 평균 거래대금 {avg20 / EOK:,.0f}억 < {cfg.watch_min_avg_value / EOK:,.0f}억 "
                                     "— 300억 장대양봉이 비현실적인 규모")
        return False

    def extra(b: dict) -> list[str]:
        why = []
        if not c >= b["top"] * (1 - cfg.watch_pct):
            why.append(f"종가가 박스 상단 {b['top']:,.0f} 대비 {c / b['top'] - 1:+.0%} (상단과 거리 멂)")
        elif not c <= b["top"] * (1 + cfg.pre_above_max):
            why.append(f"종가가 박스 상단 위 {c / b['top'] - 1:+.0%} (돌파 조건 미충족 상태로 이탈)")
        if not b["max_close"] <= b["top"] * (1 + cfg.close_spike_tol):
            why.append("베이스 내 박스 상단을 크게 넘는 종가 존재")
        j = _prior_break(A, S.cidx, b["a"], b["e"], b["top"], cfg)
        if j is not None:
            why.append(f"베이스 안에 이미 박스 상단을 넘어 유지된 장대양봉({_date(A, j)}) 존재")
        return why

    b, why = _search_base(A, last - 1, cfg, extra, cfg.watch_min_base, strict_confirm=True)
    if b is None:
        res.metrics["watch_fail"] = "; ".join(why)[:120]
        return False
    st = _context_stats(A, b, cfg)
    if np.isfinite(st["ma120_drift"]) and abs(st["ma120_drift"]) > cfg.max_ma_drift:
        res.metrics["watch_fail"] = f"{cfg.ma_len}일선 변화 {st['ma120_drift']:+.0%}"
        return False
    va = A.vavg[max(0, last - 4)]
    ve5 = float(A.v[last - 4:last + 1].mean() / va) if va > 0 else float("nan")
    ve1 = float(A.v[last] / A.vavg[last]) if A.vavg[last] > 0 else float("nan")
    ud = _ud_ratio(A, last, cfg.ud_len)
    expanding = (ve5 >= cfg.vol_expand_5d) or (ve1 >= cfg.vol_expand_1d and A.chg[last] > 0)
    if not (expanding and ud >= cfg.ud_vol_min):
        res.metrics["watch_fail"] = (f"거래량 증가·매집 미흡 (5일 {ve5:.2f}배, 당일 {ve1:.2f}배, "
                                     f"상승/하락 거래량 {ud:.2f})")
        return False

    top, bot = b["top"], b["bottom"]
    dist = c / top - 1
    pivot = _tick_up(top)
    res.detected = True
    res.stage = NEAR_PIVOT if c >= top * (1 - cfg.near_pct) else FORMING
    res.pivot = pivot
    res.stop = _tick_down(top * (1 - cfg.stop_below_top))
    res.start_date = _date(A, b["a"])
    res.end_date = _date(A, last)
    comp = np.nanmean([st["atr_compression"], st["bb_compression"]]) \
        if np.isfinite([st["atr_compression"], st["bb_compression"]]).any() else float("nan")
    # 관찰 점수(상한 60): 베이스 25 + RS 10 + 상단 근접 10 + 거래량 증가 10 + 최근 거래대금 5
    val_eok = float(A.val[last] / EOK)
    prox = 10 * _clip01(1 - max(0.0, -dist) / cfg.watch_pct)
    vexp = 10 * _clip01((max(ve5, ve1 / 1.5) - 1.0) / 2.0)
    pval = 5 * _clip01(val_eok / (_min_value(ctx, cfg) / EOK))
    # 베이스 건전성 감점은 돌파 점수와 같은 규칙 (실제 고저폭 60%↑, 실패 스파이크 2회째부터)
    spikes = _failed_spikes(A, b, cfg, S.min_value)
    sanity = ((PTS_TRUE_RANGE if b["true_range"] >= cfg.warn_true_range else 0.0)
              + max(MAX_SPIKE_PENALTY, PTS_SPIKE * max(0, len(spikes) - 1)))
    res.score = min(cfg.pre_score_cap, _base_points(b["L"], b["height"], b["drift"], comp, cfg)
                    + _rs_points(ctx.rs_rating, cfg) + prox + vexp + pval) + sanity
    stacked, _ = _ma_stacked(A, last)
    res.metrics = {
        "base_days": int(b["L"]), "box_height": b["height"], "dist_to_pivot": dist, "vol_expand_5d": ve5,
        "vol_mult_50d": ve1, "value_eok": val_eok, "position": st["position"], "pre_breakout": True,
        "ud_vol_ratio": ud, "body": None, "close_pos": None, "vol_mult_base": None,
        "box_top": top, "box_bottom": bot, "base_drift": b["drift"], "ma120_drift": st["ma120_drift"],
        "breakout_date": None, "breakout_change": None, "days_since_breakout": None, "pullback": False,
        "post_state": "pre_breakout", "hold_above_mid": None, "range_pos": st["range_pos"],
        "dd_from_2y_high": st["dd_from_2y_high"], "atr_compression": st["atr_compression"],
        "bb_compression": st["bb_compression"], "support": pivot, "ma_stacked": bool(stacked),
        "ath_breakout": None, "weekly_confirm": None, "candle_class": None, "vol_class": None,
        "true_range": b["true_range"], "failed_spikes": len(spikes),
        "failed_spike_dates": ", ".join(_date(A, j) for j in spikes) or None,
    }
    pos = {"bottom": "바닥권", "mid": "중간 위치", "high": "2년 고점권"}[st["position"]]
    res.reasons += [
        f"✔ 장기 횡보 {b['L']}일: 박스 {bot:,.0f}~{top:,.0f} (높이 {b['height']:.0%}, 추세 {b['drift']:+.0%}) · {pos}",
        f"✔ 종가가 박스 상단 대비 {dist:+.1%} — 돌파 대기 (피벗 {pivot:,.0f})",
        f"✔ 거래량 증가 시작 (최근 5일 {ve5:.1f}배, 당일 {ve1:.1f}배 / 50일 평균, "
        f"{cfg.ud_len}일 상승/하락 거래량 {ud:.1f})",
    ]
    if np.isfinite(comp) and comp < 1:
        res.reasons.append(f"✔ 변동성 수축 (1년 중앙값 대비 {comp:.2f}배)")
    if stacked:
        res.reasons.append("✔ 이동평균 정배열 (종가 > 50 > 150 > 200일선)")
    W = res.warnings
    W.append(f"✘ 아직 돌파 전: 박스 상단 위 장대양봉(+{cfg.min_chg:.0%}↑, 거래량 "
             f"{cfg.min_vol_mult:.0f}배↑, 거래대금 {_min_value(ctx, cfg) / EOK:,.0f}억↑) 확인 필요")
    if ctx.partial:
        W.append("✘ 마지막 봉이 장중 미완성 — 거래량·거래대금은 하루치 환산 추정치")
    if st["position"] == "bottom":
        W.append(f"✘ 바닥권 박스: 상단에 장기 매물대(2년 고점 {st['high_2y']:,.0f}) 존재 — 돌파하더라도 "
                 f"{_SAMPLE} 바닥권 돌파 60일 평균 -6% (2년 고점권 +12%)")
    if b["true_range"] >= cfg.warn_true_range:
        W.append(f"✘ 베이스 실제 고저폭 {b['true_range']:.0%} (5/95 백분위 박스 {b['height']:.0%}): 박스가 급등락을 가림")
    if len(spikes) >= 2:
        W.append(f"✘ 베이스 안 실패한 대량거래 스파이크 {len(spikes)}회 "
                 f"({res.metrics['failed_spike_dates']}): 위쪽 매물 출회 흔적")
    res.annotations = [
        box(A.idx[b["a"]], A.idx[b["e"]], top, bot, f"장기 박스 {b['L']}일 (높이 {b['height']:.0%})"),
        hline(pivot, "피벗(박스 상단)", "#2962ff"),
        hline(res.stop, f"손절(상단 -{cfg.stop_below_top:.0%})", "#d50000", "solid"),
    ] + [marker(A.idx[j], "실패 스파이크", "above", "#9e9e9e", "circle") for j in spikes]
    return True


def _ud_ratio(A: _A, last: int, n: int) -> float:
    """최근 n봉 상승일 거래량 합 / 하락일 거래량 합 (하락일 없으면 큰 값)."""
    a = max(1, last - n + 1)
    ch = A.c[a:last + 1] - A.c[a - 1:last]
    v = A.v[a:last + 1]
    up, dn = float(v[ch > 0].sum()), float(v[ch < 0].sum())
    return up / dn if dn > 0 else (99.0 if up > 0 else 0.0)


def _explain_miss(A: _A, cfg: LongBaseBreakoutConfig, S: _Scan, start: int, res: PatternResult) -> None:
    """미탐지 사유: 최근 창의 가장 유력한 상승일(1차 조건 통과봉 우선)의 탈락 이유 + 현재 베이스 상태."""
    last = A.n - 1
    cands = S.between(start, last)
    with np.errstate(invalid="ignore"):
        big = np.flatnonzero(A.chg[start:last + 1] >= cfg.min_chg) + start
    if len(cands):
        i = int(cands[-1])
        _, why = S.eval(i)
        if why and not why[0].startswith(f"{cfg.ma_len}일선"):
            why = [f"직전 {cfg.min_base}일 이상 유효 베이스 없음: " + ", ".join(why)]
    elif len(big):
        i = int(big[-1])
        why = _candle_fail(A, i, cfg, S.min_value)
    else:
        i = None
    if i is not None:
        res.warnings.append(f"✘ 최근 {_date(A, i)} 상승일({A.chg[i]:+.1%})은 돌파 조건 미충족: " + "; ".join(why))
    else:
        res.warnings.append(f"✘ 최근 {cfg.recent_window}봉 내 +{cfg.min_chg:.0%} 이상 장대양봉 없음")
    wf = res.metrics.get("watch_fail")
    if wf:
        res.warnings.append(f"✘ 현재 돌파 대기 베이스 아님: {wf}")
    res.metrics.setdefault("pre_breakout", False)


def _common_warnings(ctx: StockContext, A: _A, cfg: LongBaseBreakoutConfig, res: PatternResult) -> None:
    if not res.detected:
        return
    # 거래정지일: 패턴 시작 ~ 마지막 봉 사이만 (df.attrs 는 잘라낸 df 에도 전체 이력이 남아 있으므로 상한 필수)
    halts = ctx.df.attrs.get("halt_dates") or []
    if halts and res.start_date:
        last_d = _date(A, A.n - 1)
        inside = [str(d)[:10] for d in halts if res.start_date <= str(d)[:10] <= last_d]
        if inside:
            res.warnings.append(f"✘ 패턴 구간 내 거래정지일 {len(inside)}일 ({inside[-1]} 등) — 갭·거래량 왜곡 가능")
    # 거래량은 수정되지 않으므로 액면분할·병합이 베이스 안에 있으면 거래량 배수가 왜곡된다
    try:
        a = A.idx.get_loc(pd.Timestamp(res.start_date))
    except (KeyError, TypeError, ValueError):
        a = None
    if isinstance(a, (int, np.integer)):
        e = A.idx.get_loc(pd.Timestamp(res.breakout_date)) - 1 if res.breakout_date else A.n - 1
        seg = A.v[a:e + 1]
        if len(seg) >= 60:
            k = len(seg) // 3
            m1, m3 = float(np.median(seg[:k])), float(np.median(seg[-k:]))
            if m1 > 0 and m3 > 0 and (m3 / m1 > 5 or m1 / m3 > 5):
                res.warnings.append(f"✘ 베이스 앞·뒤 거래량 수준 {m3 / m1:.1f}배 차이 — 액면분할/병합 시 거래량 배수 왜곡 가능")
    ms = ctx.market_state
    if ms is not None and getattr(ms, "state", None) == CORRECTION:
        res.warnings.append(f"✘ 시장 조정 국면({getattr(ms, 'label', '조정')}) — 돌파 실패 확률 높음")
