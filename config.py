import os

# ── KIS API ───────────────────────────────────────────
APP_KEY    = os.environ.get("KIS_APP_KEY", "")
APP_SECRET = os.environ.get("KIS_APP_SECRET", "")
ACCOUNT_NO = os.environ.get("KIS_ACCOUNT_NO", "")   # 예: 12345678-01
IS_PAPER   = os.environ.get("KIS_PAPER", "false").lower() == "true"  # 모의투자 여부

# ── 텔레그램 ──────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── 전략 파라미터 ──────────────────────────────────────
POSITION_SIZE_PCT   = 0.10   # 총 자산의 10%씩 진입
MAX_POSITIONS       = 3      # 동시 최대 보유 종목 수

SCAN_START_TIME     = "09:05"  # 스캔 시작
SCAN_END_TIME       = "14:00"  # 스캔 종료 (테스트용 연장)
FORCE_CLOSE_TIME    = "14:30"  # 강제 청산 시간

# 종목 스캔 조건 (테스트용 완화)
MIN_VOLUME_RATIO    = 2.0    # 20일 평균 거래량 대비 N배 (5→2 완화)
MIN_CHANGE_RATE     = 1.0    # 당일 상승률 최소 (3→1% 완화)
MAX_CHANGE_RATE     = 10.0   # 당일 상승률 최대 (8→10% 완화)

# 익절/손절
TAKE_PROFIT_PCT     = 0.02   # +2% 익절
STOP_LOSS_PCT       = 0.015  # -1.5% 손절

# 루프 인터벌
SCAN_INTERVAL_SEC   = 60     # 종목 스캔 주기 (초)
MONITOR_INTERVAL_SEC = 10    # 포지션 모니터링 주기 (초)
