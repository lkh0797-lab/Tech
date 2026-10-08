"""보컬(김형준) 눌림목 — 강한 테마 대장주가 큰 상승 뒤 눌렸다가 지지선에서 거래대금이 다시 들어오는 자리.

규칙과 숫자는 ``chart_screener/vocal.py`` 맨 위 설명(① 거래대금 150위 → ② 강한 테마 → ③ 대장주 → ④ 큰 상승 → ⑤ 눌림 →
⑥ 지지선 · 거래량 감소 → ⑦ 재유입 양봉 → ⑧ 다음 날 시가 진입)과 같다. ①~③은 전 시장 단면이라 ``scanner.run_scan`` 이
``vocal.prepare`` 로 한 번 세어 ``ctx.info["vocal"]`` 에 넣고, 이 탐지기는 그 결과를 읽어 단계 · 근거 · 차트 표시로 바꾼다.
단일 종목 analyze · backtest 처럼 단면이 없으면 판정하지 않는다.

detected = 깔때기 ④~⑦ (기업추적 보컬 탭의 깔때기 표와 같은 범위). 급등 구간(바닥 ~ 오늘)에 강한 테마의 대장 · 부대장이었는지는
근거에 적고, 대장 이력이 없으면 경고로 남긴다(원래 보컬의 ⑧ 진입 후보는 대장만).
단계 — ④ 큰 상승 · ⑤ 눌림 = 형성 중, ⑥ 지지선 닿음 + 거래량 감소 = 피벗 근접, ⑦ 재유입 양봉 = 돌파(대장 · 손익비 1.5↑일 때만, 아니면 피벗 근접).
손절 = 눌림 저점, 목표 = 직전 고점. 피벗은 ⑦ 신호봉 종가(진입은 다음 날 시가)일 때만.

**과거 검증은 손실** (기업추적 도구/보컬_백테스트.py, 2013~2026 매 거래일, ⑦ · 대장 · 손익비 1.5↑ → 다음 날 시가 진입 ·
규칙 청산: 346건 승률 31% · 평균 −2.4% · 20일 초과수익 −4.8%p). 그래서 scoring.BASE_PATTERNS 에 넣지 않는다 —
종합 점수 · 매수 계획 · 실시간 감시에 쓰이지 않고, 후보 목록의 '보컬' 칩(관찰)으로만 보인다.
"""
from __future__ import annotations

from ..vocal import VocalConfig
from .base import BREAKOUT, FORMING, NEAR_PIVOT, PatternResult, StockContext, hline, marker, register, segment

STAGE_OF = {4: FORMING, 5: FORMING, 6: NEAR_PIVOT, 7: BREAKOUT}
STEP = {4: "④ 큰 상승 뒤", 5: "⑤ 눌림 중", 6: "⑥ 지지선 · 거래량 감소", 7: "⑦ 재유입 양봉(신호)"}
BT_NOTE = ("과거 검증(2013~2026, ⑦ 신호 400건 중 보유 겹침을 뺀 346거래): 승률 31% · 거래당 평균 −2.4% · "
           "20일 초과수익 −4.8%p — 관찰용, 매수 신호로 쓰지 않음")


def _won(x) -> str:
    return f"{x:,.0f}" if x is not None and x == x else "—"


@register("vocal", "보컬")
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg("vocal", VocalConfig)
    r = PatternResult(name="vocal", label="보컬")
    info = ctx.info or {}
    f = info.get("vocal")
    if info.get("vocal_skip"):
        r.warnings.append(info["vocal_skip"])
        return r
    if "vocal" not in info:
        r.warnings.append("보컬은 전 종목 scan 에서만 판정 — 거래대금 순위 · 테마 강도가 전 시장 기준")
        return r
    if not f:
        r.warnings.append(f"깔때기 밖 — 최근 {cfg.pool_days}거래일 동안 거래대금 {cfg.top}위 안에 든 날이 없다")
        return r
    st = int(f.get("stage") or 0)
    lead = f.get("lead") or []
    m = r.metrics
    m.update({k: f.get(k) for k in ("stage", "rank", "pool_days", "gain", "rise", "n_rank", "days", "depth", "depth_min",
                                     "retrace", "touched", "reflow_x", "rr", "stop_pct", "target_pct", "n_theme_days")})
    m.update(target=f.get("target") or f.get("H"), high=f.get("H"), base_low=f.get("base_lo"), pullback_low=f.get("pl"),
             high_date=f.get("hk"), base_date=f.get("lk"), peak_vol_date=f.get("bk"),
             lead=lead, themes=(f.get("themes") or [])[:8], asof=f.get("asof"))
    # ① ~ ③
    r.reasons.append(f"① 거래대금 {cfg.top}위 안 최근 {cfg.pool_days}거래일 중 {f.get('pool_days', 0)}일"
                     + (f" · 오늘 {f['rank']}위" if f.get("rank") else ""))
    if lead:
        t, role, day = lead[0]
        more = f" 외 {len(lead) - 1}" if len(lead) > 1 else ""
        r.reasons.append(f"②③ 강한 테마 '{t}' {role} ({day}부터){more} · 급등 구간에 강한 테마였던 날 {f.get('n_theme_days', 0)}일")
    else:
        r.warnings.append("②③ 급등 구간(바닥~오늘)에 강한 테마의 대장 · 부대장이었던 적 없음 — 원래 보컬 진입 후보(⑧)는 대장만")
    if st < 4:
        r.warnings.append(f.get("why") or "④ 큰 상승 조건 미달")
        return r
    r.reasons.append(f"④ 바닥 {_won(f.get('base_lo'))} → 고점 {_won(f.get('H'))} (+{f.get('gain', 0):.0f}%, {f.get('rise')}봉) · "
                     f"상승 중 순위 안 {f.get('n_rank')}일")
    if st >= 5:
        r.reasons.append(f"⑤ 고점 뒤 {f.get('days')}봉 · 종가 −{f.get('depth', 0):.1f}% (눌림 저점 {_won(f.get('pl'))}, "
                         f"상승 폭의 {f.get('retrace', 0):.0f}% 되돌림)")
    elif f.get("why"):
        r.warnings.append(f["why"])
    if f.get("touched"):
        dry = "거래량 마름" if (f.get("dry_prev") or f.get("dry_now")) else "거래량 아직 안 마름"
        vr = f.get("v_ratio_peak")
        r.reasons.append(f"⑥ 지지선 닿음: {', '.join(f['touched'])} · {dry}" + (f" (급등 최대봉의 {vr * 100:.0f}%)" if vr else ""))
    elif st >= 5:
        r.warnings.append("⑥ 지지선(5·10·20일선 · 전고점 · 급등봉 시가/중간 · 50% 되돌림) ±2% 안에 아직 안 닿음")
    if st == 7:
        r.reasons.append(f"⑦ 재유입 {f.get('reflow_x') or 0:.1f}배 · 양봉 · 지지 지킴 · 5일선 위 — 진입은 다음 날 시가")
    elif st == 6 and f.get("why"):
        r.warnings.append(f["why"])
    rr = f.get("rr")
    if rr is not None:
        (r.reasons if rr >= cfg.rr_min else r.warnings).append(
            f"⑧ 손익비 {rr:.1f} (손절 {_won(f.get('stop'))} {f.get('stop_pct') or 0:+.1f}% · 목표 {_won(f.get('target'))} "
            f"{f.get('target_pct') or 0:+.1f}%)" + ("" if rr >= cfg.rr_min else f" — {cfg.rr_min} 미만"))
    r.warnings.append(BT_NOTE)
    for w in f.get("warn_j") or []:
        r.warnings.append("참고: " + w)
    if f.get("junk"):
        # 원본 보컬 탭은 잡주를 깔때기 표에서 기본으로 숨기고 진입 후보에서 뺀다 — 같게 칩에서 뺀다
        r.warnings.insert(0, "잡주로 제외: " + " · ".join(f["junk"]))
        m["junk"] = f["junk"]
        return r
    r.detected = True
    r.stage = STAGE_OF.get(st, FORMING)
    if st == 7 and (not lead or rr is None or rr < cfg.rr_min):
        r.stage = NEAR_PIVOT
    r.score = {4: 40.0, 5: 55.0, 6: 70.0, 7: 85.0}.get(st, 0.0)       # 단계 점수 — 검증된 품질 점수가 아니다
    r.stop = f.get("pl")
    r.pivot = f.get("entry") if r.stage == BREAKOUT else None
    r.start_date, r.end_date = f.get("lk"), f.get("asof")
    r.breakout_date = f.get("asof") if r.stage == BREAKOUT else None
    m["step"] = STEP.get(st)
    # 차트
    ann = r.annotations
    if f.get("H"):
        ann.append(hline(f["H"], "직전 고점(목표)", "#ef5350"))
    if f.get("pl"):
        ann.append(hline(f["pl"], "눌림 저점(손절)", "#1e88e5", "solid"))
    for nm, lv in f.get("touched_lv") or []:
        ann.append(hline(lv, f"지지: {nm}", "#7e57c2"))
    if f.get("lk") and f.get("hk") and f.get("base_lo") and f.get("H"):
        ann.append(segment([(f["lk"], f["base_lo"]), (f["hk"], f["H"])], "④ 큰 상승", "#ff6d00"))
    if f.get("hk"):
        ann.append(marker(f["hk"], "고점", "above", "#ef5350", "arrowDown"))
    if f.get("bk"):
        ann.append(marker(f["bk"], "급등 최대봉", "above", "#ff6d00", "circle"))
    if st == 7 and f.get("asof"):
        ann.append(marker(f["asof"], "⑦ 신호", "below", "#e91e63", "arrowUp"))
    return r
