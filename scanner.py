import kis_auth as api
from config import MIN_VOLUME_RATIO, MIN_CHANGE_RATE, MAX_CHANGE_RATE

def get_top_volume_stocks() -> list:
    """거래량 상위 종목 조회 (코스피 + 코스닥)"""
    candidates = []
    for market in ["J", "Q"]:  # J=코스피, Q=코스닥
        try:
            data = api.get(
                "/uapi/domestic-stock/v1/ranking/volume",
                "FHPST01710000",
                {
                    "fid_cond_mrkt_div_code": market,
                    "fid_cond_scr_div_code": "20171",
                    "fid_input_iscd": "0000",
                    "fid_div_cls_code": "0",
                    "fid_blng_cls_code": "0",
                    "fid_trgt_cls_code": "111111111",
                    "fid_trgt_exls_cls_code": "000000",
                    "fid_input_price_1": "1000",   # 최소 주가 1000원
                    "fid_input_price_2": "100000",  # 최대 주가 10만원
                    "fid_vol_cnt": "100000",         # 최소 거래량
                    "fid_input_date_1": "",
                }
            )
            if data.get("rt_cd") == "0":
                candidates.extend(data.get("output", []))
        except Exception as e:
            print(f"[SCANNER] 거래량 조회 오류 ({market}): {e}")
    return candidates

def get_stock_detail(ticker: str) -> dict:
    """종목 현재가 + 상세 정보 조회"""
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
            }
        )
        if data.get("rt_cd") == "0":
            return data.get("output", {})
    except Exception as e:
        print(f"[SCANNER] 종목 상세 오류 ({ticker}): {e}")
    return {}

def get_average_volume(ticker: str, days: int = 20) -> float:
    """N일 평균 거래량 조회"""
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
        print(f"[SCANNER] 평균 거래량 오류 ({ticker}): {e}")
    return 0

def scan_candidates(exclude_tickers: list = []) -> list:
    """
    매수 후보 종목 스캔
    조건: 거래량 급증 + 상승률 3~8% 구간
    """
    print("[SCANNER] 종목 스캔 시작...")
    top_stocks = get_top_volume_stocks()
    candidates = []

    for stock in top_stocks[:50]:  # 상위 50개만 검사
        ticker = stock.get("mksc_shrn_iscd", "")
        if not ticker or ticker in exclude_tickers:
            continue

        detail = get_stock_detail(ticker)
        if not detail:
            continue

        # 당일 상승률
        change_rate = float(detail.get("prdy_ctrt", 0))
        if not (MIN_CHANGE_RATE <= change_rate <= MAX_CHANGE_RATE):
            continue

        # 거래량 비율
        today_vol = int(detail.get("acml_vol", 0))
        avg_vol = get_average_volume(ticker)
        if avg_vol == 0:
            continue

        vol_ratio = today_vol / avg_vol
        if vol_ratio < MIN_VOLUME_RATIO:
            continue

        current_price = int(detail.get("stck_prpr", 0))
        name = detail.get("hts_kor_isnm", ticker)

        candidates.append({
            "ticker": ticker,
            "name": name,
            "price": current_price,
            "change_rate": change_rate,
            "vol_ratio": vol_ratio,
            "today_vol": today_vol,
        })
        print(f"[SCANNER] ✅ {name}({ticker}) +{change_rate:.1f}% 거래량{vol_ratio:.1f}배")

    # 거래량 비율 높은 순 정렬
    candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
    print(f"[SCANNER] 스캔 완료 - {len(candidates)}개 종목 발견")
    return candidates
