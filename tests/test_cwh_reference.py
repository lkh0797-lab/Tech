"""사용자 컵앤핸들 식(chart_screener/patterns/cwh_reference.py) — 받은 파일 그대로인지 + 식 자체 시험 22개.

식 파일은 사용자가 준 cup_handle_scanner.py 를 바이트 그대로 복사한 것이다(2026-10-14). 내용이 바뀌면 아래 해시가 달라진다
— 식을 고치려면 사용자에게 새 파일을 받아 해시와 RULE_VERSION 을 함께 바꿀 것. 줄끝(CRLF/LF)은 git 설정에 따라 바뀔 수
있어 LF 로 맞춘 뒤 잰다.
"""
import hashlib
from pathlib import Path

from chart_screener.patterns import cwh_reference
from chart_screener.patterns.cwh_reference import ScannerTests  # noqa: F401  (pytest 가 식의 unittest 를 그대로 모은다)

SOURCE_SHA256_LF = "59eeaf10acb1b9c47ce95d6330e8a27de8e53f00d06f53cdb2b7a7884df955f9"


def test_reference_file_is_verbatim():
    raw = Path(cwh_reference.__file__).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256_LF
    assert cwh_reference.RULE_VERSION == "cwh_reference_v1.0.0"


def test_reference_self_tests_count():
    names = [n for n in dir(ScannerTests) if n.startswith("test_")]
    assert len(names) == 22
