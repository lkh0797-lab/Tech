import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 프로젝트 루트
"""사전 필터 검증: 표본 종목에서 필터 유무의 돌파 신호 집합이 같은지 확인."""
import sys, random
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
from chart_screener.backtest import BacktestConfig, run_backtest

PATTERNS = ["vcp", "cup_handle", "long_base_breakout", "flat_base", "double_bottom",
            "three_weeks_tight", "high_tight_flag", "pocket_pivot", "canslim"]

def one(p):
    from chart_screener.universe_data import load_universe_data
    ud = load_universe_data(offline=True, verbose=False)
    liquid = [c for c, d in ud.ohlcv.items() if len(d) > 300 and d["value"].iloc[-60:].mean() > 30e8]
    random.Random(11).shuffle(liquid)
    codes = liquid[:45]
    a = run_backtest(BacktestConfig(pattern=p, prefilter=False), workers=1, codes=codes)
    b = run_backtest(BacktestConfig(pattern=p, prefilter=True), workers=1, codes=codes)
    ka = set(zip(a.code, a.date)) if len(a) else set()
    kb = set(zip(b.code, b.date)) if len(b) else set()
    return p, len(ka), len(kb), sorted(ka - kb), sorted(kb - ka)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with ProcessPoolExecutor(max_workers=9) as ex:
        for p, na, nb, miss, extra in ex.map(one, PATTERNS):
            print(f"{p:<20} 필터없음 {na:>4}  필터 {nb:>4}  누락 {miss}  추가 {extra}", flush=True)
