"""기업추적 저평가 목록 ↔ 스캔 연결 — 기업추적 뷰어가 쓴 JSON 을 읽어 '저평가 종목' 정보 칩 · 리포트 탭에 넣는다.

    vl = load_value()                       # 환경변수 CHART_SCREENER_VALUE_JSON 의 파일. 없거나 못 읽으면 None (탭 · 칩 없음)
    scan = run_scan(ud, cfg, value=vl)      # 종목마다 ctx.info["undervalued"] = 목록 행(dict) 또는 None
                                            # 목록 종목은 후보가 아니어도 ScanResult.value_scans 에 결과(ctx 포함)를 남기고,
                                            # 분석 대상 밖(유동성 필터 · 기간 부족)은 ScanResult.value_skipped 에 사유와 종가만

파일 양식 (v1, 기업추적 뷰어가 쓴다 — vocal.load_risk 의 CHART_SCREENER_RISK_JSON 과 같은 방식)
    {"v": 1, "at": epoch초, "date": "YYYYMMDD", "source": "기업추적 저평가",
     "rows": [{"code": "005930", "name": "삼성전자", "tier": "저평가" | "관찰", "score": 0~100 저평가 점수 | null,
               "per": 지금 PER, "per_then": 1년 전 PER, "per_pct": PER 자기 역사 백분위(0~100, 0 = 역대 가장 쌈),
               "dd": 52주 고점 대비 %(음수), "roe": %, "debt_eq": 부채비율 %, "ni_yoy": 순이익 1년 %, "px_yoy": 주가 1년 %,
               "industry": 업종, "tier_why": [관찰 사유], "risk": 공시 위험 등급 | null}]}
    숫자는 모두 null 가능. 종목코드는 6자리 문자열로 맞춘다(숫자 5930 → "005930").

**관찰용** — 종합 점수 · 매수 계획 · 실시간 감시에 쓰지 않는다. 등급은 기업추적 저평가 화면의 판단
(가치는 지켰는데 주가가 빠진 회사)을 그대로 옮기고, 차트 셋업은 Tech 패턴 결과를 붙여 보여 줄 뿐이다.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import pandas as pd

ENV = "CHART_SCREENER_VALUE_JSON"
TIERS = ("저평가", "관찰")                     # 저평가 = 기업추적 저평가 등급, 관찰 = 빨간불 · 자료 부족 등으로 한 단계 아래
NUM_FIELDS = ("score", "per", "per_then", "per_pct", "dd", "roe", "debt_eq", "ni_yoy", "px_yoy")
SPARK_BARS = 120                              # 리포트 미니차트(종가) 봉 수
SKIP_NOTE = "패턴 미판정(유동성 · 기간 부족)"


@dataclass
class ValueList:
    """저평가 목록 한 벌. rows 는 파일 순서(코드 중복은 앞 것만)."""
    rows: list[dict] = field(default_factory=list)
    at: float | None = None                   # 뷰어가 쓴 시각 (epoch 초)
    date: str | None = None                   # 기준일 YYYYMMDD
    source: str = "기업추적 저평가"
    path: str | None = None

    def __post_init__(self):
        self._by = {r["code"]: r for r in self.rows}

    def get(self, code) -> dict | None:
        return self._by.get(norm_code(code) or "")

    def codes(self) -> list[str]:
        return [r["code"] for r in self.rows]

    def counts(self) -> dict[str, int]:
        """{등급: 종목 수} — 등급 순서는 TIERS."""
        out = {t: 0 for t in TIERS}
        for r in self.rows:
            out[r["tier"]] = out.get(r["tier"], 0) + 1
        return out

    def apply_status(self, exclude) -> int:
        """증권사 상태(exclude(code) → 거래정지 · 정리매매 · 관리종목 · 투자위험 | None)인 '저평가' 등급 행을 '관찰'로 내린다
        (사유 '증권사 상태: …'). 기업추적은 06:30 에 전날 스캔의 상태로 등급을 매기므로, 그날 지정 · 정지된 종목을
        이번 스캔의 상태로 맞춘다. 반환: 내린 종목 수."""
        n = 0
        for r in self.rows:
            why = exclude(r["code"]) if r["tier"] == "저평가" else None
            if why:
                r["tier"] = "관찰"
                r["tier_why"] = [f"증권사 상태: {why}"] + [w for w in r["tier_why"] if not w.startswith("증권사 상태")]
                n += 1
        return n

    def summary_line(self) -> str:
        c = self.counts()
        d = f"{self.date[:4]}-{self.date[4:6]}-{self.date[6:8]}" if self.date and len(self.date) == 8 else (self.date or "-")
        return f"저평가 목록({self.source}, {d}): {len(self.rows)}종목 — " + " · ".join(f"{t} {n}" for t, n in c.items())


# ---------------------------------------------------------------- 정리
def norm_code(x) -> str | None:
    """종목코드 → 6자리 문자열. 숫자(5930, '5930', '5930.0')는 앞을 0 으로 채운다. 영문 섞인 코드(0015N0)는 대문자 그대로."""
    if x is None:
        return None
    if isinstance(x, float) and math.isfinite(x) and x == int(x):
        x = int(x)
    s = str(x).strip().upper()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    if s.isdigit() and len(s) <= 6:
        return s.zfill(6)
    return s if len(s) == 6 and s.isalnum() else None


def _num(x) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def norm_row(r) -> dict | None:
    """파일 한 행 → 정리된 행. 코드가 없으면 None. 모르는 등급은 '관찰'."""
    if not isinstance(r, dict):
        return None
    code = norm_code(r.get("code"))
    if not code:
        return None
    tier = str(r.get("tier") or "").strip()
    why = r.get("tier_why") or []
    out = {"code": code, "name": str(r.get("name") or code), "tier": tier if tier in TIERS else "관찰",
           "industry": str(r.get("industry") or ""),
           "tier_why": [str(w) for w in (why if isinstance(why, (list, tuple)) else [why]) if w],
           "risk": str(r["risk"]) if r.get("risk") else None}
    out.update({k: _num(r.get(k)) for k in NUM_FIELDS})
    return out


def parse_value(d) -> ValueList | None:
    """JSON 객체 → ValueList. 양식이 아니면(rows 없음 · v ≠ 1) None."""
    if not isinstance(d, dict) or not isinstance(d.get("rows"), list):
        return None
    if d.get("v") not in (None, 1):
        return None
    rows, seen = [], set()
    for r in d["rows"]:
        x = norm_row(r)
        if x is not None and x["code"] not in seen:
            seen.add(x["code"])
            rows.append(x)
    date = str(d["date"]) if d.get("date") else None
    return ValueList(rows=rows, at=_num(d.get("at")), date=date, source=str(d.get("source") or "기업추적 저평가"))


def load_value(path: str | os.PathLike | None = None) -> ValueList | None:
    """저평가 목록 파일(인자, 없으면 환경변수 CHART_SCREENER_VALUE_JSON). 경로가 없거나 못 읽으면 None."""
    path = path or os.environ.get(ENV)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            vl = parse_value(json.load(fh))
    except Exception:
        return None
    if vl is not None:
        vl.path = str(path)
    return vl


# ---------------------------------------------------------------- 분석 대상 밖 종목
def spark_closes(df: pd.DataFrame | None, bars: int = SPARK_BARS) -> list:
    """최근 bars 봉 종가 (미니차트용)."""
    if df is None or not len(df) or "close" not in df:
        return []
    return [float(v) if v == v else None for v in df["close"].iloc[-bars:].to_numpy(dtype=float)]


def skip_reason(code: str, ud, cfg) -> str:
    """목록 종목이 패턴 분석에 안 들어간 이유 (유동성 필터 · 기간 부족 · 종목 목록 밖)."""
    from .universe_data import build_context, passes_universe_filter

    if code in ud.ohlcv:
        ctx = build_context(code, ud, cfg)
        if ctx is None:
            return "일봉 없음"
        ok, why = passes_universe_filter(ctx)
        return "유동성 필터: " + " · ".join(why) if not ok else "분석 오류"
    if code in ud.universe.index:
        return f"기간 부족 — 일봉 {cfg.data.min_history_days}봉 미만(신규 상장) 또는 일봉 수집 실패"
    return "종목 목록 밖 — 스팩 · 리츠 · 우선주 제외 또는 상장폐지"


def skipped_entry(code: str, ud, cfg, why: str | None = None, kis=None) -> dict:
    """분석 대상 밖 목록 종목 → {why, market, market_cap, rs, close, chg, spark, kst} (리포트 행 보충용)."""
    df = ud.ohlcv.get(code)
    info = ud.universe.loc[code].to_dict() if code in ud.universe.index else {}
    rs = None
    if code in ud.rs.columns:
        col = ud.rs[code].dropna()
        rs = float(col.iloc[-1]) if len(col) else None
    close = chg = None
    if df is not None and len(df):
        close = _num(df["close"].iloc[-1])
        prev = _num(df["close"].iloc[-2]) if len(df) > 1 else None
        chg = close / prev - 1 if close and prev else None
    return {"why": why or skip_reason(code, ud, cfg), "market": info.get("market"),
            "market_cap": _num(info.get("market_cap")), "rs": rs, "close": close, "chg": chg,
            "spark": spark_closes(df), "kst": kis.tags(code) if kis is not None else []}
