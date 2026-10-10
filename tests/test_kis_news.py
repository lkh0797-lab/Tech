"""종목 뉴스 제목 (chart_screener.data.kis_news) — 가짜 KIS 뉴스 조회(srno 커서 · 1행 겹침)로 머리 · 꼬리 · 빈 구간 ·
공시만 있는 쪽 · floor · 중복 · 재시도 · 치명 오류 · 원자적 쓰기 · CLI 종료 코드.

행 모양(필드 · 제공사 코드 · 수정된 기사 시각)은 2026-10-10 실전 응답에서 따왔고, 제목 · 종목 이름은 지어낸 것이다
(공개 저장소에 언론 · 증권사 제목을 싣지 않는다). 비밀값 · 설정 파일은 쓰지 않는다."""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from chart_screener.broker.kis import KISAuthError, KISError, KISRateLimitError
from chart_screener.data import kis_market as km
from chart_screener.data import kis_news as N

BLANK = {**{f"iscd{i}": "" for i in range(2, 11)}, **{f"kor_isnm{i}": "" for i in range(2, 11)}}


def real(srno, dt, tm, dorg, title, pc, lc, iscd1, name):
    return {"cntt_usiq_srno": srno, "data_dt": dt, "data_tm": tm, "dorg": dorg, "hts_pbnt_titl_cntt": title,
            "news_ofer_entp_code": pc, "news_lrdv_code": lc, "iscd1": iscd1, "kor_isnm1": name, **BLANK}


REAL = [   # 실측 꼴 (인포스탁 목록 · 코스닥 시장조치 · 증권사 리서치(lc 빈칸) · 수정된 기사(data_tm ≠ srno 시각)) — 제목 · 이름은 지어냄
    real("2026100817060166277", "20261008", "170601", "인포스탁", "증시요약(9) - 가상 목록 B(코스닥)",
         "7", "02", "999992", "가상바이오"),
    real("2026091820004898785", "20260918", "200048", "코스닥 공시", "가나광섬유(주) [투자주의]단일계좌 거래량 상위종목",
         "G", "03", "010170", "가나광섬유"),
    real("2026090907524175225", "20260909", "075241", "한국투자증권", "가상 업종: 지어낸 리서치 제목",
         "L", "        ", "999993", "다라소재"),
    real("2025110511563795799", "20251105", "120408", "서울경제", "지어낸 기사 제목 — 수정된 기사 꼴", "U", "31", "999994",
         "마바홀딩스"),
]

TODAY = date(2026, 10, 11)


def make_rows(n, start=datetime(2026, 10, 8, 17, 0), step=timedelta(hours=3), pc="2", lc="01", src="한국경제신문",
              tag="기사"):
    """srno 내림차순 가짜 행 n 개 (start 부터 step 간격으로 거슬러)."""
    out = []
    for i in range(n):
        t = start - step * i
        out.append(real(f"{t:%Y%m%d%H%M%S}{(i * 7919) % 100000:05d}", f"{t:%Y%m%d}", f"{t:%H%M%S}", src,
                        f"{tag} {t:%m%d %H%M}", pc, lc, "010170", "가나광섬유"))
    return out


class FakeNews:
    """client.get(path, tr_id, params) 대역 — 커서가 없으면 최신 40행, 있으면 srno 가 커서 이하인 행부터 40행
    (커서 행 포함이라 쪽끼리 1행 겹침). extra 만큼 더 최신 쪽에서 시작해 겹침을 늘린다. errors = {n번째 호출: 예외}."""

    def __init__(self, rows, errors=None, extra=0):
        self.rows = sorted(rows, key=lambda r: r["cntt_usiq_srno"], reverse=True)
        self.errors, self.extra, self.calls = dict(errors or {}), extra, []

    def add(self, rows):
        self.rows = sorted(self.rows + rows, key=lambda r: r["cntt_usiq_srno"], reverse=True)

    def get(self, path, tr_id, params):
        assert path == N.PATH_NEWS and tr_id == N.TR_NEWS
        self.calls.append(dict(params))
        e = self.errors.pop(len(self.calls), None)
        if e is not None:
            raise e
        s = params["FID_INPUT_SRNO"]
        i = 0
        if s:
            assert params["FID_INPUT_DATE_1"] == "00" + s[:8] and params["FID_INPUT_HOUR_1"] == s[8:14]
            i = next((k for k, r in enumerate(self.rows) if r["cntt_usiq_srno"] <= s), len(self.rows))
            i = max(0, i - self.extra)
        return {"rt_cd": "0", "msg_cd": "MCA00000", "output": [dict(r) for r in self.rows[i:i + N.PAGE]]}

    def ids(self):
        return [r["cntt_usiq_srno"] for r in self.rows]


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    got = []
    monkeypatch.setattr(N.time, "sleep", got.append)
    return got


def go(fake, tmp_path, codes=("010170",), **kw):
    kw.setdefault("today", TODAY)
    return N.run(fake, list(codes), cache=N.NewsCache(tmp_path / "news"), per_sec=0, **kw)


def doc(tmp_path, code="010170"):
    return json.loads((tmp_path / "news" / f"{code}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 행 모양
def test_row_shape_from_real_sample():
    rows = [N._row(r) for r in REAL]
    assert rows[0] == {"id": "2026100817060166277", "d": "20261008", "t": "170601", "src": "인포스탁", "pc": "7",
                       "lc": "02", "title": "증시요약(9) - 가상 목록 B(코스닥)", "c1": "999992",
                       "n1": "가상바이오"}
    assert rows[2]["lc"] == "" and rows[1]["pc"] == "G"
    assert rows[3]["t"] == "120408" and rows[3]["id"][8:14] == "115637"     # 수정된 기사: 시각은 응답 그대로, id 는 등록 시각
    assert N._row({**REAL[0], "cntt_usiq_srno": "12345"}) is None
    assert N._cursor("2026100817060166277") == ("0020261008", "170601", "2026100817060166277")


# ---------------------------------------------------------------- 첫 받기 · 증분
def test_first_run_walks_head_then_tail_to_end(tmp_path):
    fake = FakeNews(make_rows(100))
    r = go(fake, tmp_path)
    assert r.added == 100 and r.calls == 3 and not r.errors and r.left == 0     # 40 → 39 새 → 21 새(22행 < 40)
    assert [c["FID_INPUT_SRNO"] for c in fake.calls] == ["", fake.ids()[39], fake.ids()[78]]
    js = doc(tmp_path)
    assert js["v"] == 1 and js["code"] == "010170" and js["complete"] is True and js["capped"] is False
    assert js["pages"] == 3 and js["floor"] == "20250906" and "gaps" not in js
    ids = [x["id"] for x in js["rows"]]
    assert ids == fake.ids() and js["newest"] == ids[0] and js["oldest"] == ids[-1]
    assert js["at"].endswith("+09:00")
    assert "새 100건 · 호출 3" in r.summary_line() and "이어 받기" not in r.summary_line()


def test_incremental_stops_at_known_newest(tmp_path):
    fake = FakeNews(make_rows(100))
    go(fake, tmp_path)
    n = len(fake.calls)
    r = go(fake, tmp_path)
    assert len(fake.calls) - n == 1 and r.added == 0                             # 새 것 없음 — 한 쪽만
    fake.add(make_rows(5, start=datetime(2026, 10, 10, 9, 0), step=timedelta(minutes=10), tag="새"))
    r = go(fake, tmp_path)
    assert len(fake.calls) - n == 2 and r.added == 5
    js = doc(tmp_path)
    assert [x["id"] for x in js["rows"]] == fake.ids() and js["pages"] == 5 and js["complete"] is True


def test_head_overwrites_edited_title(tmp_path):
    fake = FakeNews(make_rows(100))
    go(fake, tmp_path)
    fake.rows[5]["hts_pbnt_titl_cntt"] = "고친 제목"
    r = go(fake, tmp_path)
    assert r.added == 0 and doc(tmp_path)["rows"][5]["title"] == "고친 제목"


def test_small_stock_one_page_is_complete(tmp_path):
    fake = FakeNews(make_rows(12))
    r = go(fake, tmp_path)
    assert r.calls == 1 and doc(tmp_path)["complete"] is True and len(doc(tmp_path)["rows"]) == 12


# ---------------------------------------------------------------- 한도 · 이어 받기
def test_pages_cap_then_resume_tail(tmp_path):
    fake = FakeNews(make_rows(200))
    r = go(fake, tmp_path, pages=2)
    js = doc(tmp_path)
    assert r.left == 1 and js["capped"] is True and js["complete"] is False and len(js["rows"]) == 79
    assert "이어 받기 남음 1" in r.summary_line()
    n = len(fake.calls)
    r = go(fake, tmp_path)
    js = doc(tmp_path)
    assert fake.calls[n]["FID_INPUT_SRNO"] == ""                                 # 머리 먼저
    assert fake.calls[n + 1]["FID_INPUT_SRNO"] == fake.ids()[78]                 # 그다음 지난번 가장 오래된 행부터
    assert js["complete"] is True and js["capped"] is False and r.left == 0
    assert [x["id"] for x in js["rows"]] == fake.ids()


def test_head_cut_short_leaves_gap_filled_next_run(tmp_path):
    fake = FakeNews(make_rows(100))
    go(fake, tmp_path)
    old_newest = fake.ids()[0]
    fake.add(make_rows(120, start=datetime(2026, 10, 10, 20, 0), step=timedelta(minutes=10), tag="새"))
    r = go(fake, tmp_path, pages=2)                                              # 120 새 행 중 79 만
    js = doc(tmp_path)
    assert js["capped"] is True and js["complete"] is True and r.left == 1
    assert js["gaps"] == [[fake.ids()[78], old_newest]] and js["newest"] == fake.ids()[0]
    r = go(fake, tmp_path)
    js = doc(tmp_path)
    assert "gaps" not in js and js["capped"] is False and r.left == 0 and r.added == 41
    assert [x["id"] for x in js["rows"]] == fake.ids()                           # 빈틈 · 중복 없음


def test_deadline_passed_touches_nothing(tmp_path):
    fake = FakeNews(make_rows(10))
    u = N.update(fake, "010170", N.NewsCache(tmp_path / "news"), floor="20250906", deadline=N.time.monotonic() - 1)
    assert u.capped and u.pages == 0 and not fake.calls and not (tmp_path / "news" / "010170.json").exists()
    r = go(fake, tmp_path, budget=0)
    assert r.pending == 1 and not fake.calls and "못 받음 1(시간 한도)" in r.summary_line()


# ---------------------------------------------------------------- 꼬리 끝
def test_tail_ends_on_disclosure_only_page_past_edge(tmp_path):
    news = make_rows(60, start=datetime(2025, 11, 30, 17, 0))
    disc = make_rows(100, start=datetime(2025, 11, 10, 18, 0), step=timedelta(hours=6), pc="G", lc="01",
                     src="코스닥 공시", tag="공시")                               # 공시만 쪽이 오늘 − 330일(2025-11-15) 앞
    fake = FakeNews(news + disc)
    r = go(fake, tmp_path)
    js = doc(tmp_path)
    assert r.calls == 3 and js["complete"] is True                               # 40 뉴스 → 섞인 쪽 → 공시만 쪽에서 끝
    assert len(js["rows"]) == 118 and js["oldest"] == fake.ids()[117]
    assert r.items[0].news_from == news[-1]["data_dt"]


def test_disclosure_only_page_inside_news_window_keeps_going(tmp_path):
    news = make_rows(60)                                                         # 2026-10-08 부터
    disc = make_rows(80, start=datetime(2026, 9, 20, 18, 0), step=timedelta(hours=6), pc="G", lc="01",
                     src="코스닥 공시", tag="공시")                               # 3쪽째가 공시만(2026-09) — 기사 보관 안쪽
    old = make_rows(80, start=datetime(2026, 6, 30, 12, 0), step=timedelta(hours=12), tag="옛 기사")
    fake = FakeNews(news + disc + old)
    r = go(fake, tmp_path)
    js = doc(tmp_path)
    assert r.calls == 6 and js["complete"] is True                               # 공시만 쪽을 넘어 옛 기사까지
    assert [x["id"] for x in js["rows"]] == fake.ids() and r.items[0].news_from == old[-1]["data_dt"]
    u = N.update(FakeNews(news + disc + old), "010170", N.NewsCache(tmp_path / "n2"), floor="20250906")
    assert u.pages == 3 and u.complete                                           # disc_edge 없이 부르면 공시만 쪽에서 끝


def test_tail_stops_at_floor_and_reopens_when_days_grow(tmp_path):
    fake = FakeNews(make_rows(300, step=timedelta(days=1)))
    r = go(fake, tmp_path, days=100)                                             # floor 2026-07-03
    js = doc(tmp_path)
    assert r.calls == 3 and js["complete"] is True and js["floor"] == "20260703"
    assert len(js["rows"]) == 118 and js["rows"][-1]["d"] < "20260703"          # 하한을 넘은 쪽까지는 그대로 둔다
    r = go(fake, tmp_path, days=100, today=date(2026, 10, 12))                   # 다음 날: floor 가 하루 늘어도 다시 열지 않음
    assert r.calls == 1 and doc(tmp_path)["floor"] == "20260703"
    r = go(fake, tmp_path, days=400)                                             # 더 앞까지 — 꼬리를 다시 연다
    js = doc(tmp_path)
    assert js["complete"] is True and [x["id"] for x in js["rows"]] == fake.ids() and js["floor"] == "20250906"


def test_dedup_by_id_when_overlap_is_more_than_one(tmp_path):
    fake = FakeNews(make_rows(100), extra=3)                                     # 커서 앞 3행까지 다시 옴 (겹침 4행)
    r = go(fake, tmp_path)
    js = doc(tmp_path)
    ids = [x["id"] for x in js["rows"]]
    assert ids == fake.ids() and len(set(ids)) == 100 and js["complete"] is True
    assert r.items[0].odd == 1 and "겹침 1행 아닌 쪽 1" in r.items[0].line()       # 마지막 쪽은 세지 않음


# ---------------------------------------------------------------- 오류
def test_rate_limit_error_is_retried(tmp_path, sleeps):
    err = KISRateLimitError("초당 호출 한도를 넘었습니다 — 잠시 쉬었다가 다시 요청합니다.", "EGW00201", retry_after=1.0)
    fake = FakeNews(make_rows(100), errors={2: err})
    r = go(fake, tmp_path)
    assert not r.errors and r.calls == 4 and sleeps == [1.0] and doc(tmp_path)["complete"] is True


def test_transient_error_after_retries_keeps_rows_and_resumes(tmp_path, sleeps):
    boom = KISError("KIS 서버 오류 (HTTP 500)", None)
    fake = FakeNews(make_rows(100), errors={2: boom, 3: boom, 4: boom})
    r = go(fake, tmp_path)
    js = doc(tmp_path)
    assert r.errors == {"010170": "KIS 서버 오류 (HTTP 500)"} and sleeps == [1.0, 2.0] and not r.stopped
    assert len(js["rows"]) == 40 and js["complete"] is False and r.left == 1
    r = go(fake, tmp_path)
    assert not r.errors and doc(tmp_path)["complete"] is True and len(doc(tmp_path)["rows"]) == 100


def test_fatal_error_stops_run_and_keeps_rows(tmp_path):
    fake = FakeNews(make_rows(200), errors={3: KISAuthError("유효하지 않은 AppKey 입니다", "EGW00103")})
    r = go(fake, tmp_path, codes=("010170", "005930"))
    assert "AppKey" in r.stopped and "중단" in r.summary_line() and r.calls == 3
    assert {c["FID_INPUT_ISCD"] for c in fake.calls} == {"010170"}               # 다음 종목은 묻지 않음
    js = doc(tmp_path)
    assert len(js["rows"]) == 79 and js["complete"] is False                     # 받은 두 쪽은 저장


def test_retry_does_not_run_past_deadline(tmp_path, sleeps):
    boom = KISError("KIS 서버 오류 (HTTP 500)", None)
    fake = FakeNews(make_rows(10), errors={1: boom, 2: boom, 3: boom})
    with pytest.raises(KISError):
        N._page(fake, "010170", None, deadline=N.time.monotonic() + 1.5)        # 1초 쉬고 한 번 더, 2초는 한도 넘음
    assert len(fake.calls) == 2 and sleeps == [1.0]
    fake = FakeNews(make_rows(10), errors={1: boom, 2: boom, 3: boom})
    u = N.update(fake, "010170", N.NewsCache(tmp_path / "news"), floor="20250906",
                 deadline=N.time.monotonic() + 0.5)
    assert u.err == "KIS 서버 오류 (HTTP 500)" and len(fake.calls) == 1 and sleeps == [1.0]   # 더 쉬지 않음
    assert not (tmp_path / "news" / "010170.json").exists()


def test_limiter_waits_before_every_call(tmp_path):
    class Lim:
        n = 0

        def wait(self):
            Lim.n += 1
            return 0.0

    fake = FakeNews(make_rows(100), errors={2: KISError("KIS 서버 오류 (HTTP 500)", None)})
    go(fake, tmp_path, limiter=Lim())
    assert Lim.n == len(fake.calls) == 4


# ---------------------------------------------------------------- 저장
def test_atomic_write_retries_when_file_is_busy(tmp_path, monkeypatch, sleeps):
    real_replace, n = os.replace, []

    def busy_once(a, b):
        n.append(1)
        if len(n) == 1:
            raise PermissionError("읽는 중")
        return real_replace(a, b)

    monkeypatch.setattr(os, "replace", busy_once)
    go(FakeNews(make_rows(30)), tmp_path)
    assert len(doc(tmp_path)["rows"]) == 30 and sleeps == [0.1]
    assert not list((tmp_path / "news").glob("*.tmp"))


def test_write_failure_keeps_old_file_and_reports(tmp_path, monkeypatch):
    fake = FakeNews(make_rows(30))
    go(fake, tmp_path)
    before = (tmp_path / "news" / "010170.json").read_bytes()
    fake.add(make_rows(3, start=datetime(2026, 10, 10, 9, 0), tag="새"))

    def busy(a, b):
        raise PermissionError("읽는 중")

    monkeypatch.setattr(os, "replace", busy)
    r = go(fake, tmp_path)
    assert "010170" in r.errors and (tmp_path / "news" / "010170.json").read_bytes() == before
    assert not list((tmp_path / "news").glob("*.tmp"))


def test_broken_cache_is_moved_aside(tmp_path):
    p = tmp_path / "news" / "010170.json"
    p.parent.mkdir(parents=True)
    p.write_text("{깨진", encoding="utf-8")
    r = go(FakeNews(make_rows(30)), tmp_path)
    assert (tmp_path / "news" / "010170.json.bad").read_text(encoding="utf-8") == "{깨진"
    assert len(doc(tmp_path)["rows"]) == 30
    assert r.items[0].moved == "010170.json.bad" and "깨진 캐시 → 010170.json.bad" in r.items[0].line()
    assert "깨진 캐시 치움 1" in r.summary_line()


def test_second_corruption_keeps_first_bad(tmp_path):
    p = tmp_path / "news" / "010170.json"
    p.parent.mkdir(parents=True)
    p.write_text("{첫째", encoding="utf-8")
    go(FakeNews(make_rows(30)), tmp_path)
    p.write_text("둘째", encoding="utf-8")
    r = go(FakeNews(make_rows(30)), tmp_path)
    assert (tmp_path / "news" / "010170.json.bad").read_text(encoding="utf-8") == "{첫째"
    assert (tmp_path / "news" / "010170.json.bad1").read_text(encoding="utf-8") == "둘째"
    assert r.items[0].moved == "010170.json.bad1" and len(doc(tmp_path)["rows"]) == 30


def test_broken_cache_that_cannot_be_moved_is_left_alone(tmp_path, monkeypatch):
    p = tmp_path / "news" / "010170.json"
    p.parent.mkdir(parents=True)
    p.write_bytes("{깨진 보관소".encode("utf-8"))

    def busy(a, b):
        raise PermissionError("읽는 중")                                          # 뷰어가 열어 둠 (Windows 이름 바꾸기 거부)

    monkeypatch.setattr(os, "replace", busy)
    fake = FakeNews(make_rows(30))
    r = go(fake, tmp_path)
    assert r.errors == {"010170": "PermissionError: 읽는 중"} and not fake.calls and not r.items
    assert p.read_bytes() == "{깨진 보관소".encode("utf-8") and not list(p.parent.glob("*.bad*"))


def test_other_cache_version_keeps_rows(tmp_path):
    fake = FakeNews(make_rows(100))
    go(fake, tmp_path)
    js = doc(tmp_path)
    js["v"] = 0
    (tmp_path / "news" / "010170.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    n = len(fake.calls)
    go(fake, tmp_path)
    js = doc(tmp_path)
    assert js["v"] == 1 and [x["id"] for x in js["rows"]] == fake.ids() and js["complete"] is True
    assert len(fake.calls) - n == 2                                              # 머리 한 쪽 + 꼬리 끝 확인 한 쪽


# ---------------------------------------------------------------- CLI
def test_cli_news_without_client_fails(monkeypatch, capsys):
    from chart_screener.__main__ import main
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: (None, "한국투자증권 설정 없음: 시험"))
    assert main(["news", "--codes", "010170"]) == 1
    assert "설정 없음: 시험" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["news"], ["news", "--codes", "10170"], ["news", "--codes", "010170", "--pages", "0"],
                                  ["news", "--codes", "010170", "--per-sec", "0"]])
def test_cli_news_bad_args(monkeypatch, capsys, args):
    from chart_screener.__main__ import main
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: pytest.fail("인자 오류면 연결하지 않음"))
    assert main(args) == 2
    assert capsys.readouterr().err


def test_cli_news_writes_cache_and_summary(monkeypatch, tmp_path, capsys):
    from chart_screener.__main__ import main
    fake = FakeNews(make_rows(50))
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: (fake, ""))
    assert main(["news", "--codes", "010170,010170", "--out", str(tmp_path / "news"), "--per-sec", "1000"]) == 0
    out = capsys.readouterr().out
    assert "뉴스 제목: 1종목 · 새 50건 · 호출 2" in out and "010170: 50행" in out and "끝까지 받음" in out
    assert len(doc(tmp_path)["rows"]) == 50


def test_cli_news_fatal_exit_1(monkeypatch, tmp_path, capsys):
    from chart_screener.__main__ import main
    fake = FakeNews(make_rows(50), errors={1: KISAuthError("유효하지 않은 AppKey 입니다", "EGW00103")})
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: (fake, ""))
    assert main(["news", "--codes", "010170", "--out", str(tmp_path / "news"), "--per-sec", "1000"]) == 1
    assert "중단: 유효하지 않은 AppKey" in capsys.readouterr().out


def test_cli_news_all_codes_failed_exit_1(monkeypatch, tmp_path, capsys):
    from chart_screener.__main__ import main
    boom = KISError("KIS 서버 오류 (HTTP 500)", None)
    fake = FakeNews(make_rows(50), errors={1: boom, 2: boom, 3: boom})
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: (fake, ""))
    assert main(["news", "--codes", "010170", "--out", str(tmp_path / "news"), "--per-sec", "1000"]) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert "HTTP 500" in out[-1] and "실패 1" in out[-2]                          # 뷰어는 마지막 줄을 보여 준다
    fake = FakeNews(make_rows(50), errors={1: boom, 2: boom, 3: boom})          # 둘 중 하나만 실패 — 정상 종료
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: (fake, ""))
    assert main(["news", "--codes", "010170,005930", "--out", str(tmp_path / "news"), "--per-sec", "1000"]) == 0
    assert "실패 1" in capsys.readouterr().out


def test_viewer_probe_string_present():
    """기업추적 뷰어는 _tech_supports('add_parser("news"') 로 이 명령이 있는지 본다."""
    import chart_screener.__main__ as m
    assert 'add_parser("news"' in Path(m.__file__).read_text(encoding="utf-8")
