import kis_auth as api

# 모니터링할 나스닥/NYSE 종목 풀 (거래량 많고 변동성 있는 종목들)
# 실제 운용 시 원하는 종목으로 교체 가능
WATCHLIST = [
    # 나스닥 대형주
    {"ticker": "AAPL",  "name": "애플",       "exchange": "NAS"},
    {"ticker": "MSFT",  "name": "마이크로소프트", "exchange": "NAS"},
    {"ticker": "NVDA",  "name": "엔비디아",    "exchange": "NAS"},
    {"ticker": "TSLA",  "name": "테슬라",      "exchange": "NAS"},
    {"ticker": "META",  "name": "메타",        "exchange": "NAS"},
    {"ticker": "GOOGL", "name": "알파벳",      "exchange": "NAS"},
    {"ticker": "AMZN",  "name": "아마존",      "exchange": "NAS"},
    {"ticker": "AMD",   "name": "AMD",         "exchange": "NAS"},
    {"ticker": "PLTR",  "name": "팔란티어",    "exchange": "NAS"},
    {"ticker": "SOFI",  "name": "소파이",      "exchange": "NAS"},
    # NYSE
    {"ticker": "BAC",   "name": "뱅크오브아메리카", "exchange": "NYS"},
    {"ticker": "F",     "name": "포드",        "exchange": "NYS"},
    {"ticker": "NIO",   "name": "니오",        "exchange": "NYS"},
]

# 스캔 조건
MIN_CHANGE_RATE = 2.0   # 당일 상승률 최소 (%)
MAX_CHANGE_RATE = 8.0   # 당일 상승률 최대 (%)

def get_overseas_price(ticker: str, exchange: str) -> dict:
    """해외 종목 현재가 조회"""
    try:
        data = api.get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS00000300",
            {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker,
            }
        )
        if data.get("rt_cd") == "0":
            output = data.get("output", {})
            return {
                "ticker": ticker,
                "exchange": exchange,
                "price": float(output.get("last", 0)),
                "change_rate": float(output.get("rate", 0)),
                "volume": int(output.get("tvol", 0)),
            }
    except Exception as e:
        print(f"[OS_SCANNER] 가격 조회 오류 ({ticker}): {e}")
    return {}

def scan_overseas_candidates(exclude_tickers: list = []) -> list:
    """
    해외 종목 스캔
    조건: 상승률 2~8% + 거래량 상위
    """
    print("[OS_SCANNER] 해외 종목 스캔 시작...")
    candidates = []

    for stock in WATCHLIST:
        ticker = stock["ticker"]
        if ticker in exclude_tickers:
            continue

        info = get_overseas_price(ticker, stock["exchange"])
        if not info:
            continue

        change_rate = info["change_rate"]
        if not (MIN_CHANGE_RATE <= change_rate <= MAX_CHANGE_RATE):
            continue

        candidates.append({
            "ticker": ticker,
            "name": stock["name"],
            "exchange": stock["exchange"],
            "price": info["price"],
            "change_rate": change_rate,
            "volume": info["volume"],
            "market": "overseas",
        })
        print(f"[OS_SCANNER] ✅ {stock['name']}({ticker}) +{change_rate:.1f}%")

    candidates.sort(key=lambda x: x["change_rate"], reverse=True)
    print(f"[OS_SCANNER] 스캔 완료 - {len(candidates)}개 종목 발견")
    return candidates
