"""한국투자증권(KIS) Open API — 시세 '조회 전용' 클라이언트.

주문 기능은 없다. 접근토큰 발급, 현재가·일봉 조회(REST), 실시간 체결가(웹소켓)만 다루며 매수·매도·정정·취소
API 는 구현하지 않는다. 계좌번호는 설정 형식 점검에만 쓴다.

출처: 한국투자증권 공식 샘플 open-trading-api (examples_user/kis_auth.py, domestic_stock/domestic_stock_functions*.py)
  접근토큰       POST {prod}/oauth2/tokenP  {"grant_type":"client_credentials","appkey","appsecret"}
                 → access_token, access_token_token_expired('YYYY-MM-DD HH:MM:SS', KST), expires_in(초).
                 1분에 1회만 발급되고(EGW00133) 유효 24시간, 발급할 때마다 알림톡이 간다 → 파일에 캐시해 재사용.
  웹소켓 접속키  POST {prod}/oauth2/Approval {"grant_type","appkey","secretkey"} → approval_key
  현재가         GET /uapi/domestic-stock/v1/quotations/inquire-price  tr_id FHKST01010100
                 (FID_COND_MRKT_DIV_CODE J=KRX · NX=NXT · UN=통합, FID_INPUT_ISCD=종목코드)
  일봉           GET /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice  tr_id FHKST03010100 (1회 최대 100봉)
  휴장일         GET /uapi/domestic-stock/v1/quotations/chk-holiday  tr_id CTCA0903R (BASS_DT → output[].opnd_yn 개장일여부)
                 '가급적 1일 1회 호출' 요청이 있어 결과를 파일에 캐시한다. 모의투자는 지원하지 않는 것으로 보고 부르지 않는다.
  호출 간격      실전 초당 15회 이하 · 모의투자 초당 2회 이하 (공식 샘플 _smartSleep 0.05초 / 0.5초)
  실시간 체결가  웹소켓 {ops}/tryitout, 구독 메시지
                 {"header":{"approval_key","custtype":"P","tr_type":"1"(등록)|"2"(해제),"content-type":"utf-8"},
                  "body":{"input":{"tr_id":"H0STCNT0","tr_key":"005930"}}}
                 H0STCNT0 = KRX 체결가, H0UNCNT0 = KRX+NXT 통합 체결가 (컬럼 47개 동일, 22번째 이름만 다름)
  수신 프레임    '0|H0STCNT0|003|f1^f2^...' = 암호화 여부|TR|건수|필드. 건수 > 1 이면 레코드가 '^' 로 이어 붙는다.
                 '1|...' 은 AES-256-CBC 암호화 (체결통보 H0STCNI0 전용 — 시세에는 쓰이지 않음).
                 JSON 은 제어 메시지(구독 결과·PINGPONG). PINGPONG 은 받은 내용 그대로 pong 으로 응답한다.
  실시간 구독은 세션당 40건까지.

보안
  - 앱키·시크릿·토큰·접속키 원문은 출력·로그·예외 메시지·repr 어디에도 넣지 않는다 (redact / scrub).
  - 토큰 캐시는 설정 파일 옆(기본 ~/KIS/config/chart_screener_token.json)에 두고 저장소 안에는 두지 않는다.
  - 설정 파일은 PyYAML 없이 '키: "값"  # 주석' 형식만 읽는 작은 파서로 읽는다.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterable

import requests

from ..config import PROJECT_ROOT

KST = timezone(timedelta(hours=9))

CONFIG_ENV = "CHART_SCREENER_KIS_CONFIG"
DEFAULT_CONFIG = Path.home() / "KIS" / "config" / "kis_devlp.yaml"
TOKEN_FILE = "chart_screener_token.json"
HOLIDAY_FILE = "chart_screener_holidays.json"   # 개장일 조회 결과 캐시 (비밀값 없음, 토큰 캐시 옆)
DEFAULT_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

PATH_TOKEN = "/oauth2/tokenP"
PATH_APPROVAL = "/oauth2/Approval"
PATH_PRICE = "/uapi/domestic-stock/v1/quotations/inquire-price"
PATH_DAILY = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
PATH_HOLIDAY = "/uapi/domestic-stock/v1/quotations/chk-holiday"
TR_PRICE = "FHKST01010100"
TR_DAILY = "FHKST03010100"
TR_HOLIDAY = "CTCA0903R"      # 국내휴장일조회 (1일 1회 권장)
TR_CCNL_KRX = "H0STCNT0"      # 실시간 체결가 (KRX)
TR_CCNL_NXT = "H0NXCNT0"      # 실시간 체결가 (NXT)
TR_CCNL_TOTAL = "H0UNCNT0"    # 실시간 체결가 (KRX+NXT 통합)
WS_PATH = "/tryitout"         # 공식 샘플 examples_user: KISWebSocket(api_url="/tryitout")
MAX_WS_SUBSCRIPTIONS = 40     # 세션당 실시간 구독 한도
# 호출 간격 (공식 샘플 kis_auth.py _smartSleep: 실전 0.05초, 모의투자 0.5초)
REST_PER_SEC = {"prod": 15.0, "vps": 2.0}
WS_SEND_INTERVAL = {"prod": 0.05, "vps": 0.5}

# 실시간 체결가 컬럼 (domestic_stock_functions_ws.py ccnl_krx). 통합·NXT 는 21번 컬럼 이름만 CNTG_CLS_CODE.
CCNL_COLUMNS = [
    "MKSC_SHRN_ISCD", "STCK_CNTG_HOUR", "STCK_PRPR", "PRDY_VRSS_SIGN", "PRDY_VRSS", "PRDY_CTRT",
    "WGHN_AVRG_STCK_PRC", "STCK_OPRC", "STCK_HGPR", "STCK_LWPR", "ASKP1", "BIDP1", "CNTG_VOL", "ACML_VOL",
    "ACML_TR_PBMN", "SELN_CNTG_CSNU", "SHNU_CNTG_CSNU", "NTBY_CNTG_CSNU", "CTTR", "SELN_CNTG_SMTN",
    "SHNU_CNTG_SMTN", "CCLD_DVSN", "SHNU_RATE", "PRDY_VOL_VRSS_ACML_VOL_RATE", "OPRC_HOUR",
    "OPRC_VRSS_PRPR_SIGN", "OPRC_VRSS_PRPR", "HGPR_HOUR", "HGPR_VRSS_PRPR_SIGN", "HGPR_VRSS_PRPR",
    "LWPR_HOUR", "LWPR_VRSS_PRPR_SIGN", "LWPR_VRSS_PRPR", "BSOP_DATE", "NEW_MKOP_CLS_CODE", "TRHT_YN",
    "ASKP_RSQN1", "BIDP_RSQN1", "TOTAL_ASKP_RSQN", "TOTAL_BIDP_RSQN", "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL", "PRDY_SMNS_HOUR_ACML_VOL_RATE", "HOUR_CLS_CODE", "MRKT_TRTM_CLS_CODE",
    "VI_STND_PRC", "MARKET_CLS_CODE",
]
_CCNL_COLUMNS_UN = [("CNTG_CLS_CODE" if c == "CCLD_DVSN" else c) for c in CCNL_COLUMNS]
COLUMNS_BY_TR = {TR_CCNL_KRX: CCNL_COLUMNS, TR_CCNL_NXT: _CCNL_COLUMNS_UN, TR_CCNL_TOTAL: _CCNL_COLUMNS_UN}

# KIS 오류 코드 → 한글 안내 (비밀값 없음)
ERROR_HINTS = {
    "EGW00103": "유효하지 않은 AppKey 입니다 — kis_devlp.yaml 의 my_app 을 KIS Developers 에서 다시 복사하세요.",
    "EGW00105": ("유효하지 않은 AppSecret 입니다 — my_sec 를 KIS Developers 에서 다시 복사하세요 "
                 "(보통 180자, 줄바꿈·공백 없이 한 줄, 앱키와 짝이 맞는 시크릿인지 확인)."),
    "EGW00121": "유효하지 않은 접근토큰입니다 — 토큰을 다시 발급합니다.",
    "EGW00123": "접근토큰이 만료되었습니다 — 토큰을 다시 발급합니다.",
    "EGW00133": "접근토큰은 1분에 1회만 발급됩니다 — 1분 뒤 다시 시도하세요.",
    "EGW00201": "초당 호출 한도를 넘었습니다 — 잠시 쉬었다가 다시 요청합니다.",
}
_FATAL_CODES = {"EGW00103", "EGW00105", "WS_LIB"}  # 다시 시도해도 소용없는 오류


# ---------------------------------------------------------------- 오류
class KISError(RuntimeError):
    """KIS 오류. message 는 한글이며 비밀값을 담지 않는다."""

    def __init__(self, message: str, code: str | None = None, *, retry_after: float | None = None):
        self.code = code
        self.message = message
        self.retry_after = retry_after
        super().__init__(f"[{code}] {message}" if code else message)


class KISConfigError(KISError):
    """설정 파일 없음·형식 오류."""


class KISAuthError(KISError):
    """접근토큰·접속키 발급 실패 (앱키·시크릿 오류 등)."""


class KISRateLimitError(KISError):
    """호출·발급 한도 초과 (retry_after 초 뒤 재시도)."""


# ---------------------------------------------------------------- 비밀값 가림
def redact(value: Any, keep: int = 4) -> str:
    """비밀값 표시용: 앞 keep 글자 + '…' + 길이. 짧은 값(예시 문구 등)이나 keep=0 이면 길이만."""
    s = "" if value is None else str(value)
    if not s:
        return "(비어 있음)"
    head = s[:keep] if keep > 0 and len(s) >= max(12, keep * 3) else ""
    return f"{head}…({len(s)}자)"


def scrub(text: Any, secrets: Iterable[str | None] = ()) -> str:
    """text 안에 들어 있는 비밀값을 redact(길이만) 로 바꿔 돌려준다 (서버 메시지·예외 문구 방어)."""
    s = "" if text is None else str(text)
    for sec in secrets:
        if sec and len(sec) >= 6 and sec in s:
            s = s.replace(sec, redact(sec, 0))
    return s


# ---------------------------------------------------------------- 설정 파일 (작은 YAML 파서)
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-]*)\s*:(?:\s+|$)(.*)$")
_HANGUL = re.compile(r"[ㄱ-ㆎ가-힣]")


def _yaml_scalar(rest: str) -> tuple[str, bool]:
    """'"값"  # 주석' → (값, 따옴표 닫힘 여부)."""
    rest = rest.strip()
    if rest[:1] in ('"', "'"):
        q, i, buf = rest[0], 1, []
        while i < len(rest):
            ch = rest[i]
            if q == '"' and ch == "\\" and i + 1 < len(rest):
                nxt = rest[i + 1]
                buf.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                i += 2
                continue
            if ch == q:
                if q == "'" and rest[i + 1:i + 2] == "'":  # 작은따옴표 안의 '' = '
                    buf.append("'")
                    i += 2
                    continue
                return "".join(buf), True
            buf.append(ch)
            i += 1
        return "".join(buf), False
    m = re.search(r"\s#", rest)
    val = rest[:m.start()] if m else rest
    return ("" if val.startswith("#") else val.strip()), True


def parse_simple_yaml(text: str, issues: list[str] | None = None) -> dict[str, str]:
    """'키: "값"  # 주석' 형식의 평평한 YAML 만 읽는다 (공식 샘플 kis_devlp.yaml 양식). 들여쓴 줄·목록은 무시.

    issues 에 형식 문제(비밀값 없는 한글 설명)를 덧붙인다: 닫히지 않은 따옴표, 여러 줄로 나뉜 값, 중복 키.
    """
    out: dict[str, str] = {}
    last_key: str | None = None
    for no, line in enumerate(text.lstrip("﻿").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] in (" ", "\t"):
            if last_key is not None and issues is not None and not line.lstrip().startswith(("#", "-")):
                issues.append(f"{last_key} 값이 여러 줄로 나뉘어 있습니다 ({no}번째 줄) — 한 줄로 붙여 넣으세요")
            continue
        m = _KEY_RE.match(line.rstrip())
        if not m:
            last_key = None
            continue
        key = m.group(1)
        val, closed = _yaml_scalar(m.group(2))
        if issues is not None:
            if not closed:
                issues.append(f"{key} 의 따옴표가 닫히지 않았습니다 ({no}번째 줄)")
            if key in out:
                issues.append(f"{key} 항목이 두 번 있습니다 ({no}번째 줄) — 마지막 값을 씁니다")
        out[key] = val
        last_key = key
    return out


# 공식 kis_devlp.yaml 의 예시 문구 (그대로 두면 '예시 문구' 로 진단)
TEMPLATE_VALUES = {
    "앱키", "앱키 시크릿", "모의투자 앱키", "모의투자 앱키 시크릿", "사용자 HTS ID", "증권계좌 8자리",
    "선물옵션계좌 8자리", "모의투자 증권계좌 8자리", "모의투자 선물옵션계좌 8자리",
}

_ENV_KEYS = {
    # env: (앱키, 시크릿, REST 주소, 웹소켓 주소, 계좌)
    "prod": ("my_app", "my_sec", "prod", "ops", "my_acct_stock"),
    "vps": ("paper_app", "paper_sec", "vps", "vops", "my_paper_stock"),
}


def resolve_config_path(path: str | Path | None = None) -> Path:
    """설정 파일 경로: 인자 → 환경변수 CHART_SCREENER_KIS_CONFIG → ~/KIS/config/kis_devlp.yaml."""
    if path:
        return Path(path).expanduser()
    env = os.environ.get(CONFIG_ENV, "").strip()
    return Path(env).expanduser() if env else DEFAULT_CONFIG


def _inside(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


@dataclass(repr=False)
class KISConfig:
    """kis_devlp.yaml 의 필요한 값. repr/str 은 비밀값을 가린다."""
    app_key: str
    app_secret: str
    base_url: str                       # REST (실전 prod / 모의 vps)
    ws_url: str                         # 웹소켓 (실전 ops / 모의 vops)
    hts_id: str = ""
    account: str = ""                   # 계좌번호 앞 8자리 (형식 점검에만 사용)
    product: str = "01"
    user_agent: str = DEFAULT_AGENT
    env: str = "prod"                   # 'prod' 실전 | 'vps' 모의투자
    path: Path | None = None
    parse_issues: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    # ---- 생성
    @classmethod
    def from_mapping(cls, d: dict, env: str = "prod", path: Path | None = None,
                     issues: list[str] | None = None) -> "KISConfig":
        if env not in _ENV_KEYS:
            raise KISConfigError(f"env 는 'prod'(실전) 또는 'vps'(모의투자)여야 합니다: {env!r}", "CONFIG")
        k_app, k_sec, k_url, k_ws, k_acct = _ENV_KEYS[env]
        missing = [k for k in (k_app, k_sec, k_url, k_ws) if k not in d]
        agent = str(d.get("my_agent") or "").strip()
        return cls(
            app_key=str(d.get(k_app, "")).strip(), app_secret=str(d.get(k_sec, "")).strip(),
            base_url=str(d.get(k_url, "")).strip(), ws_url=str(d.get(k_ws, "")).strip(),
            hts_id=str(d.get("my_htsid", "")).strip(), account=str(d.get(k_acct, "")).strip(),
            product=str(d.get("my_prod", "01")).strip() or "01",
            user_agent=agent if agent and agent.isascii() else DEFAULT_AGENT,
            env=env, path=path, parse_issues=list(issues or []), missing=missing,
        )

    @classmethod
    def load(cls, path: str | Path | None = None, env: str = "prod") -> "KISConfig":
        """설정 파일을 읽는다 (기본 ~/KIS/config/kis_devlp.yaml, 환경변수 CHART_SCREENER_KIS_CONFIG 로 변경).
        파일이 없으면 KISConfigError. 값 형식 문제는 diagnose()/warnings() 로 확인."""
        p = resolve_config_path(path)
        if not p.is_file():
            raise KISConfigError(
                f"한국투자증권 설정 파일이 없습니다: {p}\n"
                "  KIS Developers 에서 앱키·앱시크릿을 발급받아 공식 샘플의 kis_devlp.yaml 양식으로 이 위치에 저장하세요 "
                f"(다른 위치면 환경변수 {CONFIG_ENV} 또는 --config).", "CONFIG")
        issues: list[str] = []
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp949", errors="replace")
            issues.append("설정 파일이 UTF-8 이 아닙니다 — 메모장 '다른 이름으로 저장'에서 UTF-8 로 저장하세요")
        return cls.from_mapping(parse_simple_yaml(text, issues), env, p, issues)

    # ---- 표시 (비밀값 가림)
    def __repr__(self) -> str:
        acct = "8자리" if re.fullmatch(r"\d{8}", self.account or "") else ("없음" if not self.account else "형식 오류")
        return (f"KISConfig(env={self.env}, app_key={redact(self.app_key)}, app_secret={redact(self.app_secret, 0)}, "
                f"base_url={self.base_url}, ws_url={self.ws_url}, account={acct}, path={self.path})")

    __str__ = __repr__

    def summary(self) -> str:
        """사람이 읽는 한 줄 요약 (비밀값은 앞 4글자·길이만)."""
        acct = "계좌 8자리 ✓" if re.fullmatch(r"\d{8}", self.account or "") else "계좌 미설정"
        return (f"{'실전' if self.env == 'prod' else '모의투자'} · 앱키 {redact(self.app_key)} · "
                f"시크릿 {redact(self.app_secret, 0)} · {acct} · REST {self.base_url or '-'} · 웹소켓 {self.ws_url or '-'}")

    def secrets(self) -> tuple[str, ...]:
        return tuple(s for s in (self.app_key, self.app_secret) if s)

    @property
    def key_id(self) -> str:
        """토큰 캐시 구분용 해시 (원문 복원 불가)."""
        return hashlib.sha256(f"{self.env}:{self.app_key}".encode("utf-8")).hexdigest()[:16]

    @property
    def token_cache_path(self) -> Path:
        """설정 파일 옆 chart_screener_token.json. 설정이 저장소 안에 있으면 ~/KIS/config 로 (저장소에 토큰 금지)."""
        base = self.path.parent if self.path else DEFAULT_CONFIG.parent
        p = base / TOKEN_FILE
        if _inside(p, PROJECT_ROOT):
            p = DEFAULT_CONFIG.parent / TOKEN_FILE
        return p

    @property
    def holiday_cache_path(self) -> Path:
        """개장일 조회 캐시 (토큰 캐시와 같은 폴더)."""
        return self.token_cache_path.with_name(HOLIDAY_FILE)

    # ---- 진단 (한글, 비밀값 없음)
    def diagnose(self) -> list[str]:
        """연결을 막는 문제 목록 (비어 있으면 형식상 정상). 값 자체는 보여주지 않고 길이·문자 종류만 말한다."""
        k_app, k_sec, k_url, k_ws, _ = _ENV_KEYS[self.env]
        out = [f"{k} 항목이 없습니다" for k in self.missing]
        out += [m for m in self.parse_issues if _blocking_issue(m)]
        out += _key_problems(k_app, self.app_key, expect=36, lo=20, hi=64)
        out += _key_problems(k_sec, self.app_secret, expect=180, lo=100, hi=400)
        if self.app_key and self.app_key == self.app_secret:
            out.append(f"{k_app} 과 {k_sec} 가 같은 값입니다 — 시크릿 자리에 시크릿을 넣으세요")
        elif 100 <= len(self.app_key) and 20 <= len(self.app_secret) <= 64:
            out.append(f"{k_app}({len(self.app_key)}자)와 {k_sec}({len(self.app_secret)}자)가 뒤바뀐 것 같습니다")
        if self.base_url and not self.base_url.startswith("https://"):
            out.append(f"{k_url} 주소는 https:// 로 시작해야 합니다")
        if self.ws_url and not self.ws_url.startswith(("ws://", "wss://")):
            out.append(f"{k_ws} 주소는 ws:// 로 시작해야 합니다")
        return out

    def warnings(self) -> list[str]:
        """연결은 되지만 확인할 만한 점 (계좌·길이 이상·중복 키 등)."""
        k_app, k_sec, k_url, _, k_acct = _ENV_KEYS[self.env]
        out = [m for m in self.parse_issues if not _blocking_issue(m)]
        if self.app_key and 20 <= len(self.app_key) <= 64 and len(self.app_key) != 36 and self.app_key.isascii():
            out.append(f"{k_app} 길이가 {len(self.app_key)}자입니다 (보통 36자)")
        if self.app_secret and 100 <= len(self.app_secret) <= 400 and len(self.app_secret) != 180 \
                and self.app_secret.isascii():
            out.append(f"{k_sec} 길이가 {len(self.app_secret)}자입니다 (보통 180자) — 일부만 복사됐는지 확인하세요")
        acct = self.account
        if not acct or acct in TEMPLATE_VALUES or _HANGUL.search(acct):
            out.append(f"{k_acct} 이 비었거나 예시 문구입니다 (시세 조회에는 필요 없음)")
        elif not re.fullmatch(r"\d{8}", acct):
            out.append(f"{k_acct} 이 8자리 숫자가 아닙니다 ({len(acct)}자, 시세 조회에는 필요 없음)")
        if self.env == "prod" and "vts" in self.base_url:
            out.append(f"{k_url} 이 모의투자 주소입니다 — 실전은 https://openapi.koreainvestment.com:9443")
        return out

    @property
    def ok(self) -> bool:
        return not self.diagnose()


def _blocking_issue(msg: str) -> bool:
    """파싱 문제 중 값을 잘못 읽게 만드는 것(닫히지 않은 따옴표·여러 줄 값)만 오류, 나머지(중복 키·인코딩)는 경고."""
    return "따옴표" in msg or "여러 줄" in msg


def _key_problems(label: str, v: str, *, expect: int, lo: int, hi: int) -> list[str]:
    if not v:
        return [f"{label} 이 비어 있습니다"]
    if v in TEMPLATE_VALUES or _HANGUL.search(v):
        return [f"{label} 이 예시 문구 그대로입니다 (한글 포함, {len(v)}자) — KIS Developers 에서 받은 값으로 바꾸세요"]
    out = []
    if any(c.isspace() for c in v):
        out.append(f"{label} 에 공백·줄바꿈이 섞여 있습니다 ({len(v)}자) — 한 줄로 붙여 넣으세요")
    if not v.isascii():
        out.append(f"{label} 에 영문·숫자가 아닌 문자가 섞여 있습니다 ({len(v)}자) — 복사 중 섞인 특수문자 의심")
    if v[:1] in "\"'" or v[-1:] in "\"'":
        out.append(f"{label} 값 안에 따옴표가 들어가 있습니다")
    if "…" in v or "..." in v:
        out.append(f"{label} 에 말줄임표가 있습니다 — 화면에 잘려 보이는 값을 복사한 것 같습니다")
    if not lo <= len(v) <= hi:
        out.append(f"{label} 길이가 {len(v)}자입니다 (보통 {expect}자) — 전체를 복사했는지 확인하세요")
    return out


# ---------------------------------------------------------------- HTTP 공용
def _new_session(cfg: KISConfig | None = None) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = cfg.user_agent if cfg is not None else DEFAULT_AGENT
    return s


def _json_headers(cfg: KISConfig) -> dict:
    return {"Content-Type": "application/json", "Accept": "text/plain", "charset": "UTF-8",
            "User-Agent": cfg.user_agent}


def _json(r) -> dict:
    try:
        js = r.json()
    except Exception:
        return {}
    return js if isinstance(js, dict) else {}


def _error_of(js: dict, status: int) -> tuple[str, str]:
    code = str(js.get("error_code") or js.get("msg_cd") or f"HTTP{status}")
    msg = str(js.get("error_description") or js.get("msg1") or "")
    return code, msg


def _hint(code: str, msg: str, secrets: Iterable[str] = ()) -> str:
    if code in ERROR_HINTS:
        return ERROR_HINTS[code]
    msg = scrub(msg, secrets).strip()
    return f"KIS 응답: {msg}" if msg else "KIS 가 오류를 돌려줬습니다"


def _num(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("nan")


def _signed(v: float, sign) -> float:
    """전일 대비 부호(1 상한 · 2 상승 · 3 보합 · 4 하한 · 5 하락)를 값에 반영 (값이 이미 부호를 가지면 그대로)."""
    if v == v and v > 0 and str(sign).strip() in ("4", "5"):
        return -v
    return v


def now_kst() -> datetime:
    return datetime.now(KST)


# ---------------------------------------------------------------- 접근토큰
def _token_expiry(js: dict, now: float) -> float:
    s = js.get("access_token_token_expired")
    if s:
        try:
            return datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).timestamp()
        except ValueError:
            pass
    try:
        secs = float(js.get("expires_in"))
        if secs > 0:
            return now + secs
    except (TypeError, ValueError):
        pass
    return now + 6 * 3600


class TokenManager:
    """접근토큰 발급·캐시. 만료 10분 전까지 캐시(설정 파일 옆 JSON)를 재사용하고, 1분 1회 발급 한도를 지킨다.

    캐시 형식: {"version":1, "tokens":{key_id:{token, expires_at, issued_at, env}}, "last_issue_at":{key_id: epoch}}
    key_id 는 앱키 해시라 앱키를 바꾸면 새 토큰을 받는다. 토큰 값은 어디에도 출력하지 않는다.
    """
    REFRESH_MARGIN = 600.0   # 만료 10분 전부터 새로 발급
    ISSUE_GAP = 61.0         # 1분 1회 발급 한도 + 여유

    def __init__(self, cfg: KISConfig, *, cache_path: str | Path | None = None, session=None, timeout: float = 10.0,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 wait_on_limit: bool = True, notice: Callable[[str], None] | None = None):
        self.cfg = cfg
        self.cache_path = Path(cache_path) if cache_path else cfg.token_cache_path
        self.session = session or _new_session(cfg)
        self.timeout = timeout
        self._clock, self._sleep = clock, sleep
        self.wait_on_limit = wait_on_limit
        self._notice = notice or (lambda msg: None)
        self._lock = threading.RLock()
        self._token: str | None = None
        self._expires_at = 0.0
        self.source: str | None = None    # 'memory' | 'cache' | 'issued'

    def __repr__(self) -> str:
        return (f"TokenManager(env={self.cfg.env}, cache={self.cache_path}, "
                f"token={'있음' if self._token else '없음'}, source={self.source})")

    @property
    def expires_at(self) -> datetime | None:
        return datetime.fromtimestamp(self._expires_at, KST) if self._token else None

    # ---- 캐시 파일
    def _load_state(self) -> dict:
        try:
            js = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return js if isinstance(js, dict) else {}

    def _save_state(self, st: dict) -> None:
        st["version"] = 1
        now = self._clock()
        toks = st.get("tokens")
        if isinstance(toks, dict):  # 만료된 토큰 정리
            st["tokens"] = {k: v for k, v in toks.items()
                            if isinstance(v, dict) and float(v.get("expires_at", 0) or 0) > now}
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_name(self.cache_path.name + ".tmp")
            tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.cache_path)
        except OSError:
            pass  # 캐시 저장 실패는 치명적이지 않다 (다음 실행에 다시 발급)

    # ---- 공개 API
    def get(self, force: bool = False) -> str:
        """유효한 접근토큰. 메모리 → 캐시 파일 → 새 발급 순."""
        with self._lock:
            now = self._clock()
            if not force:
                if self._token and now < self._expires_at - self.REFRESH_MARGIN:
                    self.source = "memory"
                    return self._token
                ent = (self._load_state().get("tokens") or {}).get(self.cfg.key_id)
                if isinstance(ent, dict) and isinstance(ent.get("token"), str) and ent["token"]:
                    exp = float(ent.get("expires_at", 0) or 0)
                    if now < exp - self.REFRESH_MARGIN:
                        self._token, self._expires_at, self.source = ent["token"], exp, "cache"
                        return self._token
            return self._issue()

    def invalidate(self, rejected: str | None = None) -> None:
        """서버가 토큰을 거부했을 때(EGW00121·EGW00123): 메모리·캐시에서 지운다.

        rejected = 거부된 요청에 실었던 토큰. 여러 스레드가 같은 관리자를 쓸 때, 다른 스레드가 이미 새 토큰을 받았으면
        (지금 토큰 ≠ rejected) 그 새 토큰은 지우지 않는다 — 지우면 1분 1회 발급 한도(EGW00133)에 걸린다."""
        with self._lock:
            if rejected is not None and self._token and self._token != rejected:
                return
            self._token, self._expires_at = None, 0.0
            st = self._load_state()
            if isinstance(st.get("tokens"), dict):
                ent = st["tokens"].get(self.cfg.key_id)
                if rejected is not None and isinstance(ent, dict) and ent.get("token") not in (None, rejected):
                    return
                st["tokens"].pop(self.cfg.key_id, None)
                self._save_state(st)

    def _issue(self) -> str:
        url = self.cfg.base_url.rstrip("/") + PATH_TOKEN
        body = {"grant_type": "client_credentials", "appkey": self.cfg.app_key, "appsecret": self.cfg.app_secret}
        for attempt in range(2):
            last = float((self._load_state().get("last_issue_at") or {}).get(self.cfg.key_id, 0) or 0)
            wait = last + self.ISSUE_GAP - self._clock()
            if wait > 0:
                if not self.wait_on_limit:
                    raise KISRateLimitError(f"접근토큰은 1분에 1회만 발급됩니다 — {math.ceil(wait)}초 뒤 다시 시도하세요.",
                                            "EGW00133", retry_after=wait)
                self._notice(f"접근토큰 발급 한도(1분 1회) — {math.ceil(wait)}초 기다립니다")
                self._sleep(wait)
            st = self._load_state()
            st.setdefault("last_issue_at", {})[self.cfg.key_id] = self._clock()
            self._save_state(st)
            try:
                r = self.session.post(url, data=json.dumps(body), headers=_json_headers(self.cfg), timeout=self.timeout)
            except requests.RequestException as e:
                raise KISAuthError(f"접근토큰 서버에 연결하지 못했습니다 ({type(e).__name__})", "NETWORK") from None
            js = _json(r)
            tok = js.get("access_token")
            if r.status_code == 200 and isinstance(tok, str) and tok:
                now = self._clock()
                exp = _token_expiry(js, now)
                st = self._load_state()
                st.setdefault("tokens", {})[self.cfg.key_id] = {
                    "token": tok, "expires_at": exp, "issued_at": now, "env": self.cfg.env}
                self._save_state(st)
                self._token, self._expires_at, self.source = tok, exp, "issued"
                return tok
            code, msg = _error_of(js, r.status_code)
            if code == "EGW00133" and attempt == 0 and self.wait_on_limit:
                continue  # 방금 기록한 시도 시각 기준으로 61초 기다린 뒤 한 번 더
            cls = KISRateLimitError if code == "EGW00133" else KISAuthError
            raise cls(_hint(code, msg, self.cfg.secrets()) + f" (HTTP {r.status_code})", code,
                      retry_after=self.ISSUE_GAP if code == "EGW00133" else None)
        raise KISRateLimitError(ERROR_HINTS["EGW00133"], "EGW00133", retry_after=self.ISSUE_GAP)


# ---------------------------------------------------------------- REST
class RateLimiter:
    """초당 per_sec 회 이하로 호출 간격을 벌린다 (스레드 안전)."""

    def __init__(self, per_sec: float = 15.0, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval = 1.0 / per_sec if per_sec and per_sec > 0 else 0.0
        self._clock, self._sleep = clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> float:
        with self._lock:
            now = self._clock()
            at = max(now, self._next)
            self._next = at + self.interval
        delay = at - now
        if delay > 0:
            self._sleep(delay)
        return delay


@dataclass
class Quote:
    """현재가 (REST inquire-price). change_pct 는 퍼센트(1.25 = +1.25%), value_krw 는 원."""
    code: str
    price: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: float
    value_krw: float
    time: datetime

    def to_tick(self, source: str = "kis-rest") -> "Tick":
        return Tick(code=self.code, time=self.time, price=self.price, change_pct=self.change_pct,
                    cum_volume=self.volume, cum_value=self.value_krw, high=self.high, low=self.low, open=self.open,
                    change=self.change, source=source)


def quote_from_output(code: str, out: dict, at: datetime | None = None) -> Quote:
    sign = out.get("prdy_vrss_sign")
    return Quote(
        code=code, price=_num(out.get("stck_prpr")), change=_signed(_num(out.get("prdy_vrss")), sign),
        change_pct=_signed(_num(out.get("prdy_ctrt")), sign), open=_num(out.get("stck_oprc")),
        high=_num(out.get("stck_hgpr")), low=_num(out.get("stck_lwpr")), volume=_num(out.get("acml_vol")),
        value_krw=_num(out.get("acml_tr_pbmn")), time=at or now_kst(),
    )


class KISRestClient:
    """조회 전용 REST 클라이언트: 초당 15회(모의투자 2회) 이하, 5xx·연결 오류 재시도, EGW00201(초당 한도) 대기 후
    재시도, 토큰 만료(EGW00121·EGW00123)면 한 번 다시 발급."""

    def __init__(self, cfg: KISConfig, tokens: TokenManager | None = None, *, session=None,
                 per_sec: float | None = None, timeout: float = 10.0, retries: int = 3, backoff: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep, limiter: RateLimiter | None = None):
        self.cfg = cfg
        self.session = session or _new_session(cfg)
        self.tokens = tokens or TokenManager(cfg, session=self.session)
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self._sleep = sleep
        if per_sec is None:
            per_sec = REST_PER_SEC.get(cfg.env, REST_PER_SEC["vps"])
        self.limiter = limiter or RateLimiter(per_sec, sleep=sleep)

    def __repr__(self) -> str:
        return f"KISRestClient(env={self.cfg.env}, base_url={self.cfg.base_url})"

    def _secrets(self) -> tuple[str, ...]:
        """메시지에서 가릴 값: 앱키·시크릿 + 현재 접근토큰."""
        tok = getattr(self.tokens, "_token", None)
        return self.cfg.secrets() + ((tok,) if isinstance(tok, str) and tok else ())

    def _headers(self, tr_id: str) -> dict:
        h = _json_headers(self.cfg)
        h.update({"authorization": f"Bearer {self.tokens.get()}", "appkey": self.cfg.app_key,
                  "appsecret": self.cfg.app_secret, "tr_id": tr_id, "custtype": "P", "tr_cont": ""})
        return h

    def get(self, path: str, tr_id: str, params: dict) -> dict:
        url = self.cfg.base_url.rstrip("/") + path
        refreshed = False
        err: KISError | None = None
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            headers = self._headers(tr_id)
            try:
                r = self.session.get(url, headers=headers, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                err = KISError(f"KIS 서버 연결 실패 ({type(e).__name__})", "NETWORK")
                self._sleep(self.backoff * 2 ** attempt)
                continue
            js = _json(r)
            code = str(js.get("msg_cd") or js.get("error_code") or "")
            if code == "EGW00201":
                err = KISRateLimitError(ERROR_HINTS[code], code, retry_after=1.0)
                self._sleep(max(1.0, self.backoff * 2 ** attempt))
                continue
            if code in ("EGW00121", "EGW00123") and not refreshed:
                used = str(headers.get("authorization") or "")[len("Bearer "):] or None
                try:
                    self.tokens.invalidate(used)
                except TypeError:             # 예전 모양 토큰 관리자(인자 없음)
                    self.tokens.invalidate()
                refreshed = True
                continue
            if r.status_code >= 500:
                err = KISError(f"KIS 서버 오류 (HTTP {r.status_code})", code or None)
                self._sleep(self.backoff * 2 ** attempt)
                continue
            if r.status_code == 200 and str(js.get("rt_cd", "0")) == "0":
                return js
            msg = js.get("msg1") or js.get("error_description") or ""
            raise KISError(_hint(code, msg, self._secrets()) + f" (HTTP {r.status_code})", code or None)
        raise err or KISError("KIS 요청이 계속 실패했습니다", None)

    def quote(self, code: str, market: str = "J") -> Quote:
        """현재가 (FHKST01010100). market: J=KRX · NX=NXT · UN=통합."""
        js = self.get(PATH_PRICE, TR_PRICE, {"FID_COND_MRKT_DIV_CODE": market, "FID_INPUT_ISCD": code})
        q = quote_from_output(code, js.get("output") or {}, now_kst())
        if not q.price > 0:
            raise KISError(f"{code} 현재가 응답에 가격이 없습니다 — 종목코드를 확인하세요", "EMPTY")
        return q

    def daily(self, code: str, start: str | date, end: str | date, *, market: str = "J", adjusted: bool = True):
        """일봉 (FHKST03010100, 1회 최대 100봉). start·end = 'YYYYMMDD' 또는 date. 반환: open·high·low·close·volume·value."""
        import pandas as pd

        def ymd(x):
            return x.strftime("%Y%m%d") if isinstance(x, date) else str(x).replace("-", "")

        js = self.get(PATH_DAILY, TR_DAILY, {
            "FID_COND_MRKT_DIV_CODE": market, "FID_INPUT_ISCD": code, "FID_INPUT_DATE_1": ymd(start),
            "FID_INPUT_DATE_2": ymd(end), "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0" if adjusted else "1"})
        rows = [{"date": r.get("stck_bsop_date"), "open": _num(r.get("stck_oprc")), "high": _num(r.get("stck_hgpr")),
                 "low": _num(r.get("stck_lwpr")), "close": _num(r.get("stck_clpr")), "volume": _num(r.get("acml_vol")),
                 "value": _num(r.get("acml_tr_pbmn"))}
                for r in (js.get("output2") or []) if isinstance(r, dict) and r.get("stck_bsop_date")]
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "value"])
        if df.empty:
            return df.set_index("date")
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
        return df.dropna(subset=["date"]).set_index("date").sort_index()

    def open_day(self, day: date, *, cache_path: str | Path | None = None,
                 clock: Callable[[], float] = time.time) -> bool | None:
        """KRX 개장일이면 True, 휴장일이면 False, 모르면 None (국내휴장일조회 CTCA0903R 의 opnd_yn).

        KIS 가 '가급적 1일 1회 호출'을 요청하므로 응답에 들어 있는 날짜 전부를 캐시 파일(토큰 캐시 옆)에 저장하고,
        같은 기준일은 12시간 안에 다시 묻지 않는다. 모의투자는 이 조회를 지원하지 않는 것으로 보고 None.
        """
        if self.cfg.env != "prod":
            return None
        ymd = day.strftime("%Y%m%d")
        path = Path(cache_path) if cache_path else self.cfg.holiday_cache_path
        try:
            st = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(st, dict):
                st = {}
        except (OSError, ValueError):
            st = {}
        days = st.get("days") if isinstance(st.get("days"), dict) else {}
        asked = st.get("asked") if isinstance(st.get("asked"), dict) else {}
        if ymd in days:
            return days[ymd] == "Y"
        if clock() - float(asked.get(ymd, 0) or 0) < 12 * 3600:
            return None
        asked[ymd] = clock()
        try:
            js = self.get(PATH_HOLIDAY, TR_HOLIDAY, {"BASS_DT": ymd, "CTX_AREA_FK": "", "CTX_AREA_NK": ""})
        except KISError:
            js = {}
        rows = js.get("output") or []
        if isinstance(rows, dict):
            rows = [rows]
        for r in rows:
            if isinstance(r, dict) and re.fullmatch(r"\d{8}", str(r.get("bass_dt") or "")) \
                    and str(r.get("opnd_yn") or "") in ("Y", "N"):
                days[str(r["bass_dt"])] = str(r["opnd_yn"])
        cutoff = (day - timedelta(days=40)).strftime("%Y%m%d")   # 오래된 항목 정리
        st = {"version": 1, "days": {k: v for k, v in days.items() if k >= cutoff},
              "asked": {k: v for k, v in asked.items() if k >= cutoff}}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(st), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass
        return (days[ymd] == "Y") if ymd in days else None


# ---------------------------------------------------------------- 웹소켓
@dataclass
class Tick:
    """실시간 체결 1건. change_pct = 전일 대비 등락률(%, 1.25 = +1.25%), cum_value = 누적 거래대금(원)."""
    code: str
    time: datetime
    price: float
    change_pct: float
    cum_volume: float
    cum_value: float
    high: float
    low: float
    open: float
    change: float = float("nan")
    source: str = "kis"


@dataclass
class Frame:
    """웹소켓 수신 1건 해석 결과. kind: data | control | pingpong | encrypted | unknown."""
    kind: str
    tr_id: str | None = None
    tr_key: str | None = None
    records: list[dict] = field(default_factory=list)
    ok: bool | None = None
    msg: str = ""
    code: str | None = None
    encrypt: str | None = None
    key: str | None = field(default=None, repr=False)   # 암호화 키·IV (출력 금지)
    iv: str | None = field(default=None, repr=False)


def issue_approval_key(cfg: KISConfig, session=None, timeout: float = 10.0) -> str:
    """웹소켓 접속키 발급 (POST /oauth2/Approval, body 의 시크릿 필드명은 'secretkey')."""
    s = session or _new_session(cfg)
    url = cfg.base_url.rstrip("/") + PATH_APPROVAL
    body = {"grant_type": "client_credentials", "appkey": cfg.app_key, "secretkey": cfg.app_secret}
    try:
        r = s.post(url, data=json.dumps(body), headers=_json_headers(cfg), timeout=timeout)
    except requests.RequestException as e:
        raise KISAuthError(f"웹소켓 접속키 서버에 연결하지 못했습니다 ({type(e).__name__})", "NETWORK") from None
    js = _json(r)
    key = js.get("approval_key")
    if r.status_code == 200 and isinstance(key, str) and key:
        return key
    code, msg = _error_of(js, r.status_code)
    raise KISAuthError(_hint(code, msg, cfg.secrets()) + f" (웹소켓 접속키, HTTP {r.status_code})", code)


def subscribe_message(approval_key: str, tr_id: str, code: str, subscribe: bool = True, custtype: str = "P") -> str:
    """실시간 등록(tr_type '1')·해제('2') 요청 JSON. 접속키가 들어 있으므로 로그에 남기지 말 것."""
    return json.dumps({
        "header": {"approval_key": approval_key, "custtype": custtype, "tr_type": "1" if subscribe else "2",
                   "content-type": "utf-8"},
        "body": {"input": {"tr_id": tr_id, "tr_key": code}},
    })


def ws_endpoint(ws_url: str, path: str = WS_PATH) -> str:
    """설정의 웹소켓 주소(ops)에 경로를 붙인다. 주소에 이미 경로가 있으면 그대로."""
    base = (ws_url or "").rstrip("/")
    host_part = base.split("://", 1)[-1]
    return base if "/" in host_part or not path else base + path


def _aes_cbc_b64_decrypt(key: str, iv: str, text: str) -> str | None:
    """AES-256-CBC(base64) 복호화. pycryptodome 또는 cryptography 가 있으면 쓰고, 없으면 None."""
    try:
        raw = base64.b64decode(text)
    except (ValueError, TypeError):
        return None
    try:
        from Crypto.Cipher import AES  # type: ignore
        from Crypto.Util.Padding import unpad  # type: ignore
        return unpad(AES.new(key.encode(), AES.MODE_CBC, iv.encode()).decrypt(raw), 16).decode("utf-8")
    except ImportError:
        pass
    except Exception:
        return None
    try:
        from cryptography.hazmat.primitives import padding  # type: ignore
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # type: ignore
        dec = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode())).decryptor()
        padded = dec.update(raw) + dec.finalize()
        unp = padding.PKCS7(128).unpadder()
        return (unp.update(padded) + unp.finalize()).decode("utf-8")
    except Exception:
        return None


def parse_frame(raw: str | bytes, columns: list[str] | None = None,
                keys: dict[str, tuple[str, str]] | None = None) -> Frame:
    """웹소켓 수신 문자열 해석.

    데이터: '0|TR|건수|f1^f2^...' — 건수 n 이면 필드를 n 등분해 레코드 n 개 (등분이 안 되면 컬럼 수로 자름).
    암호화: '1|TR|...' — keys[TR] = (key, iv) 와 AES 라이브러리가 있으면 복호화, 아니면 kind='encrypted'.
    JSON: PINGPONG → 'pingpong', 그 밖은 'control' (ok = rt_cd == '0', msg = msg1, iv·key 는 복호화용).
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode("utf-8", "replace")
    if not raw:
        return Frame("unknown")
    if raw[0] in "01" and raw[1:2] == "|":
        parts = raw.split("|", 3)
        if len(parts) < 4:
            return Frame("unknown", msg="필드 부족")
        flag, tr_id, cnt, data = parts
        if flag == "1":
            k = (keys or {}).get(tr_id)
            plain = _aes_cbc_b64_decrypt(k[0], k[1], data) if k and k[0] and k[1] else None
            if plain is None:
                return Frame("encrypted", tr_id=tr_id)
            data = plain
        try:
            n = max(1, int(cnt))
        except ValueError:
            n = 1
        cols = columns or COLUMNS_BY_TR.get(tr_id) or []
        fields = data.split("^")
        if n > 1 and len(fields) % n and fields[-1] == "" and (len(fields) - 1) % n == 0:
            fields = fields[:-1]  # 끝에 구분자가 하나 더 붙은 경우
        if n == 1:
            per = len(fields)
        elif len(fields) % n == 0:
            per = len(fields) // n
        else:
            per = len(cols) or len(fields)
        recs = []
        for i in range(n):
            chunk = fields[i * per:(i + 1) * per]
            if not chunk or len(chunk) < min(len(cols), 15) and cols:
                break
            names = cols[:len(chunk)] + [f"F{j}" for j in range(len(cols), len(chunk))]
            recs.append(dict(zip(names, chunk)))
        return Frame("data", tr_id=tr_id, records=recs)
    try:
        js = json.loads(raw)
    except ValueError:
        return Frame("unknown")
    if not isinstance(js, dict):
        return Frame("unknown")
    hdr = js.get("header") or {}
    tr_id = hdr.get("tr_id")
    if tr_id == "PINGPONG":
        return Frame("pingpong", tr_id=tr_id)
    body = js.get("body") or {}
    out = body.get("output") or {}
    return Frame("control", tr_id=tr_id, tr_key=hdr.get("tr_key"), ok=str(body.get("rt_cd")) == "0",
                 msg=str(body.get("msg1") or ""), code=body.get("msg_cd"), encrypt=hdr.get("encrypt"),
                 key=out.get("key") if isinstance(out, dict) else None,
                 iv=out.get("iv") if isinstance(out, dict) else None)


def _kst_time(ymd, hms, today: date | None = None) -> datetime:
    d = today or now_kst().date()
    s = str(ymd or "").strip()
    if re.fullmatch(r"\d{8}", s):
        try:
            d = date(int(s[:4]), int(s[4:6]), int(s[6:]))
        except ValueError:
            pass
    h = str(hms or "").strip()
    if re.fullmatch(r"\d{6}", h):
        try:
            return datetime(d.year, d.month, d.day, int(h[:2]), int(h[2:4]), int(h[4:]), tzinfo=KST)
        except ValueError:
            pass
    return now_kst()


def tick_from_record(rec: dict, *, source: str = "kis", today: date | None = None) -> Tick | None:
    """실시간 체결가 레코드(컬럼명 → 문자열) → Tick. 종목코드·가격이 없으면 None."""
    code = str(rec.get("MKSC_SHRN_ISCD") or "").strip()
    price = _num(rec.get("STCK_PRPR"))
    if not code or not price > 0:
        return None
    sign = rec.get("PRDY_VRSS_SIGN")
    return Tick(
        code=code, time=_kst_time(rec.get("BSOP_DATE"), rec.get("STCK_CNTG_HOUR"), today), price=price,
        change_pct=_signed(_num(rec.get("PRDY_CTRT")), sign), cum_volume=_num(rec.get("ACML_VOL")),
        cum_value=_num(rec.get("ACML_TR_PBMN")), high=_num(rec.get("STCK_HGPR")), low=_num(rec.get("STCK_LWPR")),
        open=_num(rec.get("STCK_OPRC")), change=_signed(_num(rec.get("PRDY_VRSS")), sign), source=source,
    )


class KISWebSocketClient:
    """실시간 체결가 웹소켓 (조회 전용).

        client = KISWebSocketClient(cfg, ["005930", "000660"])
        async for tick in client.ticks():      # 끊기면 지수 백오프(1→60초)로 다시 접속·재구독
            ...

    - 접속키는 issue_approval_key() 로 받고(연속 3회 실패마다 새로 발급), 접속키·암호화 키는 로그에 남기지 않는다.
    - 구독 한도 max_codes(기본 40)를 넘는 종목은 제외하고 dropped 에 남긴다.
    - PINGPONG 은 공식 샘플처럼 받은 내용으로 pong 을 보낸다.
    - 접속키 거부·'ALREADY IN USE' 응답이면 연결을 닫고 백오프 뒤 다시 접속한다 (실패 횟수에 포함).
    - max_failures 회 연속 실패하면 KISError('WS') — 호출한 쪽이 REST 조회 등으로 대체할 수 있게.
    """

    def __init__(self, cfg: KISConfig, codes: Iterable[str] = (), *, tr_id: str = TR_CCNL_KRX,
                 max_codes: int = MAX_WS_SUBSCRIPTIONS, session=None, connect: Callable | None = None,
                 approval: Callable[[], str] | None = None, on_status: Callable[[str], None] | None = None,
                 backoff_start: float = 1.0, backoff_max: float = 60.0, max_failures: int | None = None,
                 send_interval: float | None = None, ws_path: str = WS_PATH, ping_interval: float | None = 30.0,
                 sleep: Callable | None = None):
        if send_interval is None:   # 구독 요청 간격: 실전 0.05초, 모의투자 0.5초
            send_interval = WS_SEND_INTERVAL.get(cfg.env, WS_SEND_INTERVAL["vps"])
        self.cfg = cfg
        self.tr_id = tr_id
        self.max_codes = max(1, int(max_codes))
        self._connect = connect
        self._approval_fn = approval or (lambda: issue_approval_key(cfg, session))
        self._on_status = on_status or (lambda msg: None)
        self.backoff_start, self.backoff_max = backoff_start, backoff_max
        self.max_failures = max_failures
        self.send_interval = send_interval
        self.ws_path = ws_path
        self.ping_interval = ping_interval
        self._sleep = sleep or asyncio.sleep
        self._codes: list[str] = []
        self.dropped: list[str] = []
        self._key: str | None = None
        self._keys: dict[str, tuple[str, str]] = {}
        self._ws = None
        self._stopped = False
        self._said: set[str] = set()
        self.failures = 0
        self.connects = 0
        self.ticks_received = 0
        self.subscribed: set[str] = set()
        # 서버가 구독을 거부한 종목 (MAX SUBSCRIBE OVER). 호출 쪽(live.KISSource)이 REST 조회로 보충한다.
        # 계정·시간대에 따라 세션당 허용 건수가 40보다 훨씬 적을 수 있다 (실측: 장 마감 후 3건).
        self.overflow: set[str] = set()
        self.last_error: str | None = None
        self._add_codes(codes)

    def __repr__(self) -> str:
        return f"KISWebSocketClient(url={self.url}, tr_id={self.tr_id}, codes={len(self._codes)})"

    # ---- 상태
    @property
    def codes(self) -> list[str]:
        return list(self._codes)

    @property
    def url(self) -> str:
        return ws_endpoint(self.cfg.ws_url, self.ws_path)

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def _secrets(self) -> tuple[str, ...]:
        """메시지에서 가릴 값: 앱키·시크릿 + 웹소켓 접속키 + 암호화 키·IV."""
        extra = [self._key or ""] + [x for kv in self._keys.values() for x in kv]
        return self.cfg.secrets() + tuple(x for x in extra if x)

    def _status(self, msg: str) -> None:
        try:
            self._on_status(scrub(msg, self._secrets()))
        except Exception:
            pass

    def _say_once(self, key: str, msg: str) -> None:
        if key not in self._said:
            self._said.add(key)
            self._status(msg)

    def _add_codes(self, codes: Iterable[str]) -> list[str]:
        added = []
        for c in codes:
            c = str(c).strip()
            if not c or c in self._codes:
                continue
            if len(self._codes) >= self.max_codes:
                if c not in self.dropped:
                    self.dropped.append(c)
                continue
            self._codes.append(c)
            added.append(c)
        if self.dropped:
            self._status(f"실시간 구독 한도 {self.max_codes}종목 — {len(self.dropped)}종목은 제외했습니다")
        return added

    # ---- 구독 관리
    async def _send(self, code: str, subscribe: bool) -> None:
        ws = self._ws
        if ws is None or not self._key:
            return
        await ws.send(subscribe_message(self._key, self.tr_id, code, subscribe))
        if self.send_interval:
            await self._sleep(self.send_interval)

    async def subscribe(self, codes: Iterable[str]) -> list[str]:
        """종목 추가 (연결 중이면 바로 등록 요청). 반환: 실제로 추가된 종목."""
        added = self._add_codes(codes)
        for c in added:
            await self._send(c, True)
        return added

    async def unsubscribe(self, codes: Iterable[str]) -> None:
        for c in [str(x).strip() for x in codes]:
            if c in self._codes:
                self._codes.remove(c)
                self.subscribed.discard(c)
                await self._send(c, False)

    def stop(self) -> None:
        """다음 수신 뒤 루프를 끝낸다 (재접속하지 않음)."""
        self._stopped = True

    # ---- 수신 루프
    def _open(self):
        if self._connect is not None:
            return self._connect(self.url)
        try:
            import websockets  # type: ignore
        except ImportError:
            raise KISError("websockets 패키지가 없습니다 — python -m pip install websockets", "WS_LIB") from None
        return websockets.connect(self.url, ping_interval=self.ping_interval, ping_timeout=self.ping_interval,
                                  close_timeout=5, max_size=2 ** 22)

    async def _pong(self, ws, raw) -> None:
        pong = getattr(ws, "pong", None)
        if pong is not None:
            await pong(raw if isinstance(raw, (str, bytes)) else str(raw))

    def _on_control(self, fr: Frame) -> str | None:
        """제어 메시지 처리. 연결을 닫고 다시 접속해야 하면 그 이유(한글)를, 아니면 None 을 돌려준다."""
        if fr.tr_id and fr.key and fr.iv:
            self._keys[fr.tr_id] = (fr.key, fr.iv)
        msg = (fr.msg or "").upper()
        if fr.ok:
            if "UNSUB" in msg:
                self.subscribed.discard(fr.tr_key or "")
                return None
            if fr.tr_key:
                self.subscribed.add(fr.tr_key)
                self.overflow.discard(fr.tr_key)
            self.failures = 0
            if self._codes and len(self.subscribed) >= len(self._codes):
                self._say_once(f"subok{self.connects}", f"실시간 구독 완료 {len(self.subscribed)}종목")
            return None
        if "ALREADY IN SUBSCRIBE" in msg:
            if fr.tr_key:
                self.subscribed.add(fr.tr_key)
            return None
        if "MAX SUBSCRIBE" in msg:
            if fr.tr_key:
                self.overflow.add(fr.tr_key)
            self._say_once("max", "실시간 구독 한도 초과 응답 — 한도를 넘은 종목은 REST 현재가 조회로 보충합니다")
            return None
        if "ALREADY IN USE" in msg:
            self._key = None
            self._say_once("inuse", "같은 앱키로 이미 실시간 접속 중이라는 응답입니다 — 다른 실시간 프로그램(또는 이전 실행)을 "
                                    "끄고 다시 시도하세요")
            return "같은 앱키로 이미 실시간 접속 중"
        if "APPROVAL" in msg:
            self._key = None
            self._say_once("approval", "웹소켓 접속키가 거부됐습니다 — 새로 발급해 다시 접속합니다")
            return "웹소켓 접속키 거부"
        # 그 밖의 오류(잘못된 종목코드 등)는 접속키를 버리지 않고 알리기만 한다
        code = f" [{fr.code}]" if fr.code else ""
        self._status(f"구독 응답 {fr.tr_key or ''}{code}: {fr.msg}".strip())
        return None

    async def ticks(self) -> AsyncIterator[Tick]:
        """체결가 Tick 을 계속 내보낸다. 끊기면 다시 접속·재구독. stop() 이나 호출 쪽 중단으로 끝난다."""
        delay = self.backoff_start
        while not self._stopped:
            try:
                if not self._key:
                    self._key = await asyncio.to_thread(self._approval_fn)
                reconnect: str | None = None
                async with self._open() as ws:
                    self._ws = ws
                    self.connects += 1
                    self.subscribed.clear()
                    self._status(f"웹소켓 연결 — {len(self._codes)}종목 실시간 체결 구독 요청")
                    for c in list(self._codes):
                        await self._send(c, True)
                    async for raw in ws:
                        fr = parse_frame(raw, keys=self._keys)
                        if fr.kind == "data":
                            if fr.tr_id == self.tr_id:
                                for rec in fr.records:
                                    t = tick_from_record(rec)
                                    if t is not None:
                                        self.ticks_received += 1
                                        self.failures = 0
                                        delay = self.backoff_start
                                        yield t
                        elif fr.kind == "pingpong":
                            await self._pong(ws, raw)
                        elif fr.kind == "control":
                            reconnect = self._on_control(fr)
                            if reconnect:
                                break   # async with 를 나가며 연결을 닫고, 아래에서 백오프 뒤 다시 접속
                        elif fr.kind == "encrypted":
                            self._say_once("enc", "암호화된 실시간 데이터는 건너뜁니다 (복호화 라이브러리 없음)")
                        if self._stopped:
                            break
                if self._stopped:
                    break
                self.last_error = reconnect or "서버가 연결을 닫음"
            except asyncio.CancelledError:
                raise
            except KISError as e:
                if e.code in _FATAL_CODES:
                    raise
                self.last_error = scrub(e.message, self._secrets())
            except Exception as e:  # 연결 끊김·DNS·핸드셰이크 오류 등
                self.last_error = scrub(f"{type(e).__name__}: {e}", self._secrets())[:160]
            finally:
                self._ws = None
            if self._stopped:
                break
            self.failures += 1
            if self.max_failures is not None and self.failures >= self.max_failures:
                raise KISError(f"웹소켓 연결이 {self.failures}회 연속 실패했습니다 ({self.last_error})", "WS")
            if self.failures % 3 == 0:
                self._key = None  # 접속키 문제일 수 있으니 새로 발급
            wait = min(delay, self.backoff_max) * (1 + random.random() * 0.2)
            self._status(f"웹소켓 재연결 {wait:.0f}초 뒤 ({self.failures}회째 · {self.last_error})")
            await self._sleep(wait)
            delay = min(delay * 2, self.backoff_max)
