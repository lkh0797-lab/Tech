"""변동성 수축 패턴 (VCP, Volatility Contraction Pattern) — 마크 미너비니.

출처: Minervini, *Trade Like a Stock Market Wizard* (2013) 10장 'Volatility Contraction Pattern',
      *Think & Trade Like a Champion* (2017) — 베이스 안에서 되돌림(T)이 점점 작아지고 거래량이
      마르면서 공급이 소진된 뒤, 마지막 수축의 고점(피벗)을 거래량 동반 돌파할 때 매수.

판정 규칙 (임계값은 모두 ``VCPConfig``)
 0. 전제 — Stage 2: 마지막 봉 기준 트렌드 템플릿 8개 중 7개 이상.
    단, 아직 돌파 전(가격이 베이스 안)이고 종가가 50일선 아래면 핵심 3개(종가>200일선,
    150일선>200일선, 200일선 1개월 상승)만 요구한다(완화 판정 — 점수 감점).
    이미 돌파한 베이스는 '실제 돌파봉' 시점에 7/8 이상이어야 한다.
    7번 기준(종가가 52주 고점 -25% 이내)은 7/8 의 '빠질 수 있는 하나'가 아니라 필수다 — 마지막 봉과
    (돌파한 베이스는) 돌파봉 모두에서. 급락 후 반등 구간의 2차 고점은 VCP 가 아니다.
 1. 선행 상승: 베이스 고점이 직전 250봉 최저가 대비 +25% 이상.
    베이스 고점은 '의미 있는 고점'이어야 한다: 직전 250봉 최고가(대표 고가)의 85% 이상. 아니면 급락 후
    반등 구간에서 생긴 2차 고점이므로 탈락.
 2. 베이스: 왼쪽 고점(베이스 고점)에서 시작해 분석 종료점까지 3~65주(15~325봉, 이상적 4~25주).
    베이스 고점은 이후 모든 고가보다 높고, 직전 25봉(5주) 최고가다 — 5주 안에 더 높은 고점이 있었다면
    그 고점에서 이미 베이스가 시작됐고(그 고점이 별도 후보로 평가됨) 이 봉은 베이스 안의 낮아진 고점이다.
    고가는 1봉 스파이크를 걸러낸 '대표 고가'를 쓴다(아래 '1봉 스파이크').
 3. 수축(T): 스윙 고점→스윙 저점 되돌림 2~6회.
    - 각 수축의 깊이는 스윙 고점(대표 고가)부터 다음 스윙 고점 직전까지의 '실제 최저가' 기준(병합으로 지운
      꼬리 저점도 포함). 최종 수축은 피벗봉 다음 날~분석 종료점의 최저가 = 손절가와 같은 저점.
    - 1차 수축 8~50% (35% 초과는 '깊은 베이스' 감점, 50% 초과 탈락)
    - 점진적 축소: d_k ≤ d_(k-1)×1.15 + 1%p 이어야 하고, '뚜렷이(10% 이상) 줄지 않은' 단계는 최대 1회,
      최종 수축 ≤ 1차 수축 × 0.65
    - 최종 수축 ≤ 12% (이상적 ≤ 6%, 10% 초과는 경고), 그리고 직전 수축보다 크지 않음(+0.5%p 허용)
    - 최소 길이: 2차 이후 수축의 하락 구간(스윙 고점→저점) ≥ 2봉, 최종 수축(피벗봉→분석 종료점) ≥ 3봉
      (돌파 후보는 2봉 연속 하락이면 2봉도 인정 — 다음 봉의 돌파가 수축 완료를 확인). 1봉짜리 장대음봉,
      '전일 고가→당일 저가', '꼬리 고점→1봉 눌림→1봉 반등'은 수축이 아니라 잡음으로 병합한다(아래 (c)(d)).
    - 1차 수축이 35% 초과로 깊으면 베이스가 최소 6주(30봉) — 단기 급락·V자 급반등 배제
    - 수축 국면(2차 수축 시작 고점~분석 종료점)이 최소 1주(5봉)
    - 피벗(최종 수축 시작 고점)은 베이스 고점 대비 -15% 이내
    - 최종 수축 저점이 최근 2봉 안에서 갱신 중(마지막 봉 기준)이면 '진행 중 수축' — 깊이·손절가가
      잠정치이므로 경고하고 최종 수축 점수를 절반만 준다.
 4. 거래량: 최종 수축 구간(피벗봉 '다음 날'~분석 종료점 — 피벗을 만든 상승일 거래량 제외) 평균이
    기준선 × 0.85 이하(이상적 ≤ 0.7)이고 1차 수축 하락 구간 평균 이하.
    기준선 = 최종 수축 시작 직전 50일 거래량의 '중앙값'(거래량 0 제외). 평균을 쓰면 뉴스 급등일 하루(10배↑)가
    평균을 부풀려 평범한 거래량도 '고갈'로 보이므로 견고한 중앙값을 쓴다(수축 중 고갈된 거래량이 기준선을
    끌어내리지 않도록 수축 시작 직전 값). 평균 기준 비율은 참고 지표로 함께 보고한다.
    기준선의 50% 미만 '거래량 고갈일'(최근 10봉, 거래량 0 제외)은 가점.
    최종 수축 구간 거래량의 20% 초과가 결측/0 이면 판정 불가로 탈락.
 5. 타이트니스(둘 다 필수): 베이스 마지막 7봉 종가 범위 ≤ min(8%, max(3%, 2.5×베이스 ATR% 중앙값))
    그리고 마지막 봉 ATR% ≤ 베이스 평균 ATR% × 1.0 (변동성이 베이스 평균보다 커지지 않음).
 6. 피벗 = 최종 수축이 시작된 스윙 고점(장중에 잠깐 넘었다 밀린 고가는 무시 — 고전적 정의),
    손절 = 그 이후 최저가. 돌파 = 베이스 종료 후 첫 '종가 > 피벗'. 베이스 안에서는 종가가 피벗 위로
    마감한 적이 없어야 한다(있었다면 그 봉의 전날을 종료점으로 하는 후보가 돌파로 처리).
    돌파 거래량(50일 평균의 1.4배 이상)은 '필수 조건'이 아니라 품질(점수·경고)로 반영한다.
    이유: ① 필수로 하면 거래량이 약간 모자란 채 급등한 종목이 '피벗 근접'으로 잘못 분류되고
    ② 장중 미완성 봉은 거래량이 추정치라 오판 위험이 크며 ③ 판정 결과(breakout_vol_ratio)로
    사후 필터링이 가능하기 때문. (돌파 거래량은 관례대로 50일 평균 대비, 중앙값 대비 비율도 함께 보고)
 7. 베이스 안 선행 돌파 금지(재베이스 방지): 베이스 [고점, 종료점] 안의 어떤 봉 b 에서 '그 시점 기준으로
    유효한 VCP 돌파'(아래 미래 참조 방지의 돌파 후보 정의와 동일)가 이미 있었고 그 돌파가 종료점까지
    아직 '진행 중'이면, 이 베이스는 '돌파 후 눌림을 새 수축으로 오인한 재형성 구조'이므로 탈락한다.
    진행 중 = 거래량(≥ 50일 평균) 동반 돌파이고, 그 손절가 미이탈이며, [돌파 후 3주(15봉) 미만] 또는
    [종가가 매수 범위(피벗 +5%)를 넘어선 적 없음]. 즉 거래량 없는 '찌르기', 손절가를 깬 실패 돌파,
    이격까지 갔다가 3주 이상 조정받아 새로 만든 베이스(base-on-base)는 별개 셋업으로 보고 새 피벗을 허용한다.
    여러 후보가 유효하면, 다른 후보의 돌파봉을 품은 후보는 같은 기준으로 정리(그 돌파가 진행 중이면
    나중 후보를, 아니면 그 돌파 후보를 버림)한 뒤 점수 최고를 채택한다.
    → 진행 중인 돌파는 같은 베이스에서 두 번(다른 피벗으로) 보고되지 않는다.
 8. 피벗 위 매물대(감점·경고): 최근 120봉(베이스 이전 포함)~피벗봉 전에 피벗 +3% 위를 찍고 내려온 '별개의
    고점'(3봉 미만 간격의 돌출은 한 번의 시험)이 3개 이상이면 피벗이 저항대 아래에 있는 것(같은 가격대에서 반복
    실패한 매물) — 경고와 감점. 1~2개는 경고만. 베이스 고점과 각 수축의 시작 고점(VCP 자체의 하강하는 고점
    계단)은 세지 않는다 — 정상적인 하강 고점 VCP 는 감점되지 않는다.
 9. 진입 위험(피벗→손절)이 10% 초과면 경고와 감점 (미너비니는 손절폭 7~8% 유지).

1봉 스파이크 (대표 고가)
 - 고가가 앞뒤 봉 종가의 최고치보다 8% 넘게 높은 봉(장중 뉴스 꼬리, 하루 만에 되돌린 상한가 등)은 그 가격에
   거래가 머문 적이 없으므로 고가를 '3봉 중앙값 고가'로 대체한 대표 고가로 베이스 고점·수축 고점·피벗·깊이를
   계산하고 경고한다(double_bottom 의 left_spike_tol 과 같은 취지). 분석 종료점 봉은 다음 봉을 모르므로 원래
   고가를 쓴다(미래 참조 방지).

스윙 탐지와 노이즈 처리
 - 지그재그(고가/저가) 임계값을 max(2.5%, k×최근 20봉 ATR% 중앙값) (k = 0.75, 1.25, 2.0, 0.25%p 단위
   반올림)으로 바꿔 가며 각각 분할하고, 유효한 결과 중 점수가 가장 높은 것을 채택한다. 작은 임계값은
   마지막의 작은 수축을 잡고, 큰 임계값은 변동성 큰 종목의 잡음 스윙을 걸러낸다. 수축된 '현재' 변동성을
   기준으로 하되 마지막 봉 하나의 ATR 이 아니라 20봉 중앙값을 반올림해 쓰므로 날마다 임계값(→스윙 집합·
   피벗)이 흔들리지 않는다. (베이스 전체 중앙값을 쓰면 변동성 큰 1차 수축 때문에 임계값이 커져 작은 최종
   수축을 놓친다.)
 - 병합 규칙(안정될 때까지 반복, 앞 규칙 우선):
   (a) 저점 미상승 — 다음 저점이 L_k×(1+rise) 보다 낮으면(하회 또는 같은 수준 재시험) 그 사이 반등은
       하락·바닥 다지기 중 잡음 → 두 저점 중 높은 쪽과 두 고점 중 낮은 쪽을 제거해 한 수축으로 합침
       (결과적으로 '스윙 저점 상승' 구조를 강제).
   (b) 고점 계단 상승 — 다음 고점이 H_k×(1+step) 보다 높으면 H_k 이후 눌림은 반등 중 잡음
       → H_k 와 두 저점 중 높은 쪽 제거 (스윙 고점은 '대체로 수평/하강').
       이미 종가로 돌파된 고점이 이렇게 흡수돼도 규칙 7 이 그 돌파를 따로 잡아낸다.
   (c) 짧은 중간 수축 — 2차 이후 수축의 하락 구간이 2봉 미만이면: 다음 스윙 고점이 같거나 높으면(상승 도중
       1봉 눌림) 그 고점·저점 쌍을 제거, 다음 고점이 낮고 1~2봉 만에 나오면 급락 저점을 꼬리로 보고 다음
       수축과 합침, 다음 고점이 낮고 반등이 길면 급락으로 시작한 정상 수축(흔들기)으로 유지.
   (d) 짧은 최종 수축 — 피벗봉→분석 종료점이 3봉 미만이면(돌파 후보의 2봉 연속 하락은 예외) 마지막
       고점·저점(및 미확정 고점)을 제거해 직전 수축을 최종 수축으로 삼는다(피벗은 직전 스윙 고점으로 유지).
       돌파 후보 쪽이 더 관대하므로 '전날 피벗 근접 → 돌파일 미보고' 같은 역방향 불일치는 생기지 않는다.
   rise = max(0.5%, 0.15×ATR%), step = max(3%, 0.75×ATR%) (ATR% = 베이스 중앙값) — 변동성이 클수록 관대.
 - 베이스 고점 후보: 분석 종료점에서 거꾸로 본 신고가(이후 모든 대표 고가보다 높은 봉) 중 왼쪽 25봉보다
   낮지 않은 봉. 가까운 것부터 최대 6개를 평가해 최고 점수를 채택(중첩 베이스 중 가장 그럴듯한 것).

미래 참조 방지
 - 분석 종료점 e 는 마지막 봉, 또는 최근 15봉 안에서 종가가 직전 5봉 종가 최고치를 넘은 봉(돌파 후보) b
   의 전날(b-1)이다. 구조(스윙·거래량·타이트니스)는 e 까지의 데이터만 사용하고, e 이후는 돌파·단계
   판정에만 쓴다. 규칙 7 의 과거 돌파 검사도 각 b 시점까지의 데이터만 쓴다. 따라서 과거 시점으로
   잘라낸 데이터에서도 '그 시점의 가장 최근 베이스'만 분석한다.

점수 (0~100)
 수축 개수·진행 20 / 최종 수축 깊이 15 / 타이트니스 10 / 거래량 고갈 15 / RS 10 / 추세 10 /
 베이스 기간 5 / 1차 수축 깊이 5 / 돌파 거래량 10 (미돌파는 중립 5)
 (진행 중 최종 수축은 최종 수축 깊이 점수 절반, 타이트니스 7 은 변동성 연동 상한 대비 위치 + ATR 비율 3)
 감점: 피벗 위 매물대(별개 고점 3개↑) -6, 1개 추가마다 -2 (최대 -10) / 진입 위험 10% 초과 -5 - 초과 1%p 당 1 (최대 -15)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import (
    PatternResult,
    StockContext,
    box,
    classify_stage,
    hline,
    marker,
    register,
    segment,
)
from .trend_template import evaluate as tt_evaluate

NAME = "vcp"
LABEL = "변동성 수축 패턴(VCP)"


@dataclass
class VCPConfig:
    # ---- 전제: Stage 2 (Minervini 트렌드 템플릿)
    min_history: int = 222              # 200일선 + 1개월 상승 판정에 필요한 최소 봉 수
    tt_min_pass: int = 7                # 8개 기준 중 최소 충족 수 (과제 정의: 7/8)
    allow_relaxed_trend: bool = True    # 종가<50일선(베이스 안)이면 핵심 3개만 요구
    require_near_high: bool = True      # 7번 기준(52주 고점 -25% 이내)은 필수 (마지막 봉·돌파봉)
    prior_advance_min: float = 0.25     # 베이스 이전 상승률 최소 (미너비니: 25~30% 이상)
    prior_lookback: int = 250           # 선행 상승 측정 구간(봉)
    prior_min_bars: int = 40            # 선행 구간이 이보다 짧으면 측정 불가
    min_high_vs_prior: float = 0.85     # 베이스 고점 ≥ 직전 250봉 최고가 × 0.85 (미만: 급락 후 반등 구간)
                                        # (워크포워드: 0.85~0.90 구간 돌파는 양호, 0.85 미만은 중앙 수익률 음수)
    # ---- 베이스
    min_base_bars: int = 15             # 3주
    max_base_bars: int = 325            # 65주
    ideal_base_bars: tuple = (20, 125)  # 4~25주 (점수)
    peak_left_bars: int = 25            # 베이스 고점은 왼쪽 n봉(5주) 최고가 — 더 높은 고점이 있으면 그쪽이 베이스 시작
    max_base_candidates: int = 6        # 평가할 베이스 고점 후보 수
    spike_tol: float = 0.08             # 1봉 스파이크: 고가 > 앞뒤 봉 종가 최고치 × (1+8%) → 3봉 중앙값 고가 사용
    # ---- 수축 (T)
    min_contractions: int = 2
    max_contractions: int = 6
    min_first_depth: float = 0.08
    deep_first_depth: float = 0.35      # 초과 시 '깊은 베이스' 감점
    deep_min_base_bars: int = 30        # 깊은 베이스는 최소 6주 (V자 급락·급반등 배제)
    min_phase_bars: int = 5             # 2차 수축 시작~분석 종료점 최소 봉 수 (수축 국면 1주 이상)
    min_leg_bars: int = 2               # 2차 이후 수축의 하락 구간(고점→저점) 최소 봉 수 (1봉 급락은 잡음)
    min_final_bars: int = 3             # 최종 수축(피벗봉→종료점) 최소 봉 수 — 마지막 봉 기준(미확정)
    min_final_bars_bo: int = 2          # 돌파 후보는 2봉 연속 하락(하락 구간 ≥ min_leg_bars)이면 2봉도 인정
                                        # — 다음 봉의 돌파가 수축 완료를 확인 (1봉 눌림+1봉 반등은 잡음)
    in_progress_bars: int = 2           # 최종 수축 저점이 최근 n봉 안이면 '진행 중 수축'
    max_first_depth: float = 0.50       # 초과 시 탈락
    max_final_depth: float = 0.12       # 최종 수축 상한 (탈락)
    final_vs_prev_abs: float = 0.005    # 최종 수축 ≤ 직전 수축 + 0.5%p (최종이 가장 작아야 함)
    warn_final_depth: float = 0.10      # 초과 시 경고
    ideal_final_depth: float = 0.06     # 이하이면 만점
    final_to_first_max: float = 0.65    # 최종/1차 수축 비율 상한
    prog_rel_tol: float = 0.15          # d_k ≤ d_(k-1)×(1+rel)+abs 허용
    prog_abs_tol: float = 0.01
    prog_min_shrink: float = 0.10       # d_k ≤ d_(k-1)×(1-0.10) 이어야 '뚜렷한 축소'
    max_prog_violations: int = 1        # 뚜렷이 줄지 않은 단계 허용 횟수
    max_pivot_below_high: float = 0.15  # 피벗이 베이스 고점 대비 이보다 낮으면 탈락
    # ---- 스윙 탐지 (지그재그 + 병합)
    zz_min_pct: float = 0.025
    zz_atr_mults: tuple = (0.75, 1.25, 2.0)
    zz_atr_window: int = 20             # 임계값용 ATR% = 최근 20봉 중앙값 (수축된 현재 변동성 반영 + 일간 안정)
    zz_quantum: float = 0.0025          # 임계값 반올림 단위 (날마다 흔들림 방지)
    low_rise_min: float = 0.005         # 스윙 저점은 직전 저점보다 이만큼 이상 높아야 별개 수축
    low_rise_atr: float = 0.15
    high_step_min: float = 0.03
    high_step_atr: float = 0.75
    atr_n: int = 14
    # ---- 거래량 (고갈 판정 기준선 = 50일 '중앙값' — 뉴스 급등일 하루가 기준선을 부풀리지 못하게)
    vol_avg_n: int = 50
    vol_baseline: str = "median"        # 'median' | 'trim'(상위 vol_trim_top 일 제외 평균) | 'mean'(단순 평균, 예전 방식)
    vol_trim_top: int = 3
    max_last_vol_ratio: float = 0.85    # 최종 수축 평균 거래량 / 50일 중앙값 상한 (탈락)
    ideal_last_vol_ratio: float = 0.7   # 이하이면 '뚜렷한 감소'
    max_last_to_first_vol: float = 1.0  # 최종 수축 거래량 ≤ 1차 수축 거래량
    dryup_ratio: float = 0.5            # 고갈일: 50일 중앙값의 50% 미만
    dryup_window: int = 10
    max_bad_vol_frac: float = 0.2       # 최종 수축 구간 거래량 결측/0 비율 상한
    breakout_vol_mult: float = 1.4      # 돌파 거래량 품질 기준 (50일 평균 대비, 필수 아님)
    # ---- 타이트니스 (둘 다 필수)
    tight_bars: int = 7
    max_tight_range: float = 0.08       # 마지막 7봉 종가 범위 상한 (과제: 5~8%)
    min_tight_cap: float = 0.03         # 변동성 연동 상한의 하한
    tight_atr_mult: float = 2.5         # 상한 = min(8%, max(3%, 2.5×베이스 ATR% 중앙값))
    ideal_tight_range: float = 0.03
    max_atr_ratio: float = 1.0          # 마지막 봉 ATR% / 베이스 평균 ATR% 상한
    tight_atr_ratio: float = 0.75       # 이하이면 '변동성 뚜렷이 수축' (사유·점수)
    # ---- 단계 판정
    near_pct: float = 0.05
    buy_range: float = 0.05
    breakout_window: int = 5
    fail_pct: float = 0.03
    breakout_lookback: int = 15         # 최근 n봉 안의 돌파까지 추적
    breakout_close_bars: int = 5        # 돌파 후보: 종가가 직전 n봉 종가 최고치 초과
    breakout_grace_bars: int = 2        # 종료점 후 이 봉 수 안에 첫 종가 돌파가 있어야 함
    # ---- 규칙 7 (베이스 안 선행 돌파): '진행 중'인 돌파만 재베이스 금지 사유로 본다
    inner_bo_min_vol: float = 1.0       # 돌파봉 거래량 ≥ 50일 평균 × 이 배수여야 돌파 시도로 인정
                                        # (이격 기준은 buy_range: 종가가 피벗+5% 를 넘었으면 성공한 돌파)
    # ---- 경고·점수 기준 (탐지 여부에는 영향 없음)
    rs_good: float = 80.0               # RS 권장 하한 (미너비니: 80~90 이상)
    score_rs_lo: float = 70.0           # RS 점수 0점 기준
    score_rs_hi: float = 95.0           # RS 점수 만점 기준
    warn_pivot_below_high: float = 0.08 # 피벗이 베이스 고점보다 이 이상 낮으면 매물대 경고
    warn_risk: float = 0.10             # 진입 위험(피벗→손절) 경고·감점 기준 (미너비니 손절 7~8%)
    risk_penalty: float = 5.0           # 초과 시 기본 감점 + 초과 1%p 당 1점
    risk_penalty_max: float = 15.0
    strong_breakout_vol: float = 2.0    # 돌파 거래량 만점 기준
    # ---- 피벗 위 매물대 (감점·경고, 탐지 여부에는 영향 없음)
    overhead_lookback: int = 120        # 최근 n봉(베이스 이전 포함) ~ 피벗봉 전까지 본다
    overhead_tol: float = 0.03          # 피벗 +3% 위를 찍은 고점만 매물로 본다
    overhead_gap: int = 3               # n봉 미만 간격으로 이어진 돌출은 같은 고점(한 번의 시험)
    overhead_min_count: int = 3         # 별개 고점이 이 개수 이상이면 감점 (1~2개는 경고만)
                                        # (워크포워드: 2개↑는 돌파의 28% 로 성과 차이 없음, 3개↑(12%)는 20일 성과 열위)
    overhead_penalty: float = 6.0       # 기본 감점 (+ 1개 추가마다 2점, 최대 10점)
    overhead_penalty_max: float = 10.0


# ---------------------------------------------------------------- 스윙 탐지
def _zigzag(H: list, L: list, s: int, e: int, pct: float) -> list[list]:
    """[s, e] 구간 지그재그. 반환 [[i, price, 'H'|'L'], ...] (마지막은 미확정 극값).

    indicators.zigzag 와 같은 규칙이지만 파이썬 리스트로 동작해 후보 반복 평가가 빠르다.
    """
    piv: list[list] = []
    trend = 0
    hi_i = lo_i = s
    up, dn = 1 + pct, 1 - pct
    for i in range(s + 1, e + 1):
        h = H[i]
        lo = L[i]
        if trend == 0:
            if h > H[hi_i]:
                hi_i = i
            if lo < L[lo_i]:
                lo_i = i
            if lo_i < hi_i and H[hi_i] >= L[lo_i] * up:
                piv.append([lo_i, L[lo_i], "L"])
                trend, lo_i = 1, hi_i
            elif hi_i < lo_i and L[lo_i] <= H[hi_i] * dn:
                piv.append([hi_i, H[hi_i], "H"])
                trend, hi_i = -1, lo_i
        elif trend == 1:
            if h >= H[hi_i]:
                hi_i = i
            elif lo <= H[hi_i] * dn:
                piv.append([hi_i, H[hi_i], "H"])
                trend, lo_i = -1, i
        else:
            if lo <= L[lo_i]:
                lo_i = i
            elif h >= L[lo_i] * up:
                piv.append([lo_i, L[lo_i], "L"])
                trend, hi_i = 1, i
    if trend == 1:
        piv.append([hi_i, H[hi_i], "H"])
    elif trend == -1:
        piv.append([lo_i, L[lo_i], "L"])
    return piv


def _merge(p: list[list], rise: float, step: float, e: int, min_leg: int, min_final: int,
           min_final_short: int) -> list[list]:
    """VCP 구조에 맞지 않는 잡음 스윙 병합 (모듈 docstring 의 (a)~(d) 규칙). p = [H0, L, H, L, ...(, H)]

    min_final_short: 최종 수축이 이 봉 수 이상이고 하락 구간이 min_leg 봉 이상이면 min_final 미만이어도 인정
    (돌파 후보 전용, 마지막 봉 기준이면 min_final 과 같게 넘겨 비활성)."""
    changed = True
    while changed:
        changed = False
        # (a) 저점 미상승 → H_a,L_b,H_c,L_d 를 max(H)→min(L) 한 구간으로 병합
        for k in range(1, len(p) - 2):
            if p[k][2] == "L" and p[k + 2][1] < p[k][1] * (1 + rise):
                hi_first = p[k - 1][1] >= p[k + 1][1]
                if p[k + 2][1] < p[k][1] and hi_first:   # 더 낮은 L_d 와 H_a 를 남김
                    del p[k:k + 2]
                elif p[k + 2][1] >= p[k][1] and hi_first:  # L_b 와 H_a 를 남김
                    del p[k + 1:k + 3]
                else:                                      # H_c 가 더 높음 → H_c 와 L_d 를 남김
                    del p[k - 1:k + 1]
                changed = True
                break
        if changed:
            continue
        # (b) 고점 계단 상승 → 상승 구간 병합 (k=0 은 베이스 고점이므로 제외)
        for k in range(2, len(p) - 2):
            if p[k][2] == "H" and p[k + 2][1] > p[k][1] * (1 + step):
                if p[k - 1][1] <= p[k + 1][1]:
                    del p[k:k + 2]
                else:
                    del p[k - 1:k + 1]
                changed = True
                break
        if changed:
            continue
        nb = len(p) - 1 if p[-1][2] == "H" else len(p)  # 미확정 고점을 뺀 본체 길이 (짝수: H,L 쌍)
        # (c) 짧은 중간 수축(2차 이후, 하락 구간 < min_leg 봉)
        #     - 다음 고점이 같거나 높으면: 상승 도중의 1봉 눌림 → 그 고점·저점 제거
        #     - 다음 고점이 낮고 1~2봉 만에 나오면: 급락 저점은 꼬리로 보고 다음 수축과 합침(저점·다음 고점 제거)
        #     - 다음 고점이 낮고 반등이 길면: 급락으로 시작한 정상 수축(흔들기)으로 유지
        for k in range(2, nb - 3, 2):
            if p[k + 1][0] - p[k][0] >= min_leg:
                continue
            if p[k][1] <= p[k + 2][1] * (1 + rise):
                del p[k:k + 2]
            elif p[k + 2][0] - p[k][0] < min_final:
                del p[k + 1:k + 3]
            else:
                continue
            changed = True
            break
        if changed:
            continue
        # (d) 짧은 최종 수축(피벗봉→종료점 < min_final 봉, 단 돌파 후보는 2봉 연속 하락이면 인정)
        #     → 마지막 수축(과 미확정 고점) 제거
        if nb >= 4:
            span, leg = e - p[nb - 2][0], p[nb - 1][0] - p[nb - 2][0]
            if span < min_final and not (span >= min_final_short and leg >= min_leg):
                del p[nb - 2:]
                changed = True
    return p


# ---------------------------------------------------------------- 보조
def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _median(x: np.ndarray) -> float:
    """결측 제외 중앙값 (np.nanmedian 보다 빠름)."""
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else np.nan


def _fmt_depths(ds: list[float]) -> str:
    return ">".join(f"{d * 100:.1f}%" for d in ds)


def _spike_clean(H: np.ndarray, C: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray]:
    """1봉 스파이크를 걸러낸 대표 고가 배열과 스파이크 크기(앞뒤 봉 종가 최고치 대비 초과율, 아니면 0).

    스파이크 = 고가 > max(전날 종가, 다음날 종가) × (1+tol) — 장중 꼬리든 하루 만에 되돌린 상한가든 그 가격에
    거래가 머물지 않은 봉. 대표 고가 = 3봉 중앙값 고가(그 주변에서 실제로 거래된 수준). 첫·마지막 봉은 원값."""
    Hc = H.copy()
    pct = np.zeros(len(H))
    if len(H) >= 3:
        a, b, c = H[:-2], H[1:-1], H[2:]
        med = np.maximum(np.minimum(a, b), np.minimum(np.maximum(a, b), c))
        with np.errstate(divide="ignore", invalid="ignore"):
            p = b / np.maximum(C[:-2], C[2:]) - 1
        sp = (p > tol) & (med < b)
        Hc[1:-1] = np.where(sp, med, b)
        pct[1:-1] = np.where(sp, p, 0.0)
    return Hc, pct


class _Arrays:
    """탐지에 쓰는 numpy/리스트 배열 묶음 (한 번만 변환)."""

    def __init__(self, ctx: StockContext, cfg: VCPConfig):
        df = ctx.df
        self.cfg = cfg
        self.H = df["high"].to_numpy(dtype=float)
        self.L = df["low"].to_numpy(dtype=float)
        self.C = df["close"].to_numpy(dtype=float)
        self.V = ctx.vol.to_numpy(dtype=float)
        # 대표 고가(1봉 스파이크 제거) — 베이스 고점·수축 고점·피벗·깊이 계산용. 종료점 봉은 scan 에서 원값으로 교체
        self.Hc, self.spk = _spike_clean(self.H, self.C, cfg.spike_tol)
        self.Hcl = self.Hc.tolist()
        self.Ll = self.L.tolist()
        self.VS = ctx.vol_sma(cfg.vol_avg_n).to_numpy(dtype=float)
        self._vb: dict[int, float] = {}
        with np.errstate(divide="ignore", invalid="ignore"):
            self.ATRP = ctx.atr(cfg.atr_n).to_numpy(dtype=float) / self.C
        self.n = len(self.C)
        # 결측/0 가격 봉이 있으면 그 이후만 사용 (규칙 7 의 과거 검사가 오래된 불량 데이터를 밟지 않게)
        bad = ~(np.isfinite(self.H) & np.isfinite(self.L) & np.isfinite(self.C)
                & (self.H > 0) & (self.L > 0) & (self.C > 0))
        self.first_ok = int(np.nonzero(bad)[0][-1]) + 1 if bad.any() else 0
        ok = np.isfinite(self.ATRP)  # 구간 평균 ATR% 를 O(1) 로 (누적합)
        self.atr_cs = np.concatenate([[0.0], np.cumsum(np.where(ok, self.ATRP, 0.0))])
        self.atr_cnt = np.concatenate([[0], np.cumsum(ok)])

    def atr_mean(self, s: int, e: int) -> float:
        """ATR% 의 [s, e] 구간 평균 (결측 제외)."""
        k = self.atr_cnt[e + 1] - self.atr_cnt[s]
        return float((self.atr_cs[e + 1] - self.atr_cs[s]) / k) if k > 0 else np.nan

    def vol_base(self, i: int) -> float:
        """i 봉까지 50일 거래량의 견고한 기준선(중앙값 또는 상위 n일 제외 평균, 거래량 0·결측 제외).
        유효 거래일이 절반 미만이면 NaN."""
        if i not in self._vb:
            cfg = self.cfg
            w = self.V[max(0, i - cfg.vol_avg_n + 1):i + 1] if i >= 0 else self.V[:0]
            w = w[np.isfinite(w) & (w > 0)]
            if len(w) < cfg.vol_avg_n // 2:
                v = np.nan
            elif cfg.vol_baseline == "mean":
                v = float(self.VS[i]) if i >= 0 else np.nan
            elif cfg.vol_baseline == "trim" and len(w) > cfg.vol_trim_top:
                v = float(np.sort(w)[:len(w) - cfg.vol_trim_top].mean())
            else:
                v = float(np.median(w))
            self._vb[i] = v
        return self._vb[i]

    def highs_until(self, e: int) -> list:
        """종료점 e 기준 대표 고가 리스트 — e 봉은 다음 봉(미래)을 모르므로 원래 고가로."""
        if self.Hc[e] == self.H[e]:
            return self.Hcl
        return self.Hcl[:e] + [float(self.H[e])]

    def spike_above(self, s: int, e: int, level: float) -> tuple[int, float, float] | None:
        """[s, e) 구간에서 원래 고가가 level 을 넘는 1봉 스파이크 중 가장 높은 것 (봉, 원래 고가, 초과율).
        대표 고가로 바꿔 계산했으므로 무시한 고가를 경고에 쓴다."""
        s = max(0, s)
        if e <= s:
            return None
        k = np.flatnonzero((self.spk[s:e] > 0) & (self.H[s:e] > level))
        if not len(k):
            return None
        i = s + int(k[np.argmax(self.H[s + k])])
        return i, float(self.H[i]), float(self.spk[i])


def _end_candidates(A: _Arrays, cfg: VCPConfig) -> list[int]:
    """분석 종료점 후보: 마지막 봉 + 최근 돌파 후보 봉의 전날 (최근 것부터)."""
    last = A.n - 1
    out = [last]
    k = cfg.breakout_close_bars
    for b in range(last, max(k, last - cfg.breakout_lookback), -1):
        if A.C[b] > A.C[b - k:b].max():
            out.append(b - 1)
    return out


def _base_high_candidates(A: _Arrays, cfg: VCPConfig, e: int) -> list[tuple[int, float]]:
    """[(베이스 고점 j, 베이스 깊이)] — e 에서 거꾸로 본 신고가(대표 고가) 중 조건 충족 봉, 가까운 순.
    왼쪽 peak_left_bars 봉 안에 더 높은 고점이 있으면 제외(그 고점에서 시작한 베이스의 낮아진 고점)."""
    lo_b = max(A.first_ok, e - cfg.max_base_bars)
    seg_h = A.Hc[lo_b:e + 1].copy()
    seg_h[-1] = A.H[e]  # 종료점 봉: 미래(다음 봉) 없이 판정
    seg_l = A.L[lo_b:e + 1]
    if len(seg_h) < cfg.min_base_bars + 1:
        return []
    rev_max = np.maximum.accumulate(seg_h[::-1])[::-1]
    rev_min = np.minimum.accumulate(seg_l[::-1])[::-1]
    rec = np.nonzero(seg_h[:-1] > rev_max[1:])[0]
    out: list[tuple[int, float]] = []
    for r in rec[::-1]:  # 가까운 것부터
        j = int(r) + lo_b
        if e - j < cfg.min_base_bars:
            continue
        depth = 1.0 - rev_min[r] / seg_h[r] if seg_h[r] > 0 else np.nan
        if not np.isfinite(depth) or depth > cfg.max_first_depth * 1.05:
            break  # 더 왼쪽 후보는 더 깊어질 뿐
        if depth < cfg.min_first_depth * 0.9:
            continue
        left = A.Hc[max(0, j - cfg.peak_left_bars):j]
        if len(left) and A.Hc[j] < left.max():
            continue
        out.append((j, float(depth)))
        if len(out) >= cfg.max_base_candidates:
            break
    return out


def _thresholds(cfg: VCPConfig, atr_r: float) -> list[float]:
    q = cfg.zz_quantum
    return sorted({round(max(cfg.zz_min_pct, round(m * atr_r / q) * q), 4) for m in cfg.zz_atr_mults})


# ---------------------------------------------------------------- 후보 평가
def _true_lows(A: _Arrays, body: list[list], e: int) -> list[list]:
    """병합 후 각 수축의 저점을 그 구간의 '실제 최저가'로 교체 (구간 = 스윙 고점 다음 봉 ~ 다음 스윙 고점 전 봉,
    최종 수축은 ~종료점). 병합 규칙이 꼬리로 보고 지운 저점도 깊이에는 반영되고, 최종 수축 저점 = 손절가."""
    his = [body[k][0] for k in range(0, len(body) - 1, 2)]
    if not his:
        return body
    out = []
    for t, h_i in enumerate(his):
        end = his[t + 1] - 1 if t + 1 < len(his) else e
        l_i = h_i + 1 + int(np.argmin(A.L[h_i + 1:end + 1])) if end > h_i else body[2 * t + 1][0]
        out += [body[2 * t], [l_i, float(A.L[l_i]), "L"]]
    return out


def _evaluate(A: _Arrays, cfg: VCPConfig, e: int, j: int, thr: float, atr_b: float, Hl: list,
              quick: bool = False) -> dict:
    """베이스 [j, e] 를 임계값 thr 로 분할해 VCP 조건을 평가. 반환 dict(fails 비면 유효, 점수는 _score).
    Hl = 종료점 e 기준 대표 고가 리스트(A.highs_until(e)).
    quick=True: 유효 여부만 필요할 때(규칙 7 과거 검사) 구조 단계에서 탈락이면 거래량·타이트니스 생략."""
    last = A.n - 1
    rise = max(cfg.low_rise_min, cfg.low_rise_atr * atr_b)
    step = max(cfg.high_step_min, cfg.high_step_atr * atr_b)
    piv = _zigzag(Hl, A.Ll, j, e, thr)
    fails: list[str] = []
    out = {"e": e, "j": j, "thr": thr, "atr_b": atr_b, "fails": fails, "bo": None}
    if not piv or piv[0][2] != "H" or piv[0][0] != j:
        fails.append("✘ 베이스 고점 이후 의미 있는 조정이 없음")
        return out
    short = cfg.min_final_bars if e == last else cfg.min_final_bars_bo
    piv = _merge(piv, rise, step, e, cfg.min_leg_bars, cfg.min_final_bars, short)
    trail = piv[-1] if piv[-1][2] == "H" and len(piv) > 1 else None
    body = _true_lows(A, piv[:-1] if trail is not None else piv, e)
    piv = body + ([trail] if trail is not None else [])
    cons = [(body[k][0], body[k][1], body[k + 1][0], body[k + 1][1], 1.0 - body[k + 1][1] / body[k][1])
            for k in range(0, len(body) - 1, 2)]
    out.update(piv=piv, cons=cons)
    nc = len(cons)
    if nc == 0:
        fails.append("✘ 수축 구간을 찾지 못함")
        return out
    depths = [c[4] for c in cons]
    d1, dl = depths[0], depths[-1]
    # 피벗 = 최종 수축 시작 고점(대표 고가 — 장중에 잠깐 넘었다 밀린 고가·1봉 스파이크는 무시),
    # 손절 = 피벗봉 '다음'부터 종료점까지의 최저가 = 최종 수축 저점(깊이와 같은 저점)
    p_i = cons[-1][0]
    pivot = float(Hl[p_i])
    s_i = cons[-1][2]
    stop = float(A.L[s_i])
    base_high = Hl[j]
    in_prog = bool(e == last and nc >= 2 and s_i >= e - cfg.in_progress_bars + 1)
    out.update(depths=depths, pivot=pivot, p_i=p_i, stop=stop, s_i=s_i, in_prog=in_prog, base_high=base_high)

    # ---- 수축 구조
    if nc < cfg.min_contractions:
        fails.append(f"✘ 수축 {nc}회 (최소 {cfg.min_contractions}회 필요, 1~2봉 흔들림은 수축으로 보지 않음)")
    if nc > cfg.max_contractions:
        fails.append(f"✘ 수축 {nc}회 (최대 {cfg.max_contractions}회 초과 — 들쭉날쭉한 베이스)")
    if d1 < cfg.min_first_depth:
        fails.append(f"✘ 1차 수축 {d1:.1%} (최소 {cfg.min_first_depth:.0%})")
    if d1 > cfg.max_first_depth:
        fails.append(f"✘ 1차 수축 {d1:.1%} > {cfg.max_first_depth:.0%} (과도하게 깊음)")
    violations = 0
    for a, b in zip(depths, depths[1:]):
        if b > a * (1 + cfg.prog_rel_tol) + cfg.prog_abs_tol:
            violations = 99
            break
        if b > a * (1 - cfg.prog_min_shrink):
            violations += 1
    out["violations"] = violations
    if nc >= 2:
        if violations > cfg.max_prog_violations:
            fails.append(f"✘ 수축폭이 점진적으로 줄지 않음 ({_fmt_depths(depths)})")
        elif dl > d1 * cfg.final_to_first_max:
            fails.append(f"✘ 최종 수축 {dl:.1%} 가 1차 {d1:.1%} 대비 충분히 작지 않음")
    if nc >= 2 and dl > cfg.max_final_depth:
        fails.append(f"✘ 최종 수축 {dl:.1%} > {cfg.max_final_depth:.0%}")
    if nc >= 2 and dl > depths[-2] + cfg.final_vs_prev_abs:
        fails.append(f"✘ 최종 수축 {dl:.1%} 이 직전 수축 {depths[-2]:.1%} 보다 큼 (마지막이 가장 타이트해야 함)")
    base_bars = e - j + 1
    out["base_bars"] = base_bars
    if d1 > cfg.deep_first_depth and base_bars < cfg.deep_min_base_bars:
        fails.append(f"✘ {d1:.0%} 급락 후 {base_bars}봉 만에 회복 — V자 급반등 (깊은 베이스는 최소 "
                     f"{cfg.deep_min_base_bars}봉)")
    if nc >= 2 and e - cons[1][0] + 1 < cfg.min_phase_bars:
        fails.append(f"✘ 수축 국면이 {e - cons[1][0] + 1}봉 뿐 (최소 {cfg.min_phase_bars}봉) — 급등 직후 흔들림")
    pivot_from_high = pivot / base_high - 1
    out["pivot_from_high"] = pivot_from_high
    if pivot_from_high < -cfg.max_pivot_below_high:
        fails.append(f"✘ 피벗이 베이스 고점 대비 {pivot_from_high:.1%} (오른쪽이 충분히 회복되지 않음)")

    # ---- 돌파 전 구조 유지: (p_i, e] 의 종가가 피벗 위로 마감한 적 없음 (돌파 판정과 같은 정의)
    if p_i < e and A.C[p_i + 1:e + 1].max() > pivot:
        fails.append("✘ 분석 구간 안에서 이미 피벗 위 마감 (구조 불일치)")
    bo = None
    if e < last:  # 종료점 다음 1~2봉 안에 첫 '종가 > 피벗' (돌파봉이 피벗에 딱 마감 후 다음날 돌파하는 경우 포함)
        for b in range(e + 1, min(e + 1 + cfg.breakout_grace_bars, last + 1)):
            if A.C[b] > pivot:
                bo = b
                break
        if bo is None:
            fails.append("✘ 돌파 후보 봉이 피벗 위로 마감하지 못함")
    out["bo"] = bo
    if quick and fails:
        return out

    # ---- 거래량: 기준선 = 최종 수축 시작 직전 50일 거래량의 중앙값 (수축 중 고갈분이 기준을 끌어내리지 않게,
    #      뉴스 급등일 하루가 기준을 부풀리지 않게). 평균 기준 비율은 참고용으로 함께 기록.
    #      최종 수축 구간은 피벗봉(고점을 만든 상승일) 다음 날부터 — 상승일 거래량이 비율을 부풀리지 않게
    vavg = A.VS[p_i - 1] if p_i >= 1 else np.nan
    vbase = A.vol_base(p_i - 1)
    last_ratio = first_ratio = last_to_first = last_ratio_mean = np.nan
    dry = 0
    fw = A.V[p_i + 1:e + 1] if p_i < e else A.V[e:e + 1]
    good = np.isfinite(fw) & (fw > 0)
    bad_n = int(len(fw) - good.sum())
    out["bad_vol"] = bad_n
    if not (np.isfinite(vbase) and vbase > 0):
        fails.append("✘ 50일 거래량 기준선 산출 불가")
    elif bad_n > cfg.max_bad_vol_frac * len(fw):
        fails.append(f"✘ 최종 수축 구간 거래량 결측/0 {bad_n}봉 (/{len(fw)}봉) — 거래량 판정 불가")
    else:
        last_vol = float(fw[good].mean())
        v1 = A.V[j + 1:cons[0][2] + 1]
        v1 = v1[np.isfinite(v1) & (v1 > 0)]
        first_vol = float(v1.mean()) if len(v1) else np.nan
        last_ratio = last_vol / vbase
        first_ratio = first_vol / vbase
        last_ratio_mean = last_vol / vavg if vavg > 0 else np.nan
        last_to_first = last_vol / first_vol if first_vol > 0 else np.nan
        w = A.V[max(p_i + 1, e - cfg.dryup_window + 1):e + 1]
        dry = int(np.sum((w > 0) & (w < cfg.dryup_ratio * vbase)))
        if not last_ratio <= cfg.max_last_vol_ratio:
            fails.append(f"✘ 최종 수축 거래량 50일 중앙값의 {last_ratio:.2f}배 (≤{cfg.max_last_vol_ratio}배 필요"
                         + (f", 평균 기준 {last_ratio_mean:.2f}배는 급등일이 평균을 부풀린 착시)"
                            if last_ratio_mean <= cfg.max_last_vol_ratio else ")"))
        if not last_to_first <= cfg.max_last_to_first_vol:
            fails.append(f"✘ 최종 수축 거래량이 1차 수축보다 많음 ({last_to_first:.2f}배)")
    out.update(last_ratio=last_ratio, first_ratio=first_ratio, last_to_first=last_to_first, dry=dry,
               last_ratio_mean=last_ratio_mean, vbase=vbase)

    # ---- 타이트니스 (종가 범위 AND ATR 비수축 금지)
    tw = A.C[max(j, e - cfg.tight_bars + 1):e + 1]
    tight = float(tw.max() / tw.min() - 1) if tw.min() > 0 else np.nan
    max_tight = min(cfg.max_tight_range, max(cfg.min_tight_cap, cfg.tight_atr_mult * atr_b))
    base_atr = A.atr_mean(j, e)
    atr_ratio = float(A.ATRP[e] / base_atr) if base_atr > 0 and np.isfinite(A.ATRP[e]) else np.nan
    out.update(tight=tight, atr_ratio=atr_ratio, max_tight=max_tight)
    if not tight <= max_tight:
        fails.append(f"✘ 피벗 앞 타이트니스 부족 (최근 {cfg.tight_bars}봉 종가 범위 {tight:.1%} > {max_tight:.1%})")
    if not atr_ratio <= cfg.max_atr_ratio:
        fails.append(f"✘ 변동성 수축 없음 (최근 ATR 이 베이스 평균의 {atr_ratio:.2f}배)")

    # ---- 돌파 거래량 (돌파봉 거래량 / 전날까지 50일 평균 — 관례 기준, 중앙값 대비도 기록)
    bvr = bvr_rob = np.nan
    if bo is not None and np.isfinite(A.VS[bo - 1]) and A.VS[bo - 1] > 0:
        bvr = float(A.V[bo] / A.VS[bo - 1])
        vb = A.vol_base(bo - 1)
        bvr_rob = float(A.V[bo] / vb) if vb > 0 else np.nan
    out.update(bvr=bvr, bvr_rob=bvr_rob)
    # ---- 피벗 위 매물대 (감점용)
    out["overhead"] = _overhead(A, cfg, j, e, p_i, pivot, cons)
    return out


def _overhead(A: _Arrays, cfg: VCPConfig, j: int, e: int, p_i: int, pivot: float, cons: list) -> list[tuple]:
    """피벗 위 매물대: 최근 overhead_lookback 봉(종료점 기준, 베이스 이전 포함) ~ 피벗봉 전에서 대표 고가가
    피벗 × (1+tol) 를 넘은 '별개의 고점'(overhead_gap 봉 미만 간격의 돌출은 하나로 묶음) 목록 [(봉, 고가)].
    베이스 고점과 각 수축의 시작 고점이 속한 돌출은 VCP 자체의 하강 고점 계단이므로 제외."""
    lo = max(A.first_ok, e - cfg.overhead_lookback + 1)
    if p_i <= lo:
        return []
    idx = np.flatnonzero(A.Hc[lo:p_i] > pivot * (1 + cfg.overhead_tol)) + lo
    if not len(idx):
        return []
    own = {j} | {c[0] for c in cons}
    out: list[tuple] = []
    for grp in np.split(idx, np.flatnonzero(np.diff(idx) >= cfg.overhead_gap) + 1):
        if own.intersection(range(int(grp[0]) - 1, int(grp[-1]) + 2)):
            continue
        k = int(grp[np.argmax(A.Hc[grp])])
        out.append((k, float(A.Hc[k])))
    return out


def _score(r: dict, cfg: VCPConfig, trend: dict, last: int) -> None:
    """후보 r 의 점수(0~100)와 구성 요소를 r 에 기록."""
    depths = r["depths"]
    nc, dl, d1 = len(depths), depths[-1], depths[0]
    sc_con = {2: 12, 3: 18, 4: 20, 5: 18, 6: 15}.get(nc, 8) - 4 * min(r["violations"], 2)
    if dl <= cfg.ideal_final_depth:
        sc_fin = 15.0
    elif dl <= cfg.warn_final_depth:
        sc_fin = 15 - (dl - cfg.ideal_final_depth) / (cfg.warn_final_depth - cfg.ideal_final_depth) * 7
    else:
        span = max(cfg.max_final_depth - cfg.warn_final_depth, 1e-9)
        sc_fin = max(0.0, 8 - (dl - cfg.warn_final_depth) / span * 6)
    if r.get("in_prog"):
        sc_fin *= 0.5  # 진행 중 수축: 깊이가 잠정치
    tight, atr_ratio, max_tight = r.get("tight", np.nan), r.get("atr_ratio", np.nan), r.get("max_tight", 0.08)
    sc_tight = 0.0
    if np.isfinite(tight) and max_tight > cfg.ideal_tight_range:
        sc_tight += 7 * _clip01((max_tight - tight) / (max_tight - cfg.ideal_tight_range))
    elif np.isfinite(tight) and tight <= max_tight:
        sc_tight += 7.0
    if np.isfinite(atr_ratio):
        sc_tight += 3 * _clip01((1.0 - atr_ratio) / 0.5)
    sc_vol = 0.0
    lr = r.get("last_ratio", np.nan)
    if np.isfinite(lr):
        sc_vol = 10 * _clip01((1.0 - lr) / 0.5) + 5 * min(r.get("dry", 0), 3) / 3
    rs = trend.get("rs")
    sc_rs = 3.0 if rs is None else 10 * _clip01((rs - cfg.score_rs_lo) / (cfg.score_rs_hi - cfg.score_rs_lo))
    sc_trend = {8: 10.0, 7: 7.0}.get(trend["passed"], 3.0) if not trend["relaxed"] else 3.0
    lo_i, hi_i = cfg.ideal_base_bars
    sc_dur = 5.0 if lo_i <= r["base_bars"] <= hi_i else 2.0
    sc_d1 = 5.0 if 0.10 <= d1 <= cfg.deep_first_depth else (3.0 if d1 < 0.10 else 1.0)
    bvr = r.get("bvr", np.nan)
    if r["e"] < last:
        sc_bo = (10.0 if bvr >= cfg.strong_breakout_vol else 7.0 if bvr >= cfg.breakout_vol_mult
                 else 3.0 if bvr >= 1.0 else 0.0)
    else:
        sc_bo = 5.0
    # 감점: 피벗 위 매물대(별개 고점 overhead_min_count 개 이상), 진입 위험(피벗→손절) warn_risk 초과
    n_over = len(r.get("overhead", []))
    sc_over = 0.0
    if n_over >= cfg.overhead_min_count:
        sc_over = -min(cfg.overhead_penalty_max, cfg.overhead_penalty + 2.0 * (n_over - cfg.overhead_min_count))
    risk = 1 - r["stop"] / r["pivot"]
    sc_risk = 0.0
    if risk > cfg.warn_risk:
        sc_risk = -min(cfg.risk_penalty_max, cfg.risk_penalty + (risk - cfg.warn_risk) * 100)
    parts = {"수축": sc_con, "최종깊이": sc_fin, "타이트": sc_tight, "거래량": sc_vol, "RS": sc_rs,
             "추세": sc_trend, "기간": sc_dur, "1차깊이": sc_d1, "돌파량": sc_bo, "매물대": sc_over,
             "손절폭": sc_risk}
    r["score_parts"] = parts
    r["score"] = float(max(0.0, min(100.0, sum(parts.values()))))


class _Scanner:
    """종료점별 후보 평가 + 트렌드 템플릿 결과를 메모해 재사용 (규칙 7 의 과거 돌파 검사용)."""

    def __init__(self, ctx: StockContext, A: _Arrays, cfg: VCPConfig, trend_last: dict):
        self.ctx, self.A, self.cfg, self.trend_last = ctx, A, cfg, trend_last
        self.last = A.n - 1
        self.memo: dict[int, list[dict]] = {}     # 전체 평가(점수 포함)
        self.memo_q: dict[int, list[dict]] = {}   # 유효 여부만 (규칙 7 과거 검사)
        self.tt: dict[int, dict] = {}
        self.pre_fails: list[str] = []

    def trend_at(self, i: int) -> dict:
        if i not in self.tt:
            ev = tt_evaluate(self.ctx, at=i)
            self.tt[i] = {"passed": ev["passed"], "relaxed": False, "rs": ev["rs"], "ev": ev}
        return self.tt[i]

    def scan(self, e: int, quick: bool = False) -> list[dict]:
        """종료점 e 의 모든 (베이스 고점 × 임계값) 후보 평가 결과 (유효/탈락 모두).
        quick=True 는 유효 여부만 필요할 때(점수 생략, 구조 탈락 시 조기 종료)."""
        if e in self.memo:
            return self.memo[e]
        if quick and e in self.memo_q:
            return self.memo_q[e]
        A, cfg, ctx = self.A, self.cfg, self.ctx
        Hl = A.highs_until(e)
        out: list[dict] = []
        for j, depth in _base_high_candidates(A, cfg, e):
            p0 = max(A.first_ok, j - cfg.prior_lookback)
            if j - p0 < cfg.prior_min_bars:
                self.pre_fails.append(f"✘ 베이스 이전 데이터 부족 ({j - p0}봉): 선행 상승 확인 불가")
                continue
            bh = float(A.Hc[j])
            prior_hi = float(A.Hc[p0:j].max())
            if bh < prior_hi * cfg.min_high_vs_prior:
                self.pre_fails.append(
                    f"✘ 급락 후 반등 구간 — 베이스 고점 {bh:,.0f}({ctx.date(j)})이 직전 {j - p0}봉 고점 "
                    f"{prior_hi:,.0f} 대비 {1 - bh / prior_hi:.0%} 아래 (≤{1 - cfg.min_high_vs_prior:.0%} 필요)")
                continue
            prior_adv = bh / float(A.L[p0:j].min()) - 1
            if prior_adv < cfg.prior_advance_min:
                self.pre_fails.append(f"✘ 선행 상승 {prior_adv:.0%} < {cfg.prior_advance_min:.0%} "
                                      f"(베이스 고점 {ctx.date(j)})")
                continue
            atr_b = _median(A.ATRP[j:e + 1])  # 베이스 전체: 병합 허용치·타이트니스 상한
            if not (np.isfinite(atr_b) and atr_b > 0):
                atr_b = 0.03
            atr_r = _median(A.ATRP[max(j, e - cfg.zz_atr_window + 1):e + 1])  # 최근: 지그재그 임계값
            if not (np.isfinite(atr_r) and atr_r > 0):
                atr_r = atr_b
            for thr in _thresholds(cfg, atr_r):
                if thr >= depth * 0.9:
                    continue
                r = _evaluate(A, cfg, e, j, thr, atr_b, Hl, quick=quick)
                r.update(prior_adv=prior_adv, prior_hi=prior_hi)
                trend = self.trend_last
                r["trend_at_bo"] = False
                if r["bo"] is not None and not r["fails"]:  # 돌파한 베이스: 실제 돌파봉 시점의 엄격한 템플릿
                    trend = self.trend_at(r["bo"])
                    r["trend_at_bo"] = True
                    ev = trend["ev"]
                    if trend["passed"] < cfg.tt_min_pass:
                        r["fails"].append(f"✘ 돌파 시점({ctx.date(r['bo'])}) 트렌드 템플릿 "
                                          f"{trend['passed']}/8 < {cfg.tt_min_pass}")
                    elif cfg.require_near_high and not ev["checks"]["52주고점-25%이내"]:
                        r["fails"].append(f"✘ 돌파 시점({ctx.date(r['bo'])}) 종가가 52주 고점 대비 "
                                          f"{ev['from_52w_high']:.1%} — 고점 -25% 이내 필수(급락 후 반등)")
                r["trend"] = trend
                if "depths" in r and not quick:
                    _score(r, cfg, trend, self.last)
                out.append(r)
        (self.memo_q if quick else self.memo)[e] = out
        return out

    def inner_breakout(self, X: dict) -> dict | None:
        """규칙 7: X 의 베이스 (j, e] 안에 아직 '진행 중'인 유효 VCP 돌파(_in_play)가 있으면 그 후보."""
        A, cfg = self.A, self.cfg
        j, e = X["j"], X["e"]
        k = cfg.breakout_close_bars
        C, V, VS = A.C, A.V, A.VS
        need = cfg.inner_bo_min_vol

        def vol_ok(i: int) -> bool:  # _in_play 의 거래량 조건을 미리 걸러 불필요한 재평가 생략 (정확한 사전 필터)
            return i <= e and VS[i - 1] > 0 and V[i] >= need * VS[i - 1]

        for b in range(max(j + 1, k), e + 1):
            if not C[b] > C[b - k:b].max():
                continue
            if not (vol_ok(b) or (cfg.breakout_grace_bars > 1 and vol_ok(b + 1))):
                continue
            for Y in self.scan(b - 1, quick=True):
                bo = Y["bo"]
                if Y["fails"] or bo is None or not (j < bo <= e):
                    continue
                if _in_play(A, cfg, Y, e):
                    return Y
        return None


def _in_play(A: _Arrays, cfg: VCPConfig, Y: dict, until: int) -> bool:
    """돌파 Y 가 until 시점까지 '진행 중'인가 — 그 사이 생긴 새 피벗은 같은 셋업의 재베이스다.
    - 돌파봉 거래량 < 50일 평균 × inner_bo_min_vol 이면 돌파 시도로 보지 않음(찌르기) → 진행 중 아님
    - 손절가(최종 수축 저점)를 깼으면 실패한 셋업 → 진행 중 아님(새 구조 허용)
    - 돌파 후 min_base_bars(3주) 미만이면 → 진행 중 (새 베이스라 하기엔 짧음)
    - 3주 이상이면 종가가 매수 범위(피벗 +5%)를 넘어선 적이 없을 때만 진행 중. 이격까지 갔다가 조정받아
      새로 만든 베이스(base-on-base)는 별개 셋업."""
    bo = Y["bo"]
    bvr = Y.get("bvr", np.nan)
    if not (np.isfinite(bvr) and bvr >= cfg.inner_bo_min_vol):
        return False
    if float(A.L[bo:until + 1].min()) < Y["stop"]:
        return False
    if until - bo < cfg.min_base_bars:
        return True
    return float(A.C[bo:until + 1].max()) <= Y["pivot"] * (1 + cfg.buy_range)


# ---------------------------------------------------------------- 메인
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, VCPConfig)
    res = PatternResult(name=NAME, label=LABEL)
    try:
        return _detect(ctx, cfg, res)
    except Exception as ex:  # 안전망: 예상 못한 데이터로도 스캔 전체가 멈추지 않게
        res.detected = False
        res.warnings.append(f"✘ 분석 오류: {type(ex).__name__}: {ex}")
        return res


def _trend_state(ctx: StockContext, cfg: VCPConfig) -> tuple[dict | None, list[str]]:
    ev = tt_evaluate(ctx, at=-1)
    passed = ev["passed"]
    c, s50, s150, s200 = ev["close"], ev["sma50"], ev["sma150"], ev["sma200"]
    core = bool(c > s200 and s150 > s200 and ev["checks"]["200상승"])
    if passed >= cfg.tt_min_pass:
        state = {"passed": passed, "relaxed": False, "rs": ev["rs"], "ev": ev}
    elif cfg.allow_relaxed_trend and c < s50 and core:
        state = {"passed": passed, "relaxed": True, "rs": ev["rs"], "ev": ev}
    else:
        failed = [k for k, v in ev["checks"].items() if not v]
        return None, [f"✘ Stage 2 추세 아님: 트렌드 템플릿 {passed}/8 (미충족: {', '.join(failed)})"]
    if cfg.require_near_high and not ev["checks"]["52주고점-25%이내"]:
        return None, [f"✘ Stage 2 아님: 종가가 52주 고점 {ev['high52']:,.0f} 대비 {ev['from_52w_high']:.1%} — "
                      f"트렌드 템플릿 7번(고점 -25% 이내)은 필수, 급락 후 반등 구간 (템플릿 {passed}/8)"]
    return state, []


def _lost_spike_high(A: _Arrays, cfg: VCPConfig, ends: list[int]) -> tuple[int, float, float] | None:
    """원래 고가로는 베이스 고점 후보(분석 종료점에서 거꾸로 본 신고가)였지만 1봉 스파이크라 대표 고가로 낮춘 봉 중
    가장 높은 것 (탈락 사유 안내용): (봉, 원래 고가, 초과율). 종료점 후보를 가까운 것부터 본다."""
    for e in ends:
        lo = max(A.first_ok, e - cfg.max_base_bars)
        if e - lo < 2:
            continue
        rev = np.maximum.accumulate(A.H[lo:e + 1][::-1])[::-1]  # rev[k] = max(H[lo+k:e+1])
        hit = np.flatnonzero((A.spk[lo:e] > 0) & (A.H[lo:e] > rev[1:]))
        if len(hit):
            i = lo + int(hit[np.argmax(A.H[lo + hit])])
            return i, float(A.H[i]), float(A.spk[i])
    return None


def _select(valid: list[dict], A: _Arrays, cfg: VCPConfig) -> list[dict]:
    """규칙 7 의 후보 간 정리: 다른 후보 Y 의 돌파봉을 품은 후보 X 는, Y 가 아직 진행 중이면 X 를 버리고,
    아니면(찌르기·실패·이미 이격) Y 를 버린다(그 뒤 새로 형성된 X 가 최신 셋업)."""
    drop: set[int] = set()
    for xi, X in enumerate(valid):
        for yi, Y in enumerate(valid):
            bo = Y["bo"]
            if xi == yi or bo is None or Y["e"] >= X["e"] or not (X["j"] < bo <= X["e"]):
                continue
            drop.add(xi if _in_play(A, cfg, Y, X["e"]) else yi)
    return [r for i, r in enumerate(valid) if i not in drop]


def _detect(ctx: StockContext, cfg: VCPConfig, res: PatternResult) -> PatternResult:
    n = ctx.n
    if n < cfg.min_history:
        res.warnings.append(f"✘ 이력 부족 ({n}봉 < {cfg.min_history}봉): 200일선 추세 판정 불가")
        return res
    df = ctx.df
    win = df.iloc[-(cfg.max_base_bars + cfg.prior_lookback + 1):][["high", "low", "close"]].to_numpy(dtype=float)
    if not np.all(np.isfinite(win)) or np.any(win <= 0):
        res.warnings.append("✘ 가격 데이터에 결측/0 값이 있어 분석 불가")
        return res
    trend, why = _trend_state(ctx, cfg)
    if trend is None:
        res.warnings.extend(why)
        return res

    A = _Arrays(ctx, cfg)
    last = n - 1
    S = _Scanner(ctx, A, cfg, trend)
    valid: list[dict] = []
    near: dict | None = None

    def _near(r: dict) -> None:
        nonlocal near
        if "pivot" not in r:
            return
        key = (r["e"] != last, len(r["fails"]), -len(r["cons"]))  # 현재 시점 관점 우선
        if near is None or key < near["_key"]:
            r["_key"] = key
            near = r

    ends = _end_candidates(A, cfg)
    for e in ends:
        for r in S.scan(e):
            if r["fails"]:
                _near(r)
                continue
            Y = S.inner_breakout(r)
            if Y is not None:
                r = dict(r, fails=[f"✘ 베이스 안에서 이미 VCP 돌파 ({ctx.date(Y['bo'])}, 피벗 {Y['pivot']:,.0f}) 후 "
                                   f"매수 범위·손절가 안에서 진행 중 — 돌파 후 눌림을 새 수축으로 본 재형성 구조"])
                _near(r)
                continue
            valid.append(r)

    valid = _select(valid, A, cfg)
    if not valid:
        pre = list(dict.fromkeys(S.pre_fails))[:3]  # 급락 후 반등·선행 상승 부족 등으로 건너뛴 베이스 고점
        if near is not None:
            _fill(ctx, cfg, A, res, near, detected=False)
            res.warnings.insert(0, "✘ VCP 조건 미충족 (가장 근접한 베이스 기준 사유)")
            res.warnings.extend(w for w in pre if w not in res.warnings)
        else:
            res.warnings.append("✘ 유효한 베이스 없음 (최근 15~325봉 안에 8~50% 조정 후 형성된 베이스 고점 없음)")
            res.warnings.extend(pre)
        sp = _lost_spike_high(A, cfg, ends)
        if sp is not None:
            k, h, pct = sp
            res.warnings.append(f"✘ {ctx.date(k)} 고가 {h:,.0f} 는 1봉 스파이크(앞뒤 종가 대비 +{pct:.0%}) — "
                                f"베이스 고점으로 보지 않음 (대표 고가 {A.Hc[k]:,.0f})")
        return res
    best = max(valid, key=lambda r: (r["score"], r["e"]))
    _fill(ctx, cfg, A, res, best, detected=True)
    return res


def _fill(ctx: StockContext, cfg: VCPConfig, A: _Arrays, res: PatternResult, r: dict, detected: bool) -> None:
    """선택된 후보 r 로 결과 필드·사유·주석을 채운다."""
    e, j = r["e"], r["j"]
    trend = r["trend"]
    last = ctx.n - 1
    cons = r["cons"]
    depths = [c[4] for c in cons]
    pivot, stop = float(r["pivot"]), float(r["stop"])
    close = float(ctx.close.iloc[-1])
    res.pivot, res.stop = pivot, stop
    res.start_date = ctx.date(j)
    res.end_date = ctx.date(e)
    bo_i = None
    if detected:
        res.detected = True
        stage, bo_i = classify_stage(ctx, pivot, e, near_pct=cfg.near_pct, buy_range=cfg.buy_range,
                                     breakout_window=cfg.breakout_window, fail_pct=cfg.fail_pct)
        res.stage = stage
        res.score = round(r.get("score", 0.0), 1)
        if bo_i is not None:
            res.breakout_date = ctx.date(bo_i)
            res.end_date = ctx.date(bo_i)
    bvr, bvr_rob = r.get("bvr", np.nan), r.get("bvr_rob", np.nan)
    ev = trend["ev"]
    over = r.get("overhead", [])
    base_high = float(r.get("base_high", ctx.high.iloc[j]))
    res.metrics = {
        "n_contractions": len(cons),
        "depths": _fmt_depths(depths),
        "first_depth": round(depths[0], 4),
        "final_contraction_depth": round(depths[-1], 4),
        "final_contraction_bars": int(e - r["p_i"]),
        "final_in_progress": int(bool(r.get("in_prog"))),
        "base_days": int(r.get("base_bars", e - j + 1)),
        "base_weeks": round((e - j + 1) / 5, 1),
        "prior_advance": round(r["prior_adv"], 4),
        "base_high": base_high,
        "base_high_vs_prior": round(base_high / r["prior_hi"], 4) if r.get("prior_hi") else np.nan,
        "pivot_from_high": round(r.get("pivot_from_high", np.nan), 4),
        "last_contraction_vol_ratio": round(r.get("last_ratio", np.nan), 3),
        "last_contraction_vol_ratio_mean": round(r.get("last_ratio_mean", np.nan), 3),
        "first_contraction_vol_ratio": round(r.get("first_ratio", np.nan), 3),
        "last_to_first_vol": round(r.get("last_to_first", np.nan), 3),
        "dryup_days": int(r.get("dry", 0)),
        "tightness": round(r.get("tight", np.nan), 4),
        "tight_limit": round(r.get("max_tight", np.nan), 4),
        "atr_ratio": round(r.get("atr_ratio", np.nan), 3),
        "pivot_distance": round(close / pivot - 1, 4),
        "risk_pct": round(1 - stop / pivot, 4),
        "breakout_vol_ratio": round(bvr, 3) if np.isfinite(bvr) else np.nan,
        "breakout_vol_ratio_robust": round(bvr_rob, 3) if np.isfinite(bvr_rob) else np.nan,
        "overhead_highs": len(over),
        "overhead_levels": ", ".join(f"{ctx.date(k)[5:]} {h:,.0f}" for k, h in over),
        "overhead_max_pct": round(max(h for _, h in over) / pivot - 1, 4) if over else 0.0,
        "from_52w_high": round(ev["from_52w_high"], 4),
        "trend_passed": int(trend["passed"]),
        "rs": ev["rs"] if ev["rs"] is not None else np.nan,
        "zigzag_pct": r["thr"],
    }
    for k, v in r.get("score_parts", {}).items():
        res.metrics[f"sc_{k}"] = round(v, 1)

    # ---- 사유 / 경고
    ok, ng = res.reasons, res.warnings
    if trend["relaxed"]:
        ng.append(f"✘ 트렌드 템플릿 {trend['passed']}/8 — 베이스 안(50일선 아래)이라 핵심 3개 기준으로 완화 판정")
    else:
        when = f", 돌파일 {ctx.date(r['bo'])} 기준" if r.get("trend_at_bo") else ""
        ok.append(f"✔ Stage 2 상승 추세 (트렌드 템플릿 {trend['passed']}/8{when})")
    ok.append(f"✔ 선행 상승 +{r['prior_adv']:.0%} (직전 {cfg.prior_lookback}봉 저점 대비)")
    bars = e - j + 1
    (ok if cfg.ideal_base_bars[0] <= bars <= cfg.ideal_base_bars[1] else ng).append(
        ("✔ " if cfg.ideal_base_bars[0] <= bars <= cfg.ideal_base_bars[1] else "✘ ")
        + f"베이스 {bars / 5:.0f}주 ({bars}봉, 이상적 4~25주)")
    if r["fails"]:
        ng.extend(r["fails"])
    else:
        ok.append(f"✔ 수축 {len(cons)}회, 점진적 축소: {_fmt_depths(depths)}")
    if depths[0] > cfg.deep_first_depth:
        ng.append(f"✘ 1차 수축 {depths[0]:.1%} — 깊은 베이스(>{cfg.deep_first_depth:.0%}), 실패 확률 높음")
    if r.get("violations", 0) == 1:
        ng.append("✘ 수축폭이 한 차례 줄지 않음 (허용 범위)")
    dl = depths[-1]
    if r.get("in_prog"):
        ng.append(f"✘ 최종 수축 진행 중 (저점 {ctx.date(r['s_i'])} 미확정) — 깊이 {dl:.1%}·손절가는 잠정치")
    elif not r["fails"]:
        if dl <= cfg.ideal_final_depth:
            ok.append(f"✔ 최종 수축 {dl:.1%} — 매우 타이트")
        elif dl <= cfg.warn_final_depth:
            ok.append(f"✔ 최종 수축 {dl:.1%}")
        else:
            ng.append(f"✘ 최종 수축 {dl:.1%} — 10% 초과로 다소 느슨함")
    lr = r.get("last_ratio", np.nan)
    if np.isfinite(lr) and lr <= cfg.max_last_vol_ratio:
        msg = (f"최종 수축 평균 거래량 50일 중앙값의 {lr:.2f}배 (평균 기준 {r['last_ratio_mean']:.2f}배, "
               f"1차 수축의 {r['last_to_first']:.2f}배)")
        if lr <= cfg.ideal_last_vol_ratio:
            ok.append("✔ " + msg)
        else:
            ng.append("✘ " + msg + " — 감소 폭이 크지 않음")
    if r.get("dry", 0) > 0:
        ok.append(f"✔ 거래량 고갈일 {r['dry']}일 (50일 중앙값의 {cfg.dryup_ratio:.0%} 미만)")
    if r.get("bad_vol", 0) > 0 and not any("결측" in f for f in r["fails"]):
        ng.append(f"✘ 최종 수축 구간 거래량 결측/0 {r['bad_vol']}봉 (평균에서 제외)")
    tight, atr_ratio, mt = r.get("tight", np.nan), r.get("atr_ratio", np.nan), r.get("max_tight", np.nan)
    if np.isfinite(tight) and not r["fails"]:
        good = atr_ratio <= cfg.tight_atr_ratio
        ok.append(f"✔ 피벗 앞 {cfg.tight_bars}봉 종가 범위 {tight:.1%} (≤{mt:.1%})")
        (ok if good else ng).append(("✔ " if good else "✘ ") + f"ATR 비율 {atr_ratio:.2f} (베이스 평균 대비"
                                    + (", 변동성 뚜렷이 수축)" if good else ", 수축 폭 작음)"))
    rs = ev["rs"]
    if rs is not None:
        good = rs >= cfg.rs_good
        (ok if good else ng).append(("✔ " if good else "✘ ") + f"RS 레이팅 {rs:.0f}"
                                    + ("" if good else f" ({cfg.rs_good:.0f} 이상 권장)"))
    pfh = r.get("pivot_from_high", 0.0)
    if pfh < -cfg.warn_pivot_below_high:
        ng.append(f"✘ 피벗이 베이스 고점보다 {abs(pfh):.0%} 낮음 — 위쪽 매물대 존재")
    # 1봉 스파이크로 무시한 고가: 베이스 고점(왼쪽 peak_left_bars 봉 ~ 종료점)·피벗(피벗봉 ~ 종료점) 위로 솟은 것
    for what, s0, lvl in (("피벗", r["p_i"] - 1, pivot), ("베이스 고점", j - cfg.peak_left_bars, base_high)):
        sp = A.spike_above(s0, e, lvl)
        if sp is not None:
            ng.append(f"✘ {ctx.date(sp[0])} 고가 {sp[1]:,.0f} 는 1봉 스파이크(앞뒤 종가 대비 +{sp[2]:.0%}) — "
                      f"무시하고 대표 고가로 {what} {lvl:,.0f} 계산")
            break
    sc = r.get("score_parts", {})
    if over:
        lv = ", ".join(f"{ctx.date(k)[5:]} {h:,.0f}" for k, h in over[:4]) + (" …" if len(over) > 4 else "")
        if len(over) >= cfg.overhead_min_count:
            ng.append(f"✘ 피벗 위 매물대: 피벗 +{cfg.overhead_tol:.0%} 위 별개 고점 {len(over)}개 ({lv}) — "
                      f"저항대 아래 피벗 (점수 {sc.get('매물대', 0):+.0f})")
        else:
            ng.append(f"✘ 피벗 +{cfg.overhead_tol:.0%} 위 고점 {len(over)}개 ({lv}) — 돌파 시 매물 소화 필요")
    risk = 1 - stop / pivot
    if risk > cfg.warn_risk:
        ng.append(f"✘ 진입 위험(피벗→손절) {risk:.1%} > {cfg.warn_risk:.0%} — 미너비니 손절 7~8% 초과 "
                  f"(점수 {sc.get('손절폭', 0):+.0f})")
    if bo_i is not None:
        vs = ctx.vol_sma(cfg.vol_avg_n).iloc[bo_i - 1]
        bv = float(ctx.vol.iloc[bo_i] / vs) if vs > 0 else np.nan
        vb = A.vol_base(bo_i - 1)
        bvr_rob = float(ctx.vol.iloc[bo_i] / vb) if vb > 0 else np.nan
        res.metrics["breakout_vol_ratio"] = round(bv, 3) if np.isfinite(bv) else np.nan
        res.metrics["breakout_vol_ratio_robust"] = round(bvr_rob, 3) if np.isfinite(bvr_rob) else np.nan
        if not np.isfinite(bv):
            ng.append("✘ 돌파 거래량 산출 불가")
        elif bv >= cfg.breakout_vol_mult:
            ok.append(f"✔ 돌파 거래량 50일 평균의 {bv:.2f}배 (중앙값의 {bvr_rob:.2f}배)")
        else:
            ng.append(f"✘ 돌파 거래량 {bv:.2f}배 (< {cfg.breakout_vol_mult}배, 중앙값의 {bvr_rob:.2f}배) "
                      f"— 돌파 신뢰도 낮음")
        if bo_i == last and ctx.partial:
            ng.append("✘ 돌파봉이 장중 미완성 봉 (거래량은 하루치 환산 추정)")
    ms = ctx.market_state
    if ms is not None and getattr(ms, "state", None) == "correction":
        ng.append("✘ 시장 조정 국면 — 돌파 실패 확률 높음")
    # 거래정지일: 패턴 구간(50일 평균 산출 구간 포함) ~ 마지막 봉 사이만 (잘린 데이터에 미래 정지일 유입 방지)
    lo_d, hi_d = ctx.date(max(0, j - cfg.vol_avg_n)), ctx.date(last)
    halts = [d for d in (ctx.df.attrs.get("halt_dates") or []) if lo_d <= str(d) <= hi_d]
    if halts:
        ng.append(f"✘ 패턴 구간에 거래정지일 존재 ({', '.join(map(str, halts[:3]))}) — 거래량 비교 왜곡 가능")

    # ---- 차트 주석
    piv = r["piv"]
    pts = [(ctx.df.index[p[0]], p[1]) for p in piv]
    ann = [segment(pts, "VCP 수축", "#ff6d00")]
    for hi_i, hi_p, lo_i, lo_p, d in cons:
        ann.append(marker(ctx.df.index[lo_i], f"-{d * 100:.0f}%", position="below", color="#ff6d00",
                          shape="arrowUp"))
    ann.append(hline(pivot, f"피벗 {pivot:,.0f}", "#2962ff", "dashed"))
    ann.append(hline(stop, f"손절 {stop:,.0f}" + (" (잠정)" if r.get("in_prog") else ""), "#d50000", "dotted"))
    ann.append(box(ctx.df.index[r["p_i"]], ctx.df.index[e], pivot, stop, "최종 수축", "#7e57c2"))
    if bo_i is not None:
        bvr_m = res.metrics["breakout_vol_ratio"]
        txt = f"돌파 {bvr_m:.1f}x" if np.isfinite(bvr_m) else "돌파"
        ann.append(marker(ctx.df.index[bo_i], txt, position="below", color="#00c853", shape="arrowUp"))
    res.annotations = ann
