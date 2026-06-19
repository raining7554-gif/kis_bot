"""어드바이저 분석 엔진 — 단타/스윙 진입가 추천 계산

자동매매가 아니라 '사람이 토스로 직접 주문'할 때 쓸 가이드를 만든다.
각 분석은 다음 구조의 dict 를 돌려준다:

  {
    "style": "단타" | "스윙",
    "ticker", "name", "price",
    "signal": "매수후보" | "관망" | "회피",
    "score": 0~100,
    "entry_low", "entry_high",   # 진입 희망 구간
    "stop",                       # 손절가
    "target",                     # 목표가(1차)
    "rr",                         # 손익비
    "comment",                    # 한줄 코멘트
  }

진입가는 '추격 금지, 눌림 매수' 원칙. 추천이지 보장이 아니다.
"""
from __future__ import annotations
import math


# ═══════════════════════════════════════════════════════
# 지표 헬퍼 (모든 시계열은 최신순: index 0 = 가장 최근)
# ═══════════════════════════════════════════════════════
def _ma(values: list, n: int) -> float:
    if len(values) < n or n <= 0:
        return 0.0
    return sum(values[:n]) / n


def _rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(period):
        diff = closes[i] - closes[i + 1]
        gains += max(diff, 0)
        losses += max(-diff, 0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)


def _atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(period):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i + 1]),
            abs(lows[i] - closes[i + 1]),
        )
        trs.append(tr)
    return sum(trs) / period


def _round_tick(price: float) -> int:
    """한국 주식 호가단위로 반올림 (2023 개편 기준 단순화)."""
    if price <= 0:
        return 0
    if price < 2000:
        tick = 1
    elif price < 5000:
        tick = 5
    elif price < 20000:
        tick = 10
    elif price < 50000:
        tick = 50
    elif price < 200000:
        tick = 100
    elif price < 500000:
        tick = 500
    else:
        tick = 1000
    return int(round(price / tick) * tick)


# ═══════════════════════════════════════════════════════
# 스윙 분석 (일봉 기반)
# ═══════════════════════════════════════════════════════
def analyze_swing(ticker: str, name: str, candles: list,
                  stop_pct: float = 0.05, rr: float = 2.0) -> dict | None:
    """일봉 MA/ATR 기반 스윙 진입가 추천.

    candles: strategy.get_daily_candles 결과 (최신순, 최소 60개 권장)
    """
    if len(candles) < 30:
        return None

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c["volume"] for c in candles]

    price = closes[0]
    if price <= 0:
        return None

    ma5 = _ma(closes, 5)
    ma20 = _ma(closes, 20)
    ma60 = _ma(closes, 60) if len(closes) >= 60 else _ma(closes, len(closes))
    rsi = _rsi(closes, 14)
    atr = _atr(highs, lows, closes, 14)
    hi20 = max(highs[:20])
    lo20 = min(lows[:20])
    avg_vol20 = sum(vols[1:21]) / 20 if len(vols) >= 21 else sum(vols) / len(vols)
    vol_ratio = (vols[0] / avg_vol20) if avg_vol20 > 0 else 0.0

    # ── 추세 점수 (0~100) ──────────────────────────────
    score = 0
    long_up = ma60 > 0 and ma20 > ma60          # 장기 상승 정배열
    short_up = ma5 > ma20                         # 단기 상승
    above_ma20 = price > ma20

    if long_up:
        score += 30
    if short_up:
        score += 20
    if above_ma20:
        score += 15
    if 45 <= rsi <= 68:                           # 과열 아닌 상승 구간
        score += 20
    elif rsi > 75:
        score -= 10
    if vol_ratio >= 1.3:
        score += 15
    score = max(0, min(100, score))

    # ── 진입 구간: 눌림목(MA20 지지 ~ MA5) ──────────────
    # 지지선 = MA20, 윗단 = MA5(또는 현재가가 지지 근처면 현재가)
    support = ma20 if ma20 > 0 else lo20
    upper = max(ma5, support * 1.005)
    entry_low = _round_tick(min(support, upper))
    entry_high = _round_tick(max(support, upper))

    # ── 손절: 지지선 하단(버퍼) 또는 20일 저점 중 가까운 쪽 ──
    stop_raw = min(support * (1 - stop_pct), lo20)
    # 손절이 너무 멀면 ATR 기준으로 제한 (진입가 - 2*ATR)
    if atr > 0:
        stop_raw = max(stop_raw, entry_low - 2 * atr)
    stop = _round_tick(stop_raw)

    # ── 목표: 진입가 + 위험폭 × RR (전고 hi20 참고) ──────
    entry_mid = (entry_low + entry_high) / 2
    risk = max(entry_mid - stop, 1)
    target = _round_tick(max(entry_mid + risk * rr, hi20))
    rr_val = (target - entry_mid) / risk if risk > 0 else 0

    # ── 신호 판정 + 코멘트 ─────────────────────────────
    if not long_up:
        signal = "회피"
        comment = f"장기 하락(MA20<MA60) — 추세전환 전 관망. RSI {rsi:.0f}"
    elif rsi > 78:
        signal = "관망"
        comment = f"과열(RSI {rsi:.0f}) — 눌림 후 MA5({_round_tick(ma5):,}) 부근 재진입 대기"
    elif price > entry_high * 1.05:
        signal = "관망"
        comment = (f"정배열 양호하나 지지선 위로 이격 — "
                   f"MA20({_round_tick(ma20):,})까지 눌림 시 분할매수")
    else:
        signal = "매수후보"
        loc = "지지선 부근" if price <= entry_high * 1.02 else "지지선 근접"
        comment = (f"정배열 {('+단기상승 ' if short_up else '')}/ {loc} / "
                   f"RSI {rsi:.0f} / 거래량 {vol_ratio:.1f}배")

    return {
        "style": "스윙",
        "ticker": ticker, "name": name, "price": int(price),
        "signal": signal, "score": int(score),
        "entry_low": entry_low, "entry_high": entry_high,
        "stop": stop, "target": target, "rr": round(rr_val, 1),
        "ma20": _round_tick(ma20), "rsi": round(rsi),
        "comment": comment,
    }


# ═══════════════════════════════════════════════════════
# 단타 분석 (당일 VWAP/지지·저항 기반)
# ═══════════════════════════════════════════════════════
def analyze_daytrade(quote: dict, minute_candles: list | None = None,
                     stop_pct: float = 0.02, rr: float = 2.0) -> dict | None:
    """당일 VWAP/고저 기반 단타 진입가 추천.

    quote: advisor_data.get_quote 결과
    minute_candles: advisor_data.get_minute_candles 결과(있으면 RSI/단기추세 반영)
    """
    if not quote or quote.get("price", 0) <= 0:
        return None

    price = quote["price"]
    vwap = quote.get("vwap", 0) or price
    day_high = quote.get("high", price)
    day_low = quote.get("low", price)
    open_px = quote.get("open", price)
    change = quote.get("change_rate", 0)

    # 분봉 RSI/단기 추세 (없으면 중립)
    m_rsi = 50.0
    m_trend_up = price >= open_px
    if minute_candles and len(minute_candles) >= 6:
        mcloses = [c["close"] for c in minute_candles]
        m_rsi = _rsi(mcloses, min(14, len(mcloses) - 1))
        m_trend_up = mcloses[0] >= mcloses[min(5, len(mcloses) - 1)]

    above_vwap = price >= vwap > 0
    pos_in_range = ((price - day_low) / (day_high - day_low)) if day_high > day_low else 0.5

    # ── 점수 ───────────────────────────────────────────
    score = 0
    if above_vwap:
        score += 30
    if m_trend_up:
        score += 15
    if change > 0:
        score += 10
    if 45 <= m_rsi <= 70:
        score += 20
    elif m_rsi > 78:
        score -= 15
    if pos_in_range <= 0.7:        # 고가권 추격 아님
        score += 15
    if quote.get("trade_amount", 0) >= 5_000_000_000:
        score += 10
    score = max(0, min(100, score))

    # ── 진입 구간: VWAP 지지 눌림 매수 ──────────────────
    if above_vwap:
        entry_low = _round_tick(vwap)
        entry_high = _round_tick(max(vwap * 1.005, min(price, vwap * 1.01)))
    else:
        # VWAP 아래 = 약세. VWAP 회복 시 진입 (돌파 매수 가이드)
        entry_low = _round_tick(vwap)
        entry_high = _round_tick(vwap * 1.005)

    # ── 손절: 진입가 하단 -stop_pct 와 당일 저가 중 가까운 쪽 ──
    stop = _round_tick(min(entry_low * (1 - stop_pct), day_low))

    # ── 목표: 위험폭×RR, 당일 고가 돌파 참고 ─────────────
    entry_mid = (entry_low + entry_high) / 2
    risk = max(entry_mid - stop, 1)
    target = _round_tick(max(entry_mid + risk * rr, day_high))
    rr_val = (target - entry_mid) / risk if risk > 0 else 0

    # ── 신호 + 코멘트 ──────────────────────────────────
    vwap_i = _round_tick(vwap)
    if not above_vwap:
        signal = "관망"
        comment = (f"VWAP({vwap_i:,}) 아래 약세 — 회복·돌파 확인 후 진입. "
                   f"분봉RSI {m_rsi:.0f}")
    elif m_rsi > 80 or pos_in_range > 0.92:
        signal = "관망"
        comment = (f"고가권 과열(분봉RSI {m_rsi:.0f}) — "
                   f"VWAP({vwap_i:,}) 눌림 대기")
    else:
        signal = "매수후보"
        comment = (f"VWAP 위 강세 / 당일 {change:+.1f}% / "
                   f"분봉RSI {m_rsi:.0f} / 고저위치 {pos_in_range*100:.0f}%")

    return {
        "style": "단타",
        "ticker": quote["ticker"], "name": quote["name"], "price": int(price),
        "signal": signal, "score": int(score),
        "entry_low": entry_low, "entry_high": entry_high,
        "stop": stop, "target": target, "rr": round(rr_val, 1),
        "vwap": vwap_i, "rsi": round(m_rsi), "change": round(change, 1),
        "comment": comment,
    }
