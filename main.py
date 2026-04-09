"""KIS 자동매매 봇 v2.1"""
import time
from datetime import datetime
import pytz
import scanner, scanner_overseas
import trader, trader_overseas
import monitor, monitor_overseas
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
    return SCAN_START_TIME <= now_str() <= SCAN_END_TIME

def is_overseas_scan_time() -> bool:
    t = now_str()
    return "22:30" <= t <= "23:59" or "00:00" <= t <= "00:30"

def is_domestic_force_close() -> bool:
    return now_str() >= FORCE_CLOSE_TIME

def is_overseas_force_close() -> bool:
    t = now_str()
    return "05:30" <= t <= "06:00"

def get_balance_info() -> dict:
    try:
        parts = ACCOUNT_NO.split("-")
        acc_no   = parts[0]
        acc_prod = parts[1] if len(parts) > 1 else "01"
        tr_id = "VTTC8434R" if IS_PAPER else "TTTC8434R"
        data = api.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            {
                "CANO": acc_no,
                "ACNT_PRDT_CD": acc_prod,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "N",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
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
        else:
            print(f"[BALANCE] API 오류: {data.get('msg1', '')}")
    except Exception as e:
        print(f"[BALANCE] 오류: {e}")
    return {}

def send_summary(dom_pos: dict, os_pos: dict, trade_count: int):
    now = now_kst().strftime("%H:%M")
    lines = [f"📊 <b>현황 요약</b> ({now} KST)"]

    bal = get_balance_info()
    if bal:
        em = "📈" if bal["eval_profit"] >= 0 else "📉"
        lines.append(
            f"\n💰 <b>계좌 잔고</b>\n"
            f"총평가: {bal['total_eval']:,}원\n"
            f"주문가능: {bal['available']:,}원\n"
            f"매수금액: {bal['buy_amount']:,}원\n"
            f"{em} 평가손익: {bal['eval_profit']:+,}원 ({bal['profit_rate']:+.2f}%)"
        )
    else:
        lines.append("\n💰 잔고 조회 실패")

    if dom_pos:
        lines.append("\n🇰🇷 <b>국내 보유</b>")
        for ticker, pos in dom_pos.items():
            try:
                pd = api.get(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    "FHKST01010100",
                    {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
                )
                cur = int(pd.get("output", {}).get("stck_prpr", pos["buy_price"]))
                pnl = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                em = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"• {pos['name']}({ticker})\n"
                    f"  {pos['buy_price']:,}→{cur:,}원 {em}{pnl:+.2f}%"
                )
            except:
                lines.append(f"• {pos['name']}({ticker}) {pos['qty']}주")
    else:
        lines.append("\n🇰🇷 국내 보유 없음")

    if os_pos:
        lines.append("\n🇺🇸 <b>해외 보유</b>")
        for ticker, pos in os_pos.items():
            try:
                pd = api.get(
                    "/uapi/overseas-price/v1/quotations/price",
                    "HHDFS00000300",
                    {"AUTH": "", "EXCD": pos["exchange"], "SYMB": ticker}
                )
                cur = float(pd.get("output", {}).get("last", pos["buy_price"]))
                pnl = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                em = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"• {pos['name']}({ticker})\n"
                    f"  ${pos['buy_price']:.2f}→${cur:.2f} {em}{pnl:+.2f}%"
                )
            except:
                lines.append(f"• {pos['name']}({ticker}) {pos['qty']}주")
    else:
        lines.append("\n🇺🇸 해외 보유 없음")

    lines.append(f"\n📈 오늘 거래: {trade_count}회")
    telegram.send("\n".join(lines))

def main():
    print("=" * 55)
    print("🚀 KIS 자동매매 봇 v2.1")
    print(f"국내: {SCAN_START_TIME}~{SCAN_END_TIME} | 강제청산 {FORCE_CLOSE_TIME}")
    print(f"해외: 22:30~00:30 | 강제청산 05:30")
    print(f"현재 KST: {now_str()}")
    print("=" * 55)

    try:
        api.get_access_token()
        print("[AUTH] 초기 토큰 발급 완료")
    except Exception as e:
        print(f"[AUTH] 초기 토큰 발급 실패: {e}")
    time.sleep(2)

    telegram.send(
        "🚀 <b>KIS 봇 v2.1 시작</b>\n"
        "전략: 하이브리드 (모멘텀+공포매수+인버스)\n"
        f"현재: {now_str()} KST"
    )

    dom_pos = {}
    os_pos  = {}

    last_dom_scan    = None
    last_os_scan     = None
    last_dom_monitor = None
    last_os_monitor  = None
    last_summary     = None

    dom_forced = False
    os_forced  = False
    trade_count = 0

    while True:
        now = now_kst()
        now_hm = now.strftime("%H:%M")

        def elapsed(t):
            return 9999 if t is None else (now - t).seconds

        # ════ 국내장 ════════════════════════════════════
        if is_domestic_open():
            if now_hm == "09:00":
                dom_forced = False

            if is_domestic_force_close() and dom_pos and not dom_forced:
                monitor.force_close_all(dom_pos)
                dom_pos.clear()
                dom_forced = True

            if dom_pos and elapsed(last_dom_monitor) >= MONITOR_INTERVAL_SEC:
                closed = monitor.check_positions(dom_pos)
                for t in closed:
                    dom_pos.pop(t, None)
                    trade_count += 1
                last_dom_monitor = now

            if is_domestic_scan_time() and len(dom_pos) < MAX_POSITIONS:
                if elapsed(last_dom_scan) >= SCAN_INTERVAL_SEC:
                    candidates = scanner.scan_candidates(
                        exclude_tickers=list(dom_pos.keys())
                    )
                    for c in candidates:
                        if len(dom_pos) >= MAX_POSITIONS:
                            break
                        result = trader.buy_market(
                            c["ticker"], c["name"],
                            reason=f"[{c.get('strategy_type','')}] {c['reason']}"
                        )
                        if result:
                            result["strategy_type"] = c.get("strategy_type", "MOMENTUM")
                            dom_pos[c["ticker"]] = result
                            monitor.register_position(
                                c["ticker"], result["buy_price"],
                                c.get("strategy_type", "MOMENTUM")
                            )
                            trade_count += 1
                    last_dom_scan = now

        # ════ 해외장 ════════════════════════════════════
        if is_overseas_open():
            if now_hm == "22:30":
                os_forced = False

            if is_overseas_force_close() and os_pos and not os_forced:
                monitor_overseas.force_close_overseas(os_pos)
                os_pos.clear()
                os_forced = True

            if os_pos and elapsed(last_os_monitor) >= MONITOR_INTERVAL_SEC:
                closed = monitor_overseas.check_overseas_positions(os_pos)
                for t in closed:
                    os_pos.pop(t, None)
                    trade_count += 1
                last_os_monitor = now

            if is_overseas_scan_time() and len(os_pos) < MAX_POSITIONS:
                if elapsed(last_os_scan) >= SCAN_INTERVAL_SEC:
                    candidates = scanner_overseas.scan_overseas_candidates(
                        exclude_tickers=list(os_pos.keys())
                    )
                    for c in candidates:
                        if len(os_pos) >= MAX_POSITIONS:
                            break
                        result = trader_overseas.buy_overseas(
                            c["ticker"], c["name"], c["exchange"],
                            reason=f"[{c.get('regime','')}] +{c['change_rate']:.1f}%"
                        )
                        if result:
                            os_pos[c["ticker"]] = result
                            trade_count += 1
                    last_os_scan = now

        # ════ 30분마다 현황 ═════════════════════════════
        if elapsed(last_summary) >= 1800:
            if is_domestic_open() or is_overseas_open():
                send_summary(dom_pos, os_pos, trade_count)
            last_summary = now

        # ════ 일일 결산 15:31 ═══════════════════════════
        if now_hm == "15:31":
            bal = get_balance_info()
            msg = f"📋 <b>오늘 결산</b>\n거래: {trade_count}회"
            if bal:
                em = "📈" if bal["eval_profit"] >= 0 else "📉"
                msg += (
                    f"\n총평가: {bal['total_eval']:,}원\n"
                    f"{em} 손익: {bal['eval_profit']:+,}원 ({bal['profit_rate']:+.2f}%)"
                )
            telegram.send(msg)
            trade_count = 0

        time.sleep(5)

if __name__ == "__main__":
    main()
