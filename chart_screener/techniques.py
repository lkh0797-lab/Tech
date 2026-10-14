"""차트 발굴 기법 공용 부품 — 《차트의 기술》 영상 기법 6종이 함께 쓰는 순수 함수(numpy · pandas).

스펙  docs/2026-10-14-chart-techniques-design.md
부록  docs/2026-10-14-chart-techniques-addendum.md  (수치 · 출처 · 알고리즘 — 스펙의 '구현 선택' 추정보다 우선)

원칙
  - 일봉 EOD 완성 봉만. 장중 미완성 봉은 eod_frame(ctx) 로 뺀다(장중 잠정 판정은 패턴 모듈이 따로, 라벨을 붙여).
  - 미래 금지: 봉 t 판정은 [0..t] 자료만. 함수가 t 를 받으면 안에서 b.cut(t) 로 잘라 쓴다 — 앞부분 불변
    (prefix invariance)이 구조로 보장된다. 스윙 고점 · 저점은 확인 봉(confirm_i) 뒤에만 쓴다.
    예외는 확인 사건 함수 hammer_confirm 하나 — 망치 뒤 봉을 보지만 upto 까지만 보고 확인 날짜를 따로 단다.
  - 출처: 결과 dict 의 'origin' 에 규칙마다 '영상 [mm:ss]' · 출처 URL · '구현 선택: 이유' 를 단다(ORIGIN 표).
    패턴 모듈은 이것을 PatternResult.metrics['origin'] 이나 reasons 로 옮긴다.
  - 확률을 쓰지 않는다. 불코우스키 수치는 bulkowski_note() — '참고 — 불코우스키 미국 통계(우리 데이터 아님)' 라벨로만.
  - 자료가 없으면 None / 'unknown'(모름). 지어내지 않는다.

비교 경계
  '같음 포함' 문턱(≥ · ≤)은 부동소수 오차(상대 1e-9)를 같음으로 본다(_ge · _le). 엄격 문턱(> · <)은 같은 오차 안이면
  넘지 않은 것으로 본다(_gt · _lt). 예: −15.0% 정확히는 데드캣 사건, 무장일과 같은 저가는 위반 아님.

API — 패턴 모듈이 import 해 쓴다 (from chart_screener import techniques as tq)
  자료       Bars.from_df(df) · b.cut(t) · b.n · b.date(i) · b.frame() · eod_frame(ctx) · window_halts(df, i0, i1)
  이평       sma · ema · prior_mean(당일 제외, volume= 주면 거래량 0 행 제외) · vol_ma(5일 거래량 이평, 오늘 포함) ·
             vol_ratio(거래량 0 행 제외) · ma_lines · ma_snapshot · cross_above · count_up · up_streak · ols_slope · MA_PERIODS · MA_NAMES
  스윙       Swing · swing_highs · swing_lows · swings_known_at
  월 · 주봉  period_bars · monthly_bars · weekly_bars · weekly_trend
  피보       FIB_RATIOS · FIB_LEVELS_BUY · fib_levels · next_deeper · retracement · in_zone · fib_touch · fib_touch_level · fib_approach
  추세선     TrendlineConfig · TrendLine · downtrend_line_candidates · fit_downtrend_line · line_cross · line_features · line_targets
  캔들       HammerConfig · hammer_frame · hammer · is_hammer · hammer_confirm
             LongWhiteConfig · long_white_frame · long_white · volume_reversal
  청산       ExitConfig · arm_days · ma_violation · ma_violations · seven_week_rule · exit_plan · violation_fill_price
  체크리스트 CheckItem · ChecklistInputs · ChecklistConfig · inputs_from_ctx · run_checklist · checklist_counts · industry_rs_table
  시장 맥락  MarketContextConfig · market_context · market_context_all
  공통       PATTERN_LABELS · RULE_IDS · ORIGIN · video · choice · bulkowski_note · CORE_VERSION
             ge · le · gt · lt (아래 '비교 경계' — 패턴 모듈이 사본 없이 같은 경계로 비교)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, NamedTuple

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from . import indicators as ind
from . import krx
from .market import CONFIRMED, STATE_LABELS

CORE_VERSION = "techniques_core_v1"
EPS = 1e-9

# ---------------------------------------------------------------- 패턴 이름 · 규칙 id (일지 'rule' 열)
PATTERN_LABELS = {
    "red_three_monthly": "월봉 적삼병",
    "fib_pullback": "피보나치 눌림 반등",
    "trendline_break": "빗각 추세선 돌파",
    "trendline_fib": "빗각 돌파 + 피보 눌림",
    "day_leader": "10% 주도주 (단타 관찰)",
    "ma60_supply": "60일선 수급 돌파",
}
RULE_IDS = {   # 권장 값 — 규칙을 바꾸면 v 를 올려 옛 기록과 섞이지 않게
    "red_three_monthly": "red3m_v1",
    "fib_pullback": "fibpb_v1",
    "trendline_break": "tlbrk_v1",
    "trendline_fib": "tlfib_v1",
    "day_leader": "dlead_v1",
    "ma60_supply": "ma60s_v1",
}

# ---------------------------------------------------------------- 출처
VIDEO_ID = "YouTube rnO2FXqo3cs"


def video(ts: str) -> str:
    """'영상 [mm:ss]' — 김정환 《차트의 기술》 요약 영상 위치."""
    return f"영상 [{ts}]"


def choice(why: str) -> str:
    """출처 없는 값 — 이유를 같이 적는다."""
    return f"구현 선택: {why}"


_KIWOOM = "https://download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf"
ORIGIN: dict[str, str] = {
    # 공통
    "white": f"키움 조건검색 도움말 p.3 — 양봉 C > O 엄격, 같으면 양봉 아님 ({_KIWOOM})",
    "baseline_excl_today": "비율 기준선은 당일 제외 직전 N봉 평균 — Bulkowski 돌파 거래량 (https://thepatternsite.com/volbkout.html) · TA-Lib",
    "sma": "종가 SMA 오늘 포함(EOD 확정) — Bulkowski Kacher–Morales 검증이 SMA (https://thepatternsite.com/KacherMorales.html)",
    "vol_ma5": video("51:00") + " '거래량이 5일 이평을 뚫는' · 키움 이동평균 관례(오늘 포함)",
    "cross": f"키움 조건검색 도움말 돌파 정의 — 앞 봉 A ≤ B, 현재 봉 A > B ({_KIWOOM})",
    "ma_names": ("60일선 = 수급선 한국경제 생글생글 2005 (https://sgsg.hankyung.com/article/2005102520411) · "
                 "120일선 = 경기선 머니투데이 (https://www.mt.co.kr/stock/2008/04/20/2008042011120047780) · "
                 "20일선 = 단기 생명선 머니투데이 (https://www.mt.co.kr/stock/2008/10/15/2008101511101671229)"),
    "halt_rows": choice("거래량 0(정지) 행은 월 · 주봉 합성과 평균에서 뺀다 — 직전 종가로 채운 행이 시가 · 저가 · 평균을 왜곡"),
    # 스윙
    "swing": ("k봉 확인 소고점 — Bulkowski 소고점 (https://thepatternsite.com/minorhl.html) · 그의 소프트웨어 3봉 대기 "
              "(https://thepatternsite.com/uptrendlines.html) · LMW d=3 "
              "(https://www.nber.org/system/files/working_papers/w7613/w7613.pdf) — 봉 p+k 부터 씀"),
    "fractal2": "좌우 2봉 엄격 — MetaTrader 5 fractals (https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/fractals)",
    # 월 · 주봉
    "monthly": (video("04:00–14:00") + " 월봉 = 일봉을 달력 월로 묶음 · "
                + choice("완성 월 = 다음 달 봉이 있는 달 — 월말 EOD 도 하루 늦게 확정, 앞부분 불변")),
    "period_calendar": choice("KRX 휴장일 표(krx.py — 비정기 휴장은 2023-09 ~ 2026-10 만)로 기간 마지막 거래일 당일 확정, 표 밖 기간은 틀릴 수 있음"),
    "period_volume": "거래량 합 · 평균 일거래량 둘 다 관례 — CSI Data (https://csidata.com/custserv/onlinehelp/OnlineManual/structureofdailyweeklyandmont.htm)",
    "weekly_10w": "체크리스트 3 주봉 = 일봉 — Bulkowski 항목 (https://thepatternsite.com/tradehelp.html) · " + choice("10주선 ≈ 50일선"),
    # 피보
    "fib_levels": ("23.6 · 38.2 · 50 · 61.8, 고점 고가 · 저점 저가(꼬리) 기준 — StockCharts ChartSchool "
                   "(https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements)"),
    "fib_buy": video("19:00–24:00, 26:00–29:00, 50:00–52:00") + " 23.6 · 38.2 · 50% 지지 · 61.8 은 표시만 " + video("40:00"),
    "fib_tol": choice("접촉 허용 1.5% — 권위 있는 수치 없음(Bulkowski '근처' · 키움 근접률 사용자 지정), 고정 · 최적화 안 함"),
    "fib_touch_wick": choice("'wick' — 저가 ≤ 라인×(1+tol) · 종가 ≥ 라인 · 저가 > 다음 깊은 라인 (아래꼬리 관통 허용, ChartSchool 망치 예시)"),
    "fib_touch_band": ("스펙 원안 'band' — 라인×(1−tol) ≤ 저가 ≤ 라인×(1+tol) · 종가 ≥ 라인 · " + video("20:00, 26:00, 50:00")
                       + " 지지 · " + choice("±1.5% (스펙)")),
    "fib_approach": choice("라인 위 3% 안 = 눌림 진행 (출처 없음)"),
    "fib_stop": "다음 깊은 라인 손절 — BabyPips (https://www.babypips.com/learn/forex/placing-stops-with-fibs) · " + video("23:00, 27:00"),
    "fib_invalid": "61.8% 아래 종가 = 무효 — Bulkowski 62% 넘는 되돌림이면 매도 (https://thepatternsite.com/tradehelp.html)",
    # 추세선
    "tl_log": "로그 눈금 — Bulkowski (https://thepatternsite.com/trenddown.html) · ChartSchool 반로그",
    "tl_lookback": choice("250봉 — 영상 9개월(~189봉)을 품고 Bulkowski 중앙 길이 44~48일보다 충분히 김"),
    "tl_anchor_highest": "앵커 = 구간 최고 확정 소고점 — Sperandeo 1-2-3 (https://thepatternsite.com/123tc.html)",
    "tl_anchor_volume": video("21:00") + " 거래량이 터진 캔들의 고점 · " + choice("2.0 × 직전 50봉 평균"),
    "tl_tol_cut": (video("44:00, 49:00") + " 캔들 관통 금지 · "
                   + choice("고가 ≤ 선 × 1.005 — 엄격(Bulkowski · 김정환 장중 고가)과 관대(ChartSchool · AAII) 사이")),
    "tl_close_cut": "선 위 종가가 이미 있으면 낡은 선 — Bulkowski 돌파 = 처음으로 선 위 종가 (https://thepatternsite.com/trenddown.html)",
    "tl_touch": ("접점 = 확정 소고점 · 선×0.985 ≤ 고가 ≤ 선×1.005 — Bulkowski QTL (https://www.thepatternsite.com/QTL.html) · "
                 "1.5% 는 LMW 쌍봉 허용치 유추"),
    "tl_min_touches": ("접점 3개 이상 — Murphy 법칙 5 · ChartSchool "
                       "(https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading) · "
                       + video("44:00–46:00")),
    "tl_bonus_touches": "접점 5개 이상 가점 — Bulkowski 상승선 시험 (https://thepatternsite.com/uptrendlines.html)",
    "tl_min_gap": choice("이웃 접점 10봉 이상 (출처 있는 최소값은 Penteado 3봉 https://arxiv.org/pdf/1302.1228)"),
    "tl_wide_gap": "간격 중앙값 13봉 초과 가점 — Bulkowski trenddown 중앙값 13일 (https://thepatternsite.com/trenddown.html)",
    "tl_min_len": choice("길이 40봉 이상 (스펙 값, Bulkowski 중앙 48 바로 아래)"),
    "tl_long_len": "길이 48봉 초과 가점 — Bulkowski trenddown 중앙값 48일 (https://thepatternsite.com/trenddown.html)",
    "tl_vol_trend": ("돌파 전 거래량 감소 가점 — Bulkowski glossary 회귀 · trenddown (https://thepatternsite.com/trenddown.html) "
                     "(효과 매우 작음, 관문 아님)"),
    "tl_entry_trend": "앵커 전 진입 추세 평평 가점 — Bulkowski trenddown · " + choice("20봉"),
    "tl_break_vol": ("돌파 거래량 ≥ 직전 50봉 × 1.5 — O'Neil 40~50% · Edwards & Magee "
                     "(반대 증거 Bulkowski https://www.thepatternsite.com/VolumeStudy.html)"),
    "tl_target": ("Bulkowski trenddown 측정 규칙(미국) — T1 앵커 고가 · T2 돌파가 + 0.56 × D · "
                  + choice("돌파가 = 돌파일 선 값")),
    # 망치형
    "hammer_lower": ("아래꼬리 ≥ 몸통 × 2 — StockCharts "
                     "(https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-bullish-reversal-patterns) · "
                     "Bulkowski (https://thepatternsite.com/Hammer.html) · " + video("00:00")),
    "hammer_upper": "위꼬리 ≤ 0.1 × 직전 10봉 평균 범위 — TA-Lib ShadowVeryShort (https://github.com/TA-Lib/ta-lib)",
    "hammer_range": "범위 ≥ 직전 10봉 평균 — StockCharts · " + choice("1.0 배"),
    "hammer_decline": ("직전 종가 < EMA20 — StockCharts 20일 지수이평 아래 = 하락 "
                       "(https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-bullish-reversal-patterns) · "
                       "Bulkowski 들어오는 추세 하락 (https://thepatternsite.com/Hammer.html)"),
    "hammer_yearly": "연중 위치 ≤ ⅓ (252봉 HH · LL) — Bulkowski (https://thepatternsite.com/Hammer.html)",
    "hammer_confirm": ("3봉 안 종가 > 망치 고가 = 망치 확인(별도 날짜) — StockCharts 1~3일 확인 "
                       "(https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-bullish-reversal-patterns)"),
    "hammer_doji": choice("몸통 0 허용 · 'doji-hammer' 라벨 (TA-Lib 식도 허용)"),
    # 장대양봉
    "lw_chg": choice("전일 대비 +7% — 한국 관례 블로그뿐 (https://i-whale.com/entry/기준봉이란-기준봉-선정하고-매매-종목-찾기)"),
    "lw_body": ("몸통 ≥ 직전 15봉 평균 몸통 × 3 — Bulkowski Long White Day (https://thepatternsite.com/LongWhiteDay.html) · "
                + choice("15봉 = 3주 환산")),
    "lw_shadow": "위 · 아래 꼬리 각각 < 몸통 — Bulkowski Long White Day (https://thepatternsite.com/LongWhiteDay.html)",
    "lw_vol": choice("거래량 ≥ 직전 20봉 평균 × 2 (출처 없음)"),
    "lw_zero_base": choice("기준선(직전 거래 봉 평균 몸통 · 거래량)이 0 이면 배수가 무한 — 통과가 아니라 모름(장대양봉 아님)"),
    # 거래량 실린 반등 양봉
    "vol_rev_cross": video("22:00–23:00, 51:00") + " 거래량 실린 반등 양봉 · 키움 '상향돌파'(전일 V ≤ MA5V, 당일 V > MA5V)",
    "vol_rev_level": "스펙 원문 수준 비교 V > MA5V — " + video("51:00") + " '거래량이 5일 이평을 뚫는'",
    "vol_rev_upclose": choice("'반등' = 전일보다 높은 종가"),
    # 청산
    "exit_ma5": (video("23:00–25:00, 28:00–29:00") + " 5일선 종가 이탈 1차 · 다음 카페 Antsstory "
                 "(https://m.cafe.daum.net/Antsstory/DJzh/152) — 종가 기준은 커뮤니티 출처"),
    "exit_ma10": ("Morales · Kacher 10일선 위반 — 무장일(10일선 아래 첫 종가) 다음 날 저가 < 무장일 저가, 무장 자체는 위반 아님 · "
                  "TradingView 7-Week Rule (https://www.tradingview.com/script/kDC1dFjU-7-Week-Rule/) · "
                  "Everand (https://www.everand.com/book/343295426)"),
    "exit_until_reclaim": "'until_reclaim' — 회복 전 어느 봉이든 — Edgerater (https://edgerater.com/blog/morales-and-kacher-signals-template) · Bulkowski",
    "exit_ma50": "50일선 위반 같은 두 단계 — https://in.tradingview.com/chart/VNINDEX/AgmKyPf9-Vnindex-Apr-2022-Rules-of-violation-of-the-50-day-MA · Bulkowski",
    "exit_7wk_edgerater": ("7주(35거래일) — 그 안에 10일선 위반이 있었으면 50일선 기준 · Edgerater "
                           "(https://edgerater.com/blog/morales-and-kacher-signals-template) · TradingView 7-Week Rule "
                           "(https://www.tradingview.com/script/kDC1dFjU-7-Week-Rule/)"),
    "exit_7wk_bulkowski": "7주(35거래일) — 보유 35 미만 50일선 · 이상 10일선 · Bulkowski (https://thepatternsite.com/KacherMorales.html)",
    "exit_arm_scope": choice("진입 봉부터(포함) 생긴 무장일만 센다"),
    "exit_fill": choice("재현 채점 체결가 min(위반 봉 시가, 무장일 저가 − 1호가)"),
    # 체크리스트 (Bulkowski's Trading Checklist https://thepatternsite.com/tradehelp.html — 항목)
    "ck1": "Bulkowski 체크리스트 1 시장 추세 · market.py 국면 그대로 — 상승 확인 통과, 조정 경고 · 상승 압박도 경고(구현 선택: 확인이 아님)",
    "ck2": "Bulkowski 체크리스트 2 산업 위치 · " + choice("업종 강도 백분위 ≥ 0.75 = 주도, 구성 종목 연중 위치 중앙값 ≥ ⅔ 고점권 · ≤ ⅓ 바닥권"),
    "ck3": "Bulkowski 체크리스트 3 한 단계 위 눈금 · " + choice("완성 주봉 종가 > 10주선 이고 일봉 종가 > 50일선"),
    "ck4": "Bulkowski 체크리스트 4 같은 종목 과거 결과 · " + choice("20거래일 뒤 수익, 3건 미만 '표본 적음', 중앙값 > 0 통과"),
    "ck5": "업종 RS 상위 ¼ — Bulkowski industryRS (https://thepatternsite.com/industryRS.html) · " + choice("구성 3종목 미만 모름"),
    "ck6": "Bulkowski 체크리스트 6 위로 돌아설 때까지 기다림 · " + choice("종가 > 20일선 · 60일선"),
    "ck7": ("Bulkowski 체크리스트 위 저항 · buylow (https://thepatternsite.com/buylow.html) — 가장 가까운 위 확정 소고점 · "
            + choice("거리 10% 미만 경고")),
    "ck8": "Bulkowski 변동성 손절 저가 − 2 × 22봉 평균 고저폭 (https://thepatternsite.com/stops.html)",
    "ck9": ("데드캣 사건 = 하루 종가 −15% 이하 · 6개월(126봉) 안이면 경고 — Bulkowski (https://www.thepatternsite.com/dcb.html) · "
            + choice("2015-06-15 전은 −14.5% 또는 2일 누적 −15%") + " · 공시 위험 꼬리표(스펙) · 6~12개월 참고 창 = 영상"),
    "ck10": ("Bulkowski 체크리스트 연속 상승 뒤 반전 경계 ↔ QConsecutive (https://www.thepatternsite.com/QConsecutive.html) 충돌 → 주의로 낮춤 · "
             + choice("5일 중 4일 상승 · 5일 +20%")),
    # 시장 맥락
    "mkt_ma120": "지수 120일선(경기선) — 머니투데이 (https://www.mt.co.kr/stock/2003/04/29/2003042918362686531)",
    "mkt_zz": ("마지막 확정 저점 = ZigZag 20% (그 뒤 20% 올라야 확정) — ChartSchool ZigZag "
               "(https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/zigzag) · "
               + choice("20% = 약세장 −20% 관례와 같은 크기")),
    "mkt_retr": ("되돌림 50~61.8% 깃발 — ChartSchool Dow Theory 이차 조정 ⅓~⅔ · 흔히 50% · " + video("39:00–41:00")
                 + " 영상에 따르면 김종봉은 50% 를 강조(공개 자료로 확인 못함) · 확률 · 반등 기대치 안 씀"),
    "mkt_basis": choice("부록 §10 사례 표대로 두 기준 — 종가(종가 ZigZag · 최고 종가 · 오늘 종가) · 장중(고저 ZigZag · 최고 고가 · 오늘 저가)"),
}
# 체크리스트 10 은 영상이 소개한 순서(스펙 '불코우스키 체크리스트 10 [01:02:00–01:05:00]') — 항목마다 영상 위치를 앞에 붙인다
CK_VIDEO_TS = "01:02:00–01:05:00"
for _k in [f"ck{_i}" for _i in range(1, 11)]:
    ORIGIN[_k] = video(CK_VIDEO_TS) + " 체크리스트 10 · " + ORIGIN[_k]
del _k

BULKOWSKI_LABEL = "참고 — 불코우스키 미국 통계(우리 데이터 아님)"
BULKOWSKI_CONTEXT = {
    "three_white_soldiers": "적삼병 상승 반전 82% · 성과 순위 103개 중 32위 (미국 일봉) https://thepatternsite.com/ThreeWhiteSoldiers.html",
    "hammer": "망치형 상승 반전 60% — 본인도 무작위에 가깝다고 평가 https://thepatternsite.com/Hammer.html",
    "long_white_day": "롱 화이트 데이 지속 58% https://thepatternsite.com/LongWhiteDay.html",
    "trendline_down": ("하향 추세선 돌파 평균 상승 51% · 중앙값 30% · 되돌림 59% (3,274선, 1991–2021 강세장) "
                       "https://thepatternsite.com/trenddown.html"),
    "fib": "손으로 고른 되돌림 중앙값 59% · 자동 시험에서 38 · 50 · 62% 는 특별하지 않음 https://thepatternsite.com/fib.html",
    "volume_breakout": "대량 돌파는 평균 상승이 조금 높지만 되돌림 57% vs 18% (사각형 · 쌍봉, 추세선 아님) https://www.thepatternsite.com/VolumeStudy.html",
    "dead_cat": "데드캣 뒤 평균 하락 31% · 6개월 안 두 번째 데드캣 38% https://www.thepatternsite.com/dcb.html",
    "kacher_morales": ("Kacher–Morales 규칙 시험(557종목, 2001–2010) 이긴 거래 28~32% — 권하지 않는다고 결론, "
                       "본인 시험이 저자 방식과 다를 수 있다고 밝힘 https://thepatternsite.com/KacherMorales.html"),
}


def bulkowski_note(topic: str) -> str:
    """후보 옆 확률이 아니라 접히는 참고 줄에만 쓰는 문장."""
    return f"{BULKOWSKI_LABEL}: {BULKOWSKI_CONTEXT[topic]}"


# ---------------------------------------------------------------- 비교 (부동소수 경계)
def _tol(b):
    return EPS * np.maximum(1.0, np.abs(b))


def _ge(a, b):
    return a >= b - _tol(b)


def _le(a, b):
    return a <= b + _tol(b)


def _gt(a, b):
    return a > b + _tol(b)


def _lt(a, b):
    return a < b - _tol(b)


# 공개 이름 — 패턴 모듈이 사본을 두지 않고 같은 경계(상대 1e-9)로 비교한다. 스칼라는 bool(...) 로 감싸 쓴다.
ge, le, gt, lt = _ge, _le, _gt, _lt


def _f(x) -> float | None:
    """유한 실수면 float, 아니면 None (JSON · 화면용)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------- 자료
class Bars(NamedTuple):
    """일봉 배열 묶음 (float numpy). dates 는 DatetimeIndex 또는 None."""
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    dates: pd.DatetimeIndex | None = None

    @classmethod
    def from_df(cls, df: pd.DataFrame) -> "Bars":
        v = df["volume"] if "volume" in df.columns else np.zeros(len(df))
        dates = pd.DatetimeIndex(df.index) if isinstance(df.index, pd.DatetimeIndex) else None
        return cls(*(np.asarray(df[k], dtype=float) for k in ("open", "high", "low", "close")),
                   np.asarray(v, dtype=float), dates)

    @classmethod
    def from_arrays(cls, open, high, low, close, volume=None, dates=None) -> "Bars":  # noqa: A002
        c = np.asarray(close, dtype=float)
        v = np.zeros(len(c)) if volume is None else np.asarray(volume, dtype=float)
        return cls(np.asarray(open, float), np.asarray(high, float), np.asarray(low, float), c, v,
                   None if dates is None else pd.DatetimeIndex(dates))

    @property
    def n(self) -> int:
        return len(self.close)

    def cut(self, t: int) -> "Bars":
        """[0..t] — 봉 t 까지만 (미래 봉 제거)."""
        if t < 0:
            t += self.n
        e = t + 1
        return Bars(self.open[:e], self.high[:e], self.low[:e], self.close[:e], self.volume[:e],
                    None if self.dates is None else self.dates[:e])

    def date(self, i: int) -> str | None:
        return None if self.dates is None or not 0 <= i < self.n else f"{self.dates[i]:%Y-%m-%d}"

    def frame(self) -> pd.DataFrame:
        idx = self.dates if self.dates is not None else pd.RangeIndex(self.n)
        return pd.DataFrame({"open": self.open, "high": self.high, "low": self.low, "close": self.close,
                             "volume": self.volume}, index=idx)


def eod_frame(ctx) -> pd.DataFrame:
    """완성 봉만 — 장중(ctx.partial)이면 마지막 미완성 봉을 뺀다."""
    df = ctx.df
    return df.iloc[:-1] if getattr(ctx, "partial", False) and len(df) else df


def window_halts(df: pd.DataFrame, i0: int, i1: int) -> list[str]:
    """봉 i0..i1 날짜 구간 안의 거래정지일(df.attrs['halt_dates'] — 공용 로더가 df 에서 뺀 날).

    Tech 거래량은 수정되지 않았다 — 정지가 분할 · 병합이면 그 창의 거래량 비교가 몇 배로 틀린다(경고용)."""
    halts = df.attrs.get("halt_dates") or []
    if not halts or len(df) == 0:
        return []
    i0, i1 = max(0, i0), min(len(df) - 1, i1)
    lo, hi = f"{df.index[i0]:%Y-%m-%d}", f"{df.index[i1]:%Y-%m-%d}"
    return [d for d in sorted(halts) if lo <= d <= hi]


# ---------------------------------------------------------------- 이동평균 · 거래량
MA_PERIODS = (5, 10, 20, 50, 60, 120)
MA_NAMES = {5: "5일선", 10: "10일선", 20: "20일선(생명선)", 50: "50일선", 60: "60일선(수급선)", 120: "120일선(경기선)"}


def sma(x, n: int) -> np.ndarray:
    """단순이동평균, 오늘 포함 (n봉 미만은 NaN)."""
    return pd.Series(np.asarray(x, dtype=float)).rolling(n, min_periods=n).mean().to_numpy()


def ema(x, n: int) -> np.ndarray:
    """지수이동평균 (indicators.ema 와 같은 정의 — span=n, adjust=False, n봉 미만 NaN)."""
    return pd.Series(np.asarray(x, dtype=float)).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def prior_mean(x, n: int, volume=None) -> np.ndarray:
    """당일을 뺀 직전 n봉 평균 — '평균의 k배' 비율 기준선 (부록 §0.2).

    volume 을 주면 거래량 0(거래정지 · NaN) 행을 평균에서 뺀다(부록 §0.2 — 직전 종가로 채운 행이 평균을 왜곡):
    봉 t 값 = t 전 거래량 > 0 인 마지막 n봉의 x 평균(모자라면 NaN). 0 행이 없으면 volume 없이 부른 값과 똑같다.
    봉 t 값은 [0..t−1] 만 쓴다 — 앞부분 불변."""
    x = np.asarray(x, dtype=float)
    plain = pd.Series(x).shift(1).rolling(n, min_periods=n).mean().to_numpy()
    if volume is None:
        return plain
    with np.errstate(invalid="ignore"):
        act = np.asarray(volume, dtype=float) > 0
    if act.all():
        return plain
    out = np.full(len(x), np.nan)
    idx = np.flatnonzero(act)
    if n < 1 or len(idx) < n:
        return out
    r = pd.Series(x[idx]).rolling(n, min_periods=n).mean().to_numpy()   # 거래 봉끼리 n봉 평균
    k = np.searchsorted(idx, np.arange(len(x)), side="left")            # 봉 t 전 거래 봉 수
    ok = k >= n
    out[ok] = r[k[ok] - 1]
    return out


def vol_ma(volume, n: int = 5) -> np.ndarray:
    """거래량 이동평균, 오늘 포함 — 5일 거래량 이평(MA5V_t = mean(V[t−4..t]), 키움 관례)."""
    return sma(volume, n)


def vol_ratio(volume, n: int) -> np.ndarray:
    """당일 거래량 / 직전 n봉 평균(당일 제외, 거래량 0 행 제외 — 부록 §0.2)."""
    v = np.asarray(volume, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return v / prior_mean(v, n, volume=v)


def ma_lines(close, periods=MA_PERIODS) -> dict[int, np.ndarray]:
    return {n: sma(close, n) for n in periods}


def ma_snapshot(close, t: int, periods=MA_PERIODS) -> dict[int, dict]:
    """봉 t 의 이평 값과 종가 위 여부 {n: {'name', 'value', 'above'}} — 이력 부족이면 value · above 가 None."""
    c = np.asarray(close, dtype=float)[:t + 1]
    out = {}
    for n in periods:
        m = sma(c, n)[t] if len(c) else np.nan
        v = _f(m)
        out[n] = {"name": MA_NAMES.get(n, f"{n}일선"), "value": v,
                  "above": None if v is None else bool(_gt(c[t], v))}
    return out


def cross_above(x, ref, t: int) -> bool:
    """x 가 ref 를 아래에서 위로 — x[t−1] ≤ ref[t−1] 이고 x[t] > ref[t] (키움 돌파 정의). NaN 이면 False."""
    if t < 1:
        return False
    return bool(_gt(x[t], ref[t]) and _le(x[t - 1], ref[t - 1]))


def count_up(close, t: int, n: int) -> int:
    """봉 t 에서 끝나는 n봉 중 종가가 전일보다 오른 날 수."""
    c = np.asarray(close, dtype=float)
    lo = max(1, t - n + 1)
    return int(sum(1 for i in range(lo, t + 1) if _gt(c[i], c[i - 1])))


def up_streak(close, t: int) -> int:
    """봉 t 에서 끝나는 연속 상승 종가 일수."""
    c = np.asarray(close, dtype=float)
    k = 0
    while t - k >= 1 and _gt(c[t - k], c[t - k - 1]):
        k += 1
    return k


def ols_slope(y) -> float:
    """최소제곱 기울기(값/봉). 유한값 3개 미만이면 NaN."""
    y = np.asarray(y, dtype=float)
    x = np.arange(len(y), dtype=float)
    m = np.isfinite(y)
    if m.sum() < 3:
        return float("nan")
    return float(np.polyfit(x[m], y[m], 1)[0])


# ---------------------------------------------------------------- 스윙 (확인 봉 뒤에만)
@dataclass(frozen=True)
class Swing:
    i: int           # 고점 · 저점 봉
    price: float
    kind: str        # 'H' | 'L'
    confirm_i: int   # 이 봉의 EOD 부터 쓸 수 있다 (= i + k)


def _swings(x, k: int, left: int | None, strict_left: bool, kind: str) -> list[Swing]:
    x = np.asarray(x, dtype=float)
    left = k if left is None else left
    w = left + k + 1
    if k < 1 or len(x) < w:
        return []
    win = sliding_window_view(x, w)
    ctr = win[:, left]
    rgt = win[:, left + 1:]
    if kind == "H":
        lft = win[:, :left].max(axis=1) if left else np.full(len(ctr), -np.inf)
        ok_l = ctr > lft if strict_left else ctr >= lft
        ok = ok_l & (ctr > rgt.max(axis=1))
    else:
        lft = win[:, :left].min(axis=1) if left else np.full(len(ctr), np.inf)
        ok_l = ctr < lft if strict_left else ctr <= lft
        ok = ok_l & (ctr < rgt.min(axis=1))
    return [Swing(int(j + left), float(x[j + left]), kind, int(j + left + k)) for j in np.flatnonzero(ok)]


def swing_highs(high, k: int = 3, left: int | None = None, strict_left: bool = False) -> list[Swing]:
    """확정 소고점: H[p] ≥ max(H[p−left..p−1]) 이고 H[p] > max(H[p+1..p+k]). confirm_i = p + k.

    부록 §4.2 TL_PIVOT_K=3 식 그대로(왼쪽은 같은 값 허용, 오른쪽은 엄격 → 같은 고가 둘이면 뒤 봉이 고점).
    부록 괄호의 '같은 값은 왼쪽 봉이 이긴다' 와 어긋나 식을 따랐다. strict_left=True 면 양쪽 엄격(fractal2: k=2).
    배열 끝 k봉 안의 고점은 아직 확정되지 않아 나오지 않는다 — 앞부분 불변."""
    return _swings(high, k, left, strict_left, "H")


def swing_lows(low, k: int = 3, left: int | None = None, strict_left: bool = False) -> list[Swing]:
    """확정 소저점: L[p] ≤ min(L[p−left..p−1]) 이고 L[p] < min(L[p+1..p+k]). confirm_i = p + k."""
    return _swings(low, k, left, strict_left, "L")


def swings_known_at(swings: list[Swing], t: int) -> list[Swing]:
    """봉 t EOD 에 알 수 있는 스윙만 (confirm_i ≤ t)."""
    return [s for s in swings if s.confirm_i <= t]


# ---------------------------------------------------------------- 월봉 · 주봉
PERIOD_COLUMNS = ["open", "high", "low", "close", "volume", "v_avg", "days", "first", "last", "complete", "gap_before"]


def _last_session(period: pd.Period) -> pd.Timestamp:
    """기간의 마지막 KRX 거래일 (주말 · krx 휴장일 표 제외)."""
    d = period.end_time.normalize()
    start = period.start_time.normalize()
    one = pd.Timedelta(1, "D")       # Timedelta(days=1) 은 pandas 2.3 · numpy 2.5 에서 DeprecationWarning(앞으로 오류)
    while d >= start:
        if d.weekday() < 5 and f"{d:%m-%d}" not in krx.FIXED_HOLIDAYS and f"{d:%Y-%m-%d}" not in krx.KRX_EXTRA_HOLIDAYS:
            return d
        d -= one
    return start


def period_bars(df: pd.DataFrame, freq: str, *, drop_zero_volume: bool = True,
                complete_rule: str = "next_bar") -> pd.DataFrame:
    """일봉 → 기간봉 (freq 'M' 달력 월, 'W-SUN' 월~일 주). 인덱스 = pd.Period.

    open 첫 행 시가 · high 최대 · low 최소 · close 마지막 행 종가 · volume 합 · v_avg 평균 일거래량 · days 거래일 수 ·
    first/last 첫 · 마지막 거래일 · gap_before 바로 앞 기간에 봉이 하나도 없음(장기 정지 — 건너서 연속 판정 금지).
    complete_rule
      'next_bar' (기본): 완성 = 그 뒤 기간의 봉이 있음 → 마지막 기간은 언제나 미완성(complete=False). 월말 EOD 에도
                         하루 늦게 확정되지만 앞부분 불변이 구조로 보장된다.
      'calendar'       : 마지막 기간도 그 기간 마지막 KRX 거래일 봉이 있으면 완성(krx 휴장일 표 범위 밖은 틀릴 수 있음).
    drop_zero_volume: 거래량 0 행 제외(부록 §0.2 구현 선택)."""
    d = df
    if drop_zero_volume and "volume" in d.columns:
        d = d[d["volume"] > 0]
    if len(d) == 0:
        return pd.DataFrame(columns=PERIOD_COLUMNS)
    key = d.index.to_period(freq)
    g = d.groupby(key, sort=True)
    vol = d["volume"].astype(float) if "volume" in d.columns else pd.Series(np.nan, index=d.index)
    dates = pd.Series(d.index, index=d.index)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
        "volume": vol.groupby(key).sum(), "v_avg": vol.groupby(key).mean(), "days": g.size(),
        "first": dates.groupby(key).first(), "last": dates.groupby(key).last(),
    })
    comp = np.ones(len(out), dtype=bool)
    comp[-1] = False
    if complete_rule == "calendar":
        comp[-1] = bool(out["last"].iloc[-1].normalize() >= _last_session(out.index[-1]))
    elif complete_rule != "next_bar":
        raise ValueError(f"complete_rule: {complete_rule!r}")
    out["complete"] = comp
    ords = np.array([p.ordinal for p in out.index])
    out["gap_before"] = np.r_[False, np.diff(ords) > 1]
    return out


def monthly_bars(df: pd.DataFrame, **kw) -> pd.DataFrame:
    """월봉 (달력 월). 진행 중 달은 complete=False — 판정은 완성 월만, 진행 중 달은 '이번 달 진행 · 미완성' 관찰로만."""
    return period_bars(df, "M", **kw)


def weekly_bars(df: pd.DataFrame, **kw) -> pd.DataFrame:
    """주봉 (월~일). 진행 중 주는 complete=False."""
    return period_bars(df, "W-SUN", **kw)


def weekly_trend(df: pd.DataFrame, n: int = 10) -> dict:
    """마지막 완성 주봉 종가와 완성 주봉 n주 SMA — 완성 주 n개 미만이면 sma · above = None(모름). df 는 이미 t 까지."""
    w = weekly_bars(df)
    w = w[w["complete"]] if len(w) else w
    out = {"weeks": int(len(w)), "week": None, "close": None, "sma": None, "above": None,
           "origin": ORIGIN["weekly_10w"]}
    if len(w) == 0:
        return out
    out["week"] = str(w.index[-1])
    out["close"] = float(w["close"].iloc[-1])
    if len(w) >= n:
        s = float(w["close"].iloc[-n:].mean())
        out["sma"] = s
        out["above"] = bool(_gt(out["close"], s))
    return out


# ---------------------------------------------------------------- 피보나치
FIB_RATIOS = (0.236, 0.382, 0.5, 0.618)      # 0.618 = 표시 + 무효선
FIB_LEVELS_BUY = (0.236, 0.382, 0.5)
FIB_LEVEL_INVALID = 0.618
FIB_TOL = 0.015                              # 구현 선택 (ORIGIN['fib_tol'])
FIB_APPROACH_PCT = 0.03                      # 구현 선택


def fib_levels(high: float, low: float, ratios=FIB_RATIOS) -> dict[float, float]:
    """되돌림 라인 lv(r) = H − r·(H − L). H = 고점 봉 고가, L = 저점 봉 저가."""
    return {r: float(high - r * (high - low)) for r in ratios}


def next_deeper(r: float, ratios=FIB_RATIOS) -> float | None:
    """다음 깊은 라인 (23.6→38.2→50→61.8) — 손절 기준. 가장 깊으면 None."""
    rs = sorted(ratios)
    for x in rs:
        if x > r + 1e-12:
            return x
    return None


def retracement(high: float, low: float, price: float) -> float:
    """(H − price) / (H − L). H ≤ L 이면 NaN."""
    return float((high - price) / (high - low)) if high > low else float("nan")


def in_zone(price: float, level: float, tol: float = FIB_TOL) -> bool:
    """level × (1 ± tol) 안 (경계 포함)."""
    return bool(_ge(price, level * (1 - tol)) and _le(price, level * (1 + tol)))


def fib_touch(low: float, close: float, level: float, next_level: float | None = None,
              tol: float = FIB_TOL, mode: str = "wick") -> bool:
    """라인 지지 접촉 (부록 §3.2 3c).

    'wick' (기본): 저가 ≤ lv×(1+tol) 이고 종가 ≥ lv 이고 저가 > 다음 깊은 라인(없으면 생략).
    'band' (스펙 원안): lv×(1−tol) ≤ 저가 ≤ lv×(1+tol) 이고 종가 ≥ lv."""
    if mode == "wick":
        ok = _le(low, level * (1 + tol)) and _ge(close, level)
        return bool(ok and (next_level is None or _gt(low, next_level)))
    if mode == "band":
        return bool(in_zone(low, level, tol) and _ge(close, level))
    raise ValueError(f"mode: {mode!r}")


def fib_touch_level(low: float, close: float, levels: dict[float, float], tol: float = FIB_TOL,
                    mode: str = "wick", buy=FIB_LEVELS_BUY) -> float | None:
    """매수 라인을 가장 깊은 것부터 보고 처음 접촉한 r (없으면 None). levels 에 0.618 이 있어야 0.5 의 wick 판정이 된다."""
    for r in sorted(buy, reverse=True):
        nr = next_deeper(r, tuple(levels))
        if fib_touch(low, close, levels[r], levels.get(nr) if nr is not None else None, tol, mode):
            return r
    return None


def fib_approach(close: float, level: float, pct: float = FIB_APPROACH_PCT) -> bool:
    """'눌림 진행(라인 접근)': lv < 종가 ≤ lv × (1 + pct)."""
    return bool(_gt(close, level) and _le(close, level * (1 + pct)))


# ---------------------------------------------------------------- 하향 추세선
@dataclass
class TrendlineConfig:
    pivot_k: int = 3               # TL_PIVOT_K — 소고점 좌우 3봉, p+3 부터 씀
    lookback: int = 250            # TL_LOOKBACK (구현 선택)
    anchor_mode: str = "highest"   # TL_ANCHOR_MODE 'highest' | 'volume' | 'both'
    anchor_vol_mult: float = 2.0   # TL_ANCHOR_VOL_MULT (구현 선택)
    anchor_vol_n: int = 50
    tol_cut: float = 0.005         # TL_TOL_CUT — 고가 ≤ 선 × 1.005 (구현 선택)
    tol_touch_below: float = 0.015 # TL_TOL_TOUCH_BELOW — 접점 선 × 0.985 이상
    min_touches: int = 3           # TL_MIN_TOUCHES (앵커 포함)
    bonus_touches: int = 5         # TL_BONUS_TOUCHES
    min_gap: int = 10              # TL_MIN_GAP (구현 선택)
    wide_gap: int = 13             # TL_WIDE_GAP
    min_len: int = 40              # TL_MIN_LEN (구현 선택)
    long_len: int = 48             # TL_LONG_LEN
    vol_mult: float = 1.5          # TL_VOL_MULT (돌파 거래량)
    vol_n: int = 50                # TL_VOL_N
    entry_trend_bars: int = 20     # 진입 추세 (구현 선택)


@dataclass
class TrendLine:
    """로그 눈금 직선 ln y = ln0 + slope·(i − anchor_i). 봉 t 종가를 시험하려고 t−1 까지 자료로 맞춘 선."""
    anchor_i: int
    anchor_price: float
    ln0: float
    slope: float                   # ln(가격)/봉 (음수 = 하향)
    touches: tuple[int, ...]
    t: int                         # 시험 봉 (선은 [anchor_i, t−1] 로 정함)
    valid: bool = False
    reasons: list[str] = field(default_factory=list)   # 무효 사유

    @property
    def length(self) -> int:
        return self.t - self.anchor_i

    @property
    def slope_pct(self) -> float:
        """봉당 % 변화 (e^b − 1)."""
        return math.expm1(self.slope) if math.isfinite(self.slope) else float("nan")

    @property
    def gaps(self) -> tuple[int, ...]:
        return tuple(int(g) for g in np.diff(self.touches))

    @property
    def median_gap(self) -> float:
        return float(np.median(self.gaps)) if self.gaps else float("nan")

    def value(self, i) -> float | np.ndarray:
        """봉 i 의 선 가격 (배열도 받는다). 돌파 뒤 동결 연장도 같은 식."""
        v = np.exp(self.ln0 + self.slope * (np.asarray(i, dtype=float) - self.anchor_i))
        return float(v) if np.ndim(v) == 0 else v

    def to_dict(self, dates: pd.DatetimeIndex | None = None) -> dict:
        d = {"anchor_i": self.anchor_i, "anchor_price": self.anchor_price, "slope_ln": _f(self.slope),
             "slope_pct": _f(self.slope_pct), "touches": list(self.touches), "touch_count": len(self.touches),
             "gaps": list(self.gaps), "median_gap": _f(self.median_gap), "length": self.length, "t": self.t,
             "valid": self.valid, "reasons": list(self.reasons)}
        if dates is not None:
            d["touch_dates"] = [f"{dates[i]:%Y-%m-%d}" for i in self.touches if 0 <= i < len(dates)]
        return d


def _tl_anchors(P: list[Swing], V: np.ndarray, cfg: TrendlineConfig) -> list[int]:
    if not P:
        return []
    hi = max(P, key=lambda s: (s.price, -s.i)).i      # 같은 값이면 이른 봉
    vol = []
    if cfg.anchor_mode in ("volume", "both"):
        n = cfg.anchor_vol_n
        for s in P:
            if s.i >= n:
                base = float(np.mean(V[s.i - n:s.i]))
                if base > 0 and _ge(V[s.i], cfg.anchor_vol_mult * base):
                    vol.append(s.i)
    if cfg.anchor_mode == "highest":
        return [hi]
    if cfg.anchor_mode == "volume":
        return vol
    if cfg.anchor_mode == "both":
        return sorted(set([hi] + vol))
    raise ValueError(f"anchor_mode: {cfg.anchor_mode!r}")


def _tl_from_anchor(A: int, P: list[Swing], lnH: np.ndarray, C: np.ndarray, t: int,
                    cfg: TrendlineConfig, H: np.ndarray | None = None) -> TrendLine:
    ap = float(H[A]) if H is not None else float(math.exp(lnH[A]))   # 앵커 고가 그대로(exp(log) 부동소수 잡음 없이)
    line = TrendLine(anchor_i=A, anchor_price=ap, ln0=float(lnH[A]), slope=float("nan"), touches=(A,), t=t)
    if A >= t - 1:
        line.reasons.append("앵커 뒤 봉 없음")
        return line
    # 앵커에서 선을 내려 돌리다 처음 닿는 곳(허용 +0.5%)에서 멈춤 — (A, t−1] 모든 고가 ≤ 선 × (1+tol_cut)
    i = np.arange(A + 1, t)
    b = float(np.max((lnH[A + 1:t] - math.log1p(cfg.tol_cut) - lnH[A]) / (i - A)))
    line.slope = b
    if not b < 0:
        line.reasons.append("하향선 아님 (기울기 ≥ 0)")
        return line
    lv = lnH[A] + b * (np.arange(A, t) - A)
    cut = np.flatnonzero(C[A:t] > np.exp(lv) * (1 + EPS))
    if cut.size:
        line.reasons.append(f"선 위 종가 {cut.size}봉 — 이미 지난 돌파(낡은 선)")
    lo_tol, hi_tol = math.log1p(-cfg.tol_touch_below), math.log1p(cfg.tol_cut)
    touches = [A]
    for s in P:
        if s.i <= A:
            continue
        lp = lnH[A] + b * (s.i - A)
        if lp + lo_tol - 1e-12 <= lnH[s.i] <= lp + hi_tol + 1e-12 and s.i - touches[-1] >= cfg.min_gap:
            touches.append(s.i)
    line.touches = tuple(touches)
    if len(touches) < cfg.min_touches:
        line.reasons.append(f"접점 {len(touches)}개 (최소 {cfg.min_touches})")
    if t - A < cfg.min_len:
        line.reasons.append(f"길이 {t - A}봉 (최소 {cfg.min_len})")
    line.valid = not line.reasons
    return line


def downtrend_line_candidates(b: Bars, t: int, cfg: TrendlineConfig | None = None,
                             swings: list[Swing] | None = None) -> list[TrendLine]:
    """봉 t 종가를 시험할 하향 추세선 후보(앵커마다 하나, 무효 포함 — '왜 아닌지' 용). t−1 까지의 자료만 쓴다.

    부록 §4.4 1~6단계: 확정 소고점 P_t(p ≥ t − lookback, p + k ≤ t − 1) → 앵커 → 가장 낮게 붙는 선
    b* = max_{i∈(A,t−1]} (ln H[i] − ln(1+tol_cut) − ln H[A])/(i − A) → 종가 관통 검사 → 접점(앞에서부터 탐욕) → 유효.
    swings 를 주면(전체 배열로 미리 센 swing_highs) 그중 confirm_i ≤ t−1 만 쓴다 — 결과는 같고 빠르다.
    t = b.n 도 받는다: 아직 없는 다음 봉을 시험할 선(오늘까지 자료로 맞춤 — 실시간 감시 · '돌파 임박' 피벗)."""
    cfg = cfg or TrendlineConfig()
    if t < 2 or t > b.n:
        return []
    H, C, V = b.high[:t], b.close[:t], b.volume[:t]
    if not np.all(H > 0):
        return []
    sw = swing_highs(H, k=cfg.pivot_k) if swings is None else [s for s in swings if s.kind == "H"]
    P = sorted((s for s in sw if s.confirm_i <= t - 1 and s.i >= t - cfg.lookback), key=lambda s: s.i)
    lnH = np.log(H)
    return [_tl_from_anchor(A, P, lnH, C, t, cfg, H) for A in _tl_anchors(P, V, cfg)]


def fit_downtrend_line(b: Bars, t: int, cfg: TrendlineConfig | None = None,
                       swings: list[Swing] | None = None) -> TrendLine | None:
    """유효한 후보 중 (접점 수, 길이, −|기울기|) 가 가장 큰 선 — 없으면 None (부록 §4.4 7단계, Bulkowski QTL)."""
    ok = [ln for ln in downtrend_line_candidates(b, t, cfg, swings) if ln.valid]
    if not ok:
        return None
    return max(ok, key=lambda ln: (len(ln.touches), ln.length, -abs(ln.slope)))


def line_cross(line: TrendLine, b: Bars, t: int) -> bool:
    """돌파 = 종가가 선 위 (C[t] > 선(t), C[t−1] ≤ 선(t−1)). 장중 고가만 넘은 봉은 돌파 아님."""
    if t < 1 or t >= b.n:
        return False
    return bool(_gt(b.close[t], line.value(t)) and _le(b.close[t - 1], line.value(t - 1)))


def line_features(line: TrendLine, b: Bars, cfg: TrendlineConfig | None = None) -> dict:
    """점수 재료 (봉 line.t 까지만): 접점 · 간격 · 길이 · 기울기 · 돌파 전 거래량 추세 · 진입 추세 · 돌파일 거래량 비율."""
    cfg = cfg or TrendlineConfig()
    t, A = line.t, line.anchor_i
    b = b.cut(min(t, b.n - 1))
    V, C = b.volume, b.close
    seg = V[A:t]
    vslope = ols_slope(seg)
    vmean = float(np.mean(seg)) if len(seg) else float("nan")
    vol_trend_pct = vslope / vmean if vmean and math.isfinite(vslope) else float("nan")
    n = cfg.entry_trend_bars
    entry = math.expm1(ols_slope(np.log(C[A - n:A]))) if A >= n and np.all(C[A - n:A] > 0) else float("nan")
    vr = None
    if t < b.n and t >= cfg.vol_n:
        base = float(np.mean(V[t - cfg.vol_n:t]))
        vr = float(V[t] / base) if base > 0 else None
    lt = line.value(t)
    return {
        "touch_count": len(line.touches), "touch_bonus": len(line.touches) >= cfg.bonus_touches,
        "median_gap": _f(line.median_gap), "wide_gap": bool(line.median_gap > cfg.wide_gap) if line.gaps else False,
        "length": line.length, "long": line.length > cfg.long_len,
        "slope_pct": _f(line.slope_pct),
        "vol_trend_pct": _f(vol_trend_pct), "vol_declining": bool(vol_trend_pct < 0) if math.isfinite(vol_trend_pct) else None,
        "entry_trend_pct": _f(entry),
        "break_vol_ratio": vr, "break_vol_ok": None if vr is None else bool(_ge(vr, cfg.vol_mult)),
        "line_t": _f(lt), "close_vs_line": _f(C[t] / lt - 1) if t < b.n else None,
        "origin": {k: ORIGIN[k] for k in ("tl_bonus_touches", "tl_wide_gap", "tl_long_len", "tl_vol_trend",
                                          "tl_entry_trend", "tl_break_vol", "tl_log")},
    }


def line_targets(line: TrendLine, b: Bars, t0: int) -> dict:
    """(표시만) T1 = 앵커 고가 · T2 = 돌파가 + 0.56 × D, D = 마지막 접점 ~ 돌파일 max(선 − 저가). 돌파가 = 돌파일 선 값."""
    p = line.touches[-1]
    idx = np.arange(p, t0 + 1)
    D = float(np.max(line.value(idx) - b.low[p:t0 + 1])) if t0 >= p else float("nan")
    bp = line.value(t0)
    return {"t1": line.anchor_price, "t2": _f(bp + 0.56 * D), "D": _f(D), "break_price": _f(bp),
            "origin": ORIGIN["tl_target"], "note": bulkowski_note("trendline_down")}


# ---------------------------------------------------------------- 망치형 (부록 §4.3)
@dataclass
class HammerConfig:
    lower_x: float = 2.0           # HM_LOWER_X
    upper_x: float = 0.1           # HM_UPPER_X (× 직전 10봉 평균 범위)
    range_rel: float = 1.0         # HM_RANGE_REL (구현 선택)
    avg_n: int = 10
    ema_n: int = 20                # HM_PRIOR_DECLINE
    yearly_n: int = 252            # HM_YEARLY_POS_MAX 창
    yearly_pos_max: float = 1 / 3
    confirm_bars: int = 3          # HM_CONFIRM_BARS


HAMMER_ORIGIN = {k: ORIGIN[k] for k in ("hammer_lower", "hammer_upper", "hammer_range", "hammer_decline",
                                        "hammer_yearly", "hammer_confirm", "hammer_doji")}


def hammer_frame(b: Bars, cfg: HammerConfig | None = None) -> pd.DataFrame:
    """봉마다 망치형 판정 (모두 그 봉까지의 자료). 열:
    shape(모양 — 아래꼬리 ≥ 2×몸통 · 위꼬리 ≤ 0.1×평균범위 · 범위 ≥ 평균범위, 평균은 직전 10봉) · doji · white ·
    prior_decline(직전 종가 < EMA20) · prior_decline_known · yearly_pos(252봉 연중 위치) · bottom(바닥권 = 둘 다) · bottom_known."""
    cfg = cfg or HammerConfig()
    O, H, L, C = b.open, b.high, b.low, b.close
    body = np.abs(C - O)
    lower = np.minimum(O, C) - L
    upper = H - np.maximum(O, C)
    rng = H - L
    avg = prior_mean(rng, cfg.avg_n)
    with np.errstate(invalid="ignore"):
        shape = (rng > 0) & np.isfinite(avg) & _ge(lower, cfg.lower_x * body) & _le(upper, cfg.upper_x * avg) \
            & _ge(rng, cfg.range_rel * avg)
    e = ema(C, cfg.ema_n)
    e_prev = np.r_[np.nan, e[:-1]]
    c_prev = np.r_[np.nan, C[:-1]]
    pd_known = np.isfinite(e_prev)
    prior_decline = pd_known & (c_prev < e_prev)
    hh = pd.Series(H).rolling(cfg.yearly_n, min_periods=cfg.yearly_n).max().to_numpy()
    ll = pd.Series(L).rolling(cfg.yearly_n, min_periods=cfg.yearly_n).min().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ypos = np.where(hh > ll, (C - ll) / (hh - ll), np.nan)
    y_known = np.isfinite(ypos)
    bottom = prior_decline & y_known & _le(ypos, cfg.yearly_pos_max)
    idx = b.dates if b.dates is not None else pd.RangeIndex(b.n)
    return pd.DataFrame({"shape": shape, "doji": body == 0, "white": C > O, "lower": lower, "body": body,
                         "upper": upper, "range": rng, "avg_range": avg, "prior_decline": prior_decline,
                         "prior_decline_known": pd_known, "yearly_pos": ypos, "bottom": bottom,
                         "bottom_known": pd_known & y_known}, index=idx)


def hammer(b: Bars, j: int, cfg: HammerConfig | None = None) -> dict:
    """봉 j 의 망치형 판정 dict. 직전 10봉이 없으면 shape=None(모름). 여러 봉이면 hammer_frame 을 한 번 쓴다."""
    cfg = cfg or HammerConfig()
    if j < 0:
        j += b.n
    r = hammer_frame(b.cut(j), cfg).iloc[j]
    known = math.isfinite(r["avg_range"])
    label = "doji-hammer" if r["doji"] else ("양봉 망치" if r["white"] else "음봉 망치")
    return {
        "j": j, "date": b.date(j), "shape": bool(r["shape"]) if known else None, "label": label,
        "white": bool(r["white"]), "doji": bool(r["doji"]),
        "lower_x": _f(r["lower"] / r["body"]) if r["body"] > 0 else None,
        "upper_ratio": _f(r["upper"] / r["avg_range"]) if known and r["avg_range"] > 0 else None,
        "range_rel": _f(r["range"] / r["avg_range"]) if known and r["avg_range"] > 0 else None,
        "prior_decline": bool(r["prior_decline"]) if r["prior_decline_known"] else None,
        "yearly_pos": _f(r["yearly_pos"]),
        "bottom": bool(r["bottom"]) if r["bottom_known"] else None,
        "origin": HAMMER_ORIGIN,
    }


def is_hammer(b: Bars, j: int, cfg: HammerConfig | None = None) -> bool:
    """망치 모양만 (바닥권 조건 없음). 이력 부족이면 False."""
    return bool(hammer(b, j, cfg)["shape"])


def hammer_confirm(b: Bars, j: int, upto: int, cfg: HammerConfig | None = None) -> int | None:
    """망치 확인 사건: j 뒤 confirm_bars 봉 안(upto 까지만)에서 종가 > 망치 고가인 첫 봉 — 신호와 다른, 더 늦은 날짜."""
    cfg = cfg or HammerConfig()
    for k in range(j + 1, min(j + cfg.confirm_bars, upto, b.n - 1) + 1):
        if _gt(b.close[k], b.high[j]):
            return k
    return None


# ---------------------------------------------------------------- 장대양봉 (부록 §3.1 LB_*)
@dataclass
class LongWhiteConfig:
    min_chg: float = 0.07          # LB_MIN_CHG (전일 종가 대비, 0.10 옵션)
    body_rel_k: float = 3.0        # LB_BODY_REL_K (완화 2.0)
    body_rel_n: int = 15           # LB_BODY_REL_N (완화 22)
    vol_mult: float = 2.0          # LB_VOL_MULT
    vol_n: int = 20                # LB_VOL_N (당일 제외)


LW_ORIGIN = {k: ORIGIN[k] for k in ("white", "lw_chg", "lw_body", "lw_shadow", "lw_vol", "baseline_excl_today",
                                    "halt_rows", "lw_zero_base")}


def long_white_frame(b: Bars, cfg: LongWhiteConfig | None = None) -> pd.DataFrame:
    """봉마다 장대양봉(기준봉) 판정 — 양봉 · 전일 대비 +7% · 몸통 ≥ 직전 15봉 평균 몸통 × 3 · 위 · 아래 꼬리 < 몸통 ·
    거래량 ≥ 직전 20봉 평균 × 2 를 모두(AND). 두 기준선 모두 당일 제외 · 거래량 0(정지) 행 제외(부록 §0.2).
    known = 기준선 이력이 있고 0 이 아님 — 기준선 0 이면 배수가 무한이라 통과가 아니라 모름(ORIGIN['lw_zero_base'])."""
    cfg = cfg or LongWhiteConfig()
    O, H, L, C, V = b.open, b.high, b.low, b.close, b.volume
    body = C - O
    prev = np.r_[np.nan, C[:-1]]
    with np.errstate(divide="ignore", invalid="ignore"):
        chg = C / prev - 1
        avg_body = prior_mean(np.abs(body), cfg.body_rel_n, volume=V)
        vbase = prior_mean(V, cfg.vol_n, volume=V)
        vr = V / vbase
        base_ok = (avg_body > 0) & (vbase > 0)
    white = _gt(C, O)
    chg_ok = _ge(chg, cfg.min_chg)
    body_ok = _ge(body, cfg.body_rel_k * avg_body) & (avg_body > 0)
    shadows_ok = _lt(H - C, body) & _lt(O - L, body)
    vol_ok = _ge(vr, cfg.vol_mult) & (vbase > 0)
    known = np.isfinite(prev) & np.isfinite(avg_body) & np.isfinite(vbase) & base_ok
    idx = b.dates if b.dates is not None else pd.RangeIndex(b.n)
    return pd.DataFrame({"white": white, "chg": chg, "chg_ok": chg_ok, "body": body, "avg_body": avg_body,
                         "body_ok": body_ok, "shadows_ok": shadows_ok, "vol_ratio": vr, "vol_ok": vol_ok,
                         "known": known, "ok": known & white & chg_ok & body_ok & shadows_ok & vol_ok}, index=idx)


def long_white(b: Bars, t: int, cfg: LongWhiteConfig | None = None) -> dict:
    """봉 t 장대양봉 판정 dict (조건별 통과 · 값 · 출처). 이력 부족이면 ok=False, known=False."""
    if t < 0:
        t += b.n
    r = long_white_frame(b.cut(t), cfg).iloc[t]
    return {"t": t, "date": b.date(t), "ok": bool(r["ok"]), "known": bool(r["known"]), "white": bool(r["white"]),
            "chg": _f(r["chg"]), "chg_ok": bool(r["chg_ok"]),
            "body_rel": _f(r["body"] / r["avg_body"]) if r["avg_body"] and math.isfinite(r["avg_body"]) else None,
            "body_ok": bool(r["body_ok"]), "shadows_ok": bool(r["shadows_ok"]),
            "vol_ratio": _f(r["vol_ratio"]), "vol_ok": bool(r["vol_ok"]), "origin": LW_ORIGIN}


def volume_reversal(b: Bars, t: int, *, test: str = "cross", require_up_close: bool = True) -> dict:
    """거래량 실린 반등 양봉 (부록 §3.1): 양봉 · (전일보다 높은 종가) · 거래량이 5일 거래량 이평(오늘 포함) 위.

    test='cross' (기본, 키움 상향돌파): V_t > MA5V_t 이고 V_{t−1} ≤ MA5V_{t−1}.  test='level' (스펙 원문): V_t > MA5V_t."""
    if t < 0:
        t += b.n
    b = b.cut(t)
    O, C, V = b.open, b.close, b.volume
    m5 = vol_ma(V, 5)
    white = bool(_gt(C[t], O[t]))
    up = bool(t >= 1 and _gt(C[t], C[t - 1]))
    above = bool(_gt(V[t], m5[t]))
    if test == "cross":
        vol_ok = above and t >= 1 and bool(_le(V[t - 1], m5[t - 1]))
    elif test == "level":
        vol_ok = above
    else:
        raise ValueError(f"test: {test!r}")
    ok = white and vol_ok and (up or not require_up_close)
    return {"t": t, "date": b.date(t), "ok": bool(ok), "white": white, "up_close": up, "vol_ok": bool(vol_ok),
            "volume": float(V[t]), "vol_ma5": _f(m5[t]), "vol_ma5_prev": _f(m5[t - 1]) if t >= 1 else None,
            "test": test,
            "origin": {"white": ORIGIN["white"], "vol_ma5": ORIGIN["vol_ma5"],
                       "vol_test": ORIGIN["vol_rev_cross" if test == "cross" else "vol_rev_level"],
                       "up_close": ORIGIN["vol_rev_upclose"]}}


# ---------------------------------------------------------------- 청산 계획 (표시만, 부록 §9)
@dataclass
class ExitConfig:
    ma1: int = 5                     # EXIT_MA1 — 5일선 종가 이탈 1차
    ma10: int = 10
    ma50: int = 50
    window: str = "next_day"         # EXIT_10D_WINDOW 'next_day' | 'until_reclaim'
    seven_week_bars: int = 35        # EXIT_7WK_BARS
    seven_week_mode: str = "edgerater"   # EXIT_7WK_MODE 'edgerater' | 'bulkowski'


def arm_days(close, ma, start: int = 1, end: int | None = None) -> list[int]:
    """무장일 d: C_d < MA_d 이고 C_{d−1} ≥ MA_{d−1} (이평 아래 첫 종가). 무장 자체는 위반이 아니다."""
    C, M = np.asarray(close, dtype=float), np.asarray(ma, dtype=float)
    end = len(C) - 1 if end is None else min(end, len(C) - 1)
    return [d for d in range(max(1, start), end + 1) if _lt(C[d], M[d]) and _ge(C[d - 1], M[d - 1])]


def ma_violation(d: int, close, low, ma, upto: int, window: str = "next_day") -> int | None:
    """무장일 d 의 위반 봉 k (없으면 None). 같은 저가는 위반 아님(엄격 <).

    'next_day': k = d+1 이고 Low_{d+1} < Low_d.
    'until_reclaim': d 뒤 종가가 이평을 되찾기(C ≥ MA) 전 어느 봉이든 Low_k < Low_d — 되찾는 봉 자신의 저가도 본다(종가 전 장중)."""
    C, L, M = np.asarray(close, float), np.asarray(low, float), np.asarray(ma, float)
    upto = min(upto, len(C) - 1)
    if window == "next_day":
        k = d + 1
        return k if k <= upto and _lt(L[k], L[d]) else None
    if window != "until_reclaim":
        raise ValueError(f"window: {window!r}")
    for k in range(d + 1, upto + 1):
        if _lt(L[k], L[d]):
            return k
        if _ge(C[k], M[k]):
            return None
    return None


def ma_violations(close, low, ma, start: int, upto: int, window: str = "next_day") -> list[tuple[int, int]]:
    """[start, upto] 의 무장일마다 위반 (d, k) 목록."""
    out = []
    for d in arm_days(close, ma, start, upto):
        k = ma_violation(d, close, low, ma, upto, window)
        if k is not None:
            out.append((d, k))
    return out


def seven_week_rule(held: int, early_v10: bool, cfg: ExitConfig | None = None) -> str:
    """7주 규칙 — 보유 held 봉째의 기준 이평 '10일선' | '50일선'. early_v10 = 보유 35봉 안에 10일선 위반이 있었음.

    'edgerater': 35봉 안(held ≤ 35)은 50일선, 그 뒤는 early_v10 이면 50일선 · 아니면 10일선.
    'bulkowski': held < 35 이면 50일선, 35 이상이면 10일선."""
    cfg = cfg or ExitConfig()
    if cfg.seven_week_mode == "bulkowski":
        return "50일선" if held < cfg.seven_week_bars else "10일선"
    if cfg.seven_week_mode != "edgerater":
        raise ValueError(f"seven_week_mode: {cfg.seven_week_mode!r}")
    if held <= cfg.seven_week_bars:
        return "50일선"
    return "50일선" if early_v10 else "10일선"


def violation_fill_price(open_k: float, low_d: float) -> float:
    """재현 채점 체결가(구현 선택): min(위반 봉 시가, 무장일 저가 − 1호가)."""
    return float(min(open_k, low_d - krx.krx_tick(low_d - 1e-6)))


def exit_plan(b: Bars, t: int | None = None, entry_i: int | None = None, cfg: ExitConfig | None = None) -> dict:
    """청산 계획 (표시만). 봉 t 까지만 본다.

    항상: 5 · 10 · 50일선 값, 오늘 5일선 종가 이탈(1차), 오늘 10일선 무장(→ '내일 저가 … 하회 시 위반'), 진행 중 무장,
          오늘이 10 · 50일선 위반 봉인지.
    entry_i(가정 진입 = 신호 봉)가 있으면: 진입 뒤 첫 5일선 이탈 · 10 · 50일선 위반 목록 · 7주 규칙 기준 이평 · 규칙상 첫 청산 봉."""
    cfg = cfg or ExitConfig()
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    b = b.cut(t)
    C, L, O = b.close, b.low, b.open
    m5, m10, m50 = sma(C, cfg.ma1), sma(C, cfg.ma10), sma(C, cfg.ma50)
    w = cfg.window
    out: dict[str, Any] = {
        "t": t, "date": b.date(t), "close": float(C[t]), "low": float(L[t]),
        "ma5": _f(m5[t]), "ma10": _f(m10[t]), "ma50": _f(m50[t]), "window": w,
        "seven_week_mode": cfg.seven_week_mode, "notes": [],
        "origin": {k: ORIGIN[k] for k in ("exit_ma5", "exit_ma10", "exit_until_reclaim", "exit_ma50",
                                          "exit_7wk_edgerater", "exit_7wk_bulkowski", "exit_arm_scope", "exit_fill", "sma")},
        "bulkowski": bulkowski_note("kacher_morales"),
    }
    out["ma5_break_today"] = None if out["ma5"] is None else bool(_lt(C[t], m5[t]))
    if out["ma5_break_today"]:
        out["notes"].append(f"1차: 5일선({m5[t]:,.0f}) 종가 이탈")
    arm_today = bool(t >= 1 and _lt(C[t], m10[t]) and _ge(C[t - 1], m10[t - 1]))
    out["ma10_arm_today"] = arm_today
    if arm_today:
        out["notes"].append(f"내일 저가 {L[t]:,.0f} 하회 시 10일선 위반(모랄레스)")
    # 진행 중 무장 (until_reclaim: 되찾기 전 · 위반 전)
    pending = None
    arms = arm_days(C, m10, 1, t)
    if arms:
        d = arms[-1]
        k = ma_violation(d, C, L, m10, t, w)
        reclaimed = any(_ge(C[i], m10[i]) for i in range(d + 1, t + 1))
        if k is None and not reclaimed and (w == "until_reclaim" or d == t):
            pending = {"d": d, "date": b.date(d), "low": float(L[d])}
            if w == "until_reclaim":
                out["notes"].append(f"기준 저가 {L[d]:,.0f} ({b.date(d) or d})")
    out["ma10_pending"] = pending
    lo = max(1, t - 1 if w == "next_day" else 1)
    out["ma10_violation_today"] = any(k == t for _, k in ma_violations(C, L, m10, lo, t, w))
    out["ma50_violation_today"] = any(k == t for _, k in ma_violations(C, L, m50, lo, t, w))
    if entry_i is None:
        return out
    if not 0 <= entry_i <= t:
        out["notes"].append(f"진입 봉 {entry_i} 이 봉 t={t} 밖 — 진입 뒤 계산 안 함")
        return out

    # 진입 뒤
    e = entry_i
    held = t - e
    v10 = ma_violations(C, L, m10, e, t, w)
    v50 = ma_violations(C, L, m50, e, t, w)
    first5 = next((k for k in range(e + 1, t + 1) if _lt(C[k], m5[k])), None)
    arm10 = {k: d for d, k in v10}          # 위반 봉 → 무장일
    arm50 = {k: d for d, k in v50}
    k10 = set(arm10)
    rule_exit = None
    for k in range(e + 1, t + 1):
        early = any(kk <= k and kk - e <= cfg.seven_week_bars for kk in k10)
        rule = seven_week_rule(k - e, early, cfg)
        arms = arm10 if rule == "10일선" else arm50
        if k in arms:
            d = arms[k]
            rule_exit = {"i": k, "date": b.date(k), "rule": rule, "arm_i": d,
                         "fill": violation_fill_price(O[k], L[d])}
            break
    early_now = any(kk - e <= cfg.seven_week_bars for kk in k10)
    active = seven_week_rule(held, early_now, cfg)
    out.update({
        "entry_i": e, "entry_date": b.date(e), "held": held, "active_rule": active,
        "first_ma5_exit": None if first5 is None else {"i": first5, "date": b.date(first5)},
        "ma10_violations": [{"arm_i": d, "i": k, "date": b.date(k)} for d, k in v10],
        "ma50_violations": [{"arm_i": d, "i": k, "date": b.date(k)} for d, k in v50],
        "rule_exit": rule_exit,
    })
    if active == "50일선" and out["ma50"] is not None:
        out["notes"].append(f"모랄레스식으로는 신호 뒤 {cfg.seven_week_bars}거래일 동안 50일선({m50[t]:,.0f}) 위반이 기준"
                            if held <= cfg.seven_week_bars else f"7주 규칙: 50일선({m50[t]:,.0f}) 위반이 기준")
    elif active == "10일선":
        out["notes"].append("7주 규칙: 10일선 위반이 기준")
    return out


# ---------------------------------------------------------------- 체크리스트 10 (부록 §8)
PASS, WARN, UNKNOWN = "pass", "warn", "unknown"
STATUS_LABELS = {PASS: "통과", WARN: "경고", UNKNOWN: "모름"}


@dataclass
class CheckItem:
    no: int
    name: str
    status: str                    # PASS | WARN | UNKNOWN
    value: Any = None
    note: str = ""
    origin: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status_label"] = self.status_label
        return d


@dataclass
class ChecklistInputs:
    """체크리스트 외부 자료 — 없으면 None 그대로(그 항목은 '모름').

    entry        진입가 (None 이면 봉 t 종가)
    stop         기법 손절가
    market_state market.MarketState (ctx.market_state) — 봉 t 와 기준일이 다르면 메모
    sector       {'group': 업종, 'rank_pct': sector.py 업종 강도 백분위(1 = 최강), 'pos52': 구성 종목 연중 위치 중앙값}
    industry_rs  {'group', 'rank_pct'(1 = 최강), 'members'} — industry_rs_table 한 행 (6개월 수익률 평균 순위)
    replay       같은 기법의 이 종목 과거 신호 [{'date', 'ret20'}] — 봉 t 전에 20거래일이 지난 신호만 넣는다
    risk         공시위험 JSON(CHART_SCREENER_RISK_JSON)의 이 종목 항목 {'level', 'hits', 'ref'}
    value_row    저평가 목록 행(CHART_SCREENER_VALUE_JSON) — 'risk' 문자열"""
    entry: float | None = None
    stop: float | None = None
    market_state: Any = None
    sector: dict | None = None
    industry_rs: dict | None = None
    replay: list[dict] | None = None
    risk: dict | None = None
    value_row: dict | None = None


def inputs_from_ctx(ctx, *, entry: float | None = None, stop: float | None = None,
                    replay: list[dict] | None = None) -> ChecklistInputs:
    """StockContext → ChecklistInputs. ctx.info 키: 'groups'(sector.stock_groups 결과) · 'sector_pos52' · 'industry_rs' ·
    'replay' · 'risk' · 'undervalued' · 'market_state_eod'. 없는 키는 None(모름).
    'market_state_eod'(스캐너가 넣는 완성 봉 기준 시장 국면 — 장중이면 오늘 미완성 지수 봉을 뺀 판정)가 있으면
    ctx.market_state(장중 잠정일 수 있음) 대신 쓴다. 키가 있고 값이 None 이면 1번 '모름'."""
    info = getattr(ctx, "info", None) or {}
    g = info.get("groups") or {}
    sector = None
    if g.get("sector") is not None:
        # rank_partial: 업종 강도(sector.group_strength)는 스냅샷 그대로라 장중이면 오늘 미완성 봉이 섞인다 — 2번이 완성 봉
        # 판정에 그 값을 쓰지 않게 표시 (연중 위치 중앙값 pos52 는 industry_rs_table 이 완성 봉 기준일까지 잰 값)
        sector = {"group": g.get("sector"), "rank_pct": g.get("sector_rank_pct"), "pos52": info.get("sector_pos52"),
                  "rank_partial": bool(getattr(ctx, "partial", False))}
    ms = info["market_state_eod"] if "market_state_eod" in info else getattr(ctx, "market_state", None)
    return ChecklistInputs(entry=entry, stop=stop, market_state=ms, sector=sector,
                           industry_rs=info.get("industry_rs"), replay=replay if replay is not None else info.get("replay"),
                           risk=info.get("risk"), value_row=info.get("undervalued"))


@dataclass
class ChecklistConfig:
    sector_lead: float = 0.75       # 2: 업종 강도 백분위 ≥ 이면 주도 (구현 선택)
    sector_high_pos: float = 2 / 3  # 2: 구성 종목 연중 위치 중앙값 ≥ 이면 고점권
    sector_low_pos: float = 1 / 3
    weekly_ma: int = 10             # 3
    daily_ma: int = 50
    replay_min: int = 3             # 4
    ind_rs_top: float = 0.25        # 5: CK_IND_RS_TOP (⅓ 옵션)
    ind_rs_min_members: int = 3
    ma_short: int = 20              # 6
    ma_mid: int = 60
    res_lookback: int = 252         # 7: CK_RES_LOOKBACK
    res_warn_pct: float = 0.10      # 7: CK_RES_WARN_PCT
    res_pivot_k: int = 3
    vstop_mult: float = 2.0         # 8: CK_VSTOP_MULT
    vstop_n: int = 22               # 8: CK_VSTOP_N (최근 봉 포함)
    dcb_drop: float = 0.15          # 9: CK_DCB_DROP
    dcb_drop_pre: float = 0.145     # 9: 2015-06-15 전 (구현 선택)
    dcb_window: int = 126           # 9: CK_DCB_WINDOW
    dcb_ref_window: int = 252
    limit_change: str = "2015-06-15"   # 가격제한폭 ±15% → ±30%
    run_days: int = 5               # 10
    run_up_min: int = 4
    run_pct: float = 0.20           # 10: CK_RUN5_PCT
    streak_warn: int = 4            # 10: CK_STREAK_WARN


def _ck_market(b, t, x: ChecklistInputs, cfg) -> CheckItem:
    ms = x.market_state
    if ms is None or getattr(ms, "state", None) is None:
        return CheckItem(1, "시장 추세", UNKNOWN, None, "시장 국면 자료 없음", ORIGIN["ck1"])
    label = getattr(ms, "label", None) or STATE_LABELS.get(ms.state, ms.state)
    note = f"{getattr(ms, 'name', '')} {label}".strip()
    md, bd = getattr(ms, "date", None), b.date(t)
    if md and bd and md != bd:
        note += f" (국면 기준일 {md} — 봉 {bd} 와 다름)"
    return CheckItem(1, "시장 추세", PASS if ms.state == CONFIRMED else WARN, label, note, ORIGIN["ck1"])


def _ck_sector(b, t, x: ChecklistInputs, cfg) -> CheckItem:
    s = x.sector or {}
    g = s.get("group")
    if not g:
        return CheckItem(2, "산업 위치", UNKNOWN, None, "업종 매핑 없음", ORIGIN["ck2"])
    rank, pos = _f(s.get("rank_pct")), _f(s.get("pos52"))
    val = {"group": g, "rank_pct": rank, "pos52": pos}
    # 장중: 업종 강도 백분위는 오늘 미완성 봉이 섞인 값 — 완성 봉 판정에 쓰지 않는다. 연중 위치로 통과면 강도와 무관하게
    # 통과(완성 봉 판정도 통과), 고점권이면 '주도'로 통과일 수 있어 모름
    intraday = bool(s.get("rank_partial")) and rank is not None
    if intraday:
        val["rank_intraday"] = True
    if rank is not None and not intraday and _ge(rank, cfg.sector_lead):
        return CheckItem(2, "산업 위치", PASS, val, f"{g} 주도 (업종 강도 백분위 {rank:.2f})", ORIGIN["ck2"])
    skip = " · 업종 강도는 장중 값이라 안 씀" if intraday else ""
    if pos is None:
        return CheckItem(2, "산업 위치", UNKNOWN, val, f"{g} — 고점권 · 바닥권 판정 자료 없음{skip}", ORIGIN["ck2"])
    if _ge(pos, cfg.sector_high_pos):
        if intraday:
            return CheckItem(2, "산업 위치", UNKNOWN, val, f"{g} 고점권 (연중 위치 중앙값 {pos:.2f}) — 주도 여부(업종 강도)는 "
                             "장중 값이라 판정 안 함 (마감 뒤 다시)", ORIGIN["ck2"])
        return CheckItem(2, "산업 위치", WARN, val, f"{g} 고점권 (연중 위치 중앙값 {pos:.2f})", ORIGIN["ck2"])
    zone = "바닥권" if _le(pos, cfg.sector_low_pos) else "중간권"
    return CheckItem(2, "산업 위치", PASS, val, f"{g} {zone} (연중 위치 중앙값 {pos:.2f}){skip}", ORIGIN["ck2"])


def _ck_weekly(b, t, x, cfg) -> CheckItem:
    wk = weekly_trend(b.frame(), cfg.weekly_ma) if b.dates is not None else None
    s50 = sma(b.close, cfg.daily_ma)[t]
    if wk is None or wk["sma"] is None or not math.isfinite(s50):
        why = "주봉 날짜 없음" if wk is None else f"완성 주 {wk['weeks']}개 · 일봉 {t + 1}개"
        return CheckItem(3, "주봉 = 일봉 추세", UNKNOWN, None, f"이력 부족 ({why})", ORIGIN["ck3"])
    d_ok = bool(_gt(b.close[t], s50))
    val = {"week": wk["week"], "week_close": wk["close"], "sma10w": wk["sma"], "close": float(b.close[t]), "sma50": float(s50)}
    note = f"주봉 {'>' if wk['above'] else '≤'} 10주선 · 일봉 {'>' if d_ok else '≤'} 50일선 (진행 중 주 제외)"
    return CheckItem(3, "주봉 = 일봉 추세", PASS if wk["above"] and d_ok else WARN, val, note, ORIGIN["ck3"])


def _ck_replay(b, t, x, cfg) -> CheckItem:
    if x.replay is None:
        return CheckItem(4, "이 종목 과거 성취율", UNKNOWN, None, "재현 안 함", ORIGIN["ck4"])
    rets = [float(r["ret20"]) for r in x.replay if _f(r.get("ret20")) is not None]
    n = len(rets)
    if n < cfg.replay_min:
        return CheckItem(4, "이 종목 과거 성취율", UNKNOWN, {"n": n}, f"표본 적음 ({n}건)", ORIGIN["ck4"])
    med = float(np.median(rets))
    wins = sum(1 for r in rets if r > 0)
    val = {"n": n, "wins": wins, "median": med}
    note = f"우리 데이터 재현 {n}건 · 20거래일 뒤 오른 것 {wins}건 · 중앙값 {med:+.1%} (확률 아님)"
    return CheckItem(4, "이 종목 과거 성취율", PASS if med > 0 else WARN, val, note, ORIGIN["ck4"])


def _ck_ind_rs(b, t, x, cfg) -> CheckItem:
    r = x.industry_rs or {}
    rank, members = _f(r.get("rank_pct")), r.get("members")
    if not r.get("group") or rank is None or members is None or members < cfg.ind_rs_min_members:
        why = "업종 매핑 없음" if not r.get("group") else f"구성 종목 {members or 0}개 (최소 {cfg.ind_rs_min_members})"
        return CheckItem(5, "산업 상대강도", UNKNOWN, None, why, ORIGIN["ck5"])
    ok = _ge(rank, 1 - cfg.ind_rs_top)
    val = {"group": r["group"], "rank_pct": rank, "members": members, "rs": _f(r.get("rs"))}
    return CheckItem(5, "산업 상대강도", PASS if ok else WARN, val,
                     f"{r['group']} 업종 RS 백분위 {rank:.2f} ({'상위' if ok else '상위 밖'} {cfg.ind_rs_top:.0%})", ORIGIN["ck5"])


def _ck_uptrend(b, t, x, cfg) -> CheckItem:
    a, m = sma(b.close, cfg.ma_short)[t], sma(b.close, cfg.ma_mid)[t]
    if not (math.isfinite(a) and math.isfinite(m)):
        return CheckItem(6, "상승 추세 확인", UNKNOWN, None, f"이력 부족 ({t + 1}봉)", ORIGIN["ck6"])
    c = b.close[t]
    ok = bool(_gt(c, a) and _gt(c, m))
    return CheckItem(6, "상승 추세 확인", PASS if ok else WARN, {"close": float(c), "sma20": float(a), "sma60": float(m)},
                     f"종가 {'>' if _gt(c, a) else '≤'} 20일선 · {'>' if _gt(c, m) else '≤'} 60일선", ORIGIN["ck6"])


def _ck_resistance(b, t, x, cfg) -> CheckItem:
    if t < 1:
        return CheckItem(7, "위 저항", UNKNOWN, None, "이력 부족", ORIGIN["ck7"])
    entry = float(x.entry) if x.entry is not None else float(b.close[t])
    lo = max(0, t - cfg.res_lookback + 1)
    hh = float(np.max(b.high[lo:t]))
    if _ge(b.close[t], hh):
        return CheckItem(7, "위 저항", PASS, {"entry": entry, "resistance": None}, "위 저항 없음(신고가)", ORIGIN["ck7"])
    sw = [s for s in swing_highs(b.high, k=cfg.res_pivot_k) if s.i >= lo and s.confirm_i <= t and _gt(s.price, entry)]
    R = min((s.price for s in sw), default=hh)
    if not _gt(R, entry):
        return CheckItem(7, "위 저항", PASS, {"entry": entry, "resistance": None}, "진입가 위 저항 없음", ORIGIN["ck7"])
    d = R / entry - 1
    val = {"entry": entry, "resistance": float(R), "dist": float(d), "from_swing": bool(sw)}
    if x.stop is not None and entry > x.stop:
        val["dist_to_stop_ratio"] = float(d / (1 - x.stop / entry))
    warn = _lt(d, cfg.res_warn_pct)
    note = f"위 저항 {R:,.0f} 까지 {d:+.1%}" + (" — 먹을 폭 작음" if warn else "")
    return CheckItem(7, "위 저항", WARN if warn else PASS, val, note, ORIGIN["ck7"])


def _ck_stop(b, t, x, cfg) -> CheckItem:
    entry = float(x.entry) if x.entry is not None else float(b.close[t])
    if x.stop is None:
        return CheckItem(8, "아래 지지 · 손절", UNKNOWN, None, "기법 손절 없음", ORIGIN["ck8"])
    s = 1 - x.stop / entry
    if t + 1 < cfg.vstop_n:
        return CheckItem(8, "아래 지지 · 손절", UNKNOWN, {"stop": float(x.stop), "stop_pct": float(s)},
                         f"손절 {s:.1%} — 변동성 손절 이력 부족", ORIGIN["ck8"])
    rng = float(np.mean(b.high[t - cfg.vstop_n + 1:t + 1] - b.low[t - cfg.vstop_n + 1:t + 1]))
    vstop = float(b.low[t] - cfg.vstop_mult * rng)
    val = {"stop": float(x.stop), "stop_pct": float(s), "vstop": vstop}
    if _gt(x.stop, vstop):
        return CheckItem(8, "아래 지지 · 손절", WARN, val,
                         f"손절 {s:.1%} — 변동성 손절 {vstop:,.0f} 보다 가까움(변동성 2배보다 가까움)", ORIGIN["ck8"])
    return CheckItem(8, "아래 지지 · 손절", PASS, val, f"손절 {s:.1%} · 변동성 손절 {vstop:,.0f}", ORIGIN["ck8"])


def _risk_tags(x: ChecklistInputs) -> list[str]:
    tags = []
    rk = x.risk or {}
    if rk.get("level"):
        tags.append(f"공시 위험: {rk['level']}")
    try:
        from .vocal import JUNK_REF, WARN_REF
        names = {**JUNK_REF, **WARN_REF}
    except Exception:   # pragma: no cover
        names = {}
    for r in rk.get("ref") or []:
        c = r.get("cat") if isinstance(r, dict) else None
        if c:
            tags.append(names.get(c, c))
    vr = (x.value_row or {}).get("risk")
    if vr and f"공시 위험: {vr}" not in tags:
        tags.append(f"공시 위험: {vr}")
    return tags


def _ck_deadcat(b, t, x, cfg) -> CheckItem:
    tags = _risk_tags(x)
    C = b.close
    pre = pd.Timestamp(cfg.limit_change)
    ev = []
    for j in range(max(1, t - cfg.dcb_ref_window + 1), t + 1):
        chg = C[j] / C[j - 1] - 1
        old = b.dates is not None and b.dates[j] < pre
        hit = _le(chg, -cfg.dcb_drop_pre if old else -cfg.dcb_drop)
        if not hit and old and j >= 2:
            hit = _le(C[j] / C[j - 2] - 1, -cfg.dcb_drop)
        if hit:
            ev.append(j)
    recent = [j for j in ev if j >= t - cfg.dcb_window + 1]
    older = [j for j in ev if j < t - cfg.dcb_window + 1]
    val = {"events": [b.date(j) or j for j in ev], "risk_tags": tags}
    notes = []
    if recent:
        notes.append(f"데드캣(6개월): {b.date(recent[-1]) or recent[-1]} 하루 종가 −15% 이하")
    elif older:
        notes.append(f"참고: 6~12개월 전 급락 {b.date(older[-1]) or older[-1]}")
    notes += tags
    if recent or tags:
        return CheckItem(9, "데드캣", WARN, val, " · ".join(notes), ORIGIN["ck9"])
    if t + 1 < cfg.dcb_window:
        return CheckItem(9, "데드캣", UNKNOWN, val, f"이력 {t + 1}봉 (최소 {cfg.dcb_window})", ORIGIN["ck9"])
    return CheckItem(9, "데드캣", PASS, val, " · ".join(notes) or "6개월 안 급락 없음", ORIGIN["ck9"])


def _ck_runup(b, t, x, cfg) -> CheckItem:
    n = cfg.run_days
    if t < n:
        return CheckItem(10, "연속 급등", UNKNOWN, None, "이력 부족", ORIGIN["ck10"])
    ups = count_up(b.close, t, n)
    r5 = float(b.close[t] / b.close[t - n] - 1)
    streak = up_streak(b.close, t)
    val = {"up_days": ups, "ret5": r5, "streak": streak}
    if ups >= cfg.run_up_min and _ge(r5, cfg.run_pct):
        return CheckItem(10, "연속 급등", WARN, val, f"단기 급등 — 되돌림 뒤 진입 고려 (5일 {r5:+.1%}, 상승 {ups}일)", ORIGIN["ck10"])
    note = f"5일 {r5:+.1%} · 상승 {ups}일" + (f" · 연속 상승 {streak}일" if streak >= cfg.streak_warn else "")
    return CheckItem(10, "연속 급등", PASS, val, note, ORIGIN["ck10"])


CHECKS: tuple[Callable[..., CheckItem], ...] = (_ck_market, _ck_sector, _ck_weekly, _ck_replay, _ck_ind_rs,
                                                _ck_uptrend, _ck_resistance, _ck_stop, _ck_deadcat, _ck_runup)


def run_checklist(b: Bars, t: int | None = None, inputs: ChecklistInputs | None = None,
                  cfg: ChecklistConfig | None = None) -> list[CheckItem]:
    """불코우스키 체크리스트 10 — 항목마다 통과 · 경고 · 모름 + 값 + 출처. 봉 t 까지만 본다."""
    cfg = cfg or ChecklistConfig()
    x = inputs or ChecklistInputs()
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    bt = b.cut(t)
    return [fn(bt, t, x, cfg) for fn in CHECKS]


def checklist_counts(items: list[CheckItem]) -> dict[str, int]:
    out = {PASS: 0, WARN: 0, UNKNOWN: 0}
    for it in items:
        out[it.status] += 1
    return out


def industry_rs_table(closes: dict[str, pd.Series], groups: dict[str, str], asof=None, lookback: int = 126,
                      min_members: int = 3, pos_window: int = 252) -> pd.DataFrame:
    """업종 RS (Bulkowski industryRS): 구성 종목 C[t]/C[t−126] − 1 평균. asof 이후 자료는 쓰지 않는다.

    열: members(126봉 이상 종목 수) · rs · rank_pct(1 = 최강, 구성 min_members 미만 업종은 NaN) ·
        pos52(구성 종목 연중 위치 (C − 최저)/(최고 − 최저) 중앙값, 종가 252봉 — 체크리스트 2 고점권 · 바닥권)."""
    rows: dict[str, dict[str, list]] = {}
    for code, s in closes.items():
        g = groups.get(code)
        if not g or s is None:
            continue
        s = (s.loc[:asof] if asof is not None else s).dropna()
        if len(s) < lookback + 1 or s.iloc[-1 - lookback] <= 0:
            continue
        r = rows.setdefault(g, {"ret": [], "pos": []})
        r["ret"].append(float(s.iloc[-1] / s.iloc[-1 - lookback] - 1))
        if len(s) >= pos_window:
            w = s.iloc[-pos_window:]
            hi, lo = float(w.max()), float(w.min())
            if hi > lo:
                r["pos"].append(float((s.iloc[-1] - lo) / (hi - lo)))
    cols = ["members", "rs", "rank_pct", "pos52"]
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame.from_dict({g: {"members": len(r["ret"]), "rs": float(np.mean(r["ret"])),
                                      "pos52": float(np.median(r["pos"])) if r["pos"] else np.nan}
                                  for g, r in rows.items()}, orient="index")
    out["members"] = out["members"].astype(int)
    elig = out["members"] >= min_members
    rank = pd.Series(np.nan, index=out.index)
    ne = int(elig.sum())
    if ne == 1:
        rank[elig] = 1.0
    elif ne > 1:
        rank[elig] = (out.loc[elig, "rs"].rank(method="average") - 1) / (ne - 1)
    out["rank_pct"] = rank
    out.index.name = "group"
    return out[cols].sort_values("rs", ascending=False)


# ---------------------------------------------------------------- 시장 맥락 (부록 §10)
@dataclass
class MarketContextConfig:
    ma: int = 120              # 경기선
    zz_pct: float = 0.20       # MKT_ZZ_PCT (구현 선택)
    zone_lo: float = 0.5
    zone_hi: float = 0.618


def _retr_zone(retr: float, cfg: MarketContextConfig) -> str | None:
    if not math.isfinite(retr):
        return None
    if _ge(retr, cfg.zone_lo) and _le(retr, cfg.zone_hi):
        return "50~61.8% 구간"
    return "61.8% 넘음" if _gt(retr, cfg.zone_hi) else None


def _leg(b: Bars, li: int, hi_i: int, lp: float, hp: float, px: float, cfg: MarketContextConfig) -> dict:
    retr = (hp - px) / (hp - lp) if hp > lp else float("nan")
    return {"low_i": li, "low_date": b.date(li), "low": lp, "high_i": hi_i, "high_date": b.date(hi_i), "high": hp,
            "price": float(px), "retr": _f(retr), "dd": float(px / hp - 1), "zone": _retr_zone(retr, cfg)}


def market_context(index_df: pd.DataFrame, name: str = "", t: int | None = None,
                   cfg: MarketContextConfig | None = None,
                   red3: Callable[[pd.DataFrame], Any] | None = None) -> dict:
    """지수 맥락 칸 — 120일선 위 · 아래, 마지막 확정 저점(ZigZag 20%) 뒤 고점 대비 낙폭, 마지막 상승 파동 되돌림.

    두 기준 (부록 §10 사례 표): 'close' = 종가 ZigZag · 그 뒤 최고 종가 · 오늘 종가, 'intraday' = 고저 ZigZag · 최고 고가 ·
    오늘 저가. 깃발 '50~61.8% 구간' · '61.8% 넘음'(out['zone']) 은 종가 기준 마지막 파동. 확률 · 반등 기대치는 쓰지 않는다.
    기준마다 'prev_leg' = 그 앞 확정 저점 → 다음 확정 고점(직전 큰 파동)의 되돌림도 같이 둔다 — 급락 뒤 20% 넘는 반등이
    있으면 마지막 파동이 그 반등이 된다(2026-10-13 KOSPI: 마지막 파동 7-30 → 9-23 되돌림 70%, 직전 큰 파동 2025-04 →
    2026-06 되돌림 45.1% = 부록 §10 사례 값). 어느 쪽을 화면 깃발로 쓸지는 패턴 · 리포트가 정한다(둘 다 보이기 권장).
    red3: 월봉 적삼병 판정 함수(red_three_monthly 모듈이 준다) — monthly_bars(지수, 거래량 0 유지)를 받아 결과를 낸다."""
    cfg = cfg or MarketContextConfig()
    b = Bars.from_df(index_df)
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    b = b.cut(t)
    C, H, L = b.close, b.high, b.low
    m = sma(C, cfg.ma)[t]
    out: dict[str, Any] = {
        "name": name, "date": b.date(t), "close": float(C[t]), "ma120": _f(m),
        "above_ma120": None if not math.isfinite(m) else bool(_gt(C[t], m)),
        "origin": {k: ORIGIN[k] for k in ("mkt_ma120", "mkt_zz", "mkt_retr", "mkt_basis")},
    }
    for basis, hi_a, lo_a, px in (("close", C, C, C[t]), ("intraday", H, L, L[t])):
        piv = [p for p in ind.zigzag(hi_a, lo_a, cfg.zz_pct) if p.confirmed]   # 확정 피벗 (H · L 교대)
        lows = [k for k, p in enumerate(piv) if p.kind == "L"]
        if not lows:
            out[basis] = None
            continue
        li = piv[lows[-1]].i
        hi_i = li + int(np.argmax(hi_a[li:t + 1]))
        leg = _leg(b, li, hi_i, float(lo_a[li]), float(hi_a[hi_i]), px, cfg)
        leg["prev_leg"] = None
        if len(lows) >= 2 and lows[-2] + 1 < lows[-1] and piv[lows[-2] + 1].kind == "H":
            pl, ph = piv[lows[-2]], piv[lows[-2] + 1]
            leg["prev_leg"] = _leg(b, pl.i, ph.i, float(pl.price), float(ph.price), px, cfg)
        out[basis] = leg
    out["zone"] = out["close"]["zone"] if out.get("close") else None
    if red3 is not None:
        out["red3_monthly"] = red3(monthly_bars(index_df.iloc[:t + 1], drop_zero_volume=False))
    else:
        out["red3_monthly"] = None
    return out


def market_context_all(index_dfs: dict[str, pd.DataFrame], **kw) -> dict[str, dict]:
    """{'KOSPI': df, 'KOSDAQ': df} → {이름: market_context}."""
    return {name: market_context(df, name, **kw) for name, df in index_dfs.items() if df is not None and len(df)}
