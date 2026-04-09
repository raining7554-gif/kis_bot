"""
해외 스캐너 v2.0 - 국면별 인버스 자동전환
"""
import kis_auth as api

# ── 상승장 워치리스트 (롱 ETF + 핵심 종목) ─────────────
BULL_WATCHLIST = [
    # 지수 레버리지
    {"ticker": "TQQQ",  "name": "나스닥3배",    "exchange": "NAS"},
    {"ticker": "QLD",   "name": "나스닥2배",    "exchange": "NAS"},
    {"ticker": "UPRO",  "name": "S&P500 3배",   "exchange": "NYS"},
    {"ticker": "SPXL",  "name": "S&P500 3배D",  "exchange": "NYS"},
    {"ticker": "SSO",   "name": "S&P500 2배",   "exchange": "NYS"},
    # AI/반도체 레버리지
    {"ticker": "SOXL",  "name": "반도체3배",    "exchange": "NYS"},
    {"ticker": "TECL",  "name": "기술주3배",    "exchange": "NYS"},
    {"ticker": "FNGU",  "name": "FANG+3배",     "exchange": "NYS"},
    # 단일주 레버리지
    {"ticker": "NVDL",  "name": "엔비디아2배",  "exchange": "NAS"},
    {"ticker": "TSLL",  "name": "테슬라2배",    "exchange": "NAS"},
    {"ticker": "PLTU",  "name": "팔란티어2배",  "exchange": "NYS"},
    # 금/귀금속
    {"ticker": "GDXU",  "name": "금광주3배",    "exchange": "NYS"},
    {"ticker": "NUGT",  "name": "금광주2배",    "exchange": "NYS"},
    {"ticker": "AGQ",   "name": "은2배",        "exchange": "NYS"},
    # 방산
    {"ticker": "DFEN",  "name": "항공방산3배",  "exchange": "NYS"},
    # 핵심 개별주
    {"ticker": "NVDA",  "name": "엔비디아",     "exchange": "NAS"},
    {"ticker": "TSLA",  "name": "테슬라",       "exchange": "NAS"},
    {"ticker": "AMD",   "name": "AMD",          "exchange": "NAS"},
    {"ticker": "META",  "name": "메타",         "exchange": "NAS"},
    {"ticker": "PLTR",  "name": "팔란티어",     "exchange": "NAS"},
    {"ticker": "MSTR",  "name": "마이크로스트레티지", "exchange": "NAS"},
    {"ticker": "COIN",  "name": "코인베이스",   "exchange": "NAS"},
    {"ticker": "HOOD",  "name": "로빈후드",     "exchange": "NAS"},
    {"ticker": "SMCI",  "name": "슈퍼마이크로", "exchange": "NAS"},
    {"ticker": "AVGO",  "name": "브로드컴",     "exchange": "NAS"},
    {"ticker": "IONQ",  "name": "아이온Q",      "exchange": "NYS"},
    {"ticker": "RKLB",  "name": "로켓랩",       "exchange": "NAS"},
    {"ticker": "IBIT",  "name": "비트코인ETF",  "exchange": "NAS"},
    {"ticker": "FAS",   "name": "금융주3배",    "exchange": "NYS"},
    {"ticker": "LABU",  "name": "바이오3배",    "exchange": "NYS"},
]

# ── 하락장 워치리스트 (인버스 ETF) ──────────────────────
BEAR_WATCHLIST = [
    {"ticker": "SQQQ",  "name": "나스닥3배인버스",  "exchange": "NAS"},
    {"ticker": "SPXU",  "name": "S&P500 3배인버스", "exchange": "NYS"},
    {"ticker": "SOXS",  "name": "반도체3배인버스",  "exchange": "NYS"},
    {"ticker": "TECS",  "name": "기술주3배인버스",  "exchange": "NYS"},
    {"ticker": "FNGD",  "name": "FANG+3배인버스",   "exchange": "NYS"},
    {"ticker": "FAZ",   "name": "금융주3배인버스",  "exchange": "NYS"},
    {"ticker": "DUST",  "name": "금광주인버스",     "exchange": "NYS"},
    {"ticker": "TSLQ",  "name": "테슬라인버스",     "exchange": "NAS"},
]

MIN_CHANGE_RATE_BULL = 0.5
MAX_CHANGE_RATE_BULL = 12.0
MIN_CHANGE_RATE_BEAR = 1.5   # 인버스는 시장 하락 시 상승
MAX_CHANGE_RATE_BEAR = 15.0  # 인버스 폭발 가능성

def get_overseas_price(ticker: str, exchange: str) -> dict:
    try:
        data = api.get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS00000300",
            {"AUTH": "", "EXCD": exchange, "SYMB": ticker}
        )
        if data.get("rt_cd") == "0":
            output = data.get("output", {})
            return {
                "ticker": ticker, "exchange": exchange,
                "price": float(output.get("last", 0)),
                "change_rate": float(output.get("rate", 0)),
                "volume": int(output.get("tvol", 0)),
            }
    except Exception as e:
        print(f"[OS_SCANNER] 조회 오류 ({ticker}): {e}")
    return {}

def detect_overseas_regime() -> str:
    """나스닥 지수 방향으로 해외 국면 판단"""
    try:
        info = get_overseas_price("QQQ", "NAS")
        if info:
            rate = info["change_rate"]
            if rate <= -2.0:
                return "BEAR"
            elif rate >= 1.0:
                return "BULL"
    except:
        pass
    return "BULL"

def scan_overseas_candidates(exclude_tickers: list = []) -> list:
    """국면별 롱/인버스 자동 선택"""
    regime = detect_overseas_regime()
    print(f"[OS_SCANNER] 해외 국면: {regime}")

    if regime == "BEAR":
        watchlist = BEAR_WATCHLIST
        min_change = MIN_CHANGE_RATE_BEAR
        max_change = MAX_CHANGE_RATE_BEAR
        print("[OS_SCANNER] 🐻 하락장 - 인버스ETF 스캔")
    else:
        watchlist = BULL_WATCHLIST
        min_change = MIN_CHANGE_RATE_BULL
        max_change = MAX_CHANGE_RATE_BULL
        print("[OS_SCANNER] 🐂 상승장 - 롱ETF/종목 스캔")

    candidates = []
    for stock in watchlist:
        ticker = stock["ticker"]
        if ticker in exclude_tickers:
            continue

        info = get_overseas_price(ticker, stock["exchange"])
        if not info or info["price"] == 0:
            continue

        change_rate = info["change_rate"]
        if not (min_change <= change_rate <= max_change):
            continue

        candidates.append({
            "ticker": ticker,
            "name": stock["name"],
            "exchange": stock["exchange"],
            "price": info["price"],
            "change_rate": change_rate,
            "volume": info["volume"],
            "market": "overseas",
            "regime": regime,
        })
        print(f"[OS_SCANNER] ✅ {stock['name']}({ticker}) +{change_rate:.1f}% [{regime}]")

    candidates.sort(key=lambda x: x["change_rate"], reverse=True)
    print(f"[OS_SCANNER] 완료 - {len(candidates)}개 (국면: {regime})")
    return candidates
