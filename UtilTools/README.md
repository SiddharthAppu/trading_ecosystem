# UtilTools

Utility scripts for Astra workflows.

## TradingView Journal Link Tool

Script: `journal_event_linker.py`

Purpose:
- Parse Astra journal JSONL.
- Build local dashboard chart links per event.
- Build TradingView links per event.
- Export report as Markdown and JSON.

### Usage

```powershell
python .\UtilTools\journal_event_linker.py `
  --journal .\logs\strategy_runtime\runtime_journal.jsonl `
  --output-md .\logs\strategy_runtime\journal_event_links.md `
  --output-json .\logs\strategy_runtime\journal_event_links.json
```

Optional filters:

```powershell
python .\UtilTools\journal_event_linker.py `
  --journal .\logs\strategy_runtime\runtime_journal.jsonl `
  --event ORDER_FILL `
  --symbol NIFTY `
  --limit 500
```

Optional custom symbol mapping file:

```powershell
python .\UtilTools\journal_event_linker.py `
  --journal .\logs\strategy_runtime\runtime_journal.jsonl `
  --symbol-map .\config\strategies\tradingview_symbol_map.json
```

### Notes

- Journal JSONL remains the single source of truth.
- TradingView option symbols can differ by data feed naming; use `tradingview_symbol_map.json` to pin exact mappings for long-term reliability.
