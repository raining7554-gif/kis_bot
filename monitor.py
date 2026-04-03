"""
포지션 모니터링 - 트레일링 스탑 + 동적 손절
"""
import kis_auth as api
import trader
import telegram
from strategy import TrailingStop, TRAIL_ACTIVATE_PCT, TRAIL_DROP_PCT, STOP_LOSS_PCT
from config import FORCE_CLOSE_TIME

# 트레일링 스탑 인스턴스 저장
_trailing_stops: dict[str, TrailingStop] = {}

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

def register_position(ticker: str, buy_price: int):
    """새 포지션 트레일링 스탑 등록"""
    _trailing_stops[ticker] = TrailingStop(buy_price)

def check_positions(positions: dict) -> list:
    """
    포지션 모니터링 - 트레일링 스탑 기반
    """
    closed = []
    for ticker, pos in list(positions.items()):
        current_price = get_current_price(ticker)
        if current_price == 0:
            continue

        trail = _trailing_stops.get(ticker)
        if not trail:
            trail = TrailingStop(pos["buy_price"])
            _trailing_stops[ticker] = trail

        should_close, reason = trail.update(current_price)
        if should_close:
            success = trader.sell_market(
                ticker, pos["name"], pos["qty"], pos["buy_price"], reason
            )
            if success:
                closed.append(ticker)
                _trailing_stops.pop(ticker, None)

    return closed

def force_close_all(positions: dict):
    """강제 전량 청산"""
    if not positions:
        return
    print("[MONITOR] 강제 청산 시작...")
    for ticker, pos in list(positions.items()):
        trader.sell_market(
            ticker, pos["name"], pos["qty"], pos["buy_price"],
            reason="장 마감 전 강제 청산"
        )
    _trailing_stops.clear()
