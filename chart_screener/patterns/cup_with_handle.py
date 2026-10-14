"""컵 앤 핸들 — 사용자가 준 식(cwh_reference.py, RULE_VERSION cwh_reference_v1.0.0)을 Tech 탐지기로 잇는 얇은 어댑터.

식 파일은 받은 그대로 둔다(바이트 동일 — tests/test_cwh_reference.py 가 해시로 확인). 임계값을 바꾸지 않고, 이 모듈은
(1) Tech 일봉 → 식의 Bar 목록, (2) 식의 결과 → PatternResult(단계 · 피벗 · 근거 · 차트 표시)로 바꾸기만 한다.
2026-10-14 패턴 초기화 때 옛 탐지기 'cup_handle'(다른 식)을 지우고 새 키로 넣었다 — 일지 · 기록 채점에서 옛 기록과 섞이지 않게.

입력
  - 일봉: StockContext.df 의 수정주가 OHLC + 거래량. 거래정지일(df.attrs['halt_dates'] — 공용 로더가 df 에서 뺀 날)은
    O=H=L=C=직전 종가 · 거래량 0 봉으로 되살려 넣는다. 식의 zero_volume_fraction(최근 50봉 중 거래량 0 비율 ≤ 10%)
    규칙이 정지일을 실제로 보게 하려는 것 — 빼 둔 채 넘기면 그 규칙이 늘 0% 로 통과해 사실과 다르다.
  - 거래량은 Tech 캐시 그대로(원 거래량, 미수정 — 가격만 수정주가). 식은 '같은 기준으로 수정된 OHLCV'를 전제하는데
    Tech 에는 수정 비율 자료가 없어 거래량을 맞출 수 없다. 그래서
      · 사건일 RVOL 비교 구간(직전 50봉)에 거래정지일이 있으면 식의 거래량 확인을 믿지 않는다 — 정지가 분할 · 병합이면
        주식 수가 바뀌어 RVOL 이 몇 배로 틀린다(1:5 분할이면 약 5배). 식 상태는 그대로 보이되 Tech 는 '돌파'로 세지 않는다.
      · 거래정지 없는 무상증자 · 분할은 알아챌 방법이 없다 — 이 한계를 탐지된 결과마다 경고로 적는다(VOL_RAW).
      · 식의 다른 거래량 구간(손잡이 거래량 비율 등)에 정지일이 끼면 경고만 단다(_halt_note).
  - 지수: 소속 시장 지수 종가(ctx.index_df — KOSPI 종목은 KOSPI, KOSDAQ 종목은 KOSDAQ). 없으면 빈 dict 를 넘겨
    식이 RS · 시장 항목을 'unknown' 으로 둔다(지어내지 않음).
  - 호가: krx.TICK_TABLE (krx_tick 과 같은 2023 구간) → 진입가 = 피벗 위 첫 호가(식의 next_entry).
  - 장중(ctx.partial): 식은 완성된 일봉만 받는다. 구조는 마지막 완성 봉(어제)까지로 찾고, 오늘 미완성 봉은 어제 READY 구조에
    대한 '잠정' 돌파 판정에만 쓴다(식의 classify_breakout). 오늘 거래량 = ctx.vol(하루치 환산 추정). 경고에 적는다.

판정 (식 함수 그대로)
  latest_scan(ctx, code, E, tick_table=TICK_TABLE, include_rejected=True), E = 마지막 완성 봉.
    → READY 스냅샷 + 어제 READY 구조에 대한 E 날 사건(돌파 시도 · 컵 바닥 이탈).
    include_rejected 는 탈락 구조로 '왜 아닌지'를 설명하는 데만 쓴다(유효 구조 집합은 같다 — 테스트로 확인).
  식은 우측 림을 넘은 봉(돌파 시도)이 생기면 다음 봉부터 그 구조를 내지 않는다 — 거래량 · 종가 확인이 없었어도 끝이다.
  Tech 의 '돌파 뒤 5봉' 단계를 위해 최근 5봉 안의 지난 사건을 같은 식 함수로 다시 잰다: d−1 날 detect_candidates →
  d 날 classify_breakout. d 날 고가가 그때까지 안 넘긴 확인된 우측 림보다 높을 때만 잰다 — 돌파 시도의 필요조건이라
  결과는 같고 빠르다. 이어 보이는 것은 식이 거래량 확인을 준 사건뿐이다(아래 표) — 나머지 지난 시도는 식처럼 탐지하지
  않고, 그 뒤 거래량 동반 종가 돌파가 있었으면 그 사실을 경고에 적는다(식이 그 구조로 다시 판정하지 않아 '돌파'로 세지 않음).

단계 대응 — 매수 범위 · 이격 과다는 식과 같게 진입가(피벗 위 첫 호가) 기준 진입가 × (1 + 식 buy_zone_max 5%).
근접 5% · 실패 −3% · 돌파 창 5봉은 Tech(base.classify_stage 기본값, 피벗 기준). '거래량 확인' = 식의 volume_confirmed
(RVOL ≥ 1.4) 이고 그 RVOL 비교 구간에 거래정지일이 없을 때.
  READY                               종가 ≥ 피벗 × 0.95 → 피벗 근접, 아니면 형성 중
  당일 BREAKOUT_CONFIRMED             거래량 확인이면 돌파. 정지일이 끼면 돌파로 세지 않음 — 아래 '확인 안 된 시도'처럼
  당일 EXTENDED                       이격 과다 (식: 종가 > 진입가 × 1.05 — 거래량과 무관). RVOL 통과 · 미달을 근거에 적는다
  당일 PRICE_BREAKOUT                 돌파 아님 — 거래량 미확인 } 종가로: > 진입가 × 1.05 이격 과다 · ≥ 피벗 × 0.95 피벗 근접 ·
  당일 VOLUME_CONFIRMED_CLOSE_FAILED  돌파 아님 — 종가 미달     } 그 아래 형성 중. '식은 다음 봉부터 이 구조를 판정하지 않음'
                                      경고 · metrics.attempt_consumed(장중 잠정이 아니면) — 실시간 감시에서 뺀다
  당일 INVALIDATED                    탐지 안 함 (컵 바닥 이탈 — 경고로 남김)
  1~4봉 전 BREAKOUT_CONFIRMED (거래량 확인)
                                      지금 종가로: < 피벗 × 0.97 돌파 실패 · > 진입가 × 1.05 이격 과다 · < 진입가 피벗 근접(재시험)
                                      · 그 외 돌파 (+ '식은 이 구조를 더 내지 않음 — Tech 5봉 창' 경고)
  1~4봉 전 EXTENDED (거래량 확인)     지금도 > 진입가 × 1.05 이면 이격 과다 (+ 같은 경고). 매수 범위로 돌아왔으면 탐지 안 함
  1~4봉 전 그 밖의 시도               탐지 안 함 — 식에서 이 시도로 구조가 끝났다는 경고 (+ 그 뒤 거래량 동반 종가 돌파 사실)
  구조가 여럿이면: 실패 아닌 사건(최근 먼저) → READY(식의 품질 점수순) → 돌파 실패. metrics.state 에 식의 원래 상태.
  탐지 안 한 사건의 설명(컵 바닥 이탈 · 끝난 시도)은 다른 구조가 대표로 뽑혀도 경고에 남긴다.

결과
  pivot = 식 pivot_price(우측 림 고점). stop = 없음 — 식에 손절 규칙이 없다(cup_low 는 '구조 무효' 기준일 뿐).
  그래서 Tech 매수 계획(권장 수량)은 나오지 않는다. score = 식 quality_score — 성공 확률이 아니고 관측된 항목만으로 계산
  (score_coverage 함께 표시). breakout_date = '돌파'로 센 BREAKOUT_CONFIRMED 사건일만.
  라벨 '컵 앤 핸들 (사용자 식)' — 지운 옛 탐지기(같은 '컵 앤 핸들' 라벨)와 리포트 · CSV 에서 구별되게.
"""
from __future__ import annotations

import bisect
import inspect
from datetime import date

import numpy as np

from .. import krx
from . import cwh_reference as ref
from .base import (BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult, StockContext, box,
                   classify_stage, hline, marker, register, segment)

NAME, LABEL = "cup_with_handle", "컵 앤 핸들 (사용자 식)"
RULE_VERSION = ref.RULE_VERSION
_DEF = {k: p.default for k, p in inspect.signature(classify_stage).parameters.items()
        if p.default is not inspect.Parameter.empty}
NEAR_PCT, FAIL_PCT, WINDOW = _DEF["near_pct"], _DEF["fail_pct"], _DEF["breakout_window"]   # 매수 범위는 식의 buy_zone_max

STATE_KO = {
    "READY": "구조 완성 · 피벗 대기",
    "BREAKOUT_CONFIRMED": "돌파 확인",
    "EXTENDED": "돌파 · 이격 과다",
    "PRICE_BREAKOUT": "가격만 돌파 (거래량 미확인)",
    "VOLUME_CONFIRMED_CLOSE_FAILED": "장중 돌파 · 종가 미달",
    "INVALIDATED": "컵 바닥 이탈 (구조 무효)",
    "REJECTED": "필수 규칙 탈락",
}
# 필수 규칙: 이름 → (한글, 값 형식)
RULE_KO = {
    "prior_advance": ("선행 상승", "pct"),
    "base_calendar_duration": ("베이스 기간(달력일)", "days"),
    "cup_sessions": ("컵 봉 수", "n"),
    "cup_depth": ("컵 깊이", "pct"),
    "handle_sessions": ("손잡이 봉 수", "n"),
    "handle_depth": ("손잡이 깊이 (컵보다 얕게)", "pct"),
    "handle_midpoint": ("손잡이 중간값 > 컵 중간값", "won"),
    "cup_floor_intact": ("손잡이 저가 > 컵 바닥", "won"),
    "recovery": ("우측 회복률", "f2"),
    "right_rim_overshoot": ("우측 림이 좌측 림을 넘은 폭", "pct"),
    "roundness": ("U자 정도(roundness)", "f2"),
    "not_prominent_W": ("뚜렷한 W(쌍바닥) 아님", "yn"),
    "zero_volume_fraction": ("최근 50봉 거래량 0 비율", "pct"),
    "median_turnover": ("최근 50봉 거래대금 중앙값", "won"),
}
OBS_KO = {
    "handle_volume_contracts": ("손잡이 거래량 감소 (손잡이 평균 / 직전 50봉 평균 < 1)", "f2"),
    "handle_volatility_contracts": ("손잡이 변동성 감소 (< 1)", "f2"),
    "handle_above50": ("손잡이가 50일선 위 (80% 이상)", "pct"),
    "no_upward_wedge": ("손잡이가 위로 쐐기 아님", "yn"),
    "RS_near_high": ("RS 선(종가 / 지수) 252봉 고점의 95% 안", "f2"),
    "market_SMA50_filter": ("지수가 50일선 위 · 50일선 상승", "yn"),
}
WARN_KO = {
    "base_stage:unknown; previous-base 20% alternative not implemented":
        "몇 번째 베이스인지 세지 않음 (식 미구현 — base_stage unknown)",
    "prior_start:window_low_fallback; verify chart":
        "선행 상승 시작점: 확인된 스윙 저점이 없어 구간 최저가로 잼 — 차트로 확인",
    "liquidity_window:partial": "거래대금 · 거래량 0 비율 계산 구간이 50봉 미만",
    "deep_profile:manually verify bear-market context": "깊은 컵 프로파일 — 약세장 맥락은 직접 확인",
}
NO_STOP = "손절 규칙 없음 — 식은 컵 바닥 이탈을 '구조 무효'로만 본다. Tech 매수 계획(권장 수량)은 내지 않음"
VOL_RAW = ("거래량은 미수정 원 거래량(Tech 캐시 — 가격만 수정주가). 식은 같은 기준으로 수정된 거래량을 전제한다 — "
           "거래정지 없는 무상증자 · 분할은 Tech 가 알아채지 못해, 최근 50봉 안에 있었다면 RVOL · 손잡이 거래량 비율이 틀릴 수 있음")
CONSUMED_NEXT = "식은 다음 봉부터 이 구조를 판정하지 않음(우측 림을 넘음) — 이 구조로는 '돌파 확인'이 다시 나오지 않는다"
CARRIED = "식은 사건 다음 봉부터 이 구조를 내지 않음 — Tech '돌파 뒤 5봉' 창으로 이어 보임"


# ---------------------------------------------------------------- 입력 변환
def to_bars(ctx: StockContext) -> tuple[list[ref.Bar], list[int]]:
    """(식의 Bar 목록, 되살린 거래정지 봉의 위치). 장중이면 마지막 봉 거래량은 ctx.vol(하루치 환산 추정)."""
    df = ctx.df
    if not len(df):
        return [], []
    days = [ts.date() for ts in df.index]
    o, h, lo, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    v = ctx.vol.to_numpy(dtype=float)
    bars = [ref.Bar(d, float(o[i]), float(h[i]), float(lo[i]), float(c[i]), float(v[i])) for i, d in enumerate(days)]
    have = set(days)
    add = []
    for s in sorted(set(df.attrs.get("halt_dates") or [])):
        try:
            d = date.fromisoformat(str(s)[:10])
        except ValueError:
            continue
        if d in have or d < days[0]:
            continue
        px = float(c[bisect.bisect_left(days, d) - 1])      # 직전 실제 봉 종가
        add.append(ref.Bar(d, px, px, px, px, 0.0))
    if not add:
        return bars, []
    bars = sorted(bars + add, key=lambda b: b.date)
    added = {b.date for b in add}
    return bars, [i for i, b in enumerate(bars) if b.date in added]


def benchmark(ctx: StockContext) -> dict[date, float]:
    """소속 시장 지수 종가 {날짜: 종가}. 지수가 없으면 빈 dict (식이 RS · 시장 항목을 unknown 으로 둔다)."""
    idx = ctx.index_df
    if idx is None or "close" not in idx or not len(idx):
        return {}
    out = {}
    for ts, x in idx["close"].items():
        x = float(x)
        if np.isfinite(x) and x > 0:
            out[ts.date()] = x
    return out


# ---------------------------------------------------------------- 표시 문자열
def _fmt(v, kind: str) -> str:
    if v is None:
        return "모름"
    if kind == "yn":
        return "예" if v else "아니오"
    if isinstance(v, (list, tuple)):
        return " ~ ".join(_fmt(x, kind) for x in v)
    if isinstance(v, dict):
        if "greater_than" in v:
            return "> " + _fmt(v["greater_than"], kind)
        if "maximum" in v:
            return "≤ " + _fmt(v["maximum"], kind) + (" · 컵 깊이보다 얕게" if v.get("less_than_cup_depth") else "")
        return str(v)
    if isinstance(v, str):
        return v
    x = float(v)
    if kind == "pct":
        return f"{x * 100:.1f}%"
    if kind == "won":
        return f"{x:,.0f}"
    if kind == "days":
        return f"{x:.0f}일"
    if kind == "n":
        return f"{x:.0f}"
    return f"{x:.2f}"


_GE = {"prior_advance", "cup_sessions", "recovery", "roundness", "median_turnover", "handle_above50", "RS_near_high"}
_LE = {"right_rim_overshoot", "zero_volume_fraction"}
_NOT = {"not_prominent_W", "no_upward_wedge"}       # 식의 value 가 '해당함'이라 뒤집어 보인다 (기준: 아니오 → 예)


def _rule_line(r: dict, table: dict) -> str:
    """식의 규칙 행 → '✔ 컵 깊이 21.0% (기준 12.0% ~ 33.0%) [cup_depth]'."""
    name = r["name"]
    label, kind = table.get(name, (name, "f2"))
    mark = {"pass": "✔", "fail": "✘"}.get(r["status"], "?")
    thr, val = r.get("threshold"), r.get("value")
    if name in _NOT:
        val, thr_s = (None if val is None else not val), "예"
    elif name in _GE:
        thr_s = "≥ " + _fmt(thr, kind)
    elif name in _LE:
        thr_s = "≤ " + _fmt(thr, kind)
    elif isinstance(thr, str):
        thr_s = thr
    elif isinstance(thr, bool):
        thr_s = _fmt(thr, "yn")
    else:
        thr_s = _fmt(thr, kind)
    status = " — 모름(자료 없음)" if r["status"] == "unknown" else ""
    return f"{mark} {label} {_fmt(val, kind)} (기준 {thr_s}){status} [{name}]"


# ---------------------------------------------------------------- 단계
def _unconfirmed_stage(close: float, pivot: float, entry: float, zone: float) -> str:
    """당일 확인 안 된 시도의 종가 자리. 이격 과다 = 식의 매수 범위(진입가 × (1 + zone)) 위, 근접 = 피벗 −5% 안."""
    if close > entry * (1 + zone):
        return EXTENDED
    if close >= pivot * (1 - NEAR_PCT):
        return NEAR_PIVOT
    return FORMING


def _rvol_text(p: dict, cfg: ref.Config) -> str:
    rv = p.get("breakout_rvol")
    if rv is None:
        return f"RVOL 모름(직전 {cfg.breakout_volume_sessions}봉 부족)"
    if p.get("volume_confirmed"):
        return f"RVOL {rv:.2f} ≥ {cfg.breakout_rvol_min:.2f} 통과"
    return f"RVOL {rv:.2f} < {cfg.breakout_rvol_min:.2f} 미달"


def _halt_text(halted: list[str], cfg: ref.Config) -> str:
    more = f" 등 {len(halted)}일" if len(halted) > 3 else ""
    return (f"이 RVOL 의 비교 구간(직전 {cfg.breakout_volume_sessions}봉)에 거래정지 {', '.join(halted[:3])}{more} — "
            "분할 · 병합이면 미수정 거래량이라 RVOL 이 몇 배로 틀릴 수 있어 거래량 확인으로 세지 않음")


def vol_ok(p: dict, halted: list[str] | None) -> bool:
    """Tech 가 믿는 거래량 확인: 식의 volume_confirmed 이고 그 RVOL 비교 구간에 거래정지일이 없다."""
    return bool(p.get("volume_confirmed")) and not halted


def assess(p: dict, k_ago: int | None, close: float, cfg: ref.Config | None = None, *,
           halted: list[str] | None = None, later: tuple | None = None) -> tuple[str | None, list[str], list[str]]:
    """(Tech 단계 | None=탐지 안 함, 근거, 경고). p = 식 결과 행, k_ago = 사건이 몇 봉 전인지(READY 면 None).
    halted = 사건일 RVOL 비교 구간(직전 50봉)의 거래정지일. later = 사건 뒤 '종가 ≥ 진입가 · RVOL ≥ 기준'인 첫 봉
    (날짜, 종가, RVOL, 장중 잠정, 그 RVOL 구간에 거래정지) | None — 탐지 안 하는 지난 시도의 설명에만 쓴다."""
    cfg = cfg or ref.Config()
    pivot = float(p["pivot_price"])
    if k_ago is None:                                       # READY 스냅샷
        return (NEAR_PIVOT if close >= pivot * (1 - NEAR_PCT) else FORMING), [], []
    st, entry, zone = p["state"], float(p["entry_price"]), cfg.buy_zone_max
    halted = halted or []
    rv_s = _rvol_text(p, cfg)
    ok = vol_ok(p, halted)
    hw = [_halt_text(halted, cfg)] if halted and p.get("volume_confirmed") else []
    ext = close / entry - 1
    if st == "INVALIDATED":
        same = " · 같은 봉에서 진입가도 넘어 순서 모름" if p.get("same_bar_order_unknown") else ""
        return None, [], [f"{p['event_date']} 컵 바닥 {p['cup_low']:,.0f} 이탈 — 피벗 {pivot:,.0f} 구조 무효(INVALIDATED){same}"]
    if k_ago == 0:
        if st == "BREAKOUT_CONFIRMED" and ok:
            return BREAKOUT, [f"오늘 돌파 확인 — {rv_s} · 종가 ≥ 진입가 {entry:,.0f} · 진입가 +{zone:.0%} 안"], []
        if p.get("provisional"):
            nxt = "장 마감 봉도 진입가를 넘으면 식은 다음 봉부터 이 구조를 판정하지 않음 — 이 구조로 '돌파 확인'이 다시 나오지 않는다"
        else:
            nxt = CONSUMED_NEXT
        if st == "BREAKOUT_CONFIRMED":                      # 식은 확인했지만 RVOL 구간에 거래정지
            return (_unconfirmed_stage(close, pivot, entry, zone),
                    [f"오늘 식은 돌파 확인(BREAKOUT_CONFIRMED, {rv_s}) — Tech 는 '돌파'로 세지 않음(아래 거래정지)"],
                    hw + [nxt])
        if st == "EXTENDED":
            return (EXTENDED, [f"오늘 진입가 {entry:,.0f} 를 넘었지만 종가가 진입가 +{zone:.0%} 초과 ({p['extension']:+.1%}) — "
                               f"식의 매수 범위 밖 · {rv_s}"], hw + [nxt])
        if st == "PRICE_BREAKOUT":
            note = f"오늘 가격만 진입가 {entry:,.0f} 를 넘음 — {rv_s} · 돌파 아님"
        else:
            note = f"오늘 장중 진입가 {entry:,.0f} 돌파 · {rv_s}, 종가 미달 — 돌파 아님"
        return _unconfirmed_stage(close, pivot, entry, zone), [note], hw + [nxt]
    when = f"{k_ago}봉 전({p['event_date']})"
    if st == "BREAKOUT_CONFIRMED" and ok:
        if close < pivot * (1 - FAIL_PCT):
            return FAILED, [f"{when} 돌파 확인 뒤 피벗 −{FAIL_PCT:.0%} 아래로 되밀림 — 돌파 실패"], [CARRIED]
        if ext > zone:
            return EXTENDED, [f"{when} 돌파 확인 · 지금 진입가 +{zone:.0%} 초과 ({ext:+.1%}) — 이격 과다"], [CARRIED]
        if close < entry:
            return NEAR_PIVOT, [f"{when} 돌파 확인 뒤 진입가 {entry:,.0f} 아래 재시험"], [CARRIED]
        return BREAKOUT, [f"{when} 돌파 확인 ({rv_s}) — 지금 매수 범위(진입가 +{zone:.0%}) 안 ({ext:+.1%})"], [CARRIED]
    if st == "EXTENDED" and ok and ext > zone:
        return EXTENDED, [f"{when} 거래량 동반 돌파였지만 그날 종가가 진입가 +{zone:.0%} 초과(식 EXTENDED, {rv_s}) · "
                          f"지금도 {ext:+.1%} — 이격 과다"], [CARRIED]
    # 그 밖의 지난 시도: 식에서는 이 시도로 구조가 끝났다 → 식처럼 탐지하지 않는다
    msg = (f"{when} 돌파 시도({STATE_KO.get(st, st)}, {rv_s}) — 식에서는 이 시도로 피벗 {pivot:,.0f} 구조가 끝남"
           "(우측 림을 넘음) · 탐지 안 함")
    if halted and p.get("volume_confirmed"):
        msg += " · " + _halt_text(halted, cfg)
    if st == "EXTENDED" and ok:
        msg += f" · 지금 종가는 진입가 대비 {ext:+.1%}(진입가 +{zone:.0%} 이하) — 식은 이 구조로 매수 범위를 다시 판정하지 않음"
    if later:
        d, c, rv, prov, lh = later
        msg += (f" · 그 뒤 {d} 종가 {c:,.0f} ≥ 진입가 {entry:,.0f} · RVOL {rv:.2f} ≥ {cfg.breakout_rvol_min:.2f}"
                + (" (장중 잠정)" if prov else "") + (" (그 RVOL 구간에도 거래정지 — 왜곡 가능)" if lh else "")
                + " — 거래량 동반 종가 돌파는 있었지만 식이 이 구조로 판정하지 않아 '돌파 확인'으로 세지 않음")
    return None, [], [msg]


# ---------------------------------------------------------------- 사건 찾기
def _may_cross(c: ref.Context, d: int) -> bool:
    """d 날 돌파 시도가 있을 수 있나 — d−1 날 구조의 우측 림(확인 · 이후 미돌파) 중 d 날 고가보다 낮은 것이 있나."""
    cfg = c.cfg
    end = d - 1
    lo = max(0, end - cfg.handle_max_sessions - cfg.handle_start_grace)
    hd = c.bars[d].high
    for r in c.right_peaks:
        if r < lo or r + cfg.right_peak_span > end:
            continue
        top = c.bars[r].high
        if hd > top and all(b.high <= top for b in c.bars[r + 1:d]):
            return True
    return False


def _events_on(c: ref.Context, code: str, d: int, ticks) -> list[dict]:
    """d 날 사건(d−1 날 READY 구조 기준, 식의 latest_scan 과 같은 방식). 돌파 시도만."""
    out = []
    for p in ref.detect_candidates(c, code, d - 1):
        ev = ref.classify_breakout(c, p, d, tick_table=ticks)
        if ev["price_crossed"]:
            q = dict(p)
            q.update(ev)
            q["structure_as_of"] = p["as_of"]
            q["as_of"] = str(c.bars[d].date)
            out.append(q)
    return out


def _classify_today(c: ref.Context, ready: list[dict], d: int, ticks) -> list[dict]:
    out = []
    for p in ready:
        ev = ref.classify_breakout(c, p, d, tick_table=ticks)
        if ev["price_crossed"] or ev["cup_floor_broken"]:
            q = dict(p)
            q.update(ev)
            q["structure_as_of"] = p["as_of"]
            q["as_of"] = str(c.bars[d].date)
            q["provisional"] = True
            out.append(q)
    return out


def _halts_before(bars: list[ref.Bar], halts: list[int], d: int, n: int) -> list[str]:
    """d 봉의 RVOL 비교 구간(식: 당일 뺀 직전 n봉)에 든 거래정지일."""
    return [str(bars[i].date) for i in halts if d - n <= i < d]


def _later_confirm(c: ref.Context, d: int, last: int, entry: float, halts: list[int], partial: bool) -> tuple | None:
    """사건(d) 다음 봉부터 지금까지 '종가 ≥ 진입가 · RVOL ≥ 기준'인 첫 봉 — RVOL 은 식의 창(당일 뺀 직전 N봉 평균) 그대로.
    (날짜, 종가, RVOL, 장중 잠정, 그 RVOL 구간에 거래정지) | None."""
    cfg, bars = c.cfg, c.bars
    n = cfg.breakout_volume_sessions
    for j in range(d + 1, last + 1):
        b = bars[j]
        if b.close < entry:
            continue
        prev = [x.volume for x in bars[max(0, j - n):j]]
        rv = ref.ratio(b.volume, ref.mean(prev) if len(prev) == n else None)
        if rv is not None and rv >= cfg.breakout_rvol_min:
            return str(b.date), b.close, rv, partial and j == last, any(j - n <= i < j for i in halts)
    return None


# ---------------------------------------------------------------- 결과 만들기
def _metrics(p: dict, k_ago: int | None, bench_name: str | None, partial: bool) -> dict:
    keys = ("state", "pattern_id", "profile", "pivot_price", "entry_price", "distance_to_entry", "cup_high", "cup_low",
            "cup_midpoint", "cup_depth", "handle_high", "handle_low", "handle_depth", "handle_sessions", "cup_sessions",
            "base_calendar_days", "base_weeks", "base_sessions", "left_peak_date", "bottom_date", "right_peak_date",
            "handle_start_date", "prior_start_date", "prior_advance", "recovery_ratio", "rim_gap", "roundness_score",
            "prominent_double_bottom", "bottom_occupancy", "handle_volume_ratio", "handle_volatility_ratio",
            "handle_above50_fraction", "upward_wedge_risk", "right_up_down_volume_sum_ratio", "zero_volume_fraction50",
            "median_turnover50", "rs_high_ratio", "market_up_filter", "quality_score", "score_coverage",
            "event_date", "structure_as_of", "breakout_rvol", "breakout_volume_status", "extension", "close_location",
            "entry_policy")
    m = {k: p.get(k) for k in keys if k in p}
    m["rule_version"] = RULE_VERSION
    m["bars_since_event"] = k_ago
    m["benchmark"] = bench_name
    m["provisional"] = bool(p.get("provisional")) and partial
    m["rejection_reasons"] = list(p.get("rejection_reasons") or [])
    return m


def _halt_note(bars: list[ref.Bar], halts: list[int], p: dict, cfg: ref.Config, last: int) -> str | None:
    if not halts:
        return None
    idx = p["_indices"]
    start = min(idx["left"], max(0, idx["handle"] - cfg.handle_volume_pre_sessions),
                max(0, idx["end"] - 49), max(0, last - cfg.breakout_volume_sessions))
    inside = [str(bars[i].date) for i in halts if start <= i <= last]
    if not inside:
        return None
    more = f" 등 {len(inside)}일" if len(inside) > 3 else ""
    return (f"식의 거래량 비교 구간(손잡이 거래량 비율 · 최근 50봉 · 돌파 RVOL)에 거래정지 {', '.join(inside[:3])}{more} — "
            "분할 · 병합 · 합병 등 주식 수가 바뀐 정지면 미수정 거래량이라 거래량 비교가 틀릴 수 있음")


def _annotations(bars: list[ref.Bar], p: dict, counted: bool = False) -> list[dict]:
    idx = p["_indices"]
    left, bottom, right = bars[idx["left"]], bars[idx["bottom"]], bars[idx["right"]]
    end = bars[idx["end"]]
    ann = [
        segment([(left.date, left.high), (bottom.date, bottom.low), (right.date, right.high)], "컵", "#ff6d00"),
        box(bars[idx["handle"]].date, end.date, p["handle_high"], p["handle_low"], "손잡이", "#7e57c2"),
        hline(p["pivot_price"], "피벗 (우측 림 고점)", "#2962ff"),
        hline(p["cup_low"], "컵 바닥 (구조 무효)", "#9e9e9e", "dotted"),
        hline(p["cup_midpoint"], "컵 중간값", "#bdbdbd", "dotted"),
    ]
    if p.get("event_date"):
        txt = "돌파" if counted else ("진입가 넘음 · 이격" if p["state"] == "EXTENDED" else "돌파 시도")
        ann.append(marker(p["event_date"], txt + (" (잠정)" if p.get("provisional") else ""), "below", "#e91e63",
                          "arrowUp"))
    return ann


def _why_not(rejected: list[dict], limit: int = 2) -> list[str]:
    out = []
    best = sorted(rejected, key=lambda p: (len(p["rejection_reasons"]), -p["quality_score"]))[:limit]
    for p in best:
        fails = [r for r in p["required_rules"] if r["status"] != "pass"]
        out.append(f"가장 가까운 구조 (좌측 림 {p['left_peak_date']} · 우측 림 {p['right_peak_date']} · 피벗 "
                   f"{p['pivot_price']:,.0f}) — 탈락 {len(fails)}개: "
                   + " · ".join(_rule_line(r, RULE_KO)[2:] for r in fails))
    return out


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, ref.Config)
    res = PatternResult(name=NAME, label=LABEL)
    res.metrics["rule_version"] = RULE_VERSION
    bars, halts = to_bars(ctx)
    last = len(bars) - 1
    partial = bool(ctx.partial) and last >= 0 and bars[last].date == ctx.df.index[-1].date() and bars[last].volume > 0
    E = last - 1 if partial else last                       # 마지막 완성 봉
    if E < cfg.cup_min_sessions:
        res.warnings.append(f"이력 부족 ({E + 1}봉)")
        return res
    bench = benchmark(ctx)
    try:
        c = ref.Context(bars, cfg, bench)
    except ValueError as e:     # 식의 validate_bars — 종목 오류로 남긴다(run_all → 스캔 오류 수)
        raise ValueError(f"식 입력 자료 오류(validate_bars): {e}") from e
    ticks = krx.TICK_TABLE
    snaps = ref.latest_scan(c, ctx.code, E, tick_table=ticks, include_rejected=True)
    events = [(last - E, p) for p in snaps if "structure_as_of" in p]
    ready = [p for p in snaps if "structure_as_of" not in p and p["structure_valid"]]
    rejected = [p for p in snaps if "structure_as_of" not in p and not p["structure_valid"]]
    if partial:
        today = _classify_today(c, ready, last, ticks)
        gone = {p["pattern_id"] for p in today}             # 오늘 넘었거나 바닥을 깬 구조는 READY 에서 뺀다
        ready = [p for p in ready if p["pattern_id"] not in gone]
        events += [(0, p) for p in today]
    for d in range(E - 1, max(0, last - WINDOW + 1) - 1, -1):
        if d >= 1 and _may_cross(c, d):
            events += [(last - d, p) for p in _events_on(c, ctx.code, d, ticks)]
    close = float(ctx.close.iloc[-1])
    bench_name = ctx.market if bench else None

    picks, notes_out = [], []
    for k, p in events:
        d = last - k
        halted = _halts_before(bars, halts, d, cfg.breakout_volume_sessions)
        later = _later_confirm(c, d, last, float(p["entry_price"]), halts, partial) if k else None
        stage, notes, warns = assess(p, k, close, cfg, halted=halted, later=later)
        if stage is None:
            notes_out += warns
        else:
            picks.append((0 if stage != FAILED else 2, k, -p["quality_score"], stage, notes, warns, halted, p))
    for p in ready:
        stage, notes, warns = assess(p, None, close, cfg)
        picks.append((1, 0, -p["quality_score"], stage, notes, warns, [], p))
    picks.sort(key=lambda t: t[:3])
    res.metrics.update(n_ready=len(ready), n_events=len(events), n_rejected=len(rejected))

    if not picks:
        res.warnings += notes_out
        res.warnings += _why_not(rejected)
        if not notes_out and not rejected:
            res.warnings.append(f"평가할 구조 없음 — 최근 {cfg.handle_max_sessions + cfg.handle_start_grace}봉 안에 확인된 "
                                "우측 림과 짝이 되는 좌측 림이 없다")
        if partial:
            res.warnings.append("장중 스캔 — 구조는 어제까지 완성 봉으로 찾음")
        return res

    _, k, _, stage, notes, warns, halted, p = picks[0]
    k_ago = None if "structure_as_of" not in p else k
    counted = p["state"] == "BREAKOUT_CONFIRMED" and vol_ok(p, halted)     # Tech 가 '돌파'로 센 사건
    res.detected = True
    res.stage = stage
    res.score = float(p["quality_score"])
    res.pivot = float(p["pivot_price"])
    res.stop = None
    res.start_date = p["left_peak_date"]
    res.end_date = p.get("structure_as_of") or p["as_of"]
    res.breakout_date = p["event_date"] if counted else None
    res.metrics.update(_metrics(p, k_ago, bench_name, partial))
    if k_ago is not None:
        res.metrics["volume_unverified"] = bool(halted) and bool(p.get("volume_confirmed"))
        # 식에서 이 시도로 구조가 끝났고 Tech 도 이어 보지 않는다 — 다음 봉부터 이 구조로 '돌파 확인'은 없다(실시간 감시 제외)
        res.metrics["attempt_consumed"] = k_ago == 0 and not res.metrics["provisional"] and not counted
    res.reasons.append(f"사용자 식 {RULE_VERSION} (받은 파일 그대로 — 지운 옛 '컵 앤 핸들' 탐지기와 다른 식)")
    res.reasons.append(f"식 상태: {STATE_KO.get(p['state'], p['state'])} ({p['state']}) · {p['profile']} 프로파일")
    res.reasons.append(f"피벗(우측 림 고점) {res.pivot:,.0f} · 진입가(피벗 위 첫 호가) {p['entry_price']:,.0f}")
    res.reasons.append(f"컵 깊이 {p['cup_depth']:.1%} · 베이스 {p['base_weeks']:.1f}주({p['base_calendar_days']}일) · "
                       f"손잡이 {p['handle_sessions']}봉 깊이 {p['handle_depth']:.1%}")
    res.reasons.append(f"품질 점수 {p['quality_score']:.1f} (관측 비중 {p['score_coverage']:.0%}) — 성공 확률 아님 · "
                       "관측 못 한 항목은 빼고 셈")
    res.reasons += notes
    res.warnings += warns
    res.reasons += [_rule_line(r, RULE_KO) for r in p["required_rules"]]
    for r in p["quality_observations"]:
        (res.reasons if r["status"] == "pass" else res.warnings).append("관찰 " + _rule_line(r, OBS_KO))
    for w in p.get("warnings") or []:
        if ":" in w and w.split(":")[0] in OBS_KO:
            continue                                        # 관찰 항목은 위에서 한글로
        res.warnings.append(WARN_KO.get(w, w))
    res.warnings.append(NO_STOP + f" (컵 바닥 {p['cup_low']:,.0f})")
    hn = _halt_note(bars, halts, p, cfg, last)
    if hn:
        res.warnings.append(hn)
    res.warnings.append(VOL_RAW)
    res.warnings += notes_out                               # 탐지 안 한 다른 구조의 사건(컵 바닥 이탈 · 끝난 시도)
    if partial:
        res.warnings.append("장중 잠정 — 오늘 봉은 미완성(거래량은 하루치 환산 추정). 식은 완성된 일봉 기준이라 마감 뒤 다시 볼 것"
                            if p.get("provisional") else "장중 스캔 — 구조는 어제까지 완성 봉으로 찾음")
    if not bench:
        res.warnings.append("지수 자료 없음 — RS · 시장 항목은 모름(unknown)으로 두고 점수에서 뺌")
    others = len(picks) - 1
    if others:
        res.warnings.append(f"같은 종목의 다른 구조 {others}개 (식의 결과 — 대표 하나만 표시)")
    res.annotations = _annotations(bars, p, counted)
    return res
