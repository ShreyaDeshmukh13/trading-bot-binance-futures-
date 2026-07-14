"""
Thin, explicit wrapper around the Binance USDT-M Futures REST API
(Testnet: https://testnet.binancefuture.com).

Implemented with `requests` + manual HMAC-SHA256 signing rather than the
python-binance SDK, so every request/response is fully visible for logging
and easy to reason about in a review.

This module knows nothing about argparse or print() - it only talks to the
exchange and raises typed exceptions. The CLI layer (cli.py) is responsible
for presentation.
"""

import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger("trading_bot")

DEFAULT_BASE_URL = "https://testnet.binancefuture.com"
ORDER_ENDPOINT = "/fapi/v1/order"
ACCOUNT_ENDPOINT = "/fapi/v2/account"
RECV_WINDOW_MS = 5000
REQUEST_TIMEOUT_S = 10

# Retry policy for transient failures only (timeouts, connection errors, 5xx).
# 4xx errors (bad request, invalid symbol, etc.) are never retried - retrying
# a rejected order would risk duplicate submissions for a mistake that
# retrying can't fix.
MAX_RETRIES = 3
BACKOFF_BASE_S = 0.5


class BinanceAPIError(Exception):
    """Raised when Binance returns a well-formed error response (4xx/5xx with JSON body)."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class BinanceNetworkError(Exception):
    """Raised for connection failures, timeouts, or malformed (non-JSON) responses."""


class BinanceFuturesClient:
    """
    Minimal signed REST client for Binance USDT-M Futures.

    Parameters
    ----------
    api_key, api_secret : str
        Testnet API credentials. Not required when dry_run=True.
    base_url : str
        Defaults to the Futures Testnet base URL.
    dry_run : bool
        If True, no network calls are made. Instead, a realistic mock
        response is generated locally. Useful for demoing/logging without
        live credentials, and for keeping the CLI testable offline.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        dry_run: bool = False,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.session = session or requests.Session()

        if not dry_run and (not api_key or not api_secret):
            raise ValueError("api_key and api_secret are required unless dry_run=True.")

    # -- internal helpers ---------------------------------------------------

    def _sign(self, params: Dict[str, Any]) -> str:
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query_string}&signature={signature}"

    def _redact(self, params: dict) -> dict:
        """Return a copy of params safe to write to logs (no secrets to begin with,
        but keeps this in one place in case sensitive fields are added later)."""
        return dict(params)

    def _signed_request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> dict:
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW_MS

        url = f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key}
        query_string = self._sign(params)
        full_url = f"{url}?{query_string}"

        logger.debug("REQUEST %s %s | params=%s", method, path, self._redact(params))

        response = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.request(method, full_url, headers=headers, timeout=REQUEST_TIMEOUT_S)
            except requests.exceptions.RequestException as exc:
                logger.warning(
                    "NETWORK ERROR on %s %s (attempt %d/%d): %s", method, path, attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue
                logger.error("NETWORK ERROR on %s %s: giving up after %d attempts", method, path, MAX_RETRIES)
                raise BinanceNetworkError(f"Network error calling {path} after {MAX_RETRIES} attempts: {exc}") from exc

            # Retry on 5xx (exchange-side transient issue); never retry 4xx (our request was rejected).
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                logger.warning(
                    "SERVER ERROR %s %s | status=%s (attempt %d/%d) - retrying",
                    method, path, response.status_code, attempt, MAX_RETRIES,
                )
                time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                continue

            break

        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "MALFORMED RESPONSE on %s %s: status=%s body=%s",
                method, path, response.status_code, response.text[:500],
            )
            raise BinanceNetworkError(f"Non-JSON response from {path} (status {response.status_code})") from exc

        if response.status_code >= 400:
            logger.error("API ERROR %s %s | status=%s | response=%s", method, path, response.status_code, data)
            raise BinanceAPIError(
                message=data.get("msg", "Unknown Binance API error"),
                status_code=response.status_code,
                payload=data,
            )

        logger.info("RESPONSE %s %s | status=%s | response=%s", method, path, response.status_code, data)
        return data

    # -- mock path for --dry-run --------------------------------------------

    def _mock_order_response(self, params: dict) -> dict:
        now_ms = int(time.time() * 1000)
        order_type = params["type"]
        price = params.get("price")
        is_market = order_type == "MARKET"

        mock = {
            "orderId": int(now_ms % 1_000_000_000),
            "symbol": params["symbol"],
            "status": "FILLED" if is_market else "NEW",
            "clientOrderId": f"dryrun_{now_ms}",
            "price": price or "0",
            "avgPrice": price or "0" if is_market else "0",
            "origQty": params["quantity"],
            "executedQty": params["quantity"] if is_market else "0",
            "side": params["side"],
            "type": order_type,
            "timeInForce": params.get("timeInForce", "GTC"),
            "updateTime": now_ms,
        }
        logger.info("DRY-RUN RESPONSE (no network call) | request=%s | mock_response=%s", self._redact(params), mock)
        return mock

    # -- public API -----------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "GTC",
    ) -> dict:
        """
        Place an order on Binance USDT-M Futures (or simulate it, if dry_run).

        order_type: "MARKET" | "LIMIT" | "STOP"
        """
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }

        if order_type == "LIMIT":
            params["price"] = price
            params["timeInForce"] = time_in_force
        elif order_type == "STOP":
            params["price"] = price
            params["stopPrice"] = stop_price
            params["timeInForce"] = time_in_force
        # MARKET orders take symbol/side/type/quantity only.

        if self.dry_run:
            return self._mock_order_response(params)

        return self._signed_request("POST", ORDER_ENDPOINT, params)

    def get_account_info(self) -> dict:
        """Fetch futures account info. Useful for a pre-flight balance check."""
        if self.dry_run:
            mock = {"totalWalletBalance": "10000.00000000", "availableBalance": "10000.00000000"}
            logger.info("DRY-RUN RESPONSE (no network call) | account_info=%s", mock)
            return mock
        return self._signed_request("GET", ACCOUNT_ENDPOINT)
