import os
import time
import json
import logging
import base64
import aiohttp
from typing import Optional, Dict, Any, Tuple
from payments.base import BasePaymentGateway
import config

logger = logging.getLogger(__name__)

class PayPalGateway(BasePaymentGateway):
    """
    PayPal Payment Gateway Integration (REST API v2)
    - Supports dynamic PayPal checkout order creation with 5% merchant surcharge
    - Supports instant checkout with PayPal balance, Credit & Debit Cards
    - Handles OAuth2 Token caching & auto-refresh
    - Handles status check & payment capture
    """

    def __init__(self):
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def client_id(self) -> str:
        val = os.getenv("PAYPAL_CLIENT_ID") or getattr(config, "PAYPAL_CLIENT_ID", "")
        return str(val).strip('"\' ')

    @property
    def client_secret(self) -> str:
        val = os.getenv("PAYPAL_CLIENT_SECRET") or getattr(config, "PAYPAL_CLIENT_SECRET", "")
        return str(val).strip('"\' ')

    @property
    def mode(self) -> str:
        val = os.getenv("PAYPAL_MODE") or getattr(config, "PAYPAL_MODE", "LIVE")
        return str(val).strip('"\' ').upper()

    @property
    def currency(self) -> str:
        val = os.getenv("PAYPAL_CURRENCY") or getattr(config, "PAYPAL_CURRENCY", "USD")
        return str(val).strip('"\' ').upper()

    @property
    def usd_rate(self) -> float:
        return float(os.getenv("PAYPAL_USD_TO_INR_RATE") or getattr(config, "PAYPAL_USD_TO_INR_RATE", 90.0))

    @property
    def surcharge_percent(self) -> float:
        return float(os.getenv("PAYPAL_SURCHARGE_PERCENT") or getattr(config, "PAYPAL_SURCHARGE_PERCENT", 0.0))

    @property
    def base_url(self) -> str:
        if self.mode == "LIVE":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def get_access_token(self) -> Optional[str]:
        """
        Retrieves or refreshes the PayPal OAuth2 Bearer Access Token.
        """
        now = time.time()
        if self._cached_token and now < self._token_expires_at - 60:
            return self._cached_token

        if not self.is_configured:
            logger.error("PayPal credentials are not configured in environment.")
            return None

        url = f"{self.base_url}/v1/oauth2/token"
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        res = await response.json()
                        token = res.get("access_token")
                        expires_in = res.get("expires_in", 3600)
                        self._cached_token = token
                        self._token_expires_at = now + expires_in
                        return token
                    else:
                        res_text = await response.text()
                        logger.error(f"Failed to obtain PayPal OAuth token: {response.status} - {res_text}")
                        return None
        except Exception as e:
            logger.error(f"Exception while obtaining PayPal OAuth token: {e}")
            return None

    def calculate_amounts(self, base_amount_inr: float) -> Tuple[float, float, float, float]:
        """
        Calculates surcharge and conversion.
        Returns: (base_inr, surcharge_inr, total_inr, total_usd)
        """
        surcharge_inr = round(base_amount_inr * (self.surcharge_percent / 100.0), 2)
        total_inr = round(base_amount_inr + surcharge_inr, 2)
        total_usd = round(total_inr / self.usd_rate, 2)
        if total_usd < 0.10:
            total_usd = 0.10
        return base_amount_inr, surcharge_inr, total_inr, total_usd

    async def create_payment_order(
        self,
        user_id: int,
        amount: float,
        order_id: str,
        customer_name: str,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a PayPal Checkout Order with 5% merchant fee surcharge included.
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "PayPal is not configured. Please set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET."
            }

        token = await self.get_access_token()
        if not token:
            return {
                "success": False,
                "error": "Unable to authenticate with PayPal. Please check credentials."
            }

        base_inr, surcharge_inr, total_inr, total_usd = self.calculate_amounts(amount)

        # Build PayPal Order Payload
        charge_currency = self.currency
        charge_value = f"{total_usd:.2f}" if charge_currency == "USD" else f"{total_inr:.2f}"

        url = f"{self.base_url}/v2/checkout/orders"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        bot_channel = getattr(config, "CHANNEL_LINK", "https://t.me/SamStoreServices")
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": order_id,
                    "description": f"SamStore Top-Up #{order_id} ({config.CURRENCY_SYMBOL}{amount:.0f} + 5% fee)",
                    "custom_id": str(user_id),
                    "amount": {
                        "currency_code": charge_currency,
                        "value": charge_value
                    }
                }
            ],
            "application_context": {
                "brand_name": getattr(config, "STORE_NAME", "SamStore Services"),
                "landing_page": "NO_PREFERENCE",
                "user_action": "PAY_NOW",
                "return_url": bot_channel,
                "cancel_url": bot_channel
            }
        }

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    res_data = await response.json()
                    if response.status in (200, 201):
                        paypal_order_id = res_data.get("id")
                        approve_url = None
                        for link in res_data.get("links", []):
                            if link.get("rel") == "approve":
                                approve_url = link.get("href")
                                break

                        if not approve_url:
                            approve_url = f"https://www.paypal.com/checkoutnow?token={paypal_order_id}"

                        return {
                            "success": True,
                            "order_id": order_id,
                            "gateway_order_id": paypal_order_id,
                            "payment_url": approve_url,
                            "base_amount": base_inr,
                            "surcharge_amount": surcharge_inr,
                            "total_inr": total_inr,
                            "total_usd": total_usd,
                            "currency": charge_currency,
                            "charge_value": charge_value
                        }
                    else:
                        err_msg = res_data.get("message") or str(res_data.get("details", [{}])[0].get("description", "PayPal Order creation failed."))
                        logger.error(f"PayPal Order Error: {res_data}")
                        return {
                            "success": False,
                            "error": f"PayPal Error: {err_msg}"
                        }
        except Exception as e:
            logger.error(f"Exception in create_payment_order (PayPal): {e}")
            return {
                "success": False,
                "error": f"Connection error with PayPal: {str(e)}"
            }

    async def verify_payment_status(self, gateway_order_id: str) -> Dict[str, Any]:
        """
        Queries PayPal to check order status and auto-captures if customer approved the payment.
        """
        if not self.is_configured:
            return {"is_paid": False, "status": "NOT_CONFIGURED"}

        token = await self.get_access_token()
        if not token:
            return {"is_paid": False, "status": "AUTH_FAILED"}

        url = f"{self.base_url}/v2/checkout/orders/{gateway_order_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                # 1. Check order details
                async with session.get(url, headers=headers) as response:
                    res_data = await response.json()
                    if response.status != 200:
                        return {"is_paid": False, "status": "NOT_FOUND", "raw": res_data}

                    status = res_data.get("status")

                    # If already COMPLETED
                    if status == "COMPLETED":
                        return {
                            "is_paid": True,
                            "status": "COMPLETED",
                            "order_id": gateway_order_id,
                            "amount": res_data.get("purchase_units", [{}])[0].get("amount", {}).get("value")
                        }

                    # If customer approved the order on PayPal UI, execute Capture
                    if status == "APPROVED":
                        capture_url = f"{self.base_url}/v2/checkout/orders/{gateway_order_id}/capture"
                        async with session.post(capture_url, headers=headers) as cap_response:
                            cap_data = await cap_response.json()
                            if cap_response.status in (200, 201):
                                cap_status = cap_data.get("status")
                                if cap_status == "COMPLETED":
                                    return {
                                        "is_paid": True,
                                        "status": "COMPLETED",
                                        "order_id": gateway_order_id,
                                        "capture_id": cap_data.get("id")
                                    }
                            return {"is_paid": False, "status": "CAPTURE_PENDING", "raw": cap_data}

                    return {"is_paid": False, "status": status}
        except Exception as e:
            logger.error(f"Exception verifying PayPal payment {gateway_order_id}: {e}")
            return {"is_paid": False, "status": "ERROR", "error": str(e)}
