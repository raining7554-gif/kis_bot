import time
from datetime import datetime
import pytz
import scanner
import scanner_overseas
import trader
import trader_overseas
import monitor
import monitor_overseas
import telegram
import kis_auth as api
from config import (
    SCAN_START_TIME, SCAN_END_TIME, FORCE_CLOSE_TIME,
    MAX_POSITIONS, SCAN_INTERVAL_SEC, MONITOR_INTERVAL_SEC,
    ACCOUNT_NO, IS_PAPER
)

KST = pytz.timezone("Asia/Seoul")

def now_kst() -> datetime:
    return datetime.now(KST)

def now_str() -> str:
    return now_kst().strftime("%H:%M")

def is_domestic_open() -> bool:
    t = now_str()
    return "09:00" <= t <= "15:30"

def is_overseas_open() -> bool:
    t = now_str()
    return t >= "22:30" or t <= "06:00"

def is_domestic_scan_time() -> bool:
    t = now_str()
    return SCAN_START_TIME <= t <= SCAN_END_TIME

def is_overseas_scan_time() -> bool:
    t = now_str()
    return "22:30" <= t <= "23:59" or "00:00" <= t <= "00:30"

def is_domestic_force_close() -> bool:
    return now_str() >= FORCE_CLOSE_TIME

def is_overseas_force_close() -> bool:
    t = now_str()
    return "05:30" <= t <= "06:00"

def get_balance_info() -> dict:
    """계좌 잔고 조회"""
    try:
        acc_no, acc_prod = ACCOUNT_NO.split("-") if "-" in ACCOUNT_NO else (ACCOUNT_NO, "01")
        tr_id = "VTTC8434R" if IS_PAPER else "TTTC8434R"
        data = api.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            {
                "CANO": acc_no, "ACNT_PRDT_CD": acc_prod,
                "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "01",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            }
        )
        if data.get("rt_cd") == "0":
            o = data.get("output2", [{}])[0]
            return {
                "total_eval": int(o.get("tot_evlu_amt", 0)),
                "available": int(o.get("prvs_rcdl_excc_amt", 0)),
                "buy_amount": int(o.get("pchs_amt_smtl_amt", 0)),
                "eval_profit": int(o.get("evlu_pfls_smtl_amt", 0)),
                "profit_rate": float(o.get("asst_icdc_erng_rt", 0)),
            }
    except Exception as e:
        print(f"[MAIN] 잔고 조회 오류: {e}")
    return {}

def send_summary(domestic_positions: dict, overseas_positions: dict, trade_count: int):
    """30분마다 종합 현황 알림"""
    now = now_kst().strftime("%H:%M")
    lines = [f"📊 <b>현황 요약</b> ({now} KST)"]

    # ── 계좌 잔고 ──────────────────────────────────────
    bal = get_balance_info()
    if bal:
        emoji = "📈" if bal["eval_profit"] >= 0 else "📉"
        lines.append(
            f"\n💰 <b>계좌 잔고</b>\n"
            f"총평가금액: {bal['total_eval']:,}원\n"
            f"주문가능금액: {bal['available']:,}원\n"
            f"매수금액: {bal['buy_amount']:,}원\n"
            f"{emoji} 평가손익: {bal['eval_profit']:+,}원 ({bal['profit_rate']:+.2f}%)"
        )

    # ── 국내 포지션 ────────────────────────────────────
    if domestic_positions:
        lines.append("\n🇰🇷 <b>국내 보유종목</b>")
        for ticker, pos in domestic_positions.items():
            try:
                price_data = api.get(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    "FHKST01010100",
                    {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
                )
                cur = int(price_data.get("output", {}).get("stck_prpr", pos["buy_price"]))
                pnl = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                em = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"• {pos['name']}({ticker}) {pos['qty']}주\n"
                    f"  매수 {pos['buy_price']:,}원 → 현재 {cur:,}원 {em}{pnl:+.2f}%"
                )
            except:
                lines.append(f"• {pos['name']}({ticker}) {pos['qty']}주 @ {pos['buy_price']:,}원")
    else:
        lines.append("\n🇰🇷 국내 보유종목 없음")

    # ── 해외 포지션 ────────────────────────────────────
    if overseas_positions:
        lines.append("\n🇺🇸 <b>해외 보유종목</b>")
        for ticker, pos in overseas_positions.items():
            try:
                price_data = api.get(
                    "/uapi/overseas-price/v1/quotations/price",
                    "HHDFS00000300",
                    {"AUTH": "", "EXCD": pos["exchange"], "SYMB": ticker}
                )
                cur = float(price_data.get("output", {}).get("last", pos["buy_price"]))
                pnl = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                em = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"• {pos['name']}({ticker}) {pos['qty']}주\n"
                    f"  매수 ${pos['buy_price']:.2f} → 현재 ${cur:.2f} {em}{pnl:+.2f}%"
                )
            except:
                lines.append(f"• {pos['name']}({ticker}) {pos['qty']}주 @ ${pos['buy_price']:.2f}")
    else:
        lines.append("\n🇺🇸 해외 보유종목 없음")

    lines.append(f"\n📈 오늘 거래: {trade_count}회")
    telegram.send("\n".join(lines))

def main():
    print("=" * 55)
    print("🚀 KIS 국내 + 해외 자동매매 봇 시작")
    print(f"국내: {SCAN_START_TIME}~{SCAN_END_TIME} | 강제청산 {FORCE_CLOSE_TIME}")
    print(f"해외: 22:30~00:30 스캔 | 강제청산 05:30")
    print(f"현재 KST: {now_str()}")
    print("=" * 55)

    # 토큰 먼저 발급
    try:
        api.get_access_token()
        print("[AUTH] 초기 토큰 발급 완료")
    except Exception as e:
        print(f"[AUTH] 초기 토큰 발급 실패: {e}")
    time.sleep(2)

    telegram.send(
        "🚀 <b>KIS 자동매매 봇 시작</b>\n"
        f"국내: {SCAN_START_TIME}~{SCAN_END_TIME} 스캔\n"
        "해외: 22:30~00:30 스캔\n"
        f"현재시각: {now_str()} KST"
    )

    domestic_positions = {}
    overseas_positions = {}

    last_dom_scan     = None
    last_os_scan      = None
    last_dom_monitor  = None
    last_os_monitor   = None
    last_summary_time = None

    dom_forced_closed = False
    os_forced_closed  = False
    trade_count = 0

    while True:
        now = now_kst()
        now_hm = now.strftime("%H:%M")

        def elapsed(last_time):
            if last_time is None:
                return 9999
            return (now - last_time).seconds

        # ═══════════════════════════════════════════════
        #  국내장
        # ═══════════════════════════════════════════════
        if is_domestic_open():
            if now_hm == "09:00":
                dom_forced_closed = False

            if is_domestic_force_close() and domestic_positions and not dom_forced_closed:
                monitor.force_close_all(domestic_positions)
                domestic_positions.clear()
                dom_forced_closed = True

            if domestic_positions and elapsed(last_dom_monitor) >= MONITOR_INTERVAL_SEC:
                closed = monitor.check_positions(domestic_positions)
                for t in closed:
                    domestic_positions.pop(t, None)
                    trade_count += 1
                last_dom_monitor = now

            if is_domestic_scan_time() and len(domestic_positions) < MAX_POSITIONS:
                if elapsed(last_dom_scan) >= SCAN_INTERVAL_SEC:
                    candidates = scanner.scan_candidates(
                        exclude_tickers=list(domestic_positions.keys())
                    )
                    for c in candidates:
                        if len(domestic_positions) >= MAX_POSITIONS:
                            break
                        result = trader.buy_market(
                            c["ticker"], c["name"],
                            reason=f"거래량{c['vol_ratio']:.0f}배 +{c['change_rate']:.1f}%"
                        )
                        if result:
                            domestic_positions[c["ticker"]] = result
                            trade_count += 1
                    last_dom_scan = now

        # ═══════════════════════════════════════════════
        #  해외장
        # ═══════════════════════════════════════════════
        if is_overseas_open():
            if now_hm == "22:30":
                os_forced_closed = False

            if is_overseas_force_close() and overseas_positions and not os_forced_closed:
                monitor_overseas.force_close_overseas(overseas_positions)
                overseas_positions.clear()
                os_forced_closed = True

            if overseas_positions and elapsed(last_os_monitor) >= MONITOR_INTERVAL_SEC:
                closed = monitor_overseas.check_overseas_positions(overseas_positions)
                for t in closed:
                    overseas_positions.pop(t, None)
                    trade_count += 1
                last_os_monitor = now

            if is_overseas_scan_time() and len(overseas_positions) < MAX_POSITIONS:
                if elapsed(last_os_scan) >= SCAN_INTERVAL_SEC:
                    candidates = scanner_overseas.scan_overseas_candidates(
                        exclude_tickers=list(overseas_positions.keys())
                    )
                    for c in candidates:
                        if len(overseas_positions) >= MAX_POSITIONS:
                            break
                        result = trader_overseas.buy_overseas(
                            c["ticker"], c["name"], c["exchange"],
                            reason=f"+{c['change_rate']:.1f}% 모멘텀"
                        )
                        if result:
                            overseas_positions[c["ticker"]] = result
                            trade_count += 1
                    last_os_scan = now

        # ═══════════════════════════════════════════════
        #  30분마다 종합 현황
        # ═══════════════════════════════════════════════
        if elapsed(last_summary_time) >= 1800:
            if is_domestic_open() or is_overseas_open():
                send_summary(domestic_positions, overseas_positions, trade_count)
            last_summary_time = now

        # ═══════════════════════════════════════════════
        #  일일 결산 (15:31)
        # ═══════════════════════════════════════════════
        if now_hm == "15:31":
            bal = get_balance_info()
            msg = f"📋 <b>오늘 결산</b>\n거래 횟수: {trade_count}회"
            if bal:
                em = "📈" if bal["eval_profit"] >= 0 else "📉"
                msg += (
                    f"\n총평가금액: {bal['total_eval']:,}원\n"
                    f"{em} 평가손익: {bal['eval_profit']:+,}원 ({bal['profit_rate']:+.2f}%)"
                )
            telegram.send(msg)
            trade_count = 0

        time.sleep(5)

if __name__ == "__main__":
    main()
