"""
최적 통합 전략 v2.0
- 하이브리드: 상승장=모멘텀, 하락장=공포매수 자동전환
- 공포매수: RSI<30 과매도 구간 반등 포착
- 양방향: 하락장 감지 시 인버스ETF 자동 편입
- 멀티팩터: RSI+볼린저+거래량+ATR 4중 필터
- 분할매수: 급락 시 단계적 진입
"""
import kis_auth as api

# ── 기본 파라미터 ──────────────────────────────────────
SCAN_MIN_CHANGE   = 1.0
SCAN_MAX_CHANGE   = 10.0
SCAN_VOL_RATIO    = 2.0
SCAN_MIN_PRICE    = 1_000
SCAN_MAX_PRICE    = 200_000

RSI_MIN = 40
RSI_MAX = 75
RSI_OVERSOLD = 30      # 공포매수 기준
RSI_OVERBOUGHT = 70

BASE_POSITION_PCT  = 0.10
HIGH_VOL_POSITION  = 0.07
LOW_VOL_POSITION   = 0.15
ATR_HIGH_THRESHOLD = 3.0

TRAIL_ACTIVATE_PCT = 0.01
TRAIL_DROP_PCT     = 0.008
STOP_LOSS_PCT      = 0.015

KOSPI_CODE = "0001"

# ── 시장 국면 판단 ────────────────────────────────────
def get_market_regime() -> dict:
    """
    시장 국면 분석
    Returns: {
        "regime": "BULL" | "BEAR" | "CRASH",
        "kospi_rsi": float,
        "ma5": float, "ma20": float,
    }
    """
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

            # 국면 판단
            if rsi < 30 and ma5 < ma20 * 0.97:
                regime = "CRASH"   # 폭락 → 공포매수 모드
            elif ma5 < ma20:
                regime = "BEAR"    # 하락장 → 인버스 + 제한 매수
            else:
                regime = "BULL"    # 상승장 → 모멘텀 풀가동

            print(f"[REGIME] 시장국면: {regime} | MA5={ma5:.0f} MA20={ma20:.0f} RSI={rsi:.1f}")
            return {"regime": regime, "kospi_rsi": rsi, "ma5": ma5, "ma20": ma20}
    except Exception as e:
        print(f"[REGIME] 시장 분석 오류: {e}")
    return {"regime": "BULL", "kospi_rsi": 50, "ma5": 0, "ma20": 0}

def is_bull_market() -> bool:
    return True  # 테스트용 - 실전 전환 시 get_market_regime() 사용

# ── 보조 지표 계산 ────────────────────────────────────
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

def get_bollinger(ticker: str, period: int = 20) -> dict:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker,
             "fid_org_adj_prc": "1", "fid_period_div_code": "D"}
        )
        prices = [float(o["stck_clpr"]) for o in data.get("output2", [])[:period] if o.get("stck_clpr")]
        if len(prices) >= period:
            ma = sum(prices) / period
            std = (sum((p - ma) ** 2 for p in prices) / period) ** 0.5
            return {"upper": ma + 2*std, "middle": ma, "lower": ma - 2*std, "std": std}
    except:
        pass
    return {}

def get_daily_prices(ticker: str, n: int = 20) -> list:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker,
             "fid_org_adj_prc": "1", "fid_period_div_code": "D"}
        )
        return [float(o["stck_clpr"]) for o in data.get("output2", [])[:n] if o.get("stck_clpr")]
    except:
        return []

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

# ── 핵심: 국면별 진입 판단 ────────────────────────────
def is_valid_entry(ticker: str, current_price: float, change_rate: float,
                   vol_ratio: float, regime: str = "BULL") -> tuple:
    """
    시장 국면에 따라 다른 기준 적용
    Returns: (진입가능, 사유, 전략유형)
    """
    prices = get_daily_prices(ticker, 20)
    rsi = calc_rsi(prices) if prices else 50.0
    bb = get_bollinger(ticker)

    # ── CRASH 국면: 공포매수 모드 ──────────────────────
    if regime == "CRASH":
        # RSI 과매도 + 볼린저 하단 이탈 → 반등 기대
        if rsi <= RSI_OVERSOLD + 5 and current_price > SCAN_MIN_PRICE:
            if bb and current_price <= bb["middle"]:
                return True, f"공포매수 RSI={rsi:.0f} 과매도반등", "FEAR_BUY"
        # 급락 후 거래량 폭발 = 바닥 신호
        if vol_ratio >= 8 and change_rate >= -5 and change_rate <= 3:
            return True, f"급락후거래량폭발 {vol_ratio:.0f}배", "FEAR_BUY"
        return False, f"공포매수조건 미충족 RSI={rsi:.0f}", ""

    # ── BEAR 국면: 제한적 매수 + 강한 종목만 ─────────────
    if regime == "BEAR":
        # 인버스ETF 신호는 scanner_overseas에서 처리
        # 국내는 아주 강한 종목만 허용
        if not (2.0 <= change_rate <= 8.0): return False, "하락장 상승률 조건", ""
        if vol_ratio < 8: return False, "하락장 거래량 부족", ""
        if rsi < 45 or rsi > 70: return False, f"하락장 RSI 범위 {rsi:.0f}", ""
        return True, f"하락장 강한종목 거래량{vol_ratio:.0f}배", "BEAR_MOMENTUM"

    # ── BULL 국면: 멀티팩터 모멘텀 ───────────────────────
    if not (SCAN_MIN_CHANGE <= change_rate <= SCAN_MAX_CHANGE):
        return False, f"상승률 범위 초과 {change_rate:.1f}%", ""
    if vol_ratio < SCAN_VOL_RATIO:
        return False, f"거래량 부족 {vol_ratio:.1f}배", ""
    if not (SCAN_MIN_PRICE <= current_price <= SCAN_MAX_PRICE):
        return False, f"주가 범위 초과 {current_price:,}원", ""

    # RSI 필터
    if not (RSI_MIN <= rsi <= RSI_MAX):
        return False, f"RSI 범위 초과 {rsi:.0f}", ""

    # 볼린저밴드 - BULL에서는 중간선 위
    if bb and current_price < bb["middle"]:
        return False, f"볼린저 중간선 하단", ""

    print(f"[STRATEGY] ✅ {ticker} RSI={rsi:.0f} 거래량{vol_ratio:.0f}배 +{change_rate:.1f}%")
    return True, f"거래량{vol_ratio:.0f}배 +{change_rate:.1f}% RSI={rsi:.0f}", "MOMENTUM"

# ── 트레일링 스탑 ────────────────────────────────────
class TrailingStop:
    def __init__(self, buy_price: float, strategy_type: str = "MOMENTUM"):
        self.buy_price = buy_price
        self.peak_price = buy_price
        self.activated = False
        self.strategy_type = strategy_type
        # 공포매수는 더 넉넉한 트레일링
        self.activate_pct = 0.015 if strategy_type == "FEAR_BUY" else TRAIL_ACTIVATE_PCT
        self.drop_pct = 0.010 if strategy_type == "FEAR_BUY" else TRAIL_DROP_PCT

    def update(self, current_price: float) -> tuple:
        pnl = (current_price - self.buy_price) / self.buy_price

        if not self.activated and pnl >= self.activate_pct:
            self.activated = True
            print(f"[TRAIL] 트레일링 활성화 {self.strategy_type} {pnl*100:.2f}%")

        if current_price > self.peak_price:
            self.peak_price = current_price

        # 손절
        if pnl <= -STOP_LOSS_PCT:
            return True, f"손절 ({pnl*100:+.2f}%)"

        # 트레일링 청산
        if self.activated:
            drop = (current_price - self.peak_price) / self.peak_price
            if drop <= -self.drop_pct:
                return True, f"트레일링 청산 ({pnl*100:+.2f}%)"

        return False, ""
