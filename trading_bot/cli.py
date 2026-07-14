#!/usr/bin/env python3
"""
CLI entry point for the simplified Binance Futures Testnet trading bot.

Examples
--------
Market order:
    python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01

Limit order:
    python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.01 --price 60000

Stop-limit order (bonus):
    python cli.py --symbol BTCUSDT --side SELL --type STOP --quantity 0.01 \\
        --price 58000 --stop-price 58500

Dry run (no real API calls / no credentials needed, still logs to file):
    python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01 --dry-run

Interactive mode (guided prompts, re-asks on invalid input):
    python cli.py --interactive
    python cli.py                    # also drops into interactive mode with no args
"""

import argparse
import os
import sys
from typing import Optional

from bot.client import BinanceFuturesClient
from bot.logging_config import setup_logging
from bot.orders import OrderManager
from bot.validators import (
    ValidationError,
    build_order_request,
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_symbol,
)

DEFAULT_BASE_URL = "https://testnet.binancefuture.com"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place MARKET, LIMIT, or STOP orders on Binance Futures Testnet (USDT-M).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Note: symbol/side/type/quantity are NOT marked required=True at the argparse
    # level, because --interactive mode (and running with no args at all) collects
    # them via prompts instead. main() enforces they're present for flag-driven mode.
    parser.add_argument("--symbol", help="Trading pair, e.g. BTCUSDT")
    parser.add_argument("--side", choices=["BUY", "SELL", "buy", "sell"], help="Order side")
    parser.add_argument(
        "--type",
        dest="order_type",
        choices=["MARKET", "LIMIT", "STOP", "market", "limit", "stop"],
        help="Order type",
    )
    parser.add_argument("--quantity", help="Order quantity, e.g. 0.01")
    parser.add_argument("--price", help="Limit/stop order price (required for LIMIT and STOP)")
    parser.add_argument("--stop-price", dest="stop_price", help="Trigger price (required for STOP)")
    parser.add_argument(
        "--time-in-force",
        dest="time_in_force",
        default="GTC",
        choices=["GTC", "IOC", "FOK"],
        help="Time in force for LIMIT/STOP orders (default: GTC)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("BINANCE_API_KEY"),
        help="Binance Testnet API key (or set BINANCE_API_KEY env var)",
    )
    parser.add_argument(
        "--api-secret",
        default=os.environ.get("BINANCE_API_SECRET"),
        help="Binance Testnet API secret (or set BINANCE_API_SECRET env var)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (default: Futures Testnet)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the order locally without calling Binance or needing API credentials.",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Guided prompt mode: asks for each field one at a time and re-asks on invalid input.",
    )

    return parser.parse_args(argv)


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def _prompt_until_valid(prompt: str, validator, default: Optional[str] = None):
    """Ask the user for a field, showing the validator's error and re-asking
    on invalid input instead of crashing or exiting (enhanced CLI UX)."""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            raw = default
        try:
            return validator(raw)
        except ValidationError as exc:
            print(f"  ! {exc} Try again.")


def run_interactive(args: argparse.Namespace) -> int:
    """Guided mode: prompts for each field one at a time, re-asking on bad input.
    This is the enhanced-CLI-UX bonus item — useful for a first-time user who
    doesn't want to memorize flag names."""
    print("=== Binance Futures Testnet Trading Bot — Interactive Mode ===")
    print("(Press Ctrl+C at any time to cancel)\n")

    symbol = _prompt_until_valid("Symbol (e.g. BTCUSDT)", validate_symbol)
    side = _prompt_until_valid("Side (BUY/SELL)", validate_side)
    order_type = _prompt_until_valid("Order type (MARKET/LIMIT/STOP)", validate_order_type)

    quantity = _prompt_until_valid("Quantity (e.g. 0.01)", validate_quantity)

    price = None
    stop_price = None
    if order_type in ("LIMIT", "STOP"):
        price = _prompt_until_valid("Price", lambda v: validate_price(v))
    if order_type == "STOP":
        stop_price = _prompt_until_valid("Stop (trigger) price", lambda v: validate_price(v, "stop price"))

    time_in_force = args.time_in_force or "GTC"

    order_req = build_order_request(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        time_in_force=time_in_force,
    )

    dry_run = args.dry_run
    if not dry_run and (not args.api_key or not args.api_secret):
        print(
            "\nNo API credentials found (env vars or --api-key/--api-secret). "
            "Falling back to --dry-run so you can still see the flow."
        )
        dry_run = True

    print()
    return _submit_order(order_req, args, dry_run, skip_confirm=args.yes)


def _submit_order(order_req, args: argparse.Namespace, dry_run: bool, skip_confirm: bool) -> int:
    """Shared path used by both flag-driven and interactive mode: build the
    client, show the summary, confirm, submit, print the result."""
    logger = setup_logging()

    if not dry_run and (not args.api_key or not args.api_secret):
        print(
            "No API credentials found. Pass --api-key/--api-secret, set "
            "BINANCE_API_KEY/BINANCE_API_SECRET env vars, or use --dry-run to test without them."
        )
        return 2

    try:
        client = BinanceFuturesClient(
            api_key=args.api_key,
            api_secret=args.api_secret,
            base_url=args.base_url,
            dry_run=dry_run,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    manager = OrderManager(client)

    print(manager.summarize_request(order_req))
    if dry_run:
        print("(DRY RUN — no real order will be sent)")

    if not skip_confirm and not confirm("Submit this order?"):
        print("Cancelled.")
        logger.info("Order cancelled by user before submission: %s", order_req)
        return 0

    result = manager.place_order(order_req)
    print(manager.summarize_result(result))

    return 0 if result.success else 1


def main(argv=None) -> int:
    args = parse_args(argv)

    # Drop into interactive mode either explicitly (--interactive) or when the
    # user ran the script with no arguments at all (friendlier than argparse's
    # default "the following arguments are required" error on a first run).
    if args.interactive or argv == []:
        try:
            return run_interactive(args)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 0

    missing = [
        name
        for name, val in [("--symbol", args.symbol), ("--side", args.side),
                           ("--type", args.order_type), ("--quantity", args.quantity)]
        if not val
    ]
    if missing:
        print(f"Missing required arguments: {', '.join(missing)}")
        print("(Tip: run with --interactive for guided prompts instead.)")
        return 2

    # Normalize case for choice fields the user may have typed lowercase.
    side = args.side.upper()
    order_type = args.order_type.upper()

    logger = setup_logging()
    try:
        order_req = build_order_request(
            symbol=args.symbol,
            side=side,
            order_type=order_type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
            time_in_force=args.time_in_force,
        )
    except ValidationError as exc:
        logger.error("Validation failed: %s", exc)
        print(f"Invalid input: {exc}")
        return 2

    return _submit_order(order_req, args, dry_run=args.dry_run, skip_confirm=args.yes)


if __name__ == "__main__":
    # sys.argv[1:] gives [] when run with zero arguments, which triggers interactive mode.
    sys.exit(main(sys.argv[1:]))
