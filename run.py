"""진입점 디스패처 — BOT_MODE 환경변수로 실행할 봇 선택

Railway 등에서 같은 저장소(같은 railway.toml)로 여러 서비스를 띄울 때,
start command 대신 서비스별 환경변수로 봇을 고른다. 환경변수는 서비스마다
독립이라 재배포해도 안 바뀐다.

  BOT_MODE=trade     (기본) → 자동매매봇 (main.py)
  BOT_MODE=advisor           → 매매 어드바이저 봇 (advisor.py)
  BOT_MODE=liquidate         → 전량 청산 후 종료 (liquidate.py)
  BOT_MODE=off               → 안전 정지 (아무것도 안 함)
"""
import os


def _resolve_mode() -> str:
    return os.environ.get("BOT_MODE", "trade").strip().lower()


def main():
    mode = _resolve_mode()
    if mode in ("off", "stop", "idle", "none", "pause", "정지"):
        # 안전 정지 — 매매/조회 아무것도 안 하고 즉시 종료.
        # (restartPolicyType=ON_FAILURE 이므로 정상 종료 시 재시작 안 됨)
        print(f"[RUN] BOT_MODE={mode} → 정지 모드. 봇이 아무 것도 하지 않습니다.")
        try:
            import telegram
            telegram.send_force("⏸️ <b>봇 정지됨</b> (BOT_MODE=off)\n"
                                "매매/조회 중단. 재개하려면 BOT_MODE를 되돌리세요.")
        except Exception:
            pass
        return
    if mode in ("liquidate", "청산", "sell_all", "selloff"):
        print(f"[RUN] BOT_MODE={mode} → 전량 청산 모드 실행")
        import liquidate
        liquidate.main()
    elif mode in ("advisor", "adviser", "advice", "어드바이저"):
        print(f"[RUN] BOT_MODE={mode} → 어드바이저 봇 실행")
        import advisor
        advisor.main()
    else:
        print(f"[RUN] BOT_MODE={mode or 'trade'} → 자동매매봇 실행")
        import main
        main.main()


if __name__ == "__main__":
    main()
