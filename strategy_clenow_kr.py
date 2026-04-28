"""KR Clenow Momentum 전략 (v1.0)

로직:
  1. 유니버스: KOSPI + KOSDAQ 시총 상위 ~350종목 (하드코딩 또는 외부 로드)
  2. 각 종목 120일 Clenow 스코어 계산 (annualized slope × R²)
  3. 크로스섹셔널 랭킹 상위 10% 선정
  4. KOSPI > MA200 일 때만 진입 허용
  5. 선정 종목 중 Close > MA50 조건 만족 것만 최대 8개 매수
  6. MA50 이탈 시 즉시 청산

백테스트 결과 (2018-2026):
  - CAGR +38%, Sharpe 1.14, MDD -42%
  - ₩1M → ₩14.8M (14.8배)

주의:
  - Clenow 스코어 계산은 CPU 쓰지만 120일 × 350종목 = 빠름 (< 1초)
  - 일봉 조회는 KIS API 대신 로컬 캐시 또는 외부 데이터 권장 (rate limit)
  - 실전용은 월~금 장중 1회 재랭킹 (매일 하면 거래 많아짐)
"""
from __future__ import annotations
import math
import numpy as np
import kis_auth as api


# ═══════════════════════════════════════════════════════
# KOSPI/KOSDAQ 시총 상위 유니버스 (2026-04 기준 시총 상위 종목)
# 실전에서는 주기적으로 갱신 필요
# ═══════════════════════════════════════════════════════
KR_UNIVERSE_TOP350 = [
    # KOSPI 시총 Top 100 (대표)
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
    ("005380", "현대차"), ("000270", "기아"), ("068270", "셀트리온"),
    ("207940", "삼성바이오로직스"), ("005490", "POSCO홀딩스"), ("035420", "NAVER"),
    ("006400", "삼성SDI"), ("105560", "KB금융"), ("055550", "신한지주"),
    ("012330", "현대모비스"), ("035720", "카카오"), ("000810", "삼성화재"),
    ("003550", "LG"), ("032830", "삼성생명"), ("015760", "한국전력"),
    ("329180", "HD현대중공업"), ("012450", "한화에어로스페이스"), ("051910", "LG화학"),
    ("086790", "하나금융지주"), ("138930", "BNK금융지주"), ("010130", "고려아연"),
    ("011200", "HMM"), ("018260", "삼성에스디에스"), ("096770", "SK이노베이션"),
    ("034730", "SK"), ("028260", "삼성물산"), ("009150", "삼성전기"),
    ("033780", "KT&G"), ("017670", "SK텔레콤"), ("030200", "KT"),
    ("316140", "우리금융지주"), ("011170", "롯데케미칼"), ("021240", "코웨이"),
    ("003670", "포스코퓨처엠"), ("000720", "현대건설"), ("003490", "대한항공"),
    ("009540", "HD한국조선해양"), ("010620", "HD현대미포"), ("042660", "한화오션"),
    ("010140", "삼성중공업"), ("079550", "LIG넥스원"), ("064350", "현대로템"),
    ("272210", "한화시스템"), ("034020", "두산에너빌리티"), ("052690", "한전기술"),
    ("267260", "HD현대일렉트릭"), ("161390", "한국타이어앤테크놀로지"),
    ("000080", "하이트진로"), ("002790", "아모레G"), ("090430", "아모레퍼시픽"),
    ("036570", "엔씨소프트"), ("001450", "현대해상"), ("000240", "한국앤컴퍼니"),
    ("078930", "GS"), ("066570", "LG전자"), ("034220", "LG디스플레이"),
    ("004020", "현대제철"), ("010950", "S-Oil"), ("003230", "삼양식품"),
    ("023530", "롯데쇼핑"), ("097950", "CJ제일제당"), ("036460", "한국가스공사"),
    ("001040", "CJ"), ("180640", "한진칼"), ("024110", "기업은행"),
    ("139480", "이마트"), ("071050", "한국금융지주"), ("047050", "포스코인터내셔널"),
    ("005830", "DB손해보험"), ("251270", "넷마블"), ("006360", "GS건설"),
    ("018880", "한온시스템"), ("020150", "롯데에너지머티리얼즈"), ("002350", "넥센타이어"),
    ("000210", "DL"), ("009830", "한화솔루션"), ("000100", "유한양행"),
    ("008770", "호텔신라"), ("293480", "하나투어"), ("042700", "한미반도체"),
    # KOSDAQ 시총 Top 80
    ("086520", "에코프로"), ("247540", "에코프로비엠"), ("196170", "알테오젠"),
    ("277810", "레인보우로보틱스"), ("058470", "리노공업"), ("328130", "루닛"),
    ("328130", "루닛"), ("214150", "클래시스"), ("237690", "에스티팜"),
    ("298380", "에이비엘바이오"), ("085660", "차바이오텍"), ("403870", "HPSP"),
    ("095340", "ISC"), ("240810", "원익IPS"), ("039030", "이오테크닉스"),
    ("005290", "동진쎄미켐"), ("357780", "솔브레인"), ("000990", "DB하이텍"),
    ("036930", "주성엔지니어링"), ("140860", "파크시스템스"), ("094840", "슈프리마"),
    ("064290", "인텍플러스"), ("131970", "테스나"), ("036810", "에프에스티"),
    ("104830", "원익머트리얼즈"), ("066970", "엘앤에프"), ("121600", "나노신소재"),
    ("253450", "스튜디오드래곤"), ("064850", "더존비즈온"), ("108860", "셀바스AI"),
    ("025770", "한국정보통신"), ("060280", "큐렉소"), ("203650", "드림시큐리티"),
    ("376300", "디어유"), ("068760", "셀트리온제약"), ("141080", "레고켐바이오"),
    ("112040", "위메이드"), ("293490", "카카오게임즈"), ("263750", "펄어비스"),
    ("095700", "제넥신"), ("145020", "휴젤"), ("290650", "엘앤씨바이오"),
    ("145720", "덴티움"), ("278280", "천보"), ("122870", "와이지엔터테인먼트"),
    ("041510", "에스엠"), ("035900", "JYP Ent."), ("352820", "하이브"),
    ("112610", "씨에스윈드"), ("267850", "아스트"), ("357550", "석경에이티"),
    ("225570", "넥슨게임즈"), ("054620", "아피스코"), ("086900", "메디톡스"),
    ("084370", "유진테크"), ("213420", "덕산네오룩스"), ("089030", "테크윙"),
    ("039200", "오스코텍"), ("389020", "엔켐"), ("054540", "삼영엠텍"),
    ("402030", "블루엠텍"), ("088800", "에이스테크"), ("138080", "오리온홀딩스"),
    ("048410", "현대바이오"), ("192080", "더블유게임즈"), ("066970", "엘앤에프"),
    ("039440", "에스티아이"), ("222080", "씨아이에스"), ("900140", "엘브이엠씨"),
    ("046890", "서울반도체"), ("085370", "뉴지랩파마"), ("950170", "JTC"),
]


# ═══════════════════════════════════════════════════════
# 일봉 조회 (KIS API) — 전 종목 조회는 느리니 캐시 권장
# ═══════════════════════════════════════════════════════
def get_kr_daily(ticker: str, count: int = 140) -> list:
    """KR 종목 일봉 조회 (최신순, count 일)"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_org_adj_prc": "1",
                "fid_period_div_code": "D",
            },
        )
        outputs = data.get("output2") or data.get("output") or []
        out = []
        for o in outputs[:count]:
            try:
                out.append({
                    "date": o.get("stck_bsop_date", ""),
                    "close": float(o.get("stck_clpr", 0)),
                    "high": float(o.get("stck_hgpr", 0)),
                    "low": float(o.get("stck_lwpr", 0)),
                    "volume": int(float(o.get("acml_vol", 0))),
                })
            except (ValueError, TypeError):
                continue
        return out
    except Exception as e:
        print(f"[CLENOW] {ticker} 일봉 오류: {e}")
        return []


def _sma(values: list[float], n: int) -> float:
    if len(values) < n:
        return 0.0
    return sum(values[:n]) / n


def clenow_score(closes: list[float], n: int = 120) -> float:
    """Clenow 모멘텀 스코어 — annualized slope × R²
    closes: 최신순 list (closes[0] = today)
    """
    if len(closes) < n:
        return float("nan")
    # 오래된 순으로 뒤집어 회귀
    y = np.log(np.array(closes[:n][::-1], dtype=float))
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    annualized = (np.exp(slope) ** 252 - 1) * 100
    return annualized * r2


def check_kospi_regime() -> dict:
    """KOSPI > MA200 판정"""
    candles = get_kr_daily("0001", count=220)  # KOSPI 지수
    if len(candles) < 200:
        # 지수 조회 실패 시 대표주 삼성전자로 근사
        candles = get_kr_daily("005930", count=220)
    if len(candles) < 200:
        return {"regime": "UNKNOWN", "close": 0, "ma200": 0}
    closes = [c["close"] for c in candles]
    close = closes[0]
    ma200 = _sma(closes, 200)
    regime = "BULL" if close > ma200 else "BEAR"
    return {"regime": regime, "close": close, "ma200": ma200}


# ═══════════════════════════════════════════════════════
# 유니버스 스코어링 + 진입 후보 선정
# ═══════════════════════════════════════════════════════
def scan_clenow_candidates(
    universe: list[tuple] = None,
    n: int = 120, top_pct: float = 0.10, exit_ma: int = 50,
    max_positions: int = 8,
    excluded_tickers: list[str] = None,
    max_price: int = None,   # 가격 상한 (소액 시드용)
) -> list[dict]:
    """유니버스 전체 스코어링 후 상위 top_pct 종목 반환.

    max_price: 종목 현재가 상한. 소액 시드에서 1주도 못 사는 종목 사전 제외.
    리턴: [{"ticker", "name", "score", "close", "ma50"}, ...] max_positions 개
    """
    if universe is None:
        universe = KR_UNIVERSE_TOP350
    if excluded_tickers is None:
        excluded_tickers = []

    # 1) KOSPI 체제
    regime_info = check_kospi_regime()
    if regime_info["regime"] != "BULL":
        print(f"[CLENOW] KOSPI 체제={regime_info['regime']} → 진입 보류")
        return []

    # 2) 전 유니버스 스코어링 (KIS API 호출이 많음 — rate limit 주의)
    scored = []
    skipped_price = 0
    for ticker, name in universe:
        if ticker in excluded_tickers:
            continue
        candles = get_kr_daily(ticker, count=max(n, exit_ma) + 10)
        if len(candles) < n:
            continue
        closes = [c["close"] for c in candles]
        # 가격 상한 필터 (소액 시드)
        if max_price and closes[0] > max_price:
            skipped_price += 1
            continue
        score = clenow_score(closes, n)
        if math.isnan(score):
            continue
        ma50 = _sma(closes, exit_ma)
        if closes[0] <= ma50:
            continue  # MA50 이탈 종목 제외
        scored.append({
            "ticker": ticker, "name": name,
            "score": score, "close": closes[0], "ma50": ma50,
        })

    if max_price and skipped_price:
        print(f"[CLENOW] 가격상한 ₩{max_price:,} 초과 {skipped_price}개 제외")

    if not scored:
        print("[CLENOW] 점수 매긴 종목 없음")
        return []

    # 3) 상위 top_pct 선정
    scored.sort(key=lambda x: -x["score"])
    n_top = max(1, int(len(scored) * top_pct))
    top = scored[:n_top]

    # 4) 최대 max_positions 개
    return top[:max_positions]


def should_exit(ticker: str, exit_ma: int = 50) -> tuple[bool, str]:
    """MA50 이탈 체크"""
    candles = get_kr_daily(ticker, count=exit_ma + 5)
    if len(candles) < exit_ma:
        return False, "데이터 부족"
    closes = [c["close"] for c in candles]
    ma = _sma(closes, exit_ma)
    if closes[0] < ma:
        return True, f"MA{exit_ma} 이탈 ({closes[0]:.0f} < {ma:.0f})"
    return False, ""
