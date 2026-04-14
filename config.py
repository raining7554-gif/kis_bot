"""설정 v3.0 — 섹터 스윙 전략 (국장 50만 + 나스닥 50만 시드 가정)"""
import os

# ── KIS API ───────────────────────────────────────────
APP_KEY    = os.environ.get("KIS_APP_KEY", "")
APP_SECRET = os.environ.get("KIS_APP_SECRET", "")
ACCOUNT_NO = os.environ.get("KIS_ACCOUNT_NO", "")
IS_PAPER   = os.environ.get("KIS_PAPER", "false").lower() == "true"

# ── 텔레그램 ──────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────────────────
# 국내(한국장) 설정
# ─────────────────────────────────────────────────────────
# 시드 가정 (실계좌 잔고로 동적 계산하지만 유니버스 필터링 기준용)
DOM_ASSUMED_SEED = 500_000          # 50만원

# 운영 시간 — 스윙이므로 신규 진입만 제한, 청산은 언제든
DOM_SCAN_START  = "09:30"           # 오전장 안정화 후
DOM_SCAN_END    = "14:00"           # 종가 직전 피함
DOM_EOD_CHECK   = "15:15"           # 일봉 청산 조건 체크
DOM_CLOSING_MSG = "15:35"           # 결산 알림

# 포지션
DOM_MAX_POSITIONS = 2               # 시드 작으니 2종목 분산이 현실적
DOM_POSITION_PCT  = 0.45            # 시드의 45%씩 (2종목 = 90%, 버퍼 10%)
DOM_UNIVERSE_MAX_PRICE = 150_000    # 유니버스 가격 상한(1주라도 살 수 있게)
DOM_UNIVERSE_MIN_PRICE = 2_000      # 저가 작전주 회피

# 청산 조건 (스윙)
DOM_STOP_LOSS      = 0.03           # -3% 하드 손절
DOM_TRAIL_ACTIVATE = 0.03           # +3% 도달 시 트레일링 활성
DOM_TRAIL_DROP     = 0.05           # 고점 대비 -5%
DOM_MAX_HOLD_DAYS  = 10             # 최대 10영업일

# ─────────────────────────────────────────────────────────
# 해외(나스닥) 설정
# ─────────────────────────────────────────────────────────
OS_ASSUMED_SEED_USD = 350           # 약 50만원

# 운영 시간 (KST 기준, 서머타임 고려 않고 넉넉히)
OS_SCAN_TIME_START  = "22:45"       # 미장 개장 직후 1회만 진입
OS_SCAN_TIME_END    = "23:15"
OS_EOD_CHECK        = "05:45"       # 미장 종료 직전 일봉 청산 체크

# 포지션
OS_MAX_POSITIONS  = 2               # $350 시드면 2종목이 현실적
OS_POSITION_USD   = 150             # 1종목당 $150 목표
OS_QQQ_BASE_USD   = 50              # QQQ 방어용 베이스 (상승장에서만)

# 청산 조건
OS_STOP_LOSS      = 0.05            # -5% 하드 손절 (장중 실시간 봇 감시)
OS_TRAIL_DROP     = 0.10            # 고점 대비 -10%
OS_PANIC_TRIGGER  = 0.02            # QQQ -2% 이상 급락 시 방어 가동
# 나스닥은 최대 보유일 제한 없음 — 추세 유효하면 계속 보유

# ─────────────────────────────────────────────────────────
# 공통 루프 인터벌
# ─────────────────────────────────────────────────────────
SCAN_INTERVAL_SEC     = 180         # 스캔 3분에 1회 (스윙이라 급할 것 없음)
MONITOR_INTERVAL_SEC  = 15          # 장중 모니터링 15초
SUMMARY_INTERVAL_SEC  = 3600        # 1시간에 1회 현황

# ─────────────────────────────────────────────────────────
# 레거시 호환 (다른 모듈이 import할 수도 있어 유지)
# ─────────────────────────────────────────────────────────
POSITION_SIZE_PCT = DOM_POSITION_PCT
MAX_POSITIONS     = DOM_MAX_POSITIONS
SCAN_START_TIME   = DOM_SCAN_START
SCAN_END_TIME     = DOM_SCAN_END
FORCE_CLOSE_TIME  = "99:99"         # 강제청산 안 함 (스윙)
TAKE_PROFIT_PCT   = DOM_TRAIL_ACTIVATE
STOP_LOSS_PCT     = DOM_STOP_LOSS
