"""
종목 스캐너 - 복합 필터 모멘텀 전략
"""
import kis_auth as api
from strategy import is_valid_entry, is_bull_market

def get_top_volume_stocks() -> list:
    candidates = []
    # volume-rank API 마켓코드: J=코스피, Q=코스닥
    # 코스닥은 별도 scr_div_code 필요
    market_configs = [
        {"market": "J", "scr": "20171"},  # 코스피
        {"market": "Q", "scr": "20172"},  # 코스닥
    ]
    for cfg in market_configs:
        try:
            data = api.get(
                "/uapi/domestic-stock/v1/quotations/volume-rank",
                "FHPST01710000",
                {
                    "fid_cond_mrkt_div_code": cfg["market"],
                    "fid_cond_scr_div_code": cfg["scr"],
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
                candidates.extend(results)
                print(f"[SCANNER] {cfg['market']} 거래량 상위 {len(results)}개 조회 완료")
            else:
                print(f"[SCANNER] API 오류 ({cfg['market']}): {data.get('msg1', '')}")
        except Exception as e:
            print(f"[SCANNER] 조회 오류 ({cfg['market']}): {e}")
    return candidates

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
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_org_adj_prc": "1",
                "fid_period_div_code": "D",
            }
        )
        if data.get("rt_cd") == "0":
            outputs = data.get("output2", [])[:days]
            volumes = [int(o.get("acml_vol", 0)) for o in outputs if o.get("acml_vol")]
            if volumes:
                return sum(volumes) / len(volumes)
    except Exception as e:
        print(f"[SCANNER] 평균거래량 오류 ({ticker}): {e}")
    return 0

def scan_candidates(exclude_tickers: list = []) -> list:
    """복합 필터 종목 스캔"""

    # ① 시장 필터 먼저
    if not is_bull_market():
        print("[SCANNER] 📉 하락장 감지 - 오늘 매수 중단")
        return []

    print("[SCANNER] 종목 스캔 시작...")
    top_stocks = get_top_volume_stocks()
    candidates = []

    for stock in top_stocks[:60]:
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
        if avg_vol == 0:
            continue
        vol_ratio = today_vol / avg_vol

        # ② 복합 필터 진입 판단
        valid, reason = is_valid_entry(ticker, current_price, change_rate, vol_ratio)
        if not valid:
            continue

        candidates.append({
            "ticker": ticker,
            "name": name,
            "price": current_price,
            "change_rate": change_rate,
            "vol_ratio": vol_ratio,
            "reason": reason,
        })
        print(f"[SCANNER] ✅ {name}({ticker}) +{change_rate:.1f}% 거래량{vol_ratio:.1f}배")

    candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
    print(f"[SCANNER] 스캔 완료 - {len(candidates)}개 종목 통과")
    return candidates
