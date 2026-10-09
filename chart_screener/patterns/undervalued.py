"""저평가 종목 (undervalued) — 기업추적 저평가 화면이 고른 종목(가치는 지켰는데 주가가 빠진 회사)을 정보 칩으로 붙인다.

차트 패턴이 아니라 외부 목록이다. ``scanner.run_scan`` 이 ``value_list.load_value`` 로 읽은 목록 행을
``ctx.info["undervalued"]`` 에 넣고(목록에 없으면 None), 이 탐지기는 그 행을 등급 · 점수 · PER 1년 전 → 지금 ·
52주 고점 대비 · ROE · 부채비율 같은 수치와 근거로 바꾼다. (``ctx.info["value"]`` 는 당일 거래대금이라 다른 키를 쓴다.)

detected = 목록에 있음(저평가 · 관찰 등급 모두 — 등급은 metrics.tier). 단계 · 피벗 · 손절은 없다.
**관찰용** — scoring.BASE_PATTERNS 밖이라 종합 점수 · 매수 계획 · 실시간 감시에 쓰지 않고, 혼자서 후보를 만들지 않는다
(scoring.is_candidate). 후보 목록의 '저평가 종목' 칩은 후보 중 목록 종목만 거르는 필터다.
score = 기업추적 저평가 점수(0~100) — 상세 탭 표시용이며 종합 점수에는 들어가지 않는다.
"""
from __future__ import annotations

from ..value_list import ENV
from .base import PatternResult, StockContext, register

NAME, LABEL = "undervalued", "저평가 종목"
BT_NOTE = ("과거 검증(기업추적 차트 셋업 검증): 저평가 범위 안 바닥 투매 흡수 6개월 +3.4%p · 컵 12개월 +6~10%p "
           "(앞 기간 약함, 표본 수백 건) — 관찰용, 점수 · 매수 계획에 안 들어감")


def _f(x, nd: int = 1, sign: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    r = PatternResult(name=NAME, label=LABEL)
    info = ctx.info or {}
    if "undervalued" not in info:
        r.warnings.append(f"저평가 목록 파일 없음 — 기업추적 뷰어가 쓴 JSON 경로를 환경변수 {ENV} 에 (전 종목 scan 에서만)")
        return r
    v = info.get("undervalued")
    if not v:
        r.warnings.append("기업추적 저평가 목록에 없음")
        return r
    m = r.metrics
    m.update({k: v.get(k) for k in ("tier", "score", "per_then", "per", "per_pct", "dd", "px_yoy", "roe", "debt_eq",
                                     "ni_yoy", "industry", "risk", "tier_why")})
    m["observe_only"] = True
    tier, score = v.get("tier"), v.get("score")
    r.reasons.append(f"기업추적 저평가 등급: {tier}" + (f" · 저평가 점수 {score:.0f}" if score is not None else ""))
    per = f"PER 1년 전 {_f(v.get('per_then'))} → 지금 {_f(v.get('per'))}"
    if v.get("per_pct") is not None:
        per += f" · 자기 역사 백분위 {v['per_pct']:.0f}% (0 = 역대 가장 쌈)"
    r.reasons.append(per)
    r.reasons.append(f"52주 고점 대비 {_f(v.get('dd'), sign=True)}% · 주가 1년 {_f(v.get('px_yoy'), sign=True)}%")
    r.reasons.append(f"ROE {_f(v.get('roe'))}% · 부채비율 {_f(v.get('debt_eq'), 0)}% · 순이익 1년 {_f(v.get('ni_yoy'), sign=True)}%"
                     + (f" · 업종 {v['industry']}" if v.get("industry") else ""))
    for w in v.get("tier_why") or []:
        r.warnings.append("관찰 사유: " + w)
    if v.get("risk"):
        r.warnings.append("공시 위험: " + v["risk"])
    r.warnings.append(BT_NOTE)
    r.detected = True
    r.score = float(score) if score is not None else 0.0
    return r
