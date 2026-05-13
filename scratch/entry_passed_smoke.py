from pathlib import Path
import asyncio
import json
from datetime import datetime

from services.strategy_runtime.offline_adapter.artifacts import _write_journal

async def main():
    path = Path("scratch/entry_passed_smoke.jsonl")
    if path.exists():
        path.unlink()
    await _write_journal(
        strategy_name="nifty_trend_options",
        timeframe="5m",
        symbol="NSE:NIFTY50-INDEX",
        journal_path=path,
        run_params={"mode": "backtest"},
        indicators=["ema_20", "sma_20", "macd"],
        trades=[{
            "entry_time": datetime.fromisoformat("2024-08-29T14:45:00+05:30"),
            "exit_time": datetime.fromisoformat("2024-09-04T09:15:00+05:30"),
            "symbol": "NIFTY 24300 PE 03 OCT 24",
            "direction": "PE",
            "entry_price": 140.0,
            "exit_price": 89.85,
            "exit_reason": "NTO_EXIT",
            "underlying_price_at_entry": 24300.0,
            "decision": "BEARISH",
            "target_price": 238.0,
            "stop_price": 91.0,
        }],
        lot_size=75,
    )
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print("events:", [e.get("event") for e in events])
    print("entry_event_symbol:", events[1].get("symbol"))
    print("entry_event_price:", events[1].get("data", {}).get("price"))

asyncio.run(main())
