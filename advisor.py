"""토스 직접매매용 어드바이저 봇 v1.0

자동매매를 하지 않는다. 토스증권으로 직접 매매하는 단타/스윙 종목에 대해
진입가·손절가·목표가를 계산해 '정해진 시각'에 텔레그램 요약 리포트로 보낸다.

종목 풀:
  - 관심종목: ADVISOR_WATCHLIST (직접 등록)
  - 자동발굴: 단타=거래대금 상위, 스윙=Clenow 모멘텀 상위

기존 자동매매봇(main.py)과 독립 실행:  python advisor.py
KIS 인증/텔레그램/일봉조회는 기존 모듈 재사용.
"""
import time
from datetime import datetime
import pytz

import kis_auth as api
import telegram
import advisor_data as data
import advisor_analysis as analysis
from market_calendar import is_trading_day
from strategy import get_daily_candles
from advisor_config import (
    ADVISOR_WATCHLIST, ADVISOR_REPORT_TIMES,
    ADVISOR_AUTO_DISCOVER, ADVISOR_DAYTRADE_TOPN, ADVISOR_SWING_TOPN,
    ADVISOR_MIN_TRADE_AMOUNT, ADVISOR_MIN_PRICE, ADVISOR_MAX_PRICE,
    DT_STOP_PCT, DT_RR, DT_MIN_SCORE,
    SW_STOP_PCT, SW_RR, SW_MIN_SCORE,
    ADVISOR_LOOP_SEC, ADVISOR_API_DELAY,
)

KST = pytz.timezone("Asia/Seoul")


def now_kst():
    return datetime.now(KST)


def hhmm():
    return now_kst().strftime("%H:%M")


def is_market_hours() -> bool:
    """국내 정규장(09:00~15:30, 영업일)."""
    if not is_trading_day(now_kst()):
        return False
    return "09:00" <= hhmm() <= "15:30"


# ═══════════════════════════════════════════════════════
# 종목 풀 구성
# ═══════════════════════════════════════════════════════
def discover_daytrade_tickers(exclude: set) -> list[tuple]:
    """단타 자동발굴 — 거래대금 상위 종목."""
    if not ADVISOR_AUTO_DISCOVER:
        return []
    ranked = data.get_volume_rank(
        topn=ADVISOR_DAYTRADE_TOPN * 3,
        min_price=ADVISOR_MIN_PRICE, max_price=ADVISOR_MAX_PRICE,
    )
    out = []
    for r in ranked:
        t = r["ticker"]
        if not t or t in exclude:
            continue
        if r["trade_amount"] < ADVISOR_MIN_TRADE_AMOUNT:
            continue
        out.append((t, r["name"]))
        if len(out) >= ADVISOR_DAYTRADE_TOPN:
            break
    return out


def discover_swing_tickers(exclude: set) -> list[tuple]:
    """스윙 자동발굴 — Clenow 모멘텀 상위(추세 강한 종목)."""
    if not ADVISOR_AUTO_DISCOVER:
        return []
    try:
        import strategy_clenow_kr as clenow
        cands = clenow.scan_clenow_candidates(
            excluded_tickers=list(exclude),
            max_positions=ADVISOR_SWING_TOPN,
            max_price=ADVISOR_MAX_PRICE,
        )
        return [(c["ticker"], c["name"]) for c in cands]
    except Exception as e:
        print(f"[ADVISOR] 스윙 발굴 오류: {e}")
        return []


def resolve_watchlist() -> list[tuple]:
    """관심종목 티커 → (ticker, name) 보강."""
    out = []
    for t in ADVISOR_WATCHLIST:
        q = data.get_quote(t)
        name = q.get("name", t) if q else t
        out.append((t, name))
        time.sleep(ADVISOR_API_DELAY)
    return out


# ═══════════════════════════════════════════════════════
# 분석 실행
# ═══════════════════════════════════════════════════════
def run_swing(tickers: list[tuple]) -> list[dict]:
    results = []
    for ticker, name in tickers:
        candles = get_daily_candles(ticker, "J", count=70)
        rec = analysis.analyze_swing(ticker, name, candles,
                                     stop_pct=SW_STOP_PCT, rr=SW_RR)
        if rec:
            results.append(rec)
        time.sleep(ADVISOR_API_DELAY)
    results.sort(key=lambda r: -r["score"])
    return results


def run_daytrade(tickers: list[tuple]) -> list[dict]:
    results = []
    base = now_kst().strftime("%H%M%S") if is_market_hours() else "153000"
    for ticker, name in tickers:
        quote = data.get_quote(ticker)
        if not quote:
            continue
        if not name and quote.get("name"):
            name = quote["name"]
        quote["name"] = name or quote.get("name", ticker)
        minutes = data.get_minute_candles(ticker, base_time=base)
        rec = analysis.analyze_daytrade(quote, minutes,
                                        stop_pct=DT_STOP_PCT, rr=DT_RR)
        if rec:
            results.append(rec)
        time.sleep(ADVISOR_API_DELAY)
    results.sort(key=lambda r: -r["score"])
    return results


# ═══════════════════════════════════════════════════════
# 리포트 포매팅
# ═══════════════════════════════════════════════════════
_SIGNAL_EMOJI = {"매수후보": "🟢", "관망": "🟡", "회피": "🔴"}


def _fmt_rec(r: dict, min_score: int) -> str:
    em = _SIGNAL_EMOJI.get(r["signal"], "⚪")
    # 관망/회피여도 정보는 주되, 매수후보는 진입가 강조
    head = f"{em} <b>{r['name']}</b>({r['ticker']}) · {r['signal']} ({r['score']}점)"
    body = (
        f"\n  현재가 {r['price']:,}\n"
        f"  진입 {r['entry_low']:,}~{r['entry_high']:,} · "
        f"손절 {r['stop']:,} · 목표 {r['target']:,} (R/R {r['rr']})\n"
        f"  ↳ {r['comment']}"
    )
    return head + body


def build_report(swing: list[dict], day: list[dict], market_open: bool) -> str:
    ts = now_kst().strftime("%m/%d %H:%M")
    lines = [f"📒 <b>매매 어드바이저 리포트</b> ({ts} KST)"]

    # ── 단타 섹션 ──────────────────────────────────────
    lines.append("\n⚡ <b>단타</b> (당일 VWAP/지지·저항)")
    if not market_open:
        lines.append("  · 장 시작 전/마감 — 단타 신호는 장중 기준")
    if day:
        buy = [r for r in day if r["signal"] == "매수후보"]
        watch = [r for r in day if r["signal"] != "매수후보"]
        shown = buy + watch
        for r in shown[:8]:
            lines.append(_fmt_rec(r, DT_MIN_SCORE))
    else:
        lines.append("  · 분석 가능한 종목 없음")

    # ── 스윙 섹션 ──────────────────────────────────────
    lines.append("\n📈 <b>스윙</b> (일봉 MA/눌림목)")
    if swing:
        buy = [r for r in swing if r["signal"] == "매수후보"]
        watch = [r for r in swing if r["signal"] != "매수후보"]
        shown = buy + watch
        for r in shown[:8]:
            lines.append(_fmt_rec(r, SW_MIN_SCORE))
    else:
        lines.append("  · 분석 가능한 종목 없음 (KOSPI 약세 시 스윙 보류)")

    lines.append("\n※ 추천이며 보장 아님. 진입가·손절 지키고 분할매수 권장.")
    return "\n".join(lines)


def generate_and_send():
    """종목 풀 구성 → 분석 → 리포트 전송 (1회)."""
    print(f"[ADVISOR] 리포트 생성 시작 {hhmm()}")
    market_open = is_market_hours()

    watch = resolve_watchlist()
    watch_set = {t for t, _ in watch}

    # ── 단타 풀: 관심종목 + 거래대금 상위 ───────────────
    dt_pool = list(watch)
    dt_pool += discover_daytrade_tickers(exclude=watch_set)

    # ── 스윙 풀: 관심종목 + 모멘텀 상위 ─────────────────
    sw_pool = list(watch)
    sw_pool += discover_swing_tickers(exclude=watch_set)

    day = run_daytrade(dt_pool) if dt_pool else []
    swing = run_swing(sw_pool) if sw_pool else []

    report = build_report(swing, day, market_open)
    telegram.send_force(report)
    print(f"[ADVISOR] 리포트 전송 완료 (단타 {len(day)} / 스윙 {len(swing)})")


# ═══════════════════════════════════════════════════════
# 메인 루프
# ═══════════════════════════════════════════════════════
def main():
    print("=" * 55)
    print("📒 토스 매매 어드바이저 봇 v1.0")
    print(f"관심종목: {ADVISOR_WATCHLIST or '(미등록)'}")
    print(f"리포트 시각: {ADVISOR_REPORT_TIMES}")
    print(f"자동발굴: {ADVISOR_AUTO_DISCOVER} "
          f"(단타 {ADVISOR_DAYTRADE_TOPN} / 스윙 {ADVISOR_SWING_TOPN})")
    print("=" * 55)

    try:
        api.get_access_token()
    except Exception as e:
        print(f"[AUTH] 초기 토큰 실패: {e}")
    time.sleep(2)

    telegram.send_force(
        "📒 <b>매매 어드바이저 봇 시작</b>\n"
        f"관심종목 {len(ADVISOR_WATCHLIST)}개 + 자동발굴"
        f"({'ON' if ADVISOR_AUTO_DISCOVER else 'OFF'})\n"
        f"리포트: {', '.join(ADVISOR_REPORT_TIMES)} KST\n"
        f"현재 {hhmm()} KST"
    )

    sent_today: set[str] = set()
    last_day = now_kst().date()

    # 수동 트리거: 시작 직후 1회 즉시 리포트 (영업일이면)
    if is_trading_day(now_kst()):
        try:
            generate_and_send()
        except Exception as e:
            print(f"[ADVISOR] 초기 리포트 오류: {e}")
            telegram.send_error(f"어드바이저 초기 리포트 오류: {e}")

    while True:
        now = now_kst()
        # 자정 지나면 발송 플래그 리셋
        if now.date() != last_day:
            sent_today.clear()
            last_day = now.date()

        t = now.strftime("%H:%M")
        if t in ADVISOR_REPORT_TIMES and t not in sent_today and is_trading_day(now):
            sent_today.add(t)
            try:
                generate_and_send()
            except Exception as e:
                print(f"[ADVISOR] 리포트 오류: {e}")
                telegram.send_error(f"어드바이저 리포트 오류: {e}")

        time.sleep(ADVISOR_LOOP_SEC)


if __name__ == "__main__":
    main()
