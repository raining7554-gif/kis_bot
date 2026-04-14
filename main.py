"""KIS 자동매매 봇 v3.0 — 섹터 모멘텀 스윙"""
import time
from datetime import datetime
import pytz
import scanner, scanner_overseas
import trader, trader_overseas
import monitor, monitor_overseas
import telegram
import kis_auth as api
from market_calendar import is_trading_day
from config import (
    DOM_SCAN_START, DOM_SCAN_END, DOM_EOD_CHECK, DOM_CLOSING_MSG,
    DOM_MAX_POSITIONS,
    OS_SCAN_TIME_START, OS_SCAN_TIME_END, OS_EOD_CHECK, OS_MAX_POSITIONS,
    SCAN_INTERVAL_SEC, MONITOR_INTERVAL_SEC, SUMMARY_INTERVAL_SEC,
    ACCOUNT_NO, IS_PAPER,
)

KST = pytz.timezone("Asia/Seoul")


def now_kst():
    return datetime.now(KST)


def hhmm():
    return now_kst().strftime("%H:%M")


# ═══════════════════════════════════════════════════════
# 시간대 헬퍼
# ═══════════════════════════════════════════════════════
def is_dom_market_hours() -> bool:
    """국내 장중(09:00~15:30, 영업일)"""
    if not is_trading_day(now_kst()):
        return False
    return "09:00" <= hhmm() <= "15:30"


def is_dom_scan_time() -> bool:
    if not is_trading_day(now_kst()):
        return False
    return DOM_SCAN_START <= hhmm() <= DOM_SCAN_END


def is_dom_eod_check() -> bool:
    """EOD 체크 윈도우: 15:15~15:20"""
    if not is_trading_day(now_kst()):
        return False
    t = hhmm()
    return DOM_EOD_CHECK <= t <= "15:20"


def is_os_market_hours() -> bool:
    """미장 시간대 (KST 22:30~06:00, 간단 고정)"""
    t = hhmm()
    return t >= "22:30" or t <= "06:00"


def is_os_scan_time() -> bool:
    t = hhmm()
    return OS_SCAN_TIME_START <= t <= OS_SCAN_TIME_END


def is_os_eod_check() -> bool:
    t = hhmm()
    return OS_EOD_CHECK <= t <= "05:55"


# ═══════════════════════════════════════════════════════
# 잔고 조회
# ═══════════════════════════════════════════════════════
def get_balance_info() -> dict:
    try:
        parts = ACCOUNT_NO.split("-")
        acc_no = parts[0]
        acc_prod = parts[1] if len(parts) > 1 else "01"
        tr_id = "VTTC8434R" if IS_PAPER else "TTTC8434R"
        data = api.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            {
                "CANO": acc_no, "ACNT_PRDT_CD": acc_prod,
                "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
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
        print(f"[BALANCE] 오류: {e}")
    return {}


# ═══════════════════════════════════════════════════════
# 현황 요약
# ═══════════════════════════════════════════════════════
def send_summary(dom_pos, os_pos, trade_count):
    lines = [f"📊 <b>현황 요약</b> ({hhmm()} KST)"]
    bal = get_balance_info()
    if bal:
        em = "📈" if bal["eval_profit"] >= 0 else "📉"
        lines.append(
            f"\n💰 <b>계좌</b>\n"
            f"총평가: {bal['total_eval']:,}원\n"
            f"주문가능: {bal['available']:,}원\n"
            f"{em} 평가손익: {bal['eval_profit']:+,}원 ({bal['profit_rate']:+.2f}%)"
        )
    if dom_pos:
        lines.append("\n🇰🇷 <b>국내 보유</b>")
        for t, p in dom_pos.items():
            lines.append(f"• {p['name']}({t}) {p['qty']}주 @ {p['buy_price']:,}")
    else:
        lines.append("\n🇰🇷 국내 보유 없음")
    if os_pos:
        lines.append("\n🇺🇸 <b>해외 보유</b>")
        for t, p in os_pos.items():
            lines.append(f"• {p['name']}({t}) {p['qty']}주 @ ${p['buy_price']:.2f}")
    else:
        lines.append("\n🇺🇸 해외 보유 없음")
    lines.append(f"\n📈 오늘 거래: {trade_count}회")
    telegram.send("\n".join(lines), dedup_sec=600)


# ═══════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════
def main():
    print("=" * 55)
    print("🚀 KIS 자동매매 봇 v3.0 (섹터 스윙)")
    print(f"국내 진입: {DOM_SCAN_START}~{DOM_SCAN_END} | EOD체크 {DOM_EOD_CHECK}")
    print(f"해외 진입: {OS_SCAN_TIME_START}~{OS_SCAN_TIME_END} (KST)")
    print(f"현재: {hhmm()} KST")
    print("=" * 55)

    try:
        api.get_access_token()
    except Exception as e:
        print(f"[AUTH] 초기 토큰 실패: {e}")
    time.sleep(2)

    telegram.send_force(
        "🚀 <b>KIS 봇 v3.0 시작</b>\n"
        "전략: 섹터 모멘텀 스윙 (국장+나스닥)\n"
        f"국내 진입: {DOM_SCAN_START}~{DOM_SCAN_END}\n"
        f"해외 진입: {OS_SCAN_TIME_START}~{OS_SCAN_TIME_END} KST\n"
        f"보유: 국장 최대 {DOM_MAX_POSITIONS} / 나스닥 최대 {OS_MAX_POSITIONS}\n"
        f"현재 {hhmm()} KST"
    )

    dom_pos, os_pos = {}, {}
    last_dom_scan = last_os_scan = None
    last_dom_mon = last_os_mon = None
    last_summary = None
    dom_eod_done = False
    os_eod_done = False
    sent_closing = False
    trade_count = 0

    def elapsed(t):
        return 9999 if t is None else (now_kst() - t).seconds

    while True:
        now = now_kst()
        t_hm = now.strftime("%H:%M")

        # ════ 국내장 ════════════════════════════════════
        if is_dom_market_hours():
            # 09:00 ~ 09:05 초기화
            if t_hm == "09:00":
                dom_eod_done = False
                sent_closing = False

            # 보유 포지션 실시간 감시
            if dom_pos and elapsed(last_dom_mon) >= MONITOR_INTERVAL_SEC:
                closed = monitor.check_positions(dom_pos)
                for t in closed:
                    dom_pos.pop(t, None)
                    trade_count += 1
                last_dom_mon = now

            # 신규 진입 (스캔 시간대)
            if is_dom_scan_time() and len(dom_pos) < DOM_MAX_POSITIONS:
                if elapsed(last_dom_scan) >= SCAN_INTERVAL_SEC:
                    try:
                        cands = scanner.scan_candidates(
                            exclude_tickers=list(dom_pos.keys())
                        )
                    except Exception as e:
                        print(f"[MAIN] 국내 스캔 오류: {e}")
                        cands = []
                    for c in cands:
                        if len(dom_pos) >= DOM_MAX_POSITIONS:
                            break
                        res = trader.buy_market(
                            c["ticker"], c["name"],
                            reason=f"[{c.get('sector','')}] {c['reason']}",
                        )
                        if res:
                            res["strategy_type"] = "SWING"
                            dom_pos[c["ticker"]] = res
                            monitor.register_position(
                                c["ticker"], res["buy_price"], "SWING"
                            )
                            trade_count += 1
                    last_dom_scan = now

            # EOD 일봉 청산 체크 (15:15 ~ 15:20, 1회만)
            if is_dom_eod_check() and not dom_eod_done and dom_pos:
                print("[MAIN] EOD 일봉 청산 체크")
                closed = monitor.check_eod(dom_pos)
                for t in closed:
                    dom_pos.pop(t, None)
                    trade_count += 1
                dom_eod_done = True

        # ════ 해외장 ════════════════════════════════════
        if is_os_market_hours():
            if t_hm == "22:30":
                os_eod_done = False

            # 실시간 감시
            if os_pos and elapsed(last_os_mon) >= MONITOR_INTERVAL_SEC:
                closed = monitor_overseas.check_overseas_positions(os_pos)
                for t in closed:
                    os_pos.pop(t, None)
                    trade_count += 1
                last_os_mon = now

            # 진입 스캔 (22:45 ~ 23:15)
            if is_os_scan_time() and len(os_pos) < OS_MAX_POSITIONS:
                if elapsed(last_os_scan) >= SCAN_INTERVAL_SEC:
                    try:
                        cands = scanner_overseas.scan_overseas_candidates(
                            exclude_tickers=list(os_pos.keys())
                        )
                    except Exception as e:
                        print(f"[MAIN] 해외 스캔 오류: {e}")
                        cands = []
                    for c in cands:
                        if len(os_pos) >= OS_MAX_POSITIONS:
                            break
                        res = trader_overseas.buy_overseas(
                            c["ticker"], c["name"], c["exchange"],
                            reason=f"[{c.get('regime','')}] {c['reason']}",
                        )
                        if res:
                            os_pos[c["ticker"]] = res
                            trade_count += 1
                    last_os_scan = now

            # EOD (05:45 ~ 05:55)
            if is_os_eod_check() and not os_eod_done and os_pos:
                print("[MAIN] 해외 EOD 체크")
                closed = monitor_overseas.check_overseas_eod(os_pos)
                for t in closed:
                    os_pos.pop(t, None)
                    trade_count += 1
                os_eod_done = True

        # ════ 현황 요약 (1시간 주기) ═══════════════════
        if elapsed(last_summary) >= SUMMARY_INTERVAL_SEC:
            if is_dom_market_hours() or is_os_market_hours():
                send_summary(dom_pos, os_pos, trade_count)
            last_summary = now

        # ════ 일일 결산 (15:35) ════════════════════════
        if t_hm == DOM_CLOSING_MSG and not sent_closing and is_trading_day(now):
            bal = get_balance_info()
            msg = f"📋 <b>오늘 결산</b>\n거래: {trade_count}회"
            if bal:
                em = "📈" if bal["eval_profit"] >= 0 else "📉"
                msg += (
                    f"\n총평가: {bal['total_eval']:,}원\n"
                    f"{em} 손익: {bal['eval_profit']:+,}원 ({bal['profit_rate']:+.2f}%)"
                )
            if dom_pos:
                msg += "\n\n🇰🇷 보유 유지:"
                for t, p in dom_pos.items():
                    msg += f"\n• {p['name']}({t})"
            telegram.send_force(msg)
            sent_closing = True
            trade_count = 0

        time.sleep(5)


if __name__ == "__main__":
    main()
