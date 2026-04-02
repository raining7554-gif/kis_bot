import kis_auth as api
import trader
from config import TAKE_PROFIT_PCT, STOP_LOSS_PCT

def get_current_price(ticker: str) -> int:
    """현재가 조회"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
        )
        return int(data.get("output", {}).get("stck_prpr", 0))
    except:
        return 0

def check_positions(positions: dict) -> list:
    """
    보유 포지션 체크 - 익절/손절 조건 확인
    positions: {ticker: {name, qty, buy_price}}
    returns: 청산된 ticker 목록
    """
    closed = []

    for ticker, pos in list(positions.items()):
        current_price = get_current_price(ticker)
        if current_price == 0:
            continue

        buy_price = pos["buy_price"]
        pnl_pct = (current_price - buy_price) / buy_price

        # 익절
        if pnl_pct >= TAKE_PROFIT_PCT:
            success = trader.sell_market(
                ticker, pos["name"], pos["qty"], buy_price,
                reason=f"익절 ({pnl_pct*100:+.2f}%)"
            )
            if success:
                closed.append(ticker)

        # 손절
        elif pnl_pct <= -STOP_LOSS_PCT:
            success = trader.sell_market(
                ticker, pos["name"], pos["qty"], buy_price,
                reason=f"손절 ({pnl_pct*100:+.2f}%)"
            )
            if success:
                closed.append(ticker)

    return closed

def force_close_all(positions: dict) -> None:
    """강제 전량 청산 (장 마감 전)"""
    if not positions:
        return
    print("[MONITOR] 강제 청산 시작...")
    for ticker, pos in list(positions.items()):
        trader.sell_market(
            ticker, pos["name"], pos["qty"], pos["buy_price"],
            reason="장 마감 전 강제 청산"
        )
