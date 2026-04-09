"""스캐너 v2.2 - 디버그 로그 + 조건 완화"""
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
    regime_info = get_market_regime()
    regime = regime_info["regime"]
    print(f"[SCANNER] 스캔 시작 - 국면: {regime}")

    stock_pool = get_top_volume_stocks()
    if not stock_pool:
        print("[SCANNER] 종목 풀 비어있음")
        return []

    candidates = []
    reject_summary = {}  # 탈락 이유 집계

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
            # 탈락 이유 집계 (로그 도배 방지)
            key = reason.split(" ")[0]
            reject_summary[key] = reject_summary.get(key, 0) + 1
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
        print(f"[SCANNER] ✅ {name}({ticker}) +{change_rate:.1f}% 거래량{vol_ratio:.0f}배")

    # 탈락 요약 출력
    if reject_summary:
        summary = " | ".join([f"{k}:{v}개" for k, v in reject_summary.items()])
        print(f"[SCANNER] 탈락 요약: {summary}")

    if regime == "CRASH":
        candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
    else:
        candidates.sort(key=lambda x: (x["vol_ratio"] * x["change_rate"]), reverse=True)

    print(f"[SCANNER] 완료 - {len(candidates)}개 통과 (국면: {regime})")
    return candidates
