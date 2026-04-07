---
trigger: always_on
---

# Options Strategy Logic (Core Rule)
**Activation:** Always On

## Technical Constraints
- **Precision:** Always use the `Decimal` class for strike prices and premiums. Never use floats.
- **Data Source:** Use the Upstox API for historical chain downloads. 
- **Error Handling:** If a symbol is missing in the chain, log it to `error_log.csv` and continue; do not halt the process.

## Calculation Logic
- **Delta:** Use the Black-Scholes model defined in `utils/greeks.py`.
- **Strategy:** This project builds an "Iron Condor" automation. The short strikes should always be 2 standard deviations from the spot price.

## Local Environment
- **Linter:** Always run `ruff check --fix` after editing backend files.
- **Next.js:** Use `node_modules\.bin\next lint` for frontend checks (don't use npx).