"""미너비니 트렌드 템플릿 8개 기준 — 업종·테마 강도(sector.py)의 'TT 통과 비율'에 쓰는 계산.

패턴이 아니다(REGISTRY 에 없음 — 칩 · 점수 · 후보에 안 쓴다). 2026-10-14 패턴 초기화 때 옛 탐지기
patterns/trend_template.py 의 설정 · 평가 함수만 값 그대로 옮겼다 (sector.tt_pass 가 같은 규칙인지 맞춰 보는 기준).

기준 (Minervini, *Trade Like a Stock Market Wizard*):
 1. 종가 > 150일선, 종가 > 200일선
 2. 150일선 > 200일선
 3. 200일선이 최소 1개월(22거래일) 이상 상승 중
 4. 50일선 > 150일선, 50일선 > 200일선
 5. 종가 > 50일선
 6. 종가가 52주 최저가 대비 +30% 이상
 7. 종가가 52주 최고가 대비 -25% 이내
 8. RS 레이팅 70 이상
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .patterns.base import StockContext

CFG_KEY = "trend_template"     # Config.patterns 덮어쓰기 키 (예전과 같은 이름)


@dataclass
class TrendTemplateConfig:
    sma200_rising_days: int = 22
    above_52w_low: float = 0.30
    within_52w_high: float = 0.25
    rs_min: float = 70.0
    min_pass_for_detect: int = 8     # 8개 모두 충족해야 통과


def evaluate(ctx: StockContext, cfg: TrendTemplateConfig | None = None, at: int = -1) -> dict:
    """``at`` 봉 시점의 8개 기준 평가 결과 dict."""
    cfg = cfg or ctx.cfg.pattern_cfg(CFG_KEY, TrendTemplateConfig)
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
