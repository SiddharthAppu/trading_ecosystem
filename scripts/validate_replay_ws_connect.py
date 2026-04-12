import asyncio
import json
import websockets


async def main() -> None:
    uri = "ws://localhost:8765"
    config = {
        "symbol": "NSE:NIFTY50-INDEX",
        "provider": "fyers",
        "data_type": "ohlcv_1min_from_ticks",
        "timeframe": "1m",
        "speed": 1000,
    }

    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(config))
        first = json.loads(await ws.recv())
        print(f"[VALIDATE] first_message={first}")

        status = first.get("status")
        if status not in {"started", "no_data"}:
            raise RuntimeError(f"Unexpected first replay message: {first}")

        print("[VALIDATE] replay websocket connectivity check passed.")


if __name__ == "__main__":
    asyncio.run(main())
