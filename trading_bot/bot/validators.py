"""
Input validation for order requests.

Kept separate from the CLI and the API client so validation rules can be
unit-tested in isolation and reused (e.g. by a future web/UI layer).
"""

from dataclasses import dataclass
from typing import Optional

VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP"}  # STOP = bonus stop-limit order


class ValidationError(Exception):
    """Raised when user-supplied order parameters fail validation."""


@dataclass
class OrderRequest:
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"


def validate_symbol(symbol: str) -> str:
    if not symbol or not symbol.strip():
        raise ValidationError("Symbol cannot be empty.")
    symbol = symbol.strip().upper()
    if not symbol.isalnum():
        raise ValidationError(f"Symbol '{symbol}' looks invalid (expected e.g. BTCUSDT).")
    if not symbol.endswith("USDT"):
        # Not a hard Binance rule, but this bot targets USDT-M futures per spec.
        raise ValidationError(f"Symbol '{symbol}' must be a USDT-margined pair (e.g. BTCUSDT).")
    return symbol


def validate_side(side: str) -> str:
    side = (side or "").strip().upper()
    if side not in VALID_SIDES:
        raise ValidationError(f"Side must be one of {sorted(VALID_SIDES)}, got '{side}'.")
    return side


def validate_order_type(order_type: str) -> str:
    order_type = (order_type or "").strip().upper()
    if order_type not in VALID_ORDER_TYPES:
        raise ValidationError(
            f"Order type must be one of {sorted(VALID_ORDER_TYPES)}, got '{order_type}'."
        )
    return order_type


def validate_quantity(quantity) -> float:
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise ValidationError(f"Quantity must be a number, got '{quantity}'.")
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than 0.")
    return quantity


def validate_price(price, field_name: str = "price") -> float:
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name.capitalize()} must be a number, got '{price}'.")
    if price <= 0:
        raise ValidationError(f"{field_name.capitalize()} must be greater than 0.")
    return price


def build_order_request(
    symbol: str,
    side: str,
    order_type: str,
    quantity,
    price=None,
    stop_price=None,
    time_in_force: str = "GTC",
) -> OrderRequest:
    """
    Validate all fields together (including cross-field rules) and return
    a clean OrderRequest, or raise ValidationError with a clear message.
    """
    symbol = validate_symbol(symbol)
    side = validate_side(side)
    order_type = validate_order_type(order_type)
    quantity = validate_quantity(quantity)

    if order_type == "LIMIT":
        if price is None:
            raise ValidationError("Price is required for LIMIT orders.")
        price = validate_price(price)

    if order_type == "STOP":
        if price is None or stop_price is None:
            raise ValidationError("Both --price and --stop-price are required for STOP orders.")
        price = validate_price(price)
        stop_price = validate_price(stop_price, field_name="stop price")

    if order_type == "MARKET" and price is not None:
        raise ValidationError("Price should not be provided for MARKET orders.")

    return OrderRequest(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        time_in_force=time_in_force,
    )
