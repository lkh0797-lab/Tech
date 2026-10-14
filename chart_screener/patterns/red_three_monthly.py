"""월봉 적삼병 (red_three_monthly) — 일봉 EOD 를 달력 월봉으로 묶어 '바닥권 확정 저점 뒤 첫 3연속 양봉'을 찾는다.

스펙  docs/2026-10-14-chart-techniques-design.md §1 (영상 [04:00–14:00])
부록  docs/2026-10-14-chart-techniques-addendum.md §2 (파라미터 · 출처 · 알고리즘 — 스펙의 '구현 선택'보다 우선) · §13 테스트
규칙마다 출처(영상 [mm:ss] · URL · '구현 선택: 이유')는 RTM_ORIGIN — 결과 metrics['origin'] 으로 리포트에 간다.

규칙 (부록 §2.3 순서)
  1. 거래량 0 행 제외 → 달력 월봉(monthly() = tq.monthly_bars, 거래량 = 합). 완성 월 = 뒤 달 봉이 있는 달 — 월말 마지막
     거래일 EOD 에도 그 달은 미완성이고 다음 달 첫 봉에 확정(하루 늦지만 앞부분 불변). 'calendar' 옵션은 krx 휴장일 표로
     당일 확정(tq.monthly_bars(complete_rule='calendar') 그대로).
  2. 양봉 C > O 엄격(도지 · 보합은 연속을 끊음). 병정 3개(RTM_N) · 종가 상승 C[k] > C[k−1](RTM_REQUIRE_HIGHER_CLOSE).
  3. 확정 저점 m: L[m] < L[m−1] 이고 L[m] < L[m+1], m+1 이 완성 월 [08:00–09:00]. 첫 병정은 m 뒤(RTM_LOW_MONTH_AS_FIRST
     False), 셋째 ≤ m + 6 (RTM_MAX_LAG). 그 뒤 새 저가 없음. 저점 뒤 첫 3연속 양봉만 — 4번째 연속 양봉 달은 새 신호 아님.
     후보 여럿이면 가장 낮은 저가(같으면 이른 달). 거래 없는 달(장기 정지, gap_before)을 건너서는 판정하지 않는다.
  4. 바닥권: 저점 ≤ 직전 완성 월 12개 최고 종가 × (1 − 0.20). 12개월이 없으면 '바닥권 모름' — 신호 없음(이유만 보임).
  5. 신호 = 셋째 양봉 월이 가장 최근 완성 월(다음 달 내내 유지). 영상 가설 '다음 달도 양봉'은 신호가 아니라
     '이번 달 진행 · 미완성' 관찰(metrics.month_now). 키움 '3봉 연속 양봉' 0봉전 · 1봉전 대조는 metrics.hts.
  6. 스팩 · ETF · 리츠 제외 [11:00] — 종목 목록이 이미 빼지만 이름으로 한 번 더 거른다.

단계 (base 공통 단계에 맞춘 구현 선택)
  형성 중   병정 2개 완성 · 이번 달 진행이 아직 양봉 · 종가 상승 아님     pivot = 셋째 조건가 max(이번 달 시가, 지난달 종가)
  피벗 근접 병정 2개 완성 + 이번 달 진행이 지금까지 양봉 · 종가 상승 — 잠정 셋째(키움 0봉전 꼴), 신호 아님
  돌파      신호 · 이번 달 종가 ≤ 기준가 × 1.05                              pivot = 셋째 양봉 종가(기준가)
  이격 과다 신호 · 이번 달 종가 > 기준가 × 1.05 (Tech 공통 매수 범위 — base.classify_stage 기본값)
  돌파 실패 신호 · 이번 달 저가 ≤ 확정 저점(구조 무효) 또는 종가 < 셋째 양봉 시가(몸통 반납)
  그 밖(지난 신호 뒤 연속 양봉 · 바닥권 모름 · 바닥권 아님 · 아님)은 탐지하지 않고 이유를 warnings 에 남긴다.
  형성 중은 시장 전체가 급락 뒤 반등한 달에 아주 많아질 수 있다(2026-10-13 캐시 2,419종목 중 427) — detect_forming=False 로 끈다.
  stop = 없음 — 영상 · 스펙 · 부록이 손절을 정하지 않았다. 확정 저점은 구조 무효선(metrics.invalid_below)으로만 보인다.

점수 (구현 선택 — 성공 확률 아님): 단계 기본(신호 50 · 피벗 근접 40 · 형성 중 30) + 꼬리표 5개 × 10 —
  짧은 위꼬리 · 저가 상승 · 어드밴스 블록 아님(부록 §2.2) · 키 큰 몸통(§2.1 Morris · Bulkowski) · 연중 하단 ⅓(§2.2).
  이력이 모자라 모르는 꼬리표는 0점이고 metrics.score_unknown 에 적는다.

장중(ctx.partial): 오늘 미완성 봉은 판정에 쓰지 않는다(tq.eod_frame). 오늘이 새 달 첫 거래일이면 지난달을 완성 월로 본
판정을 '장중 잠정' 라벨로 metrics.provisional 에 따로 둔다(오늘 봉 값은 안 씀). 같은 달이면 이번 달 진행 등락의
장중 값만 '장중 잠정'으로 덧붙인다. 예외 — 신호 뒤 '이번 달 저가 ≤ 확정 저점'은 저가 규칙이라 오늘 장중 저가가 이미 닿았으면
마감 뒤에도 같으므로 단계를 돌파 실패로 둔다(metrics.intraday_final '장중 확정(저가)').

일지 rule = 'red3m_v1' (metrics.rule_version — journal.rule_of). 규칙을 바꾸면 v 를 올린다.
지수: tq.market_context(index_df, red3=judge_monthly) — 지수 월봉 적삼병 칸(같은 1~12단계, 제외 대상 없음).
재현: signals(df) — 과거 신호 월 목록(known_date = 신호가 처음 보이는 봉) — 체크리스트 4번 · 기록 채점용.
불코우스키 적삼병 통계는 미국 일봉 표본이다 — metrics.bulkowski_note 의 '참고' 줄로만, 확률로 쓰지 않는다.
"""
from __future__ import annotations

import inspect
import math
import re
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .. import techniques as tq
from .base import (BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, STAGE_LABELS, PatternResult, StockContext, box,
                   classify_stage, hline, marker, register, segment)

NAME = "red_three_monthly"
LABEL = tq.PATTERN_LABELS[NAME]            # '월봉 적삼병'
RULE_ID = tq.RULE_IDS[NAME]                # 'red3m_v1'
_BUY_RANGE = inspect.signature(classify_stage).parameters["buy_range"].default


@dataclass
class RedThreeConfig:
    """부록 §2.2 상수(RTM_*) + 단계 · 관찰 창(구현 선택)."""
    n: int = 3                          # RTM_N
    require_higher_close: bool = True   # RTM_REQUIRE_HIGHER_CLOSE
    bottom_dd: float = 0.20             # RTM_BOTTOM_DD
    bottom_lookback: int = 12           # RTM_BOTTOM_LOOKBACK (저점 월 제외 직전 완성 월 수)
    max_lag: int = 6                    # RTM_MAX_LAG (셋째 ≤ 저점 월 + 6)
    low_month_as_first: bool = False    # RTM_LOW_MONTH_AS_FIRST
    drop_zero_volume: bool = True       # RTM_DROP_ZERO_VOLUME
    complete_rule: str = "next_bar"     # 'calendar' = 기간 마지막 KRX 거래일 봉이면 당일 완성 (구현 선택 옵션)
    short_upper_k: float = 0.1          # RTM_FLAG_SHORT_UPPER (TA-Lib ShadowVeryShort)
    range_n: int = 10                   # 평균 범위 · 몸통 창 (TA-Lib 기본 10)
    adv_far: float = 0.6                # RTM_FLAG_ADV_BLOCK (TA-Lib Far)
    adv_n: int = 5
    yearly_n: int = 12                  # RTM_YEARLY_POS
    yearly_low: float = 1 / 3
    buy_range: float = _BUY_RANGE       # 이격 과다 문턱 (Tech 공통)
    fail_below_body: bool = True        # 이번 달 종가 < 셋째 양봉 시가 → 돌파 실패 (구현 선택)
    after_lookback: int = 12            # 지난 신호 뒤 연속 양봉 관찰 창 (구현 선택)
    detect_forming: bool = True         # False 면 '병정 2개 · 셋째 대기'(형성 중)를 탐지로 세지 않고 이유만 남긴다


# ---------------------------------------------------------------- 출처
_HK = "https://dic.hankyung.com/economy/view/?seq=5747"
_BK = "https://thepatternsite.com/ThreeWhiteSoldiers.html"
_TALIB = "https://github.com/TA-Lib/ta-lib"
_KIWOOM = "https://download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf"
RTM_ORIGIN: dict[str, str] = {
    "monthly": tq.ORIGIN["monthly"],
    "halt_rows": tq.ORIGIN["halt_rows"],
    "volume": tq.ORIGIN["period_volume"] + " — 화면은 월 거래량 '합'",
    "white": tq.ORIGIN["white"],
    "n3": f"석 달 연속 양봉 — 한경 경제용어사전 ({_HK}) · " + tq.video("04:00–14:00"),
    "higher_close": (f"종가 상승 C[k] > C[k−1] — Bulkowski ({_BK}) · TA-Lib ta_CDL3WHITESOLDIERS.c ({_TALIB}) · "
                     "미래에셋 HTS 0544 (https://securities.miraeasset.com/kairos/0544.htm) · 삼성증권 POP 1512 "
                     "(http://www.samsungpop.com/contents/poptrading/help/1512.html) · 野村 赤三兵 "
                     "(https://www.nomura.co.jp/terms/japan/a/akasanpei.html) — 한경은 요구 안 함 (RTM_REQUIRE_HIGHER_CLOSE)"),
    "low_confirm": (tq.video("08:00–09:00") + " 월봉 m 저가 < 왼쪽 · 오른쪽 월 저가 (영상 정의 그대로) — "
                    "m+1 이 완성 월이어야 확정 (같은 저가는 저점 아님)"),
    "after_low": tq.choice("첫 병정은 확정 저점 '뒤' (스펙 문장) — 저점 월은 첫 병정 아님 (RTM_LOW_MONTH_AS_FIRST, 출처 없음)"),
    "max_lag": tq.choice("셋째 양봉 ≤ 저점 월 + 6 — 저점 뒤 음봉 1~3개월을 거친 적삼병까지 허용하는 상한 (RTM_MAX_LAG)"),
    "no_new_low": "스펙 §1 '그 사이 확정 저점 아래로 새 저가 없음' · 부록 §2.3 7",
    "first_run": "부록 §2.3 8 — 저점 뒤 첫 3연속 양봉만 신호, 4번째 연속 양봉 달은 새 신호 아님",
    "pick_low": tq.choice("후보 저점 여럿이면 가장 낮은 달, 같으면 이른 달 (부록 §2.3 9)"),
    "gap": tq.choice("거래 없는 달(장기 정지)을 건너서는 연속 · 저점 판정 안 함 (부록 §2.3 4)"),
    "bottom": (tq.video("04:00–05:00") + " '하락이 지속된 바닥권' · 저점 ≤ 직전 완성 월 12개 최고 종가 × 0.8 — "
               "약세장 −20% 관례 (https://www.fool.com/investing/how-to-invest/bear-market.aspx), 캔들 문헌 규칙 아님"),
    "bottom_unknown": "부록 §2.3 10 — 저점 앞 완성 월 12개가 없으면 '바닥권 모름', 신호 안 냄",
    "signal_hold": "부록 §2.3 11 — 셋째 양봉 월이 가장 최근 완성 월인 동안(다음 달 내내) 신호 유지",
    "next_month": "스펙 §1 — 영상 가설 '다음 달도 양봉'은 신호가 아니라 이번 달 진행 · 미완성 관찰",
    "exclude": tq.video("11:00") + " 스팩 · ETF · 리츠 제외",
    "hts": (f"키움 도움말 p.3 — 진행 중 봉은 현재가가 종가, 맨 오른쪽 = 0봉전 ({_KIWOOM}) · "
            "우리 규칙 = 1봉전 + 확정 저점 · 바닥권 · 종가 상승"),
    "flag_short_upper": (f"짧은 위꼬리 (H − C) < 0.1 × 직전 완성 월 10개 평균 (H − L) — TA-Lib ShadowVeryShort ({_TALIB}) · "
                         f"Bulkowski ({_BK})"),
    "flag_adv_block": ("셋째 몸통 < 둘째 몸통 − 0.6 × 직전 5개월 평균 (H − L) 또는 셋째 위꼬리 ≥ 몸통 — TA-Lib Far · "
                       f"키움 어드밴스 블록 · 정체 (도움말 p.39 {_KIWOOM}) · iFinance 先詰まり · 思案星"),
    "flag_rising_lows": ("병정 모두 L[k] > L[k−1] — iFinance 赤三兵 (https://www.ifinance.ne.jp/learn/technical/twd068.html) · "
                         "미래에셋 · 키움"),
    "flag_tall_body": (f"몸통 ≥ 직전 완성 월 10개 평균 몸통 — TA-Lib BodyLong 기본값 ({_TALIB}) · Morris · Bulkowski 키 큰 흰 봉 "
                       "(Nison 은 요구 안 함 — 점수만, 판정 아님)"),
    "yearly_pos": ("연중 위치 (C − 12개월 최저가)/(최고가 − 최저가), ⅓ 이하 = 연중 하단 ⅓ — Bulkowski glossary · "
                   "buylow (https://thepatternsite.com/buylow.html)"),
    "stage": tq.choice("단계 — 병정 2개 = 형성 중, + 이번 달 진행 양봉 = 피벗 근접(잠정), 신호 = 돌파 (base 공통 단계에 맞춤)"),
    "pivot": tq.choice("기준가 = 셋째 양봉 종가 (적삼병엔 돌파 피벗이 없다 — 신호 월 마지막 거래일 종가에 완성) · "
                       "신호 전은 셋째 조건가 max(이번 달 시가, 지난달 종가)"),
    "buy_range": f"이격 과다 = 기준가 × {1 + _BUY_RANGE:g} 넘음 — Tech 공통 매수 범위 (base.classify_stage 기본값)",
    "fail": tq.choice("돌파 실패 = 이번 달 저가 ≤ 확정 저점(구조 무효) 또는 이번 달 종가 < 셋째 양봉 시가(몸통 반납)"),
    "stop": "손절 규칙 없음 — 영상 · 스펙 · 부록이 정하지 않음. 확정 저점은 구조 무효선일 뿐 손절 권고 아님",
    "score": tq.choice("점수 = 단계 기본(신호 50 · 피벗 근접 40 · 형성 중 30) + 꼬리표 5개 × 10 — 성공 확률 아님"),
    "after_lookback": tq.choice("지난 신호 뒤 연속 양봉은 12개월 안 신호만 관찰 표시"),
    "intraday_final": tq.choice("장중 확정(저가) — 신호 뒤 '이번 달 저가 ≤ 확정 저점'은 저가 규칙이라 오늘 장중 저가가 이미 닿았으면 "
                                "마감 뒤 판정도 같다(저가는 내려가기만) → 단계 = 돌파 실패. 종가 규칙(몸통 반납)은 마감 뒤에"),
}
BULKOWSKI = tq.bulkowski_note("three_white_soldiers") + " — 일봉 적삼병 통계, 월봉 아님"
STOP_NOTE = "손절 규칙 없음 — 영상 · 부록이 정하지 않음. 확정 저점(월 저가)은 구조 무효선일 뿐 — Tech 매수 계획(권장 수량)은 내지 않음"
PARTIAL_NOTE = "장중 — 오늘 미완성 봉은 판정에 쓰지 않음 (EOD 완성 봉만 · 장 마감 뒤 다시 판정)"

STATE_LABELS = {
    "signal": "적삼병 신호",
    "pending": "셋째 병정 진행 중 (잠정)",
    "forming": "병정 2개 완성 · 셋째 대기",
    "after_signal": "적삼병 이후 연속 양봉 (새 신호 아님)",
    "bottom_unknown": "바닥권 모름 (관찰만)",
    "not_bottom": "바닥권 아님",
    "none": "적삼병 아님",
    "too_short": "월봉 이력 부족",
    "empty": "자료 없음",
    "excluded": "제외 대상 (스팩 · ETF · 리츠)",
}
SCORE_BASE = {"signal": 50.0, "pending": 40.0, "forming": 30.0}
SCORE_TAG = 10.0
_TAGS = (("short_upper", "짧은 위꼬리"), ("rising_lows", "저가 상승"), ("no_adv_block", "어드밴스 블록 아님"),
         ("tall_body", "키 큰 몸통"), ("yearly_low_third", "연중 하단 ⅓"))
# 종목 목록(data/universe.py)이 이미 빼는 규칙 + ETF · ETN 상표 — 이름으로 한 번 더 거른다
_EXCLUDE_RE = re.compile(r"스팩|\d+호$|리츠|리얼티\d*$|REIT|ETF|ETN|^(KODEX|TIGER|KBSTAR|RISE|ARIRANG|HANARO|KOSEF|ACE|"
                         r"SOL|PLUS|TIMEFOLIO|KoAct|TREX|WOORI|BNK|FOCUS|UNICORN|마이티|히어로즈|에셋플러스|TRUSTON|"
                         r"VITA|1Q|HK|IBK|DAISHIN343|KIWOOM)\s")

_EPS = 1e-9


def _tol(b: float) -> float:
    return _EPS * max(1.0, abs(b))


def _gt(a, b) -> bool:
    return bool(a > b + _tol(b))


def _lt(a, b) -> bool:
    return bool(a < b - _tol(b))


def _ge(a, b) -> bool:
    return bool(a >= b - _tol(b))


def _le(a, b) -> bool:
    return bool(a <= b + _tol(b))


def _ds(ts) -> str | None:
    return None if ts is None or (isinstance(ts, float) and math.isnan(ts)) else f"{pd.Timestamp(ts):%Y-%m-%d}"


def _px(x) -> str:
    if x is None or not math.isfinite(x):
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}"


def _yn(v) -> str:
    return "모름" if v is None else ("예" if v else "아니오")


# ---------------------------------------------------------------- 월봉 배열
class _Mon:
    """완성 월봉 배열(0..n−1) + 진행 중 달 cur (없으면 None — 'calendar' 규칙으로 마지막 달이 완성된 경우)."""

    _ARR = ("per", "O", "H", "L", "C", "V", "gap", "first", "last", "bull")

    def __init__(self, mb: pd.DataFrame | None = None):
        self.cur = None
        if mb is None or len(mb) == 0:
            self.per, self.first, self.last = [], [], []
            self.O = self.H = self.L = self.C = self.V = np.zeros(0)
            self.gap = self.bull = np.zeros(0, dtype=bool)
            self.n = 0
            return
        comp = mb["complete"].to_numpy(dtype=bool)
        if not comp[-1]:
            row = mb.iloc[-1]
            o, c = float(row["open"]), float(row["close"])
            self.cur = {"month": str(mb.index[-1]), "open": o, "high": float(row["high"]), "low": float(row["low"]),
                        "close": c, "volume": float(row["volume"]), "days": int(row["days"]),
                        "first": _ds(row["first"]), "last": _ds(row["last"]), "gap_before": bool(row["gap_before"]),
                        "bull": _gt(c, o)}
        done = mb[comp]
        self.per = [str(p) for p in done.index]
        self.O, self.H, self.L, self.C, self.V = (done[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "volume"))
        self.gap = done["gap_before"].to_numpy(dtype=bool)
        self.first = [_ds(x) for x in done["first"]]
        self.last = [_ds(x) for x in done["last"]]
        self.bull = self.C > self.O + _EPS * np.maximum(1.0, np.abs(self.O))      # _gt 와 같은 엄격 비교
        self.n = len(self.per)

    def upto(self, j: int) -> "_Mon":
        """완성 월 0..j 만 (진행 월 없음) — 지난 시점 판정용, 미래 월을 볼 수 없다."""
        a = _Mon.__new__(_Mon)
        for k in self._ARR:
            setattr(a, k, getattr(self, k)[:j + 1])
        a.cur = None
        a.n = len(a.per)
        return a

    def row(self, k: int) -> dict:
        o, c = float(self.O[k]), float(self.C[k])
        return {"month": self.per[k], "open": o, "high": float(self.H[k]), "low": float(self.L[k]), "close": c,
                "volume": float(self.V[k]), "chg": c / o - 1 if o else None, "first": self.first[k], "last": self.last[k]}


# ---------------------------------------------------------------- 판정 단계
def _run_why(A: _Mon, s: int, e: int, cfg: RedThreeConfig) -> str | None:
    """완성 월 s..e 가 병정 런인지 — 아니면 이유."""
    for k in range(s, e + 1):
        if not A.bull[k]:
            kind = "보합(도지)" if abs(A.C[k] - A.O[k]) <= _tol(A.O[k]) else "음봉"
            return f"{A.per[k]} {kind} — 시가 {_px(A.O[k])} · 종가 {_px(A.C[k])} (양봉은 종가 > 시가 엄격)"
    for k in range(s + 1, e + 1):
        if A.gap[k]:
            return f"{A.per[k]} 앞에 거래 없는 달 — 건너서 연속 판정 안 함"
        if cfg.require_higher_close and not _gt(A.C[k], A.C[k - 1]):
            return (f"{A.per[k]} 종가 {_px(A.C[k])} ≤ 전월 종가 {_px(A.C[k - 1])} — 종가 상승 조건 탈락 "
                    f"(양봉이어도 월 경계 갭 하락)")
    return None


def _lows(A: _Mon, s: int, e: int, cfg: RedThreeConfig, cur_low: float | None = None) -> tuple[list[int], list[tuple[int, str]]]:
    """첫 병정 s · 마지막 완성 월 e 에 대한 확정 저점 후보와 탈락 이유. cur_low = 진행 월 저가(셋째 대기 단계만)."""
    N = cfg.n
    m_lo = max(1, s + N - 1 - cfg.max_lag)             # 셋째(s+N−1) ≤ m + max_lag
    m_hi = s if cfg.low_month_as_first else s - 1
    ok, rej = [], []
    L = A.L
    for m in range(m_lo, m_hi + 1):
        if m + 1 > e:
            continue
        if not (_lt(L[m], L[m - 1]) and _lt(L[m], L[m + 1])):
            continue
        if A.gap[m] or A.gap[m + 1:e + 1].any():
            rej.append((m, f"{A.per[m]} 저점 — 사이에 거래 없는 달이 있어 판정 안 함"))
            continue
        lo_after = float(L[m + 1:e + 1].min())
        if not _gt(lo_after, L[m]):
            rej.append((m, f"{A.per[m]} 저점 {_px(L[m])} — 그 뒤 새 저가 {_px(lo_after)}"))
            continue
        if cur_low is not None and not _gt(cur_low, L[m]):
            rej.append((m, f"{A.per[m]} 저점 {_px(L[m])} — 이번 달(진행) 저가 {_px(cur_low)} 가 아래"))
            continue
        k0 = m if cfg.low_month_as_first else m + 1          # 저점 월도 병정이면 그 런부터 센다
        k_run = next((k for k in range(k0, s) if k + N - 1 <= e and A.bull[k:k + N].all()), None)
        if k_run is not None:
            rej.append((m, f"{A.per[m]} 저점 뒤 {A.per[k_run]}~{A.per[k_run + N - 1]} 에 이미 {N}연속 양봉 — "
                           f"첫 런만 신호 (4번째 연속 양봉 달은 새 신호 아님)"))
            continue
        ok.append(m)
    return ok, rej


def _bottom(A: _Mon, m: int, cfg: RedThreeConfig) -> dict:
    lb = cfg.bottom_lookback
    out = {"status": "unknown", "ref_close": None, "dd": None, "need": cfg.bottom_dd, "lookback": lb, "months_before": int(m)}
    if m < lb:
        return out
    ref = float(A.C[m - lb:m].max())
    out.update(ref_close=ref, dd=float(1 - A.L[m] / ref) if ref > 0 else None,
               status="ok" if _le(A.L[m], (1 - cfg.bottom_dd) * ref) else "fail")
    return out


def _attempt(A: _Mon, s: int, e: int, cfg: RedThreeConfig, cur_low: float | None = None) -> dict:
    """병정 런 s..e(완성 월)와 확정 저점 · 바닥권 판정. 반환 {'ok', 'step', 'why', 'm', 'bottom'}."""
    if s < 1 or e >= A.n or s > e:
        return {"ok": False, "step": "short", "why": f"완성 월봉 {A.n}개 — 저점 확인과 병정에 모자람"}
    why = _run_why(A, s, e, cfg)
    if why:
        return {"ok": False, "step": "run", "why": why}
    ok, rej = _lows(A, s, e, cfg, cur_low)
    if not ok:
        if rej:
            why = min(rej, key=lambda x: (A.L[x[0]], x[0]))[1]
        else:
            m_lo = max(1, s + cfg.n - 1 - cfg.max_lag)
            why = (f"첫 병정 {A.per[s]} 앞 {A.per[m_lo]}~{A.per[s - 1]} 에 확정 저점(좌우 월 저가보다 낮은 달) 없음 — "
                   f"셋째 양봉 ≤ 저점 + {cfg.max_lag}개월")
        return {"ok": False, "step": "low", "why": why}
    m = min(ok, key=lambda k: (A.L[k], k))
    bot = _bottom(A, m, cfg)
    res = {"ok": bot["status"] == "ok", "step": None if bot["status"] == "ok" else "bottom", "why": None, "m": int(m),
           "bottom": bot, "candidates": [A.per[k] for k in ok]}
    if bot["status"] == "unknown":
        res["why"] = (f"바닥권 모름 — 저점 {A.per[m]} 앞 완성 월 {m}개 (12개 필요) · 신호 안 냄")
    elif bot["status"] == "fail":
        res["why"] = (f"바닥권 아님 — 저점 {_px(A.L[m])} 이 직전 12개월 최고 종가 {_px(bot['ref_close'])} 대비 "
                      f"−{bot['dd'] * 100:.1f}% (기준 −{cfg.bottom_dd * 100:.0f}% 이하)")
    return res


def _flags(A: _Mon, ks: list[int], e: int, cfg: RedThreeConfig) -> dict:
    """부록 §2.2 관찰 꼬리표 + 몸통 크기 — 판정에 쓰지 않는다. 이력이 모자라면 None(모름)."""
    rng = A.H - A.L
    body = np.abs(A.C - A.O)

    def prior(x, k, n):
        return float(x[k - n:k].mean()) if k >= n else None

    def every(xs):
        if any(x is False for x in xs):
            return False
        return None if any(x is None for x in xs) else True

    su, tall = [], []
    for k in ks:
        ar, ab = prior(rng, k, cfg.range_n), prior(body, k, cfg.range_n)
        su.append(None if ar is None else _lt(A.H[k] - A.C[k], cfg.short_upper_k * ar))
        tall.append(None if ab is None else _ge(body[k], ab))
    rising = every([None if k < 1 else _gt(A.L[k], A.L[k - 1]) for k in ks])
    adv = None
    if len(ks) >= 3:
        k2, k3 = ks[-2], ks[-1]
        a5 = prior(rng, k3, cfg.adv_n)
        shrink = None if a5 is None else _lt(body[k3], body[k2] - cfg.adv_far * a5)
        stall = _ge(A.H[k3] - A.C[k3], body[k3])
        adv = True if (shrink or stall) else (None if shrink is None else False)
    pos = None
    yn = cfg.yearly_n
    if e + 1 >= yn:
        lo, hi = float(A.L[e - yn + 1:e + 1].min()), float(A.H[e - yn + 1:e + 1].max())
        pos = (float(A.C[e]) - lo) / (hi - lo) if hi > lo else None
    return {"short_upper": every(su), "rising_lows": rising, "adv_block": adv, "tall_body": every(tall),
            "yearly_pos": pos, "yearly_low_third": None if pos is None else _le(pos, cfg.yearly_low),
            "per_month": {"short_upper": su, "tall_body": tall}}


def _score(state: str, f: dict) -> tuple[float, dict, list[str]]:
    vals = {"short_upper": f["short_upper"], "rising_lows": f["rising_lows"],
            "no_adv_block": None if f["adv_block"] is None else not f["adv_block"],
            "tall_body": f["tall_body"], "yearly_low_third": f["yearly_low_third"]}
    parts = {"base": SCORE_BASE[state]}
    for k, _ in _TAGS:
        parts[k] = SCORE_TAG if vals[k] else 0.0
    unknown = [k for k, _ in _TAGS if vals[k] is None]
    return float(min(100.0, sum(parts.values()))), parts, unknown


def _after_signal(A: _Mon, cfg: RedThreeConfig) -> dict | None:
    """최근 after_lookback 개월 안 지난 신호 — 그 뒤 연속 양봉 수 (그 시점까지 완성 월만으로 판정)."""
    e, N = A.n - 1, cfg.n
    for j in range(e - 1, max(N, e - cfg.after_lookback) - 1, -1):
        att = _attempt(A.upto(j), j - N + 1, j, cfg)
        if not att["ok"]:
            continue
        m = att["m"]
        run = 0
        for k in range(j + 1, e + 1):
            if not A.bull[k] or A.gap[k]:
                break
            run += 1
        lows = list(A.L[m + 1:e + 1]) + ([A.cur["low"]] if A.cur else [])
        return {"signal_month": A.per[j], "months_ago": int(e - j), "run_after": int(run), "continuing": run == e - j,
                "total_run": int(N + run) if run == e - j else None, "low_month": A.per[m], "low": float(A.L[m]),
                "pivot": float(A.C[j]), "intact": _gt(min(lows), A.L[m]) if lows else True}
    return None


def _month_now(A: _Mon) -> dict | None:
    cur = A.cur
    if cur is None:
        return None
    d = dict(cur)
    d["chg"] = cur["close"] / cur["open"] - 1 if cur["open"] else None
    d["vs_prev_close"] = cur["close"] / float(A.C[-1]) - 1 if A.n and A.C[-1] else None
    d["label"] = "이번 달 진행 · 미완성"
    return d


def _hts(A: _Mon, cfg: RedThreeConfig) -> dict:
    """키움 '캔들연속발생 [월] 3봉 연속 양봉' — 0봉전은 진행 중 달 포함, 1봉전 = 완성 월만(우리 신호의 런 조건)."""
    N = cfg.n
    one = bool(A.n >= N and A.bull[A.n - N:].all())
    zero = None
    if A.cur is not None:
        zero = bool(A.n >= N - 1 and A.bull[A.n - (N - 1):].all() and A.cur["bull"])
    return {"0봉전": zero, "1봉전": one, "origin": RTM_ORIGIN["hts"]}


def judge_monthly(mb: pd.DataFrame, cfg: RedThreeConfig | None = None) -> dict:
    """월봉(tq.monthly_bars 결과 — complete · gap_before 열)으로 적삼병 판정. 완성 월만 신호에 쓰고 진행 월은 관찰 ·
    잠정 단계에만. tq.market_context(red3=judge_monthly) 의 지수 칸에도 그대로 쓴다. 결과는 JSON 으로 바로 쓸 수 있다."""
    cfg = cfg or RedThreeConfig()
    A = _Mon(mb)
    N = cfg.n
    out: dict = {"detected": False, "state": "empty", "state_label": None, "stage": None, "rule_version": RULE_ID,
                 "months": int(A.n), "last_month": A.per[-1] if A.n else None, "month_now": _month_now(A),
                 "hts": _hts(A, cfg), "pivot": None, "why": [], "after_signal": None}

    def done(state: str) -> dict:
        out["state"] = state
        out["state_label"] = STATE_LABELS[state]
        return out

    if A.n == 0:
        out["why"].append("완성 월봉 없음")
        return done("empty")
    if A.n < N + 1:
        out["why"].append(f"완성 월봉 {A.n}개 — 확정 저점과 병정을 보려면 더 필요")
        return done("too_short")
    e = A.n - 1
    sig = _attempt(A, e - N + 1, e, cfg)
    if sig["ok"]:
        _fill(out, A, sig, e - N + 1, e, "signal", cfg)
        return done("signal")
    pend = None
    if A.cur is None or not A.cur["gap_before"]:
        pend = _attempt(A, e - N + 2, e, cfg, cur_low=None if A.cur is None else A.cur["low"])
        if pend["ok"]:
            st = "pending" if A.cur is not None and A.cur["bull"] and (
                not cfg.require_higher_close or _gt(A.cur["close"], A.C[e])) else "forming"
            _fill(out, A, pend, e - N + 2, e, st, cfg)
            if st == "forming" and not cfg.detect_forming:
                out["detected"] = False
                out["why"].append(f"병정 {N - 1}개 완성 · 셋째 대기 — 형성 중은 탐지로 세지 않음 (detect_forming=False)")
            return done(st)
    out["after_signal"] = _after_signal(A, cfg)
    out["why"].append(f"신호(셋째 = {A.per[e]}): {sig['why']}")
    if pend is not None and pend["why"] and pend["why"] != sig["why"]:
        out["why"].append(f"셋째 대기(병정 = {A.per[max(0, e - N + 2)]}~{A.per[e]}): {pend['why']}")
    elif A.cur is not None and A.cur["gap_before"]:
        out["why"].append(f"이번 달({A.cur['month']}) 앞에 거래 없는 달 — 셋째 대기 판정 안 함")
    for att in (sig, pend):
        if att is not None and att.get("step") == "bottom":
            out.update(low_month=A.per[att["m"]], low=float(A.L[att["m"]]), bottom=att["bottom"])
            return done("bottom_unknown" if att["bottom"]["status"] == "unknown" else "not_bottom")
    return done("after_signal" if out["after_signal"] else "none")


def _fill(out: dict, A: _Mon, att: dict, s: int, e: int, state: str, cfg: RedThreeConfig) -> None:
    m = att["m"]
    ks = list(range(s, e + 1))
    cur = A.cur
    fl = _flags(A, ks, e, cfg)
    score, parts, unknown = _score(state, fl)
    out.update(detected=True, soldiers=[A.row(k) for k in ks], low_month=A.per[m], low=float(A.L[m]),
               low_left=float(A.L[m - 1]), low_right=float(A.L[m + 1]), low_first=A.first[m], low_last=A.last[m],
               bottom=att["bottom"], candidates=att["candidates"], invalid_below=float(A.L[m]), flags=fl,
               score=score, score_parts=parts, score_unknown=unknown)
    if state == "signal":
        piv = float(A.C[e])
        stage, note = BREAKOUT, f"기준가 {_px(piv)} ~ +{cfg.buy_range * 100:.0f}% 안"
        if cur is not None:
            c = cur["close"]
            if not _gt(cur["low"], A.L[m]):
                stage, note = FAILED, f"이번 달 저가 {_px(cur['low'])} ≤ 확정 저점 {_px(A.L[m])} — 구조 무효"
            elif cfg.fail_below_body and _lt(c, A.O[e]):
                stage, note = FAILED, f"이번 달 종가 {_px(c)} < 셋째 양봉 시가 {_px(A.O[e])} — 몸통 반납"
            elif _gt(c, piv * (1 + cfg.buy_range)):
                stage, note = EXTENDED, f"이번 달 종가 {_px(c)} = 기준가 대비 {c / piv - 1:+.1%} (> +{cfg.buy_range * 100:.0f}%)"
            else:
                note = f"이번 달 종가 {_px(c)} = 기준가 대비 {c / piv - 1:+.1%}"
        known = A.last[e] if cur is None else cur["first"]
        out.update(stage=stage, stage_note=note, pivot=piv, signal_month=A.per[e], signal_date=A.last[e],
                   known_date=known, lag=int(e - m), third_open=float(A.O[e]))
    else:
        if cur is None:
            piv = float(A.C[e]) if cfg.require_higher_close else None
        else:
            piv = max(cur["open"], float(A.C[e])) if cfg.require_higher_close else cur["open"]
        out.update(stage=NEAR_PIVOT if state == "pending" else FORMING, pivot=piv, lag=int(e - m),
                   third_by_index=int(m + cfg.max_lag))


# ---------------------------------------------------------------- 월봉 만들기
def monthly(df: pd.DataFrame, cfg: RedThreeConfig | None = None) -> pd.DataFrame:
    """일봉 → 월봉 (tq.monthly_bars, 'next_bar'). 'calendar' 이면 마지막 달을 그 달 마지막 KRX 거래일 봉이 있을 때 완성으로
    (코어 tq._last_session — 예전엔 그쪽 pd.Timedelta(days=1) 경고를 피하려 여기서 따로 셌다, 코어 수정 뒤 코어 그대로)."""
    cfg = cfg or RedThreeConfig()
    if cfg.complete_rule not in ("next_bar", "calendar"):
        raise ValueError(f"complete_rule: {cfg.complete_rule!r}")
    mb = tq.monthly_bars(df, drop_zero_volume=cfg.drop_zero_volume, complete_rule=cfg.complete_rule)
    return mb


# ---------------------------------------------------------------- 진입점
def evaluate(df: pd.DataFrame, t: int | None = None, cfg: RedThreeConfig | None = None) -> dict:
    """일봉 df 의 봉 t 까지(포함)로 판정 — 안에서 자르므로 t 뒤 봉은 보지 않는다(앞부분 불변)."""
    cfg = cfg or RedThreeConfig()
    if t is not None:
        t = t + len(df) if t < 0 else t
        df = df.iloc[:t + 1]
    mb = monthly(df, cfg)
    out = judge_monthly(mb, cfg)
    out["asof"] = _ds(df.index[-1]) if len(df) else None
    return out


def signals(df: pd.DataFrame, cfg: RedThreeConfig | None = None) -> list[dict]:
    """과거 적삼병 신호 월 전부 — 각 월은 그 시점까지 완성 월만으로 판정(미래 없음).

    signal_date = 셋째 양봉 월 마지막 거래일(패턴을 완성한 봉) · known_date = 신호가 처음 보이는 봉
    ('next_bar' 규칙: 다음 달 첫 거래일, 아직 없으면 None · 'calendar': signal_date) · known_i = df 안 위치."""
    cfg = cfg or RedThreeConfig()
    mb = monthly(df, cfg)
    A = _Mon(mb)
    out = []
    for j in range(cfg.n, A.n):
        att = _attempt(A.upto(j), j - cfg.n + 1, j, cfg)
        if not att["ok"]:
            continue
        if cfg.complete_rule == "calendar":
            known = A.last[j]
        else:
            known = _ds(mb["first"].iloc[j + 1]) if j + 1 < len(mb) else None
        ki = None if known is None else int(df.index.searchsorted(pd.Timestamp(known)))
        out.append({"signal_month": A.per[j], "signal_date": A.last[j], "known_date": known, "known_i": ki,
                    "low_month": A.per[att["m"]], "low": float(A.L[att["m"]]), "pivot": float(A.C[j]),
                    "rule_version": RULE_ID})
    return out


def _excluded(ctx: StockContext) -> str | None:
    info = ctx.info or {}
    if info.get("end_type") not in (None, "stock"):
        return f"종목 구분 {info.get('end_type')}"
    nm = str(ctx.name or info.get("name") or "")
    hit = _EXCLUDE_RE.search(nm)
    return f"이름 '{nm}'" if hit else None


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, RedThreeConfig)
    r = PatternResult(name=NAME, label=LABEL)
    m = r.metrics
    m.update(rule_version=RULE_ID, core_version=tq.CORE_VERSION, origin=dict(RTM_ORIGIN), params=asdict(cfg),
             bulkowski_note=BULKOWSKI)
    ex = _excluded(ctx)
    if ex:
        m.update(state="excluded", state_label=STATE_LABELS["excluded"])
        r.warnings.append(f"제외 대상 — {ex} ({RTM_ORIGIN['exclude']})")
        return r
    df = tq.eod_frame(ctx)
    if ctx.partial:
        r.warnings.append(PARTIAL_NOTE)
    j = evaluate(df, cfg=cfg)
    _to_result(r, j, df, cfg)
    if ctx.partial and len(ctx.df):
        _provisional(r, ctx, df, cfg, j)
        _intraday_final(r, ctx, j)
    return r


def _intraday_final(r: PatternResult, ctx: StockContext, j: dict) -> None:
    """장중 — 신호 뒤 '이번 달 저가 ≤ 확정 저점'(구조 무효)은 저가 규칙: 오늘 장중 저가가 같은 달 안에서 이미 닿았으면
    마감 뒤 판정도 돌파 실패다(저가는 내려가기만). 종가 규칙(이번 달 종가 < 셋째 양봉 시가)은 마감 전엔 모르니 그대로."""
    if not r.detected or j.get("state") != "signal" or r.stage == FAILED:
        return
    today = pd.Timestamp(ctx.df.index[-1])
    mn = j.get("month_now") or {}
    if mn.get("month") != str(today.to_period("M")):
        return                       # 새 달 첫 거래일 — 오늘 저가는 신호의 '이번 달'이 아니다
    low_l = j.get("low")
    try:
        lo = float(ctx.df["low"].iloc[-1])
    except (TypeError, ValueError):
        return
    if low_l is None or not math.isfinite(lo) or _gt(lo, low_l):
        return
    day = f"{today:%Y-%m-%d}"
    text = f"장중 확정(저가): 오늘({day}) 저가 {_px(lo)} ≤ 확정 저점 {_px(low_l)} — 구조 무효"
    r.stage = FAILED
    r.metrics.update(intraday_final={"kind": "invalid_low", "date": day, "low": lo, "level": float(low_l), "text": text},
                     stage_label="돌파 실패 · 장중 확정(저가)", stage_short="실패(장중 확정)")
    r.warnings.insert(0, text + " — 저가는 마감까지 내려가기만 해 마감 뒤 판정도 같다 (종가 규칙은 마감 뒤에)")


def _to_result(r: PatternResult, j: dict, df: pd.DataFrame, cfg: RedThreeConfig) -> None:
    m = r.metrics
    for k in ("state", "state_label", "months", "last_month", "month_now", "hts", "after_signal", "asof", "low_month",
              "low", "low_left", "low_right", "bottom", "soldiers", "third_open", "flags", "score_parts", "score_unknown",
              "invalid_below", "signal_month", "signal_date", "known_date", "lag", "third_by_index", "candidates",
              "stage_note"):
        if j.get(k) is not None:
            m[k] = j[k]
    a = j.get("after_signal")
    if a:
        tail = (f" — 이후 연속 양봉 {a['run_after']}개월 (총 {a['total_run']}개월)" if a["continuing"]
                else f" — 그 뒤 연속 양봉 {a['run_after']}개월에서 끊김")
        r.warnings.append(f"지난 적삼병 신호 {a['signal_month']} ({a['months_ago']}개월 전, 저점 {a['low_month']} {_px(a['low'])})"
                          + tail + (" · 저점 유지" if a["intact"] else " · 저점 깨짐")
                          + " — 4번째 연속 양봉 달은 새 신호 아님 (부록 §2.3 8)")
    if not j["detected"]:
        r.warnings[:0] = [f"{j['state_label']}: {w}" for w in j["why"]] or [j["state_label"]]
        mn = j.get("month_now")
        if mn:
            r.warnings.append(f"이번 달 진행 · 미완성 {mn['month']} ({mn['days']}거래일): 월초 시가 대비 {mn['chg']:+.1%}")
        return
    N = cfg.n
    sd = j["soldiers"]
    lm = j["low_month"]
    piv = j["pivot"]
    r.detected = True
    r.stage = j["stage"]
    r.score = j["score"]
    r.pivot = piv
    r.stop = None
    r.start_date = j.get("low_first")
    sig = j["state"] == "signal"
    r.end_date = j.get("signal_date") if sig else j.get("asof")
    r.breakout_date = j.get("signal_date") if sig else None
    fl = j["flags"]
    bot = j["bottom"]
    mn = j.get("month_now")
    # 근거
    sold = " · ".join(f"{x['month']} {x['chg']:+.1%}" for x in sd)
    if sig:
        r.reasons.append(f"월봉 적삼병 — 완성 월봉 {N}개 연속 양봉" + (" · 종가 상승" if cfg.require_higher_close else "")
                         + f": {sold} (시가 → 종가) [{tq.video('04:00–14:00')} · 한경 · Bulkowski]")
    else:
        r.reasons.append(f"병정 {len(sd)}개 완성 — {sold} (시가 → 종가)" + (" · 종가 상승" if cfg.require_higher_close else "")
                         + f" · 셋째 대기 [{tq.video('04:00–14:00')}]")
    r.reasons.append(f"확정 저점 {lm} 저가 {_px(j['low'])} — 왼쪽 {_px(j['low_left'])} · 오른쪽 {_px(j['low_right'])} 보다 낮음 "
                     f"[{tq.video('08:00–09:00')}] · 그 뒤 새 저가 없음 · 저점 뒤 첫 {N}연속 양봉")
    r.reasons.append(f"바닥권 — 저점이 직전 12개월 최고 종가 {_px(bot['ref_close'])} 대비 −{bot['dd'] * 100:.1f}% "
                     f"(기준 −{cfg.bottom_dd * 100:.0f}% 이하 · {tq.video('04:00–05:00')} · 약세장 관례)")
    r.reasons.append(f"셋째 양봉 {'=' if sig else '기한'} 저점 뒤 {j['lag'] if sig else cfg.max_lag}개월"
                     + (f" (상한 {cfg.max_lag} — 구현 선택)" if sig else " (RTM_MAX_LAG — 구현 선택)"))
    if sig:
        r.reasons.append(f"신호 {j['signal_month']} — 완성 봉 {j['signal_date']} · 확정 {j.get('known_date') or '—'} "
                         f"(가장 최근 완성 월인 동안 유지) · {STAGE_LABELS[r.stage]}: {j['stage_note']}")
    if mn:
        live = (f" · 지난달 종가 대비 {mn['vs_prev_close']:+.1%}" if mn.get("vs_prev_close") is not None else "")
        if sig:
            r.reasons.append(f"이번 달 진행 · 미완성 {mn['month']} ({mn['days']}거래일): 월초 시가 대비 {mn['chg']:+.1%}{live} — "
                             "영상 가설 '다음 달도 양봉'은 관찰 대상, 신호 아님")
        elif r.stage == NEAR_PIVOT:
            r.reasons.append(f"이번 달 진행 · 미완성 {mn['month']}: 지금까지 양봉 {mn['chg']:+.1%}{live} — 잠정 셋째 병정 "
                             f"(키움 0봉전 꼴 · 다음 달 첫 봉에 확정, 신호 아님)")
        else:
            r.reasons.append(f"셋째 대기 — 이번 달({mn['month']}) 종가가 {_px(piv)} 위로 끝나면 셋째 병정 "
                             f"(지금 {_px(mn['close'])}, 월초 시가 대비 {mn['chg']:+.1%})")
    tags = [f"짧은 위꼬리 {_yn(fl['short_upper'])}", f"저가 상승 {_yn(fl['rising_lows'])}",
            f"키 큰 몸통 {_yn(fl['tall_body'])}"]
    if fl["adv_block"] is not None or len(sd) >= 3:
        tags.append(f"어드밴스 블록 {_yn(fl['adv_block'])}")
    tags.append("연중 위치 모름" if fl["yearly_pos"] is None else f"연중 위치 {fl['yearly_pos'] * 100:.0f}%"
                + (" (하단 ⅓)" if fl["yearly_low_third"] else ""))
    r.reasons.append("관찰 꼬리표 — " + " · ".join(tags) + f" · 점수 {r.score:.0f} (구현 선택 — 성공 확률 아님)")
    if fl["adv_block"]:
        r.warnings.append("어드밴스 블록 · 정체 꼴 — 셋째 몸통이 줄었거나 위꼬리 ≥ 몸통 (키움 도움말 p.39 · TA-Lib)")
    if j["score_unknown"]:
        lab = dict(_TAGS)
        r.warnings.append("꼬리표 모름(이력 부족 — 0점): " + " · ".join(lab[k] for k in j["score_unknown"]))
    if r.stage == FAILED:
        r.warnings.append(f"돌파 실패 — {j['stage_note']}")
    r.warnings.append(STOP_NOTE)
    m = r.metrics
    m["stop_rule"] = None
    halts = _halts(df, j)
    if halts:
        m["halts"] = halts
        r.warnings.append(f"패턴 구간 거래정지일 {len(halts)}일 — 월봉은 거래한 날만으로 묶음: {', '.join(halts[:5])}"
                          + (" …" if len(halts) > 5 else ""))
    r.annotations.extend(_annotations(j, df, sig, cfg))


def _low_day(df: pd.DataFrame, j: dict, cfg: RedThreeConfig) -> str | None:
    if not j.get("low_first") or not j.get("low_last"):
        return None
    d = df.loc[j["low_first"]:j["low_last"]]
    if cfg.drop_zero_volume and "volume" in d:
        d = d[d["volume"] > 0]
    return _ds(d["low"].idxmin()) if len(d) else j["low_first"]


def _halts(df: pd.DataFrame, j: dict) -> list[str]:
    if not len(df) or not j.get("low_first"):
        return []
    i0 = int(df.index.searchsorted(pd.Timestamp(j["low_first"])))
    return tq.window_halts(df, i0, len(df) - 1)


def _annotations(j: dict, df: pd.DataFrame, sig: bool, cfg: RedThreeConfig) -> list[dict]:
    ann = []
    low_day = _low_day(df, j, cfg)
    ann.append(hline(j["low"], "확정 저점 (구조 무효선)", "#1e88e5", "solid"))
    if j.get("pivot") is not None:
        ann.append(hline(j["pivot"], "기준가 (셋째 양봉 종가)" if sig else "셋째 조건가", "#2962ff"))
    if low_day:
        ann.append(marker(low_day, f"월봉 저점 {j['low_month']}", "below", "#1e88e5", "arrowUp"))
    for i, x in enumerate(j["soldiers"], 1):
        ann.append(box(x["first"], x["last"], max(x["open"], x["close"]), min(x["open"], x["close"]),
                       f"{i}병 {x['month']}", "#ef5350"))
    mn = j.get("month_now")
    if mn and not sig and j["stage"] == NEAR_PIVOT and mn["last"] and mn["first"] and mn["last"] > mn["first"]:
        ann.append(box(mn["first"], mn["last"], max(mn["open"], mn["close"]), min(mn["open"], mn["close"]),
                       f"잠정 {len(j['soldiers']) + 1}병 (이번 달 진행)", "#ffab91"))
    last = j["soldiers"][-1]
    if low_day:
        ann.append(segment([(low_day, j["low"]), (last["last"], last["close"])], "저점 → 병정", "#ff6d00"))
    if sig:
        ann.append(marker(j["signal_date"], "적삼병 완성", "above", "#e91e63", "arrowDown"))
    return ann


def _provisional(r: PatternResult, ctx: StockContext, df: pd.DataFrame, cfg: RedThreeConfig, j: dict) -> None:
    """장중 잠정 — 오늘 봉 값은 쓰지 않는다. 새 달 첫 거래일이면 지난달을 완성 월로 본 판정을 따로 둔다."""
    today = pd.Timestamp(ctx.df.index[-1])
    m = r.metrics
    if not len(df):
        return
    if today.to_period("M") != pd.Timestamp(df.index[-1]).to_period("M"):
        mb = monthly(df, cfg)
        if not len(mb):
            return
        prev = str(mb.index[-1])
        pj = judge_monthly(mb.assign(complete=True), cfg)
        m["provisional"] = {"label": "장중 잠정", "basis": f"오늘({today:%Y-%m-%d})이 새 달 첫 거래일 — 지난달 {prev} 를 완성 월로 본 "
                                                       f"판정 (오늘 봉 값은 안 씀)",
                            "state": pj["state"], "state_label": pj["state_label"], "stage": pj["stage"],
                            "signal_month": pj.get("signal_month"), "pivot": pj.get("pivot")}
        if pj["state"] == "signal" and j["state"] != "signal":
            r.reasons.append(f"장중 잠정 — 오늘이 새 달 첫 거래일: 지난달 {prev} 가 끝나 적삼병 완성 "
                             f"(기준가 {_px(pj['pivot'])} · 오늘 장 마감 뒤 EOD 로 확정)")
        return
    mn = m.get("month_now")
    if mn and mn.get("month") == str(today.to_period("M")) and mn.get("open"):
        live = float(ctx.df["close"].iloc[-1])
        mn.update(live_close=live, live_chg=live / mn["open"] - 1, live_label="장중 잠정")
