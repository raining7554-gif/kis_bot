"""모니터링 v2.0 - 전략유형별 트레일링 스탑"""
import kis_auth as api
import trader
from strategy import TrailingStop

_trailing_stops = {}

def get_current_price(ticker: str) -> int:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
        )
        return int(data.get("output", {}).get("stck_prpr", 0))
    except:
        return 0

def register_position(ticker: str, buy_price: int, strategy_type: str = "MOMENTUM"):
    _trailing_stops[ticker] = TrailingStop(buy_price, strategy_type)

def check_positions(positions: dict) -> list:
    closed = []
    for ticker, pos in list(positions.items()):
        current_price = get_current_price(ticker)
        if current_price == 0:
            continue
        trail = _trailing_stops.get(ticker)
        if not trail:
            strategy_type = pos.get("strategy_type", "MOMENTUM")
            trail = TrailingStop(pos["buy_price"], strategy_type)
            _trailing_stops[ticker] = trail

        should_close, reason = trail.update(current_price)
        if should_close:
            success = trader.sell_market(ticker, pos["name"], pos["qty"], pos["buy_price"], reason)
            if success:
                closed.append(ticker)
                _trailing_stops.pop(ticker, None)
    return closed

def force_close_all(positions: dict):
    if not positions:
        return
    print("[MONITOR] 강제 청산 시작...")
    for ticker, pos in list(positions.items()):
        trader.sell_market(ticker, pos["name"], pos["qty"], pos["buy_price"], "장마감 강제청산")
    _trailing_stops.clear()
