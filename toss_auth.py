"""토스증권 Open API 인증/요청 래퍼 (v0.1 — 골격)

확인된 규격(2026):
  - Base URL: https://openapi.tossinvest.com
  - 인증: OAuth2 Client Credentials (client_id + client_secret, form-urlencoded)
          → access_token(Bearer), expires_in 86400(24h). refresh 없음, client당 토큰 1개.
  - 헤더: Authorization: Bearer {token}, 계좌/자산/주문 API는 X-Tossinvest-Account 필수
  - Rate limit(초당): ACCOUNT 1 · ASSET 5 · MARKET_DATA 10 · ORDER 6
                     응답 헤더 X-RateLimit-* / Retry-After 존재 → 429 시 대기 후 재시도

환경변수:
  TOSS_CLIENT_ID, TOSS_CLIENT_SECRET, TOSS_ACCOUNT(계좌번호, X-Tossinvest-Account 값)

⚠️ 시세/캔들/주문의 정확한 파라미터·body 필드는 공식 OpenAPI spec에만 있어
   여기선 엔드포인트·인증만 확정. 실제 필드는 toss_probe.py로 확인 후 채운다.
"""
import os
import time
from datetime import datetime, timedelta
import requests

BASE_URL = "https://openapi.tossinvest.com"

TOSS_CLIENT_ID     = os.environ.get("TOSS_CLIENT_ID", "")
TOSS_CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET", "")
TOSS_ACCOUNT       = os.environ.get("TOSS_ACCOUNT", "")

_token = {"access_token": None, "expires_at": None}


def get_access_token() -> str:
    now = datetime.now()
    if _token["access_token"] and _token["expires_at"] and _token["expires_at"] > now:
        return _token["access_token"]
    resp = requests.post(
        f"{BASE_URL}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": TOSS_CLIENT_ID,
            "client_secret": TOSS_CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token["access_token"] = data["access_token"]
    ttl = int(data.get("expires_in", 86400))
    _token["expires_at"] = now + timedelta(seconds=ttl - 3600)  # 만료 1시간 전 갱신
    print(f"[TOSS] 토큰 발급 완료 (ttl {ttl}s)")
    return _token["access_token"]


def _headers(account: bool) -> dict:
    h = {"Authorization": f"Bearer {get_access_token()}"}
    if account:
        h["X-Tossinvest-Account"] = TOSS_ACCOUNT
    return h


def _request(method: str, path: str, *, params=None, json=None,
             account=False, _retries=2) -> dict:
    """공통 요청 — 429(레이트리밋) 시 Retry-After 만큼 대기 후 재시도."""
    url = f"{BASE_URL}{path}"
    resp = requests.request(method, url, headers=_headers(account),
                            params=params, json=json, timeout=10)
    if resp.status_code == 429 and _retries > 0:
        wait = int(resp.headers.get("Retry-After", "1") or 1)
        print(f"[TOSS] 429 레이트리밋 → {wait}s 대기 후 재시도")
        time.sleep(min(wait, 5))
        return _request(method, path, params=params, json=json,
                        account=account, _retries=_retries - 1)
    resp.raise_for_status()
    return resp.json()


def get(path: str, params=None, account=False) -> dict:
    return _request("GET", path, params=params, account=account)


def post(path: str, json=None, account=False) -> dict:
    return _request("POST", path, json=json, account=account)
