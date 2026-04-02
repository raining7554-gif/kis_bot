import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send(message: str):
    """텔레그램 메시지 전송"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM 미설정] {message}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM 오류] {e}")

def send_buy(ticker: str, name: str, price: int, qty: int, amount: int, reason: str):
    send(
        f"🟢 <b>매수 체결</b>\n"
        f"종목: {name} ({ticker})\n"
        f"가격: {price:,}원 × {qty}주\n"
        f"금액: {amount:,}원\n"
        f"사유: {reason}"
    )

def send_sell(ticker: str, name: str, price: int, qty: int, pnl: float, reason: str):
    emoji = "💰" if pnl >= 0 else "🔴"
    send(
        f"{emoji} <b>매도 체결</b>\n"
        f"종목: {name} ({ticker})\n"
        f"가격: {price:,}원 × {qty}주\n"
        f"수익률: {pnl:+.2f}%\n"
        f"사유: {reason}"
    )

def send_scan_result(candidates: list):
    if not candidates:
        send("📊 스캔 완료 - 조건 충족 종목 없음")
        return
    lines = ["📊 <b>스캔 결과</b>"]
    for c in candidates:
        lines.append(f"• {c['name']} ({c['ticker']}) +{c['change_rate']:.1f}% 거래량{c['vol_ratio']:.0f}배")
    send("\n".join(lines))

def send_error(msg: str):
    send(f"⚠️ <b>오류 발생</b>\n{msg}")

def send_daily_summary(total_pnl: float, trade_count: int):
    emoji = "✅" if total_pnl >= 0 else "❌"
    send(
        f"{emoji} <b>일일 결산</b>\n"
        f"총 수익률: {total_pnl:+.2f}%\n"
        f"거래 횟수: {trade_count}회"
    )
