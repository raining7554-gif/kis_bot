"""진입점 디스패처 — BOT_MODE 환경변수로 실행할 봇 선택

Railway 등에서 같은 저장소(같은 railway.toml)로 여러 서비스를 띄울 때,
start command 대신 서비스별 환경변수로 봇을 고른다. 환경변수는 서비스마다
독립이라 재배포해도 안 바뀐다.

  BOT_MODE=trade    (기본) → 자동매매봇 (main.py)
  BOT_MODE=advisor          → 매매 어드바이저 봇 (advisor.py)
"""
import os


def _resolve_mode() -> str:
    return os.environ.get("BOT_MODE", "trade").strip().lower()


if __name__ == "__main__":
    mode = _resolve_mode()
    if mode in ("advisor", "adviser", "advice", "어드바이저"):
        print(f"[RUN] BOT_MODE={mode} → 어드바이저 봇 실행")
        import advisor
        advisor.main()
    else:
        print(f"[RUN] BOT_MODE={mode or 'trade'} → 자동매매봇 실행")
        import main
        main.main()
