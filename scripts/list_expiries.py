import argparse
import json

import requests

DEFAULT_BACKEND_URL = "http://localhost:8080"
DEFAULT_UNDERLYING = "NSE:NIFTY50-INDEX"
DEFAULT_TIMEOUT = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch option expiries from Data Collector API for one provider or both providers."
    )
    parser.add_argument(
        "--provider",
        choices=["fyers", "upstox"],
        help="If set, fetch expiries only for this provider. If omitted, fetch for both providers.",
    )
    parser.add_argument(
        "--underlying-symbol",
        default=DEFAULT_UNDERLYING,
        help="Underlying symbol to query expiries for.",
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help="Base URL for the Data Collector API.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def fetch_expiries(
    backend_url: str,
    underlying_symbol: str,
    provider: str | None,
    timeout: int,
) -> dict:
    params = {"underlying_symbol": underlying_symbol}
    if provider:
        params["provider"] = provider

    response = requests.get(f"{backend_url}/expiries/list", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def main() -> None:
    args = parse_args()

    try:
        payload = fetch_expiries(
            backend_url=args.backend_url,
            underlying_symbol=args.underlying_symbol,
            provider=args.provider,
            timeout=args.timeout,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] Failed to fetch expiries: {exc}")
        raise SystemExit(1)

    print(json.dumps(payload, indent=2))

    data = payload.get("data", {})
    for provider_name in sorted(data.keys()):
        expiries = data.get(provider_name, [])
        print(f"\n{provider_name.upper()} expiries ({len(expiries)}):")
        for expiry in expiries:
            print(f"- {expiry}")


if __name__ == "__main__":
    main()
