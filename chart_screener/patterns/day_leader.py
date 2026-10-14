"""10% 주도주 (단타 관찰) — 《차트의 기술》 영상 [33:00–39:00] '10% 주도주 분봉 피보 단타' 중 일봉으로 되는 부분만.

스펙  docs/2026-10-14-chart-techniques-design.md §5
부록  docs/2026-10-14-chart-techniques-addendum.md §6 (수치 · 출처 — 스펙의 추정보다 우선) · §12 DL_BASIS 충돌 · §13 테스트
공용  chart_screener/techniques.py (Bars · eod_frame · fib_levels · window_halts · 체크리스트 · 청산 계획)

규칙 — 봉 t = 마지막 완성 봉, [0..t] 만 본다 (모든 함수가 b.cut(t) 또는 앞부분 불변인 벡터 계산 — 테스트로 확인)
  1. up_open = C/O − 1 · up_prev = C/C[−1] − 1 (둘 다 계산해 보인다) · vr = V / 기준선
     기준선 = t 전 거래량 > 0 인 마지막 20봉 평균 — 당일 제외(부록 §0.2 · §6), 거래량 0(정지) 행 제외(부록 §0.2)
  2. 후보 = 양봉(C > O 엄격) · DL_BASIS 쪽 등락 ≥ 10% · vr ≥ 3
  3. 표시 (다음 거래일 하루만 유효): 그날 저가 L → 고가 H 피보 참고가 lv(r) = H − r(H − L), r = 23.6 · 38.2 · 50%
     (61.8 은 표시만), 순서 불명 꼬리표 (O − L)/(H − L) > 0.3, 안내 'HTS 3분봉에서 반등 양봉 다음 봉 시가 진입 · 손절 기준선 이탈'
  4. 진입 판정은 하지 않는다 — 분봉 이력이 없다(스펙). 그래서 pivot · stop 은 None — Tech 매수 계획 · 실시간 감시 대상 아님.
     '3분봉' 크기도 영상 요약에 없어 미검증(부록 §6).

단계 (구현 선택 — base.classify_stage 는 피벗 돌파 기준이라 그대로 못 쓰고 그 뜻만 빌린다)
  마지막 완성 봉 t 가 신호                     단계 값 near_pivot = '매수 대기' 뜻 (관찰일 = 다음 거래일, 피벗 없음 — 이름 '관찰일')
  장중(t+1 = 관찰일 진행 중) 지금가 < 61.8%    단계는 그대로 — 경고 줄 '장중 잠정 · 그날 관찰 끝'(피보 눌림 61.8% 무효를 빌려 씀)
  장중 오늘 미완성 봉만 조건 충족              탐지 안 함 — 경고 줄 · metrics.provisional 만 (하루치 환산 거래량, 마감 뒤 다시 판정)
  일봉 EOD · 완성 봉만(스펙): 오늘 미완성 봉은 단계 · 탐지를 바꾸지 않는다 — 장중 정보는 경고 줄 · metrics.intraday 에만.
  t−1 신호 · t 는 아님                          탐지 안 함 — 관찰일(t)이 지났다는 경고만
점수 (구현 선택 — 확률 아님, 검증 안 됨): 40(조건 충족) + 거래량 배수 25(3→10배, 로그) + 등락 15(10→25%)
  + 두 기준(시가 · 전일) 모두 10% 이상 10 + 저가→고가 순서 명확 10. 거래량 기준선 구간에 거래정지가 있으면 거래량 몫 0.
과거 검증 없음 — scoring.BASE_PATTERNS 에 넣지 않을 관찰 칩 전제(보컬처럼). 불코우스키 통계는 이 기법에 해당 수치가 없어 쓰지
  않고, 같은 생각의 분봉 매매 설명(Daytrade)만 참고 문장으로 단다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import techniques as tq
from .base import NEAR_PIVOT, PatternResult, StockContext, hline, marker, register

NAME = "day_leader"
LABEL = tq.PATTERN_LABELS[NAME]           # '10% 주도주 (단타 관찰)'
RULE_VERSION = tq.RULE_IDS[NAME]          # 'dlead_v1' — 일지 rule 칸 (journal.rule_of 가 metrics['rule_version'] 을 읽음)

TILNOTE = "https://tilnote.io/pages/689b046edf13c4ef330e3e39"
KIWOOM_VI = "https://download.kiwoom.com/kiwoom_easy_help_new/5110.htm"
DAYTRADE = "https://thepatternsite.com/Daytrade.html"
LIMIT_URL = "https://www.etoday.co.kr/news/view/1127429"
LIMIT_CHANGE = pd.Timestamp("2015-06-15")
ENTRY_NOTE = "HTS 3분봉에서 반등 양봉 다음 봉 시가 진입 · 손절 기준선 이탈"
BASIS_KO = {"open": "시가 대비", "prev_close": "전일 대비"}
NO_BT = "관찰용 — 이 식은 과거 검증(백테스트) 없음 · 매수 신호 아님 · 진입 판정은 분봉에서 사람이"

ORIGIN = {
    "candidate": tq.video("33:00–39:00") + " 당일 10% 이상 오른 양봉 + 대량 거래 → 다음 날 단타 관찰 후보 (스펙 §5)",
    "white": tq.ORIGIN["white"],
    "min_chg": (f"10% — {tq.video('33:00–39:00')} · 정적 VI 는 직전 단일가 대비 ±10% 에서 발동 (키움 {KIWOOM_VI}) — "
                "개장 직후 직전 단일가 = 시가는 추론 · 전일 종가 기준 자료(kbthink)와 충돌 (부록 §6 · §12)"),
    "basis": (f"DL_BASIS 시가 대비(스펙 기본) · 전일 대비 둘 다 계산 — tilnote 영상 요약 ({TILNOTE}) 은 무엇 대비인지 "
              "밝히지 않음: 시가 대비는 미검증 (부록 §6 · §12)"),
    "vol": (tq.choice("거래량 ≥ 직전 20봉 평균 × 3 — 블로그 '세력봉 5~10배'(L 등급)는 안 씀, 당일을 빼야 급증 거래량이 "
                      "제 기준선을 부풀리지 않음 (부록 §6)") + " · " + tq.ORIGIN["baseline_excl_today"]),
    "zero_vol": tq.ORIGIN["halt_rows"],
    "fib": (f"피보 참고가 lv(r) = 고가 − r × (고가 − 저가), 그날 저가 → 고가 · 23.6 · 38.2 · 50% (61.8 표시만) — "
            f"tilnote 영상 요약 ({TILNOTE}): 분봉 자동 지표가 인식한 저점 · 고점에 0.236 · 0.382 · 0.5 · 0.618 · 1 · 1.618, "
            "진입은 38.2% 지지 반등 캔들 · " + tq.ORIGIN["fib_levels"]),
    "order": tq.choice("(시가 − 저가)/(고가 − 저가) > 0.3 이면 '저가→고가 순서 불명' — 일봉으로는 저가 · 고가 중 먼저 난 쪽을 모름"),
    "valid": tq.choice("표시는 신호 다음 거래일(t+1) 하루만 유효 (부록 §6)"),
    "no_entry": ("진입 판정 안 함 — 분봉 이력 없음 (스펙 §5 · 부록 §6) · 'HTS 3분봉' 크기는 영상 요약에 없어 미검증 · "
                 + tq.video("33:00–39:00")),
    "stage": tq.choice("단계 — 마지막 완성 봉이 신호 = 단계 값 near_pivot(다음 거래일 관찰 = 매수 대기 · 피벗 없음 — 화면 이름은 "
                       "'관찰일 (다음 거래일)'). 장중 정보"
                       "(관찰일 지금가 < 61.8% · 오늘 미완성 봉만 충족)는 경고 줄에만 — 단계는 완성 봉(스펙: 일봉 EOD)"),
    "intraday_invalid": (tq.choice("장중 잠정 — 관찰일 지금가가 61.8% 라인 아래면 그날 관찰 끝 · 피보 눌림 61.8% 무효를 빌려 씀")
                         + " · " + tq.ORIGIN["fib_invalid"]),
    "provisional": tq.choice("장중 잠정 — 오늘 미완성 봉 + 하루치 환산 거래량(ctx.vol)에 같은 조건, 마감 뒤 다시 판정"),
    "score": tq.choice("품질 점수 = 40(조건 충족) + 거래량 배수 25(3→10배, 로그) + 등락 15(10→25%) + 두 기준 일치 10 + "
                       "순서 명확 10 — 확률 아님 · 검증 안 됨"),
    "replay": tq.choice("체크리스트 4 재현 — 이 종목의 같은 식 과거 신호, 신호 다음 봉 시가 → 신호 뒤 20번째 봉 종가 "
                        "(일지 · 백테스트 진입 규칙) — 단타 결과가 아님"),
    "limit": f"가격제한폭 2015-06-15 부터 ±30%, 그 전 ±15% — 이투데이 ({LIMIT_URL}) · % 문턱은 이 변화에 민감 (부록 §0.2)",
    "halts": tq.choice("거래량 기준선 구간에 거래정지일이 있으면 경고 · 점수의 거래량 몫 0 — Tech 거래량은 미수정이라 정지가 "
                       "분할 · 병합이면 배수가 몇 배로 틀림 (techniques.window_halts · 컵 앤 핸들 어댑터와 같은 취지)"),
}
REFERENCE = (f"참고(분봉 영역 — EOD 로 코딩 안 함): Bulkowski Daytrade ({DAYTRADE}) — 일직선 상승 뒤 38 · 50% 되돌림에서 "
             "반전 기대, 종목 · 지수 10분 차트가 같은 방향으로 돌아설 때 진입. 통계가 아니라 방법 설명")


@dataclass
class DayLeaderConfig:
    basis: str = "open"                   # DL_BASIS 'open'(스펙 기본) | 'prev_close' — 둘 다 계산해 보인다
    min_chg: float = 0.10                 # DL_MIN_CHG
    vol_mult: float = 3.0                 # DL_VOL_MULT (구현 선택)
    vol_n: int = 20                       # DL_VOL_N — 당일 제외 · 거래량 0 행 제외
    order_ambig: float = 0.3              # DL_ORDER_AMBIG (구현 선택)
    ratios: tuple = tq.FIB_RATIOS         # 23.6 · 38.2 · 50 · 61.8
    buy_ratios: tuple = tq.FIB_LEVELS_BUY
    invalid_ratio: float = tq.FIB_LEVEL_INVALID   # 장중 잠정 — 관찰일 지금가가 이 라인 아래면 그날 관찰 끝
    replay_h: int = 20                    # 체크리스트 4 — 20거래일
    checklist: bool = True                # 탐지된 후보에만 체크리스트 10 · 청산 계획을 붙인다
    # 품질 점수 (구현 선택 — 확률 아님)
    score_base: float = 40.0
    w_vol: float = 25.0
    vol_full: float = 10.0                # 이 배수에서 거래량 몫 만점
    w_chg: float = 15.0
    chg_full: float = 0.25                # 이 등락에서 등락 몫 만점
    w_agree: float = 10.0
    w_order: float = 10.0


# ---------------------------------------------------------------- 비교 (techniques 와 같은 부동소수 경계)
def _tol(b):
    return tq.EPS * np.maximum(1.0, np.abs(b))


def _ge(a, b):
    return a >= b - _tol(b)


def _le(a, b):
    return a <= b + _tol(b)


def _gt(a, b):
    return a > b + _tol(b)


def _lt(a, b):
    return a < b - _tol(b)


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _plain(x):
    """중첩 metrics(체크리스트 · 청산 계획)를 JSON 그대로 — numpy 스칼라 → 파이썬, NaN → None, tuple → list."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return _num(x)
    if isinstance(x, pd.Timestamp):
        return f"{x:%Y-%m-%d}"
    return x


def _rlabel(r: float) -> str:
    return f"{r * 100:g}%"


def _rkey(r: float) -> str:
    return f"fib_{int(round(r * 1000)):03d}"


# ---------------------------------------------------------------- 판정 (앞부분 불변)
def vol_baseline(v, n: int) -> np.ndarray:
    """봉 t 의 거래량 기준선 = t 전(당일 제외) 거래량 > 0 인 마지막 n봉 평균. 모자라면 NaN.

    거래량 0 행이 없으면 techniques.prior_mean(v, n) 과 같다(테스트로 확인). 봉 t 값은 v[:t] 만 쓴다 — 앞부분 불변."""
    v = np.asarray(v, dtype=float)
    out = np.full(len(v), np.nan)
    nz = np.flatnonzero(v > 0)                       # NaN 도 뺀다
    if n < 1 or len(nz) < n:
        return out
    cs = np.concatenate([[0.0], np.cumsum(v[nz])])
    k = np.searchsorted(nz, np.arange(len(v)), side="left")   # t 전 유효 봉 수
    ok = k >= n
    out[ok] = (cs[k[ok]] - cs[k[ok] - n]) / n
    return out


def signal_frame(b: tq.Bars, cfg: DayLeaderConfig | None = None) -> pd.DataFrame:
    """봉마다 후보 판정 (모두 그 봉까지의 자료). 열: white · up_open · up_prev · chg(DL_BASIS 쪽) · vol_base · vr · known · ok.
    known = 기준 등락과 거래량 기준선을 잴 수 있음 (False 면 '모름' — 후보 아님)."""
    cfg = cfg or DayLeaderConfig()
    if cfg.basis not in BASIS_KO:
        raise ValueError(f"basis: {cfg.basis!r}")
    O, C, V = b.open, b.close, b.volume
    pc = np.r_[np.nan, C[:-1]] if b.n else np.array([])
    base = vol_baseline(V, cfg.vol_n)
    with np.errstate(divide="ignore", invalid="ignore"):
        up_open = np.where(O > 0, C / O - 1, np.nan)
        up_prev = np.where(pc > 0, C / pc - 1, np.nan)
        vr = np.where(base > 0, V / base, np.nan)
        white = _gt(C, O)
        chg = up_open if cfg.basis == "open" else up_prev
        known = np.isfinite(chg) & np.isfinite(vr)
        ok = known & white & _ge(chg, cfg.min_chg) & _ge(vr, cfg.vol_mult)
    idx = b.dates if b.dates is not None else pd.RangeIndex(b.n)
    return pd.DataFrame({"white": white, "up_open": up_open, "up_prev": up_prev, "chg": chg, "vol_base": base,
                         "vr": vr, "known": known, "ok": ok}, index=idx)


def _fails(row: dict, cfg: DayLeaderConfig) -> list[str]:
    """후보가 아닌 이유 (한글)."""
    out = []
    bk = BASIS_KO[cfg.basis]
    if row["chg"] is None:
        out.append(f"{bk} 등락 모름 — " + ("전일 종가 없음" if cfg.basis == "prev_close" else "시가 없음"))
    if row["vr"] is None:
        out.append(f"이력 부족 — 거래량 기준선(직전 {cfg.vol_n}봉, 당일 · 거래량 0 행 제외) 모름")
    if not row["white"]:
        out.append("양봉 아님 (종가 ≤ 시가)")
    if row["chg"] is not None and not _ge(row["chg"], cfg.min_chg):
        out.append(f"{bk} {row['chg']:+.1%} < {cfg.min_chg:.0%}")
    if row["vr"] is not None and not _ge(row["vr"], cfg.vol_mult):
        out.append(f"거래량 {row['vr']:.2f}배 < {cfg.vol_mult:g}배 (직전 {cfg.vol_n}봉 평균, 당일 제외)")
    return out


def _score(row: dict, cfg: DayLeaderConfig) -> tuple[float, dict]:
    vr, chg = row["vr"], row["chg"]
    lv = math.log(cfg.vol_full / cfg.vol_mult) if cfg.vol_full > cfg.vol_mult > 0 else 0.0
    p_vol = cfg.w_vol * _clip01(math.log(vr / cfg.vol_mult) / lv) if vr and lv > 0 else 0.0
    span = cfg.chg_full - cfg.min_chg
    p_chg = cfg.w_chg * _clip01((chg - cfg.min_chg) / span) if chg is not None and span > 0 else 0.0
    parts = {"base": cfg.score_base, "vol": p_vol, "chg": p_chg,
             "agree": cfg.w_agree if row["agree"] else 0.0,
             "order": cfg.w_order if row["ambiguous"] is False else 0.0}
    return float(min(100.0, max(0.0, sum(parts.values())))), {k: float(v) for k, v in parts.items()}


def _row(fr: pd.DataFrame, b: tq.Bars, t: int, cfg: DayLeaderConfig) -> dict:
    """signal_frame 의 봉 t 한 줄 → 화면용 dict (피보 참고가 · 순서 · 점수 · 탈락 사유)."""
    o, h, lo, c, v = (float(x[t]) for x in (b.open, b.high, b.low, b.close, b.volume))
    x = fr.iloc[t]
    row = {"t": t, "date": b.date(t), "open": o, "high": h, "low": lo, "close": c, "volume": v, "basis": cfg.basis,
           "white": bool(x["white"]), "up_open": _num(x["up_open"]), "up_prev": _num(x["up_prev"]),
           "chg": _num(x["chg"]), "vol_base": _num(x["vol_base"]), "vr": _num(x["vr"]),
           "known": bool(x["known"]), "ok": bool(x["ok"])}
    rng = h - lo
    good = math.isfinite(rng) and rng > 0
    row["order_pos"] = (o - lo) / rng if good else None
    row["ambiguous"] = None if row["order_pos"] is None else bool(_gt(row["order_pos"], cfg.order_ambig))
    row["close_pos"] = (c - lo) / rng if good else None
    uo, up = row["up_open"], row["up_prev"]
    row["agree"] = None if uo is None or up is None else bool(_ge(uo, cfg.min_chg) and _ge(up, cfg.min_chg))
    lvl = tq.fib_levels(h, lo, cfg.ratios) if good else {}
    row["fib"] = [{"r": float(r), "label": _rlabel(r), "price": float(p), "buy": r in cfg.buy_ratios}
                  for r, p in sorted(lvl.items())]
    row["fails"] = [] if row["ok"] else _fails(row, cfg)
    row["score"], row["score_parts"] = _score(row, cfg) if row["ok"] else (0.0, {})
    return row


def judge(b: tq.Bars, t: int, cfg: DayLeaderConfig | None = None) -> dict:
    """봉 t 판정 — [0..t] 만 본다(b.cut). 미래 봉을 더해도 같은 dict (앞부분 불변)."""
    cfg = cfg or DayLeaderConfig()
    t = t + b.n if t < 0 else t
    bt = b.cut(t)
    return _row(signal_frame(bt, cfg), bt, t, cfg)


def replay_signals(b: tq.Bars, t: int, cfg: DayLeaderConfig | None = None,
                   fr: pd.DataFrame | None = None) -> list[dict]:
    """체크리스트 4 — 봉 t 에 이미 20거래일이 지난 이 종목 과거 신호 [{'date', 'ret20'}].
    ret20 = C[j+20] / O[j+1] − 1 (j + 20 ≤ t 인 신호만 — 미래 없음). 단타 결과가 아니다."""
    cfg = cfg or DayLeaderConfig()
    t = t + b.n if t < 0 else t
    ok = (signal_frame(b.cut(t), cfg) if fr is None else fr)["ok"].to_numpy()[:t + 1]
    h, out = cfg.replay_h, []
    for j in np.flatnonzero(ok):
        if j + h > t or j + 1 > t:
            break
        e, x = float(b.open[j + 1]), float(b.close[j + h])
        if e > 0 and math.isfinite(x):
            out.append({"date": b.date(int(j)), "ret20": x / e - 1})
    return out


def intraday_view(sig: dict, o: float, h: float, lo: float, c: float, cfg: DayLeaderConfig | None = None) -> dict:
    """관찰일 장중(미완성 봉) 위치 — 표시만(3분봉 판정 아님). sig = 신호일 판정 dict."""
    cfg = cfg or DayLeaderConfig()
    fib = sig["fib"]
    reached = [f["label"] for f in fib if _le(lo, f["price"])]          # 저가 ≤ 라인
    inv = next((f["price"] for f in fib if abs(f["r"] - cfg.invalid_ratio) < 1e-12), None)
    if _gt(c, sig["high"]):
        zone = "신호일 고가 위"
    else:
        zone, upper = None, "신호일 고가"
        for f in fib:
            if _ge(c, f["price"]):
                zone = f"{upper} ~ {f['label']}"
                break
            upper = f["label"]
        zone = zone or f"{upper} 아래"
    return {"open": o, "high": h, "low": lo, "price": c, "deepest": reached[-1] if reached else None,
            "zone": zone, "gap_above_high": bool(_gt(o, sig["high"])),
            "below_invalid": bool(inv is not None and _lt(c, inv)), "invalid_line": inv}


# ---------------------------------------------------------------- 탐지기
def _halts(df: pd.DataFrame, v: np.ndarray, t: int, n: int) -> list[str]:
    """봉 t 거래량 기준선 구간(직전 n개 유효 봉 ~ t) 안의 거래정지일."""
    nz = np.flatnonzero(v[:t] > 0)
    i0 = int(nz[-n]) if len(nz) >= n else 0
    return tq.window_halts(df, i0, t)


def _fib_text(sig: dict) -> str:
    return " · ".join(f"{f['label']} {f['price']:,.0f}" + ("" if f["buy"] else "(표시만)") for f in sig["fib"])


def _pct(x: float | None) -> str:
    return "모름" if x is None else f"{x:+.1%}"


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, DayLeaderConfig)
    r = PatternResult(name=NAME, label=LABEL)
    m = r.metrics
    m["rule_version"] = RULE_VERSION
    df = tq.eod_frame(ctx)
    partial = bool(ctx.partial) and len(ctx.df) > len(df)
    b = tq.Bars.from_df(df)
    E = b.n - 1
    if E < 0:
        r.warnings.append("완성 봉 없음 — 판정 안 함")
        return r
    fr = signal_frame(b, cfg)
    row = _row(fr, b, E, cfg)
    today, ball = None, None
    if partial:
        # 오늘 미완성 봉: 거래량은 하루치 환산 추정(ctx.vol) — 장중 잠정 판정 · 관찰일 위치 표시에만
        ball = tq.Bars.from_df(ctx.df)._replace(volume=ctx.vol.to_numpy(dtype=float))
        today = _row(signal_frame(ball, cfg), ball, E + 1, cfg)

    if row["ok"]:
        sig, prov = row, False
    else:
        for k in ("up_open", "up_prev", "vr"):
            m[k] = row[k]
        r.warnings += [f"{row['date']} {w}" for w in row["fails"]]
        if E >= 1 and bool(fr["ok"].iloc[E - 1]):
            prev = _row(fr, b, E - 1, cfg)
            seen = intraday_view(prev, row["open"], row["high"], row["low"], row["close"], cfg)
            r.warnings.append(f"직전 신호 {prev['date']} — 관찰일 {row['date']} 이 지남 (표시는 다음 거래일 하루만 유효) · "
                              f"그날 저가 {row['low']:,.0f} " + (f"{seen['deepest']} 라인까지 내려옴" if seen["deepest"]
                                                                  else "23.6% 라인 위"))
        if today is not None and today["ok"]:
            # 일봉 EOD · 완성 봉만: 오늘 미완성 봉만 충족하면 탐지하지 않고 알리기만 (마감 뒤 다시 판정)
            m["provisional"] = True
            m["provisional_today"] = {k: today[k] for k in ("date", "up_open", "up_prev", "vr", "close")}
            r.warnings.append(f"장중 잠정: 오늘({today['date']}) 미완성 봉이 지금 기준 조건 충족 — 시가 대비 "
                              f"{_pct(today['up_open'])} · 거래량 {today['vr']:.1f}배(하루치 환산 추정). 판정은 완성 봉만 — "
                              "마감 뒤 다시 판정, 관찰일은 다음 거래일")
        elif partial:
            r.warnings.append("장중 스캔 — 판정은 어제까지 완성 봉, 오늘 미완성 봉은 잠정 확인에만 씀 (오늘 봉도 조건 미달)")
        return r

    t = sig["t"]
    sdf = ctx.df if prov else df
    vol = ball.volume if prov else b.volume
    halts = _halts(sdf, vol, t, cfg.vol_n)
    score, parts = sig["score"], dict(sig["score_parts"])
    if halts:
        score -= parts["vol"]
        parts["vol"] = 0.0
    r.detected = True
    r.score = float(score)
    r.pivot, r.stop = None, None
    r.start_date = r.end_date = sig["date"]
    intraday = None
    r.stage = NEAR_PIVOT       # 신호는 늘 완성 봉 (prov 는 이제 늘 False — 오늘 미완성 봉만 충족이면 위에서 탐지 안 함)
    if partial:                # 관찰일 장중 위치 — 표시만 (단계는 완성 봉 그대로)
        intraday = intraday_view(sig, today["open"], today["high"], today["low"], today["close"], cfg)
        intraday["date"] = today["date"]

    # ---- 수치
    bk = BASIS_KO[cfg.basis]
    other = "prev_close" if cfg.basis == "open" else "open"
    other_chg = sig["up_prev"] if other == "prev_close" else sig["up_open"]
    value = None
    if "value" in sdf.columns:
        value = _num((ctx.value if prov else sdf["value"]).iloc[t])
    pre15 = b.dates is not None and pd.Timestamp(sig["date"]) < LIMIT_CHANGE
    m.update({
        "signal_date": sig["date"], "observe_on": "신호 다음 거래일 하루", "basis": cfg.basis,
        "up_open": sig["up_open"], "up_prev": sig["up_prev"], "chg": sig["chg"], "min_chg": cfg.min_chg,
        "vr": sig["vr"], "volume": sig["volume"], "vol_base": sig["vol_base"], "vol_n": cfg.vol_n, "vol_mult": cfg.vol_mult,
        "open": sig["open"], "high": sig["high"], "low": sig["low"], "close": sig["close"],
        "order_pos": sig["order_pos"], "order_ambiguous": sig["ambiguous"], "close_pos": sig["close_pos"],
        "basis_agree": sig["agree"],
    })
    for f in sig["fib"]:
        m[_rkey(f["r"])] = f["price"]
    m.update({
        "fib": sig["fib"], "entry_note": ENTRY_NOTE, "value": value,
        "limit_regime": "±15% (2015-06-15 전)" if pre15 else "±30%",
        "halts": halts, "volume_unverified": bool(halts), "provisional": prov, "intraday": intraday,
        "score_parts": parts, "stage_rule": ORIGIN["stage"], "reference": REFERENCE, "origin": dict(ORIGIN),
        # 단계 값은 '매수 대기' 뜻의 near_pivot(점수용)이지만 피벗이 없어 '피벗 근접'이라 부르지 않는다 [stage]
        "stage_label": "관찰일 (다음 거래일)", "stage_short": "관찰일",
    })

    # ---- 근거
    tag = " (장중 잠정)" if prov else ""
    r.reasons.append(f"신호일 {sig['date']}{tag}: 양봉 · 시가 대비 {_pct(sig['up_open'])} · 전일 대비 {_pct(sig['up_prev'])} — "
                     f"기준 {bk} ≥ {cfg.min_chg:.0%} (출처: {tq.video('33:00–39:00')} · 시가 대비는 미검증)")
    r.reasons.append(f"거래량 {sig['vr']:.1f}배 — 직전 {cfg.vol_n}봉 평균(당일 · 정지 행 제외) {sig['vol_base']:,.0f} 대비 "
                     f"≥ {cfg.vol_mult:g}배 (구현 선택)")
    r.reasons.append(f"피보 참고가 (그날 저가 {sig['low']:,.0f} → 고가 {sig['high']:,.0f}): {_fib_text(sig)} "
                     "(출처: tilnote 영상 요약 · ChartSchool)")
    r.reasons.append(f"{'다음 거래일' if not prov else '내일'} 하루 관찰 — {ENTRY_NOTE} "
                     "(진입 판정 안 함 — 분봉 이력 없음, 피벗 · 손절 없음)")
    r.reasons.append("품질 점수 {:.0f} = 조건 {:.0f} + 거래량 {:.1f} + 등락 {:.1f} + 두 기준 일치 {:.0f} + 순서 명확 {:.0f} "
                     "(구현 선택 — 확률 아님)".format(score, parts["base"], parts["vol"], parts["chg"], parts["agree"],
                                                   parts["order"]))
    if sig["agree"] is False:
        r.warnings.append(f"{BASIS_KO[other]} {_pct(other_chg)} < {cfg.min_chg:.0%} — 기준을 {BASIS_KO[other]}로 하면 후보 아님 "
                          "(영상 요약이 기준을 밝히지 않음 · 부록 §12 DL_BASIS)")
    elif sig["agree"] is None:
        r.warnings.append(f"{BASIS_KO[other]} 모름 — 두 기준 일치 여부 모름")
    if sig["ambiguous"]:
        r.warnings.append(f"저가→고가 순서 불명 — 시가가 그날 범위의 {sig['order_pos']:.0%} 위치(> {cfg.order_ambig:.0%}): "
                          "저가가 고가 뒤에 났을 수 있어 피보 참고가가 분봉 자동 지표와 다를 수 있음")
    r.warnings.append(NO_BT)
    r.warnings.append("'3분봉' 크기는 영상 요약에 없음 — 미검증 (부록 §6)")
    if halts:
        r.warnings.append(f"거래량 기준선 구간에 거래정지일 {', '.join(halts)} — 정지가 분할 · 병합이면 거래량 배수가 몇 배로 틀림 "
                          "(Tech 거래량 미수정) · 점수의 거래량 몫 0")
    if pre15:
        r.warnings.append("가격제한폭 ±15% 시기(2015-06-15 전) — 10% 문턱의 무게가 지금과 다름")
    if prov:
        r.warnings.append("장중 잠정 — 오늘 봉은 미완성(거래량은 하루치 환산 추정). 마감 뒤 다시 판정, 관찰일은 다음 거래일")
    elif intraday is not None:
        line = (f"장중 잠정 (관찰일 {intraday['date']}): 지금가 {intraday['price']:,.0f} · {intraday['zone']} · 저가 "
                f"{intraday['low']:,.0f}" + (f" ({intraday['deepest']} 라인까지)" if intraday["deepest"] else "")
                + (" · 시가가 신호일 고가 위(갭 상승)" if intraday["gap_above_high"] else ""))
        if intraday["below_invalid"]:
            r.warnings.append(line + f" — 61.8% 라인 {intraday['invalid_line']:,.0f} 아래: 이날 관찰 끝 (3분봉 판정 아님)")
        else:
            r.warnings.append(line + " — 3분봉 판정 아님, 표시만")
        if today is not None and today["ok"]:
            r.warnings.append(f"장중 잠정: 오늘({today['date']}) 봉도 지금 기준 조건 충족 — 마감 뒤 내일 관찰 후보가 될 수 있음")

    # ---- 체크리스트 10 · 청산 계획 (모든 후보 공통, 표시만 — 완성 봉 E 기준)
    if cfg.checklist:
        rp = replay_signals(b, E, cfg, fr)
        items = tq.run_checklist(b, E, tq.inputs_from_ctx(ctx, replay=rp))
        cnt = tq.checklist_counts(items)
        m["checklist"] = _plain([it.to_dict() for it in items])
        m["checklist_counts"] = _plain(cnt)
        m["replay_n"] = len(rp)
        m["exit_plan"] = _plain(tq.exit_plan(b, E))
        r.reasons.append(f"체크리스트 10 (검증 전 · 완성 봉 {b.date(E)} 기준): 통과 {cnt[tq.PASS]} · 경고 {cnt[tq.WARN]} · "
                         f"모름 {cnt[tq.UNKNOWN]} — 4번 재현은 신호 다음 봉 시가 → 20거래일 뒤 종가(단타 결과 아님)")

    # ---- 차트
    ann = r.annotations
    for f in sig["fib"]:
        ann.append(hline(f["price"], f"피보 {f['label']}" + (" (다음 날 참고가)" if f["buy"] else " (표시만)"),
                         "#7e57c2" if f["buy"] else "#9e9e9e", "dashed" if f["buy"] else "dotted"))
    ann.append(hline(sig["high"], "신호일 고가 (피보 0%)", "#ef5350", "dotted"))
    ann.append(hline(sig["low"], "신호일 저가 (피보 100%)", "#1e88e5", "dotted"))
    ann.append(marker(sig["date"], "10% 주도주" + (" (잠정)" if prov else ""), "below", "#e91e63", "arrowUp"))
    return r
