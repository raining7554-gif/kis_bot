import kis_auth as api
import telegram
from config import ACCOUNT_NO, IS_PAPER, POSITION_SIZE_PCT

def get_overseas_balance() -> dict:
    """해외주식 잔고 + 가용 달러 조회"""
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    tr_id = "VTTS3012R" if IS_PAPER else "TTTS3012R"
    try:
        data = api.get(
            "/uapi/overseas-stock/v1/trading/inquire-present-balance",
            tr_id,
            {
                "CANO": acc_no,
                "ACNT_PRDT_CD": acc_prod,
                "WCRC_FRCR_DVSN_CD": "02",
                "NATN_CD": "840",       # 미국 = 840
                "TR_MKET_CD": "00",
                "INQR_DVSN_CD": "00",
            }
        )
        if data.get("rt_cd") == "0":
            output3 = data.get("output3", {})
            return {
                "total_eval_usd": float(output3.get("tot_asst_amt", 0)),
                "available_usd": float(output3.get("ord_psbl_frcr_amt", 0)),
            }
    except Exception as e:
        print(f"[OS_TRADER] 잔고 조회 오류: {e}")
    return {"total_eval_usd": 0, "available_usd": 0}

def calc_overseas_qty(price_usd: float) -> int:
    """매수 수량 계산 (총 자산의 POSITION_SIZE_PCT)"""
    balance = get_overseas_balance()
    total = balance["total_eval_usd"]
    available = balance["available_usd"]
    target = total * POSITION_SIZE_PCT
    target = min(target, available)
    qty = int(target // price_usd)
    return max(qty, 0)

def buy_overseas(ticker: str, name: str, exchange: str, reason: str = "모멘텀 진입") -> dict | None:
    """해외주식 시장가 매수"""
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    tr_id = "VTTT1002U" if IS_PAPER else "TTTT1002U"

    # 현재가 조회
    price_data = api.get(
        "/uapi/overseas-price/v1/quotations/price",
        "HHDFS00000300",
        {"AUTH": "", "EXCD": exchange, "SYMB": ticker}
    )
    current_price = float(price_data.get("output", {}).get("last", 0))
    if current_price == 0:
        print(f"[OS_TRADER] 현재가 조회 실패: {ticker}")
        return None

    qty = calc_overseas_qty(current_price)
    if qty == 0:
        print(f"[OS_TRADER] 매수 수량 0 - 달러 잔고 부족")
        return None

    body = {
        "CANO": acc_no,
        "ACNT_PRDT_CD": acc_prod,
        "OVRS_EXCG_CD": exchange,
        "PDNO": ticker,
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": "0",    # 시장가
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00",
    }

    data = api.post("/uapi/overseas-stock/v1/trading/order", tr_id, body)
    if data.get("rt_cd") == "0":
        amount_usd = current_price * qty
        print(f"[OS_TRADER] 매수 완료: {name}({ticker}) {qty}주 @ ${current_price:.2f}")
        telegram.send(
            f"🟢 <b>해외 매수 체결</b>\n"
            f"종목: {name} ({ticker})\n"
            f"가격: ${current_price:.2f} × {qty}주\n"
            f"금액: ${amount_usd:.2f}\n"
            f"사유: {reason}"
        )
        return {"ticker": ticker, "name": name, "exchange": exchange,
                "qty": qty, "buy_price": current_price, "market": "overseas"}
    else:
        msg = f"해외 매수 실패 {name}({ticker}): {data.get('msg1', '')}"
        print(f"[OS_TRADER] {msg}")
        telegram.send_error(msg)
        return None

def sell_overseas(ticker: str, name: str, exchange: str, qty: int, buy_price: float, reason: str = "청산") -> bool:
    """해외주식 시장가 매도"""
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    tr_id = "VTTT1006U" if IS_PAPER else "TTTT1006U"

    # 현재가 조회
    price_data = api.get(
        "/uapi/overseas-price/v1/quotations/price",
        "HHDFS00000300",
        {"AUTH": "", "EXCD": exchange, "SYMB": ticker}
    )
    current_price = float(price_data.get("output", {}).get("last", 0))

    body = {
        "CANO": acc_no,
        "ACNT_PRDT_CD": ACCOUNT_NO.split("-")[0],
        "ACNT_PRDT_CD": ACCOUNT_NO.split("-")[1],
        "OVRS_EXCG_CD": exchange,
        "PDNO": ticker,
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": "0",
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00",
    }

    # body CANO 수정
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    body["CANO"] = acc_no
    body["ACNT_PRDT_CD"] = acc_prod

    data = api.post("/uapi/overseas-stock/v1/trading/order", tr_id, body)
    if data.get("rt_cd") == "0":
        pnl = (current_price - buy_price) / buy_price * 100
        print(f"[OS_TRADER] 매도 완료: {name}({ticker}) {pnl:+.2f}% - {reason}")
        telegram.send(
            f"{'💰' if pnl >= 0 else '🔴'} <b>해외 매도 체결</b>\n"
            f"종목: {name} ({ticker})\n"
            f"가격: ${current_price:.2f} × {qty}주\n"
            f"수익률: {pnl:+.2f}%\n"
            f"사유: {reason}"
        )
        return True
    else:
        msg = f"해외 매도 실패 {name}({ticker}): {data.get('msg1', '')}"
        print(f"[OS_TRADER] {msg}")
        telegram.send_error(msg)
        return False
