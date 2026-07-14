# Trading Bot — Binance Futures Testnet (USDT-M)

A structured CLI application that places MARKET, LIMIT, and STOP-LIMIT
orders on Binance USDT-M Futures Testnet, with input validation, retrying
and rotating logging, a guided interactive mode, and a unit-tested
client/CLI split.

## Contents

- [Project structure](#project-structure)
- [Setup](#setup)
- [Running examples](#running-examples)
- [Testing](#testing)
- [Error handling](#error-handling)
- [Design notes](#design-notes)
- [Assumptions](#assumptions)
- [If I kept extending this](#if-i-kept-extending-this)

## Project structure

```
trading_bot/
  bot/
    __init__.py
    client.py           # Signed REST client for Binance Futures Testnet
    orders.py            # Order placement + request/response summaries
    validators.py         # Input validation, cross-field rules
    logging_config.py     # Rotating file handler + console handler
  cli.py                  # CLI entry point (argparse) — flag mode + interactive mode
  tests/
    test_validators.py    # Validation rules, in isolation
    test_client.py         # Retry/backoff, dry-run, 4xx-vs-5xx handling (mocked HTTP)
    test_orders.py          # OrderManager against a fake client (no network)
  logs/
    trading_bot.log         # Sample log: one MARKET, one LIMIT, one STOP order
  .github/workflows/tests.yml  # CI: runs pytest + dry-run smoke tests on push/PR
  requirements.txt
  requirements-dev.txt
  pyproject.toml
  .env.example
  README.md
```

`client.py` knows nothing about argparse or `print()` — it only talks to
the exchange and raises typed exceptions (`BinanceAPIError`,
`BinanceNetworkError`). `cli.py` decides how to present results. This keeps
the client reusable (e.g. from a scheduled script or a future web UI) and
independently testable, which is why `tests/test_client.py` can fully
exercise retry/backoff behavior without ever hitting the network.

## Setup

1. **Create a Binance Futures Testnet account** at
   https://testnet.binancefuture.com and log in (GitHub login works).
2. **Generate API credentials** from the testnet dashboard (API Key +
   Secret). These are testnet-only keys — no real funds involved.
3. **Install Python 3.9+** and dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Provide credentials** via environment variables or CLI flags:
   ```bash
   cp .env.example .env
   # edit .env with your real testnet key/secret, then:
   export $(grep -v '^#' .env | xargs)     # Linux/macOS
   ```
   or pass them directly with `--api-key` / `--api-secret` on each run.

## Running examples

**Market order:**
```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01
```

**Limit order:**
```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.01 --price 60000
```

**Stop-limit order (bonus: third order type):**
```bash
python cli.py --symbol ETHUSDT --side SELL --type STOP --quantity 0.5 \
    --price 3000 --stop-price 3050
```

**Interactive mode (bonus: enhanced CLI UX)** — prompts for each field,
re-asks on invalid input instead of exiting:
```bash
python cli.py --interactive
python cli.py                    # running with no args also drops into this mode
```

**Dry run** — no credentials or network needed, simulates a realistic
response locally and still writes to the log file. Works with any of the
modes above by adding `--dry-run`:
```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01 --dry-run
```

Add `-y` / `--yes` to skip the confirmation prompt (useful for scripting/CI).

Every run prints:
1. an order request summary (symbol, side, type, quantity, price if applicable)
2. an order response summary (orderId, status, executedQty, avgPrice if available)
3. a clear `SUCCESS:` or `FAILED:` line

All requests, responses, and errors are also logged to `logs/trading_bot.log`
(rotates at 2MB, keeps 5 backups — file gets full DEBUG detail, console
shows INFO and above so normal runs aren't noisy).

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v
```

29 tests cover:
- every validation rule and cross-field constraint (`test_validators.py`)
- retry-with-backoff on connection errors and 5xx responses, *no* retry on
  4xx rejections, dry-run behavior, malformed-response handling
  (`test_client.py`, HTTP fully mocked — no network needed)
- `OrderManager`'s handling of success, `BinanceAPIError`,
  `BinanceNetworkError`, and unexpected exceptions (`test_orders.py`)

CI (`.github/workflows/tests.yml`) runs this matrix across Python 3.9/3.11/3.12
on every push and PR, plus two dry-run smoke tests through the actual CLI
entry point.

## Error handling

Three distinct failure classes, each reported clearly instead of a raw
traceback reaching the user:

- **Invalid input** — caught in `validators.py` before any network call
  (missing price on a LIMIT order, non-numeric quantity, unsupported
  symbol/side/type, etc.). Exits with `Invalid input: ...`.
- **API errors** — Binance responds but rejects the order (bad symbol,
  insufficient testnet balance, filter violations). Surfaced as
  `BinanceAPIError` with the exchange's own message and HTTP status.
  These are **never retried** — a rejected order won't succeed by resending
  it, and retrying could risk an unintended duplicate if the rejection
  reason were transient on Binance's side.
- **Network failures** — timeouts, connection errors, 5xx responses, or
  malformed responses. These **are retried** (up to 3 attempts, exponential
  backoff: 0.5s → 1s → 2s) since they're plausibly transient, then surfaced
  as `BinanceNetworkError` without crashing the CLI.

## Design notes

- Implemented with `requests` + manual HMAC-SHA256 signing rather than the
  `python-binance` SDK, so every request/response is fully visible for
  logging/review and the client stays a small, auditable surface.
- No secrets are ever written to the log file — only order parameters and
  exchange responses.
- Retry policy distinguishes 4xx (our mistake, don't retry) from 5xx/network
  (their/transient problem, retry) rather than retrying everything blindly.
- `OrderManager` and `BinanceFuturesClient` are decoupled via a plain method
  signature (`place_order(...)`), so `tests/test_orders.py` swaps in a
  `FakeClient` with zero mocking framework needed.

## Assumptions

- Scope is limited to USDT-margined pairs (symbols must end in `USDT`),
  per the task's "USDT-M" requirement.
- `STOP` was chosen as the bonus third order type (stop-limit: requires
  both `--price` and `--stop-price`), since it's directly supported by the
  same Futures order endpoint used for MARKET/LIMIT. Interactive mode was
  added as a second bonus item since the task listed it as an independent
  option.
- Order quantities/prices are passed straight through as given; the bot
  does not fetch and enforce Binance's per-symbol `LOT_SIZE`/`PRICE_FILTER`
  exchange rules. In practice, use reasonable testnet values (e.g. small
  BTCUSDT quantities like 0.01) — the exchange itself rejects values outside
  its filters, surfaced as a `BinanceAPIError`.
- Default `timeInForce` for LIMIT/STOP orders is `GTC`, overridable with
  `--time-in-force`.
- **`logs/trading_bot.log` in this repo was generated using `--dry-run`
  mode** (no live credentials were available in the environment this was
  built in). Dry-run produces the same log structure as a real order, minus
  the actual HTTP round trip. Before submitting, re-run the MARKET and
  LIMIT examples above with your own testnet credentials (drop `--dry-run`)
  so the submitted log reflects real testnet responses — the task asks for
  genuine order logs, and passing off simulated ones as real would misrepresent
  what was tested.

## If I kept extending this

Left out to keep the task inside its 60-minute scope, but the natural next
steps: fetch `/fapi/v1/exchangeInfo` once at startup to validate
quantity/price against each symbol's real `LOT_SIZE`/`PRICE_FILTER` instead
of just checking `> 0`; add an `order_history.json`/SQLite record of
submitted orders for reconciliation; add OCO order support; and swap the
`--dry-run` mock responses for a recorded-fixture replay so integration
tests can assert against real historical Binance response shapes.
