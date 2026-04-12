import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "packages" / "trading_core"))

from trading_core.db import DatabaseManager  # noqa: E402
from services.replay_engine.main import fetch_historical_series  # noqa: E402


PROVIDER_TO_SCHEMA = {
    "fyers": "broker_fyers",
    "upstox": "broker_upstox",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate replay timeframe aggregation on derived tick candles."
    )
    parser.add_argument("--provider", choices=["fyers", "upstox"], default="fyers")
    parser.add_argument("--symbol", default="", help="Optional symbol to validate")
    parser.add_argument(
        "--data-type",
        default="ohlcv_1min_from_ticks",
        choices=["ohlcv_1min_from_ticks", "ohlcv_1m"],
    )
    return parser.parse_args()


async def resolve_symbol(provider: str, data_type: str, explicit_symbol: str) -> str:
    if explicit_symbol:
        return explicit_symbol

    schema = PROVIDER_TO_SCHEMA[provider]
    table = data_type
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        symbol = await conn.fetchval(
            f"SELECT symbol FROM {schema}.{table} ORDER BY time DESC LIMIT 1"
        )
    if not symbol:
        raise RuntimeError(f"No symbols found in {schema}.{table}")
    return symbol


async def main_async() -> None:
    args = parse_args()
    symbol = await resolve_symbol(args.provider, args.data_type, args.symbol)

    print(f"[VALIDATE] provider={args.provider} data_type={args.data_type} symbol={symbol}")

    one_min = await fetch_historical_series(
        symbol=symbol,
        provider=args.provider,
        data_type=args.data_type,
        timeframe="1m",
    )
    five_min = await fetch_historical_series(
        symbol=symbol,
        provider=args.provider,
        data_type=args.data_type,
        timeframe="5m",
    )
    ten_min = await fetch_historical_series(
        symbol=symbol,
        provider=args.provider,
        data_type=args.data_type,
        timeframe="10m",
    )

    print(f"[VALIDATE] 1m rows: {len(one_min)}")
    print(f"[VALIDATE] 5m rows: {len(five_min)}")
    print(f"[VALIDATE] 10m rows: {len(ten_min)}")

    if not one_min:
        raise RuntimeError("No 1m rows returned")
    if not five_min:
        raise RuntimeError("No 5m rows returned")
    if not ten_min:
        raise RuntimeError("No 10m rows returned")

    if len(one_min) < len(five_min) or len(five_min) < len(ten_min):
        raise RuntimeError("Unexpected aggregation row counts")

    sample = one_min[0]
    required = ["time", "symbol", "open", "high", "low", "close", "volume"]
    missing = [k for k in required if k not in sample]
    if missing:
        raise RuntimeError(f"Missing keys in sample row: {missing}")

    print("[VALIDATE] Replay timeframe aggregation checks passed.")

    await DatabaseManager.close_pool()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
