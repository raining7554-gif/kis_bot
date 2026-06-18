"""어드바이저 데이터 레이어 — KIS Open API 조회 래퍼

- get_quote: 현재가/시가/고가/저가/전일종가/누적거래대금 등 (단타 VWAP 계산용)
- get_minute_candles: 당일 분봉 (단타 RSI/단기 추세)
- get_volume_rank: 거래대금 상위 종목 (단타 자동발굴)
- 일봉은 기존 strategy.get_daily_candles 재사용 (스윙 분석용)
"""
import kis_auth as api


def get_quote(ticker: str) -> dict:
    """현재가 시세 조회. 단타 분석의 핵심 입력.

    리턴 키:
      name, price, open, high, low, prev_close,
      change_rate(전일대비%), volume(누적거래량),
      trade_amount(누적거래대금 원), vwap(=거래대금/거래량)
    """
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker},
        )
        if data.get("rt_cd") != "0":
            return {}
        o = data.get("output", {})
        price = _f(o.get("stck_prpr"))
        vol = _f(o.get("acml_vol"))
        amt = _f(o.get("acml_tr_pbmn"))
        vwap = (amt / vol) if vol > 0 else 0.0
        return {
            "ticker": ticker,
            "name": o.get("hts_kor_isnm", "").strip() or ticker,
            "price": price,
            "open": _f(o.get("stck_oprc")),
            "high": _f(o.get("stck_hgpr")),
            "low": _f(o.get("stck_lwpr")),
            "prev_close": _f(o.get("stck_sdpr")),  # 기준가(전일 종가)
            "change_rate": _f(o.get("prdy_ctrt")),
            "volume": vol,
            "trade_amount": amt,
            "vwap": vwap,
            "stat": str(o.get("iscd_stat_cls_code", "00")),  # 종목상태(00 정상)
        }
    except Exception as e:
        print(f"[ADVISOR_DATA] {ticker} 시세 조회 오류: {e}")
        return {}


def get_minute_candles(ticker: str, base_time: str = "153000") -> list:
    """당일 분봉 조회 (기준시각으로부터 최근 ~30봉, 최신순).

    리턴: [{time, close, high, low, volume}, ...]
    base_time: "HHMMSS" — 이 시각 이전 30봉. 장중엔 현재시각을 넣으면 최근 30분.
    """
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            {
                "fid_etc_cls_code": "",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_input_hour_1": base_time,
                "fid_pw_data_incu_yn": "Y",
            },
        )
        if data.get("rt_cd") != "0":
            return []
        outputs = data.get("output2") or []
        result = []
        for c in outputs:
            try:
                result.append({
                    "time": c.get("stck_cntg_hour", ""),
                    "close": _f(c.get("stck_prpr")),
                    "high": _f(c.get("stck_hgpr")),
                    "low": _f(c.get("stck_lwpr")),
                    "volume": _f(c.get("cntg_vol")),
                })
            except (ValueError, TypeError):
                continue
        return result  # 최신순
    except Exception as e:
        print(f"[ADVISOR_DATA] {ticker} 분봉 조회 오류: {e}")
        return []


def get_volume_rank(topn: int = 30, min_price: int = 1000, max_price: int = 2000000) -> list:
    """거래대금 상위 종목 (단타 자동발굴용).

    리턴: [{ticker, name, price, change_rate, volume, trade_amount}, ...]
    주의: 실시간 데이터라 장중에만 의미 있음. 모의계좌에선 미지원일 수 있음 → []
    """
    try:
        data = api.get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20171",
                "fid_input_iscd": "0000",       # 전체
                "fid_div_cls_code": "0",         # 전체
                "fid_blng_cls_code": "3",        # 3: 거래금액순
                "fid_trgt_cls_code": "111111111",
                "fid_trgt_exls_cls_code": "000000",  # 관리/투자경고 등 제외 안함(필요시 조정)
                "fid_input_price_1": str(min_price),
                "fid_input_price_2": str(max_price),
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )
        if data.get("rt_cd") != "0":
            print(f"[ADVISOR_DATA] 거래대금 순위 응답 코드={data.get('rt_cd')} {data.get('msg1','')}")
            return []
        outputs = data.get("output") or []
        result = []
        for o in outputs[:topn]:
            result.append({
                "ticker": o.get("mksc_shrn_iscd", ""),
                "name": o.get("hts_kor_isnm", "").strip(),
                "price": _f(o.get("stck_prpr")),
                "change_rate": _f(o.get("prdy_ctrt")),
                "volume": _f(o.get("acml_vol")),
                "trade_amount": _f(o.get("acml_tr_pbmn")),
            })
        return result
    except Exception as e:
        print(f"[ADVISOR_DATA] 거래대금 순위 오류: {e}")
        return []


def _f(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0
