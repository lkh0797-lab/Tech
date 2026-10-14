#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cup-with-handle scanner / Claude Code handoff — Python 3.10+, standard library only.

실행 예:
  python cup_handle_scanner.py self-test
  python cup_handle_scanner.py demo --directory demo
  python cup_handle_scanner.py scan --input demo/DEMO.csv --output result.json
  python cup_handle_scanner.py scan --input data/*.csv --output result.json \
      --summary result.csv --charts-dir charts --benchmark index.csv
  python cup_handle_scanner.py replay --input demo/DEMO.csv --output events.json
  python cup_handle_scanner.py replay --input data.csv --output events.json --evaluate
  python cup_handle_scanner.py config --output config.json
  python cup_handle_scanner.py scan --input data.csv --config config.json \
      --as-of 2026-10-13 --tick-size 100 --output result.json

CSV: date,open,high,low,close,volume[,symbol]
날짜 YYYY-MM-DD 또는 YYYYMMDD. 헤더는 대소문자 무관. 종목 코드는 문자열 보존.
여러 종목을 한 CSV에 넣거나 파일 여러 개를 전달할 수 있음. 지수 CSV는 date,close.
행은 내부에서 날짜순 정렬하되 동일 종목·동일 날짜 중복은 오류 처리.

주의 / 이 구현이 실제로 보장하는 것:
1. 일봉 EOD 기준. 입력 마지막 봉은 완성된 봉이라고 가정. 장중 누적 거래량 미지원.
2. OHLCV는 공급처에서 동일 기준으로 조정해야 함. 기업행동 자동 조정·시세 수집 없음.
3. classic: 선행 상승 >=30%, 경과 기간 >=49일, 컵 12~33%, 손잡이 >=5세션,
   손잡이 깊이 <=12%, 중간값 검사. 8% 손잡이 최소 조건은 없음.
4. 기간은 '달력상 경과 7주' 정책. IBD 주봉 포함 개수 방식과 경계에서 차이 가능.
5. U자·회복률·쐐기·점수는 공개 기준을 정량화한 구현 휴리스틱. 공식 오닐 수식 아님.
6. 깊은 베이스는 deep 프로파일(33~50%)로 명시 분리. 시장 약세 여부는 사용자 확인.
7. 스윙 고점은 span개 후속 봉으로 확인. 확인일 <= as_of인 고점만 사용.
8. 피벗 계산에서 돌파 봉 제외. replay는 전일 READY 구조의 고정 피벗으로 판정.
9. 거래량 기준은 당일 제외 이전 50세션. 저거래량 돌파도 사건으로 남김.
10. RS선=종가/지수종가. IBD RS Rating이나 RSI 아님. 지수 없는 항목은 unknown.
11. 품질 점수는 성공 확률 아님. 미관측 항목을 제외한 점수와 coverage 함께 출력.
12. 이전 베이스를 자동 세는 기능은 미구현(base_stage=unknown). market filter는
    자체 지수 SMA50 정책이며 IBD confirmed uptrend와 동의어가 아님.
13. --evaluate는 사후 종가 수익률/MFE/MAE 관찰값. 주문·손절 전략 백테스트 아님.
14. 종목당 복수 후보를 보존하고 같은 피벗 주변 중복만 묶음. exhaustive가 아닌
    확인된 스윙 고점 기반 후보 검색이므로 패턴 recall은 별도 수작업 검증 필요.

Claude Code에서 확장할 때:
  - Config / evaluate_structure / classify_breakout / replay_symbol을 중심으로 유지.
  - 미래 데이터를 보는 centered smoothing, 최종 ZigZag 피벗 소급 사용 금지.
  - 형태 점수와 필수 구조 조건 분리. 임계값을 walk-forward 표본 밖에서 검증.
  - 실제 시장 호가 규칙은 --tick-table JSON([[가격하한,호가단위],...])로 제공.
    기본 entry는 수학적으로 pivot을 초과하는 최소 부동소수점 값. 실행용 호가 아님.
  - API/캐시/유니버스/병렬화/거래정지 달력/상장폐지 표본/분봉 체결을 별도 연결.

기준 출처(요약 기준의 링크; 자체 구현 수치는 Config와 rule origin으로 구분):
  https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf
  https://www.investors.com/how-to-invest/investors-corner/netflix-stock-chart-pattern/
  https://www.investors.com/how-to-invest/investors-corner/how-to-buy-stocks-lam-research-cup-with-handle-launched-75-percent-advance/
  https://finance.yahoo.com/news/handle-may-form-flat-double-223300101.html
  https://www.investors.com/how-to-invest/investors-corner/chart-reading-basics-how-a-buy-point-marks-a-time-of-opportunity/
  https://www.marketsmith.hk/cup-with-handle/?lang=en

배포 파일은 이 파일 하나. 추가 설치 불필요. 현재 버전 RULE_VERSION 참조.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import glob
import html
import json
import math
import statistics
import sys
import unittest
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Iterable

RULE_VERSION = "cwh_reference_v1.0.0"


@dataclass(frozen=True)
class Config:
    profile: str = "classic"
    prior_min_advance: float = 0.30
    prior_lookback: int = 250
    prior_min_sessions: int = 20
    base_min_calendar_days: int = 49
    base_max_calendar_days: int = 455
    cup_min_sessions: int = 20
    cup_min_depth: float = 0.12
    cup_max_depth: float = 0.33
    handle_min_sessions: int = 5
    handle_max_sessions: int = 40
    handle_max_depth: float = 0.12
    handle_start_grace: int = 3
    left_peak_span: int = 3
    right_peak_span: int = 2
    # These are implementation heuristics, NOT official O'Neil thresholds.
    min_recovery_ratio: float = 0.75
    max_right_rim_overshoot: float = 0.03
    bottom_zone_fraction: float = 0.15
    min_roundness_score: float = 0.55
    reject_prominent_double_bottom: bool = True
    handle_volume_pre_sessions: int = 50
    handle_volume_pre_min_sessions: int = 20
    breakout_volume_sessions: int = 50
    breakout_rvol_min: float = 1.40
    buy_zone_max: float = 0.05
    rs_high_window: int = 252
    rs_min_sessions: int = 60
    max_zero_volume_fraction: float = 0.10
    min_median_turnover: float = 0.0
    max_results_per_symbol: int = 10

    def validate(self) -> None:
        defaults = Config()
        for f in fields(self):
            value, expected = getattr(self, f.name), getattr(defaults, f.name)
            if isinstance(expected, bool):
                if type(value) is not bool:
                    raise ValueError(f"{f.name}: boolean required")
            elif isinstance(expected, int):
                if type(value) is not int or value < 1:
                    raise ValueError(f"{f.name}: positive integer required")
            elif isinstance(expected, float):
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"{f.name}: finite nonnegative number required")
        if self.profile not in ("classic", "deep"):
            raise ValueError("profile must be classic or deep")
        if not 0 < self.cup_min_depth < self.cup_max_depth < 1:
            raise ValueError("require 0 < cup_min_depth < cup_max_depth < 1")
        if not 0 < self.handle_max_depth < 1:
            raise ValueError("handle_max_depth must be between 0 and 1")
        if self.handle_min_sessions > self.handle_max_sessions:
            raise ValueError("handle_min_sessions exceeds handle_max_sessions")
        if self.base_min_calendar_days > self.base_max_calendar_days:
            raise ValueError("base duration bounds reversed")
        if self.handle_volume_pre_min_sessions > self.handle_volume_pre_sessions:
            raise ValueError("volume minimum exceeds volume window")
        if self.rs_min_sessions > self.rs_high_window:
            raise ValueError("RS minimum exceeds RS window")
        if not 0 < self.bottom_zone_fraction < 1:
            raise ValueError("bottom_zone_fraction must be between 0 and 1")
        if not 0 <= self.min_roundness_score <= 1:
            raise ValueError("min_roundness_score must be in [0,1]")
        if not 0 <= self.max_zero_volume_fraction <= 1:
            raise ValueError("max_zero_volume_fraction must be in [0,1]")
        if self.breakout_rvol_min < 1:
            raise ValueError("breakout_rvol_min must be >= 1")


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


def validate_bars(bars: list[Bar]) -> None:
    for i, b in enumerate(bars):
        values = (b.open, b.high, b.low, b.close, b.volume)
        if any(not math.isfinite(x) for x in values):
            raise ValueError(f"{b.date}: nonfinite OHLCV")
        if min(values[:4]) <= 0 or b.volume < 0:
            raise ValueError(f"{b.date}: price must be positive / volume nonnegative")
        if b.high < max(b.open, b.close, b.low) or b.low > min(b.open, b.close):
            raise ValueError(f"{b.date}: inconsistent OHLC")
        if i and b.date <= bars[i - 1].date:
            raise ValueError(f"{b.date}: dates must be unique and increasing")


def parse_date(value: str) -> date:
    s = value.strip()
    if len(s) == 8 and s.isdigit():
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return date.fromisoformat(s)


def load_csv_files(paths: Iterable[str]) -> dict[str, list[Bar]]:
    groups: dict[str, list[Bar]] = {}
    for filename in paths:
        path = Path(filename)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            names = {s.strip().lower(): s for s in (reader.fieldnames or [])}
            required = ("date", "open", "high", "low", "close", "volume")
            if any(s not in names for s in required):
                raise ValueError(f"{path}: required columns: {','.join(required)}")
            for row_no, row in enumerate(reader, 2):
                try:
                    symbol = row[names["symbol"]].strip() if "symbol" in names else path.stem
                    if not symbol:
                        raise ValueError("empty symbol")
                    vals = [float(row[names[k]]) for k in required[1:]]
                    b = Bar(parse_date(row[names["date"]]), *vals)
                    groups.setdefault(symbol, []).append(b)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError(f"{path}:{row_no}: {exc}") from exc
    if not groups:
        raise ValueError("input contains no bars")
    for symbol, bars in groups.items():
        bars.sort(key=lambda b: b.date)
        try:
            validate_bars(bars)
        except ValueError as exc:
            raise ValueError(f"{symbol}: {exc}") from exc
    return groups


def load_benchmark(path: str | None) -> dict[date, float]:
    if not path:
        return {}
    result: dict[date, float] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        names = {s.strip().lower(): s for s in (reader.fieldnames or [])}
        if not {"date", "close"}.issubset(names):
            raise ValueError("benchmark requires date,close")
        for row in reader:
            d, c = parse_date(row[names["date"]]), float(row[names["close"]])
            if d in result or not math.isfinite(c) or c <= 0:
                raise ValueError(f"invalid/duplicate benchmark row: {d}")
            result[d] = c
    return result


def mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def ratio(a: float | None, b: float | None) -> float | None:
    return a / b if a is not None and b is not None and b > 0 else None


def clip(x: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, x))


def slope(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    xm, ym = (len(xs) - 1) / 2, statistics.fmean(xs)
    return sum((i - xm) * (y - ym) for i, y in enumerate(xs)) / sum(
        (i - xm) ** 2 for i in range(len(xs)))


def midpoint_pass(cup_high: float, cup_low: float,
                  handle_high: float, handle_low: float) -> bool:
    return handle_high + handle_low > cup_high + cup_low


def swing_highs(bars: list[Bar], span: int) -> list[int]:
    # i is NOT known until i+span. Callers must enforce that confirmation date.
    return [i for i in range(span, len(bars) - span)
            if bars[i].high > max(b.high for b in bars[i - span:i])
            and bars[i].high >= max(b.high for b in bars[i + 1:i + span + 1])]


class Context:
    def __init__(self, bars: list[Bar], cfg: Config,
                 benchmark: dict[date, float] | None = None):
        validate_bars(bars)
        cfg.validate()
        self.bars, self.cfg, self.benchmark = bars, cfg, benchmark or {}
        self.dates = [b.date for b in bars]
        self.left_peaks = swing_highs(bars, cfg.left_peak_span)
        self.right_peaks = swing_highs(bars, cfg.right_peak_span)
        self.sma50: list[float | None] = []
        self.ntr: list[float] = []
        for i, b in enumerate(bars):
            self.sma50.append(mean([x.close for x in bars[i - 49:i + 1]]) if i >= 49 else None)
            prev = bars[i - 1].close if i else b.open
            tr = max(b.high - b.low, abs(b.high - prev), abs(b.low - prev))
            self.ntr.append(tr / prev)


def prior_uptrend(ctx: Context, left: int) -> dict[str, Any]:
    cfg, bars = ctx.cfg, ctx.bars
    lo, hi = max(0, left - cfg.prior_lookback), left - cfg.prior_min_sessions
    if hi < lo:
        return {"advance": None, "start": None, "slope": None, "source": "unknown"}
    # Recent qualifying confirmed swing low; earliest local window low is fallback.
    troughs = [i for i in range(lo + 2, hi + 1)
               if i + 2 <= left and bars[i].low <= min(b.low for b in bars[i - 2:i])
               and bars[i].low < min(b.low for b in bars[i + 1:i + 3])]
    fallback = min(range(lo, hi + 1), key=lambda i: bars[i].low)
    qualified = [i for i in troughs
                 if bars[left].high / bars[i].low - 1 >= cfg.prior_min_advance]
    start = max(qualified) if qualified else fallback
    return {"advance": bars[left].high / bars[start].low - 1,
            "start": start,
            "slope": slope([math.log(b.close) for b in bars[start:left + 1]]),
            "source": "confirmed_swing_low" if qualified else "window_low_fallback"}


def shape_features(bars: list[Bar], left: int, bottom: int, right: int,
                   top: float, low: float, cfg: Config) -> dict[str, Any]:
    section = bars[left:right + 1]
    height = top - low
    cutoff = low + cfg.bottom_zone_fraction * height
    occupancy = sum(b.close <= cutoff for b in section) / len(section)
    position = (bottom - left) / (right - left)
    down = slope([math.log(b.close) for b in bars[left:bottom + 1]])
    up = slope([math.log(b.close) for b in bars[bottom:right + 1]])
    # Prominent intervening rally between two low zones => W-like ambiguity.
    before, after = [], [0.0] * len(section)
    running = math.inf
    for b in section:
        running = min(running, b.low)
        before.append(running)
    running = math.inf
    for j in range(len(section) - 1, -1, -1):
        running = min(running, section[j].low)
        after[j] = running
    double_bottom = any(
        before[j - 1] <= low + 0.25 * height
        and after[j + 1] <= low + 0.25 * height
        and (section[j].high - max(before[j - 1], after[j + 1])) / height >= 0.50
        for j in range(3, len(section) - 3))
    dwell = clip(occupancy / 0.20)
    location = clip(min(position, 1 - position) / 0.20)
    direction = 0.5 * float(down < 0) + 0.5 * float(up > 0)
    roundness = 0.60 * dwell + 0.20 * location + 0.20 * direction
    return {"bottom_occupancy": occupancy, "bottom_time_position": position,
            "left_log_slope": down, "right_log_slope": up,
            "roundness_score": roundness, "prominent_double_bottom": double_bottom}


def rule(name: str, passed: bool | None, value: Any, threshold: Any,
         origin: str) -> dict[str, Any]:
    return {"name": name, "status": "unknown" if passed is None else ("pass" if passed else "fail"),
            "value": value, "threshold": threshold, "origin": origin}


def evaluate_structure(ctx: Context, symbol: str, left: int, right: int,
                       end: int) -> dict[str, Any] | None:
    bars, cfg = ctx.bars, ctx.cfg
    if not 0 <= left < right < end < len(bars):
        return None
    if right - left < 2:
        return None
    if left + cfg.left_peak_span > end or right + cfg.right_peak_span > end:
        return None
    starts = [i for i in range(right + 1, min(end, right + cfg.handle_start_grace) + 1)
              if bars[i].close < bars[i - 1].close]
    if not starts:
        return None
    hs = starts[0]
    handle = bars[hs:end + 1]
    ref = bars[right:end + 1]
    cup = bars[left:right + 1]
    top = max(b.high for b in cup)
    bottom = min(range(left + 1, right), key=lambda i: bars[i].low)
    low = bars[bottom].low
    if top <= low or min(b.low for b in cup) < low:
        return None
    hh, hl = max(b.high for b in ref), min(b.low for b in ref)
    # A crossing after this right-rim anchor is already a price event; do not
    # silently raise its pivot. A later confirmed right-rim may generate a new ID.
    if any(b.high > bars[right].high for b in bars[right + 1:end + 1]):
        return None
    depth, hd = (top - low) / top, (hh - hl) / hh
    elapsed = (bars[end].date - bars[left].date).days
    recovery = (bars[right].high - low) / (bars[left].high - low)
    prior = prior_uptrend(ctx, left)
    shape = shape_features(bars, left, bottom, right, top, low, cfg)
    pre = bars[max(0, hs - cfg.handle_volume_pre_sessions):hs]
    vols = [b.volume for b in handle]
    pv = [b.volume for b in pre]
    enough_pre = len(pre) >= cfg.handle_volume_pre_min_sessions
    hv = ratio(mean(vols), mean(pv)) if enough_pre else None
    hvm = ratio(statistics.median(vols), statistics.median(pv)) if enough_pre else None
    hvol = ratio(statistics.median(ctx.ntr[hs:end + 1]),
                 statistics.median(ctx.ntr[max(0, hs - cfg.handle_volume_pre_sessions):hs])) if enough_pre else None
    early = handle[:max(2, math.ceil(len(handle) * 0.70))]
    handle_slope = slope([math.log(b.close) for b in early])
    low_slope = slope([math.log(b.low) for b in early])
    wedging = handle_slope > 0 and low_slope > 0
    available_ma = [i for i in range(hs, end + 1) if ctx.sma50[i] is not None]
    above50 = (sum(bars[i].close > ctx.sma50[i] for i in available_ma) / len(available_ma)
               if len(available_ma) == len(handle) else None)
    upv = [bars[i].volume for i in range(bottom + 1, right + 1)
           if bars[i].close > bars[i - 1].close]
    dnv = [bars[i].volume for i in range(bottom + 1, right + 1)
           if bars[i].close < bars[i - 1].close]
    ud_sum, ud_mean = ratio(sum(upv), sum(dnv)), ratio(mean(upv), mean(dnv))
    recent = bars[max(0, end - 49):end + 1]
    zero_fraction = sum(b.volume == 0 for b in recent) / len(recent)
    turnover = statistics.median([b.close * b.volume for b in recent])
    rs_window = bars[max(0, end - cfg.rs_high_window + 1):end + 1]
    rs_values = [b.close / ctx.benchmark[b.date] for b in rs_window if b.date in ctx.benchmark]
    rs = (bars[end].close / ctx.benchmark[bars[end].date]
          if bars[end].date in ctx.benchmark else None)
    rs_high_ratio = ratio(rs, max(rs_values)) if len(rs_values) >= cfg.rs_min_sessions else None
    market_values = [ctx.benchmark[d] for d in sorted(ctx.benchmark) if d <= bars[end].date]
    market_up = None
    if bars[end].date in ctx.benchmark and len(market_values) >= 60:
        market_up = (market_values[-1] > statistics.fmean(market_values[-50:])
                     and statistics.fmean(market_values[-50:]) > statistics.fmean(market_values[-60:-10]))
    required = [
        rule("prior_advance", None if prior["advance"] is None else prior["advance"] >= cfg.prior_min_advance,
             prior["advance"], cfg.prior_min_advance, "IBD criterion; swing selection heuristic"),
        rule("base_calendar_duration", cfg.base_min_calendar_days <= elapsed <= cfg.base_max_calendar_days,
             elapsed, [cfg.base_min_calendar_days, cfg.base_max_calendar_days], "IBD duration; elapsed-calendar policy"),
        rule("cup_sessions", len(cup) >= cfg.cup_min_sessions, len(cup), cfg.cup_min_sessions, "implementation"),
        rule("cup_depth", cfg.cup_min_depth <= depth <= cfg.cup_max_depth,
             depth, [cfg.cup_min_depth, cfg.cup_max_depth], "IBD normal range / explicit profile"),
        rule("handle_sessions", cfg.handle_min_sessions <= len(handle) <= cfg.handle_max_sessions,
             len(handle), [cfg.handle_min_sessions, cfg.handle_max_sessions], "IBD minimum; implementation maximum"),
        rule("handle_depth", 0 < hd <= cfg.handle_max_depth and hd < depth,
             hd, {"maximum": cfg.handle_max_depth, "less_than_cup_depth": True}, "IBD normal range"),
        rule("handle_midpoint", midpoint_pass(top, low, hh, hl), (hh + hl) / 2,
             {"greater_than": (top + low) / 2}, "IBD midpoint test"),
        rule("cup_floor_intact", hl > low, hl, {"greater_than": low}, "structure"),
        rule("recovery", recovery >= cfg.min_recovery_ratio, recovery, cfg.min_recovery_ratio, "implementation"),
        rule("right_rim_overshoot", bars[right].high / bars[left].high - 1 <= cfg.max_right_rim_overshoot,
             bars[right].high / bars[left].high - 1, cfg.max_right_rim_overshoot, "implementation"),
        rule("roundness", shape["roundness_score"] >= cfg.min_roundness_score,
             shape["roundness_score"], cfg.min_roundness_score, "implementation"),
        rule("not_prominent_W", not (cfg.reject_prominent_double_bottom and shape["prominent_double_bottom"]),
             shape["prominent_double_bottom"], False, "implementation"),
        rule("zero_volume_fraction", zero_fraction <= cfg.max_zero_volume_fraction,
             zero_fraction, cfg.max_zero_volume_fraction, "data quality policy"),
        rule("median_turnover", turnover >= cfg.min_median_turnover,
             turnover, cfg.min_median_turnover, "execution policy"),
    ]
    valid = all(r["status"] == "pass" for r in required)
    observations = [
        rule("handle_volume_contracts", None if hv is None else hv < 1, hv, "< 1", "IBD qualitative; implementation measurement"),
        rule("handle_volatility_contracts", None if hvol is None else hvol < 1, hvol, "< 1", "implementation"),
        rule("handle_above50", None if above50 is None else above50 >= 0.8, above50, 0.8, "IBD location; implementation fraction"),
        rule("no_upward_wedge", not wedging, wedging, False, "IBD qualitative; implementation measurement"),
        rule("RS_near_high", None if rs_high_ratio is None else rs_high_ratio >= 0.95,
             rs_high_ratio, 0.95, "implementation, not RS Rating"),
        rule("market_SMA50_filter", market_up, market_up, True, "implementation, not IBD market status"),
    ]
    handle_quality = (clip(1 - hd / cfg.handle_max_depth) * 0.3
                      + clip(((hh + hl) / 2 - (top + low) / 2) / ((top - low) / 2)) * 0.4
                      + (0 if wedging else 1) * 0.3)
    components = [
        ("prior_trend", 10, clip((prior["advance"] or 0) / 0.6) if prior["advance"] is not None else None),
        ("cup_shape", 20, shape["roundness_score"] * (0.3 if shape["prominent_double_bottom"] else 1)),
        ("cup_recovery", 10, clip(recovery)),
        ("handle_structure", 20, handle_quality),
        ("volume_contraction", 10, clip((1 - hv) / 0.4) if hv is not None else None),
        ("volatility_contraction", 10, clip((1 - hvol) / 0.4) if hvol is not None else None),
        ("relative_strength", 10, clip((rs_high_ratio - 0.8) / 0.2) if rs_high_ratio is not None else None),
        ("market_filter", 10, float(market_up) if market_up is not None else None),
    ]
    weight = sum(w for _, w, value in components if value is not None)
    score = 100 * sum(w * value for _, w, value in components if value is not None) / weight
    warnings = [r["name"] + ":" + r["status"] for r in observations if r["status"] != "pass"]
    warnings.append("base_stage:unknown; previous-base 20% alternative not implemented")
    if prior["source"] == "window_low_fallback":
        warnings.append("prior_start:window_low_fallback; verify chart")
    if len(recent) < 50:
        warnings.append("liquidity_window:partial")
    if cfg.profile == "deep":
        warnings.append("deep_profile:manually verify bear-market context")
    return {
        "symbol": symbol, "pattern_id": f"{symbol}:{bars[left].date}:{bars[right].date}",
        "pattern_type": "cup_with_handle", "rule_version": RULE_VERSION, "profile": cfg.profile,
        "as_of": str(bars[end].date), "state": "READY" if valid else "REJECTED",
        "left_peak_date": str(bars[left].date), "left_peak_confirmed_date": str(bars[left + cfg.left_peak_span].date),
        "bottom_date": str(bars[bottom].date), "right_peak_date": str(bars[right].date),
        "right_peak_confirmed_date": str(bars[right + cfg.right_peak_span].date),
        "handle_start_date": str(bars[hs].date), "prior_start_date": str(bars[prior["start"]].date) if prior["start"] is not None else None,
        "base_calendar_days": elapsed, "base_weeks": elapsed / 7, "base_sessions": end - left + 1,
        "cup_sessions": len(cup), "handle_sessions": len(handle),
        "cup_high": top, "cup_low": low, "cup_depth": depth,
        "cup_midpoint": (top + low) / 2, "handle_high": hh, "handle_low": hl,
        "handle_depth": hd, "handle_midpoint": (hh + hl) / 2,
        "entire_handle_above_midpoint": hl > (top + low) / 2,
        "prior_advance": prior["advance"], "prior_log_slope": prior["slope"],
        "recovery_ratio": recovery, "rim_gap": bars[right].high / bars[left].high - 1,
        **shape, "handle_early_log_slope": handle_slope, "upward_wedge_risk": wedging,
        "handle_volume_ratio": hv, "handle_median_volume_ratio": hvm,
        "handle_volatility_ratio": hvol, "handle_above50_fraction": above50,
        "right_up_down_volume_sum_ratio": ud_sum, "right_up_down_volume_mean_ratio": ud_mean,
        "median_turnover50": turnover, "zero_volume_fraction50": zero_fraction,
        "rs_line": rs, "rs_high_ratio": rs_high_ratio, "market_up_filter": market_up,
        "base_stage": "unknown", "pivot_price": hh, "structure_valid": valid,
        "quality_score": round(score, 2), "score_coverage": weight / 100,
        "score_components": [{"name": n, "weight": w, "value": v} for n, w, v in components],
        "required_rules": required, "quality_observations": observations,
        "rejection_reasons": [r["name"] for r in required if r["status"] != "pass"],
        "warnings": warnings,
        "_indices": {"left": left, "bottom": bottom, "right": right, "handle": hs, "end": end},
    }


def detect_candidates(ctx: Context, symbol: str, end: int,
                      include_rejected: bool = False, deduplicate: bool = True) -> list[dict[str, Any]]:
    cfg = ctx.cfg
    if end < 0:
        return []
    earliest = ctx.bars[end].date - timedelta(days=cfg.base_max_calendar_days)
    first_left = bisect.bisect_left(ctx.dates, earliest)
    lefts = [i for i in ctx.left_peaks if first_left <= i and i + cfg.left_peak_span <= end]
    rights = [i for i in ctx.right_peaks
              if max(0, end - cfg.handle_max_sessions - cfg.handle_start_grace) <= i
              and i + cfg.right_peak_span <= end]
    results = []
    for right in rights:
        for left in lefts:
            if right - left + 1 < cfg.cup_min_sessions:
                continue
            candidate = evaluate_structure(ctx, symbol, left, right, end)
            if candidate and (include_rejected or candidate["structure_valid"]):
                results.append(candidate)
    results.sort(key=lambda p: (p["structure_valid"], p["quality_score"], p["score_coverage"]), reverse=True)
    if not deduplicate:
        return results
    kept = []
    for p in results:
        # Same rim date and <=1% pivot difference: one representative.
        if any(p["right_peak_date"] == q["right_peak_date"]
               and abs(p["pivot_price"] / q["pivot_price"] - 1) <= 0.01 for q in kept):
            continue
        kept.append(p)
    return kept[:cfg.max_results_per_symbol]


def next_entry(pivot: float, tick: float | None = None,
               tick_table: list[list[float]] | None = None) -> float:
    if tick_table:
        # Try each band, including when the next price crosses a tick boundary.
        options = []
        p = Decimal(str(pivot))
        for j, (floor, step) in enumerate(tick_table):
            upper = tick_table[j + 1][0] if j + 1 < len(tick_table) else math.inf
            base, s = Decimal(str(floor)), Decimal(str(step))
            k = ((p - base) / s).to_integral_value(rounding=ROUND_FLOOR) + 1
            price = base + max(Decimal(0), k) * s
            if price > p and float(price) < upper:
                options.append(float(price))
        if not options:
            raise ValueError("tick table cannot price this pivot")
        return min(options)
    if tick is not None:
        if not math.isfinite(tick) or tick <= 0:
            raise ValueError("tick-size must be positive and finite")
        p, step = Decimal(str(pivot)), Decimal(str(tick))
        return float(((p / step).to_integral_value(rounding=ROUND_FLOOR) + 1) * step)
    return math.nextafter(pivot, math.inf)


def classify_breakout(ctx: Context, candidate: dict[str, Any], day: int,
                      tick: float | None = None, tick_table: list[list[float]] | None = None) -> dict[str, Any]:
    bars, cfg = ctx.bars, ctx.cfg
    if candidate["_indices"]["end"] >= day:
        raise ValueError("breakout must be checked AFTER the structure snapshot")
    b = bars[day]
    pivot = candidate["pivot_price"]
    entry = next_entry(pivot, tick, tick_table)
    previous = [x.volume for x in bars[max(0, day - cfg.breakout_volume_sessions):day]]
    avg = mean(previous) if len(previous) == cfg.breakout_volume_sessions else None
    rvol = ratio(b.volume, avg)
    crossed = b.high >= entry
    closed = b.close >= entry
    extension = b.close / entry - 1
    volume_ok = rvol is not None and rvol >= cfg.breakout_rvol_min
    inside = 0 <= extension <= cfg.buy_zone_max
    floor_broken = b.low <= candidate["cup_low"]
    if floor_broken:
        state = "INVALIDATED"
    elif not crossed:
        state = "READY"
    elif extension > cfg.buy_zone_max:
        state = "EXTENDED"
    elif volume_ok and closed:
        state = "BREAKOUT_CONFIRMED"
    elif volume_ok:
        state = "VOLUME_CONFIRMED_CLOSE_FAILED"
    else:
        state = "PRICE_BREAKOUT"
    return {"event_date": str(b.date), "state": state, "pivot_price": pivot,
            "entry_price": entry, "entry_policy": "tick_table" if tick_table else ("fixed_tick" if tick else "strictly_above_pivot_not_an_order_tick"),
            "price_crossed": crossed, "close_confirmed": closed,
            "volume_confirmed": volume_ok, "breakout_volume_status": "unknown" if rvol is None else ("pass" if volume_ok else "fail"),
            "previous_average_volume": avg, "breakout_rvol": rvol,
            "close_location": (b.close - b.low) / (b.high - b.low) if b.high > b.low else None,
            "extension": extension, "within_buy_zone": inside,
            "gap_open_extension": b.open / entry - 1, "cup_floor_broken": floor_broken,
            "same_bar_order_unknown": floor_broken and crossed,
            "reference_close": b.close}


def latest_scan(ctx: Context, symbol: str, end: int, tick: float | None = None,
                tick_table: list[list[float]] | None = None,
                include_rejected: bool = False) -> list[dict[str, Any]]:
    snapshots = detect_candidates(ctx, symbol, end, include_rejected)
    # Detect today's event from YESTERDAY's mature candidates, not today's high.
    if end > 0:
        for p in detect_candidates(ctx, symbol, end - 1):
            event = classify_breakout(ctx, p, end, tick, tick_table)
            if event["price_crossed"] or event["cup_floor_broken"]:
                q = dict(p)
                q.update(event)
                q["structure_as_of"] = p["as_of"]
                q["as_of"] = str(ctx.bars[end].date)
                snapshots.append(q)
    for p in snapshots:
        if "entry_price" not in p:
            p["entry_price"] = next_entry(p["pivot_price"], tick, tick_table)
            p["distance_to_entry"] = p["entry_price"] / ctx.bars[end].close - 1
    snapshots.sort(key=lambda p: (p["structure_valid"], p["quality_score"]), reverse=True)
    # A scan is a snapshot, not a full history: prior breakout events require replay.
    return snapshots


def replay_symbol(ctx: Context, symbol: str, end: int, tick: float | None = None,
                  tick_table: list[list[float]] | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    ready_previous: dict[str, dict[str, Any]] = {}
    seen_ready: set[str] = set()
    completed: set[str] = set()
    for day in range(end + 1):
        for ident, p in ready_previous.items():
            if ident in completed:
                continue
            signal = classify_breakout(ctx, p, day, tick, tick_table)
            if signal["price_crossed"] or signal["cup_floor_broken"]:
                q = dict(p)
                q.update(signal)
                q["structure_as_of"] = p["as_of"]
                q["as_of"] = str(ctx.bars[day].date)
                q["event_kind"] = "BREAKOUT_ATTEMPT" if signal["price_crossed"] else "INVALIDATED"
                events.append(q)
                completed.add(ident)
        current = {p["pattern_id"]: p for p in detect_candidates(ctx, symbol, day, deduplicate=False)
                   if p["pattern_id"] not in completed}
        for ident, p in current.items():
            if ident not in seen_ready:
                q = dict(p)
                q["event_kind"] = "FIRST_READY"
                q["event_date"] = p["as_of"]
                events.append(q)
                seen_ready.add(ident)
        for ident, p in ready_previous.items():
            if ident not in current and ident not in completed:
                q = dict(p)
                q.update({"event_kind": "STRUCTURE_LOST", "state": "INVALIDATED",
                          "event_date": str(ctx.bars[day].date), "as_of": str(ctx.bars[day].date),
                          "structure_as_of": p["as_of"],
                          "invalidation_reason": "candidate expired or structure/rule no longer valid"})
                events.append(q)
                # A lost structure needs a NEW anchor/ID for a fresh lifecycle.
                completed.add(ident)
        ready_previous = current
    return events


def evaluate_outcomes(ctx: Context, events: list[dict[str, Any]], end: int) -> None:
    for event in events:
        if event.get("event_kind") != "BREAKOUT_ATTEMPT":
            continue
        i = bisect.bisect_left(ctx.dates, parse_date(event["event_date"]))
        ref = ctx.bars[i].close
        observations = {}
        for horizon in (5, 20, 60):
            stop = min(i + horizon, end)
            future = ctx.bars[i + 1:stop + 1]
            observations[str(horizon)] = {
                "available_sessions": len(future), "complete": len(future) == horizon,
                "close_return": future[-1].close / ref - 1 if future else None,
                "mfe": max(b.high / ref - 1 for b in future) if future else None,
                "mae": min(b.low / ref - 1 for b in future) if future else None,
                "reentered_below_pivot": any(b.close < event["pivot_price"] for b in future) if future else None,
            }
        event["posthoc_outcomes"] = observations
        event["outcome_reference"] = "signal close; observations only, no assumed execution/PnL"


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def dump_json(path: str | None, payload: Any) -> None:
    content = json.dumps(clean(payload), ensure_ascii=False, indent=2, allow_nan=False)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)


def write_summary(path: str, results: list[dict[str, Any]]) -> None:
    names = ["symbol", "pattern_id", "as_of", "state", "quality_score", "score_coverage",
             "left_peak_date", "bottom_date", "handle_start_date", "cup_depth", "handle_depth",
             "handle_sessions", "pivot_price", "entry_price", "breakout_rvol", "warnings"]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        for p in results:
            writer.writerow({k: json.dumps(p.get(k), ensure_ascii=False) if isinstance(p.get(k), (list, dict))
                             else p.get(k) for k in names})


def chart_svg(ctx: Context, p: dict[str, Any], output: Path) -> None:
    idx = p["_indices"]
    end = bisect.bisect_left(ctx.dates, parse_date(p["as_of"]))
    start = max(0, idx["left"] - 15)
    bars = ctx.bars[start:end + 1]
    w, h, pad = 1100, 600, 55
    ymin, ymax = min(b.low for b in bars), max(b.high for b in bars)
    span = max(ymax - ymin, ymax * 0.01)
    def x(i: int) -> float:
        return pad + (i - start) / max(1, len(bars) - 1) * (w - 2 * pad)
    def y(v: float) -> float:
        return 410 - (v - ymin) / span * 330
    esc = lambda s: html.escape(str(s), quote=True)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" fill="#101827"/>',
             f'<text x="55" y="30" fill="white" font-family="sans-serif" font-size="18">{esc(p["symbol"])} · {esc(p["state"])} · quality {p["quality_score"]} / coverage {p["score_coverage"]:.0%}</text>',
             f'<rect x="{x(idx["handle"]):.2f}" y="65" width="{max(1, x(end)-x(idx["handle"])):.2f}" height="360" fill="#223a48"/>']
    maxvol = max((b.volume for b in bars), default=1) or 1
    for i in range(start, end + 1):
        b = ctx.bars[i]
        color = "#55d8b4" if b.close >= b.open else "#ff8290"
        parts.append(f'<line x1="{x(i):.2f}" x2="{x(i):.2f}" y1="{y(b.high):.2f}" y2="{y(b.low):.2f}" stroke="{color}"/>')
        parts.append(f'<line x1="{x(i):.2f}" x2="{x(i):.2f}" y1="{y(b.open):.2f}" y2="{y(b.close):.2f}" stroke="{color}" stroke-width="3"/>')
        vh = b.volume / maxvol * 100
        parts.append(f'<rect x="{x(i)-1.5:.2f}" y="{540-vh:.2f}" width="3" height="{vh:.2f}" fill="{color}"/>')
    for label, price in (("pivot", p["pivot_price"]), ("cup midpoint", p["cup_midpoint"])):
        parts.append(f'<line x1="55" x2="1045" y1="{y(price):.2f}" y2="{y(price):.2f}" stroke="#f0c76c" stroke-dasharray="6 4"/>')
        parts.append(f'<text x="60" y="{y(price)-5:.2f}" fill="#f0c76c" font-size="12">{label}: {price:.4f}</text>')
    for label, i in (("L", idx["left"]), ("B", idx["bottom"]), ("R", idx["right"])):
        parts.append(f'<text x="{x(i):.2f}" y="{y(ctx.bars[i].high)-12:.2f}" fill="white" font-size="14">{label}</text>')
    parts.append(f'<text x="55" y="575" fill="#b6c4d8" font-size="13">{bars[0].date} → {bars[-1].date} | green/red OHLC; lower bars: volume | shaded: handle</text></svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def synthetic_bars() -> list[Bar]:
    values: list[tuple[float, float]] = []
    values += [(60 + 40 * i / 79, 1_000_000) for i in range(80)]
    values += [(100 - 25 * i / 20, 900_000) for i in range(1, 21)]
    values += [(75 + 0.25 * (1 + math.sin(i)), 650_000) for i in range(12)]
    values += [(75.3 + (98 - 75.3) * i / 25, 1_200_000) for i in range(1, 26)]
    values += [(v, 450_000) for v in (97, 96, 94.8, 94, 93.8, 94.2, 94.8, 95.8)]
    result, d = [], date(2024, 1, 2)
    for c, v in values:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        result.append(Bar(d, c - 0.12, c + 0.25, c - 0.45, c, v))
        d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    result.append(Bar(d, 97.2, 100.0, 96.9, 99.1, 2_000_000))
    for j in range(1, 7):
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        c = 99.1 + j * 1.5
        result.append(Bar(d, c - 0.4, c + 0.3, c - 0.6, c, 1_100_000))
    return result


def create_demo(directory: str) -> None:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    bars = synthetic_bars()
    with (target / "DEMO.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["date", "open", "high", "low", "close", "volume", "symbol"])
        for b in bars:
            writer.writerow([b.date, b.open, b.high, b.low, b.close, b.volume, "DEMO"])
    dump_json(str(target / "config.json"), asdict(Config()))
    breakout = bars[-7].date
    print(f"Created {target / 'DEMO.csv'}", file=sys.stderr)
    print(f"READY example: --as-of {bars[-8].date}; BREAKOUT example: --as-of {breakout}", file=sys.stderr)


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = Config()
        self.bars = synthetic_bars()
        self.ctx = Context(self.bars, self.cfg)
        self.x = len(self.bars) - 7
        candidates = detect_candidates(self.ctx, "DEMO", self.x - 1)
        self.assertTrue(candidates, "synthetic normal cup must be discoverable")
        self.p = candidates[0]

    def test_midpoint_is_not_low_test(self):
        self.assertTrue(midpoint_pass(100, 88, 100, 90))
        self.assertLess(90, (100 + 88) / 2)
        self.assertFalse(midpoint_pass(100, 88, 99, 89))

    def test_shallow_handle_is_allowed(self):
        self.assertLess(self.p["handle_depth"], 0.08)
        self.assertTrue(self.p["structure_valid"])

    def test_volume_denominator_excludes_event(self):
        e = classify_breakout(self.ctx, self.p, self.x)
        expected = statistics.fmean(b.volume for b in self.bars[self.x - 50:self.x])
        self.assertEqual(e["previous_average_volume"], expected)
        self.assertAlmostEqual(e["breakout_rvol"], self.bars[self.x].volume / expected)

    def test_pivot_does_not_chase_breakout_high(self):
        e = classify_breakout(self.ctx, self.p, self.x)
        self.assertEqual(e["pivot_price"], self.p["pivot_price"])
        self.assertLess(e["pivot_price"], self.bars[self.x].high)
        self.assertEqual(e["state"], "BREAKOUT_CONFIRMED")

    def test_prefix_invariance(self):
        full = detect_candidates(self.ctx, "DEMO", self.x - 1)
        prefix = detect_candidates(Context(self.bars[:self.x], self.cfg), "DEMO", self.x - 1)
        self.assertEqual(clean(full), clean(prefix))

    def test_replay_future_prefix_invariance(self):
        past = replay_symbol(Context(self.bars[:self.x], self.cfg), "DEMO", self.x - 1)
        all_events = replay_symbol(self.ctx, "DEMO", len(self.bars) - 1)
        until = [e for e in all_events if parse_date(e["event_date"]) <= self.bars[self.x - 1].date]
        self.assertEqual(clean(past), clean(until))

    def test_no_same_bar_structure_signal(self):
        with self.assertRaises(ValueError):
            classify_breakout(self.ctx, self.p, self.x - 1)

    def test_weak_volume_still_emits_price_event(self):
        bs = list(self.bars)
        bs[self.x] = replace(bs[self.x], volume=100_000)
        e = classify_breakout(Context(bs, self.cfg), self.p, self.x)
        self.assertEqual(e["state"], "PRICE_BREAKOUT")
        self.assertFalse(e["volume_confirmed"])

    def test_intraday_cross_close_failure(self):
        bs = list(self.bars)
        bs[self.x] = replace(bs[self.x], close=97.5)
        e = classify_breakout(Context(bs, self.cfg), self.p, self.x)
        self.assertTrue(e["price_crossed"])
        self.assertFalse(e["close_confirmed"])
        self.assertEqual(e["state"], "VOLUME_CONFIRMED_CLOSE_FAILED")

    def test_explicit_tick_and_boundary(self):
        self.assertEqual(next_entry(98.25, 0.01), 98.26)
        self.assertEqual(next_entry(98.251, 0.01), 98.26)
        self.assertEqual(next_entry(1999, tick_table=[[0, 1], [2000, 5]]), 2000)
        self.assertEqual(next_entry(2000, tick_table=[[0, 1], [2000, 5]]), 2005)

    def test_handle_minimum(self):
        idx = self.p["_indices"]
        short = evaluate_structure(self.ctx, "DEMO", idx["left"], idx["right"], idx["handle"] + 3)
        self.assertIsNotNone(short)
        self.assertIn("handle_sessions", short["rejection_reasons"])

    def test_deep_handle_rejected(self):
        bs = list(self.bars)
        j = self.p["_indices"]["handle"] + 2
        bs[j] = replace(bs[j], low=82)
        ctx = Context(bs, self.cfg)
        idx = self.p["_indices"]
        p = evaluate_structure(ctx, "DEMO", idx["left"], idx["right"], self.x - 1)
        self.assertIn("handle_depth", p["rejection_reasons"])

    def test_floor_and_cross_same_day_order_unknown(self):
        bs = list(self.bars)
        bs[self.x] = replace(bs[self.x], low=70)
        e = classify_breakout(Context(bs, self.cfg), self.p, self.x)
        self.assertEqual(e["state"], "INVALIDATED")
        self.assertTrue(e["same_bar_order_unknown"])

    def test_unknown_RS_not_fabricated(self):
        self.assertIsNone(self.p["rs_high_ratio"])
        self.assertEqual(self.p["score_coverage"], 0.8)
        self.assertEqual(self.p["base_stage"], "unknown")

    def test_invalid_data_rejected(self):
        with self.assertRaises(ValueError):
            Context([replace(self.bars[0], close=math.nan)], self.cfg)
        with self.assertRaises(ValueError):
            Context([replace(self.bars[0], low=self.bars[0].high + 1)], self.cfg)
        with self.assertRaises(ValueError):
            Context([self.bars[0], self.bars[0]], self.cfg)

    def test_future_benchmark_does_not_change_history(self):
        past = {b.date: 1000 + i for i, b in enumerate(self.bars[:self.x])}
        future = dict(past)
        future[self.bars[-1].date] = 1
        a = detect_candidates(Context(self.bars, self.cfg, past), "DEMO", self.x - 1)
        b = detect_candidates(Context(self.bars, self.cfg, future), "DEMO", self.x - 1)
        self.assertEqual(clean(a), clean(b))

    def test_extended_and_censored_outcomes(self):
        bs = list(self.bars)
        bs[self.x] = replace(bs[self.x], high=111, close=110)
        e = classify_breakout(Context(bs, self.cfg), self.p, self.x)
        self.assertEqual(e["state"], "EXTENDED")
        events = replay_symbol(self.ctx, "DEMO", self.x)
        evaluate_outcomes(self.ctx, events, self.x)
        breakout = next(x for x in events if x["event_kind"] == "BREAKOUT_ATTEMPT")
        self.assertFalse(breakout["posthoc_outcomes"]["20"]["complete"])
        self.assertIsNone(breakout["posthoc_outcomes"]["20"]["mfe"])

    def test_narrow_V_roundness_penalty(self):
        # A one-session crash/rebound around the middle must not get a U score
        # from direction + centered-bottom position alone.
        prices = [95.0] * 29 + [90.0, 75.0, 90.0] + [95.0] * 29
        bs = [Bar(date(2024, 1, 1) + timedelta(days=i), c, c + 0.1,
                  c - 0.1, c, 100) for i, c in enumerate(prices)]
        features = shape_features(bs, 0, 30, len(bs) - 1, 100, 74.9, self.cfg)
        self.assertLess(features["roundness_score"], self.cfg.min_roundness_score)

    def test_prominent_W_flag(self):
        prices = ([100 - i * 2.5 for i in range(11)]
                  + [75 + i * 2 for i in range(1, 11)]
                  + [95 - i * 2 for i in range(1, 11)]
                  + [75 + i * 2.3 for i in range(1, 11)])
        bs = [Bar(date(2024, 1, 1) + timedelta(days=i), c, c + 0.1,
                  c - 0.1, c, 100) for i, c in enumerate(prices)]
        features = shape_features(bs, 0, 10, len(bs) - 1, 100.1, 74.9, self.cfg)
        self.assertTrue(features["prominent_double_bottom"])

    def test_unknown_breakout_volume_when_history_short(self):
        cfg = replace(self.cfg, breakout_volume_sessions=500)
        e = classify_breakout(Context(self.bars, cfg), self.p, self.x)
        self.assertIsNone(e["breakout_rvol"])
        self.assertEqual(e["breakout_volume_status"], "unknown")

    def test_config_validation(self):
        for cfg in (replace(self.cfg, handle_min_sessions=0),
                    replace(self.cfg, cup_max_depth=math.nan),
                    replace(self.cfg, cup_min_depth=0.4),
                    replace(self.cfg, reject_prominent_double_bottom="false")):
            with self.assertRaises(ValueError):
                cfg.validate()

    def test_CSV_symbols_and_duplicate_detection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_text("Date,Open,High,Low,Close,Volume,Symbol\n"
                            "20240102,10,11,9,10,100,005930\n"
                            "20240103,10,11,9,10,100,000660\n", encoding="utf-8-sig")
            groups = load_csv_files([str(path)])
            self.assertEqual(set(groups), {"005930", "000660"})
            with path.open("a", encoding="utf-8") as f:
                f.write("20240102,10,11,9,10,100,005930\n")
            with self.assertRaises(ValueError):
                load_csv_files([str(path)])


def read_config(path: str | None, profile: str | None) -> Config:
    params: dict[str, Any] = {}
    if path:
        params = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(params, dict):
            raise ValueError("config must be a JSON object")
        unknown = set(params) - {f.name for f in fields(Config)}
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
    if profile:
        params["profile"] = profile
        # Explicit command-line profile changes depth defaults; custom file
        # without --profile keeps its own configured boundaries.
        params["cup_min_depth"] = 0.33 if profile == "deep" else 0.12
        params["cup_max_depth"] = 0.50 if profile == "deep" else 0.33
    cfg = Config(**params)
    cfg.validate()
    return cfg


def read_tick_table(path: str | None) -> list[list[float]] | None:
    if not path:
        return None
    table = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(table, list) or not table:
        raise ValueError("tick table must be a nonempty [[lower_bound,tick],...] list")
    previous = -1.0
    result = []
    for row in table:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("invalid tick table row")
        if any(type(v) not in (int, float) for v in row):
            raise ValueError("tick table values must be numeric")
        floor, step = map(float, row)
        if not math.isfinite(floor) or not math.isfinite(step) or floor < 0 or floor <= previous or step <= 0:
            raise ValueError("tick bands must increase; finite positive ticks required")
        previous = floor
        result.append([floor, step])
    if result[0][0] != 0:
        raise ValueError("first tick band must start at 0")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-file causal EOD cup-with-handle scanner. See module docstring.")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("self-test", help="Run deterministic correctness and look-ahead tests")
    demo = subs.add_parser("demo", help="Generate synthetic OHLCV (not real market data)")
    demo.add_argument("--directory", default="demo")
    config = subs.add_parser("config", help="Export editable defaults")
    config.add_argument("--output")
    for name in ("scan", "replay"):
        p = subs.add_parser(name)
        p.add_argument("--input", nargs="+", required=True, help="CSV file(s); quoted wildcard supported")
        p.add_argument("--config")
        p.add_argument("--profile", choices=["classic", "deep"])
        p.add_argument("--as-of", help="inclusive YYYY-MM-DD cutoff")
        p.add_argument("--benchmark", help="index date,close CSV")
        tick = p.add_mutually_exclusive_group()
        tick.add_argument("--tick-size", type=float)
        tick.add_argument("--tick-table", help="market-specific tick bands JSON")
        p.add_argument("--output", help="JSON output; omitted => stdout")
        p.add_argument("--summary", help="flat CSV output; ratios are decimal fractions")
        p.add_argument("--charts-dir", help="write SVG chart for each output row")
        if name == "scan":
            p.add_argument("--include-rejected", action="store_true")
        else:
            p.add_argument("--evaluate", action="store_true", help="append explicitly post-hoc horizon observations")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ScannerTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    try:
        if args.command == "demo":
            create_demo(args.directory)
            return 0
        if args.command == "config":
            dump_json(args.output, asdict(Config()))
            return 0
        cfg = read_config(args.config, args.profile)
        if args.tick_size is not None and (not math.isfinite(args.tick_size) or args.tick_size <= 0):
            raise ValueError("tick-size must be positive and finite")
        table = read_tick_table(args.tick_table)
        files = []
        for expression in args.input:
            found = sorted(glob.glob(expression))
            if not found:
                raise ValueError(f"no files match: {expression}")
            files.extend(found)
        files = list(dict.fromkeys(files))
        groups, benchmark = load_csv_files(files), load_benchmark(args.benchmark)
        cutoff = parse_date(args.as_of) if args.as_of else None
        results: list[dict[str, Any]] = []
        contexts: dict[str, Context] = {}
        diagnostics = []
        for symbol, original in sorted(groups.items()):
            bars = [b for b in original if cutoff is None or b.date <= cutoff]
            if not bars:
                diagnostics.append({"symbol": symbol, "status": "no_data_before_cutoff"})
                continue
            ctx = Context(bars, cfg, benchmark)
            contexts[symbol] = ctx
            end = len(bars) - 1
            if args.command == "scan":
                found = latest_scan(ctx, symbol, end, args.tick_size, table, args.include_rejected)
            else:
                found = replay_symbol(ctx, symbol, end, args.tick_size, table)
                if args.evaluate:
                    evaluate_outcomes(ctx, found, end)
            results.extend(found)
            diagnostics.append({"symbol": symbol, "sessions": len(bars), "as_of": str(bars[-1].date),
                                "output_rows": len(found), "status": "ok"})
        if args.charts_dir:
            for i, p in enumerate(results):
                safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in p["symbol"])
                output = Path(args.charts_dir) / f"{i:04d}_{safe}_{p['as_of']}.svg"
                chart_svg(contexts[p["symbol"]], p, output)
                p["chart_file"] = str(output)
        if args.summary:
            write_summary(args.summary, results)
        dump_json(args.output, {
            "rule_version": RULE_VERSION, "mode": args.command, "config": asdict(cfg),
            "ratios_are_decimal_fractions": True,
            "input_policy": "completed EOD bars; consistently adjusted OHLCV supplied by caller",
            "not_implemented": ["intraday volume", "automatic corporate actions", "automatic base stages",
                                "previous-base 20% alternative", "trade execution/PnL engine"],
            "diagnostics": diagnostics, "results": results})
        print(f"{args.command}: {len(contexts)} symbol(s), {len(results)} row(s)", file=sys.stderr)
        return 0
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
