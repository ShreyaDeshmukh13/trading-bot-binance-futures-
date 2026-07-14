"""
Order placement logic sitting between the CLI and the API client.

Responsible for:
- turning a validated OrderRequest into the right client.place_order() call
- logging a human-readable summary before and after the call
- translating client-layer exceptions into a single OrderResult the CLI can
  print without needing to know about requests/HTTP/Binance error shapes
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .client import BinanceAPIError, BinanceFuturesClient, BinanceNetworkError
from .validators import OrderRequest

logger = logging.getLogger("trading_bot")


@dataclass
class OrderResult:
    success: bool
    message: str
    order_id: Optional[int] = None
    status: Optional[str] = None
    executed_qty: Optional[str] = None
    avg_price: Optional[str] = None
    raw_response: Optional[dict] = None


class OrderManager:
    def __init__(self, client: BinanceFuturesClient):
        self.client = client

    def summarize_request(self, req: OrderRequest) -> str:
        lines = [
            "Order Request",
            f"  Symbol       : {req.symbol}",
            f"  Side         : {req.side}",
            f"  Type         : {req.order_type}",
            f"  Quantity     : {req.quantity}",
        ]
        if req.price is not None:
            lines.append(f"  Price        : {req.price}")
        if req.stop_price is not None:
            lines.append(f"  Stop Price   : {req.stop_price}")
        if req.order_type in ("LIMIT", "STOP"):
            lines.append(f"  TimeInForce  : {req.time_in_force}")
        return "\n".join(lines)

    def place_order(self, req: OrderRequest) -> OrderResult:
        logger.info("Submitting order: %s", req)

        try:
            response = self.client.place_order(
                symbol=req.symbol,
                side=req.side,
                order_type=req.order_type,
                quantity=req.quantity,
                price=req.price,
                stop_price=req.stop_price,
                time_in_force=req.time_in_force,
            )
        except BinanceAPIError as exc:
            logger.error("Order rejected by Binance: %s", exc)
            return OrderResult(
                success=False,
                message=f"Order rejected by Binance API: {exc} (status {exc.status_code})",
            )
        except BinanceNetworkError as exc:
            logger.error("Order failed due to network/connectivity issue: %s", exc)
            return OrderResult(success=False, message=f"Network error while placing order: {exc}")
        except Exception as exc:  # last-resort safety net; logs full context for debugging
            logger.exception("Unexpected error while placing order.")
            return OrderResult(success=False, message=f"Unexpected error: {exc}")

        return OrderResult(
            success=True,
            message="Order placed successfully.",
            order_id=response.get("orderId"),
            status=response.get("status"),
            executed_qty=response.get("executedQty"),
            avg_price=response.get("avgPrice"),
            raw_response=response,
        )

    def summarize_result(self, result: OrderResult) -> str:
        if not result.success:
            return f"FAILED: {result.message}"

        lines = [
            "Order Response",
            f"  Order ID     : {result.order_id}",
            f"  Status       : {result.status}",
            f"  Executed Qty : {result.executed_qty}",
        ]
        if result.avg_price and result.avg_price != "0":
            lines.append(f"  Avg Price    : {result.avg_price}")
        lines.append("SUCCESS: Order placed.")
        return "\n".join(lines)
