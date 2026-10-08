"""명령줄 진입점.

    python -m chart_screener scan                 # 전 종목 스캔 → output/ 에 HTML·엑셀·CSV
    python -m chart_screener scan --offline       # 캐시만 사용 (네트워크 없이)
    python -m chart_screener analyze 005930       # 한 종목 모든 패턴 판정 상세
    python -m chart_screener market               # KOSPI/KOSDAQ 시장 방향
    python -m chart_screener backtest vcp         # 워크포워드 신호 성과 검증
    python -m chart_screener track                # 스캔 일지(output/journal.csv) 후보의 사후 성과 집계
    python -m chart_screener update               # 데이터만 갱신
    python -m chart_screener live                 # 실시간 감시: 후보 + 증권사(KIS)/네이버 시세 → 돌파·눌림·손절 알림
    python -m chart_screener live --check         # 한국투자증권 연결 점검 (설정·토큰·현재가·개장일·웹소켓)

live 는 조회 전용이다 — 주문(매수·매도) 기능이 없다.
"""
from __future__ import annotations

import argparse
import io
import sys
import webbrowser
from pathlib import Path

import pandas as pd

from .config import OUTPUT_DIR, Config


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        if isinstance(s, io.TextIOWrapper):
            s.reconfigure(encoding="utf-8")


def _print_market(ud) -> None:
    for m in ud.market.values():
        dd = f"분산일 {m.distribution_days}개" + (f" ({', '.join(m.dd_dates[-3:])})" if m.dd_dates else "")
        print(f"  {m.name:<6} {m.close:>10,.2f}  {m.label:<6}  {dd}  "
              f"50일선 {'위' if m.above_50sma else '아래'} · 200일선 {'위' if m.above_200sma else '아래'}  "
              f"{' / '.join(m.notes)}")


def _print_breadth(ud) -> None:
    b = getattr(ud, "breadth", None) or {}
    for k in ("KOSPI", "KOSDAQ"):
        x = b.get(k) or {}
        if not x or x.get("nh_nl_10d") is None:
            continue
        pct50 = x.get("pct_above_50")
        print(f"  {k:<6} 시장 폭: 신고가 {x.get('new_highs', 0)} · 신저가 {x.get('new_lows', 0)} "
              f"(10일 평균 {x['nh_nl_10d']:+.1f})"
              + (f" · 50일선 위 {pct50:.0f}%" if pct50 is not None else ""))


def _names(items, k: int = 8) -> str:
    out = []
    for it in items[:k]:
        if isinstance(it, dict):
            out.append(f"{it['name']}({it['code']})")
        else:
            out.append(f"{it.name}({it.code})")
    return ", ".join(out) + (f" 외 {len(items) - k}" if len(items) > k else "")


def _print_changes(summary: dict, prev_asof: str | None, rerun: bool = False) -> None:
    if not prev_asof:
        print("변화: 비교할 이전 기준일 스캔 없음 " + ("(같은 기준일 재실행 — 일지 행 교체)" if rerun else "(일지 첫 기록)"))
        return
    counts = " · ".join(f"{k} {len(summary.get(k, []))}" for k in ("신규", "돌파", "단계상승", "실패", "탈락"))
    print(f"변화 (직전 {prev_asof} 대비): {counts}")
    for k in ("신규", "돌파", "실패", "탈락"):
        if summary.get(k):
            print(f"  {k}: {_names(summary[k])}")


def _parse_patterns(text: str) -> tuple[list[str] | None, list[str]]:
    from .patterns import REGISTRY
    pats = [p.strip() for p in (text or "").split(",") if p.strip()]
    return (pats or None), [p for p in pats if p not in REGISTRY]


def _cfg_years(a) -> Config:
    """--years N → 일봉 N년치 사용 (캐시가 더 짧으면 온라인 실행 시 자동으로 다시 받음)."""
    from .config import bars_for_years
    cfg = Config()
    years = getattr(a, "years", None)
    if years:
        cfg.data.history_days = bars_for_years(years)
    return cfg


def cmd_scan(a) -> int:
    from . import journal
    from .patterns import REGISTRY
    from .report import write_report
    from .scanner import enrich_investor, run_scan, to_frame
    from .universe_data import load_universe_data

    pats, bad = _parse_patterns(a.patterns)
    if bad:
        print(f"알 수 없는 패턴: {', '.join(bad)}\n사용 가능한 패턴: {', '.join(REGISTRY)}", file=sys.stderr)
        return 2
    cfg = _cfg_years(a)
    if a.min_value:
        cfg.universe.min_avg_value_20d = a.min_value * 1e8
    if a.account is not None:
        if a.account <= 0:
            print("--account 는 0보다 커야 합니다 (원 단위, 예: 50000000).", file=sys.stderr)
            return 2
        cfg.account_size = float(a.account)
    if a.risk is not None:
        if not 0 < a.risk <= 10:
            print("--risk 는 0~10 사이 퍼센트입니다 (예: 1 = 계좌의 1%).", file=sys.stderr)
            return 2
        cfg.risk_per_trade = a.risk / 100
    tty = sys.stderr.isatty()  # 작업 스케줄러 로그(리다이렉트)에는 진행률 표시를 남기지 않음
    print("데이터 적재 중...")
    ud = load_universe_data(cfg, refresh=a.refresh, offline=a.offline, verbose=tty)
    if ud.asof is None or not ud.ohlcv:
        print("분석할 일봉 데이터가 없습니다 (캐시가 비었거나 수집 실패). 온라인으로 다시 실행해 보세요.",
              file=sys.stderr)
        return 1
    print(f"시장 상태 (기준일 {ud.asof:%Y-%m-%d})")
    _print_market(ud)
    _print_breadth(ud)
    scan = run_scan(ud, cfg, pats, verbose=tty, offline=a.offline)
    if a.investor_top > 0 and scan.stocks:
        k = enrich_investor(scan, top=a.investor_top, offline=a.offline, verbose=tty)
        print(f"수급 자료 반영: 상위 {k}종목 (CAN SLIM I 재계산)")
    print(f"분석 {scan.scanned}종목 · 후보 {len(scan.stocks)} · {scan.elapsed:.0f}초"
          + (f" · 오류 {len(scan.errors)}건" if scan.errors else "")
          + (f" · 300억 레이더 {len(scan.radar)}" if scan.radar else ""))

    # 일지: 직전 스캔 대비 배지·탈락 → 기록 (일부 패턴만 돌린 스캔은 비교가 왜곡되므로 기록하지 않음)
    if pats is None and not a.no_journal:
        try:
            jpath = Path(a.journal) if a.journal else None
            jold = journal.load_journal(jpath)
            rerun = bool(len(jold)) and f"{ud.asof:%Y-%m-%d}" in set(jold["asof"])
            summary = journal.annotate(scan, jpath, journal=jold)
            journal.append(scan, jpath)
            _print_changes(summary, scan.prev_asof, rerun)
        except Exception as e:
            print(f"일지 기록 생략: {type(e).__name__}: {e}")
    elif pats is not None and not a.no_journal:
        print("일지 기록 생략: 일부 패턴만 실행한 스캔")

    out = Path(a.out or OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    stamp = f"{scan.generated_at:%Y%m%d_%H%M}"
    table = to_frame(scan)
    table.to_csv(out / f"scan_{stamp}.csv", index=False, encoding="utf-8-sig")
    try:
        table.to_excel(out / f"scan_{stamp}.xlsx", index=False)
    except Exception as e:  # openpyxl 없음 등
        print(f"엑셀 저장 생략: {e}")
    if not a.no_html:
        try:
            path = write_report(scan, out / f"scan_{stamp}.html", top=a.top, standalone=not a.fragment)
            print(f"리포트: {path}")
            if a.open:
                webbrowser.open(path.resolve().as_uri())
        except Exception as e:
            print(f"리포트 생성 실패: {type(e).__name__}: {e}", file=sys.stderr)

    if table.empty:
        print("후보 없음")
        return 0
    cols = [c for c in ["종목코드", "종목명", "시장", "종가", "종합점수", "배지", "RS", "대표패턴", "단계", "피벗대비",
                        "손절폭%", "권장수량", "진입계획"] if c in table.columns]
    with pd.option_context("display.max_rows", 200, "display.width", 250, "display.unicode.east_asian_width", True):
        print(table[cols].head(a.show).to_string(index=False))
    return 0


def cmd_analyze(a) -> int:
    from .patterns import REGISTRY
    from .scanner import scan_one
    from .universe_data import build_context, load_universe_data, passes_universe_filter

    cfg = _cfg_years(a)
    ud = load_universe_data(cfg, refresh=a.refresh, offline=a.offline, codes=[a.code], verbose=False)
    ctx = build_context(a.code, ud, cfg)
    if ctx is None:
        print(f"{a.code}: 데이터 없음 (상장 120일 미만이거나 코드 오류)")
        return 1
    ok, why = passes_universe_filter(ctx)
    s = scan_one(ctx)
    print(f"{s.name} ({s.code}, {s.market})  종가 {s.close:,.0f} ({s.change_pct:+.2%})  RS {s.rs or '-'}  "
          f"종합 {s.score.composite}")
    print("  점수 근거: " + " / ".join(s.score.notes) + "  (업종·테마 가감은 전 종목 scan 에서만 반영)")
    if s.position:
        p = s.position
        print(f"  진입 계획: {p['plan']} · 손절 {p['stop']:,.0f} · 권장 {p['shares']:,}주 "
              f"({p['amount'] / 1e4:,.0f}만원, 최대손실 {p['max_loss'] / 1e4:,.0f}만원)")
    if not ok:
        print("  ※ 유동성 필터 미달: " + "; ".join(why))
    for name, r in s.results.items():
        flag = "●" if r.detected else "○"
        extra = f" 단계={r.stage_label} 피벗={r.pivot:,.0f}" if r.detected and r.pivot else ""
        extra += f" 손절={r.stop:,.0f}" if r.detected and r.stop else ""
        print(f"\n{flag} {REGISTRY[name][0]}  점수 {r.score:.1f}{extra}")
        for line in r.reasons[:12]:
            print(f"    {line}")
        for line in r.warnings[:12]:
            print(f"    {line}")
    if not a.no_html:
        from .report import write_report
        from .scanner import ScanResult
        scan = ScanResult(asof=ud.asof, generated_at=pd.Timestamp.now(), market=ud.market, stocks=[s],
                          scanned=1, elapsed=0, patterns=list(REGISTRY))
        out = Path(a.out or OUTPUT_DIR)
        path = write_report(scan, out / f"analyze_{a.code}.html")
        print(f"\n리포트: {path}")
        if a.open:
            webbrowser.open(path.resolve().as_uri())
    return 0


def cmd_market(a) -> int:
    from .universe_data import load_universe_data
    ud = load_universe_data(_cfg_years(a), offline=a.offline, codes=["005930"], verbose=False)
    _print_market(ud)
    _print_breadth(ud)
    return 0


def cmd_backtest(a) -> int:
    from .backtest import BacktestConfig, first_entries, run_backtest, summarize, summarize_first_entries
    hz = tuple(int(x) for x in a.horizons.split(","))
    bt = BacktestConfig(pattern=a.pattern, mode=a.mode, step=a.step if a.mode == "stage" else 1,
                        since=a.since, horizons=hz, stages=tuple(a.stages.split(",")),
                        history_days=_cfg_years(a).data.history_days if a.years else None)
    codes = [c for c in a.codes.split(",") if c] or None
    ev = run_backtest(bt, workers=a.workers, codes=codes)
    if ev.empty:
        print("신호 없음")
        return 0
    out = Path(a.out or OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"backtest_{a.pattern}_{pd.Timestamp.now():%Y%m%d_%H%M}.csv"
    ev.to_csv(path, index=False, encoding="utf-8-sig")
    summ = summarize(ev, hz)
    print(f"[{a.pattern}] 신호 {len(ev)}건 ({ev['date'].min()} ~ {ev['date'].max()})")
    with pd.option_context("display.width", 200, "display.unicode.east_asian_width", True):
        print(summ.to_string(index=False))
    if summ.attrs.get("outcome"):
        oc = summ.attrs["outcome"]
        print(f"  손절 전 +20% 도달 {oc.get('target', 0)}% · 손절 {oc.get('stop', 0)}% · 미결 {oc.get('open', 0)}%")
    if a.mode == "stage":  # 같은 패턴 구간(시작일)이 여러 번 잡히는 눌림목형 대비: 첫 진입만
        fe = summarize_first_entries(ev, hz)
        print(f"\n[첫 진입만] (종목·패턴 시작일마다 첫 신호 1건) 신호 {len(first_entries(ev))}건")
        with pd.option_context("display.width", 200, "display.unicode.east_asian_width", True):
            print(fe.to_string(index=False))
    print(f"이벤트 CSV: {path}")
    return 0


def cmd_track(a) -> int:
    from . import journal

    path = Path(a.journal) if a.journal else journal.JOURNAL_PATH
    if not path.exists():
        print(f"일지가 없습니다: {path} (scan 을 먼저 실행하세요)")
        return 1
    hz = tuple(int(x) for x in a.horizons.split(","))
    j = journal.track(path, horizons=hz, target=a.target, save=not a.no_save)
    if j.empty:
        print("일지가 비어 있습니다.")
        return 0
    dates = sorted(j["asof"].unique())
    print(f"스캔 일지 {len(j)}행 · 기준일 {len(dates)}개 ({dates[0]} ~ {dates[-1]}) · "
          f"진입가 확정 {int(j['entry'].notna().sum())}행 (진입 = 다음 봉 시가)")
    summ = journal.summarize(j, hz)
    with pd.option_context("display.width", 250, "display.max_columns", 50, "display.unicode.east_asian_width", True):
        for title, t in summ.items():
            print(f"\n[{title}]")
            print(t.to_string(index=False))
    if not a.no_save:
        print(f"\n사후 성과를 일지에 기록: {path}")
    return 0


def cmd_update(a) -> int:
    from .universe_data import load_universe_data
    ud = load_universe_data(_cfg_years(a), refresh=True)
    asof = f"{ud.asof:%Y-%m-%d}" if ud.asof is not None else "-"
    print(f"갱신 완료: {len(ud.ohlcv)}종목, 기준일 {asof}")
    return 0 if ud.asof is not None else 1


def cmd_live(a) -> int:
    from .live import run
    return run(a)


LIVE_HELP = "실시간 감시 — 스캔 후보 + 증권사(한국투자증권)/네이버 시세 → 돌파·눌림·손절 알림 (조회 전용, 주문 없음)"
LIVE_DESC = (
    "스캔 후보 중 돌파·피벗 근접·300억 눌림목·돌파 전 관찰·돌파 매수 대기 종목(최대 40)을 실시간 시세로 감시해 "
    "피벗 근접·돌파(하루 예상 거래량 배수 포함)·눌림 구간 진입·손절가 이탈을 알리고 output/live.html 대시보드를 갱신한다. "
    "조회 전용: 주문(매수·매도) 기능이 없다. 장중 신호는 잠정이므로 종가로 확인할 것. "
    "한국투자증권 설정: ~/KIS/config/kis_devlp.yaml (공식 샘플 양식)."
)


def main(argv: list[str] | None = None) -> int:
    _utf8()
    ap = argparse.ArgumentParser(prog="chart_screener", description="한국 주식 기술적 차트 패턴 발굴기")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="전 종목 스캔")
    s.add_argument("--offline", action="store_true", help="캐시만 사용")
    s.add_argument("--refresh", action="store_true", help="캐시 무시하고 재수집")
    s.add_argument("--patterns", default="", help="쉼표 구분 패턴만 실행")
    s.add_argument("--top", type=int, default=150, help="리포트에 담을 후보 수")
    s.add_argument("--show", type=int, default=30, help="콘솔에 출력할 후보 수")
    s.add_argument("--min-value", type=float, default=0, help="20일 평균 거래대금 하한(억)")
    s.add_argument("--investor-top", type=int, default=60, help="기관·외국인 수급을 붙일 상위 후보 수 (0=끔)")
    s.add_argument("--out", default="")
    s.add_argument("--no-html", action="store_true")
    s.add_argument("--fragment", action="store_true", help="HTML 조각으로 저장(Artifact 게시용)")
    s.add_argument("--open", action="store_true", help="완료 후 브라우저로 열기")
    s.add_argument("--account", type=float, default=None, help="계좌 규모(원), 포지션 수량 계산용 (기본 1억)")
    s.add_argument("--risk", type=float, default=None, help="1회 거래 위험 한도(계좌 대비 %%, 기본 1)")
    s.add_argument("--no-journal", action="store_true", help="스캔 일지(output/journal.csv)에 기록하지 않음")
    s.add_argument("--journal", default="", help="스캔 일지 경로 (기본 output/journal.csv)")
    s.add_argument("--years", type=float, default=None,
                   help="일봉 이력 연수 (기본 3년, 최대 약 10년). 예: --years 10")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("analyze", help="한 종목 상세 판정")
    s.add_argument("code")
    s.add_argument("--offline", action="store_true")
    s.add_argument("--refresh", action="store_true")
    s.add_argument("--out", default="")
    s.add_argument("--no-html", action="store_true")
    s.add_argument("--open", action="store_true")
    s.add_argument("--years", type=float, default=None,
                   help="일봉 이력 연수 (기본 3년, 최대 약 10년). 예: --years 10")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("market", help="시장 방향(M)")
    s.add_argument("--offline", action="store_true")
    s.add_argument("--years", type=float, default=None,
                   help="일봉 이력 연수 (기본 3년, 최대 약 10년). 예: --years 10")
    s.set_defaults(fn=cmd_market)

    s = sub.add_parser("backtest", help="워크포워드 신호 성과 검증 (캐시 데이터 사용)")
    s.add_argument("pattern")
    s.add_argument("--mode", default="breakout_day", choices=["breakout_day", "stage"],
                   help="breakout_day: 돌파 당일 신호(매일 실행) / stage: step 간격·단계 기준")
    s.add_argument("--step", type=int, default=5, help="stage 모드에서 몇 거래일마다 탐지할지")
    s.add_argument("--since", default=None, help="YYYY-MM-DD 이후 신호만")
    s.add_argument("--horizons", default="5,20,60")
    s.add_argument("--stages", default="breakout")
    s.add_argument("--codes", default="")
    s.add_argument("--workers", type=int, default=None)
    s.add_argument("--out", default="")
    s.add_argument("--years", type=float, default=None,
                   help="일봉 이력 연수 (기본 3년, 최대 약 10년). 예: --years 10")
    s.set_defaults(fn=cmd_backtest)

    s = sub.add_parser("track", help="스캔 일지 후보의 사후 성과(5·20·60일, 손절·+20%%) 집계 (캐시 사용)")
    s.add_argument("--journal", default="", help="일지 경로 (기본 output/journal.csv)")
    s.add_argument("--horizons", default="5,20,60")
    s.add_argument("--target", type=float, default=0.20, help="목표 수익률 (기본 0.20 = +20%%)")
    s.add_argument("--no-save", action="store_true", help="채운 성과를 일지에 다시 쓰지 않음")
    s.set_defaults(fn=cmd_track)

    s = sub.add_parser("update", help="데이터만 갱신")
    s.add_argument("--years", type=float, default=None,
                   help="일봉 이력 연수 (기본 3년, 최대 약 10년). 예: --years 10")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("live", help=LIVE_HELP, description=LIVE_DESC)
    s.add_argument("--source", choices=["auto", "kis", "naver"], default="auto",
                   help="시세 출처: auto(KIS 설정·토큰이 되면 KIS, 아니면 네이버) · kis(한국투자증권) · naver")
    s.add_argument("--top", type=int, default=40, help="감시 종목 수 (KIS 실시간 구독 한도 40)")
    s.add_argument("--codes", default="", help="꼭 감시할 종목코드 (쉼표 구분, 피벗이 있는 스캔 후보만)")
    s.add_argument("--interval", type=float, default=None,
                   help="조회 간격(초): 네이버 기본 10, KIS 웹소켓 실패 시 REST 조회 기본 15")
    s.add_argument("--venue", choices=["krx", "total"], default="krx",
                   help="KIS 체결 시장: krx(H0STCNT0) · total(KRX+NXT 통합, H0UNCNT0)")
    s.add_argument("--near", type=float, default=1.0, help="피벗 근접 알림 기준 (%%, 기본 1)")
    s.add_argument("--vol-mult", type=float, default=1.4,
                   help="돌파 거래량 기준: 하루 예상 거래량 ÷ 50일 평균 (기본 1.4배)")
    s.add_argument("--no-toast", action="store_true", help="윈도우 알림(토스트) 끄기")
    s.add_argument("--beep", action="store_true", help="알림 때 소리")
    s.add_argument("--no-open", action="store_true", help="대시보드를 브라우저로 열지 않음")
    s.add_argument("--after-hours", action="store_true", help="장 시간(09:00~15:30) 밖에도 실행·계속")
    s.add_argument("--offline", action="store_true", help="감시 목록 스캔을 캐시로만")
    s.add_argument("--refresh-scan", action="store_true", help="감시 목록 스캔 전에 일봉을 새로 받음")
    s.add_argument("--dash-every", type=float, default=3.0, help="대시보드 갱신 간격(초, 기본 3)")
    s.add_argument("--config", default="",
                   help="KIS 설정 파일 (기본 ~/KIS/config/kis_devlp.yaml, 환경변수 CHART_SCREENER_KIS_CONFIG)")
    s.add_argument("--paper", action="store_true", help="모의투자 키·주소 사용 (paper_app·paper_sec, vps·vops)")
    s.add_argument("--check", action="store_true", help="한국투자증권 연결 점검만 (설정 형식·토큰·현재가·개장일·웹소켓)")
    s.add_argument("--check-code", default="005930", help="--check 에서 조회할 종목 (기본 005930)")
    s.add_argument("--out", default="")
    s.set_defaults(fn=cmd_live)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
