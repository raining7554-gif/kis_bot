"""
최적 통합 전략 v2.1
- RSI/볼린저 API 호출 제거 (안정성 우선)
- 거래량 + 상승률 + 주가 3중 필터로 단순화
- 시장 국면 자동 감지 유지
"""
import kis_auth as api

# ── 기본 파라미터 ──────────────────────────────────────
SCAN_MIN_CHANGE   = 1.0
SCAN_MAX_CHANGE   = 10.0
SCAN_VOL_RATIO    = 2.0
SCAN_MIN_PRICE    = 1_000
SCAN_MAX_PRICE    = 200_000

BASE_POSITION_PCT  = 0.10
HIGH_VOL_POSITION  = 0.07
LOW_VOL_POSITION   = 0.15
ATR_HIGH_THRESHOLD = 3.0

TRAIL_ACTIVATE_PCT = 0.01
TRAIL_DROP_PCT     = 0.008
STOP_LOSS_PCT      = 0.015

KOSPI_CODE = "0001"

# ── 시장 국면 판단 ────────────────────────────────────
def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[i-1] - prices[i]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_market_regime() -> dict:
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
            ma5  = sum(prices[:5]) / 5
            ma20 = sum(prices[:20]) / 20
            rsi  = calc_rsi(prices)
            if rsi < 30 and ma5 < ma20 * 0.97:
                regime = "CRASH"
            elif ma5 < ma20:
                regime = "BEAR"
            else:
                regime = "BULL"
            print(f"[REGIME] 국면: {regime} MA5={ma5:.0f} MA20={ma20:.0f} RSI={rsi:.1f}")
            return {"regime": regime, "kospi_rsi": rsi, "ma5": ma5, "ma20": ma20}
    except Exception as e:
        print(f"[REGIME] 오류: {e}")
    return {"regime": "BULL", "kospi_rsi": 50, "ma5": 0, "ma20": 0}

def is_bull_market() -> bool:
    return True  # 테스트용

def calc_atr_pct(ticker: str) -> float:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker,
             "fid_org_adj_prc": "1", "fid_period_div_code": "D"}
        )
        outputs = data.get("output2", [])[:14]
        trs = []
        for o in outputs:
            h = float(o.get("stck_hgpr", 0))
            l = float(o.get("stck_lwpr", 0))
            if h and l:
                trs.append(h - l)
        if trs:
            atr = sum(trs) / len(trs)
            last_close = float(outputs[0].get("stck_clpr", 1))
            return (atr / last_close) * 100
    except:
        pass
    return 2.0

def get_position_size_pct(ticker: str) -> float:
    atr_pct = calc_atr_pct(ticker)
    if atr_pct >= ATR_HIGH_THRESHOLD:
        pct = HIGH_VOL_POSITION
    elif atr_pct <= 1.5:
        pct = LOW_VOL_POSITION
    else:
        pct = BASE_POSITION_PCT
    print(f"[STRATEGY] {ticker} ATR={atr_pct:.1f}% → 포지션 {pct*100:.0f}%")
    return pct

# ── 진입 판단 (단순화) ────────────────────────────────
def is_valid_entry(ticker: str, current_price: float, change_rate: float,
                   vol_ratio: float, regime: str = "BULL") -> tuple:
    """거래량 + 상승률 + 주가 3중 필터"""

    # CRASH: 급락 후 거래량 폭발 종목
    if regime == "CRASH":
        if vol_ratio >= 5 and -5 <= change_rate <= 5:
            return True, f"공포매수 거래량{vol_ratio:.0f}배", "FEAR_BUY"
        return False, f"공포매수 조건 미충족", ""

    # BEAR: 강한 종목만
    if regime == "BEAR":
        if vol_ratio >= 8 and 2.0 <= change_rate <= 8.0:
            return True, f"하락장 강한종목 거래량{vol_ratio:.0f}배", "BEAR_MOMENTUM"
        return False, f"하락장 조건 미충족", ""

    # BULL: 기본 3중 필터
    if not (SCAN_MIN_CHANGE <= change_rate <= SCAN_MAX_CHANGE):
        return False, f"상승률 {change_rate:.1f}%", ""
    if vol_ratio < SCAN_VOL_RATIO:
        return False, f"거래량 {vol_ratio:.1f}배", ""
    if not (SCAN_MIN_PRICE <= current_price <= SCAN_MAX_PRICE):
        return False, f"주가 {current_price:,}원", ""

    print(f"[STRATEGY] ✅ {ticker} +{change_rate:.1f}% 거래량{vol_ratio:.0f}배")
    return True, f"거래량{vol_ratio:.0f}배 +{change_rate:.1f}%", "MOMENTUM"

# ── 트레일링 스탑 ────────────────────────────────────
class TrailingStop:
    def __init__(self, buy_price: float, strategy_type: str = "MOMENTUM"):
        self.buy_price = buy_price
        self.peak_price = buy_price
        self.activated = False
        self.strategy_type = strategy_type
        self.activate_pct = 0.015 if strategy_type == "FEAR_BUY" else TRAIL_ACTIVATE_PCT
        self.drop_pct = 0.010 if strategy_type == "FEAR_BUY" else TRAIL_DROP_PCT

    def update(self, current_price: float) -> tuple:
        pnl = (current_price - self.buy_price) / self.buy_price
        if not self.activated and pnl >= self.activate_pct:
            self.activated = True
            print(f"[TRAIL] 트레일링 활성화 {pnl*100:.2f}%")
        if current_price > self.peak_price:
            self.peak_price = current_price
        if pnl <= -STOP_LOSS_PCT:
            return True, f"손절 ({pnl*100:+.2f}%)"
        if self.activated:
            drop = (current_price - self.peak_price) / self.peak_price
            if drop <= -self.drop_pct:
                return True, f"트레일링 청산 ({pnl*100:+.2f}%)"
        return False, ""
