import pytest

from bot.validators import ValidationError, build_order_request


def test_valid_market_order():
    req = build_order_request("btcusdt", "buy", "market", "0.01")
    assert req.symbol == "BTCUSDT"
    assert req.side == "BUY"
    assert req.order_type == "MARKET"
    assert req.quantity == 0.01
    assert req.price is None


def test_valid_limit_order():
    req = build_order_request("BTCUSDT", "SELL", "LIMIT", "0.01", price="60000")
    assert req.order_type == "LIMIT"
    assert req.price == 60000.0


def test_valid_stop_order():
    req = build_order_request("ETHUSDT", "SELL", "STOP", "0.5", price="3000", stop_price="3050")
    assert req.price == 3000.0
    assert req.stop_price == 3050.0


def test_limit_order_missing_price_raises():
    with pytest.raises(ValidationError, match="Price is required"):
        build_order_request("BTCUSDT", "BUY", "LIMIT", "0.01")


def test_stop_order_missing_stop_price_raises():
    with pytest.raises(ValidationError, match="stop-price"):
        build_order_request("BTCUSDT", "BUY", "STOP", "0.01", price="60000")


def test_market_order_with_price_raises():
    with pytest.raises(ValidationError, match="should not be provided"):
        build_order_request("BTCUSDT", "BUY", "MARKET", "0.01", price="60000")


def test_invalid_side_raises():
    with pytest.raises(ValidationError, match="Side must be"):
        build_order_request("BTCUSDT", "HOLD", "MARKET", "0.01")


def test_invalid_order_type_raises():
    with pytest.raises(ValidationError, match="Order type must be"):
        build_order_request("BTCUSDT", "BUY", "TWAP", "0.01")


def test_non_usdt_symbol_raises():
    with pytest.raises(ValidationError, match="USDT-margined"):
        build_order_request("BTCBUSD", "BUY", "MARKET", "0.01")


def test_empty_symbol_raises():
    with pytest.raises(ValidationError, match="cannot be empty"):
        build_order_request("", "BUY", "MARKET", "0.01")


def test_negative_quantity_raises():
    with pytest.raises(ValidationError, match="greater than 0"):
        build_order_request("BTCUSDT", "BUY", "MARKET", "-1")


def test_zero_quantity_raises():
    with pytest.raises(ValidationError, match="greater than 0"):
        build_order_request("BTCUSDT", "BUY", "MARKET", "0")


def test_non_numeric_quantity_raises():
    with pytest.raises(ValidationError, match="must be a number"):
        build_order_request("BTCUSDT", "BUY", "MARKET", "abc")


def test_non_numeric_price_raises():
    with pytest.raises(ValidationError, match="must be a number"):
        build_order_request("BTCUSDT", "BUY", "LIMIT", "0.01", price="cheap")


def test_negative_price_raises():
    with pytest.raises(ValidationError, match="greater than 0"):
        build_order_request("BTCUSDT", "BUY", "LIMIT", "0.01", price="-100")
