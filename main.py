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
from config import (
    SCAN_START_TIME, SCAN_END_TIME, FORCE_CLOSE_TIME,
    MAX_POSITIONS, SCAN_INTERVAL_SEC, MONITOR_INTERVAL_SEC
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
    return t >= "23:30" or t <= "06:00"

def is_domestic_scan_time() -> bool:
    t = now_str()
    return SCAN_START_TIME <= t <= SCAN_END_TIME

def is_overseas_scan_time() -> bool:
    t = now_str()
    return "23:30" <= t <= "23:59" or "00:00" <= t <= "01:00"

def is_domestic_force_close() -> bool:
    return now_str() >= FORCE_CLOSE_TIME

def is_overseas_force_close() -> bool:
    t = now_str()
    return "05:30" <= t <= "06:00"

def main():
    print("=" * 55)
    print("🚀 KIS 국내 + 해외 자동매매 봇 시작")
    print(f"국내: {SCAN_START_TIME}~{SCAN_END_TIME} | 강제청산 {FORCE_CLOSE_TIME}")
    print(f"해외: 23:30~01:00 스캔 | 강제청산 05:30")
    print(f"현재 KST: {now_str()}")
    print("=" * 55)
    telegram.send(
        "🚀 <b>KIS 자동매매 봇 시작</b>\n"
        "국내: 09:05~10:00 스캔\n"
        "해외: 23:30~01:00 스캔\n"
        f"현재시각: {now_str()} KST"
    )

    domestic_positions = {}
    overseas_positions = {}

    last_dom_scan    = None
    last_os_scan     = None
    last_dom_monitor = None
    last_os_monitor  = None

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
                    telegram.send_scan_result(candidates[:5])

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
            if now_hm == "23:30":
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
                    if candidates:
                        lines = ["📊 <b>해외 스캔 결과</b>"]
                        for c in candidates[:5]:
                            lines.append(f"• {c['name']} ({c['ticker']}) +{c['change_rate']:.1f}%")
                        telegram.send("\n".join(lines))

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

        if now_hm == "15:31" and trade_count > 0:
            telegram.send(f"📋 <b>오늘 국내 거래 횟수: {trade_count}회</b>")

        time.sleep(5)

if __name__ == "__main__":
    main()
