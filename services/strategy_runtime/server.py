from __future__ import annotations

import asyncio
import logging

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from services.strategy_runtime.bootstrap import ensure_repo_paths

ensure_repo_paths()

from services.strategy_runtime.config import RuntimeSettings
from services.strategy_runtime.main import configure_logging
from services.strategy_runtime.runtime import StrategyRuntime, create_runtime


logger = logging.getLogger("strategy_runtime.server")
app = FastAPI(title="Strategy Runtime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RuntimeApiState:
    def __init__(self):
        self.runtime: StrategyRuntime | None = None
        self.runtime_task: asyncio.Task | None = None

    def get_runtime(self) -> StrategyRuntime:
        if self.runtime is None:
            settings = RuntimeSettings.from_env()
            configure_logging(settings)
            self.runtime = create_runtime(settings)
        return self.runtime


state = RuntimeApiState()


def _get_runtime() -> StrategyRuntime:
    return state.get_runtime()


async def _ensure_started() -> None:
    runtime = _get_runtime()
    if state.runtime_task and not state.runtime_task.done():
        return

    async def _runner() -> None:
        try:
            await runtime.run()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Strategy runtime task failed: %s", exc)

    state.runtime_task = asyncio.create_task(_runner())


@app.on_event("startup")
async def _startup() -> None:
    runtime = _get_runtime()
    if runtime.settings.autostart:
        await _ensure_started()


@app.on_event("shutdown")
async def _shutdown() -> None:
    runtime = _get_runtime()
    await runtime.stop()
    if state.runtime_task:
        await asyncio.wait({state.runtime_task}, timeout=5)


@app.get("/health")
async def health() -> dict:
    runtime = _get_runtime()
    return {
        "service": "strategy_runtime",
        "ok": True,
        "running": runtime.get_status().get("running", False),
    }


@app.get("/status")
async def status() -> dict:
    runtime = _get_runtime()
    return runtime.get_status()


@app.get("/events")
async def events(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    runtime = _get_runtime()
    return {"events": runtime.get_recent_events(limit=limit)}


@app.post("/runtime/start")
async def start_runtime() -> dict:
    runtime = _get_runtime()
    if runtime.get_status().get("running"):
        return {"status": "already_running"}

    await _ensure_started()
    return {"status": "started"}


@app.post("/runtime/stop")
async def stop_runtime() -> dict:
    runtime = _get_runtime()
    if not runtime.get_status().get("running"):
        return {"status": "already_stopped"}

    await runtime.stop()
    if state.runtime_task:
        await asyncio.wait({state.runtime_task}, timeout=5)
        state.runtime_task = None
    return {"status": "stopped"}


@app.post("/runtime/restart")
async def restart_runtime() -> dict:
    await stop_runtime()
    await start_runtime()
    return {"status": "restarted"}


@app.get("/runtime/config")
async def runtime_config() -> dict:
    runtime = _get_runtime()
    return {
        "feed_source": runtime.settings.feed_source,
        "provider": runtime.settings.provider,
        "symbol": runtime.settings.symbol,
        "timeframe": runtime.settings.timeframe,
        "strategy_name": runtime.settings.strategy_name,
        "strategy_class_path": runtime.settings.strategy_class_path,
        "polling_interval_seconds": runtime.settings.polling_interval_seconds,
        "lookback_bars": runtime.settings.lookback_bars,
        "autostart": runtime.settings.autostart,
        "replay_ws_url": runtime.settings.replay_ws_url,
        "replay_data_type": runtime.settings.replay_data_type,
        "replay_speed": runtime.settings.replay_speed,
        "replay_start_time": runtime.settings.replay_start_time,
        "replay_end_time": runtime.settings.replay_end_time,
    }


if __name__ == "__main__":
    uvicorn.run(
        "services.strategy_runtime.server:app",
        host="0.0.0.0",
        port=8090,
        reload=False,
    )
