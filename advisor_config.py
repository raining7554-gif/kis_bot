"""어드바이저 봇 설정 v1.0 — 토스 직접매매용 진입가 추천

이 봇은 '자동매매'를 하지 않는다. 토스증권으로 직접 매매하는 단타/스윙
종목에 대해 진입가·손절가·목표가를 계산해 정해진 시각에 텔레그램 요약
리포트로 보내준다. KIS 인증/텔레그램/일봉조회 인프라는 기존 봇 것을 재사용.

환경변수로 운영을 튜닝한다 (없으면 합리적 기본값).
"""
import os

# ─────────────────────────────────────────────────────────
# 관심종목 (토스로 보고 있는 종목 직접 등록)
# ─────────────────────────────────────────────────────────
# CSV 로 티커만 나열. 예: "005930,000660,042700"
# (종목명은 KIS 시세조회로 자동 채움)
ADVISOR_WATCHLIST = [
    t.strip() for t in os.environ.get("ADVISOR_WATCHLIST", "").split(",") if t.strip()
]

# ─────────────────────────────────────────────────────────
# 리포트 전송 시각 (KST, CSV "HH:MM")
# ─────────────────────────────────────────────────────────
#   08:50 — 장 시작 전 스윙 브리핑 + 관심종목 진입가
#   12:20 — 장중 단타/스윙 점검
#   15:40 — 마감 후 정리 + 내일 스윙 후보
ADVISOR_REPORT_TIMES = [
    t.strip() for t in os.environ.get("ADVISOR_REPORT_TIMES", "08:50,12:20,15:40").split(",")
    if t.strip()
]

# ─────────────────────────────────────────────────────────
# 자동 발굴 (관심종목 외 봇이 후보를 추가로 골라줌)
# ─────────────────────────────────────────────────────────
ADVISOR_AUTO_DISCOVER = os.environ.get("ADVISOR_AUTO_DISCOVER", "true").lower() == "true"
ADVISOR_DAYTRADE_TOPN = int(os.environ.get("ADVISOR_DAYTRADE_TOPN", "5"))  # 단타 자동발굴 개수
ADVISOR_SWING_TOPN    = int(os.environ.get("ADVISOR_SWING_TOPN", "5"))     # 스윙 자동발굴 개수

# 발굴 종목 필터 (저유동성/동전주 회피)
ADVISOR_MIN_TRADE_AMOUNT = int(os.environ.get("ADVISOR_MIN_TRADE_AMOUNT", "5000000000"))  # 50억
ADVISOR_MIN_PRICE = int(os.environ.get("ADVISOR_MIN_PRICE", "1000"))
ADVISOR_MAX_PRICE = int(os.environ.get("ADVISOR_MAX_PRICE", "2000000"))

# ─────────────────────────────────────────────────────────
# 단타 파라미터 (당일 VWAP/지지·저항 기반)
# ─────────────────────────────────────────────────────────
DT_STOP_PCT   = float(os.environ.get("DT_STOP_PCT", "0.02"))   # 진입가 대비 손절 폭(최소)
DT_RR         = float(os.environ.get("DT_RR", "2.0"))          # 손익비 (목표 = 손절폭 × RR)
DT_MIN_SCORE  = int(os.environ.get("DT_MIN_SCORE", "55"))      # 이 점수 미만은 '관망'

# ─────────────────────────────────────────────────────────
# 스윙 파라미터 (일봉 MA/ATR 기반)
# ─────────────────────────────────────────────────────────
SW_STOP_PCT   = float(os.environ.get("SW_STOP_PCT", "0.05"))   # MA20 기준 손절 버퍼
SW_RR         = float(os.environ.get("SW_RR", "2.0"))
SW_MIN_SCORE  = int(os.environ.get("SW_MIN_SCORE", "55"))

# ─────────────────────────────────────────────────────────
# 루프 인터벌
# ─────────────────────────────────────────────────────────
ADVISOR_LOOP_SEC = int(os.environ.get("ADVISOR_LOOP_SEC", "20"))
# 대화형 질의응답 폴링 주기(초) — 텔레그램으로 종목명 물어보면 답하는 모드
ADVISOR_POLL_SEC = int(os.environ.get("ADVISOR_POLL_SEC", "3"))
# 대화형 질의응답 on/off (끄면 정시 리포트만)
ADVISOR_INTERACTIVE = os.environ.get("ADVISOR_INTERACTIVE", "true").lower() == "true"
# 자동발굴 스캔이 KIS rate-limit 에 걸리지 않도록 호출 간 지연(초)
ADVISOR_API_DELAY = float(os.environ.get("ADVISOR_API_DELAY", "0.12"))
