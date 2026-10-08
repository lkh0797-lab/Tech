"""마크 미너비니 트렌드 템플릿 (Stage 2 상승 추세 판정).

VCP·컵앤핸들 등 모든 '상승 지속형 베이스' 패턴의 전제 조건으로 사용된다.

기준 (Minervini, *Trade Like a Stock Market Wizard*):
 1. 종가 > 150일선, 종가 > 200일선
 2. 150일선 > 200일선
 3. 200일선이 최소 1개월(22거래일) 이상 상승 중
 4. 50일선 > 150일선, 50일선 > 200일선
 5. 종가 > 50일선
 6. 종가가 52주 최저가 대비 +30% 이상
 7. 종가가 52주 최고가 대비 -25% 이내
 8. RS 레이팅 70 이상 (80~90 이상이 바람직)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import PatternResult, StockContext, hline, register


@dataclass
class TrendTemplateConfig:
    sma200_rising_days: int = 22
    above_52w_low: float = 0.30
    within_52w_high: float = 0.25
    rs_min: float = 70.0
    min_pass_for_detect: int = 8     # 8개 모두 충족해야 detected


def evaluate(ctx: StockContext, cfg: TrendTemplateConfig | None = None, at: int = -1) -> dict:
    """``at`` 봉 시점의 8개 기준 평가 결과 dict (다른 패턴에서 재사용)."""
    cfg = cfg or ctx.cfg.pattern_cfg("trend_template", TrendTemplateConfig)
    i = at if at >= 0 else ctx.n + at
    c = float(ctx.close.iloc[i])
    s50, s150, s200 = (float(ctx.sma(n).iloc[i]) for n in (50, 150, 200))
    s200_prev = ctx.sma(200).iloc[i - cfg.sma200_rising_days] if i >= cfg.sma200_rising_days else np.nan
    win = ctx.df.iloc[max(0, i - 251):i + 1]
    hi52, lo52 = float(win["high"].max()), float(win["low"].min())
    rs = None
    if ctx.rs_rating_hist is not None and len(ctx.rs_rating_hist):
        rs_s = ctx.rs_rating_hist.loc[:ctx.df.index[i]]
        rs = float(rs_s.iloc[-1]) if len(rs_s) else None
    elif at == -1:
        rs = ctx.rs_rating

    def ok(x) -> bool:
        return bool(x) if x == x else False  # NaN → False

    checks = {
        "c>150&200": ok(c > s150 and c > s200),
        "150>200": ok(s150 > s200),
        "200상승": ok(s200 > s200_prev),
        "50>150&200": ok(s50 > s150 and s50 > s200),
        "c>50": ok(c > s50),
        "52주저점+30%": ok(c >= lo52 * (1 + cfg.above_52w_low)),
        "52주고점-25%이내": ok(c >= hi52 * (1 - cfg.within_52w_high)),
        "RS": rs is not None and rs >= cfg.rs_min,
    }
    return {
        "checks": checks, "passed": sum(checks.values()), "close": c,
        "sma50": s50, "sma150": s150, "sma200": s200, "high52": hi52, "low52": lo52, "rs": rs,
        "from_52w_low": c / lo52 - 1 if lo52 else np.nan,
        "from_52w_high": c / hi52 - 1 if hi52 else np.nan,
    }


_DESC = {
    "c>150&200": "종가가 150일선·200일선 위",
    "150>200": "150일선 > 200일선 (정배열)",
    "200상승": "200일선 1개월 이상 상승",
    "50>150&200": "50일선 > 150·200일선",
    "c>50": "종가가 50일선 위",
    "52주저점+30%": "52주 저점 대비 +30% 이상",
    "52주고점-25%이내": "52주 고점 대비 -25% 이내",
    "RS": "RS 레이팅 기준 충족",
}


@register("trend_template", "트렌드 템플릿(Stage 2)")
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg("trend_template", TrendTemplateConfig)
    res = PatternResult(name="trend_template", label="트렌드 템플릿(Stage 2)")
    if ctx.n < 220:
        res.warnings.append(f"이력 부족 ({ctx.n}일 < 220일)")
        return res
    ev = evaluate(ctx, cfg)
    for k, passed in ev["checks"].items():
        (res.reasons if passed else res.warnings).append(("✔ " if passed else "✘ ") + _DESC[k])
    res.detected = ev["passed"] >= cfg.min_pass_for_detect
    # 점수: 충족 개수 + RS·52주 고점 근접도 가산
    rs = ev["rs"] or 0
    res.score = float(min(100, ev["passed"] / 8 * 70 + max(0, rs - 70) / 29 * 15
                          + max(0, 0.25 + ev["from_52w_high"]) / 0.25 * 15))
    res.metrics = {k: v for k, v in ev.items() if k != "checks"} | {"passed": ev["passed"]}
    res.start_date = ctx.date(max(0, ctx.n - 252))
    res.end_date = ctx.date(ctx.n - 1)
    res.annotations = [hline(ev["high52"], "52주 고점", "#9e9e9e", "dotted")]
    return res
