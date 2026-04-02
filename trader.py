import kis_auth as api
import telegram
from config import ACCOUNT_NO, IS_PAPER, POSITION_SIZE_PCT

def get_account_balance() -> dict:
    """계좌 잔고 조회"""
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    tr_id = "VTTC8434R" if IS_PAPER else "TTTC8434R"
    data = api.get(
        "/uapi/domestic-stock/v1/trading/inquire-balance",
        tr_id,
        {
            "CANO": acc_no,
            "ACNT_PRDT_CD": acc_prod,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
    )
    if data.get("rt_cd") == "0":
        output2 = data.get("output2", [{}])[0]
        return {
            "total_eval": int(output2.get("tot_evlu_amt", 0)),      # 총 평가금액
            "available_cash": int(output2.get("prvs_rcdl_excc_amt", 0)),  # 주문가능현금
        }
    return {"total_eval": 0, "available_cash": 0}

def calc_buy_qty(price: int) -> int:
    """매수 수량 계산 (총 자산의 POSITION_SIZE_PCT)"""
    balance = get_account_balance()
    total = balance["total_eval"]
    available = balance["available_cash"]
    target_amount = int(total * POSITION_SIZE_PCT)
    target_amount = min(target_amount, available)  # 가용 현금 초과 방지
    qty = target_amount // price
    return max(qty, 0)

def buy_market(ticker: str, name: str, reason: str = "모멘텀 진입") -> dict | None:
    """시장가 매수"""
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    tr_id = "VTTC0802U" if IS_PAPER else "TTTC0802U"

    # 현재가 조회
    price_data = api.get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
    )
    current_price = int(price_data.get("output", {}).get("stck_prpr", 0))
    if current_price == 0:
        print(f"[TRADER] 현재가 조회 실패: {ticker}")
        return None

    qty = calc_buy_qty(current_price)
    if qty == 0:
        print(f"[TRADER] 매수 수량 0 - 잔고 부족")
        return None

    body = {
        "CANO": acc_no,
        "ACNT_PRDT_CD": acc_prod,
        "PDNO": ticker,
        "ORD_DVSN": "01",       # 시장가
        "ORD_QTY": str(qty),
        "ORD_UNPR": "0",        # 시장가는 0
    }

    data = api.post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
    if data.get("rt_cd") == "0":
        amount = current_price * qty
        print(f"[TRADER] 매수 완료: {name}({ticker}) {qty}주 @ {current_price:,}원")
        telegram.send_buy(ticker, name, current_price, qty, amount, reason)
        return {"ticker": ticker, "name": name, "qty": qty, "buy_price": current_price}
    else:
        msg = f"매수 실패 {name}({ticker}): {data.get('msg1', '')}"
        print(f"[TRADER] {msg}")
        telegram.send_error(msg)
        return None

def sell_market(ticker: str, name: str, qty: int, buy_price: int, reason: str = "청산") -> bool:
    """시장가 매도"""
    acc_no, acc_prod = ACCOUNT_NO.split("-")
    tr_id = "VTTC0801U" if IS_PAPER else "TTTC0801U"

    # 현재가 조회
    price_data = api.get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
    )
    current_price = int(price_data.get("output", {}).get("stck_prpr", 0))

    body = {
        "CANO": acc_no,
        "ACNT_PRDT_CD": acc_prod,
        "PDNO": ticker,
        "ORD_DVSN": "01",
        "ORD_QTY": str(qty),
        "ORD_UNPR": "0",
    }

    data = api.post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
    if data.get("rt_cd") == "0":
        pnl = (current_price - buy_price) / buy_price * 100
        print(f"[TRADER] 매도 완료: {name}({ticker}) {pnl:+.2f}% - {reason}")
        telegram.send_sell(ticker, name, current_price, qty, pnl, reason)
        return True
    else:
        msg = f"매도 실패 {name}({ticker}): {data.get('msg1', '')}"
        print(f"[TRADER] {msg}")
        telegram.send_error(msg)
        return False
