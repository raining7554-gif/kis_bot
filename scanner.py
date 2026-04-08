"""
스캐너 v2.0 - 시장 국면별 종목 스캔
"""
import kis_auth as api
from strategy import is_valid_entry, get_market_regime

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
                "fid_input_price_2": "200000",
                "fid_vol_cnt": "100000",
                "fid_input_date_1": "",
            }
        )
        if data.get("rt_cd") == "0":
            results = data.get("output", [])
            print(f"[SCANNER] 거래량 상위 {len(results)}개 조회 완료")
            return results
        else:
            print(f"[SCANNER] API 오류: {data.get('msg1', '')}")
    except Exception as e:
        print(f"[SCANNER] 조회 오류: {e}")
    return []

def get_oversold_stocks() -> list:
    """
    공포매수용: 급락 + 과매도 종목 스캔
    하락률 상위 종목에서 반등 후보 찾기
    """
    try:
        # 하락률 상위 (낙폭과대 종목)
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20171",
                "fid_input_iscd": "0000",
                "fid_div_cls_code": "0",
                "fid_blng_cls_code": "1",   # 하락 종목
                "fid_trgt_cls_code": "111111111",
                "fid_trgt_exls_cls_code": "000000",
                "fid_input_price_1": "2000",
                "fid_input_price_2": "200000",
                "fid_vol_cnt": "500000",
                "fid_input_date_1": "",
            }
        )
        if data.get("rt_cd") == "0":
            results = data.get("output", [])
            print(f"[SCANNER] 과매도 후보 {len(results)}개 조회 완료")
            return results
    except Exception as e:
        print(f"[SCANNER] 과매도 조회 오류: {e}")
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
    except Exception as e:
        print(f"[SCANNER] 상세 오류 ({ticker}): {e}")
    return {}

def get_average_volume(ticker: str, days: int = 20) -> float:
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST01010400",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker,
             "fid_org_adj_prc": "1", "fid_period_div_code": "D"}
        )
        if data.get("rt_cd") == "0":
            outputs = data.get("output2", [])[:days]
            volumes = [int(o.get("acml_vol", 0)) for o in outputs if o.get("acml_vol")]
            if volumes:
                return sum(volumes) / len(volumes)
    except:
        pass
    return 0

def scan_candidates(exclude_tickers: list = []) -> list:
    """시장 국면에 따라 다른 스캔 전략 적용"""

    # 시장 국면 분석
    regime_info = get_market_regime()
    regime = regime_info["regime"]

    print(f"[SCANNER] 스캔 시작 - 국면: {regime}")

    # 국면별 종목 풀 선택
    if regime == "CRASH":
        stock_pool = get_oversold_stocks()
        if not stock_pool:
            stock_pool = get_top_volume_stocks()
    else:
        stock_pool = get_top_volume_stocks()

    if not stock_pool:
        print("[SCANNER] 종목 풀 비어있음")
        return []

    candidates = []

    for stock in stock_pool[:60]:
        ticker = stock.get("mksc_shrn_iscd", "")
        if not ticker or ticker in exclude_tickers:
            continue

        detail = get_stock_detail(ticker)
        if not detail:
            continue

        change_rate   = float(detail.get("prdy_ctrt", 0))
        today_vol     = int(detail.get("acml_vol", 0))
        current_price = int(detail.get("stck_prpr", 0))
        name          = detail.get("hts_kor_isnm", ticker)

        avg_vol = get_average_volume(ticker)
        vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0

        valid, reason, strategy_type = is_valid_entry(
            ticker, current_price, change_rate, vol_ratio, regime
        )

        if not valid:
            continue

        candidates.append({
            "ticker": ticker,
            "name": name,
            "price": current_price,
            "change_rate": change_rate,
            "vol_ratio": vol_ratio,
            "reason": reason,
            "strategy_type": strategy_type,
            "regime": regime,
        })
        print(f"[SCANNER] ✅ {name}({ticker}) {strategy_type} {reason}")

    # 공포매수는 거래량 많은 순, 모멘텀은 상승률 순
    if regime == "CRASH":
        candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
    else:
        candidates.sort(key=lambda x: (x["vol_ratio"] * x["change_rate"]), reverse=True)

    print(f"[SCANNER] 완료 - {len(candidates)}개 통과 (국면: {regime})")
    return candidates
