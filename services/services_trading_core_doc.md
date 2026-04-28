# Trading Ecosystem Services & Core Documentation

This document outlines the architecture, roles, and components of the core microservices (located in the `services/` directory) and the shared foundation package (`packages/trading_core/`). Together, these form the backbone of the unified trading platform.

---

## PART I: Core Package (`packages/trading_core`)

**Role**: A shared, provider-neutral foundation library. It encapsulates all cross-cutting concerns, ensuring that microservices don't duplicate code and remain loosely coupled.

### Key Components
*   **`providers/`**: The broker adapter layer. It enforces a standard interface (`base.py`) across different brokers (`fyers_adapter.py`, `upstox_adapter.py`, `upstox_historical.py`). Services interact with this layer instead of specific broker APIs.
*   **`analytics/`**: Centralized mathematical and quantitative logic (e.g., Black-Scholes options pricing, Greeks calculations, indicator math).
*   **`db/`**: Handles asynchronous connection pooling (`DatabaseManager`) and schema migrations (`migrations.py`) for TimescaleDB.
*   **`events.py`**: An internal Event Bus used to decouple components. Enables broadcasting of `TickEvent`, `OrderEvent`, etc., across the system.
*   **`models.py`**: Shared dataclasses and Pydantic schemas (e.g., `Tick`, `Order`) for strict type enforcement across service boundaries.
*   **`strategies.py`**: Defines the base `Strategy` class and `StrategyContext` which custom trading algorithms inherit from.
*   **`symbols/`**: Logic for token resolution and symbol formatting across different broker formats.
*   **`auth.py`**: Centralized token management and validation for broker APIs.

---

## PART II: Microservices (`services/`)

### 1. Data Collector (`services/data_collector`)

**Role**: The primary ingestion engine and central API for market data and broker interactions.
**How it starts**: Launched via `start_platform.bat` (FastAPI running on port `8080`).

#### Components
*   `main.py`: The FastAPI web server exposing endpoints for:
    *   Broker Authentication status/URL generation.
    *   Live Recorder control (`/recorder/start`, `/recorder/stop`).
    *   Data queries (`/db/overview`, `/index-ticks/recent`, etc.).
*   `live_recorder.py`: Manages real-time WebSocket connections to brokers (Fyers/Upstox) to collect live ticks and option chains.
*   **Scripts (`services/data_collector/scripts/`)**: Standalone batch processing scripts used for downloading, auditing, and patching historical data (especially for Upstox).
    *   `upstox_options_sync.py` & `run_upstox_options_sync_all_days.py`: Core historical download pipeline.
    *   `audit_upstox_options.py` & `repair_upstox_keys.py`: Utility scripts for data integrity and patching gaps.

#### Extension Ideas
*   **Webhooks**: Add endpoints to receive order execution updates directly from brokers.
*   **Scheduling**: Integrate a task scheduler (like Celery or APScheduler) directly into the API to trigger `upstox_options_sync.py` automatically at EOD without external cron jobs.

---

### 2. Replay Engine (`services/replay_engine`)

**Role**: A mock live-data feed that reads historical data from TimescaleDB and streams it to clients/strategies as if it were happening in real-time.
**How it starts**: Launched via `start_platform.bat` (WebSocket on port `8765`, HTTP on port `8766`).

#### Components
*   `main.py`: Contains both the WebSocket streaming logic and an HTTP endpoint (`/replay/load`).
*   **Features**: Strictly acts as a raw historical data pump with on-the-fly timeframe aggregation (e.g., converting 1m to 5m/10m) powered by TimescaleDB `time_bucket`. All indicator and strategy logic has been explicitly removed from the server layer to maintain a clean architecture.

#### Extension Ideas
*   **Event Bus Integration**: Instead of just sending data over a raw WebSocket to the UI, it could publish ticks directly to the `trading_core.events` event bus, allowing strategies to seamlessly switch between "Live" and "Replay" modes without changing their ingestion logic.

---



### 3. Strategy Runtime (`services/strategy_runtime`)

**Role**: An advanced, robust framework for deploying and managing live trading strategies.
**How it starts**: **Not currently launched** by `start_platform.bat`.

#### Components
*   `main.py`, `bootstrap.py`, `config.py`, `runtime.py`, `server.py`, `notifier.py`: A fully structured environment with logging, settings management, and strategy lifecycle hooks.
*   `strategies/`: Directory for housing specific algorithm implementations.

---

## PART III: Lightweight Cloud Architecture

This architecture is designed for low-latency, low-cost execution on cloud environments (e.g., VPS, Lambda, or lightweight containers) where a persistent TimescaleDB might be too heavy or expensive.

### 1. Data Collection (Tick-to-File)
*   **Mechanism**: `LiveTickRecorder` is configured in `FILE_ONLY` mode.
*   **Output**: Ticks and Greeks are appended to a date-stamped text file (e.g., `logs/ticks/NIFTY_2026-04-27.csv`).
*   **Benefit**: Zero DB latency during the trading session and high portability.

### 2. Strategy Execution (Journaled Orders)
*   **Journaling**: Every order placement, modification, and fill is logged to `logs/journal.jsonl`.
*   **State Management**: The runtime can recover its current position state by replaying the day's `journal.jsonl` upon restart.
*   **Notifications**: Critical events (Execution, Risk Rejections) are pushed to Telegram via `notifier.py`.

### 3. EOD Local Sync
*   **Workflow**: At the end of the trading day, the cloud files (`ticks.csv` and `journal.jsonl`) are downloaded to the local desktop.
*   **Ingestion**: A local utility script parses these files and performs a bulk `INSERT` into the main TimescaleDB `market_ticks` and `orders` tables.

---

## Analysis & Redundancies

### 1. Unified Strategy Host
*Resolved*: Previously, there was redundancy between a legacy `execution_engine` and `strategy_runtime`. The `execution_engine` has been officially deprecated and completely removed. The `strategy_runtime` is now the definitive host for all algorithm execution and paper-trading moving forward.

### 2. Standalone Scripts in `data_collector`
The historical sync scripts currently reside inside the `data_collector/scripts` folder. While related to data collection, they are executed manually or via separate scheduled tasks. They operate independently of the FastAPI server. This isn't strictly redundant, but keeping heavy batch scripts separate from the real-time API codebase might be cleaner if they grow further.

### 3. Indicator Calculation Logic
*Resolved*: Previously, `replay_engine` calculated technical indicators via pure Python. This has been removed. The server is strictly a raw data pump, and any indicator math is deferred to the client UI or the `trading_core/analytics` module.
