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
