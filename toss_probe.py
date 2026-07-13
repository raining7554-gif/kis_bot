"""토스증권 Open API 탐침 — 실제 응답으로 필드명 확인용 (일회성)

목적: 정확한 필드 스키마(특히 주문 전에 시세/잔고 구조)를 실제 계좌 응답으로
확인한다. 추측 대신 실물 JSON을 보고 어댑터를 정확히 구현하기 위함.

실행:
  TOSS_CLIENT_ID=... TOSS_CLIENT_SECRET=... TOSS_ACCOUNT=... python toss_probe.py

⚠️ 조회(GET)만 한다. 주문은 하지 않는다. 출력 JSON을 그대로 공유해주면
   데이터/주문 어댑터를 실제 필드에 맞춰 완성한다.
"""
import json
import toss_auth as t


def show(name: str, fn):
    print("\n" + "=" * 60)
    print(name)
    print("-" * 60)
    try:
        data = fn()
        s = json.dumps(data, ensure_ascii=False, indent=2)
        print(s[:2500] + ("\n… (생략)" if len(s) > 2500 else ""))
    except Exception as e:
        print(f"오류: {e}")


def main():
    # 1) 계좌/보유 — 파라미터 없이 확실히 호출 가능
    show("GET /api/v1/accounts", lambda: t.get("/api/v1/accounts", account=True))
    show("GET /api/v1/holdings", lambda: t.get("/api/v1/holdings", account=True))

    # 2) 시세 — 파라미터명이 문서에만 있어, 흔한 후보들을 시도(삼성전자 005930)
    for p in ({"productCodes": "005930"}, {"symbols": "005930"},
              {"code": "005930"}, {"productCode": "005930"}, {"stockCodes": "005930"}):
        show(f"GET /api/v1/prices {p}", lambda p=p: t.get("/api/v1/prices", params=p))

    # 3) 캔들(일봉) — 후보 파라미터 시도
    for p in ({"code": "005930", "period": "DAY", "count": 5},
              {"productCode": "005930", "interval": "1d", "count": 5},
              {"symbol": "005930", "type": "DAY"}):
        show(f"GET /api/v1/candles {p}", lambda p=p: t.get("/api/v1/candles", params=p))


if __name__ == "__main__":
    main()
