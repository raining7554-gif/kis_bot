"""KRX 영업일/휴장일 판정 유틸 v1.0

- 주말(토·일) 자동 제외
- 하드코딩된 2026년 KRX 휴장일 목록
- 수정이 필요하면 KRX_HOLIDAYS 셋만 업데이트
"""
from datetime import datetime, date
import pytz

# 2026년 한국거래소 정규시장 휴장일
KRX_HOLIDAYS = {
    "2026-01-01",  # 신정
    "2026-02-16",  # 설 연휴
    "2026-02-17",  # 설날
    "2026-02-18",  # 설 연휴
    "2026-03-02",  # 3·1절 대체
    "2026-05-05",  # 어린이날
    "2026-05-25",  # 부처님오신날
    "2026-06-03",  # 지방선거
    "2026-08-17",  # 광복절 대체
    "2026-09-24",  # 추석 연휴
    "2026-09-25",  # 추석
    "2026-09-26",  # 추석 연휴
    "2026-10-05",  # 개천절 대체
    "2026-10-09",  # 한글날
    "2026-12-25",  # 성탄절
    "2026-12-31",  # 연말 휴장
    # 2027 년 대비
    "2027-01-01",
}


def is_trading_day(dt=None) -> bool:
    """정규장 영업일 여부. 인자는 KST aware datetime 권장."""
    if dt is None:
        dt = datetime.now(pytz.timezone("Asia/Seoul"))
    if dt.weekday() >= 5:
        return False
    if dt.strftime("%Y-%m-%d") in KRX_HOLIDAYS:
        return False
    return True
