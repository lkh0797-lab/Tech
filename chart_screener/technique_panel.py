"""차트 발굴 기법 공통 칸 — 스캔이 후보마다 붙이는 체크리스트 10 · 청산 계획, 스캔마다 한 번 재는 시장 맥락 · 업종 RS,
저평가 등급 · 공시위험 배지. 모두 표시만 — 종합 점수(scoring)에 넣지 않는다.

스펙  docs/2026-10-14-chart-techniques-design.md '모든 후보 공통'
부록  docs/2026-10-14-chart-techniques-addendum.md §8 체크리스트 · §9 청산 계획 · §10 시장 맥락 (부록 우선)
공용  chart_screener/techniques.py (tq) — 판정 규칙과 출처(ORIGIN)는 모두 거기. 이 모듈은 자료를 모아 넘기기만 한다.

흐름 (scanner.run_scan)
  1. scan_inputs(ud, sector_map, strength, stock_groups, cfg) — 스캔마다 한 번:
       업종 RS 표(tq.industry_rs_table — 업종 = 네이버 업종 분류, 구성 종목 6개월 수익률 평균, 완성 봉 기준일까지) ·
       공시위험 파일(CHART_SCREENER_RISK_JSON — vocal.load_risk 와 같은 파일, 기업추적이 씀) · 업종 · 테마 강도(sector.py).
  2. fill_info(ctx, si) — 탐지 전에 ctx.info 에 'groups' · 'industry_rs' · 'sector_pos52' · 'risk' 를 넣는다 →
     패턴 모듈이 붙이는 체크리스트(tq.inputs_from_ctx)도 2 · 5 · 9 번을 채운다. 저평가 행('undervalued')은 스캐너가 넣는다.
  3. stock_panel(s) — 후보마다: 표시 대표(StockScan.display_lead)의 체크리스트 · 청산 계획.
     패턴이 metrics 에 이미 붙였으면 그것(그 기법의 진입가 · 손절 · 재현 — 빗각 · 피보 · 빗각+피보 · 60일선 · 10% 주도주),
     아니면 여기서 잰다(컵 앤 핸들 · 보컬 · 월봉 적삼병: 진입 = max(피벗, 종가) · 손절 = 그 결과 손절가 · 재현은 적삼병만).
  4. badges(ctx) — 저평가 등급(CHART_SCREENER_VALUE_JSON) · 공시위험 꼬리표 → 후보 줄 배지 (체크리스트 9 와 같은 자료).
  5. market_panel(ud) — 지수 KOSPI · KOSDAQ 맥락 칸 (tq.market_context + 지수 월봉 적삼병 judge_monthly).

미래 금지: 체크리스트 · 청산은 완성 봉(tq.eod_frame)까지, 업종 RS · 시장 맥락도 장중이면 오늘 미완성 봉을 뺀다.
업종 · 테마 강도(sector.group_strength — 스냅샷 그대로라 장중이면 오늘 봉이 섞임)는 장중엔 체크리스트 2번 판정에 쓰지 않는다
(tq._ck_sector — 연중 위치 중앙값만, 고점권이면 '모름'). 그 표는 점수 보너스 · 화면 표시용.
체크리스트는 '검증 전' — Bulkowski 체크리스트 항목을 우리 자료로 옮긴 판정이고 우리 데이터로 효과를 잰 적이 없다.
공시위험 파일은 그날 하루치(기업추적 스냅샷)라 과거 날짜 재현 · 백테스트에는 쓰지 않는다.
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import scoring
from . import techniques as tq
from .config import Config

CHECK_LABEL = "검증 전"
CHECK_NOTE = ("체크리스트 10 — 검증 전 · 표시만(종합 점수에 안 들어감). Bulkowski 체크리스트(https://thepatternsite.com/tradehelp.html) "
              "항목을 우리 자료로 옮긴 판정이며 우리 데이터로 효과를 잰 적이 없다. 4번 '이 종목 재현'만 우리 데이터 결과(확률 아님).")
EXIT_NOTE = "청산 계획 — 표시만(주문 · 알림 없음). 5일선 종가 이탈 1차 · 모랄레스 10일선 위반 2차 · 7주 규칙 (부록 §9)"
RISK_ENV = "CHART_SCREENER_RISK_JSON"
RED3_KEEP = ("detected", "state", "state_label", "stage", "rule_version", "last_month", "signal_month", "signal_date",
             "known_date", "low_month", "low", "pivot", "soldiers", "month_now", "after_signal", "why", "stage_note",
             "invalid_below", "bottom")


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------- 스캔마다 한 번
@dataclass
class ScanInputs:
    sector_map: pd.DataFrame | None = None
    strength: pd.DataFrame | None = None
    stock_groups: Callable | None = None
    sector_of: dict = field(default_factory=dict)          # {code: 업종}
    ind_rs: pd.DataFrame | None = None                     # tq.industry_rs_table (index = 업종)
    risk: dict = field(default_factory=dict)               # 공시위험 {code: {level, hits, ref, …}}
    risk_path: str | None = None
    risk_date: str | None = None                           # 공시위험 파일 기준일 (YYYYMMDD)
    asof_eod: str | None = None                            # 업종 RS 를 잰 완성 봉 기준일
    market_eod: dict = field(default_factory=dict)         # 체크리스트 1 — 완성 봉 기준 시장 국면 {시장: MarketState | None}

    def summary(self) -> dict:
        n_rs = int(self.ind_rs["rank_pct"].notna().sum()) if self.ind_rs is not None and len(self.ind_rs) else 0
        return {"risk_loaded": bool(self.risk), "risk_date": self.risk_date, "risk_env": RISK_ENV,
                "industry_rs_groups": n_rs, "asof_eod": self.asof_eod}


def eod_asof(ud) -> pd.Timestamp | None:
    """업종 RS · 시장 맥락의 기준일 — 스냅샷이 장중이면 오늘(미완성) 전 거래일."""
    from .universe_data import partial_bar
    asof = getattr(ud, "asof", None)
    if asof is None:
        return None
    fetched = getattr(ud, "fetched_at", None)
    part = partial_bar(asof, fetched)[0] if fetched is not None else False
    if not part:
        return pd.Timestamp(asof)
    idx = (getattr(ud, "index", None) or {}).get("KOSPI")
    if idx is None or not len(idx):
        return None
    before = idx.index[idx.index < pd.Timestamp(asof)]
    return before[-1] if len(before) else None


def eod_market(ud, asof: pd.Timestamp | None) -> dict:
    """체크리스트 1 의 시장 국면 — 완성 봉까지. 지수 마지막 봉이 asof(완성 봉 기준일) 뒤면(장중 스냅샷) 그 봉을 빼고
    analyze_market 을 다시 돌린다(시장 폭 = breadth_hist 의 asof 값, 백테스트와 같은 방식). 아니면 ud.market 그대로.
    다시 판정하지 못하면 None → 체크리스트 1 '모름' (장중 잠정 국면을 완성 봉 판정에 섞지 않는다)."""
    out: dict = {}
    states = getattr(ud, "market", None) or {}
    for m, df in (getattr(ud, "index", None) or {}).items():
        if df is None or not len(df) or asof is None:
            continue
        if df.index[-1] <= asof:
            out[m] = states.get(m)
            continue
        cut = df[df.index <= asof]
        try:
            from .breadth import breadth_at
            from .market import analyze_market
            hist = getattr(ud, "breadth_hist", None)
            out[m] = analyze_market(m, cut, breadth=breadth_at(hist, m, asof) if hist else None) if len(cut) > 1 else None
        except Exception:
            out[m] = None
    return out


def load_risk(cfg: Config | None = None) -> tuple[dict, str | None, str | None]:
    """공시위험 파일 → ({code: 항목}, 경로, 기준일). 보컬 설정의 risk_path, 없으면 환경변수. 없거나 못 읽으면 ({}, 경로, None)."""
    path = None
    try:
        from .vocal import VocalConfig
        path = (cfg or Config()).pattern_cfg("vocal", VocalConfig).risk_path
    except Exception:
        path = None
    path = path or os.environ.get(RISK_ENV)
    if not path:
        return {}, None, None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh) or {}
        codes = d.get("codes") or {}
        return ({str(k).zfill(6): v for k, v in codes.items() if isinstance(v, dict)}, path,
                str(d.get("기준일")) if d.get("기준일") else None)
    except Exception:
        return {}, path, None


def scan_inputs(ud, sector_map: pd.DataFrame | None, strength: pd.DataFrame | None, stock_groups: Callable | None,
                cfg: Config | None = None, verbose: bool = False) -> ScanInputs:
    si = ScanInputs(sector_map=sector_map, strength=strength, stock_groups=stock_groups)
    asof = eod_asof(ud)
    si.asof_eod = f"{asof:%Y-%m-%d}" if asof is not None else None
    if sector_map is not None and len(sector_map) and "sector" in sector_map:
        si.sector_of = {str(c): s for c, s in zip(sector_map["code"], sector_map["sector"]) if isinstance(s, str) and s}
    if si.sector_of and getattr(ud, "ohlcv", None) and asof is not None:
        try:
            closes = {c: d["close"] for c, d in ud.ohlcv.items() if c in si.sector_of}
            si.ind_rs = tq.industry_rs_table(closes, si.sector_of, asof=asof)
        except Exception as e:      # 업종 RS 는 체크리스트 5 · 2 의 자료 — 실패하면 그 항목만 '모름'
            si.ind_rs = None
            if verbose:
                print(f"  업종 RS 생략: {type(e).__name__}: {e}", file=sys.stderr)
    si.risk, si.risk_path, si.risk_date = load_risk(cfg)
    si.market_eod = eod_market(ud, asof)
    return si


def industry_row(si: ScanInputs, code: str) -> tuple[dict | None, float | None]:
    """(체크리스트 5 입력 {group, rank_pct, members, rs}, 체크리스트 2 의 업종 연중 위치 중앙값 pos52)."""
    g = si.sector_of.get(code)
    if not g:
        return None, None
    t = si.ind_rs
    if t is None or g not in t.index:
        return {"group": g, "rank_pct": None, "members": 0, "rs": None}, None
    row = t.loc[g]
    return ({"group": g, "rank_pct": _f(row["rank_pct"]), "members": int(row["members"]), "rs": _f(row["rs"])},
            _f(row["pos52"]))


def fill_info(ctx, si: ScanInputs | None) -> None:
    """탐지 전에 ctx.info 에 체크리스트 입력을 넣는다 (없는 자료는 넣지 않음 → 그 항목 '모름')."""
    if si is None:
        return
    info = ctx.info
    if si.stock_groups is not None and si.sector_map is not None and len(si.sector_map):
        try:
            info["groups"] = si.stock_groups(ctx.code, si.sector_map, si.strength)
        except Exception:
            info.pop("groups", None)
    ir, pos = industry_row(si, ctx.code)
    info["industry_rs"] = ir
    info["sector_pos52"] = pos
    info["risk"] = si.risk.get(ctx.code) if si.risk else None
    if ctx.market in si.market_eod:         # 장중이면 ctx.market_state(오늘 미완성 봉 포함 잠정)가 아닌 완성 봉 국면
        info["market_state_eod"] = si.market_eod[ctx.market]


# ---------------------------------------------------------------- 배지 (저평가 등급 · 공시위험)
def risk_tags(entry: dict | None, value_row: dict | None = None) -> list[list[str]]:
    """공시위험 항목 → [[글, 'bad'|'warn'], …] (vocal 의 잡주 분류와 같은 이름). 저평가 행의 공시 위험 글도 덧붙인다."""
    try:
        from .vocal import JUNK_REF, RISK_RED, WARN_REF
    except Exception:   # pragma: no cover
        JUNK_REF, RISK_RED, WARN_REF = {}, (), {}
    out: list[list[str]] = []
    rk = entry or {}
    if rk.get("level"):
        out.append([f"공시 위험: {rk['level']}", "bad" if rk["level"] in RISK_RED else "warn"])
    for r in rk.get("ref") or []:
        c = r.get("cat") if isinstance(r, dict) else None
        if not c:
            continue
        if c in JUNK_REF:
            out.append([JUNK_REF[c], "bad"])
        elif c in WARN_REF:
            out.append([WARN_REF[c], "warn"])
        else:
            out.append([str(c), "warn"])
    vr = (value_row or {}).get("risk") if isinstance(value_row, dict) else None
    if vr and not any(t == f"공시 위험: {vr}" for t, _ in out):
        out.append([f"공시 위험: {vr}", "bad"])
    seen, uniq = set(), []
    for t, sev in out:
        if t not in seen:
            seen.add(t)
            uniq.append([t, sev])
    return uniq


def badges(ctx) -> dict | None:
    """후보 줄 배지: {'tier': '저평가'|'관찰', 'tier_why', 'value_score', 'risk': [[글, 등급], …]} — 없으면 None."""
    info = getattr(ctx, "info", None) or {}
    out: dict[str, Any] = {}
    v = info.get("undervalued")
    if isinstance(v, dict) and v.get("tier"):
        out["tier"] = str(v["tier"])
        out["tier_why"] = [str(x) for x in (v.get("tier_why") or [])][:4]
        out["value_score"] = _f(v.get("score"))
    tags = risk_tags(info.get("risk"), v if isinstance(v, dict) else None)
    if tags:
        out["risk"] = tags
    return out or None


# ---------------------------------------------------------------- 후보마다: 체크리스트 · 청산 계획
def _entry_stop(lead, close: float) -> tuple[float, float | None]:
    entry = scoring.planned_entry(lead, close) if scoring.has_pivot(lead) else None
    stop = _f(lead.stop) if lead is not None and lead.stop else None
    return (float(entry) if entry else float(close)), (stop if stop and stop > 0 else None)


def _bar_of(df: pd.DataFrame, day, t: int) -> int | None:
    if not day:
        return None
    try:
        ts = pd.Timestamp(day)
    except (TypeError, ValueError):
        return None
    i = int(df.index.searchsorted(ts))
    return i if i <= t and i < len(df) and df.index[i] == ts else None


def _entry_i(lead, df: pd.DataFrame, t: int) -> int | None:
    """가정 진입 봉 (부록 §9: 신호 봉). 월봉 적삼병은 신호가 처음 보이는 봉(known_date — 다음 달 첫 거래일)."""
    if lead is None:
        return None
    m = lead.metrics or {}
    day = m.get("known_date") if lead.name == "red_three_monthly" and lead.breakout_date else lead.breakout_date
    return _bar_of(df, day, t)


def red3_replay(df: pd.DataFrame, cfg: Config | None = None, horizon: int = 20) -> list[dict]:
    """체크리스트 4 — 이 종목 과거 월봉 적삼병 신호: 확정 봉(다음 달 첫 거래일) 종가 → 20거래일 뒤 종가.
    df 는 완성 봉까지만(호출자가 자른다) — 20봉이 지난 신호만 (우리 데이터 재현, 확률 아님)."""
    from .patterns import red_three_monthly as rtm
    rcfg = (cfg or Config()).pattern_cfg(rtm.NAME, rtm.RedThreeConfig)
    C = df["close"].to_numpy(dtype=float)
    out = []
    for x in rtm.signals(df, rcfg):
        k = x.get("known_i")
        if k is None or k + horizon > len(df) - 1 or not C[k] > 0:
            continue
        out.append({"date": x.get("known_date"), "signal_month": x.get("signal_month"),
                    "ret20": float(C[k + horizon] / C[k] - 1)})
    return out


def _replay(lead, df: pd.DataFrame, cfg: Config | None) -> list[dict] | None:
    if lead is not None and lead.name == "red_three_monthly":
        try:
            return red3_replay(df, cfg)
        except Exception:
            return None
    return None     # 컵 앤 핸들 · 보컬: 날마다 식을 다시 돌려야 해 스캔에서 재현하지 않는다 → 4번 '모름'


def _counts(items: list[dict]) -> dict[str, int]:
    out = {tq.PASS: 0, tq.WARN: 0, tq.UNKNOWN: 0}
    for it in items:
        st = it.get("status") if isinstance(it, dict) else None
        if st in out:
            out[st] += 1
    return out


def stock_panel(s, cfg: Config | None = None) -> dict | None:
    """후보 하나의 기법 공통 칸 (표시 대표 기준). ctx 가 없거나 완성 봉이 2개 미만이면 None."""
    ctx = getattr(s, "ctx", None)
    if ctx is None:
        return None
    cfg = cfg or ctx.cfg
    lead = s.display_lead() if hasattr(s, "display_lead") else s.lead()
    df = tq.eod_frame(ctx)
    if len(df) < 2:
        return None
    b = tq.Bars.from_df(df)
    t = b.n - 1
    m = (lead.metrics or {}) if lead is not None else {}
    ck = m.get("checklist")
    if isinstance(ck, list) and len(ck) == len(tq.CHECKS) and all(isinstance(x, dict) for x in ck):
        items, src = ck, lead.name
    else:
        entry, stop = _entry_stop(lead, float(b.close[t]))
        rp = _replay(lead, df, cfg)
        items = [it.to_dict() for it in tq.run_checklist(b, t, tq.inputs_from_ctx(ctx, entry=entry, stop=stop, replay=rp))]
        src = "scan"
    ep = m.get("exit_plan")
    if isinstance(ep, dict) and ep:
        ep_src = lead.name
    else:
        ep, ep_src = tq.exit_plan(b, t, entry_i=_entry_i(lead, df, t)), "scan"
    return {"pattern": lead.name if lead is not None else None, "asof": b.date(t), "label": CHECK_LABEL,
            "note": CHECK_NOTE, "checklist": items, "counts": _counts(items), "source": src,
            "exit_plan": ep, "exit_source": ep_src, "exit_note": EXIT_NOTE}


# ---------------------------------------------------------------- 시장 맥락 칸 (지수)
def slim_red3(j: dict | None) -> dict | None:
    if not isinstance(j, dict):
        return None
    return {k: j[k] for k in RED3_KEEP if k in j}


def market_panel(ud) -> dict | None:
    """{'KOSPI': tq.market_context(...) + 지수 월봉 적삼병, 'KOSDAQ': …} — 완성 봉까지(장중이면 오늘 지수 봉 뺌)."""
    from .patterns import red_three_monthly as rtm
    from .universe_data import partial_bar
    fetched = getattr(ud, "fetched_at", None)
    out: dict[str, dict] = {}
    for name in ("KOSPI", "KOSDAQ"):
        df = (getattr(ud, "index", None) or {}).get(name)
        if df is None or len(df) < 2:
            continue
        part = bool(partial_bar(df.index[-1], fetched)[0]) if fetched is not None else False
        if part:
            df = df.iloc[:-1]
        try:
            mc = tq.market_context(df, name, red3=rtm.judge_monthly)
        except Exception as e:
            out[name] = {"name": name, "error": f"{type(e).__name__}: {e}"}
            continue
        mc["red3_monthly"] = slim_red3(mc.get("red3_monthly"))
        mc["partial_dropped"] = part
        out[name] = mc
    return out or None
