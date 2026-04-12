import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "packages" / "trading_core"))

from trading_core.db import DatabaseManager  # noqa: E402
from services.replay_engine.main import fetch_historical_series  # noqa: E402


async def main_async() -> None:
    provider = "fyers"
    schema = "broker_fyers"

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        symbol = await conn.fetchval(
            f"SELECT symbol FROM {schema}.market_ticks ORDER BY time DESC LIMIT 1"
        )

    if not symbol:
        raise RuntimeError(f"No symbols found in {schema}.market_ticks")

    print(f"[VALIDATE] provider={provider} symbol={symbol}")

    rows = await fetch_historical_series(
        symbol=symbol,
        provider=provider,
        data_type="market_ticks",
        timeframe="1m",
    )

    if not rows:
        raise RuntimeError("No market_ticks rows returned for 1m")

    required = {"time", "symbol", "price", "volume", "bid", "ask"}
    missing = required.difference(rows[0].keys())
    if missing:
        raise RuntimeError(f"Missing required market_ticks keys: {sorted(missing)}")

    print(f"[VALIDATE] market_ticks_1m_rows={len(rows)}")
    print(f"[VALIDATE] sample_keys={sorted(rows[0].keys())}")

    try:
        await fetch_historical_series(
            symbol=symbol,
            provider=provider,
            data_type="market_ticks",
            timeframe="5m",
        )
        raise RuntimeError("Expected 5m market_ticks request to be rejected")
    except ValueError as exc:
        print(f"[VALIDATE] expected_rejection={exc}")

    print("[VALIDATE] market_ticks replay compatibility checks passed.")
    await DatabaseManager.close_pool()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
