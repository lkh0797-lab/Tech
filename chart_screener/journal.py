"""스캔 일지 (output/journal.csv) — 매 스캔의 후보를 쌓아 두고 직전 스캔과 비교·사후 성과를 추적.

    annotate(scan)   직전 기준일 행과 비교해 StockScan.badge·prev_stage, ScanResult.dropped·prev_asof 설정
                     배지: 신규(직전에 없음) · 돌파(단계가 돌파로) · 실패(단계가 돌파 실패로)
                           · 단계상승(형성 중 → 피벗 근접 → 돌파 순으로 한 단계 이상 올라감)
                     직전 일지가 아예 없으면 배지를 달지 않는다.
    append(scan)     후보 행을 일지에 추가 (UTF-8-SIG). 같은 기준일 행은 통째로 교체 → 기준일+종목 중복 없음.
    track()          과거 행의 이후 성과를 캐시 일봉으로 채운다 (python -m chart_screener track).
                     진입 = 기준일 다음 봉 시가 (백테스트와 같은 규칙), ret_N = N번째 봉 종가 / 진입가 − 1,
                     stop_hit / target_hit = 진입 후 60봉 안에 손절가 터치 / 진입가 +20% 터치,
                     outcome = 먼저 일어난 쪽 ('stop' | 'target' | 'open', 같은 봉이면 stop).
                     대표 패턴·단계·종합점수 5분위별 집계 — 시간이 갈수록 쌓이는 표본 외 근거.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import OUTPUT_DIR
from .patterns.base import BREAKOUT, FAILED, FORMING, NEAR_PIVOT, STAGE_LABELS

JOURNAL_PATH = OUTPUT_DIR / "journal.csv"
COLUMNS = ["asof", "code", "name", "market", "pattern", "stage", "pivot", "stop", "composite", "rs",
           "close", "value", "leader"]
TRACK_COLUMNS = ["entry", "ret_5", "ret_20", "ret_60", "stop_hit", "target_hit", "outcome", "bars"]
STAGE_ORDER = {FORMING: 0, NEAR_PIVOT: 1, BREAKOUT: 2}
BADGES = ("신규", "돌파", "단계상승", "실패")


# ---------------------------------------------------------------- 일지 입출력
def load_journal(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path or JOURNAL_PATH)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={"code": str, "asof": str}, encoding="utf-8-sig")
    code = df["code"].astype(str).str.strip()
    df["code"] = code.where(~code.str.fullmatch(r"\d{1,5}"), code.str.zfill(6))  # 엑셀 저장으로 0 이 빠진 코드 복원
    for c in ("pattern", "stage", "name", "market"):
        if c in df:
            df[c] = df[c].fillna("")
    return df


def _asof(scan) -> str | None:
    return f"{scan.asof:%Y-%m-%d}" if scan.asof is not None else None


def scan_rows(scan) -> pd.DataFrame:
    asof = _asof(scan)
    rows = []
    for s in scan.stocks:
        r = s.lead()
        rows.append({
            "asof": asof, "code": s.code, "name": s.name, "market": s.market,
            "pattern": r.name if r is not None else ("leader" if s.leader else ""),
            "stage": (r.stage or "") if r is not None else "",
            "pivot": r.pivot if r is not None else None, "stop": r.stop if r is not None else None,
            "composite": s.score.composite, "rs": s.rs, "close": s.close, "value": s.value_today,
            "leader": bool(s.leader),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def append(scan, path: str | Path | None = None) -> Path | None:
    """후보 행을 일지에 추가. 같은 기준일의 기존 행은 교체(장중 재실행·재스캔 대비). 기준일 없으면 None."""
    asof = _asof(scan)
    if asof is None:
        return None
    path = Path(path or JOURNAL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = load_journal(path)
    new = scan_rows(scan)
    keep = old[old["asof"] != asof] if len(old) else old
    parts = [p for p in (keep, new) if len(p)]
    out = pd.concat(parts, ignore_index=True) if parts else new
    out = out.drop_duplicates(["asof", "code"], keep="last").sort_values(["asof", "composite"],
                                                                         ascending=[True, False])
    out.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# ---------------------------------------------------------------- 직전 스캔 비교
def badge_for(prev_stage: str | None, stage: str | None, in_prev: bool) -> str | None:
    if not in_prev:
        return "신규"
    prev_stage, stage = prev_stage or "", stage or ""
    if stage == prev_stage:
        return None
    if stage == BREAKOUT:
        return "돌파"
    if stage == FAILED:
        return "실패"
    if prev_stage in STAGE_ORDER and stage in STAGE_ORDER and STAGE_ORDER[stage] > STAGE_ORDER[prev_stage]:
        return "단계상승"
    return None


def previous_snapshot(journal: pd.DataFrame, asof: str) -> tuple[str | None, pd.DataFrame]:
    """asof 보다 앞선 가장 최근 기준일과 그 행들."""
    if journal is None or journal.empty:
        return None, pd.DataFrame(columns=COLUMNS)
    earlier = journal[journal["asof"] < asof]
    if earlier.empty:
        return None, earlier
    prev = earlier["asof"].max()
    return prev, earlier[earlier["asof"] == prev]


def annotate(scan, path: str | Path | None = None, journal: pd.DataFrame | None = None) -> dict:
    """직전 기준일 대비 배지·이전 단계·탈락 목록을 scan 에 붙이고 {배지: [종목], '탈락': [...]} 요약을 반환."""
    asof = _asof(scan)
    summary: dict[str, list] = {b: [] for b in BADGES} | {"탈락": []}
    if asof is None:
        return summary
    journal = load_journal(path) if journal is None else journal
    prev_asof, prev = previous_snapshot(journal, asof)
    scan.prev_asof = prev_asof
    if prev_asof is None:
        return summary
    by_code = {r.code: r for r in prev.itertuples(index=False)}
    now_codes = set()
    for s in scan.stocks:
        now_codes.add(s.code)
        r = s.lead()
        stage = r.stage if r is not None else None
        p = by_code.get(s.code)
        s.prev_stage = (p.stage or None) if p is not None else None
        s.badge = badge_for(s.prev_stage, stage, p is not None)
        if s.badge:
            summary[s.badge].append(s)
    # 증권사 상태(관리종목 등)로 이번에 뺀 후보 — 사유를 붙여 탈락 표에 함께 남긴다
    excluded = {d["code"]: d for d in getattr(scan, "excluded", None) or [] if isinstance(d, dict) and d.get("code")}
    dropped = []
    for p in prev.itertuples(index=False):
        if p.code in now_codes:
            continue
        dropped.append({"code": p.code, "name": p.name, "market": getattr(p, "market", ""),
                        "pattern": p.pattern or None, "stage": p.stage or None,
                        "composite": _f(p.composite), "close": _f(p.close), "asof": prev_asof,
                        "reason": (excluded.get(p.code) or {}).get("reason")})
    dropped.sort(key=lambda d: -(d["composite"] or 0))
    summary["탈락"] = dropped
    seen = {d["code"] for d in dropped}
    scan.dropped = dropped + [d for c, d in excluded.items() if c not in seen]
    return summary


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


# ---------------------------------------------------------------- 사후 성과 추적
def forward_outcome(df: pd.DataFrame, asof, stop, horizons=(5, 20, 60), target: float = 0.20) -> dict:
    """기준일(asof) 신호의 사후 성과. 진입 = 다음 봉 시가(0 이면 종가)."""
    out: dict = {c: np.nan for c in TRACK_COLUMNS}
    out.update(stop_hit=None, target_hit=None, outcome=None, bars=0)
    if df is None or df.empty:
        return out
    idx = df.index
    e = int(idx.searchsorted(pd.Timestamp(asof), side="right"))
    n = len(df)
    if e >= n:
        return out
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    entry = o[e] if o[e] > 0 else c[e]
    out["entry"] = float(entry)
    out["bars"] = n - e
    for hz in horizons:
        j = e + hz - 1
        out[f"ret_{hz}"] = float(c[j] / entry - 1) if j < n else np.nan
    stop = _f(stop)
    end = min(n, e + max(horizons))
    outcome, stop_hit, target_hit = "open", False, False
    for j in range(e, end):
        s_hit = stop is not None and l[j] <= stop
        t_hit = h[j] >= entry * (1 + target)
        if outcome == "open":
            outcome = "stop" if s_hit else ("target" if t_hit else "open")
        stop_hit |= bool(s_hit)
        target_hit |= bool(t_hit)
    out.update(stop_hit=stop_hit, target_hit=target_hit, outcome=outcome)
    return out


def track(path: str | Path | None = None, horizons=(5, 20, 60), target: float = 0.20,
          cache=None, save: bool = True) -> pd.DataFrame:
    """일지의 모든 행에 사후 성과를 채워 반환 (save=True 면 일지에 덮어씀)."""
    from .data import OHLCVCache

    path = Path(path or JOURNAL_PATH)
    j = load_journal(path)
    if j.empty:
        return j
    cache = cache or OHLCVCache()
    filled = []
    for code, g in j.groupby("code", sort=False):
        df = cache.load(code)
        for i, row in g.iterrows():
            filled.append((i, forward_outcome(df, row["asof"], row.get("stop"), horizons, target)))
    res = pd.DataFrame([d for _, d in filled], index=[i for i, _ in filled])
    for c in res.columns:
        j[c] = res[c]
    j["first"] = _first_appearance(j)
    if save:
        j.drop(columns=["first"]).to_csv(path, index=False, encoding="utf-8-sig")
    return j


def _first_appearance(j: pd.DataFrame) -> pd.Series:
    """직전 기준일 일지에 없던(새로 후보가 된) 행."""
    dates = sorted(j["asof"].unique())
    prev_of = dict(zip(dates[1:], dates[:-1]))
    seen = {d: set(g["code"]) for d, g in j.groupby("asof")}
    return pd.Series([r.code not in seen.get(prev_of.get(r.asof), set()) for r in j.itertuples()], index=j.index)


def _agg(g: pd.DataFrame, horizons) -> dict:
    entered = g[g["entry"].notna()] if "entry" in g else g.iloc[0:0]
    row = {"표본": len(g), "진입": len(entered)}
    for hz in horizons:
        col = f"ret_{hz}"
        r = (pd.to_numeric(entered[col], errors="coerce").dropna() if col in entered and len(entered)
             else pd.Series(dtype=float))
        row[f"{hz}일n"] = len(r)
        row[f"{hz}일평균%"] = round(r.mean() * 100, 2) if len(r) else None
        row[f"{hz}일중앙%"] = round(r.median() * 100, 2) if len(r) else None
        row[f"{hz}일승률%"] = round((r > 0).mean() * 100, 1) if len(r) else None
    oc = entered["outcome"] if "outcome" in entered and len(entered) else pd.Series(dtype=object)
    row["손절먼저%"] = round((oc == "stop").mean() * 100, 1) if len(oc) else None
    row["+20%먼저%"] = round((oc == "target").mean() * 100, 1) if len(oc) else None
    return row


def summarize(j: pd.DataFrame, horizons=(5, 20, 60)) -> dict[str, pd.DataFrame]:
    """대표 패턴·단계·종합점수 5분위별 집계 (+ 전체·신규 진입만)."""
    if j.empty:
        return {}
    j = j.copy()
    j["pattern"] = j["pattern"].replace("", "-")
    j["단계"] = j["stage"].map(lambda s: STAGE_LABELS.get(s, s or "-"))
    comp = pd.to_numeric(j["composite"], errors="coerce")
    if comp.notna().sum() >= 5:
        j["점수5분위"] = pd.qcut(comp.rank(method="first"), 5, labels=["Q1(하위)", "Q2", "Q3", "Q4", "Q5(상위)"])
    else:
        j["점수5분위"] = "-"
    out = {"전체": pd.DataFrame([{"구분": "전체"} | _agg(j, horizons)])}
    if "first" in j:
        out["전체"] = pd.concat([out["전체"], pd.DataFrame([{"구분": "신규 진입만"} | _agg(j[j["first"]], horizons)])],
                              ignore_index=True)
    for key, col in (("대표 패턴", "pattern"), ("단계", "단계"), ("종합점수 5분위", "점수5분위")):
        rows = [{key: k} | _agg(g, horizons) for k, g in j.groupby(col, observed=True, sort=True)]
        out[key] = pd.DataFrame(rows)
    return out
