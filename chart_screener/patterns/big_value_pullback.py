"""300억 장대양봉 후 눌림목 (장대양봉 몸통 50%선 지정가 매수).

배경 (실데이터 워크포워드, 2024-09~2026-10 유동성 종목, 아래 '검증' 참고)
 거래대금 300억↑·+7%↑ 장대양봉 다음날 시가에 사는 것은 평균적으로 손실이다. 그러나 Stage 2 상승 추세
 문맥에서 나온 장대양봉이 몸통 50%선까지 '눌릴 때' 지정가로 사면 기준선보다 나은 성과를 보였다.
 상승 추세 밖이거나 +15%↑(상한가 포함) 장대양봉은 눌림에 사도 성과가 음수였다 → 관찰만(detected=False).

기준
 [장대양봉] 마지막 봉 기준 15봉 이내
  1. 거래대금 ≥ 300억 (Config.big_value_threshold), 전일 대비 +7% 이상, 종가 위치(고저폭 내) ≥ 0.5.
  2. 연속 장대양봉: 10봉 이내로 이어지는 장대양봉은 한 묶음 → '첫 봉'이 기준 장대양봉(지지선·손절·경과일),
     뒤의 것은 후속 장대양봉(metrics.legs). 단 첫 봉이 다음 장대양봉 전에 이미 실패(아래 실패선 아래 종가)했다면
     다음 장대양봉이 새 기준이다.
  3. 등락률 +15% 이상(상한가 +25%↑ 포함)이면 관찰만 (detected=False).
 [Stage 2 문맥 — 장대양봉 당일 기준, 필수]
  4. 20일선 > 60일선 > 120일선 정배열, 종가가 52주 고점 -15% 이내, 트렌드 템플릿 8개 중 6개 이상.
     (과제 초안의 'TT 6개 이상 또는 정배열·고점 근접' 은 실데이터에서 TT 단독 통과분이 20일 +0.6%·중앙 -4.2%
     로 약해 '그리고'로 강화했다.) 미충족이면 관찰만 (detected=False, 경고).
 [50%선(지지선)·손절]
  5. 지지선 = 장대양봉 몸통 50% = (시가 + 종가)/2. 상한가권(+25%↑)은 (min(시가, 전일 종가) + 종가)/2.
     갭 상승봉에 갭 포함 정의((min(시가, 전일 종가)+종가)/2)도 검증했으나 몸통 기준보다 나빠(20일 +3.2% vs +4.3%)
     상한가권만 갭을 포함한다.
  6. 실패선 = max(지지선 -3%, 장대양봉 저가). 손절 = 실패선을 KRX 호가 단위로 내림.
 [단계 — 마지막 봉 기준]
  failed     : 장대양봉 다음 봉부터 한 번이라도 종가 < 실패선 (50%선 이탈).
  breakout   : 눌림(아래 near_pivot 조건의 저가 도달)을 거친 뒤 종가가 '눌림 전 고점'(장대양봉~눌림 직전 최고가,
               보통 장대양봉 고가) 위로 재돌파, 5봉 이내 & 고점 +5% 이내. 피벗 = 눌림 전 고점.
               (재돌파 후 5봉이 지났지만 +5% 이내에서 버티면 near_pivot, +5% 초과는 extended)
  near_pivot : 매수 구간 — 장대양봉 2봉째부터, 당일 저가가 지지선 +3% 이내에 닿거나 종가가 지지선 +5% 이내.
               피벗 = 지지선 (지정가 매수 기준: 지지선 ~ +3%).
  extended   : 아직 눌림 없이 종가가 장대양봉 고가 +5% 위 (추격 금지, 눌림 대기).
  forming    : 지지선 위에서 눌림 대기 (지정가 지지선 +3% 걸어 두기), 또는 눌림 후 반등 중.
  거래량 마름(최근 3일 평균 ≤ 장대양봉의 40%)은 실데이터에서 오히려 성과가 낮아(아래) 필수 조건이 아니다.
  눌림 거래량 비율은 metrics.pullback_vol_ratio 로 보고하고 점수에 반영한다(0.3~1.0 우대).

점수(0~100, detected 일 때만)
 Stage 2 30 (TT 6/7/8개 = 8/14/20, RS 70→99 = 0→10)
 + 장대양봉 30 (거래대금 300억→3000억 로그 0→10, 등락률 +7~10% 8 → +15% 2, 거래량 50일 평균 ≤8배 6·≤15배 3·
   초과 0, 종가 위치 0.5→0.9 = 0→6)
 + 눌림 25 (재돌파 25, 매수 구간 = 10 + 지지선 위 마감 5(-3% 이내 2) + 눌림 거래량 0.3~1.0배 6(그 밖 3)
   + 장대양봉 후 지지선 아래 마감 없음 4, 눌림 후 반등 12, 눌림 대기 8, 재돌파 후 지지 18, 재돌파 후 이격 15,
   눌림 없이 이격 4, 실패 0)
 + 최근성 15 (장대양봉 3봉 이내 15 → 15봉 5).

검증 (scratch 이벤트 스터디 — 이 탐지기와 같은 규칙의 독립 구현, 캐시 2,424종목, 장대양봉 2024-09-30~2026-10-06,
      유동성 필터·종목별 260봉 이후. 워크포워드로 df 를 매일 잘라 detect() 를 돌린 결과와 장대양봉·체결일·실패일·
      첫 눌림일·재돌파일이 5,700건 전부 일치)
 진입 (a) 지정가: 장대양봉 2~15봉째 저가가 지지선 +3% 에 처음 닿는 날 체결가 min(시가, 지지선×1.03)
      (그날 종가가 실패선 아래여도 체결로 집계), (b) 종가 신호: 처음 near_pivot(눌림) 판정일 다음날 시가.
 수익률 = 진입일 포함 h 거래일째 종가 기준. 기준선(무작위 유동성 종목-일) 5일 -0.08%·20일 +0.29%·60일 +2.34%.
 - 탐지 조건(Stage 2 & +7~15% & 종가 위치 ≥0.5) 장대양봉 1,047개, 82% 체결(n=852):
   (a) 5일 +0.9%, 20일 +3.3%(중앙 -1.1%, 승률 49%), 60일 +11.3%(중앙 +1.4%).
   (b) 20일 +3.9%(중앙 -0.6%), 60일 +11.8%. 같은 장대양봉 전체를 다음날 시가에 사면 20일 +2.6%·60일 +9.6%,
   체결된 사건만 다음날 시가였다면 20일 +0.4% — 성과의 상당 부분은 '문맥 필터'에서, 눌림 지정가는 진입가 개선.
   손절(실패선, 장중 저가) 적용 시 20일 +1.5%(승률 25%), 손절이 +20% 보다 먼저 78%.
   점수 3분위(체결 전날 점수): 하 20일 -0.4%·60일 -0.3%, 중 +4.1%·+13.5%, 상 +6.4%·+21.0% (가중치는 같은 표본에서
   정했으므로 표본 내 결과).
 - 관찰만 처리한 군(50%선 지정가): Stage 2 & +15~25% 20일 -2.5%·60일 -4.0%, Stage 2 & 상한가권 -3.6%·-8.4%,
   Stage 2 아님 & +7~15% -0.3%·+0.4%, Stage 2 아님 & 상한가권 -3.0%·-7.8%. 전체 장대양봉 다음날 시가 20일 -1.3%.
 - 재돌파 다음날 시가: 20일 +5.0%(중앙 +1.0%), 60일 +14.0% (n=304). 눌림 없이 고가 +5% 이격 후 진입: 20일 -0.3%.
 - 눌림 직전 3일 평균 거래량/장대양봉: ≤0.25배 20일 +1.5%(중앙 -5.6%), 0.25~0.4배 +2.0%, 0.4~1.0배 +4.3%
   (중앙 +1.6%), >1.0배 +2.9% — '거래량 마름'은 우위가 없다. 장대양봉 거래량 50일 평균 15배 초과는 -6.2% (n=31).
 - 단계별(탐지된 종목-일 관측, 중복 포함, 다음날 시가 20일): 눌림 +4.3%(중앙 0.0%), 재돌파 +4.2%, 재돌파 후 이격
   +6.3%, 눌림 대기 +2.5%, 눌림 없이 이격 +2.1%(중앙 -1.8%), 실패 +0.3%(중앙 -2.7%).
 - 분기별 편차가 매우 크다(2026Q1 20일 +9.1%, 2026Q2 -3.1%·60일 -22.5%) — 시장 국면 확인 필수.
 한계: 생존 편향(현재 상장 종목만), 거래비용·슬리피지 미반영, 상승장 비중이 큰 2년 표본.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..config import EOK
from .base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult, StockContext, hline, marker, \
    register
from .trend_template import evaluate as tt_evaluate

NAME = "big_value_pullback"
LABEL = "300억 장대양봉 후 눌림목"


@dataclass
class BigValuePullbackConfig:
    # ---- 장대양봉
    min_chg: float = 0.07                 # 전일 대비 +7% 이상
    max_chg: float = 0.15                 # 이 이상(+15%↑, 상한가 포함)은 관찰만 — 실데이터 눌림 매수 성과 음수
    min_close_pos: float = 0.5            # 고저폭 내 종가 위치 (윗꼬리가 몸통 위 절반 이하)
    min_value_eok: float | None = None    # None → Config.big_value_threshold (300억)
    limit_up_chg: float = 0.25            # 상한가권: 50%선에 갭 포함 (min(시가, 전일 종가)+종가)/2
    lookback: int = 15                    # 마지막 봉 기준 이 봉수 이내 장대양봉(묶음의 첫 봉)만
    cluster_gap: int = 10                 # 이 봉수 이내로 이어지는 장대양봉은 한 묶음 (첫 봉 기준)
    # ---- Stage 2 문맥 (장대양봉 당일 기준, 필수)
    tt_min: int = 6                       # 트렌드 템플릿 8개 중 최소 통과 수
    ma_stack: tuple = (20, 60, 120)       # 20일선 > 60일선 > 120일선
    near_high: float = 0.15               # 종가가 52주 고점 -15% 이내
    # ---- 눌림·단계
    min_pullback_days: int = 2            # 장대양봉 2봉째부터 눌림 인정 (다음날 바로 밀리는 것은 눌림 아님)
    zone: float = 0.03                    # 매수 구간: 저가가 지지선 +3% 이내 도달 (지정가 = 지지선 ~ +3%)
    near_band: float = 0.05               # 또는 종가가 지지선 +5% 이내
    fail_pct: float = 0.03                # 종가 < 지지선 -3% (또는 장대양봉 저가) → 실패
    extended_pct: float = 0.05            # 눌림 없이 종가 > 장대양봉 고가 +5% → 이격 과다
    buy_range: float = 0.05               # 재돌파 매수 한도: 눌림 전 고점 +5%
    breakout_window: int = 5              # 재돌파 후 이 봉수 이내면 breakout
    # ---- 점수·경고 참고값
    vol_dry: float = 0.30                 # 눌림 거래량/장대양봉 0.3~1.0 우대 (실데이터: 과도한 마름은 오히려 약함)
    vol_heavy: float = 1.0                #   (상한)
    vol_mult_ok: float = 8.0              # 장대양봉 거래량 50일 평균 배수: ≤8배 우대
    vol_mult_warn: float = 15.0           #   15배 초과는 감점·경고 (실데이터 성과 음수)
    value_full_eok: float = 3000.0        # 거래대금 점수 만점 (로그 척도 300억→3000억)


# ---------------------------------------------------------------- 호가 단위
_TICK_EDGES = np.array([2_000, 5_000, 20_000, 50_000, 200_000, 500_000], dtype=float)
_TICK_SIZES = np.array([1, 5, 10, 50, 100, 500, 1_000], dtype=float)


def _tick(p: float) -> float:
    """KRX 호가 단위 (2023 개편, KOSPI·KOSDAQ 공통)."""
    return float(_TICK_SIZES[np.searchsorted(_TICK_EDGES, p, side="right")])


def _floor_tick(p: float) -> float:
    t = _tick(p)
    return float(math.floor(p / t + 1e-9) * t)


def _round_tick(p: float) -> float:
    t = _tick(p)
    return float(math.floor(p / t + 0.5) * t)


# ---------------------------------------------------------------- 내부 배열
class _A:
    __slots__ = ("n", "idx", "o", "h", "l", "c", "v", "val", "chg", "cp", "mid", "nan_fixed")


def _arrays(ctx: StockContext, cfg: BigValuePullbackConfig) -> _A:
    return ctx._memo((NAME, "arrays", cfg.limit_up_chg), lambda: _build_arrays(ctx, cfg))


def _build_arrays(ctx: StockContext, cfg: BigValuePullbackConfig) -> _A:
    df = ctx.df
    A = _A()
    A.idx, A.n = df.index, len(df)
    px = df[["open", "high", "low", "close"]].astype(float)
    A.nan_fixed = bool(px.isna().to_numpy().any())
    if A.nan_fixed:
        px = px.ffill().bfill()
    o, h, l, c = (px[k].to_numpy().copy() for k in ("open", "high", "low", "close"))
    with np.errstate(invalid="ignore"):
        bad = ~(o > 0) | ~(h > 0) | ~(l > 0)
    if bad.any():                       # 시가·고가·저가 0·음수는 종가로 보정
        A.nan_fixed = True
        o = np.where(o > 0, o, c)
        h = np.where(h > 0, h, np.maximum(o, c))
        l = np.where(l > 0, l, np.minimum(o, c))
    A.o, A.c = o, c
    A.h, A.l = np.maximum.reduce([h, o, c]), np.minimum.reduce([l, o, c])
    A.v = np.nan_to_num(ctx.vol.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    A.val = np.nan_to_num(ctx.value.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pc = np.concatenate([[np.nan], c[:-1]])
        A.chg = c / pc - 1
        rng = A.h - A.l
        # 고저폭 0(점상한가 등): 전일보다 높게 마감했으면 고가 마감으로 간주
        A.cp = np.where(rng > 0, (c - A.l) / rng, np.where(c > pc, 1.0, np.nan))
        A.mid = np.where(A.chg >= cfg.limit_up_chg, (np.fmin(o, pc) + c) / 2, (o + c) / 2)
    return A


def _min_value(ctx: StockContext, cfg: BigValuePullbackConfig) -> float:
    return cfg.min_value_eok * EOK if cfg.min_value_eok is not None else ctx.cfg.big_value_threshold


def _fail_line(A: _A, i: int, cfg: BigValuePullbackConfig) -> float:
    return float(max(A.mid[i] * (1 - cfg.fail_pct), A.l[i]))


def _clusters(A: _A, cand: np.ndarray, cfg: BigValuePullbackConfig) -> list[list[int]]:
    """장대양봉 묶음 [[첫 봉, 후속...], ...]. 첫 봉이 다음 장대양봉 전에 실패했으면 새 묶음."""
    out: list[list[int]] = []
    for k in cand:
        k = int(k)
        if out and k - out[-1][-1] <= cfg.cluster_gap:
            a = out[-1][0]
            if not (A.c[a + 1:k] < _fail_line(A, a, cfg)).any():
                out[-1].append(k)
                continue
        out.append([k])
    return out


def _stage2(ctx: StockContext, A: _A, i: int, cfg: BigValuePullbackConfig) -> dict:
    """장대양봉 당일(i) 기준 Stage 2 문맥."""
    ev = tt_evaluate(ctx, at=-1 if i == ctx.n - 1 else i)
    mas = [float(ctx.sma(n).iloc[i]) for n in cfg.ma_stack]
    stack = bool(all(np.isfinite(mas)) and all(a > b for a, b in zip(mas, mas[1:])))
    hi52 = float(A.h[max(0, i - 251):i + 1].max())
    from_high = float(A.c[i] / hi52 - 1) if hi52 > 0 else float("nan")
    near = bool(hi52 > 0 and A.c[i] >= hi52 * (1 - cfg.near_high))
    passed = int(ev["passed"])
    return {"ok": bool(stack and near and passed >= cfg.tt_min), "tt_passed": passed, "ma_stack": stack,
            "near_high": near, "from_52w_high": from_high, "rs": ev["rs"], "mas": mas, "checks": ev["checks"]}


def _post(A: _A, i: int, cfg: BigValuePullbackConfig) -> dict:
    """장대양봉(i) 이후 마지막 봉까지의 흐름: 실패·눌림·재돌파와 현재 단계."""
    last = A.n - 1
    sup = float(A.mid[i])
    fail = _fail_line(A, i, cfg)
    zone_top = sup * (1 + cfg.zone)
    seg = slice(i + 1, last + 1)
    bad = np.flatnonzero(A.c[seg] < fail)
    fail_i = int(i + 1 + bad[0]) if len(bad) else None
    end = fail_i if fail_i is not None else last        # 실패 이전(또는 마지막 봉)까지에서 눌림을 찾는다
    a = i + cfg.min_pullback_days
    hit = np.flatnonzero(A.l[a:end + 1] <= zone_top) if a <= end else np.array([], int)
    touch_i = int(a + hit[0]) if len(hit) else None
    level = rb_i = None
    if touch_i is not None:
        level = float(A.h[i:touch_i].max())           # 눌림 전 고점 (보통 장대양봉 고가)
        up = np.flatnonzero(A.c[touch_i + 1:end + 1] > level)
        rb_i = int(touch_i + 1 + up[0]) if len(up) else None
    c, lo = float(A.c[last]), float(A.l[last])
    days = last - i
    if fail_i is not None:
        stage, state = FAILED, "failed"
    elif rb_i is not None and c > level:
        if c > level * (1 + cfg.buy_range):
            stage, state = EXTENDED, "rebreak_extended"
        elif last - rb_i < cfg.breakout_window:
            stage, state = BREAKOUT, "rebreak"
        else:
            stage, state = NEAR_PIVOT, "rebreak_hold"
    elif days >= cfg.min_pullback_days and (lo <= zone_top or c <= sup * (1 + cfg.near_band)):
        stage, state = NEAR_PIVOT, "pullback"
    elif touch_i is None and c > A.h[i] * (1 + cfg.extended_pct):
        stage, state = EXTENDED, "extended"
    elif touch_i is not None:
        stage, state = FORMING, "bounced"
    else:
        stage, state = FORMING, "waiting"
    post_lo = float(A.l[i + 1:last + 1].min()) if last > i else float("nan")
    win = slice(max(i + 1, last - 2), last + 1)
    pb_vol = float(A.v[win].mean() / A.v[i]) if last > i and A.v[i] > 0 else float("nan")
    held = bool(last == i or (A.c[i + 1:last + 1] >= sup).all())
    return {"stage": stage, "state": state, "sup": sup, "fail": fail, "zone_top": zone_top, "fail_i": fail_i,
            "touch_i": touch_i, "level": level, "rb_i": rb_i, "c": c, "days": days, "post_lo": post_lo,
            "pb_vol": pb_vol, "held": held}


# ---------------------------------------------------------------- 점수
def _clip01(x: float) -> float:
    return 0.0 if not np.isfinite(x) else float(min(1.0, max(0.0, x)))


def _score(S2: dict, cd: dict, P: dict, cfg: BigValuePullbackConfig) -> float:
    rs = S2["rs"]
    s2 = {6: 8.0, 7: 14.0}.get(S2["tt_passed"], 20.0 if S2["tt_passed"] >= 8 else 0.0) \
        + 10 * _clip01(((rs or 0) - 70) / 29)
    chg = cd["chg"]
    vm = cd["vol_mult"]
    span = math.log(max(cfg.value_full_eok / cd["min_eok"], 1.01))
    candle = (10 * _clip01(math.log(max(cd["value_eok"], 1e-9) / cd["min_eok"]) / span)
              + (8.0 if chg <= 0.10 else 8 - 6 * _clip01((chg - 0.10) / (cfg.max_chg - 0.10)))
              + (6.0 if not np.isfinite(vm) or vm <= cfg.vol_mult_ok else 3.0 if vm <= cfg.vol_mult_warn else 0.0)
              + 6 * _clip01((cd["cp"] - cfg.min_close_pos) / 0.4))
    st = P["state"]
    if st == "pullback":
        r = P["pb_vol"]
        pb = 10 + (5 if P["c"] >= P["sup"] else 2) \
            + (6 if cfg.vol_dry <= r <= cfg.vol_heavy else 3) + (4 if P["held"] else 0)
    else:
        pb = {"rebreak": 25, "rebreak_hold": 18, "bounced": 12, "waiting": 8, "rebreak_extended": 15,
              "extended": 4, "failed": 0}[st]
    rec = 15 - 10 * _clip01((P["days"] - 3) / (cfg.lookback - 3))
    return float(s2 + candle + pb + rec)


# ---------------------------------------------------------------- 탐지
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, BigValuePullbackConfig)
    res = PatternResult(name=NAME, label=LABEL)
    if ctx.n < 2:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}일)")
        return res
    A = _arrays(ctx, cfg)
    if not np.isfinite(A.c).any():
        res.warnings.append("✘ 가격 데이터 없음")
        return res
    min_value = _min_value(ctx, cfg)
    last = A.n - 1
    with np.errstate(invalid="ignore"):
        cand = np.flatnonzero((A.val >= min_value) & (A.chg >= cfg.min_chg) & (A.cp >= cfg.min_close_pos))
    clusters = _clusters(A, cand, cfg)
    if not clusters or last - clusters[-1][-1] > cfg.lookback:
        _explain_miss(A, cfg, min_value, res)
        return res
    legs = clusters[-1]
    i = legs[0]
    if last - i > cfg.lookback:
        res.warnings.append(f"✘ 장대양봉 묶음의 첫 봉({ctx.date(i)}) 이후 {last - i}봉 경과 (> {cfg.lookback}봉) — "
                            f"후속 장대양봉 {len(legs) - 1}개로 이미 상승, 눌림 기준 만료")
        res.metrics = {"candle_date": ctx.date(i), "days_since_candle": int(last - i), "legs": len(legs)}
        return res
    _fill(ctx, A, legs, cfg, min_value, res)
    return res


def _fill(ctx: StockContext, A: _A, legs: list[int], cfg: BigValuePullbackConfig, min_value: float,
          res: PatternResult) -> None:
    i = legs[0]
    last = A.n - 1
    S2 = _stage2(ctx, A, i, cfg)
    P = _post(A, i, cfg)
    stage, st, sup, c = P["stage"], P["state"], P["sup"], P["c"]
    min_eok = min_value / EOK
    vavg = A.v[max(0, i - 50):i]
    vm = float(A.v[i] / vavg.mean()) if len(vavg) >= 20 and vavg.mean() > 0 else float("nan")
    chg = float(A.chg[i])
    limit_up = bool(chg >= cfg.limit_up_chg)
    cd = {"chg": chg, "value_eok": float(A.val[i] / EOK), "vol_mult": vm, "cp": float(A.cp[i]), "min_eok": min_eok}
    too_big = chg >= cfg.max_chg
    detected = S2["ok"] and not too_big

    stop = _floor_tick(P["fail"])
    rebreak = st.startswith("rebreak")
    pivot = _round_tick(P["level"]) if rebreak else _round_tick(sup)
    res.detected = bool(detected)
    res.stage = stage
    res.pivot = pivot
    res.stop = stop
    res.start_date = ctx.date(i)
    res.end_date = ctx.date(last)
    res.breakout_date = ctx.date(P["rb_i"]) if rebreak else None
    res.score = round(min(100.0, _score(S2, cd, P, cfg)), 1) if detected else 0.0
    risk = 1 - stop / max(pivot, c) if max(pivot, c) > 0 else float("nan")
    res.metrics = {
        "candle_date": ctx.date(i), "candle_change": chg, "value_eok": cd["value_eok"], "support": sup,
        "days_since_candle": int(P["days"]), "stage2_ok": bool(S2["ok"]),
        "pullback_low_vs_support": P["post_lo"] / sup - 1 if np.isfinite(P["post_lo"]) else None,
        "limit_up": limit_up, "post_state": st, "candle_open": float(A.o[i]), "candle_close": float(A.c[i]),
        "candle_high": float(A.h[i]), "candle_low": float(A.l[i]), "close_pos": cd["cp"], "vol_mult_50d": vm,
        "tt_passed": S2["tt_passed"], "ma_stack": S2["ma_stack"], "from_52w_high": S2["from_52w_high"],
        "rs_at_candle": S2["rs"], "buy_zone_top": _floor_tick(P["zone_top"]), "fail_line": P["fail"],
        "pullback_date": ctx.date(P["touch_i"]) if P["touch_i"] is not None else None,
        "pullback_vol_ratio": P["pb_vol"], "held_above_support": P["held"],
        "rebreak_level": P["level"], "rebreak_date": ctx.date(P["rb_i"]) if P["rb_i"] is not None else None,
        "dist_from_support": c / sup - 1, "risk_pct": risk, "legs": len(legs),
        "last_leg_date": ctx.date(legs[-1]) if len(legs) > 1 else None, "too_big": bool(too_big),
    }

    R, W = res.reasons, res.warnings
    R.append(f"✔ {ctx.date(i)} 장대양봉 {chg:+.1%} · 거래대금 {cd['value_eok']:,.0f}억 (≥ {min_eok:,.0f}억) · "
             f"종가 위치 {cd['cp']:.2f}" + (f" · 거래량 50일 평균 {vm:.1f}배" if np.isfinite(vm) else ""))
    if len(legs) > 1:
        tail = ", ".join(f"{ctx.date(k)} {A.chg[k]:+.1%}" for k in legs[1:])
        R.append(f"✔ 후속 장대양봉 {len(legs) - 1}개 ({tail}) — 지지선·손절은 첫 장대양봉 기준")
    s2_txt = (f"20>60>120일선 {'정배열' if S2['ma_stack'] else '아님'}, 52주 고점 대비 {S2['from_52w_high']:+.0%}, "
              f"트렌드 템플릿 {S2['tt_passed']}/8" + (f", RS {S2['rs']:.0f}" if S2["rs"] is not None else ""))
    if S2["ok"]:
        R.append(f"✔ 장대양봉 당일 Stage 2 상승 추세: {s2_txt}")
    else:
        W.append(f"✘ 장대양봉 당일 Stage 2 문맥 아님 ({s2_txt}) — 관찰만. 상승 추세 밖 장대양봉은 눌림 매수도 "
                 f"평균 손실 (조건: 정배열 & 52주 고점 -{cfg.near_high:.0%} 이내 & 트렌드 템플릿 {cfg.tt_min}/8↑)")
    if too_big:
        W.append(f"✘ 장대양봉 {chg:+.1%} ≥ +{cfg.max_chg:.0%}{' (상한가권)' if limit_up else ''} — 관찰만. "
                 f"급등 장대양봉은 50%선 눌림 매수도 평균 손실 (실데이터)")
    zt = _floor_tick(P["zone_top"])
    lu_txt = " (상한가권: 갭 포함 (min(시가, 전일 종가)+종가)/2)" if limit_up else " ((시가+종가)/2)"
    R.append(f"✔ 지지선 = 장대양봉 몸통 50% {sup:,.0f}{lu_txt}, 손절 {stop:,.0f} "
             f"(실패선 max(지지선 -{cfg.fail_pct:.0%}, 장대양봉 저가))")

    if st == "failed":
        W.append(f"✘ 50%선 이탈: {ctx.date(P['fail_i'])} 종가 {A.c[P['fail_i']]:,.0f} < 실패선 {P['fail']:,.0f}")
    elif st == "pullback":
        touched = A.l[last] <= P["zone_top"]
        how = f"저가 {A.l[last]:,.0f}가 매수 구간(지지선 +{cfg.zone:.0%} = {zt:,.0f}) 도달" if touched else \
            f"종가가 지지선 +{cfg.near_band:.0%} 이내"
        R.append(f"✔ 눌림 매수 구간: {how} — 지정가 {pivot:,.0f}~{zt:,.0f} (피벗 = 50%선), 손절 {stop:,.0f}"
                 + (f" (위험 {risk:.1%})" if np.isfinite(risk) else ""))
        if c < sup:
            W.append(f"✘ 종가 {c:,.0f}가 지지선 아래 (실패선 {P['fail']:,.0f} 위) — 지지 확인 필요")
    elif st == "waiting":
        if P["days"] < cfg.min_pullback_days:
            R.append(f"✔ 눌림 대기: 장대양봉 {cfg.min_pullback_days}봉째부터 지정가 {pivot:,.0f}~{zt:,.0f} "
                     f"(현재가 대비 {zt / c - 1:+.1%})")
        else:
            R.append(f"✔ 눌림 대기: 지정가 {pivot:,.0f}~{zt:,.0f} (현재가 대비 {zt / c - 1:+.1%}) — 저가가 닿으면 체결")
    elif st == "bounced":
        R.append(f"✔ {ctx.date(P['touch_i'])} 50%선 눌림 후 반등 (현재 지지선 대비 {c / sup - 1:+.1%}) — "
                 f"재돌파 기준 {P['level']:,.0f} 또는 50%선 재눌림 대기")
    elif st == "extended":
        W.append(f"✘ 눌림 없이 장대양봉 고가 {A.h[i]:,.0f} +{cfg.extended_pct:.0%} 위 (지지선 대비 {c / sup - 1:+.0%}) "
                 f"— 추격 금지, 50%선 눌림 대기 (실데이터: 이격 후 진입 20일 성과 음수)")
    else:  # 재돌파 계열
        R.append(f"✔ {ctx.date(P['touch_i'])} 50%선 눌림 후 {ctx.date(P['rb_i'])} 눌림 전 고점 {P['level']:,.0f} "
                 f"재돌파 (피벗 = 눌림 전 고점)")
        if st == "rebreak_extended":
            W.append(f"✘ 재돌파 매수 한도(피벗 +{cfg.buy_range:.0%}) 초과 ({c / P['level'] - 1:+.0%}) — 추격 주의")
        elif st == "rebreak_hold":
            R.append(f"✔ 재돌파 후 {last - P['rb_i']}봉, 피벗 +{cfg.buy_range:.0%} 이내에서 지지")
    if st == "pullback" and np.isfinite(P["pb_vol"]):
        R.append(f"✔ 눌림 거래량: 최근 3일 평균이 장대양봉의 {P['pb_vol']:.0%}")
    if not P["held"] and st != "failed":
        W.append("✘ 장대양봉 이후 한때 지지선 아래 종가 기록 (실패선 위)")
    if np.isfinite(vm) and vm > cfg.vol_mult_warn:
        W.append(f"✘ 장대양봉 거래량이 50일 평균 {vm:.0f}배 (> {cfg.vol_mult_warn:.0f}배) — 과열·일회성 수급 가능성")
    if cd["value_eok"] < 500 and detected:
        W.append(f"✘ 거래대금 {cd['value_eok']:,.0f}억 — 500억 미만은 성과가 상대적으로 약함")
    if legs[-1] == last and ctx.partial:
        W.append("✘ 최근 장대양봉이 장중 미완성 봉 — 거래대금·등락률은 장중 추정치")
    elif ctx.partial:
        W.append("✘ 마지막 봉이 장중 미완성 — 저가·종가가 바뀔 수 있음")
    if A.nan_fixed:
        W.append("✘ 가격 결측·이상치를 보정함 (직전 값/종가)")

    ann = [
        marker(A.idx[i], f"{min_eok:,.0f}억+ · {chg:+.1%}", "below", "#e91e63", "arrowUp"),
        hline(sup, "50%선 (지지)", "#ff9800", "dashed"),
        hline(zt, f"매수 구간 상단 (+{cfg.zone:.0%})", "#ffb74d", "dotted"),
        hline(stop, "손절", "#d50000", "solid"),
    ]
    ann += [marker(A.idx[k], f"후속 {A.chg[k]:+.1%}", "below", "#f48fb1", "circle") for k in legs[1:]]
    if P["touch_i"] is not None:
        ann.append(marker(A.idx[P["touch_i"]], "50%선 눌림", "below", "#ff9800", "arrowUp"))
    if P["rb_i"] is not None:
        ann.append(hline(P["level"], "재돌파 기준 (눌림 전 고점)", "#2962ff", "dashed"))
        ann.append(marker(A.idx[P["rb_i"]], "재돌파", "below", "#2962ff", "arrowUp"))
    res.annotations = ann


def _explain_miss(A: _A, cfg: BigValuePullbackConfig, min_value: float, res: PatternResult) -> None:
    """최근 lookback 봉 안의 가장 유력한 상승일이 장대양봉 조건을 못 채운 이유."""
    last = A.n - 1
    a = max(1, last - cfg.lookback)
    with np.errstate(invalid="ignore"):
        up = np.flatnonzero(A.chg[a:last + 1] >= cfg.min_chg) + a
    if not len(up):
        big = np.flatnonzero(A.val[a:last + 1] >= min_value) + a
        if len(big):
            k = int(big[np.nanargmax(A.chg[big])])
            res.warnings.append(f"✘ 최근 {cfg.lookback}봉 내 +{cfg.min_chg:.0%} 이상 장대양봉 없음 "
                                f"(거래대금 {min_value / EOK:,.0f}억↑ 최대 상승일 {_d(A, k)} {A.chg[k]:+.1%})")
        else:
            res.warnings.append(f"✘ 최근 {cfg.lookback}봉 내 거래대금 {min_value / EOK:,.0f}억↑·"
                                f"+{cfg.min_chg:.0%}↑ 장대양봉 없음")
        return
    k = int(up[-1])
    why = []
    if not A.val[k] >= min_value:
        why.append(f"거래대금 {A.val[k] / EOK:,.0f}억 < {min_value / EOK:,.0f}억")
    if not A.cp[k] >= cfg.min_close_pos:
        why.append(f"종가 위치 {A.cp[k]:.2f} < {cfg.min_close_pos:.2f} (윗꼬리 김)")
    res.warnings.append(f"✘ 최근 {_d(A, k)} 상승일({A.chg[k]:+.1%})은 장대양봉 조건 미충족: " + "; ".join(why or ["-"]))


def _d(A: _A, i: int) -> str:
    return A.idx[i].strftime("%Y-%m-%d")
