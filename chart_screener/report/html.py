"""스캔 결과 → 단일 HTML 리포트 (차트 데이터 내장, 오프라인 열람 가능 / 차트 라이브러리만 CDN).

새 필드(포지션·배지·업종/테마·레이더·시장 폭·탈락 목록·저평가 목록)는 ``getattr`` 로 읽어, 해당 필드가 없는
예전 ScanResult/StockScan 으로도 그대로 렌더링된다 (템플릿이 빈 섹션을 숨김).

'저평가 종목' 탭 (ScanResult.value, 기업추적 저평가 목록이 있을 때만)
    value = {"date", "source", "n", "tiers": {등급: 수}, "rows": [목록 전 종목 — 등급 · 저평가 수치 · Tech 패턴(단계) ·
             수급 · 목표가 · 종가 미니차트]}. 후보가 아닌 '저평가' 등급 종목은 value_stocks 에 짧은 이력(약 250봉)을 담아
    차트를 열 수 있게 하고(탐지된 패턴이 있는 종목만, 저평가 점수순 MAX_VALUE_CHARTS 개까지), '관찰' 등급 비후보는
    미니차트만 (리포트 크기).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .. import scoring
from ..patterns import REGISTRY
from ..scanner import ScanResult, StockScan, investor_summary

TEMPLATE = Path(__file__).with_name("template.html")
MIN_BARS, MAX_BARS, PAD_BARS = 2600, 2600, 30  # 불러온 이력 전체(최대 약 10년)를 담고, 기본 보기는 3년 (차트 기간 버튼)
MAX_RADAR, MAX_GROUPS, MAX_DROPPED, SPARK_DAYS = 300, 15, 200, 60
MAX_POSITION_PCT = 0.20   # 1종목 최대 비중 (계좌 대비) — 클라이언트 수량 재계산 상한
# 탐지 목록(태그 · 상세 탭) 순서: 베이스 → CAN SLIM · 포켓 피벗 → 저평가 종목(정보) → 관찰 전용(보컬 · 바닥 투매 흡수 · 바닥 탈출)
DETECTED_ORDER = (list(scoring.BASE_PATTERNS) + ["canslim", "pocket_pivot"] + list(scoring.INFO_PATTERNS)
                  + list(scoring.OBSERVE_PATTERNS))
# 후보 목록 칩 순서 (베이스 칩 뒤): CAN SLIM · 포켓 피벗 · 보컬 · 저평가 종목 · 바닥 투매 흡수 · 바닥 탈출
CHIP_ORDER = (["canslim", "pocket_pivot"] + list(scoring.OBSERVE_PATTERNS[:1]) + list(scoring.INFO_PATTERNS)
              + list(scoring.OBSERVE_PATTERNS[1:]))
VALUE_CHART_BARS, VALUE_SPARK_BARS = 250, 120   # 저평가 탭: 비후보 '저평가' 등급 차트 봉 수 · 미니차트 봉 수
MAX_VALUE_CHARTS = 120                          # 비후보 '저평가' 등급 차트 상한 (저평가 점수순 — 종목당 약 19KB, 리포트 크기)
VALUE_KEEP = ("trend_template",)                # 비후보 차트에 탐지 안 된 패턴 중 담을 것 (나머지는 크기 때문에 뺀다)


def _r(x, nd=0):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, nd) if nd else int(round(f))


def _arr(s: pd.Series, nd=0) -> list:
    return [_r(v, nd) for v in s.to_numpy()]


def _date(x) -> str | None:
    if x is None or x is pd.NaT:
        return None
    try:
        return f"{pd.Timestamp(x):%Y-%m-%d}"
    except (TypeError, ValueError):
        return str(x)


def _window_start(s: StockScan) -> int:
    """표시 구간: 탐지된 패턴의 시작일 앞 PAD_BARS 봉부터 (최소 MIN_BARS, 최대 MAX_BARS)."""
    df = s.ctx.df
    n = len(df)
    start = n - MIN_BARS
    for r in s.results.values():
        if r.detected and r.start_date:
            i = int(df.index.searchsorted(pd.Timestamp(r.start_date)))
            start = min(start, i - PAD_BARS)
    return max(0, n - MAX_BARS, start)


# ---------------------------------------------------------------- 새 필드 정리 (없으면 None / 빈 목록)
def _records(x) -> list:
    """list[dict] 또는 DataFrame → list (None 은 빈 목록)."""
    if x is None:
        return []
    if isinstance(x, str):
        return [x]
    if isinstance(x, pd.DataFrame):
        return x.to_dict("records")
    return list(x)


def _position(p) -> dict | None:
    """StockScan.position → {entry, stop, risk_pct, shares, amount, max_loss, plan, cap}.
    cap: 수량을 묶은 한도('위험'|'비중'|'유동성'), None 이면 스캐너가 매수 보류(관망·눌림 대기)로 판단."""
    if not isinstance(p, dict):
        return None
    out = {k: _r(p.get(k), 2) for k in ("entry", "stop")}
    out["risk_pct"] = _r(p.get("risk_pct"), 4)
    out.update({k: _r(p.get(k)) for k in ("shares", "amount", "max_loss")})
    out["plan"] = str(p["plan"]) if p.get("plan") else None
    out["cap"] = str(p["cap"]) if p.get("cap") else None
    return out


def _stock_groups(g) -> dict | None:
    """StockScan.groups(sector.stock_groups 결과) + 표 칩용 best = [이름, 구분, rank_pct]."""
    if not isinstance(g, dict):
        return None
    themes = []
    for t in _records(g.get("themes")):
        if isinstance(t, (list, tuple)) and t:
            themes.append([str(t[0]), _r(t[1], 3) if len(t) > 1 else None])
        elif t:
            themes.append([str(t), None])
    sector = g.get("sector") or None
    srank = _r(g.get("sector_rank_pct"), 3)
    cands = ([[str(sector), "업종", srank]] if sector else []) + [[n, "테마", r] for n, r in themes]
    ranked = [c for c in cands if c[2] is not None]
    best = max(ranked, key=lambda c: c[2]) if ranked else (cands[0] if cands else None)
    ranked_names = {n for n, _ in themes}
    extra = [str(t) for t in _records(g.get("themes_all")) if str(t) not in ranked_names]
    return {"sector": str(sector) if sector else None, "sector_rank_pct": srank, "themes": themes[:8],
            "themes_other": extra[:8], "best_rank_pct": _r(g.get("best_rank_pct"), 3), "best": best}


def _breadth(scan: ScanResult) -> dict | None:
    """시장 폭: ScanResult.breadth(전체) 우선, 없으면 MarketState.breadth 를 시장별로 모음."""
    src = getattr(scan, "breadth", None)
    if not isinstance(src, dict) or not src:
        src = {k: getattr(m, "breadth", None) for k, m in (scan.market or {}).items()}
    out = {}
    for k, b in src.items():
        if not isinstance(b, dict):
            continue
        d = {"date": _date(b.get("date"))}
        for f in ("universe", "new_highs", "new_lows", "nh_nl", "big_value_up"):
            d[f] = _r(b.get(f))
        for f in ("nh_nl_10d", "pct_above_50", "pct_above_200"):
            d[f] = _r(b.get(f), 4)
        ser = b.get("series") or {}
        d["series"] = {"dates": [_date(x) for x in list(ser.get("dates") or [])[-SPARK_DAYS:]],
                       "nh_nl": [_r(v, 1) for v in list(ser.get("nh_nl") or [])[-SPARK_DAYS:]],
                       "pct_above_50": [_r(v, 4) for v in list(ser.get("pct_above_50") or [])[-SPARK_DAYS:]]}
        out[str(k)] = d
    return out or None


def _radar(scan: ScanResult, listed: set[str]) -> list[dict]:
    rows = []
    for r in _records(getattr(scan, "radar", None))[:MAX_RADAR]:
        if not isinstance(r, dict) or not r.get("code"):
            continue
        rows.append({
            "code": str(r["code"]), "name": str(r.get("name") or r["code"]), "market": r.get("market"),
            "date": _date(r.get("date")), "days_ago": _r(r.get("days_ago")), "change": _r(r.get("change"), 4),
            "value": _r(r.get("value")), "close": _r(r.get("close"), 2), "support": _r(r.get("support"), 2),
            "holding": None if r.get("holding") is None else bool(r.get("holding")),
            "themes": [str(t) for t in _records(r.get("themes"))][:6],
            "in_list": str(r["code"]) in listed,
        })
    return rows


def _groups(scan: ScanResult, listed: set[str]) -> list[dict]:
    rows = []
    for g in _records(getattr(scan, "groups", None))[:MAX_GROUPS]:
        if not isinstance(g, dict) or not g.get("group"):
            continue
        leaders = []
        for x in _records(g.get("leaders")):
            if isinstance(x, (list, tuple)) and len(x):
                code = str(x[0])
                leaders.append([code, str(x[1]) if len(x) > 1 else code, code in listed])
        rows.append({
            "group": str(g["group"]), "kind": g.get("kind"), "members": _r(g.get("members")),
            "median_rs": _r(g.get("median_rs"), 1), "tt_pass_pct": _r(g.get("tt_pass_pct"), 4),
            "new_highs_20d": _r(g.get("new_highs_20d")), "big_value_today": _r(g.get("big_value_today")),
            "score": _r(g.get("score"), 1), "rank_pct": _r(g.get("rank_pct"), 3), "leaders": leaders[:5],
        })
    return rows


def _dropped(scan: ScanResult) -> list[dict]:
    """직전 스캔 후보 중 이번에 빠진 종목. dict 목록 또는 코드 목록 모두 허용."""
    rows = []
    for d in _records(getattr(scan, "dropped", None))[:MAX_DROPPED]:
        if isinstance(d, str):
            d = {"code": d}
        if not isinstance(d, dict) or not d.get("code"):
            continue
        rows.append({
            "code": str(d["code"]), "name": str(d.get("name") or d["code"]), "market": d.get("market"),
            "stage": d.get("prev_stage") or d.get("stage"), "pattern": d.get("prev_pattern") or d.get("pattern"),
            "score": _r(next((d[k] for k in ("composite", "prev_score", "score") if d.get(k) is not None), None), 1),
            "close": _r(d.get("close"), 2), "reason": d.get("reason"),
        })
    return rows


def _account(scan: ScanResult) -> dict | None:
    a = getattr(scan, "account", None)
    if not isinstance(a, dict):
        return None
    return {"size": _r(a.get("size")), "risk_per_trade": _r(a.get("risk_per_trade"), 4),
            "max_position_pct": _r(a.get("max_position_pct", MAX_POSITION_PCT), 4),
            "max_entry_risk": _r(a.get("max_entry_risk"), 4), "max_liquidity_pct": _r(a.get("max_liquidity_pct"), 4)}


def _stock_kis(k) -> dict | None:
    """StockScan.kis (kis_scan.stock_kis) → 리포트용. 목표가 괴리 · EPS 증가율은 % 단위."""
    if not isinstance(k, dict):
        return None
    ops = [{"date": _date(o.get("date")), "broker": str(o.get("broker") or ""), "opinion": str(o.get("opinion") or ""),
            "target": _r(o.get("target"))} for o in _records(k.get("opinions")) if isinstance(o, dict)][:3]
    eps = [[str(e[0]), _r(e[1])] for e in _records(k.get("eps_e")) if isinstance(e, (list, tuple)) and len(e) >= 2][:2]
    return {"tp_n30": _r(k.get("tp_n30")), "tp_up30": _r(k.get("tp_up30")), "tp_down30": _r(k.get("tp_down30")),
            "tp_avg": _r(k.get("tp_avg")), "tp_gap": _r(k.get("tp_gap"), 2), "opinions": ops,
            "fwd_eps_g": _r(k.get("fwd_eps_g"), 2), "eps_e": eps}


def _kis_header(scan: ScanResult) -> dict | None:
    """ScanResult.kis → 헤더 한 줄 {on, line, reason, day, real_value}. 필드가 없으면(예전 스캔·analyze) None."""
    k = getattr(scan, "kis", None)
    if not isinstance(k, dict):
        return None
    return {"on": bool(k.get("on")), "line": str(k.get("line") or ""), "reason": k.get("reason") or None,
            "day": k.get("day"), "real_value": bool(k.get("real_value")),
            "steps": [{"step": str(st.get("step")), "n": _r(st.get("n")), "ok": _r(st.get("ok")),
                       "fail": _r(st.get("fail")), "secs": _r(st.get("secs"), 1)}
                      for st in _records(k.get("steps")) if isinstance(st, dict)]}


def stock_payload(s: StockScan, rank: int, max_bars: int | None = None, slim: bool = False) -> dict:
    """종목 하나 → 리포트 자료. max_bars 가 있으면 차트 이력을 최근 그 봉 수로 자르고, slim 이면 탐지된 패턴(+VALUE_KEEP)만
    담는다 — 저평가 탭의 비후보 종목용 (리포트 크기)."""
    ctx = s.ctx
    df = ctx.df
    i0 = _window_start(s)
    if max_bars:
        i0 = max(i0, len(df) - max_bars)
    w = df.iloc[i0:]
    # 표시용 대표(보컬만 걸린 종목은 보컬) — 예전 StockScan 모양(display_lead 없음)도 그대로 그린다
    best = s.display_lead() if hasattr(s, "display_lead") else s.lead()
    _, risk = s.entry_risk()
    pats = {}
    for name, r in s.results.items():
        if slim and not r.detected and name not in VALUE_KEEP:
            continue
        d = r.to_dict()
        pats[name] = {k: d[k] for k in ("detected", "score", "stage", "pivot", "stop", "start_date", "end_date",
                                        "breakout_date", "metrics", "reasons", "warnings", "annotations")}
        pats[name]["score"] = round(float(r.score or 0), 1)
    rsl = ctx.rs_line
    rsl_vals = []
    if rsl is not None:
        tail = rsl.iloc[-252:]
        base = float(tail.dropna().iloc[0]) if tail.notna().any() else 1.0
        rsl_vals = [_r(v / base * 100, 2) for v in tail.to_numpy()]
    return {
        "rank": rank, "code": s.code, "name": s.name, "market": s.market,
        "close": _r(s.close), "chg": _r(s.change_pct, 4), "score": s.score.composite, "rs": _r(s.rs),
        "market_cap": _r(s.market_cap), "value_today": _r(s.value_today), "avg_value_20": _r(s.avg_value_20),
        "partial": s.partial,
        "best": best.name if best else None, "stage": best.stage if best else None,
        "dist": _r(s.close / best.pivot - 1, 4) if best and best.pivot else None,
        "risk": _r(risk, 4),
        "detected": [n for n in DETECTED_ORDER if n in s.results and s.results[n].detected],
        "bd": {"pattern_part": s.score.pattern_part, "tech_part": s.score.tech_part,
               "rs_part": s.score.rs_part, "notes": s.score.notes},
        "badge": getattr(s, "badge", None) or None,
        "prev_stage": getattr(s, "prev_stage", None) or None,
        "leader": bool(getattr(s, "leader", False)),
        "groups": _stock_groups(getattr(s, "groups", None)),
        "pos": _position(getattr(s, "position", None)),
        "patterns": pats,
        "ohlcv": {
            "t": [int(d.strftime("%Y%m%d")) for d in w.index],
            "o": _arr(w["open"]), "h": _arr(w["high"]), "l": _arr(w["low"]), "c": _arr(w["close"]),
            "v": _arr(w["volume"]),
        },
        "ma": {f"sma{n}": _arr(ctx.sma(n).iloc[i0:], 0 if slim else 1) for n in (50, 150, 200)},   # slim: 원 단위 (크기)
        "rsl": rsl_vals,
        "inv": investor_summary(s),
        "kst": [str(x) for x in (getattr(s, "kst", None) or [])],     # 증권사 종목 상태 태그 (경고 칩)
        "kis": _stock_kis(getattr(s, "kis", None)),
    }


# ---------------------------------------------------------------- 저평가 종목 탭
def _vnum(r: dict) -> dict:
    nd = {"score": 1, "per": 1, "per_then": 1, "per_pct": 0, "dd": 1, "roe": 1, "debt_eq": 0, "ni_yoy": 1, "px_yoy": 1}
    return {k: _r(r.get(k), d) if d else _r(r.get(k)) for k, d in nd.items()}


def _value_pats(s: StockScan) -> list:
    """목록 종목에 걸린 Tech 패턴 [[이름, 단계], …] (저평가 종목 칩 자신은 뺀다)."""
    return [[n, s.results[n].stage] for n in DETECTED_ORDER
            if n not in scoring.INFO_PATTERNS and n in s.results and s.results[n].detected]


def _value_row(r: dict, s: StockScan | None, skip: dict | None) -> dict:
    row = {"code": r["code"], "name": r.get("name") or r["code"], "tier": r.get("tier"), "industry": r.get("industry") or "",
           "why": list(r.get("tier_why") or []), "risk": r.get("risk"), **_vnum(r)}
    if s is not None:
        closes = s.ctx.df["close"].iloc[-VALUE_SPARK_BARS:] if s.ctx is not None else pd.Series(dtype=float)
        row.update(market=s.market, market_cap=_r(s.market_cap), rs=_r(s.rs), close=_r(s.close), chg=_r(s.change_pct, 4),
                   kst=[str(x) for x in (getattr(s, "kst", None) or [])], pats=_value_pats(s), skip=None,
                   thin=getattr(s, "thin", None),
                   inv=investor_summary(s) if s.ctx is not None else None, kis=_stock_kis(getattr(s, "kis", None)),
                   spark=_arr(closes))
    else:
        k = skip or {}
        row.update(market=k.get("market"), market_cap=_r(k.get("market_cap")), rs=_r(k.get("rs")), close=_r(k.get("close")),
                   chg=_r(k.get("chg"), 4), kst=[str(x) for x in k.get("kst") or []], pats=[],
                   skip=str(k.get("why") or "분석 안 함"), inv=None, kis=None,
                   spark=[_r(v) for v in (k.get("spark") or [])[-VALUE_SPARK_BARS:]])
    return row


def _value_eligible(scan: ScanResult) -> list[dict]:
    """비후보 '저평가' 등급 중 짧은 차트를 담을 수 있는 목록 행 (담는 순서대로 — 앞에서 MAX_VALUE_CHARTS 개까지).
    탐지된 패턴이 있어야 하고(없으면 열 탭이 없다), 후보(상위 top 밖 포함)는 뺀다 — 짧은 '후보 아님' 차트로 그리면
    매수 계획이 가려진다. 순서: Tech 패턴(정보 칩 '저평가 종목' 말고)이 걸린 종목 먼저, 그다음 저평가 점수순."""
    vl = getattr(scan, "value", None)
    if vl is None or not hasattr(vl, "rows"):
        return []
    scans = getattr(scan, "value_scans", None) or {}
    cands = {s.code for s in scan.stocks}
    eligible = [r for r in vl.rows if r.get("tier") == "저평가" and r["code"] not in cands
                and (s := scans.get(r["code"])) is not None and s.ctx is not None
                and any(x.detected for x in s.results.values())]
    eligible.sort(key=lambda r: (not _value_pats(scans[r["code"]]),
                                 -(r.get("score") if r.get("score") is not None else -1)))
    return eligible


def report_charts(scan: ScanResult, top: int = 150) -> list[tuple[str, StockScan]]:
    """리포트에 차트를 담는 종목 [(code, StockScan)] — 후보 상위 top, 그다음 저평가 비후보 차트 (chart_history.fill 순서)."""
    out = [(s.code, s) for s in scan.stocks if s.ctx is not None][:top]
    have = {c for c, _ in out}
    scans = getattr(scan, "value_scans", None) or {}
    out += [(r["code"], scans[r["code"]]) for r in _value_eligible(scan)[:MAX_VALUE_CHARTS] if r["code"] not in have]
    return out


def _value(scan: ScanResult, listed: set[str]) -> tuple[dict | None, list[dict]]:
    """(저평가 탭 자료, 비후보 '저평가' 등급 종목의 짧은 차트 자료). 목록이 없으면 (None, [])."""
    vl = getattr(scan, "value", None)
    if vl is None or not hasattr(vl, "rows"):
        return None, []
    scans = getattr(scan, "value_scans", None) or {}
    skipped = getattr(scan, "value_skipped", None) or {}
    cands = {s.code for s in scan.stocks}
    eligible = _value_eligible(scan)
    eligible_codes = {r["code"] for r in eligible}
    chart_codes = {r["code"] for r in eligible[:MAX_VALUE_CHARTS]}
    rows, charts = [], []
    for r in vl.rows:
        s = scans.get(r["code"])
        row = _value_row(r, s, skipped.get(r["code"]))
        row["in_list"] = r["code"] in listed
        row["cand"] = r["code"] in cands                 # 후보(상위 top 밖이어도) — '후보' 태그
        row["chart"] = row["in_list"]
        if r["code"] in chart_codes:
            p = stock_payload(s, 0, max_bars=VALUE_CHART_BARS, slim=True)
            p["vonly"] = True
            charts.append(p)
            row["chart"] = True
        elif not row["chart"]:
            row["nochart"] = ("후보 — 리포트 상위 목록 밖 (후보 표 CSV · 엑셀에 있음)" if row["cand"]
                              else "패턴 미판정" if row.get("skip") else "관찰 등급" if r.get("tier") != "저평가"
                              else "탐지된 패턴 없음" if r["code"] not in eligible_codes
                              else f"차트 상한 {MAX_VALUE_CHARTS}개 밖")
        rows.append(row)
    d = vl.date
    meta = {"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 else d, "source": vl.source, "n": len(rows),
            "tiers": vl.counts(), "chart_bars": VALUE_CHART_BARS, "spark_bars": VALUE_SPARK_BARS, "rows": rows}
    return meta, charts


def build_payload(scan: ScanResult, top: int = 150) -> dict:
    stocks = [s for s in scan.stocks if s.ctx is not None][:top]
    listed = {s.code for s in stocks}
    prev = getattr(scan, "prev_asof", None)
    value, value_stocks = _value(scan, listed)
    return {
        "asof": f"{scan.asof:%Y-%m-%d}" if scan.asof is not None else "-",
        "generated_at": f"{scan.generated_at:%Y-%m-%d %H:%M}",
        "partial": any(s.partial for s in stocks),
        "scanned": scan.scanned,
        "labels": {n: lbl for n, (lbl, _) in REGISTRY.items()},
        "base_patterns": [n for n in scoring.BASE_PATTERNS if n in REGISTRY],
        "chip_patterns": [n for n in CHIP_ORDER if n in REGISTRY],
        "observe_patterns": [n for n in scoring.OBSERVE_PATTERNS if n in REGISTRY],
        "info_patterns": [n for n in scoring.INFO_PATTERNS if n in REGISTRY],
        "kis": _kis_header(scan),
        "market": {k: {"name": m.name, "state": m.state, "label": m.label, "close": m.close,
                       "distribution_days": m.distribution_days, "notes": m.notes,
                       "last_ftd": m.last_ftd} for k, m in scan.market.items()},
        "breadth": _breadth(scan),
        "prev_asof": _date(prev) if prev else None,
        "account": _account(scan),
        "max_position_pct": MAX_POSITION_PCT,
        # 필드 자체가 없으면 None(탭 숨김), 있으나 비었으면 [] ("해당 없음" 표시)
        "radar": _radar(scan, listed) if getattr(scan, "radar", None) is not None else None,
        "groups": _groups(scan, listed) if getattr(scan, "groups", None) is not None else None,
        "dropped": _dropped(scan) if getattr(scan, "dropped", None) is not None else None,
        "stocks": [stock_payload(s, i + 1) for i, s in enumerate(stocks)],
        "value": value,                     # 저평가 목록 없으면 None (탭 · 칩 숨김)
        "value_stocks": value_stocks,       # 비후보 '저평가' 등급 종목 짧은 차트 (약 250봉)
    }


class _Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o) if np.isfinite(o) else None
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (pd.Timestamp,)):
            return o.strftime("%Y-%m-%d")
        return str(o)


def _clean(o):
    """NaN/inf/NaT/NA → None (JSON 표준), numpy 스칼라·배열, 튜플·집합 → 파이썬 기본형."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_clean(v) for v in o.tolist()]
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if o is pd.NaT or o is pd.NA:
        return None
    return o


def render(payload: dict, standalone: bool = True) -> str:
    data = json.dumps(_clean(payload), ensure_ascii=False, cls=_Enc, separators=(",", ":"), allow_nan=False)
    data = data.replace("</", "<\\/")
    body = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", data)
    if not standalone:  # Artifact 게시용 조각 (스켈레톤은 게시 시 감싸짐)
        return body
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '</head>\n<body>\n' + body + "\n</body>\n</html>\n")


def write_report(scan: ScanResult, path: str | Path, top: int = 150, standalone: bool = True) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(build_payload(scan, top), standalone), encoding="utf-8")
    return path
