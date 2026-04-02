import kis_auth as api
import trader_overseas as ot
from config import TAKE_PROFIT_PCT, STOP_LOSS_PCT

def get_overseas_price(ticker: str, exchange: str) -> float:
    try:
        data = api.get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS00000300",
            {"AUTH": "", "EXCD": exchange, "SYMB": ticker}
        )
        return float(data.get("output", {}).get("last", 0))
    except:
        return 0.0

def check_overseas_positions(positions: dict) -> list:
    """
    해외 포지션 익절/손절 체크
    positions: {ticker: {name, exchange, qty, buy_price, market}}
    """
    closed = []
    for ticker, pos in list(positions.items()):
        if pos.get("market") != "overseas":
            continue

        current_price = get_overseas_price(ticker, pos["exchange"])
        if current_price == 0:
            continue

        pnl_pct = (current_price - pos["buy_price"]) / pos["buy_price"]

        if pnl_pct >= TAKE_PROFIT_PCT:
            success = ot.sell_overseas(
                ticker, pos["name"], pos["exchange"], pos["qty"], pos["buy_price"],
                reason=f"익절 ({pnl_pct*100:+.2f}%)"
            )
            if success:
                closed.append(ticker)

        elif pnl_pct <= -STOP_LOSS_PCT:
            success = ot.sell_overseas(
                ticker, pos["name"], pos["exchange"], pos["qty"], pos["buy_price"],
                reason=f"손절 ({pnl_pct*100:+.2f}%)"
            )
            if success:
                closed.append(ticker)

    return closed

def force_close_overseas(positions: dict):
    """해외 전량 강제청산"""
    for ticker, pos in list(positions.items()):
        if pos.get("market") != "overseas":
            continue
        ot.sell_overseas(
            ticker, pos["name"], pos["exchange"], pos["qty"], pos["buy_price"],
            reason="장 마감 전 강제청산"
        )
