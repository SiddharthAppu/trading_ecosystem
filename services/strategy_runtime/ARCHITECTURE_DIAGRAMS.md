# Strategy Runtime Architecture Diagrams

This file is intentionally diagram-first and rewrite-friendly.

If architecture changes (performance refactors, queueing changes, execution path changes), update only the Mermaid blocks below and keep section titles stable.

## 1) End-to-End Runtime Sequence

```mermaid
sequenceDiagram
    autonumber
    participant L as Launcher/Server
    participant C as RuntimeSettings
    participant R as StrategyRuntime
    participant J as JournalManager
    participant F as Feed
    participant A as trading_core.analytics
    participant S as StrategyImpl
    participant DA as Data Adapter (Upstox)
    participant TA as Trading Adapter (Zerodha)
    participant X as StrategyContext
    participant B as EventBus
    participant E as Executor (Live/Paper)
    participant PM as PortfolioManager
    participant N as Notifier

    L->>C: Load env and create settings
    L->>R: create_runtime(settings)
    R->>DA: Initialize Data Adapter
    R->>TA: Initialize Trading Adapter
    R->>R: Build feed, risk manager, notifier
    R->>PM: Initialize PortfolioManager
    R->>E: Initialize Executor(TA)
    R->>J: Initialize JournalManager
    R->>S: Load strategy via strategies/__init__.py
    R->>S: on_init() and on_start()

    loop Every polling cycle
        R->>F: fetch bars (polling or replay)
        F-->>R: bars (lookback window)
        R->>A: compute_indicator_rows(rows, indicators)
        A-->>R: Indicators calculated on rows
        R->>R: Build MarketSnapshot

        R->>S: evaluate_snapshot(snapshot)
        alt Entry Condition Met
            S->>DA: Resolve option chain (via Data Adapter)
            S->>X: ctx.log_signal(indicator, action)
            X->>B: Publish SignalEvent
            B->>J: log_indicator_signal() (Async)
            S->>X: ctx.buy(symbol, qty, price)
            X->>B: Publish OrderEvent
            B->>R: _on_order_event (Risk Check)
            B->>E: handle_order_event
            E->>TA: place_order()
            E->>B: Publish FillEvent
            B->>R: _on_fill_event
            R->>PM: Update position
            R->>J: log_fill() (Async)
            R->>N: Send fill notification
        end
        
        R->>B: Publish BarEvent and TickEvent
        R->>R: Apply runtime risk exits (SL/TP)
    end

    R->>N: Send runtime stopped notification
```

## 2) Ownership Boundary (strategy_runtime vs trading_core)

```mermaid
flowchart LR
    subgraph SR[services/strategy_runtime]
        Server[server.py]
        Runtime[runtime.py]
        Strategy[strategies/.../strategy.py]
        Exec[executor.py]
        Port[portfolio.py]
        Notify[notifier.py]
        Journal[journal.py]
    end

    subgraph TC[packages/trading_core]
        Providers[providers/* adapters]
        Analytics[analytics/compute_indicator_rows]
        CoreStrategy[strategies.py: Strategy + StrategyContext]
        Events[events bus + EventType]
        Models[models: Bar, Order, Fill, Position]
    end

    Server --> Runtime
    Runtime --> Strategy
    Runtime --> Exec
    Runtime --> Port
    Runtime --> Notify
    Runtime --> Journal

    Runtime --> Analytics
    Runtime --> Providers
    Strategy --> Providers
    Strategy --> CoreStrategy
    Runtime --> CoreStrategy

    Strategy --> Events
    Runtime --> Events
    Exec --> Events
    Journal --> Events

    Runtime --> Models
    Strategy --> Models
```

## 3) Fast Update Checklist

When performance architecture changes, update these first:

1. Feed behavior in Diagram 1 (polling vs replay vs streaming path)
2. Execution path in Diagram 1 (sync/async, queue, batch, retry)
3. Boundary ownership in Diagram 2 (what moved from strategy_runtime to trading_core, or vice versa)
4. Notification path in Diagram 1 (inline vs async worker)

## 4) Suggested Versioning Note (optional)

Add a single line at top when you revise:

- Updated on: YYYY-MM-DD
- Reason: short note (for example: moved indicator compute off main loop)
