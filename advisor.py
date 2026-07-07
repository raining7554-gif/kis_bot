"""토스 직접매매용 어드바이저 봇 v1.0

자동매매를 하지 않는다. 토스증권으로 직접 매매하는 단타/스윙 종목에 대해
진입가·손절가·목표가를 계산해 '정해진 시각'에 텔레그램 요약 리포트로 보낸다.

종목 풀:
  - 관심종목: ADVISOR_WATCHLIST (직접 등록)
  - 자동발굴: 단타=거래대금 상위, 스윙=Clenow 모멘텀 상위

기존 자동매매봇(main.py)과 독립 실행:  python advisor.py
KIS 인증/텔레그램/일봉조회는 기존 모듈 재사용.
"""
import re
import time
from datetime import datetime
import pytz

import kis_auth as api
import telegram
import advisor_data as data
import advisor_analysis as analysis
import stock_lookup
from market_calendar import is_trading_day
from strategy import get_daily_candles
from config import TELEGRAM_CHAT_ID
from advisor_config import (
    ADVISOR_WATCHLIST, ADVISOR_REPORT_TIMES,
    ADVISOR_AUTO_DISCOVER, ADVISOR_DAYTRADE_TOPN, ADVISOR_SWING_TOPN,
    ADVISOR_MIN_TRADE_AMOUNT, ADVISOR_MIN_PRICE, ADVISOR_MAX_PRICE,
    DT_STOP_PCT, DT_RR, DT_MIN_SCORE,
    SW_STOP_PCT, SW_RR, SW_MIN_SCORE,
    ADVISOR_LOOP_SEC, ADVISOR_API_DELAY,
    ADVISOR_POLL_SEC, ADVISOR_INTERACTIVE, ADVISOR_MOMENTUM_TOPN,
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
        rec = analysis.analyze_swing(ticker, name, candles, stop_pct=SW_STOP_PCT,
                                     rr=SW_RR, min_buy_score=SW_MIN_SCORE)
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
# 표시용 라벨 — 점수는 수익 '예측'이 아니라 '추세·진입조건 충족도'라서
# '매수후보' 같은 단정적 표현 대신 추세 상태로 표기한다.
_SIGNAL_LABEL = {"매수후보": "추세양호", "관망": "관망", "회피": "추세약함"}


def _label(signal: str) -> str:
    return _SIGNAL_LABEL.get(signal, signal)


# 점수는 '수익 예측'이 아니라 '추세·진입조건 충족도'다. (광범위 백테스트에서
# 점수 자체의 초과수익 예측력은 확인되지 않음 → 종목 선택은 본인, 봇은 규율 도구)
_DISCLAIMER = (
    "\n※ 점수=추세·진입조건 충족도(수익 예측 아님). 종목 선택은 본인 판단,\n"
    "  봇은 진입가·손절·추세상태 정리용. 손절 지키고 분할매수 권장."
)


def _px(v, market: str = "KR") -> str:
    """시장별 가격 표기 — 국내 '12,300', 미국 '$182.45'."""
    if market == "US":
        return f"${v:,.2f}"
    return f"{int(round(v)):,}"


def _levels(r: dict) -> str:
    """진입/손절/청산 라인 — 스윙은 추세추종(MA20 이탈) 청산, 단타는 고정 목표."""
    m = r.get("market", "KR")
    if r.get("style") == "스윙":
        s = (f"  진입 {_px(r['entry_low'], m)}~{_px(r['entry_high'], m)} · "
             f"손절 {_px(r['stop'], m)}\n"
             f"  청산: 일봉 종가가 MA20({_px(r['exit_ma'], m)}) 이탈 시")
        if r.get("ref_target"):
            s += f" · 추세목표(참고) {_px(r['ref_target'], m)}"
        return s
    return (f"  진입 {_px(r['entry_low'], m)}~{_px(r['entry_high'], m)} · "
            f"손절 {_px(r['stop'], m)} · 목표 {_px(r['target'], m)} (R/R {r['rr']})")


def _fmt_rec(r: dict, min_score: int) -> str:
    em = _SIGNAL_EMOJI.get(r["signal"], "⚪")
    m = r.get("market", "KR")
    head = f"{em} <b>{r['name']}</b>({r['ticker']}) · {_label(r['signal'])} ({r['score']}점)"
    body = f"\n  현재가 {_px(r['price'], m)}\n{_levels(r)}\n  ↳ {r['comment']}"
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

    lines.append(_DISCLAIMER)
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
# 대화형 질의응답 (텔레그램으로 종목명 물어보면 답함)
# ═══════════════════════════════════════════════════════
HELP_TEXT = (
    "📒 <b>매매 어드바이저 — 사용법</b>\n"
    "종목명·코드·미국티커를 보내면 진입가를 분석해 드려요.\n\n"
    "🇰🇷 국내: <code>삼성전자</code> · <code>에코프로</code> · <code>000660</code>\n"
    "🇺🇸 미국: <code>엔비디아</code> · <code>NVDA</code> · <code>TSLA</code>\n"
    "단타만: <code>삼성전자 단타</code> / 스윙만: <code>NVDA 스윙</code>\n"
    "⭐ <code>모멘텀</code> — 백테스트로 검증된 모멘텀 상위 랭킹(월 1회 교체)\n"
    "정시 리포트: <code>리포트</code> · 도움말: <code>도움말</code>"
)


def _momentum_report(topn: int = ADVISOR_MOMENTUM_TOPN) -> str:
    """크로스섹셔널 모멘텀 상위 랭킹 — 백테스트로 검증된 전략.

    strategy_clenow_kr(120일 Clenow 모멘텀, KOSPI>MA200 게이트) 재사용.
    """
    try:
        import strategy_clenow_kr as clenow
    except Exception as e:
        return f"⚠️ 모멘텀 모듈 로드 오류: {e}"

    regime = clenow.check_kospi_regime()
    if regime.get("regime") != "BULL":
        return (
            "📊 <b>모멘텀 랭킹 (KR)</b>\n"
            f"KOSPI 체제: <b>{regime.get('regime','?')}</b> (200일선 하회)\n\n"
            "⚠️ 모멘텀은 약세장에서 급격히 깨집니다(momentum crash).\n"
            "→ 신규 진입 보류 / 현금 비중 확대 권장. KOSPI가 MA200 회복하면 재개."
        )

    cands = clenow.scan_clenow_candidates(max_positions=topn, top_pct=0.20)
    if not cands:
        return "📊 모멘텀 랭킹 — 조건 충족 종목 없음 (데이터/체제 확인 필요)"

    lines = [
        f"📊 <b>모멘텀 랭킹 (KR · {now_kst().strftime('%m/%d')})</b>",
        f"KOSPI 체제: BULL · 상위 {len(cands)}종목",
        "",
    ]
    for i, c in enumerate(cands, 1):
        lines.append(f"{i:>2}. <b>{c['name']}</b>({c['ticker']}) "
                     f"{int(c['close']):,} · 점수 {c['score']:.0f}")
    lines.append(
        "\n💡 <b>운용법</b>: 상위 10~15종목 균등 보유, <b>월 1회 재랭킹</b>해서 "
        "상위권 유지·하위 이탈/MA50 깨진 종목만 교체. 보유 수주~수개월."
    )
    lines.append(
        "\n※ 백테스트: 동일가중 전체 대비 꾸준한 초과수익(8개 설정 전부). "
        "단 생존편향·우호장 영향으로 절대수익은 과신 금물, 약세장 손실 큼."
    )
    return "\n".join(lines)


# KIS 종목상태(iscd_stat_cls_code) 중 '주의가 필요한' 코드만 경고.
# 55(신용가능)·57(증거금100%)·00(그외) 등은 정상이므로 경고 안 함.
_STAT_WARN = {
    "51": "관리종목", "52": "투자위험", "53": "투자경고",
    "54": "투자주의", "58": "거래정지", "59": "단기과열",
}


def _single_report(code: str, name: str, styles: set) -> str:
    """단일 종목 분석 결과를 텔레그램 메시지로."""
    quote = data.get_quote(code)
    if not quote or quote.get("price", 0) <= 0:
        return f"⚠️ {name or code} 시세를 가져오지 못했어요. 코드가 맞는지 확인해 주세요."
    # 찾아둔 한글명을 우선 사용 (KIS 응답명이 비면 코드로 떨어지므로)
    q_name = quote.get("name", "")
    if q_name == code:  # get_quote가 이름을 못 받아 코드로 폴백한 경우
        q_name = ""
    name = name or q_name or code
    warn = _STAT_WARN.get(str(quote.get("stat", "00")))
    if warn:
        head = f"⚠️ <b>{name}</b>({code}) — {warn} 상태예요. 주의하세요.\n"
    else:
        head = ""

    lines = [f"📊 <b>{name}</b>({code}) · 현재가 {_px(quote['price'], 'KR')} "
             f"({quote.get('change_rate',0):+.1f}%)"]

    if "단타" in styles:
        base = now_kst().strftime("%H%M%S") if is_market_hours() else "153000"
        minutes = data.get_minute_candles(code, base_time=base)
        dt = analysis.analyze_daytrade(quote, minutes, stop_pct=DT_STOP_PCT, rr=DT_RR)
        if dt:
            lines.append(_style_block(dt))
            if not is_market_hours():
                lines.append("  · (장중 기준 신호 — 지금은 참고용)")

    if "스윙" in styles:
        candles = get_daily_candles(code, "J", count=70)
        sw = analysis.analyze_swing(code, name, candles, stop_pct=SW_STOP_PCT,
                                    rr=SW_RR, min_buy_score=SW_MIN_SCORE)
        if sw:
            lines.append(_style_block(sw))
        else:
            lines.append("\n📈 <b>스윙</b> — 일봉 데이터 부족으로 분석 불가")

    lines.append(_DISCLAIMER)
    return head + "\n".join(lines)


def _style_block(rec: dict) -> str:
    """단타/스윙 한 종목 분석 블록 (국내·미국 공용)."""
    em = _SIGNAL_EMOJI.get(rec["signal"], "⚪")
    icon = "⚡ <b>단타</b>" if rec["style"] == "단타" else "📈 <b>스윙</b>"
    return (
        f"\n{icon} {em} {_label(rec['signal'])} ({rec['score']}점)\n"
        f"{_levels(rec)}\n  ↳ {rec['comment']}"
    )


def _single_report_us(ticker: str, styles: set) -> str:
    """미국주식 단일 종목 분석 (달러)."""
    print(f"[ADVISOR] US 분석 시작: {ticker} 시세 조회…")
    quote = data.get_us_quote(ticker)
    print(f"[ADVISOR] US {ticker} 시세: "
          f"{('있음 '+quote.get('exchange','?')) if quote else '없음'}")
    if not quote or quote.get("price", 0) <= 0:
        return (f"⚠️ {ticker} 미국주식 시세를 못 가져왔어요.\n"
                "티커 철자를 확인하거나(예: NVDA, TSLA), 잠시 후 다시 시도해 주세요.\n"
                "※ 미국장 시세는 KIS 해외 권한/시간대에 따라 지연될 수 있어요.")
    exchange = quote.get("exchange", "NAS")
    price = quote["price"]
    change = quote.get("change_rate", 0)
    name = stock_lookup.us_name_of(ticker)
    title = f"{name}({ticker})" if name else ticker

    lines = [f"📊 <b>🇺🇸 {title}</b> · {exchange} · 현재가 ${price:,.2f} ({change:+.1f}%)"]

    candles = data.get_us_daily(ticker, exchange, count=210)

    if "단타" in styles:
        dt = analysis.analyze_daytrade_us(ticker, name, price, change, candles, rr=DT_RR)
        if dt:
            lines.append(_style_block(dt))
            lines.append("  · 미장 단타는 전일 피벗 기준 (장중 갱신 참고)")
        else:
            lines.append("\n⚡ <b>단타</b> — 일봉 데이터 부족으로 분석 불가")

    if "스윙" in styles:
        sw = analysis.analyze_swing(ticker, name, candles, stop_pct=SW_STOP_PCT,
                                    rr=SW_RR, market="US", min_buy_score=SW_MIN_SCORE)
        if sw:
            lines.append(_style_block(sw))
        else:
            lines.append("\n📈 <b>스윙</b> — 일봉 데이터 부족으로 분석 불가")

    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def handle_query(text: str) -> str:
    """사용자 메시지 → 응답 텍스트."""
    t = text.strip()
    low = t.lower()

    if low in ("/start", "도움말", "help", "/help", "사용법", "?"):
        return HELP_TEXT
    if low in ("리포트", "report", "/report"):
        # 즉석 전체 리포트 요청
        return None  # 신호: 호출부에서 generate_and_send() 실행
    if low in ("모멘텀", "momentum", "랭킹", "모멘텀랭킹", "/모멘텀"):
        telegram.send_force("⏳ 모멘텀 랭킹 스캔 중… (350종목, 1~2분 소요)")
        return _momentum_report()

    # 스타일 키워드 파싱
    styles = set()
    for kw, st in (("단타", "단타"), ("day", "단타"), ("스윙", "스윙"), ("swing", "스윙")):
        if kw in low:
            styles.add(st)
            t = re.sub(kw, "", t, flags=re.IGNORECASE)
    if not styles:
        styles = {"단타", "스윙"}

    query = t.strip()
    if not query:
        return HELP_TEXT

    # 미국주식 우선 판별 (영문 티커 / 인기 한글명)
    us = stock_lookup.resolve_us(query)
    if us:
        return _single_report_us(us, styles)

    cands = stock_lookup.resolve(query)
    if not cands:
        return (f"🔍 '{query}' 를 못 찾았어요.\n"
                "6자리 종목코드로 보내주시면 바로 분석할게요. (예: 005930)")
    if len(cands) > 1:
        # 코드 직접입력이 아닌 부분일치 다수 → 후보 제시
        listing = "\n".join(f"• {n}  <code>{c}</code>" for c, n in cands[:8])
        more = "\n…(더 있음)" if len(cands) > 8 else ""
        return (f"🔍 '{query}' 검색 결과 여러 개예요. 코드로 다시 보내주세요:\n"
                f"{listing}{more}")

    code, name = cands[0]
    return _single_report(code, name, styles)


def poll_telegram(offset: int | None) -> int | None:
    """수신 메시지 처리. 새 offset 반환."""
    updates = telegram.get_updates(offset=offset, timeout=25)  # 롱폴링(최대 25s 대기)
    if updates:
        print(f"[ADVISOR] 업데이트 {len(updates)}건 수신")
    for u in updates:
        offset = u["update_id"] + 1
        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "")
        print(f"[ADVISOR] 메시지: chat={chat_id} text={text!r}")
        # 본인(설정된 chat) 메시지만 응답
        if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
            print(f"[ADVISOR] chat_id 불일치 → 무시 (설정값={TELEGRAM_CHAT_ID!r})")
            continue
        if not text:
            continue
        try:
            reply = handle_query(text)
            if reply is None:
                generate_and_send()  # '리포트' 요청
            else:
                telegram.send_force(reply)
        except Exception as e:
            print(f"[ADVISOR] 질의 처리 오류: {e}")
            telegram.send_force(f"⚠️ 처리 중 오류: {e}")
    return offset


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
    print(f"대화형: {ADVISOR_INTERACTIVE} | 폴링주기 {ADVISOR_POLL_SEC}s | "
          f"CHAT_ID={TELEGRAM_CHAT_ID!r}")
    if not TELEGRAM_CHAT_ID:
        print("[ADVISOR] ⚠️ TELEGRAM_CHAT_ID 미설정 — 아무 메시지에나 응답합니다")
    print("=" * 55)

    try:
        api.get_access_token()
    except Exception as e:
        print(f"[AUTH] 초기 토큰 실패: {e}")
    time.sleep(2)

    mode = "대화형+정시리포트" if ADVISOR_INTERACTIVE else "정시리포트"
    telegram.send_force(
        "📒 <b>매매 어드바이저 봇 시작</b>\n"
        f"모드: {mode}\n"
        f"관심종목 {len(ADVISOR_WATCHLIST)}개 + 자동발굴"
        f"({'ON' if ADVISOR_AUTO_DISCOVER else 'OFF'})\n"
        f"리포트: {', '.join(ADVISOR_REPORT_TIMES)} KST\n\n"
        + (HELP_TEXT if ADVISOR_INTERACTIVE else f"현재 {hhmm()} KST")
    )

    sent_today: set[str] = set()
    last_day = now_kst().date()
    offset = None

    # 시작 시 기존 밀린 메시지는 무시 (offset 을 최신으로 당겨놓음)
    if ADVISOR_INTERACTIVE:
        try:
            backlog = telegram.get_updates(timeout=0)
            if backlog:
                offset = backlog[-1]["update_id"] + 1
        except Exception:
            pass

    while True:
        now = now_kst()
        # 자정 지나면 발송 플래그 리셋
        if now.date() != last_day:
            sent_today.clear()
            last_day = now.date()

        # ── 대화형 질의 처리 ───────────────────────────
        if ADVISOR_INTERACTIVE:
            try:
                offset = poll_telegram(offset)
            except Exception as e:
                print(f"[ADVISOR] 폴링 오류: {e}")

        # ── 정시 리포트 ────────────────────────────────
        t = now.strftime("%H:%M")
        if t in ADVISOR_REPORT_TIMES and t not in sent_today and is_trading_day(now):
            sent_today.add(t)
            try:
                generate_and_send()
            except Exception as e:
                print(f"[ADVISOR] 리포트 오류: {e}")
                telegram.send_error(f"어드바이저 리포트 오류: {e}")

        time.sleep(ADVISOR_POLL_SEC if ADVISOR_INTERACTIVE else ADVISOR_LOOP_SEC)


if __name__ == "__main__":
    main()
