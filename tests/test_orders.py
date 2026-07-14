from bot.client import BinanceAPIError, BinanceNetworkError
from bot.orders import OrderManager
from bot.validators import build_order_request


class FakeClient:
    """Stand-in for BinanceFuturesClient so OrderManager can be tested without network."""

    def __init__(self, response=None, raise_exc=None):
        self.response = response
        self.raise_exc = raise_exc
        self.last_call_kwargs = None

    def place_order(self, **kwargs):
        self.last_call_kwargs = kwargs
        if self.raise_exc:
            raise self.raise_exc
        return self.response


def test_place_order_success():
    fake_response = {
        "orderId": 12345,
        "status": "FILLED",
        "executedQty": "0.01",
        "avgPrice": "60000.00",
    }
    client = FakeClient(response=fake_response)
    manager = OrderManager(client)
    req = build_order_request("BTCUSDT", "BUY", "MARKET", "0.01")

    result = manager.place_order(req)

    assert result.success is True
    assert result.order_id == 12345
    assert result.status == "FILLED"
    assert result.executed_qty == "0.01"
    assert client.last_call_kwargs["symbol"] == "BTCUSDT"
    assert client.last_call_kwargs["side"] == "BUY"


def test_place_order_api_error_is_caught():
    client = FakeClient(raise_exc=BinanceAPIError("Invalid symbol.", status_code=400))
    manager = OrderManager(client)
    req = build_order_request("BTCUSDT", "BUY", "MARKET", "0.01")

    result = manager.place_order(req)

    assert result.success is False
    assert "rejected by Binance API" in result.message
    assert "Invalid symbol" in result.message


def test_place_order_network_error_is_caught():
    client = FakeClient(raise_exc=BinanceNetworkError("Connection timed out"))
    manager = OrderManager(client)
    req = build_order_request("BTCUSDT", "BUY", "MARKET", "0.01")

    result = manager.place_order(req)

    assert result.success is False
    assert "Network error" in result.message


def test_place_order_unexpected_error_is_caught_not_raised():
    client = FakeClient(raise_exc=RuntimeError("something exploded"))
    manager = OrderManager(client)
    req = build_order_request("BTCUSDT", "BUY", "MARKET", "0.01")

    result = manager.place_order(req)  # must not raise

    assert result.success is False
    assert "Unexpected error" in result.message


def test_summarize_request_includes_price_for_limit():
    manager = OrderManager(FakeClient())
    req = build_order_request("BTCUSDT", "SELL", "LIMIT", "0.01", price="60000")
    summary = manager.summarize_request(req)
    assert "LIMIT" in summary
    assert "60000" in summary


def test_summarize_result_failure_message():
    manager = OrderManager(FakeClient())
    from bot.orders import OrderResult

    result = OrderResult(success=False, message="Order rejected by Binance API: bad symbol")
    summary = manager.summarize_result(result)
    assert summary.startswith("FAILED:")
