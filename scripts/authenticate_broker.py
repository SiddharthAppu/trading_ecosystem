from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    core = root / "packages" / "trading_core"
    for p in (root, core):
        ptxt = str(p)
        if ptxt not in sys.path:
            sys.path.insert(0, ptxt)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and refresh broker authentication token.")
    parser.add_argument("--provider", default="upstox", help="Broker provider name (e.g. upstox, fyers)")
    parser.add_argument("--auth-code", default="", help="Optional auth code from broker redirect")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt for auth code; fail if not authenticated",
    )
    args = parser.parse_args()

    _ensure_paths()

    from trading_core import get_adapter

    provider = args.provider.strip().lower()
    adapter = get_adapter(provider)

    if adapter.validate_token():
        print(f"[OK] {provider} is already authenticated.")
        return 0

    print(f"[WARN] {provider} is not authenticated.")
    auth_url = adapter.generate_auth_link()
    print("\nOpen this URL in your browser and complete login:")
    print(auth_url)

    auth_code = args.auth_code.strip()
    if not auth_code and args.non_interactive:
        print("[ERROR] Non-interactive mode and no --auth-code provided.")
        return 2

    if not auth_code:
        auth_code = input("\nPaste broker auth code: ").strip()

    if not auth_code:
        print("[ERROR] Empty auth code. Aborting.")
        return 2

    try:
        adapter.fetch_access_token(auth_code)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to fetch access token: {exc}")
        return 3

    if not adapter.validate_token():
        print("[ERROR] Token saved but validation still failed.")
        return 4

    print(f"[OK] {provider} authentication successful and token saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
