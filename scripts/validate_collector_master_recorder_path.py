from pathlib import Path
import sys
import requests


ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from scripts.master_recorder import QUICK_RECORDER, next_tuesday_expiries, build_command  # noqa: E402


BACKEND_URL = "http://localhost:8080"


def main() -> None:
    if not QUICK_RECORDER.exists():
        raise RuntimeError(f"quick_live_recorder missing at {QUICK_RECORDER}")

    expiries = next_tuesday_expiries(4)
    cmd = build_command(sys.executable, "fyers", expiries, 1)
    print(f"[VALIDATE] master_recorder command sample={cmd}")

    for provider in ("fyers", "upstox"):
        resp = requests.get(
            f"{BACKEND_URL}/auth/status",
            params={"provider": provider},
            timeout=8,
        )
        print(f"[VALIDATE] /auth/status provider={provider} status={resp.status_code}")
        if resp.status_code != 200:
            raise RuntimeError(f"auth/status failed for {provider}: {resp.text}")

    chain_resp = requests.post(
        f"{BACKEND_URL}/chain/generate",
        json={
            "underlying_symbol": "NSE:NIFTY50-INDEX",
            "expiry_date": expiries[0],
            "strike_count": 1,
            "provider": "fyers",
        },
        timeout=12,
    )
    print(f"[VALIDATE] /chain/generate status={chain_resp.status_code}")

    if chain_resp.status_code in (404, 405):
        raise RuntimeError("chain/generate endpoint unavailable")

    # Endpoint may return 200 with data or 500 for provider/auth/data conditions.
    print("[VALIDATE] collector-only API path required by recorder scripts is reachable.")


if __name__ == "__main__":
    main()
