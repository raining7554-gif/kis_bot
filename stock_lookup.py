"""종목명 → 종목코드 변환기

텔레그램에서 사람이 '삼성전자', '하이닉스', '에코프로' 처럼 이름으로 물어보면
6자리 코드로 바꿔준다. 기존 유니버스 목록(시총 상위 350 + 섹터 후보)을
이름 인덱스로 재활용. 6자리 숫자를 그대로 보내면 코드로 인식.

resolve(query) → [(code, name), ...]
  - 정확히 1개면 바로 분석
  - 여러 개면 사용자가 고르도록 후보 리스트 반환
  - 0개면 "코드로 보내달라" 안내
"""
from __future__ import annotations
import re


def _build_index() -> dict[str, str]:
    """code -> name 통합 인덱스 (중복은 먼저 등록된 이름 유지)."""
    idx: dict[str, str] = {}
    try:
        from strategy_clenow_kr import KR_UNIVERSE_TOP350
        for code, name in KR_UNIVERSE_TOP350:
            idx.setdefault(code, name)
    except Exception:
        pass
    try:
        from universe_filter import SECTOR_CANDIDATES
        for lst in SECTOR_CANDIDATES.values():
            for code, name in lst:
                idx.setdefault(code, name)
    except Exception:
        pass
    return idx


_CODE_TO_NAME = _build_index()


# 인기 미국주식 한글명 → 티커 (대표 종목만; 티커 직접입력은 항상 가능)
US_NAME_MAP = {
    "애플": "AAPL", "엔비디아": "NVDA", "테슬라": "TSLA", "마이크로소프트": "MSFT",
    "엠에스": "MSFT", "구글": "GOOGL", "알파벳": "GOOGL", "아마존": "AMZN",
    "메타": "META", "넷플릭스": "NFLX", "팔란티어": "PLTR", "브로드컴": "AVGO",
    "에이엠디": "AMD", "인텔": "INTC", "퀄컴": "QCOM", "마이크론": "MU",
    "코인베이스": "COIN", "마이크로스트래티지": "MSTR", "스트래티지": "MSTR",
    "슈퍼마이크로": "SMCI", "슈마컴": "SMCI", "쇼피파이": "SHOP",
    "우버": "UBER", "디즈니": "DIS", "스타벅스": "SBUX", "보잉": "BA",
    "비자": "V", "마스터카드": "MA", "제이피모건": "JPM",
    "티에스엠씨": "TSM", "엘리릴리": "LLY", "릴리": "LLY",
    # 인기 ETF
    "나스닥": "QQQ", "소엑셀": "SOXL", "티큐큐큐": "TQQQ",
}

# US 티커 패턴 (영문 1~5자, BRK.B 같은 점 포함 허용)
_US_TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")


def resolve_us(query: str) -> str | None:
    """질의가 미국주식이면 티커 반환, 아니면 None."""
    q = query.strip()
    if not q:
        return None
    key = re.sub(r"\s+", "", q)
    if key in US_NAME_MAP:
        return US_NAME_MAP[key]
    up = q.upper()
    if _US_TICKER_RE.match(up):
        return up
    return None


# 티커 → 한글명 (역매핑, 표시용)
_US_TICKER_TO_NAME = {}
for _kname, _tk in US_NAME_MAP.items():
    _US_TICKER_TO_NAME.setdefault(_tk, _kname)


def us_name_of(ticker: str) -> str:
    return _US_TICKER_TO_NAME.get(ticker.upper(), "")


def _norm(s: str) -> str:
    """비교용 정규화 — 공백/특수문자 제거, 대문자, 일부 표기 통일."""
    s = s.strip().upper()
    s = re.sub(r"\s+", "", s)
    s = s.replace("(우)", "").replace("우B", "").replace("&", "")
    return s


def _is_code(q: str) -> bool:
    q = q.strip()
    # 보통 6자리 숫자, 일부 우선주/신주는 끝에 영문 (예: 0126Z0)
    return bool(re.fullmatch(r"[0-9][0-9A-Z]{5}", q.upper()))


def name_of(code: str) -> str:
    return _CODE_TO_NAME.get(code, "")


def resolve(query: str) -> list[tuple[str, str]]:
    """질의 → 후보 [(code, name), ...]"""
    q = query.strip()
    if not q:
        return []

    # 1) 6자리 코드 직접 입력
    if _is_code(q):
        code = q.upper()
        return [(code, _CODE_TO_NAME.get(code, ""))]

    nq = _norm(q)

    # 2) 정확한 이름 일치
    exact = [(c, n) for c, n in _CODE_TO_NAME.items() if _norm(n) == nq]
    if exact:
        return exact

    # 3) 부분 일치 (이름에 질의가 포함, 또는 질의에 이름이 포함)
    partial = [
        (c, n) for c, n in _CODE_TO_NAME.items()
        if nq in _norm(n) or _norm(n) in nq
    ]
    # 짧은 이름(더 정확한 매칭) 우선
    partial.sort(key=lambda x: len(x[1]))
    return partial
