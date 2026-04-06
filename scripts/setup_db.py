import asyncio
import sys
from pathlib import Path

# Add core package to path if not installed
sys.path.append(str(Path(__file__).parent.parent / "packages" / "trading_core"))

from trading_core.db import MigrationManager, DatabaseManager

async def setup():
    print("=== TRADING ECOSYSTEM DB SETUP ===")
    try:
        await MigrationManager.run_migrations()
        print("\n[SUCCESS] TimescaleDB schema and hypertables are ready.")
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {str(e)}")
    finally:
        await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(setup())
