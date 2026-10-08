"""개발/보정용 하네스: 캐시된 전 종목에 탐지기 하나를 돌려 통계를 출력.

    python -m chart_screener.dev vcp --top 20
    python -m chart_screener.dev cup_handle --show 005930
    python -m chart_screener.dev base_breakout --stage breakout --no-filter

네트워크를 쓰지 않는다(--online 지정 시 제외). 먼저 한 번은 온라인으로 데이터를 받아 두어야 한다.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections import Counter

from .config import Config
from .patterns import REGISTRY
from .universe_data import build_context, iter_contexts, load_universe_data


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 1000 else f"{v:,.0f}"
    return str(v)


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", help=f"패턴 이름: {', '.join(REGISTRY)}")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--codes", default="", help="쉼표 구분 종목코드만")
    ap.add_argument("--no-filter", action="store_true", help="유동성 필터 끄기")
    ap.add_argument("--stage", default="", help="이 단계만 출력")
    ap.add_argument("--show", default="", help="한 종목 상세 결과(JSON)")
    ap.add_argument("--online", action="store_true")
    a = ap.parse_args(argv)

    if a.pattern not in REGISTRY:
        print(f"알 수 없는 패턴: {a.pattern}. 등록된 패턴: {list(REGISTRY)}")
        return 2
    label, fn = REGISTRY[a.pattern]
    cfg = Config()
    codes = [c for c in a.codes.split(",") if c] or None
    ud = load_universe_data(cfg, offline=not a.online, verbose=False)

    if a.show:
        ctx = build_context(a.show, ud, cfg)
        if ctx is None:
            print("데이터 없음")
            return 1
        print(json.dumps(fn(ctx).to_dict(), ensure_ascii=False, indent=2, default=str))
        return 0

    t0 = time.perf_counter()
    results = []
    total = 0
    for ctx in iter_contexts(ud, cfg, apply_filter=not a.no_filter):
        if codes and ctx.code not in codes:
            continue
        total += 1
        try:
            r = fn(ctx)
        except Exception as e:
            print(f"[오류] {ctx.code} {ctx.name}: {type(e).__name__}: {e}")
            raise
        results.append((ctx, r))
    dt = time.perf_counter() - t0

    det = [(c, r) for c, r in results if r.detected]
    print(f"[{a.pattern}] {label}: 대상 {total}종목, 탐지 {len(det)} ({len(det) / max(total, 1):.1%}), "
          f"{dt / max(total, 1) * 1000:.1f} ms/종목")
    print("단계별:", dict(Counter(r.stage for _, r in det)))
    if a.stage:
        det = [(c, r) for c, r in det if r.stage == a.stage]
    det.sort(key=lambda x: -x[1].score)
    for ctx, r in det[: a.top]:
        close = float(ctx.close.iloc[-1])
        dist = f"{close / r.pivot - 1:+.1%}" if r.pivot else "-"
        m = ", ".join(f"{k}={_fmt(v)}" for k, v in list(r.metrics.items())[:8])
        print(f"  {ctx.code} {ctx.name[:10]:<10} 점수 {r.score:5.1f} {r.stage_label:<6} "
              f"피벗 {r.pivot or 0:>10,.0f} 현재가 {close:>10,.0f} ({dist}) RS {ctx.rs_rating or 0:.0f} "
              f"{r.start_date}~{r.end_date} | {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
