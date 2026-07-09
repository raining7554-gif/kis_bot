"""일회성 전량 청산 모드 — BOT_MODE=liquidate

계좌의 모든 국내/해외 보유 종목을 '시장가'로 매도하고, 텔레그램으로 보고한 뒤
프로세스를 종료한다. 실거래(실제 돈) 작업이므로 BOT_MODE=liquidate 로 명시적으로
켤 때만 실행된다. 보유가 없으면 아무 것도 하지 않는다(idempotent).

주의: '시장가' 체결이라 장중에 실행해야 실제로 팔린다.
  - 국내: 한국 09:00~15:20
  - 미국: 한국시간 밤(미장 정규장)
장 마감 상태에서 돌리면 주문이 거부되어 '실패'로 보고된다.
"""
import kis_auth as api
import telegram
import trader
import trader_overseas as ot
from config import ACCOUNT_NO, IS_PAPER


def _acc_parts():
    parts = ACCOUNT_NO.split("-")
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "01")


def get_domestic_holdings() -> list:
    acc_no, acc_prod = _acc_parts()
    tr_id = "VTTC8434R" if IS_PAPER else "TTTC8434R"
    out = []
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance", tr_id,
            {
                "CANO": acc_no, "ACNT_PRDT_CD": acc_prod,
                "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )
        for o in data.get("output1", []) or []:
            try:
                qty = int(float(o.get("hldg_qty", 0) or 0))
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                out.append({
                    "ticker": o.get("pdno", ""),
                    "name": o.get("prdt_name", "") or o.get("pdno", ""),
                    "qty": qty,
                    "avg": float(o.get("pchs_avg_pric", 0) or 0),
                })
    except Exception as e:
        print(f"[LIQUIDATE] 국내 잔고 조회 오류: {e}")
    return out


def get_overseas_holdings() -> list:
    acc_no, acc_prod = _acc_parts()
    out = []
    try:
        data = api.get(
            "/uapi/overseas-stock/v1/trading/inquire-present-balance",
            "VTRP6504R" if IS_PAPER else "CTRP6504R",
            {
                "CANO": acc_no, "ACNT_PRDT_CD": acc_prod,
                "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": "840",
                "TR_MKET_CD": "00", "INQR_DVSN_CD": "00",
            },
        )
        for o in data.get("output1", []) or []:
            try:
                qty = int(float(o.get("ovrs_cblc_qty", 0) or o.get("cblc_qty13", 0)
                                 or o.get("ord_psbl_qty", 0) or 0))
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                out.append({
                    "ticker": o.get("pdno", "") or o.get("ovrs_pdno", ""),
                    "name": o.get("prdt_name", "") or o.get("ovrs_item_name", "")
                            or o.get("pdno", ""),
                    "exchange": o.get("ovrs_excg_cd", "") or o.get("tr_mket_cd", ""),
                    "qty": qty,
                    "avg": float(o.get("pchs_avg_pric", 0) or 0),
                })
    except Exception as e:
        print(f"[LIQUIDATE] 해외 잔고 조회 오류: {e}")
    return out


def main():
    print("=" * 55)
    print("🧹 전량 청산 모드 (BOT_MODE=liquidate)")
    print(f"{'📝 모의' if IS_PAPER else '💵 실거래'}")
    print("=" * 55)

    try:
        api.get_access_token()
    except Exception as e:
        print(f"[AUTH] 토큰 오류: {e}")

    dom = get_domestic_holdings()
    os_h = get_overseas_holdings()

    if not dom and not os_h:
        telegram.send_force(
            "🧹 <b>전량 청산</b>\n보유 종목이 없습니다. 청산할 것 없음.\n"
            "봇 정지 준비 완료 — Railway 서비스를 Remove/Pause 하세요."
        )
        print("[LIQUIDATE] 보유 종목 없음 — 종료")
        return

    lines = ["🧹 <b>전량 청산 시작</b>"]
    for h in dom:
        lines.append(f"• 🇰🇷 {h['name']}({h['ticker']}) {h['qty']}주")
    for h in os_h:
        lines.append(f"• 🇺🇸 {h['name']}({h['ticker']}) {h['qty']}주 [{h['exchange']}]")
    telegram.send_force("\n".join(lines))

    sold = failed = 0
    for h in dom:
        ok = trader.sell_market(h["ticker"], h["name"], h["qty"], h["avg"], "전량청산")
        sold += 1 if ok else 0
        failed += 0 if ok else 1
    for h in os_h:
        if not h["exchange"]:
            print(f"[LIQUIDATE] {h['ticker']} 거래소 코드 없음 — 수동 매도 필요")
            failed += 1
            continue
        ok = ot.sell_overseas(h["ticker"], h["name"], h["exchange"],
                              h["qty"], h["avg"], "전량청산")
        sold += 1 if ok else 0
        failed += 0 if ok else 1

    msg = f"🧹 <b>청산 완료</b>\n성공 {sold}종목 / 실패 {failed}종목"
    if failed:
        msg += ("\n⚠️ 실패분은 장 마감/시간대/권한 문제일 수 있어요.\n"
                "→ 장중에 다시 배포하거나, KIS/토스 앱에서 직접 매도하세요.")
    msg += "\n\n봇은 정지 상태로 두세요 — Railway 서비스를 Remove/Pause 권장."
    telegram.send_force(msg)
    print(f"[LIQUIDATE] 완료 — 성공 {sold} / 실패 {failed}")


if __name__ == "__main__":
    main()
