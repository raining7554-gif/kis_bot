"""어드바이저 스윙 점수 백테스트 (FinanceDataReader 기반)

어드바이저의 '스윙 매수후보' 신호와 점수가 실제로 의미가 있는지 과거
일봉으로 검증한다. 미래참조(lookahead) 없음:
  - 신호는 당일 종가까지의 데이터로만 생성
  - 진입(지정가 체결)·청산은 '다음 날 이후' 가격으로만 시뮬레이션

측정:
  - 점수 구간별 신호 수 / 체결률 / 승률(목표 선도달) / 평균수익 / 목표·손절·타임아웃 비율
  - N일 포워드 수익(신호 당일 종가 기준) — 체결 여부와 무관한 '신호 품질'
  - 베이스라인(전체 무작위 진입 평균 포워드 수익)과 비교

설치:  pip install -r requirements-backtest.txt
실행 예:
  python backtest_advisor.py --market kr --start 2019-01-01 --max-tickers 60
  python backtest_advisor.py --market us --start 2019-01-01 \
         --tickers NVDA,TSLA,AAPL,MSFT,AMD,META,AMZN,GOOGL
"""
from __future__ import annotations
import argparse

from advisor_analysis import analyze_swing
from advisor_config import SW_STOP_PCT, SW_RR


# ═══════════════════════════════════════════════════════
# 핵심 시뮬레이션 (FDR/pandas 없이도 동작 — 테스트 용이)
# ═══════════════════════════════════════════════════════
def _simulate_trade(ohlcv: list, f: int, entry: float, stop: float,
                    target: float, max_hold: int) -> tuple:
    """체결일 f부터 손절/목표/만기까지 추적. (수익률, 결과) 반환.
    같은 날 손절·목표 동시 충족 시 손절 우선(보수적)."""
    n = len(ohlcv)
    end = min(f + max_hold, n - 1)
    for j in range(f, end + 1):
        if ohlcv[j]["low"] <= stop:
            return (stop - entry) / entry, "stop"
        if ohlcv[j]["high"] >= target:
            return (target - entry) / entry, "target"
    c = ohlcv[end]["close"]
    return (c - entry) / entry, "timeout"


def backtest_series(ohlcv: list, market: str = "KR",
                    stop_pct: float = SW_STOP_PCT, rr: float = SW_RR,
                    max_hold: int = 10, fill_window: int = 5,
                    horizon: int = 10, cooldown: int = 5,
                    min_rows: int = 70) -> list:
    """단일 종목 일봉(oldest-first OHLCV dict 리스트)에 대한 신호 시뮬레이션.

    ohlcv: [{open,high,low,close,volume}, ...] 과거→현재 순
    리턴: 신호 레코드 리스트 [{score, filled, outcome, ret, fwd}, ...]
    """
    n = len(ohlcv)
    records = []
    last_sig = -10 ** 9
    for i in range(min_rows, n - 1):
        if i - last_sig < cooldown:
            continue
        # 당일(i)까지의 데이터로만 신호 생성 (최신순 변환, 최근 250봉)
        lo = max(0, i - 249)
        candles = [
            {"close": r["close"], "high": r["high"], "low": r["low"], "volume": r["volume"]}
            for r in reversed(ohlcv[lo:i + 1])
        ]
        rec = analyze_swing("BT", "BT", candles, stop_pct=stop_pct, rr=rr, market=market)
        if not rec or rec["signal"] != "매수후보":
            continue
        last_sig = i

        # 신호 당일 종가 기준 N일 포워드 수익 (체결과 무관)
        fwd = None
        if i + horizon < n:
            c0 = ohlcv[i]["close"]
            fwd = (ohlcv[i + horizon]["close"] - c0) / c0 if c0 else None

        # 지정가 체결 시뮬: 다음날부터 fill_window 일 내 저가가 진입가 터치 시 체결
        entry = rec["entry_high"]
        stop = rec["stop"]
        target = rec["target"]
        filled, fidx = False, None
        for j in range(i + 1, min(i + 1 + fill_window, n)):
            if ohlcv[j]["low"] <= entry:
                filled, fidx = True, j
                break

        outcome, ret = None, None
        if filled:
            ret, outcome = _simulate_trade(ohlcv, fidx, entry, stop, target, max_hold)

        records.append({"score": rec["score"], "filled": filled,
                        "outcome": outcome, "ret": ret, "fwd": fwd})
    return records


def baseline_forward(ohlcv: list, horizon: int = 10,
                     min_rows: int = 70, step: int = 5) -> list:
    """무작위(매일) 진입 시 N일 포워드 수익 — 비교 기준."""
    out = []
    n = len(ohlcv)
    for i in range(min_rows, n - horizon, step):
        c0 = ohlcv[i]["close"]
        if c0:
            out.append((ohlcv[i + horizon]["close"] - c0) / c0)
    return out


# ═══════════════════════════════════════════════════════
# 집계 / 출력
# ═══════════════════════════════════════════════════════
_BUCKETS = [(0, 59, "0~59"), (60, 69, "60~69"), (70, 79, "70~79"), (80, 100, "80~100")]


def _pct(x):
    return f"{x*100:+.2f}%" if x is not None else "  -  "


def summarize(records: list, baseline: list):
    print("\n" + "=" * 78)
    print("스윙 점수 백테스트 결과")
    print("=" * 78)
    if not records:
        print("신호 없음 — 기간/유니버스를 넓혀 보세요.")
        return

    base_avg = (sum(baseline) / len(baseline)) if baseline else None
    print(f"총 신호: {len(records)}건 | 베이스라인(무작위 {len(baseline)}표본) "
          f"평균 포워드수익: {_pct(base_avg)}")
    print("-" * 78)
    print(f"{'점수대':>8} | {'신호':>5} | {'체결률':>6} | {'승률':>6} | "
          f"{'평균수익':>8} | {'목표':>5} {'손절':>5} {'만기':>5} | {'포워드':>8}")
    print("-" * 78)

    def row(label, recs):
        n = len(recs)
        if n == 0:
            print(f"{label:>8} | {'0':>5} |")
            return
        filled = [r for r in recs if r["filled"]]
        nf = len(filled)
        fill_rate = nf / n
        wins = [r for r in filled if r["outcome"] == "target"]
        stops = [r for r in filled if r["outcome"] == "stop"]
        tos = [r for r in filled if r["outcome"] == "timeout"]
        winrate = (len(wins) / nf) if nf else None
        avg_ret = (sum(r["ret"] for r in filled) / nf) if nf else None
        fwds = [r["fwd"] for r in recs if r["fwd"] is not None]
        avg_fwd = (sum(fwds) / len(fwds)) if fwds else None
        tgt = (len(wins) / nf) if nf else 0
        stp = (len(stops) / nf) if nf else 0
        to = (len(tos) / nf) if nf else 0
        print(f"{label:>8} | {n:>5} | {fill_rate*100:>5.0f}% | "
              f"{(winrate*100 if winrate is not None else 0):>5.0f}% | "
              f"{_pct(avg_ret):>8} | {tgt*100:>4.0f}% {stp*100:>4.0f}% {to*100:>4.0f}% | "
              f"{_pct(avg_fwd):>8}")

    for lo, hi, label in _BUCKETS:
        row(label, [r for r in records if lo <= r["score"] <= hi])
    print("-" * 78)
    row("전체", records)
    print("=" * 78)
    print("해석: '포워드'가 베이스라인보다 높고 점수대가 올라갈수록 개선되면 점수에 신호력이 있는 것.")
    print("      '승률/평균수익'은 진입가·손절·목표 규칙까지 포함한 실제 매매 근사치.")


# ═══════════════════════════════════════════════════════
# 데이터 로드 (FinanceDataReader)
# ═══════════════════════════════════════════════════════
def load_ohlcv(ticker: str, start: str, end: str | None) -> list:
    import FinanceDataReader as fdr
    df = fdr.DataReader(ticker, start, end)
    if df is None or len(df) == 0:
        return []
    out = []
    for r in df.itertuples():
        try:
            o, h, l, c = float(r.Open), float(r.High), float(r.Low), float(r.Close)
            v = float(getattr(r, "Volume", 0) or 0)
            if c <= 0:
                continue
            out.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def default_universe(market: str, max_tickers: int) -> list[str]:
    if market == "kr":
        from strategy_clenow_kr import KR_UNIVERSE_TOP350
        return [code for code, _ in KR_UNIVERSE_TOP350[:max_tickers]]
    # 미국 대표 종목
    us = ["NVDA", "TSLA", "AAPL", "MSFT", "AMD", "META", "AMZN", "GOOGL",
          "AVGO", "PLTR", "NFLX", "QCOM", "MU", "SMCI", "COIN", "UBER",
          "CRM", "ADBE", "INTC", "MRVL"]
    return us[:max_tickers]


def main():
    ap = argparse.ArgumentParser(description="어드바이저 스윙 점수 백테스트")
    ap.add_argument("--market", choices=["kr", "us"], default="kr")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--tickers", default="", help="CSV 직접 지정 (없으면 기본 유니버스)")
    ap.add_argument("--max-tickers", type=int, default=60)
    ap.add_argument("--stop-pct", type=float, default=SW_STOP_PCT)
    ap.add_argument("--rr", type=float, default=SW_RR)
    ap.add_argument("--max-hold", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=10)
    args = ap.parse_args()

    market_code = "US" if args.market == "us" else "KR"
    if args.tickers.strip():
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = default_universe(args.market, args.max_tickers)

    print(f"[BT] {args.market.upper()} {len(tickers)}종목 | {args.start}~{args.end or '오늘'} "
          f"| stop {args.stop_pct} RR {args.rr} hold {args.max_hold}")

    all_records, all_baseline = [], []
    for n, t in enumerate(tickers, 1):
        try:
            ohlcv = load_ohlcv(t, args.start, args.end)
        except Exception as e:
            print(f"[BT] {t} 로드 실패: {e}")
            continue
        if len(ohlcv) < 120:
            print(f"[BT] {t} 데이터 부족({len(ohlcv)})")
            continue
        recs = backtest_series(ohlcv, market=market_code,
                               stop_pct=args.stop_pct, rr=args.rr,
                               max_hold=args.max_hold, horizon=args.horizon)
        all_records.extend(recs)
        all_baseline.extend(baseline_forward(ohlcv, horizon=args.horizon))
        print(f"[BT] ({n}/{len(tickers)}) {t}: 신호 {len(recs)}건")

    summarize(all_records, all_baseline)


if __name__ == "__main__":
    main()
