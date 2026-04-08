import os

# ── KIS API ───────────────────────────────────────────
APP_KEY    = os.environ.get("KIS_APP_KEY", "")
APP_SECRET = os.environ.get("KIS_APP_SECRET", "")
ACCOUNT_NO = os.environ.get("KIS_ACCOUNT_NO", "")
IS_PAPER   = os.environ.get("KIS_PAPER", "false").lower() == "true"

# ── 텔레그램 ──────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── 운영 시간 ──────────────────────────────────────────
SCAN_START_TIME  = "09:05"
SCAN_END_TIME    = "14:00"   # 테스트용 연장
FORCE_CLOSE_TIME = "14:30"

# ── 포지션 설정 ────────────────────────────────────────
POSITION_SIZE_PCT = 0.10
MAX_POSITIONS     = 3

# ── 스캔 조건 (테스트 완화) ────────────────────────────
MIN_VOLUME_RATIO  = 2.0
MIN_CHANGE_RATE   = 1.0
MAX_CHANGE_RATE   = 10.0

# ── 청산 조건 ──────────────────────────────────────────
TAKE_PROFIT_PCT   = 0.02
STOP_LOSS_PCT     = 0.015

# ── 루프 인터벌 ────────────────────────────────────────
SCAN_INTERVAL_SEC    = 60
MONITOR_INTERVAL_SEC = 10
