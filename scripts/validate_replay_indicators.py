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
    data_type = "ohlcv_1min_from_ticks"
    schema = "broker_fyers"

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        symbol = await conn.fetchval(
            f"SELECT symbol FROM {schema}.{data_type} ORDER BY time DESC LIMIT 1"
        )

    if not symbol:
        raise RuntimeError(f"No symbols found in {schema}.{data_type}")

    rows = await fetch_historical_series(
        symbol=symbol,
        provider=provider,
        data_type=data_type,
        timeframe="1m",
        indicators=["ema_20", "sma_20", "rsi_14", "macd"],
    )

    if not rows:
        raise RuntimeError("No rows returned for indicator validation")

    sample_keys = sorted(rows[0].keys())
    print(f"[VALIDATE] symbol={symbol}")
    print(f"[VALIDATE] rows={len(rows)}")
    print(f"[VALIDATE] sample_keys={sample_keys}")

    expected_keys = {
        "ema_20",
        "sma_20",
        "rsi_14",
        "macd_line",
        "macd_signal",
        "macd_histogram",
    }

    missing = [k for k in expected_keys if k not in rows[0]]
    if missing:
        raise RuntimeError(f"Missing indicator keys in stream rows: {missing}")

    non_null_counts = {
        key: sum(1 for r in rows if r.get(key) is not None)
        for key in expected_keys
    }
    print(f"[VALIDATE] non_null_counts={non_null_counts}")

    if non_null_counts["ema_20"] == 0:
        raise RuntimeError("EMA values are all null")
    if non_null_counts["sma_20"] == 0:
        raise RuntimeError("SMA values are all null")
    if non_null_counts["rsi_14"] == 0:
        raise RuntimeError("RSI values are all null")
    if non_null_counts["macd_line"] == 0:
        raise RuntimeError("MACD line values are all null")

    print("[VALIDATE] indicator computation checks passed.")
    await DatabaseManager.close_pool()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
