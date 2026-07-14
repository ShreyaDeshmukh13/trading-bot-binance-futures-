import json
from unittest.mock import MagicMock

import pytest

from bot.client import BinanceAPIError, BinanceFuturesClient, BinanceNetworkError
import requests


def _mock_response(status_code=200, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = json.dumps(json_body or {})
    return resp


def test_dry_run_market_order_no_network_call():
    client = BinanceFuturesClient(dry_run=True)
    result = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01)
    assert result["status"] == "FILLED"
    assert result["executedQty"] == 0.01
    assert result["symbol"] == "BTCUSDT"


def test_dry_run_limit_order_status_new():
    client = BinanceFuturesClient(dry_run=True)
    result = client.place_order(symbol="BTCUSDT", side="SELL", order_type="LIMIT", quantity=0.01, price=60000)
    assert result["status"] == "NEW"
    assert result["price"] == 60000


def test_real_client_requires_credentials():
    with pytest.raises(ValueError):
        BinanceFuturesClient(dry_run=False)


def test_successful_order_hits_session_once():
    session = MagicMock()
    session.request.return_value = _mock_response(200, {"orderId": 1, "status": "FILLED"})
    client = BinanceFuturesClient(api_key="k", api_secret="s", session=session)

    result = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01)

    assert result["orderId"] == 1
    assert session.request.call_count == 1


def test_4xx_error_is_not_retried():
    session = MagicMock()
    session.request.return_value = _mock_response(400, {"code": -1121, "msg": "Invalid symbol."})
    client = BinanceFuturesClient(api_key="k", api_secret="s", session=session)

    with pytest.raises(BinanceAPIError) as exc_info:
        client.place_order(symbol="BADSYM", side="BUY", order_type="MARKET", quantity=0.01)

    assert exc_info.value.status_code == 400
    assert session.request.call_count == 1  # no retry on client errors


def test_5xx_error_is_retried_then_succeeds():
    session = MagicMock()
    session.request.side_effect = [
        _mock_response(503, {"msg": "Service unavailable"}),
        _mock_response(200, {"orderId": 42, "status": "FILLED"}),
    ]
    client = BinanceFuturesClient(api_key="k", api_secret="s", session=session)

    result = client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01)

    assert result["orderId"] == 42
    assert session.request.call_count == 2


def test_connection_error_is_retried_then_raises_after_max_attempts():
    session = MagicMock()
    session.request.side_effect = requests.exceptions.ConnectionError("boom")
    client = BinanceFuturesClient(api_key="k", api_secret="s", session=session)

    with pytest.raises(BinanceNetworkError):
        client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01)

    assert session.request.call_count == 3  # MAX_RETRIES


def test_malformed_json_response_raises_network_error():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("not json")
    resp.text = "<html>not json</html>"
    session.request.return_value = resp
    client = BinanceFuturesClient(api_key="k", api_secret="s", session=session)

    with pytest.raises(BinanceNetworkError):
        client.place_order(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01)
