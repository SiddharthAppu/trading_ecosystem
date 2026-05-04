"""Check what replay data is available for the ema_cross strategy config."""
import asyncio
from pathlib import Path
from dotenv import dotenv_values
import asyncpg

cfg = dotenv_values(Path(__file__).parents[1] / "config/.env")
db_url = (
    cfg.get("DATABASE_URL")
    or f"postgresql://{cfg['DB_USER']}:{cfg['DB_PASSWORD']}@{cfg['DB_HOST']}:{cfg.get('DB_PORT', 5432)}/{cfg['DB_NAME']}"
)


async def main():
    pool = await asyncpg.create_pool(db_url)
    async with pool.acquire() as conn:
        # First find the timestamp column name
        col_rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='broker_fyers' AND table_name='market_ticks' "
            "ORDER BY ordinal_position"
        )
        mt_cols = [r['column_name'] for r in col_rows]
        print('market_ticks columns:', mt_cols)
        ts_col = mt_cols[0]  # first column assumed timestamp

        print("=== broker_fyers.market_ticks — available dates ===")
        rows = await conn.fetch(
            f"""
            SELECT DATE({ts_col}) AS day, COUNT(*) AS cnt,
                   MIN(symbol) AS sym_sample
            FROM broker_fyers.market_ticks
            GROUP BY DATE({ts_col})
            ORDER BY day DESC LIMIT 15
        """
        )
        for r in rows:
            print(dict(r))

        for schema_table in ["master_broker.ohlcv_1m", "broker_fyers.ohlcv_1m"]:
            try:
                schema, table = schema_table.split(".")
                col_rows = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    f"WHERE table_schema='{schema}' AND table_name='{table}' "
                    "ORDER BY ordinal_position"
                )
                cols = [r["column_name"] for r in col_rows]
                if not cols:
                    print(f"\n=== {schema_table}: table does not exist ===")
                    continue
                print(f"\n=== {schema_table} columns: {cols} ===")
                ts_c = cols[0]
                rows = await conn.fetch(
                    f"SELECT DATE({ts_c}) AS day, COUNT(*) AS cnt, MIN(symbol) AS sym_sample "
                    f"FROM {schema_table} GROUP BY DATE({ts_c}) ORDER BY day DESC LIMIT 15"
                )
                for r in rows:
                    print(dict(r))
            except Exception as e:
                print(f"  ({schema_table} error: {e})")

        print("\n=== Distinct symbols in broker_fyers.market_ticks ===")
        rows = await conn.fetch(
            "SELECT DISTINCT symbol FROM broker_fyers.market_ticks ORDER BY symbol LIMIT 30"
        )
        for r in rows:
            print(r["symbol"])

    await pool.close()


asyncio.run(main())
