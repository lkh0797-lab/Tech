import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 프로젝트 루트
"""전 패턴 워크포워드 백테스트 일괄 실행 → output/backtest_summary.md"""
import io, json, sys, time
import pandas as pd
from chart_screener.backtest import BacktestConfig, run_backtest, summarize

PATTERNS = ["long_base_breakout", "vcp", "cup_handle", "flat_base", "double_bottom",
            "three_weeks_tight", "high_tight_flag", "pocket_pivot", "canslim"]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out = []
    for p in PATTERNS:
        t = time.time()
        ev = run_backtest(BacktestConfig(pattern=p), workers=14)
        ev.to_csv(f"output/bt_{p}.csv", index=False, encoding="utf-8-sig")
        s = summarize(ev)
        oc = s.attrs.get("outcome", {})
        print(f"== {p}: {len(ev)} events, {time.time()-t:.0f}s", flush=True)
        print(s.to_string(index=False), flush=True)
        print(oc, flush=True)
        out.append({"pattern": p, "events": len(ev), "summary": s.to_dict("records"), "outcome": oc,
                    "first": ev["date"].min() if len(ev) else None, "last": ev["date"].max() if len(ev) else None})
        json.dump(out, open("output/backtest_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
