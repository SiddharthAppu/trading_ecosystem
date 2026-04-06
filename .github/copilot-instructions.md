# Project Guidelines

## Code Style
- Keep changes minimal and localized; do not refactor unrelated modules.
- Python services and trading core are async-first. Prefer non-blocking I/O and avoid blocking calls in event handlers.
- Keep domain models and shared abstractions in packages/trading_core, not duplicated inside services.
- Frontend code in apps/forge_dashboard and apps/historical_dashboard uses TypeScript + Next.js App Router. Prefer typed API helpers and shared interfaces from src/lib/types.ts.

## Architecture
- apps/: Next.js dashboards (historical_dashboard on port 3000, forge_dashboard on port 3001).
- services/: backend runtime services.
- services/data_collector: FastAPI API (port 8080).
- services/replay_engine: WebSocket replay server (port 8765).
- services/execution_engine: strategy orchestration and portfolio flow.
- packages/trading_core: shared events, models, provider adapters, config, and DB access.
- config/: central .env and auth token files consumed by services and trading_core.

See RESOURCES.md for high-level architecture and operational context.

## Build And Test
- Frontend install: run npm install inside each dashboard app.
- Frontend dev:
  - apps/historical_dashboard: npm run dev
  - apps/forge_dashboard: npm run dev
- Frontend quality checks:
  - npm run lint
  - npm run build
- Python core package install: from packages/trading_core run pip install -e .
- Service run commands:
  - services/data_collector: python main.py
  - services/replay_engine: python main.py
  - services/execution_engine: python main.py
- There are currently no automated tests in this repo. Validate changes with targeted manual checks.

## Conventions
- Event-driven flow is the primary backend integration model.
  - Publish via trading_core.events.bus.publish(...)
  - Subscribe via bus.subscribe(EventType..., handler)
- Broker/provider access must go through trading_core.providers.get_adapter(...). Do not instantiate provider adapters ad hoc in services.
- Keep API and WebSocket endpoints configurable with NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL in frontend code.
- Prefer extending existing abstractions:
  - strategies inherit trading_core.strategies.Strategy
  - shared entities are dataclasses in trading_core.models
- Use central config loading from trading_core.config; do not add duplicate per-service env loaders unless required.

## Known Pitfalls
- start_platform.bat and scripts/start_collector_service.bat currently reference consolidated_platform paths, which do not exist in this workspace root. Fix script paths before relying on one-click startup.
- data_collector runs on port 8080, while forge_dashboard defaults API/WS URLs to port 8000 in src/lib/api.ts and src/lib/websocket.ts. Set NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL explicitly during local runs.
- Ensure config/.env and required auth token files under config/auth exist before running provider-dependent flows.
- EventBus handler errors are printed and swallowed; add explicit error handling/logging in strategy and service handlers.

## Documentation Links
- Operational architecture and quick verification: RESOURCES.md
- Frontend app commands and framework details:
  - apps/forge_dashboard/README.md
  - apps/historical_dashboard/README.md
