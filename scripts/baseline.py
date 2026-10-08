import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 프로젝트 루트
"""기준선: 같은 기간 유동성 필터 통과 종목-일의 무작위 진입 평균 수익률 (다음날 시가 진입)."""
import sys
import numpy as np, pandas as pd
from chart_screener.config import Config
from chart_screener.universe_data import load_universe_data
sys.stdout.reconfigure(encoding="utf-8")
cfg = Config()
ud = load_universe_data(cfg, offline=True, verbose=False)
first = min(d.index[0] for d in ud.ohlcv.values())
since = first + pd.tseries.offsets.BDay(260)
rows = {h: [] for h in (5, 20, 60)}
for code, df in ud.ohlcv.items():
    if len(df) < 300: continue
    o, c = df["open"].to_numpy(float), df["close"].to_numpy(float)
    v20 = df["value"].rolling(20).mean().to_numpy()
    ok = (np.arange(len(df)) >= 260) & (c >= cfg.universe.min_price) & (v20 >= cfg.universe.min_avg_value_20d)
    idx = np.where(ok)[0]
    idx = idx[idx + 1 < len(df)]
    for h in rows:
        j = idx + h
        m = j < len(df)
        e = o[idx[m] + 1]
        rows[h].append(c[j[m]] / np.where(e > 0, e, c[idx[m] + 1]) - 1)
print(f"기준선 (종목별 260봉 이후 = 백테스트와 같은 구간, 유동성 필터 통과 종목-일, 다음날 시가 진입)")
for h, parts in rows.items():
    r = np.concatenate(parts)
    print(f"  {h:>2}일: n={len(r):,}  평균 {r.mean()*100:+.2f}%  중앙 {np.median(r)*100:+.2f}%  승률 {(r>0).mean()*100:.1f}%")
