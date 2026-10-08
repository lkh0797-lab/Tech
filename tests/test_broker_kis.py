"""한국투자증권 클라이언트 (chart_screener.broker.kis) — 네트워크 없이 가짜 세션·가짜 웹소켓으로 검증.

비밀값은 전부 가짜(FAKE...) 이며, 실제 설정 파일(~/KIS/config)은 읽지 않는다 (경로를 항상 tmp 로 지정).
"""
import asyncio
import json

import pytest

from chart_screener.broker import kis
from chart_screener.broker.kis import (
    CCNL_COLUMNS, TR_CCNL_KRX, TR_CCNL_TOTAL, KISAuthError, KISConfig, KISConfigError, KISError, KISRateLimitError,
    KISRestClient, KISWebSocketClient, RateLimiter, TokenManager, issue_approval_key, parse_frame, parse_simple_yaml,
    redact, subscribe_message, tick_from_record, ws_endpoint,
)

APP_KEY = "PSFAKE" + "k" * 30                 # 36자
APP_SECRET = "FAKESECRET" + "s" * 170         # 180자
TOKEN = "eyFAKE.TOKEN." + "t" * 300
APPROVAL = "fake-approval-" + "a" * 22

TEMPLATE = """#홈페이지에서 API서비스 신청시 받은 Appkey, Appsecret 값 설정
#실전투자
my_app: "앱키"
my_sec: "앱키 시크릿"

#모의투자
paper_app: "모의투자 앱키"
paper_sec: "모의투자 앱키 시크릿"

# HTS ID
my_htsid: "사용자 HTS ID"

#계좌번호 앞 8자리
my_acct_stock: "증권계좌 8자리"
my_prod: "01" # 종합계좌
# my_prod: "03" # 국내선물옵션계좌

#domain infos
prod: "https://openapi.koreainvestment.com:9443" # 서비스
ops: "ws://ops.koreainvestment.com:21000" # 웹소켓
vps: "https://openapivts.koreainvestment.com:29443" # 모의투자 서비스
vops: "ws://ops.koreainvestment.com:31000" # 모의투자 웹소켓

my_token: ""

my_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
"""


def filled(app=APP_KEY, sec=APP_SECRET, acct="12345678") -> str:
    return (TEMPLATE.replace('my_app: "앱키"', f'my_app: "{app}"')
            .replace('my_sec: "앱키 시크릿"', f'my_sec: "{sec}"')
            .replace('my_acct_stock: "증권계좌 8자리"', f'my_acct_stock: "{acct}"'))


def write_cfg(tmp_path, text=None, name="kis_devlp.yaml"):
    p = tmp_path / name
    p.write_text(filled() if text is None else text, encoding="utf-8")
    return p


def make_cfg(tmp_path, **kw) -> KISConfig:
    return KISConfig.load(write_cfg(tmp_path, filled(**kw)))


# ---------------------------------------------------------------- 가짜 HTTP
class Resp:
    def __init__(self, status=200, js=None):
        self.status_code = status
        self._js = js

    def json(self):
        if self._js is None:
            raise ValueError("not json")
        return self._js


class FakeSession:
    def __init__(self, posts=(), gets=()):
        self.posts, self.gets = list(posts), list(gets)
        self.post_calls, self.get_calls = [], []
        self.headers = {}

    def post(self, url, data=None, headers=None, timeout=None):
        self.post_calls.append({"url": url, "body": json.loads(data), "headers": headers})
        r = self.posts.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_calls.append({"url": url, "headers": dict(headers or {}), "params": dict(params or {})})
        r = self.gets.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def token_ok(expired="2026-10-09 10:00:00"):
    return Resp(200, {"access_token": TOKEN, "token_type": "Bearer", "expires_in": 86400,
                      "access_token_token_expired": expired})


class Clock:
    def __init__(self, t=1_791_400_000.0):   # 2026-10-08 KST 무렵
        self.t = t
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


# ---------------------------------------------------------------- 설정 파싱·진단
def test_parse_simple_yaml_handles_comments_quotes_crlf_bom():
    text = ("\ufeffa: \"x # not comment\"  # comment\r\n"
            "b: plain value # trailing\r\n"
            "c: 'it''s'\r\n"
            "d:\r\n"
            "# skipped: \"z\"\r\n"
            "  indented: \"ignored\"\r\n"
            "e: \"esc \\\" q\"\r\n")
    d = parse_simple_yaml(text)
    assert d == {"a": "x # not comment", "b": "plain value", "c": "it's", "d": "", "e": 'esc " q'}


def test_template_placeholders_are_diagnosed_in_korean_without_values(tmp_path):
    cfg = KISConfig.load(write_cfg(tmp_path, TEMPLATE))
    diag = cfg.diagnose()
    assert "my_sec 이 예시 문구 그대로입니다 (한글 포함, 6자) — KIS Developers 에서 받은 값으로 바꾸세요" in diag
    assert any(m.startswith("my_app 이 예시 문구 그대로입니다 (한글 포함, 2자)") for m in diag)
    assert not cfg.ok
    assert any("my_acct_stock" in w and "예시" in w for w in cfg.warnings())


def test_valid_config_ok_and_repr_hides_secrets(tmp_path):
    cfg = make_cfg(tmp_path)
    assert cfg.ok, cfg.diagnose()
    assert cfg.warnings() == []
    assert cfg.app_key == APP_KEY and cfg.app_secret == APP_SECRET
    assert cfg.base_url == "https://openapi.koreainvestment.com:9443"
    assert cfg.ws_url == "ws://ops.koreainvestment.com:21000"
    assert cfg.account == "12345678" and cfg.product == "01"
    for text in (repr(cfg), str(cfg), cfg.summary(), " ".join(cfg.diagnose() + cfg.warnings())):
        assert APP_SECRET not in text and APP_KEY not in text
        assert APP_SECRET[:8] not in text
    assert "PSFA…(36자)" in cfg.summary() and "…(180자)" in cfg.summary()


def test_secret_shape_problems(tmp_path):
    short = make_cfg(tmp_path, sec="S" * 50)
    assert any("my_sec 길이가 50자입니다 (보통 180자)" in m for m in short.diagnose())
    truncated = make_cfg(tmp_path, sec="S" * 120)
    assert truncated.ok
    assert any("my_sec 길이가 120자입니다 (보통 180자)" in m for m in truncated.warnings())
    spaced = make_cfg(tmp_path, sec="S" * 90 + " " + "S" * 89)
    assert any("공백·줄바꿈" in m for m in spaced.diagnose())
    swapped = make_cfg(tmp_path, app=APP_SECRET, sec=APP_KEY)
    assert any("뒤바뀐 것 같습니다" in m for m in swapped.diagnose())
    same = make_cfg(tmp_path, sec=APP_KEY)
    assert any("같은 값" in m for m in same.diagnose())
    ellipsis = make_cfg(tmp_path, sec="S" * 170 + "...")
    assert any("말줄임표" in m for m in ellipsis.diagnose())
    bad_acct = make_cfg(tmp_path, acct="1234-5678")
    assert bad_acct.ok and any("8자리 숫자가 아닙니다" in w for w in bad_acct.warnings())
    for c in (short, truncated, spaced, swapped, same, ellipsis):
        assert all(c.app_secret not in m for m in c.diagnose() + c.warnings())


def test_unclosed_quote_and_wrapped_value_are_reported(tmp_path):
    text = filled().replace(f'my_sec: "{APP_SECRET}"', f'my_sec: "{APP_SECRET[:100]}\n  {APP_SECRET[100:]}"')
    cfg = KISConfig.load(write_cfg(tmp_path, text))
    diag = cfg.diagnose()
    assert any("따옴표가 닫히지 않았습니다" in m for m in diag)
    assert any("my_sec 값이 여러 줄로 나뉘어 있습니다" in m for m in diag)
    dup = KISConfig.load(write_cfg(tmp_path, filled() + f'my_app: "{APP_KEY}"\n'))
    assert dup.ok and any("두 번" in w for w in dup.warnings())


def test_missing_keys_and_urls(tmp_path):
    cfg = KISConfig.load(write_cfg(tmp_path, f'my_app: "{APP_KEY}"\nmy_sec: "{APP_SECRET}"\n'))
    diag = cfg.diagnose()
    assert "prod 항목이 없습니다" in diag and "ops 항목이 없습니다" in diag
    bad = KISConfig.load(write_cfg(tmp_path, filled().replace("ws://ops", "http://ops")))
    assert any("ws:// 로 시작" in m for m in bad.diagnose())


def test_load_default_path_env_override_and_missing_file(tmp_path, monkeypatch):
    p = write_cfg(tmp_path, name="custom.yaml")
    monkeypatch.setenv(kis.CONFIG_ENV, str(p))
    assert kis.resolve_config_path() == p
    assert KISConfig.load().path == p
    monkeypatch.setenv(kis.CONFIG_ENV, str(tmp_path / "nope.yaml"))
    with pytest.raises(KISConfigError) as ei:
        KISConfig.load()
    assert "설정 파일이 없습니다" in ei.value.message and "nope.yaml" in ei.value.message
    monkeypatch.delenv(kis.CONFIG_ENV)
    assert kis.resolve_config_path() == kis.DEFAULT_CONFIG


def test_paper_env_uses_paper_keys(tmp_path):
    text = filled().replace('paper_app: "모의투자 앱키"', f'paper_app: "{APP_KEY}"').replace(
        'paper_sec: "모의투자 앱키 시크릿"', f'paper_sec: "{APP_SECRET}"')
    cfg = KISConfig.load(write_cfg(tmp_path, text), env="vps")
    assert cfg.base_url.startswith("https://openapivts") and cfg.ws_url.endswith(":31000")
    assert cfg.diagnose() == []


def test_token_cache_lives_next_to_config_never_in_repo(tmp_path):
    cfg = make_cfg(tmp_path)
    assert cfg.token_cache_path == tmp_path / "chart_screener_token.json"
    inside = KISConfig.from_mapping({}, path=kis.PROJECT_ROOT / "kis_devlp.yaml")
    assert inside.token_cache_path == kis.DEFAULT_CONFIG.parent / "chart_screener_token.json"


def test_redact_and_scrub():
    assert redact(APP_SECRET, 0) == "…(180자)"
    assert redact(APP_KEY) == "PSFA…(36자)"
    assert redact("앱키") == "…(2자)"            # 짧은 값은 앞글자도 보이지 않음
    assert redact("") == "(비어 있음)"
    assert kis.scrub(f"bad key {APP_SECRET} here", [APP_SECRET]) == "bad key …(180자) here"


# ---------------------------------------------------------------- 접근토큰
def test_token_issue_cache_and_reuse_by_new_instance(tmp_path):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    s = FakeSession(posts=[token_ok()])
    tm = TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep)
    assert tm.get() == TOKEN and tm.source == "issued"
    call = s.post_calls[0]
    assert call["url"] == "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    assert call["body"] == {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    assert tm.get() == TOKEN and tm.source == "memory"
    cache = tmp_path / "chart_screener_token.json"
    st = json.loads(cache.read_text(encoding="utf-8"))
    assert st["tokens"][cfg.key_id]["token"] == TOKEN
    assert APP_KEY not in cache.read_text(encoding="utf-8") and APP_SECRET not in cache.read_text(encoding="utf-8")
    # 새 프로세스(새 인스턴스)는 발급 없이 캐시 재사용
    s2 = FakeSession()
    tm2 = TokenManager(cfg, session=s2, clock=clock, sleep=clock.sleep)
    assert tm2.get() == TOKEN and tm2.source == "cache" and s2.post_calls == []
    assert TOKEN not in repr(tm2) and TOKEN[:20] not in repr(tm2)


def test_token_refreshes_ten_minutes_before_expiry(tmp_path):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    exp = kis.datetime.fromtimestamp(clock.t + 3600, kis.KST).strftime("%Y-%m-%d %H:%M:%S")
    s = FakeSession(posts=[token_ok(exp), token_ok()])
    tm = TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep)
    tm.get()
    clock.t += 3600 - 900          # 만료 15분 전: 재사용
    assert tm.get() == TOKEN and len(s.post_calls) == 1
    clock.t += 400                 # 만료 8분 20초 전: 새로 발급
    tm.get()
    assert len(s.post_calls) == 2 and tm.source == "issued"


def test_token_issue_rate_limit_one_per_minute(tmp_path):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    s = FakeSession(posts=[token_ok()])
    TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep).get(force=True)
    clock.t += 20
    strict = TokenManager(cfg, session=FakeSession(), clock=clock, sleep=clock.sleep, wait_on_limit=False)
    with pytest.raises(KISRateLimitError) as ei:
        strict.get(force=True)
    assert ei.value.code == "EGW00133" and 40 <= ei.value.retry_after <= 41
    assert "1분에 1회" in ei.value.message
    notes = []
    s3 = FakeSession(posts=[token_ok()])
    patient = TokenManager(cfg, session=s3, clock=clock, sleep=clock.sleep, notice=notes.append)
    assert patient.get(force=True) == TOKEN
    assert clock.slept and 40 <= clock.slept[-1] <= 41
    assert notes and "1분 1회" in notes[0]


def test_token_errors_are_korean_and_secret_free(tmp_path):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    s = FakeSession(posts=[Resp(403, {"error_description": f"유효하지 않은 AppSecret ({APP_SECRET})",
                                      "error_code": "EGW00105"})])
    with pytest.raises(KISAuthError) as ei:
        TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep).get()
    e = ei.value
    assert e.code == "EGW00105" and "AppSecret" in e.message and "180자" in e.message
    assert APP_SECRET not in str(e) and APP_KEY not in str(e)
    s = FakeSession(posts=[Resp(403, {"error_description": "x", "error_code": "EGW00103"})])
    clock.t += 100
    with pytest.raises(KISAuthError) as ei:
        TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep).get()
    assert "AppKey" in ei.value.message
    s = FakeSession(posts=[Resp(500, {"error_description": f"oops {APP_SECRET}", "error_code": "EGW09999"})])
    clock.t += 100
    with pytest.raises(KISAuthError) as ei:
        TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep).get()
    assert APP_SECRET not in str(ei.value) and "…(180자)" in str(ei.value)


def test_token_egw00133_waits_and_retries_once(tmp_path):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    s = FakeSession(posts=[Resp(403, {"error_code": "EGW00133", "error_description": "1분당 1회"}), token_ok()])
    tm = TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep)
    assert tm.get() == TOKEN
    assert len(s.post_calls) == 2 and clock.slept and clock.slept[0] >= 60


def test_token_network_error_message(tmp_path):
    import requests
    cfg = make_cfg(tmp_path)
    s = FakeSession(posts=[requests.ConnectionError("boom")])
    with pytest.raises(KISAuthError) as ei:
        TokenManager(cfg, session=s, clock=Clock(), sleep=lambda x: None).get()
    assert ei.value.code == "NETWORK" and "연결하지 못했습니다" in ei.value.message


# ---------------------------------------------------------------- REST
PRICE_OUT = {"stck_prpr": "30950", "prdy_vrss": "-550", "prdy_vrss_sign": "5", "prdy_ctrt": "-1.75",
             "stck_oprc": "31500", "stck_hgpr": "31600", "stck_lwpr": "30800", "acml_vol": "1234567",
             "acml_tr_pbmn": "38000000000"}


def rest_client(tmp_path, gets, posts=None):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    s = FakeSession(posts=posts or [token_ok()], gets=gets)
    tm = TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep)
    slept = []
    return KISRestClient(cfg, tm, session=s, sleep=slept.append, limiter=RateLimiter(0)), s, slept


def test_rest_quote_parses_and_sends_kis_headers(tmp_path):
    c, s, _ = rest_client(tmp_path, [Resp(200, {"rt_cd": "0", "msg_cd": "MCA00000", "output": PRICE_OUT})])
    q = c.quote("003490")
    assert (q.price, q.change, q.change_pct, q.open, q.high, q.low) == (30950, -550, -1.75, 31500, 31600, 30800)
    assert q.volume == 1234567 and q.value_krw == 38e9 and q.time.tzinfo is not None
    call = s.get_calls[0]
    assert call["url"] == "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    assert call["params"] == {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "003490"}
    h = call["headers"]
    assert h["tr_id"] == "FHKST01010100" and h["custtype"] == "P" and h["authorization"] == f"Bearer {TOKEN}"
    assert h["appkey"] == APP_KEY and h["appsecret"] == APP_SECRET
    t = q.to_tick()
    assert t.code == "003490" and t.cum_volume == 1234567 and t.source == "kis-rest"
    assert APP_SECRET not in repr(c)


def test_rest_unsigned_change_gets_sign_from_sign_field(tmp_path):
    out = dict(PRICE_OUT, prdy_vrss="550", prdy_ctrt="1.75")
    c, _, _ = rest_client(tmp_path, [Resp(200, {"rt_cd": "0", "output": out})])
    q = c.quote("003490")
    assert q.change == -550 and q.change_pct == -1.75


def test_rest_retries_rate_limit_and_5xx(tmp_path):
    c, s, slept = rest_client(tmp_path, [
        Resp(500, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."}),
        Resp(502, None),
        Resp(200, {"rt_cd": "0", "output": PRICE_OUT}),
    ])
    assert c.quote("003490").price == 30950
    assert len(s.get_calls) == 3 and len(slept) == 2 and slept[0] >= 1.0


def test_rest_gives_up_with_rate_limit_error(tmp_path):
    busy = Resp(500, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."})
    c, s, _ = rest_client(tmp_path, [busy] * 4)
    with pytest.raises(KISRateLimitError) as ei:
        c.quote("003490")
    assert ei.value.code == "EGW00201" and len(s.get_calls) == 4


def test_rest_expired_token_is_reissued_once(tmp_path):
    cfg = make_cfg(tmp_path)
    clock = Clock()
    s = FakeSession(posts=[token_ok(), Resp(200, {"access_token": "NEWTOKEN" + "n" * 50,
                                                  "access_token_token_expired": "2026-10-09 12:00:00"})],
                    gets=[Resp(500, {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}),
                          Resp(200, {"rt_cd": "0", "output": PRICE_OUT})])
    tm = TokenManager(cfg, session=s, clock=clock, sleep=clock.sleep)
    c = KISRestClient(cfg, tm, session=s, sleep=lambda x: None, limiter=RateLimiter(0))
    assert c.quote("003490").price == 30950
    assert len(s.post_calls) == 2
    assert s.get_calls[1]["headers"]["authorization"].startswith("Bearer NEWTOKEN")
    assert clock.slept and clock.slept[0] > 55     # 재발급도 1분 1회 한도를 지킨다


def test_rest_business_error_is_korean_and_secret_free(tmp_path):
    c, _, _ = rest_client(tmp_path, [Resp(200, {"rt_cd": "1", "msg_cd": "OPSQ0002",
                                                "msg1": f"없는 종목 {APP_KEY}"})])
    with pytest.raises(KISError) as ei:
        c.quote("999999")
    assert ei.value.code == "OPSQ0002" and "없는 종목" in str(ei.value) and APP_KEY not in str(ei.value)


def test_rest_daily_ohlcv(tmp_path):
    rows = [{"stck_bsop_date": "20261008", "stck_oprc": "100", "stck_hgpr": "110", "stck_lwpr": "95",
             "stck_clpr": "105", "acml_vol": "1000", "acml_tr_pbmn": "105000"},
            {"stck_bsop_date": "20261007", "stck_oprc": "98", "stck_hgpr": "101", "stck_lwpr": "97",
             "stck_clpr": "100", "acml_vol": "900", "acml_tr_pbmn": "90000"}]
    c, s, _ = rest_client(tmp_path, [Resp(200, {"rt_cd": "0", "output1": {}, "output2": rows})])
    df = c.daily("005930", "20261001", kis.date(2026, 10, 8))
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "value"]
    assert df.index.is_monotonic_increasing and df["close"].tolist() == [100, 105]
    p = s.get_calls[0]["params"]
    assert s.get_calls[0]["headers"]["tr_id"] == "FHKST03010100"
    assert p["FID_INPUT_DATE_2"] == "20261008" and p["FID_PERIOD_DIV_CODE"] == "D" and p["FID_ORG_ADJ_PRC"] == "0"


def test_rate_limiter_spacing():
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s

    rl = RateLimiter(15, clock=lambda: t[0], sleep=sleep)
    for _ in range(16):
        rl.wait()
    assert t[0] == pytest.approx(15 / 15, abs=1e-9)   # 16번째 호출은 1초 뒤
    assert len(slept) == 15


# ---------------------------------------------------------------- 웹소켓 프레임
def ccnl_fields(code="005930", hms="093015", price="70000", sign="2", chg="500", pct="0.72", vol="1234567",
                val="86000000000", ymd="20261008", ncols=47):
    f = [""] * ncols
    f[0], f[1], f[2], f[3], f[4], f[5] = code, hms, price, sign, chg, pct
    f[7], f[8], f[9], f[12], f[13], f[14], f[33] = "69500", "70100", "69400", "10", vol, val, ymd
    return f


def frame(*records, tr=TR_CCNL_KRX):
    flat = [x for r in records for x in r]
    return f"0|{tr}|{len(records):03d}|" + "^".join(flat)


def test_parse_single_record_frame_and_tick():
    fr = parse_frame(frame(ccnl_fields()))
    assert fr.kind == "data" and fr.tr_id == TR_CCNL_KRX and len(fr.records) == 1
    rec = fr.records[0]
    assert len(CCNL_COLUMNS) == 47 and rec["MKSC_SHRN_ISCD"] == "005930" and rec["ACML_VOL"] == "1234567"
    t = tick_from_record(rec)
    assert (t.code, t.price, t.change_pct, t.cum_volume, t.cum_value) == ("005930", 70000, 0.72, 1234567, 86e9)
    assert (t.open, t.high, t.low, t.change) == (69500, 70100, 69400, 500)
    assert (t.time.year, t.time.month, t.time.day, t.time.hour, t.time.minute, t.time.second) == (
        2026, 10, 8, 9, 30, 15)
    assert t.time.utcoffset().total_seconds() == 9 * 3600


def test_parse_multi_record_frames():
    fr = parse_frame(frame(ccnl_fields("005930"), ccnl_fields("000660", price="200000"),
                           ccnl_fields("003490", price="30950")))
    assert [r["MKSC_SHRN_ISCD"] for r in fr.records] == ["005930", "000660", "003490"]
    assert [tick_from_record(r).price for r in fr.records] == [70000, 200000, 30950]
    # 옛 46컬럼 형식(MARKET_CLS_CODE 없음)도 건수로 나눠 읽는다
    legacy = parse_frame(frame(ccnl_fields(ncols=46), ccnl_fields("000660", ncols=46)))
    assert [r["MKSC_SHRN_ISCD"] for r in legacy.records] == ["005930", "000660"]
    # 통합(H0UNCNT0)도 같은 위치
    un = parse_frame(frame(ccnl_fields(), tr=TR_CCNL_TOTAL))
    assert un.tr_id == TR_CCNL_TOTAL and "CNTG_CLS_CODE" in un.records[0]


def test_tick_sign_and_bad_records():
    t = tick_from_record(dict(zip(CCNL_COLUMNS, ccnl_fields(sign="5", chg="300", pct="0.43"))))
    assert t.change == -300 and t.change_pct == -0.43
    t2 = tick_from_record(dict(zip(CCNL_COLUMNS, ccnl_fields(sign="5", chg="-300", pct="-0.43"))))
    assert t2.change == -300 and t2.change_pct == -0.43
    assert tick_from_record(dict(zip(CCNL_COLUMNS, ccnl_fields(price="0")))) is None
    assert tick_from_record({}) is None


def test_parse_control_pingpong_encrypted_unknown():
    ping = '{"header":{"tr_id":"PINGPONG","datetime":"20261008093000"}}'
    assert parse_frame(ping).kind == "pingpong"
    ok = parse_frame(json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930", "encrypt": "N"},
                                 "body": {"rt_cd": "0", "msg_cd": "OPSP0000", "msg1": "SUBSCRIBE SUCCESS",
                                          "output": {"iv": "IVIVIVIVIVIVIVIV", "key": "K" * 32}}}))
    assert ok.kind == "control" and ok.ok and ok.tr_key == "005930" and ok.msg == "SUBSCRIBE SUCCESS"
    assert "K" * 32 not in repr(ok)     # 암호화 키는 repr 에 나오지 않는다
    bad = parse_frame(json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
                                  "body": {"rt_cd": "1", "msg_cd": "OPSP0008", "msg1": "MAX SUBSCRIBE OVER"}}))
    assert bad.kind == "control" and bad.ok is False
    enc = parse_frame("1|H0STCNI0|001|c2VjcmV0")
    assert enc.kind == "encrypted" and enc.tr_id == "H0STCNI0"
    assert parse_frame("garbage").kind == "unknown"
    assert parse_frame(b"").kind == "unknown"
    assert parse_frame(frame(ccnl_fields()).encode()).kind == "data"


def test_subscribe_message_and_endpoint():
    m = json.loads(subscribe_message(APPROVAL, TR_CCNL_KRX, "005930"))
    assert m == {"header": {"approval_key": APPROVAL, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
                 "body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}}}
    assert json.loads(subscribe_message(APPROVAL, TR_CCNL_KRX, "005930", False))["header"]["tr_type"] == "2"
    assert ws_endpoint("ws://ops.koreainvestment.com:21000") == "ws://ops.koreainvestment.com:21000/tryitout"
    assert ws_endpoint("ws://ops.koreainvestment.com:21000/") == "ws://ops.koreainvestment.com:21000/tryitout"
    assert ws_endpoint("ws://host:1/custom") == "ws://host:1/custom"


def test_issue_approval_key(tmp_path):
    cfg = make_cfg(tmp_path)
    s = FakeSession(posts=[Resp(200, {"approval_key": APPROVAL})])
    assert issue_approval_key(cfg, s) == APPROVAL
    call = s.post_calls[0]
    assert call["url"].endswith("/oauth2/Approval")
    assert call["body"] == {"grant_type": "client_credentials", "appkey": APP_KEY, "secretkey": APP_SECRET}
    s = FakeSession(posts=[Resp(403, {"error_code": "EGW00105", "error_description": "x"})])
    with pytest.raises(KISAuthError) as ei:
        issue_approval_key(cfg, s)
    assert ei.value.code == "EGW00105" and APP_SECRET not in str(ei.value)


# ---------------------------------------------------------------- 웹소켓 클라이언트 (가짜 연결)
class FakeWS:
    def __init__(self, frames, error=None):
        self.frames, self.error = list(frames), error
        self.sent, self.pongs = [], []

    async def send(self, m):
        self.sent.append(json.loads(m))

    async def pong(self, data=b""):
        self.pongs.append(data)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for f in self.frames:
            await asyncio.sleep(0)
            yield f
        if self.error is not None:
            raise self.error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def connector(sessions, urls):
    it = iter(sessions)

    def connect(url):
        urls.append(url)
        return next(it)
    return connect


async def _nosleep(_s=0):
    await asyncio.sleep(0)


def test_websocket_client_subscribes_pongs_parses_and_resubscribes(tmp_path):
    cfg = make_cfg(tmp_path)
    ping = '{"header":{"tr_id":"PINGPONG","datetime":"20261008093000"}}'
    ok = json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930", "encrypt": "N"},
                     "body": {"rt_cd": "0", "msg_cd": "OPSP0000", "msg1": "SUBSCRIBE SUCCESS",
                              "output": {"iv": "x" * 16, "key": "y" * 32}}})
    ws1 = FakeWS([ok, ping, frame(ccnl_fields("005930"), ccnl_fields("000660", price="200000"))],
                 error=ConnectionResetError("closed"))
    ws2 = FakeWS([frame(ccnl_fields("000660", price="201000"))])
    urls, status, approvals = [], [], []

    def approval():
        approvals.append(1)
        return APPROVAL

    client = KISWebSocketClient(cfg, ["005930", "000660"], connect=connector([ws1, ws2], urls), approval=approval,
                                on_status=status.append, send_interval=0, sleep=_nosleep)

    async def collect():
        got = []
        async for t in client.ticks():
            got.append(t)
            if len(got) == 3:
                client.stop()
                break
        return got

    ticks = asyncio.run(collect())
    assert [(t.code, t.price) for t in ticks] == [("005930", 70000), ("000660", 200000), ("000660", 201000)]
    assert urls == ["ws://ops.koreainvestment.com:21000/tryitout"] * 2
    assert ws1.pongs == [ping]                                   # PINGPONG 은 받은 그대로 pong
    for ws in (ws1, ws2):                                        # 재접속 때 전 종목 재구독
        assert [m["body"]["input"]["tr_key"] for m in ws.sent] == ["005930", "000660"]
        assert all(m["header"]["tr_type"] == "1" and m["body"]["input"]["tr_id"] == "H0STCNT0" for m in ws.sent)
    assert len(approvals) == 1                                   # 접속키는 재사용
    assert client.connects == 2 and client.ticks_received == 3
    assert any("재연결" in m for m in status)
    joined = " ".join(status)
    assert APPROVAL not in joined and APP_SECRET not in joined and "y" * 32 not in joined


def test_websocket_client_caps_subscriptions_at_40(tmp_path):
    cfg = make_cfg(tmp_path)
    status = []
    codes = [f"{i:06d}" for i in range(45)]
    c = KISWebSocketClient(cfg, codes, approval=lambda: APPROVAL, on_status=status.append)
    assert len(c.codes) == 40 and c.dropped == codes[40:]
    assert any("40종목" in m and "5종목" in m for m in status)


def test_websocket_client_gives_up_after_max_failures(tmp_path):
    cfg = make_cfg(tmp_path)

    def connect(url):
        raise OSError("refused")

    c = KISWebSocketClient(cfg, ["005930"], connect=connect, approval=lambda: APPROVAL, max_failures=3,
                           sleep=_nosleep)

    async def run():
        async for _ in c.ticks():
            pass

    with pytest.raises(KISError) as ei:
        asyncio.run(run())
    assert ei.value.code == "WS" and c.failures == 3


def test_websocket_client_stops_on_bad_secret(tmp_path):
    cfg = make_cfg(tmp_path)

    def approval():
        raise KISAuthError(kis.ERROR_HINTS["EGW00105"], "EGW00105")

    c = KISWebSocketClient(cfg, ["005930"], connect=lambda u: FakeWS([]), approval=approval, sleep=_nosleep)

    async def run():
        async for _ in c.ticks():
            pass

    with pytest.raises(KISAuthError):
        asyncio.run(run())


def test_websocket_control_messages_update_state(tmp_path):
    cfg = make_cfg(tmp_path)
    status = []
    c = KISWebSocketClient(cfg, ["005930"], approval=lambda: APPROVAL, on_status=status.append)
    c._key = APPROVAL
    c._on_control(parse_frame(json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
                                          "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"}})))
    assert c.subscribed == {"005930"} and any("구독 완료" in m for m in status)
    c._on_control(parse_frame(json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "000660"},
                                          "body": {"rt_cd": "1", "msg1": "MAX SUBSCRIBE OVER"}})))
    assert any("구독 한도" in m for m in status)
    c._on_control(parse_frame(json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "000660"},
                                          "body": {"rt_cd": "1", "msg1": "invalid approval : NOT FOUND"}})))
    assert c._key is None


def test_websocket_client_with_real_websockets_library_on_localhost(tmp_path):
    """실제 websockets 라이브러리 경로(_open·pong)를 로컬 서버로 확인 (외부 네트워크 없음)."""
    websockets = pytest.importorskip("websockets")
    from websockets.asyncio.server import serve

    received = []

    async def handler(ws):
        for _ in range(2):
            received.append(json.loads(await ws.recv()))
        await ws.send(json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930", "encrypt": "N"},
                                  "body": {"rt_cd": "0", "msg_cd": "OPSP0000", "msg1": "SUBSCRIBE SUCCESS"}}))
        await ws.send('{"header":{"tr_id":"PINGPONG","datetime":"20261008093000"}}')
        await ws.send(frame(ccnl_fields("005930"), ccnl_fields("000660", price="200000")))
        await ws.wait_closed()

    async def main():
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            cfg = make_cfg(tmp_path)
            cfg.ws_url = f"ws://127.0.0.1:{port}"
            client = KISWebSocketClient(cfg, ["005930", "000660"], approval=lambda: APPROVAL, send_interval=0,
                                        max_failures=1)
            got = []
            async for t in client.ticks():
                got.append(t)
                if len(got) == 2:
                    client.stop()
                    break
            return got, client

    got, client = asyncio.run(asyncio.wait_for(main(), 10))
    assert [(t.code, t.price) for t in got] == [("005930", 70000), ("000660", 200000)]
    assert [m["body"]["input"]["tr_key"] for m in received] == ["005930", "000660"]
    assert all(m["header"]["approval_key"] == APPROVAL for m in received)
    assert client.subscribed == {"005930"} and client.connects == 1


# ---------------------------------------------------------------- 리뷰 수정 회귀 테스트
HOLIDAY_ROWS = [{"bass_dt": "20261008", "wday_dvsn_cd": "05", "bzdy_yn": "Y", "tr_day_yn": "Y", "opnd_yn": "Y",
                 "sttl_day_yn": "Y"},
                {"bass_dt": "20261009", "wday_dvsn_cd": "06", "bzdy_yn": "N", "tr_day_yn": "N", "opnd_yn": "N",
                 "sttl_day_yn": "N"}]


def test_open_day_uses_holiday_api_once_and_caches(tmp_path):
    c, s, _ = rest_client(tmp_path, [Resp(200, {"rt_cd": "0", "output": HOLIDAY_ROWS})])
    cache = tmp_path / "holidays.json"
    clock = Clock()
    assert c.open_day(kis.date(2026, 10, 8), cache_path=cache, clock=clock) is True
    call = s.get_calls[0]
    assert call["url"].endswith("/uapi/domestic-stock/v1/quotations/chk-holiday")
    assert call["headers"]["tr_id"] == "CTCA0903R" and call["params"]["BASS_DT"] == "20261008"
    # 응답에 들어 있던 다음 날(한글날)은 다시 묻지 않고 캐시로
    assert c.open_day(kis.date(2026, 10, 9), cache_path=cache, clock=clock) is False
    assert len(s.get_calls) == 1
    text = cache.read_text(encoding="utf-8")
    assert TOKEN not in text and APP_SECRET not in text and APP_KEY not in text
    # 기본 위치는 토큰 캐시 옆 (저장소 밖)
    assert c.cfg.holiday_cache_path.parent == c.cfg.token_cache_path.parent


def test_open_day_failure_is_unknown_and_not_retried_soon(tmp_path):
    busy = Resp(500, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."})
    c, s, _ = rest_client(tmp_path, [busy] * 4)
    cache = tmp_path / "holidays.json"
    clock = Clock()
    assert c.open_day(kis.date(2026, 10, 8), cache_path=cache, clock=clock) is None
    n = len(s.get_calls)
    assert c.open_day(kis.date(2026, 10, 8), cache_path=cache, clock=clock) is None   # 12시간 안에는 다시 묻지 않음
    assert len(s.get_calls) == n
    paper = KISConfig.load(write_cfg(tmp_path, filled().replace('paper_app: "모의투자 앱키"', f'paper_app: "{APP_KEY}"')
                                     .replace('paper_sec: "모의투자 앱키 시크릿"', f'paper_sec: "{APP_SECRET}"'),
                                     name="paper.yaml"), env="vps")
    s2 = FakeSession()
    pc = KISRestClient(paper, TokenManager(paper, session=s2), session=s2, limiter=RateLimiter(0))
    assert pc.open_day(kis.date(2026, 10, 8), cache_path=cache) is None and s2.get_calls == []


def test_paper_env_uses_slower_rate_limits(tmp_path):
    prod = make_cfg(tmp_path)
    paper = KISConfig.from_mapping({"paper_app": APP_KEY, "paper_sec": APP_SECRET,
                                    "vps": "https://openapivts.koreainvestment.com:29443",
                                    "vops": "ws://ops.koreainvestment.com:31000"}, env="vps")
    assert KISRestClient(prod, TokenManager(prod)).limiter.interval == pytest.approx(1 / 15)
    paper_tm = TokenManager(paper, cache_path=tmp_path / "t.json")   # 경로 없는 설정 → 캐시도 tmp 로
    assert KISRestClient(paper, paper_tm).limiter.interval == pytest.approx(0.5)
    assert KISWebSocketClient(prod, ["005930"]).send_interval == pytest.approx(0.05)
    assert KISWebSocketClient(paper, ["005930"]).send_interval == pytest.approx(0.5)
    assert KISWebSocketClient(paper, ["005930"], send_interval=0).send_interval == 0


def _ctl(msg, rt_cd="1", code="005930", msg_cd="OPSP0011"):
    return json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": code},
                       "body": {"rt_cd": rt_cd, "msg_cd": msg_cd, "msg1": msg}})


def test_websocket_reconnects_on_already_in_use_and_approval_rejection(tmp_path):
    cfg = make_cfg(tmp_path)
    ws1 = FakeWS([_ctl("ALREADY IN USE appkey"), frame(ccnl_fields("005930", price="11111"))])
    ws2 = FakeWS([_ctl("invalid approval : NOT FOUND"), frame(ccnl_fields("005930", price="22222"))])
    ws3 = FakeWS([frame(ccnl_fields("005930", price="70000"))])
    urls, status, approvals = [], [], []

    def approval():
        approvals.append(1)
        return f"KEY{len(approvals)}" + "q" * 30

    client = KISWebSocketClient(cfg, ["005930"], connect=connector([ws1, ws2, ws3], urls), approval=approval,
                                on_status=status.append, send_interval=0, sleep=_nosleep, max_failures=5)

    async def first():
        async for t in client.ticks():
            client.stop()
            return t

    t = asyncio.run(first())
    assert t.price == 70000                     # 거부 뒤에 온 체결(11111·22222)은 쓰지 않고 연결을 닫았다
    assert client.connects == 3 and len(approvals) == 3   # 거부될 때마다 접속키를 새로 받았다
    joined = " ".join(status)
    assert "이미 실시간 접속 중" in joined and "접속키가 거부" in joined and "재연결" in joined
    assert "KEY1" not in joined and "KEY2" not in joined


def test_websocket_other_invalid_messages_keep_key_and_are_scrubbed(tmp_path):
    cfg = make_cfg(tmp_path)
    status = []
    c = KISWebSocketClient(cfg, ["005930"], on_status=status.append)
    key = "KEYXYZ" + "q" * 30
    c._key = key
    assert c._on_control(parse_frame(_ctl(f"invalid tr_key [{key}]", code="99999X"))) is None
    assert c._key == key                        # 접속키를 버리지 않는다
    assert any("구독 응답 99999X [OPSP0011]" in m for m in status)
    assert all(key not in m for m in status)    # 서버가 접속키를 되돌려 보내도 가린다


def test_rest_error_scrubs_access_token(tmp_path):
    c, _, _ = rest_client(tmp_path, [Resp(200, {"rt_cd": "1", "msg_cd": "OPSQ9999", "msg1": f"bad {TOKEN}"})])
    with pytest.raises(KISError) as ei:
        c.quote("005930")
    assert TOKEN not in str(ei.value) and "bad" in str(ei.value)
