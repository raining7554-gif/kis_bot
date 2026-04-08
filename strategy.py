"""
복합 필터 모멘텀 전략
국내 단타 고수 원칙 + 글로벌 알고트레이딩 2025 최신 기법 결합
"""
import kis_auth as api
from config import ACCOUNT_NO, IS_PAPER

# ── 전략 파라미터 ──────────────────────────────────────
MARKET_REGIME_SHORT = 5     # 시장 필터 단기 MA
MARKET_REGIME_LONG  = 20    # 시장 필터 장기 MA

SCAN_MIN_CHANGE   = 1.0     # 최소 상승률 (%) - 테스트용 완화
SCAN_MAX_CHANGE   = 10.0    # 최대 상승률 (%)
SCAN_VOL_RATIO    = 2.0     # 거래량 배수 - 테스트용 완화
SCAN_MIN_PRICE    = 1_000   # 최소 주가 (완화)
SCAN_MAX_PRICE    = 200_000 # 최대 주가 (완화)

RSI_MIN = 40   # RSI 최소 (완화)
RSI_MAX = 75   # RSI 최대 (완화)

BASE_POSITION_PCT  = 0.10   # 기본 포지션 비율
HIGH_VOL_POSITION  = 0.07   # 고변동성시 포지션
LOW_VOL_POSITION   = 0.15   # 저변동성시 포지션
ATR_HIGH_THRESHOLD = 3.0    # ATR% 기준 고변동성

TRAIL_ACTIVATE_PCT = 0.01   # 트레일링 스탑 활성화 수익률
TRAIL_DROP_PCT     = 0.008  # 고점 대비 하락시 청산
STOP_LOSS_PCT      = 0.015  # 기본 손절

KOSPI_CODE = "0001"  # KOSPI 지수 코드

# ── 시장 필터 ──────────────────────────────────────────
def get_kospi_ma() -> tuple[float, float]:
    """KOSPI 5일MA, 20일MA 반환"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {
                "fid_cond_mrkt_div_code": "U",
                "fid_input_iscd": KOSPI_CODE,
                "fid_org_adj_prc": "0",
                "fid_period_div_code": "D",
            }
        )
        prices = [float(o["stck_clpr"]) for o in data.get("output2", [])[:20] if o.get("stck_clpr")]
        if len(prices) >= 20:
            ma5  = sum(prices[:5])  / 5
            ma20 = sum(prices[:20]) / 20
            return ma5, ma20
    except Exception as e:
        print(f"[STRATEGY] KOSPI MA 조회 오류: {e}")
    return 0, 0

def is_bull_market() -> bool:
    """상승장 여부 (5MA > 20MA)"""
    ma5, ma20 = get_kospi_ma()
    if ma5 == 0 or ma20 == 0:
        return True  # 조회 실패시 허용
    result = ma5 > ma20
    print(f"[STRATEGY] 시장 필터: KOSPI MA5={ma5:.0f} MA20={ma20:.0f} → {'📈 상승장' if result else '📉 하락장 (매수 중단)'}")
    return result

# ── RSI 계산 ──────────────────────────────────────────
def calc_rsi(prices: list[float], period: int = 14) -> float:
    """RSI 계산"""
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[i-1] - prices[i]  # 최신순 정렬
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ── ATR 계산 ──────────────────────────────────────────
def calc_atr_pct(ticker: str) -> float:
    """ATR% 계산 (변동성 지표)"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_org_adj_prc": "1",
                "fid_period_div_code": "D",
            }
        )
        outputs = data.get("output2", [])[:14]
        trs = []
        for o in outputs:
            h = float(o.get("stck_hgpr", 0))
            l = float(o.get("stck_lwpr", 0))
            c = float(o.get("stck_clpr", 0))
            if h and l and c:
                trs.append(h - l)
        if trs:
            atr = sum(trs) / len(trs)
            last_close = float(outputs[0].get("stck_clpr", 1))
            return (atr / last_close) * 100
    except:
        pass
    return 2.0  # 기본값

def get_position_size_pct(ticker: str) -> float:
    """ATR 기반 동적 포지션 사이징"""
    atr_pct = calc_atr_pct(ticker)
    if atr_pct >= ATR_HIGH_THRESHOLD:
        pct = HIGH_VOL_POSITION
        print(f"[STRATEGY] {ticker} ATR={atr_pct:.1f}% → 고변동성: {pct*100:.0f}% 투입")
    elif atr_pct <= 1.5:
        pct = LOW_VOL_POSITION
        print(f"[STRATEGY] {ticker} ATR={atr_pct:.1f}% → 저변동성: {pct*100:.0f}% 투입")
    else:
        pct = BASE_POSITION_PCT
        print(f"[STRATEGY] {ticker} ATR={atr_pct:.1f}% → 기본: {pct*100:.0f}% 투입")
    return pct

# ── 볼린저밴드 ────────────────────────────────────────
def get_bollinger(ticker: str, period: int = 20) -> dict:
    """볼린저밴드 계산"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_org_adj_prc": "1",
                "fid_period_div_code": "D",
            }
        )
        prices = [float(o["stck_clpr"]) for o in data.get("output2", [])[:period] if o.get("stck_clpr")]
        if len(prices) >= period:
            ma = sum(prices) / period
            std = (sum((p - ma) ** 2 for p in prices) / period) ** 0.5
            return {"upper": ma + 2 * std, "middle": ma, "lower": ma - 2 * std}
    except:
        pass
    return {}

def get_daily_prices(ticker: str, n: int = 20) -> list[float]:
    """일봉 종가 리스트 (최신순)"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_org_adj_prc": "1",
                "fid_period_div_code": "D",
            }
        )
        return [float(o["stck_clpr"]) for o in data.get("output2", [])[:n] if o.get("stck_clpr")]
    except:
        return []

# ── 종합 진입 판단 ────────────────────────────────────
def is_valid_entry(ticker: str, current_price: float, change_rate: float, vol_ratio: float) -> tuple[bool, str]:
    """
    복합 필터 진입 판단
    Returns: (진입가능여부, 사유)
    """
    # 1. 상승률 필터
    if not (SCAN_MIN_CHANGE <= change_rate <= SCAN_MAX_CHANGE):
        return False, f"상승률 범위 초과: {change_rate:.1f}%"

    # 2. 거래량 필터
    if vol_ratio < SCAN_VOL_RATIO:
        return False, f"거래량 부족: {vol_ratio:.1f}배"

    # 3. 주가 필터
    if not (SCAN_MIN_PRICE <= current_price <= SCAN_MAX_PRICE):
        return False, f"주가 범위 초과: {current_price:,}원"

    # 4. RSI 필터
    prices = get_daily_prices(ticker, 20)
    if prices:
        rsi = calc_rsi(prices)
        if not (RSI_MIN <= rsi <= RSI_MAX):
            return False, f"RSI 범위 초과: {rsi:.1f}"
        print(f"[STRATEGY] {ticker} RSI={rsi:.1f} ✅")

    # 5. 볼린저밴드 필터
    bb = get_bollinger(ticker)
    if bb:
        if current_price < bb["middle"]:
            return False, f"볼린저밴드 중간선 하단: {current_price:,} < {bb['middle']:.0f}"
        print(f"[STRATEGY] {ticker} BB중간선={bb['middle']:.0f} 위에 있음 ✅")

    return True, f"거래량{vol_ratio:.0f}배 +{change_rate:.1f}% RSI OK"

# ── 트레일링 스탑 관리 ────────────────────────────────
class TrailingStop:
    """트레일링 스탑 관리"""
    def __init__(self, buy_price: float):
        self.buy_price = buy_price
        self.peak_price = buy_price
        self.activated = False

    def update(self, current_price: float) -> tuple[bool, str]:
        """
        현재가 업데이트 → (청산여부, 사유) 반환
        """
        pnl = (current_price - self.buy_price) / self.buy_price

        # 트레일링 활성화
        if not self.activated and pnl >= TRAIL_ACTIVATE_PCT:
            self.activated = True
            print(f"[TRAIL] 트레일링 스탑 활성화! 수익률 {pnl*100:.2f}%")

        # 고점 갱신
        if current_price > self.peak_price:
            self.peak_price = current_price

        # 손절
        if pnl <= -STOP_LOSS_PCT:
            return True, f"손절 ({pnl*100:+.2f}%)"

        # 트레일링 청산
        if self.activated:
            drop_from_peak = (current_price - self.peak_price) / self.peak_price
            if drop_from_peak <= -TRAIL_DROP_PCT:
                return True, f"트레일링 청산 (고점대비 {drop_from_peak*100:.2f}%, 수익 {pnl*100:+.2f}%)"

        return False, ""
