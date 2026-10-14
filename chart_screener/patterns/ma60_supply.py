"""60일선 수급 돌파 (ma60_supply) — 《차트의 기술》 영상 [57:00–01:00:00]: 종가가 60일선(수급선)을 아래에서 위로 돌파하고
기관 · 외국인의 실질적인 매수가 따라오는지 본다.

스펙 docs/2026-10-14-chart-techniques-design.md §6 · 부록 docs/2026-10-14-chart-techniques-addendum.md §7 (부록 우선).
공용 부품은 chart_screener/techniques.py (tq). 규칙 id 'ma60s_v1' → 일지 rule 칸 (metrics.rule_version, journal.rule_of).

규칙 (출처는 metrics.origin — '영상 [mm:ss]' · URL · '구현 선택: 이유')
  자료      일봉 EOD 완성 봉만(tq.eod_frame — 장중 미완성 봉 제외). 봉 t 판정은 [0..t] 만(evaluate 가 b.cut(t)).
  60일선    종가 SMA60, 오늘 포함. 이력 61봉 미만이면 판정 안 함(전일 60일선이 있어야 돌파를 잰다).
  돌파      C[k−1] ≤ SMA60[k−1] 이고 C[k] > SMA60[k] (키움 돌파 정의 · tq.cross_above — 전일 같음은 돌파, 당일 같음은 아님).
            거래량 0 봉(정지 채움 행)의 돌파는 세지 않는다(구현 선택).
  탐지      최근 5봉(Tech 돌파 창) 안에 돌파 봉 k 가 있음 — 가장 최근 k 가 신호.
  수급      신호 봉 k 까지 5거래일(봉 k−4..k 의 날짜)의 기관 + 외국인 순매수. ctx.info['kis_flows'](증권사 체결 금액, 억원 → 원)
            우선, 그 5일을 다 덮지 못하면 ctx.info['investor'](순매매 수량, 주). 봉 날짜로만 찾으므로 봉 k 뒤 행은 읽지 않는다.
            f_d = 기관_d + 외국인_d, s5 = 5일 합.
              '수급 동반' f_k > 0 이고 s5 > 0 (스펙) · '수급 역행' s5 < 0 · '수급 약함' 나머지(구현 선택) ·
              '수급 미확인' 5일 중 하루라도 자료 없음(지어내지 않음) · 꼬리표 '쌍끌이' 기관 5일 합 > 0 이고 외국인 5일 합 > 0.
  함께 보임 20일선(생명선) · 120일선(경기선) 위 여부(신호 봉과 오늘). 표시만: 60일선 5봉 기울기, 돌파 전 60일선 아래 머문 봉 수,
            최근 60봉 돌파 횟수(3회 이상이면 '잦은 돌파' 경고).

단계 (base.classify_stage 기본값과 같은 문턱 · 피벗 = 오늘 60일선 — 60일선이 날마다 움직여 classify_stage 를 직접 못 쓴다)
  돌파 창 5봉 안에 돌파가 있을 때만 탐지. 오늘 종가 c · 오늘 60일선 p:
    c < p × 0.97 돌파 실패 · c > p × 1.05 이격 과다 · c ≤ p 피벗 근접(돌파 뒤 60일선 재시험) · 그 밖 돌파.
  돌파 전 '60일선 접근'은 탐지하지 않는다 — 스펙 · 부록에 없는 단계(비탐지 사유에 거리만 적는다).
손절 — 없음. 영상의 이 기법 부분은 손절을 말하지 않는다(그래서 Tech 매수 계획 · 권장 수량은 안 나온다).
  청산 계획(5일선 종가 이탈 · 10일선 위반, tq.exit_plan)은 metrics.exit_plan 에 표시만.
점수 (구현 선택 — 성공 확률 아님) 돌파 40 + 수급 동반 30 · 약함 10 · 미확인 0 · 역행 −10 + 쌍끌이 5 + 신호 봉 20일선 위 10 +
  120일선 위 15 (0~100 으로 자름). 모르는 항목(수급 미확인 · 120일선 이력 부족)은 0점 — score_unknown · score_coverage 에 적는다.
체크리스트 10(tq.run_checklist, 진입 = 마지막 완성 봉 종가 · 손절 없음 → 8번 모름)과 청산 계획을 탐지된 결과의 metrics 에 붙인다.
  4번 재현 = 이 종목 과거 60일선 종가 돌파 → 20거래일 뒤 종가(수급 이력이 없어 가격 돌파만 — 구현 선택).
장중(ctx.partial) — 판정은 어제까지 완성 봉. 오늘 미완성 봉이 60일선을 넘었으면 '장중 잠정' 경고와 metrics.provisional_cross 만.
"""
from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from .. import techniques as tq
from .base import (BREAKOUT, EXTENDED, FAILED, NEAR_PIVOT, STAGE_LABELS, PatternResult, StockContext, classify_stage,
                   marker, register, segment)

NAME = "ma60_supply"
LABEL = tq.PATTERN_LABELS[NAME]          # '60일선 수급 돌파'
RULE_ID = tq.RULE_IDS[NAME]              # 'ma60s_v1'
_DEF = {k: p.default for k, p in inspect.signature(classify_stage).parameters.items()
        if p.default is not inspect.Parameter.empty}

DONGBAN, YAKHAM, YEOKHAENG, MIHWAKIN = "수급 동반", "수급 약함", "수급 역행", "수급 미확인"
SSANG = "쌍끌이"
FLOW_PTS = {DONGBAN: 30, YAKHAM: 10, MIHWAKIN: 0, YEOKHAENG: -10}     # 구현 선택
PTS_CROSS, PTS_SSANG, PTS_MA20, PTS_MA120 = 40, 5, 10, 15


@dataclass
class MA60Config:
    n: int = 60                                  # MA60_N — 60일선(수급선)
    flow_days: int = 5                           # MA60_FLOW_DAYS (구현 선택)
    window: int = _DEF["breakout_window"]        # 돌파 창 5봉 (Tech)
    buy_range: float = _DEF["buy_range"]         # 이격 과다 = 60일선 +5% 초과
    fail_pct: float = _DEF["fail_pct"]           # 돌파 실패 = 60일선 −3% 미만
    slope_bars: int = 5                          # 60일선 기울기 (표시만)
    whipsaw_bars: int = 60                       # 잦은 돌파 세는 창 (표시만)
    whipsaw_warn: int = 3
    replay_horizon: int = 20                     # 체크리스트 4 — 20거래일 뒤
    ann_bars: int = 120                          # 차트에 그릴 이평 구간
    lookback_why: int = 250                      # 비탐지 설명용 마지막 돌파 찾기


_V = tq.video("57:00–01:00:00")
ORIGIN = {
    "cross": f"{_V} 종가 60일선 상향 돌파 (스펙 §6) · {tq.ORIGIN['cross']}",
    "ma60": "60일선 = 수급선 — 한국경제 생글생글 2005 (https://sgsg.hankyung.com/article/2005102520411) · " + tq.ORIGIN["sma"],
    "ma_names": tq.ORIGIN["ma_names"],
    "with_ma": "함께 보임: 20일선(생명선) · 120일선(경기선) 위 여부 (스펙 §6 · 부록 §7)",
    "flow": (tq.video("58:00") + " '기관과 외국인의 실질적인 매수' — 당일 · 5일 기관+외국인 순매수 > 0 = '수급 동반' "
             "(스펙 §6 · 부록 §7)"),
    "flow_days": tq.choice("MA60_FLOW_DAYS 5 = 1주(5거래일) — 영상 요약 · 한국 뉴스 · 위키독스 · 키움 도움말 어디에도 일수 기준 없음 "
                           "(부록 §7)"),
    "flow_source": ("순매수 금액(원) 우선, 없으면 수량(주) — 부록 §7 · 판정 봉 날짜까지의 행만 (투자자별 매매는 장 마감 뒤 확정, "
                    "기관은 약 18시 — chart_screener/data/investor.py)"),
    "flow_unknown": "5일 중 하루라도 자료 없으면 '수급 미확인' — 지어내지 않음 (스펙 §6 · 부록 §7 · 부록 §13)",
    "flow_weak": tq.choice("'수급 약함' = 동반 · 역행이 아닌 나머지 (부록 §7)"),
    "flow_ssang": "'쌍끌이' 꼬리표 = 기관 5일 합 > 0 이고 외국인 5일 합 > 0 (부록 §7)",
    "logic": ("영상 논리(tilnote 요약, 부록 §7): 바닥권의 단기 골든크로스는 반등에 그치기 쉽고, 진짜 추세 전환은 60일선 돌파에 "
              "기관 · 외국인 매수가 따라와야 한다"),
    "zero_vol": tq.choice("거래량 0 봉(정지 채움 행)의 돌파는 세지 않음 — 부록 §0.2 정지 행 처리와 같은 이유"),
    "stage": tq.choice("돌파 창 5봉 · 이격 과다 60일선 +5% · 실패 60일선 −3% · 피벗 = 오늘 60일선 — Tech base.classify_stage "
                       "기본값, 돌파 전 접근 단계는 두지 않음(스펙에 없음)"),
    "stop": ("손절 규칙 없음 — 영상의 60일선 수급 돌파 부분(스펙 §6)은 손절을 말하지 않음 · 청산 계획(5일선 종가 · 10일선 위반, "
             "부록 §9)은 표시만"),
    "score": tq.choice(f"점수 = 돌파 {PTS_CROSS} + 수급 동반 {FLOW_PTS[DONGBAN]} · 약함 {FLOW_PTS[YAKHAM]} · 미확인 0 · "
                       f"역행 {FLOW_PTS[YEOKHAENG]} + 쌍끌이 {PTS_SSANG} + 신호 봉 20일선 위 {PTS_MA20} + 120일선 위 {PTS_MA120} "
                       "(0~100) — 성공 확률 아님, 모르는 항목은 0점"),
    "display": tq.choice("60일선 5봉 기울기 · 돌파 전 60일선 아래 봉 수 · 최근 60봉 돌파 횟수(3회 이상 경고) — 표시만, 점수 안 씀"),
    "replay": tq.choice("체크리스트 4 재현 = 이 종목 과거 60일선 종가 돌파(수급 이력이 없어 가격만) → 신호 종가 대비 20거래일 뒤 종가"),
    "provisional": "장중 잠정 — 미완성 봉은 판정에 안 씀, 오늘 돌파 가능성만 따로 표시 (스펙 · 일봉 EOD 원칙)",
}
NO_STOP = "손절 규칙 없음 — 영상의 이 기법 부분은 손절을 말하지 않는다. Tech 매수 계획(권장 수량)은 내지 않음 · 청산 계획은 표시만"

# 리포트 표시용 한글 라벨 (template.html MLABEL 형식 [라벨, 형식]) — 리포트 연결 때 옮겨 쓴다
METRIC_LABELS = {
    "rule_version": ["규칙 id (일지 rule)", "t"], "asof": ["판정 봉", "t"], "close": ["종가", "won"], "ma60": ["60일선(수급선)", "won"],
    "dist_ma60": ["60일선 대비", "spct"], "cross_date": ["60일선 돌파일", "t"], "bars_since_cross": ["돌파 뒤 경과 (봉)", "n"],
    "cross_close": ["돌파일 종가", "won"], "cross_ma60": ["돌파일 60일선", "won"], "below_bars": ["돌파 전 60일선 이하 (봉)", "n"],
    "crosses_recent": ["최근 60봉 돌파 횟수", "n"], "ma60_slope": ["60일선 5봉 기울기", "spct"],
    "flow_label": ["수급 (신호일 5일)", "t"], "flow_ssang": ["쌍끌이 (기관 · 외국인 5일 합 모두 > 0)", "yn"],
    "flow_unit": ["수급 단위", "t"], "flow_src": ["수급 자료", "t"], "flow_missing": ["수급 자료 빠진 날", "list"],
    "flow_now_label": ["수급 (오늘까지 5일)", "t"], "ma20_above": ["신호일 20일선(생명선) 위", "yn"],
    "ma120_above": ["신호일 120일선(경기선) 위", "yn"], "ma20_above_now": ["오늘 20일선 위", "yn"],
    "ma120_above_now": ["오늘 120일선 위", "yn"], "score_coverage": ["점수 관측 비중", "pct"],
    "score_unknown": ["점수에서 모름 항목", "list"], "replay_n": ["재현 표본 (과거 돌파)", "n"],
    "provisional_cross": ["장중 잠정 돌파", "yn"],
    "rule_id": ["규칙 id", "t"], "core_version": ["공용 부품 판", "t"], "n_bars": ["완성 봉 수", "n"],
    "prev_close": ["돌파 전일 종가", "won"], "prev_ma60": ["돌파 전일 60일선", "won"],
    "ma20": ["20일선(생명선)", "won"], "ma120": ["120일선(경기선)", "won"], "flow_asof": ["수급 기준일 (신호 봉)", "t"],
    "flow_f_t": ["신호일 기관+외국인 순매수 (수급 단위)", "n"], "flow_s5": ["5일 기관+외국인 순매수 합 (수급 단위)", "n"],
    "flow_inst5": ["5일 기관 순매수 합 (수급 단위)", "n"], "flow_foreign5": ["5일 외국인 순매수 합 (수급 단위)", "n"],
    "flow_now": ["수급 (오늘까지 5일) 세부", "t"],
}


# ---------------------------------------------------------------- 작은 도우미
def _fl(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _le(a: float, b: float) -> bool:
    """a ≤ b — tq 비교 경계(상대 1e-9)와 같게."""
    return a <= b + tq.EPS * max(1.0, abs(b))


def _crosses(C, S, V, lo: int, hi: int) -> list[int]:
    """[lo, hi] 의 60일선 상향 돌파 봉 (거래량 0 봉 제외)."""
    return [k for k in range(max(1, lo), hi + 1) if V[k] > 0 and tq.cross_above(C, S, k)]


def _won(x) -> str:
    return "—" if x is None else f"{x:,.0f}"


def fmt_flow(x: float | None, unit: str | None) -> str:
    if x is None:
        return "—"
    return f"{x / 1e8:+,.1f}억원" if unit == "원" else f"{x:+,.0f}주"


# ---------------------------------------------------------------- 수급 표
def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v


def _norm_index(idx) -> pd.DatetimeIndex:
    di = pd.DatetimeIndex(idx)
    if di.tz is not None:
        di = di.tz_localize(None)
    return di.normalize()


def _table(inst, foreign, idx: pd.DatetimeIndex, unit: str, src: str) -> pd.DataFrame | None:
    df = pd.DataFrame({"inst": np.asarray(inst, float), "foreign": np.asarray(foreign, float)}, index=idx)
    df = df[~df.index.isna()]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if not len(df):
        return None
    df.attrs.update(unit=unit, src=src)
    return df


def flow_tables(info: dict | None) -> list[pd.DataFrame]:
    """ctx.info → 수급 표 목록(우선순위 순). 열 inst · foreign(기관 · 외국인 순매수), attrs unit '원' | '주' · src.

    1) kis_flows (data.kis_market.Flows 또는 같은 키의 dict) — orgn · frgn 체결 금액(억원 → 원)
    2) investor (data.investor 모양 DataFrame) — inst_net · foreign_net 순매매 수량(주)"""
    info = info or {}
    out: list[pd.DataFrame] = []
    fl = info.get("kis_flows")
    if fl is not None:
        dates, fr, og = _get(fl, "dates"), _get(fl, "frgn"), _get(fl, "orgn")
        if dates and fr is not None and og is not None and len(fr) == len(dates) == len(og):
            idx = _norm_index(pd.to_datetime([str(d) for d in dates], format="%Y%m%d", errors="coerce"))
            tb = _table([_num(x) * 1e8 for x in og], [_num(x) * 1e8 for x in fr], idx, "원", "증권사(KIS) 체결 금액")
            if tb is not None:
                out.append(tb)
    inv = info.get("investor")
    if isinstance(inv, pd.DataFrame) and len(inv) and {"inst_net", "foreign_net"} <= set(inv.columns):
        try:
            idx = _norm_index(inv.index)
        except (TypeError, ValueError):
            idx = None
        if idx is not None:
            src = "증권사(KIS) 순매매 수량" if fl is not None else "네이버 순매매 수량"
            tb = _table(pd.to_numeric(inv["inst_net"], errors="coerce").to_numpy(float),
                        pd.to_numeric(inv["foreign_net"], errors="coerce").to_numpy(float), idx, "주", src)
            if tb is not None:
                out.append(tb)
    return out


def flow_at(dates: pd.DatetimeIndex | None, i: int, tables: Sequence[pd.DataFrame], days: int = 5) -> dict:
    """봉 i 까지 days 거래일(봉 i−days+1..i 의 날짜) 수급 라벨. 표 하나가 그 날들을 모두 덮어야 쓴다(섞지 않음)."""
    out = {"label": MIHWAKIN, "ssang": False, "asof": None, "days": days, "unit": None, "src": None,
           "f_t": None, "s5": None, "inst5": None, "foreign5": None, "missing": [], "why": None}
    if dates is None or not 0 <= i < len(dates):
        out["why"] = "봉 날짜 없음"
        return out
    out["asof"] = f"{dates[i]:%Y-%m-%d}"
    if i - days + 1 < 0:
        out["why"] = f"이력 {i + 1}봉 — 수급 {days}일 창 부족"
        return out
    if not tables:
        out["why"] = "투자자 자료 없음 (ctx.info investor · kis_flows)"
        return out
    want = _norm_index(dates[i - days + 1:i + 1])
    best = None
    for tb in tables:
        sub = tb.reindex(want)
        inst, fo = sub["inst"].to_numpy(float), sub["foreign"].to_numpy(float)
        ok = np.isfinite(inst) & np.isfinite(fo)
        if ok.all():
            f = inst + fo
            ft, s5, i5, f5 = float(f[-1]), float(f.sum()), float(inst.sum()), float(fo.sum())
            label = DONGBAN if ft > 0 and s5 > 0 else YEOKHAENG if s5 < 0 else YAKHAM
            out.update(label=label, ssang=bool(i5 > 0 and f5 > 0), unit=tb.attrs.get("unit"), src=tb.attrs.get("src"),
                       f_t=ft, s5=s5, inst5=i5, foreign5=f5)
            return out
        miss = [f"{d:%Y-%m-%d}" for d, k in zip(want, ok) if not k]
        if best is None or len(miss) < len(best[0]):
            best = (miss, tb)
    miss, tb = best
    out.update(missing=miss, unit=tb.attrs.get("unit"), src=tb.attrs.get("src"),
               why=f"{days}일 중 {len(miss)}일 자료 없음: {', '.join(miss)}")
    return out


# ---------------------------------------------------------------- 판정 (봉 t, 미래 금지)
def _stage(c: float, p: float, cfg: MA60Config) -> str:
    if c < p * (1 - cfg.fail_pct):
        return FAILED
    if c > p * (1 + cfg.buy_range):
        return EXTENDED
    if c <= p:
        return NEAR_PIVOT            # 돌파 뒤 60일선 아래 재시험 (실패 기준 안)
    return BREAKOUT


def _score(flow: dict, ma_k: dict) -> tuple[float, dict, list, float]:
    parts = {"60일선 돌파": PTS_CROSS, "수급": FLOW_PTS[flow["label"]]}
    unknown, cover = [], PTS_CROSS
    if flow["label"] == MIHWAKIN:
        unknown.append("수급")
    else:
        cover += FLOW_PTS[DONGBAN] + PTS_SSANG
    if flow["ssang"]:
        parts[SSANG] = PTS_SSANG
    for n, key, pts in ((20, "20일선 위", PTS_MA20), (120, "120일선 위", PTS_MA120)):
        a = ma_k[n]["above"]
        if a is None:
            unknown.append(key.replace(" 위", ""))
        else:
            cover += pts
        parts[key] = pts if a else 0
    return float(min(100, max(0, sum(parts.values())))), parts, unknown, cover / 100


def _why_not(b: tq.Bars, C, S, V, t: int, cfg: MA60Config) -> str:
    c, p = float(C[t]), float(S[t])
    if _le(c, p):
        return f"종가가 60일선 이하 — 종가 {c:,.0f} · 60일선 {p:,.0f} ({c / p - 1:+.1%}) · 돌파 전"
    for k in range(t - cfg.window, max(cfg.n, t - cfg.lookback_why) - 1, -1):
        if V[k] > 0 and tq.cross_above(C, S, k):
            return (f"60일선 위({c / p - 1:+.1%}) — 마지막 돌파 {b.date(k) or k} ({t - k}봉 전) · 돌파 창 {cfg.window}봉 밖")
    return f"60일선 위({c / p - 1:+.1%}) — 최근 {cfg.lookback_why}봉 안 돌파 없음"


def evaluate(b: tq.Bars, t: int | None = None,
             tables: Sequence[pd.DataFrame] | Callable[[], Sequence[pd.DataFrame]] = (),
             cfg: MA60Config | None = None) -> dict:
    """봉 t 판정 — [0..t] 만 본다(앞부분 불변). 수급 표는 봉 날짜로만 찾으므로 t 뒤 행은 읽지 않는다.
    tables 는 flow_tables() 결과 또는 그것을 돌려주는 함수(돌파가 있을 때만 부른다 — 전 종목 스캔 비용)."""
    cfg = cfg or MA60Config()
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    b = b.cut(t)
    C, V = b.close, b.volume
    S = tq.sma(C, cfg.n)
    ev: dict = {"t": t, "date": b.date(t), "close": float(C[t]), "n_bars": t + 1, "ma60": _fl(S[t]), "dist": None,
                "detected": False, "stage": None, "cross_i": None, "why": None, "skipped_zero_vol": []}
    if t < cfg.n:
        ev["why"] = f"이력 부족 ({t + 1}봉 — 60일선 돌파 판정에 {cfg.n + 1}봉 필요)"
        return ev
    c, p = float(C[t]), float(S[t])
    ev["dist"] = c / p - 1
    lo = max(cfg.n, t - cfg.window + 1)
    ev["skipped_zero_vol"] = [b.date(k) or k for k in range(lo, t + 1)
                              if not V[k] > 0 and tq.cross_above(C, S, k)]
    ks = _crosses(C, S, V, lo, t)
    if not ks:
        ev["why"] = _why_not(b, C, S, V, t, cfg)
        return ev
    k = ks[-1]
    below = 0
    while k - 1 - below >= cfg.n - 1 and _le(float(C[k - 1 - below]), float(S[k - 1 - below])):
        below += 1
    tabs = tables() if callable(tables) else tables
    flow = flow_at(b.dates, k, tabs, cfg.flow_days)
    ma_k = tq.ma_snapshot(C, k, (20, 60, 120))
    score, parts, unknown, cover = _score(flow, ma_k)
    sb = cfg.slope_bars
    ev.update(
        detected=True, stage=_stage(c, p, cfg), cross_i=k, cross_date=b.date(k), bars_since=t - k,
        cross_close=float(C[k]), cross_ma60=float(S[k]), prev_close=float(C[k - 1]), prev_ma60=float(S[k - 1]),
        below_bars=below, start_i=k - below,
        crosses_recent=len(_crosses(C, S, V, max(cfg.n, k - cfg.whipsaw_bars + 1), k)),
        slope=_fl(S[t] / S[t - sb] - 1) if t - sb >= cfg.n - 1 else None,
        ma_signal=ma_k, ma_now=tq.ma_snapshot(C, t, (20, 60, 120)),
        flow=flow, flow_now=flow_at(b.dates, t, tabs, cfg.flow_days) if t != k else None,
        score=score, score_parts=parts, score_unknown=unknown, score_coverage=cover,
    )
    return ev


def replay(b: tq.Bars, t: int | None = None, cfg: MA60Config | None = None) -> list[dict]:
    """체크리스트 4 재현 — 봉 t 전에 20거래일이 지난 과거 60일선 돌파 [{date, ret20}] (신호 종가 → 20봉 뒤 종가, 가격만)."""
    cfg = cfg or MA60Config()
    t = b.n - 1 if t is None else (t + b.n if t < 0 else t)
    b = b.cut(t)
    C, V = b.close, b.volume
    S = tq.sma(C, cfg.n)
    h = cfg.replay_horizon
    return [{"date": b.date(j) or j, "ret20": float(C[j + h] / C[j] - 1)} for j in _crosses(C, S, V, cfg.n, t - h)]


# ---------------------------------------------------------------- 장중 잠정
def _provisional(ctx: StockContext, cfg: MA60Config) -> dict | None:
    """장중이면 오늘 미완성 봉(종가 = 현재가)이 60일선을 넘었는지 — 판정에는 안 쓴다."""
    df = ctx.df
    if not getattr(ctx, "partial", False) or len(df) < cfg.n + 2:
        return None
    C = df["close"].to_numpy(float)
    S = tq.sma(C, cfg.n)
    last = len(C) - 1
    return {"cross": bool(tq.cross_above(C, S, last)), "close": float(C[last]), "ma60": _fl(S[last]),
            "date": f"{df.index[last]:%Y-%m-%d}"}


# ---------------------------------------------------------------- 차트
def _annotations(b: tq.Bars, ev: dict, cfg: MA60Config) -> list[dict]:
    if b.dates is None:
        return []
    t, C = ev["t"], b.close
    i0 = max(0, t - cfg.ann_bars + 1)
    ann = []
    for n, lab, col in ((60, "60일선(수급선)", "#ff6d00"), (20, "20일선(생명선)", "#26a69a"), (120, "120일선(경기선)", "#7e57c2")):
        s = tq.sma(C[:t + 1], n)
        pts = [(b.dates[i], round(float(s[i]), 2)) for i in range(i0, t + 1) if math.isfinite(s[i])]   # 리포트 크기
        if len(pts) >= 2:
            ann.append(segment(pts, lab, col))
    k = ev["cross_i"]
    if k is not None:
        fl = ev["flow"]
        txt = "60일선 돌파 · " + fl["label"] + (f" · {SSANG}" if fl["ssang"] else "")
        ann.append(marker(b.dates[k], txt, "below", "#e91e63", "arrowUp"))
    return ann


# ---------------------------------------------------------------- 결과
def _ma_line(snap: dict, n: int, when: str, r: PatternResult) -> None:
    it = snap[n]
    if it["above"] is None:
        r.warnings.append(f"{when} {it['name']} 모름 — 이력 부족({n}봉 필요)")
    elif it["above"]:
        r.reasons.append(f"{when} {it['name']} 위 ({_won(it['value'])})")
    else:
        r.warnings.append(f"{when} {it['name']} 아래 ({_won(it['value'])})")


def _flow_line(fl: dict, when: str) -> str:
    if fl["label"] == MIHWAKIN:
        return f"{when} {MIHWAKIN} — {fl['why']} (지어내지 않음)"
    u = fl["unit"]
    return (f"{when} {fl['label']}" + (f" · {SSANG}" if fl["ssang"] else "")
            + f" — {fl['asof']}까지 {fl['days']}거래일 기관+외국인: 당일 {fmt_flow(fl['f_t'], u)} · {fl['days']}일 합 "
            f"{fmt_flow(fl['s5'], u)} (기관 {fmt_flow(fl['inst5'], u)} · 외국인 {fmt_flow(fl['foreign5'], u)}) · {fl['src']}")


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, MA60Config)
    r = PatternResult(name=NAME, label=LABEL)
    m = r.metrics
    m.update(rule_version=RULE_ID, rule_id=RULE_ID, core_version=tq.CORE_VERSION)
    info = ctx.info or {}
    b = tq.Bars.from_df(tq.eod_frame(ctx))
    prov = _provisional(ctx, cfg)
    m["provisional_cross"] = None if prov is None else prov["cross"]
    partial_notes = []
    if getattr(ctx, "partial", False):
        if prov and prov["cross"]:
            partial_notes.append(f"장중 잠정 — 오늘({prov['date']}) 미완성 봉 현재가 {prov['close']:,.0f} 이 60일선 "
                                 f"{_won(prov['ma60'])} 위(어제 ≤). 마감 뒤 확정 — 판정 · 단계 · 점수는 어제까지 완성 봉")
        else:
            partial_notes.append("장중 스캔 — 판정은 어제까지 완성 봉")
    if b.n == 0:
        r.warnings.append("완성 일봉 없음")
        r.warnings += partial_notes
        return r
    ev = evaluate(b, b.n - 1, lambda: flow_tables(info), cfg)
    m.update(asof=ev["date"], close=ev["close"], ma60=ev["ma60"], dist_ma60=ev["dist"], n_bars=ev["n_bars"])
    m["origin"] = dict(ORIGIN)
    if not ev["detected"]:
        r.warnings.append(ev["why"])
        if ev["skipped_zero_vol"]:
            r.warnings.append(f"거래량 0 봉의 돌파는 세지 않음: {', '.join(map(str, ev['skipped_zero_vol']))}")
        r.warnings += partial_notes
        return r

    t, k = ev["t"], ev["cross_i"]
    fl, fn = ev["flow"], ev["flow_now"]
    r.detected = True
    r.stage = ev["stage"]
    r.score = ev["score"]
    r.pivot = ev["ma60"]
    r.stop = None
    r.start_date = b.date(ev["start_i"])
    r.end_date = ev["date"]
    r.breakout_date = ev["cross_date"]
    sig, now = ev["ma_signal"], ev["ma_now"]
    rp = replay(b, t, cfg)
    m.update(
        cross_date=ev["cross_date"], bars_since_cross=ev["bars_since"], cross_close=ev["cross_close"],
        cross_ma60=ev["cross_ma60"], prev_close=ev["prev_close"], prev_ma60=ev["prev_ma60"], below_bars=ev["below_bars"],
        crosses_recent=ev["crosses_recent"], ma60_slope=ev["slope"],
        flow_label=fl["label"], flow_ssang=fl["ssang"], flow_unit=fl["unit"], flow_src=fl["src"], flow_asof=fl["asof"],
        flow_f_t=fl["f_t"], flow_s5=fl["s5"], flow_inst5=fl["inst5"], flow_foreign5=fl["foreign5"],
        flow_missing=fl["missing"], flow=fl,
        flow_now_label=fn["label"] if fn else None, flow_now=fn,
        ma20_above=sig[20]["above"], ma120_above=sig[120]["above"], ma20=sig[20]["value"], ma120=sig[120]["value"],
        ma20_above_now=now[20]["above"], ma120_above_now=now[120]["above"],
        score_parts=ev["score_parts"], score_unknown=ev["score_unknown"], score_coverage=ev["score_coverage"],
        replay=rp, replay_n=len(rp),
    )

    # 근거
    r.reasons.append(f"60일선(수급선) 종가 돌파 {ev['cross_date']}: 전일 종가 {ev['prev_close']:,.0f} ≤ 60일선 "
                     f"{ev['prev_ma60']:,.0f} → 당일 종가 {ev['cross_close']:,.0f} > {ev['cross_ma60']:,.0f} ({_V})")
    line = _flow_line(fl, "신호일 수급:") + f" ({tq.video('58:00')})"
    (r.reasons if fl["label"] == DONGBAN else r.warnings).append(line)
    _ma_line(sig, 20, "신호일", r)
    _ma_line(sig, 120, "신호일", r)
    if t != k:
        r.reasons.append(f"오늘 {ev['date']}: 종가 {ev['close']:,.0f} · 60일선 {ev['ma60']:,.0f} ({ev['dist']:+.1%}) · "
                         f"돌파 {t - k}봉 뒤 · {STAGE_LABELS[r.stage]}")
        r.reasons.append(_flow_line(fn, "오늘까지 수급(참고):"))
        for n in (20, 120):
            if now[n]["above"] is not None and now[n]["above"] != sig[n]["above"]:
                r.warnings.append(f"오늘 {now[n]['name']} {'위' if now[n]['above'] else '아래'} ({_won(now[n]['value'])}) — 신호일과 다름")
    if r.stage == EXTENDED:
        r.warnings.append(f"60일선 +{cfg.buy_range:.0%} 넘게 이격 ({ev['dist']:+.1%}) — 추격 매수 구간")
    elif r.stage == FAILED:
        r.warnings.append(f"돌파 뒤 60일선 −{cfg.fail_pct:.0%} 아래로 되밀림 ({ev['dist']:+.1%}) — 돌파 실패")
    elif r.stage == NEAR_PIVOT:
        r.warnings.append(f"돌파 뒤 60일선 아래 재시험 ({ev['dist']:+.1%}, 실패 기준 −{cfg.fail_pct:.0%} 안)")
    slope = f" · 60일선 {cfg.slope_bars}봉 기울기 {ev['slope']:+.2%}" if ev["slope"] is not None else ""
    r.reasons.append(f"돌파 전 종가가 60일선 이하로 {ev['below_bars']}봉{slope} (표시만)")
    if ev["crosses_recent"] >= cfg.whipsaw_warn:
        r.warnings.append(f"최근 {cfg.whipsaw_bars}봉 60일선 돌파 {ev['crosses_recent']}회 — 60일선 근처 횡보 · 잦은 돌파 (표시만)")
    parts = " + ".join(f"{k_} {v:+d}" for k_, v in ev["score_parts"].items())
    unk = f" · 모름 {', '.join(ev['score_unknown'])}(0점)" if ev["score_unknown"] else ""
    r.reasons.append(f"점수 {r.score:.0f} = {parts}{unk} — 구현 선택 가중치, 성공 확률 아님")
    r.warnings.append(NO_STOP)
    if ev["skipped_zero_vol"]:
        r.warnings.append(f"거래량 0 봉의 돌파는 세지 않음: {', '.join(map(str, ev['skipped_zero_vol']))}")
    r.warnings += partial_notes

    # 체크리스트 10 · 청산 계획 (표시만)
    items = tq.run_checklist(b, t, tq.inputs_from_ctx(ctx, entry=None, stop=None, replay=rp))
    cnt = tq.checklist_counts(items)
    m["checklist"] = [it.to_dict() for it in items]
    m["checklist_counts"] = {tq.STATUS_LABELS[s]: n for s, n in cnt.items()}
    r.reasons.append(f"체크리스트 10 (검증 전 · Bulkowski 항목을 우리 자료로 옮김): 통과 {cnt[tq.PASS]} · 경고 {cnt[tq.WARN]} · 모름 {cnt[tq.UNKNOWN]} "
                     f"(4번 재현 {len(rp)}건 — 수급 없이 가격 돌파만)")
    ep = tq.exit_plan(b, t, entry_i=k)
    m["exit_plan"] = ep
    r.reasons.append("청산 계획(표시만): " + " · ".join(
        [f"5일선 {_won(ep['ma5'])}", f"10일선 {_won(ep['ma10'])}", f"50일선 {_won(ep['ma50'])}"] + ep["notes"]))
    r.annotations = _annotations(b, ev, cfg)
    return r
