"""스캐너 v2.4 - 거래정지/파생ETF 필터 추가"""
import kis_auth as api
from strategy import get_market_regime

# 파생/레버리지 ETF 등 별도 계좌 권한이 필요한 종목 이름 키워드
_BLOCKED_KEYWORDS = (
    "레버리지", "인버스", "2X", "선물", "ETN",
    "곱버스", "3X", "X2", "X3",
)

def _is_blocked_name(name: str) -> bool:
    if not name:
        return False
    up = name.upper()
    return any(k.upper() in up for k in _BLOCKED_KEYWORDS)


def get_top_volume_stocks() -> list:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20171",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_blng_cls_code": "0",
                "fid_trgt_cls_code": "111111111",
                "fid_trgt_exls_cls_code": "000000",
                "fid_input_price_1": "1000",
                "fid_input_price_2": "300000",
                "fid_vol_cnt": "100000",
                "fid_input_date_1": "",
            }
        )
        if data.get("rt_cd") == "0":
            results = data.get("output", [])
            print(f"[SCANNER] 거래량 상위 {len(results)}개 조회")
            return results
        else:
            print(f"[SCANNER] API 오류: {data.get('msg1', '')}")
    except Exception as e:
        print(f"[SCANNER] 오류: {e}")
    return []

def get_stock_detail(ticker: str) -> dict:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
        )
        if data.get("rt_cd") == "0":
            return data.get("output", {})
    except:
        pass
    return {}

def scan_candidates(exclude_tickers: list = []) -> list:
    regime_info = get_market_regime()
    regime = regime_info["regime"]
    print(f"[SCANNER] 스캔 시작 - 국면: {regime}")

    stock_pool = get_top_volume_stocks()
    if not stock_pool:
        return []

    candidates = []

    for stock in stock_pool[:30]:
        ticker = stock.get("mksc_shrn_iscd", "")
        if not ticker or ticker in exclude_tickers:
            continue

        detail = get_stock_detail(ticker)
        if not detail:
            continue

        change_rate   = float(detail.get("prdy_ctrt", 0))
        current_price = int(detail.get("stck_prpr", 0))
        name          = detail.get("hts_kor_isnm", ticker)

        # ── 거래정지/관리종목 등 필터 ─────────────────
        # iscd_stat_cls_code: 00=정상, 51=관리, 52=투자주의, 53=투자경고,
        #                     54=투자위험, 55=거래정지, 58=거래중단, 59=단기과열
        stat = str(detail.get("iscd_stat_cls_code", "00"))
        if stat != "00":
            print(f"[SCANNER] ⏭️  {name}({ticker}) 종목상태={stat} 제외")
            continue

        # 파생 ETF/ETN/레버리지/인버스 등 이름 기반 필터
        if _is_blocked_name(name):
            print(f"[SCANNER] ⏭️  {name}({ticker}) 파생/레버리지 계열 제외")
            continue

        # ── 최소 조건 체크 ───────────────────────────
        # 상승률 0.5% 이상
        if change_rate < 0.5:
            print(f"[SCANNER] ❌ {name} 상승률 {change_rate:.1f}% (0.5% 미만)")
            continue

        # 주가 1000원 이상
        if current_price < 1000:
            print(f"[SCANNER] ❌ {name} 주가 {current_price:,}원 (1000원 미만)")
            continue

        candidates.append({
            "ticker": ticker,
            "name": name,
            "price": current_price,
            "change_rate": change_rate,
            "vol_ratio": 1.0,
            "reason": f"+{change_rate:.1f}% 거래량상위",
            "strategy_type": "MOMENTUM",
            "regime": regime,
        })
        print(f"[SCANNER] ✅ {name}({ticker}) +{change_rate:.1f}원 {current_price:,}원")

    # 상승률 높은 순 정렬
    candidates.sort(key=lambda x: x["change_rate"], reverse=True)
    print(f"[SCANNER] 완료 - {len(candidates)}개 통과")
    return candidates
