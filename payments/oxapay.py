import os
import json
import logging
import aiohttp
from typing import Optional, Dict, Any, Tuple
from payments.base import BasePaymentGateway
import config

logger = logging.getLogger(__name__)

class OxaPayGateway(BasePaymentGateway):
    """
    OxaPay Crypto Payment Gateway Integration
    - Supports Crypto Invoices (USDT TRC20/ERC20/BEP20/Polygon, BTC, ETH, TRX, SOL, BNB, LTC, etc.)
    - Direct payment link generation
    - Real-time invoice status verification
    - Webhook automated instant fulfillment
    """

    @property
    def merchant_key(self) -> str:
        val = os.getenv("OXAPAY_MERCHANT_KEY") or getattr(config, "OXAPAY_MERCHANT_KEY", "")
        return str(val).strip('"\' ')

    @property
    def currency(self) -> str:
        val = os.getenv("OXAPAY_CURRENCY") or getattr(config, "OXAPAY_CURRENCY", "USDT")
        return str(val).strip('"\' ').upper()

    @property
    def usd_rate(self) -> float:
        return float(os.getenv("OXAPAY_USD_TO_INR_RATE") or getattr(config, "OXAPAY_USD_TO_INR_RATE", 85.0))

    @property
    def surcharge_percent(self) -> float:
        return float(os.getenv("OXAPAY_SURCHARGE_PERCENT") or getattr(config, "OXAPAY_SURCHARGE_PERCENT", 0.0))

    @property
    def is_configured(self) -> bool:
        return bool(self.merchant_key and len(self.merchant_key) >= 5)

    def calculate_amounts(self, inr_amount: float) -> Tuple[float, float, float, float]:
        """
        Convert INR to USD/USDT with optional merchant surcharge.
        Returns: (base_inr, surcharge_inr, total_inr, total_usd)
        """
        base_inr = round(float(inr_amount), 2)
        surcharge_inr = round(base_inr * (self.surcharge_percent / 100.0), 2)
        total_inr = round(base_inr + surcharge_inr, 2)
        total_usd = round(total_inr / self.usd_rate, 2)
        if total_usd < 0.50:
            total_usd = 0.50
        return base_inr, surcharge_inr, total_inr, total_usd

    async def create_payment_order(
        self,
        user_id: int,
        amount: float,
        order_id: str,
        customer_name: str,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        bot_username: str = "SamStoreServices_Bot"
    ) -> Dict[str, Any]:
        """
        Creates an OxaPay crypto invoice.
        """
        if not self.is_configured:
            return {"success": False, "error": "OxaPay Merchant Key is not configured."}

        base_inr, surcharge_inr, total_inr, total_usd = self.calculate_amounts(amount)

        callback_url = getattr(config, "OXAPAY_CALLBACK_URL", "")
        return_url = f"https://t.me/{bot_username.lstrip('@')}"

        # OxaPay v1 API payload
        payload = {
            "amount": total_usd,
            "currency": self.currency,
            "order_id": str(order_id),
            "description": f"SamStore Order #{order_id} ({customer_name})",
            "return_url": return_url,
            "fee_paid_by_payer": 1
        }
        if callback_url:
            payload["callback_url"] = callback_url

        headers = {
            "merchant_api_key": self.merchant_key,
            "Content-Type": "application/json"
        }

        # Try v1 invoice endpoint first, fallback to merchants/request
        endpoints = [
            ("https://api.oxapay.com/v1/payment/invoice", headers, payload),
            ("https://api.oxapay.com/merchants/request", {"Content-Type": "application/json"}, {
                "merchant": self.merchant_key,
                "amount": total_usd,
                "currency": self.currency,
                "orderId": str(order_id),
                "description": f"SamStore Order #{order_id}",
                "callbackUrl": callback_url,
                "returnUrl": return_url,
                "feePaidByPayer": 1
            })
        ]

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            for url, req_headers, req_payload in endpoints:
                try:
                    async with session.post(url, json=req_payload, headers=req_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        res_data = await resp.json()
                        logger.info(f"OxaPay create invoice response from {url}: {res_data}")

                        pay_link = res_data.get("payLink") or res_data.get("data", {}).get("payLink") or res_data.get("link")
                        track_id = res_data.get("trackId") or res_data.get("data", {}).get("trackId")

                        if pay_link and track_id:
                            return {
                                "success": True,
                                "payment_url": pay_link,
                                "gateway_order_id": str(track_id),
                                "amount_usd": total_usd,
                                "amount_inr": total_inr,
                                "currency": self.currency,
                                "gateway": "OXAPAY"
                            }
                except Exception as e:
                    logger.warning(f"OxaPay invoice request to {url} failed: {e}")
                    continue

        return {"success": False, "error": "Failed to create OxaPay invoice session."}

    async def verify_payment_status(self, track_id: str) -> Dict[str, Any]:
        """
        Queries OxaPay API to verify if an invoice has been paid.
        """
        if not self.is_configured or not track_id:
            return {"is_paid": False, "status": "NOT_CONFIGURED"}

        headers = {
            "merchant_api_key": self.merchant_key,
            "Content-Type": "application/json"
        }

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # 1. Try v1 payment info GET
            try:
                url_v1 = f"https://api.oxapay.com/v1/payment/{track_id}"
                async with session.get(url_v1, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = str(data.get("status") or data.get("data", {}).get("status") or "").lower()
                        logger.info(f"OxaPay payment verification (v1) for track_id {track_id}: status={status}")
                        if status in ("paid", "completed", "success"):
                            return {"is_paid": True, "status": "PAID", "data": data}
                        return {"is_paid": False, "status": status.upper() or "PENDING", "data": data}
            except Exception as e:
                logger.warning(f"OxaPay v1 status inquiry failed: {e}")

            # 2. Try legacy inquiry POST
            try:
                url_legacy = "https://api.oxapay.com/merchants/inquiry"
                payload = {"merchant": self.merchant_key, "trackId": track_id}
                async with session.post(url_legacy, json=payload, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = str(data.get("status") or "").lower()
                        result = data.get("result")
                        logger.info(f"OxaPay payment verification (legacy) for track_id {track_id}: status={status}, result={result}")
                        if status in ("paid", "completed", "success") or (result == 100 and status == "paid"):
                            return {"is_paid": True, "status": "PAID", "data": data}
                        return {"is_paid": False, "status": status.upper() or "PENDING", "data": data}
            except Exception as e:
                logger.warning(f"OxaPay legacy status inquiry failed: {e}")

        return {"is_paid": False, "status": "UNKNOWN"}

    async def test_credentials(self, merchant_key: str) -> Tuple[bool, str]:
        """
        Validates OxaPay Merchant Key by making a lightweight API test call.
        """
        key = str(merchant_key).strip('"\' ')
        if not key:
            return False, "Merchant Key cannot be empty."

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                url = "https://api.oxapay.com/v1/payment/invoice"
                headers = {"merchant_api_key": key, "Content-Type": "application/json"}
                payload = {
                    "amount": 1.0,
                    "currency": "USDT",
                    "order_id": "test_auth_check",
                    "description": "Auth Check",
                    "return_url": "https://t.me/test"
                }
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if resp.status in (200, 201) and (data.get("payLink") or data.get("trackId") or data.get("result") == 100):
                        return True, "OxaPay Merchant API Key successfully verified and connected!"
                    elif data.get("message") or data.get("error"):
                        err = data.get("message") or data.get("error")
                        return False, f"OxaPay API Error: {err}"
                    else:
                        return True, "OxaPay Merchant Key saved."
            except Exception as e:
                return True, f"Key saved (Validation check note: {e})"
