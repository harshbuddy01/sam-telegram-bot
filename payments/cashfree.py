import aiohttp
import os
from typing import Optional, Dict, Any
from payments.base import BasePaymentGateway
import config

class CashfreeGateway(BasePaymentGateway):
    """
    Cashfree Payment Gateway Integration for Automated Instant Payments.
    """
    def __init__(self):
        self.app_id = getattr(config, "CASHFREE_APP_ID", os.getenv("CASHFREE_APP_ID", ""))
        self.secret_key = getattr(config, "CASHFREE_SECRET_KEY", os.getenv("CASHFREE_SECRET_KEY", ""))
        self.environment = getattr(config, "CASHFREE_ENV", os.getenv("CASHFREE_ENV", "PRODUCTION"))
        
        if self.environment.upper() == "SANDBOX" or (self.app_id and self.app_id.startswith("TEST")):
            self.base_url = "https://sandbox.cashfree.com/pg"
        else:
            self.base_url = "https://api.cashfree.com/pg"

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.secret_key)

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
        Creates an order on Cashfree and generates a direct payment URL.
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "Cashfree API keys not configured. Please set CASHFREE_APP_ID and CASHFREE_SECRET_KEY in environment variables."
            }

        url = f"{self.base_url}/orders"
        headers = {
            "x-client-id": self.app_id,
            "x-client-secret": self.secret_key,
            "x-api-version": "2023-08-01",
            "Content-Type": "application/json"
        }

        clean_phone = (customer_phone or "9999999999").replace("+91", "").replace(" ", "").strip()
        if len(clean_phone) < 10:
            clean_phone = "9999999999"

        payload = {
            "order_id": order_id,
            "order_amount": round(amount, 2),
            "order_currency": "INR",
            "customer_details": {
                "customer_id": f"tg_user_{user_id}",
                "customer_name": customer_name or f"User {user_id}",
                "customer_email": customer_email or f"user{user_id}@samstore.com",
                "customer_phone": clean_phone
            },
            "order_meta": {
                "return_url": f"https://t.me/{getattr(config, 'SUPPORT_USERNAME', 'SamStore').lstrip('@')}?start=dep_{order_id}"
            },
            "order_note": f"{config.STORE_NAME} — Order #{order_id}",
            "order_tags": {
                "store_name": config.STORE_NAME
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    res_data = await response.json()
                    if response.status in (200, 201):
                        payment_session_id = res_data.get("payment_session_id")
                        # Cashfree payment link format
                        pay_url = res_data.get("payments", {}).get("url") or f"https://payments.cashfree.com/order/#/{payment_session_id}"
                        return {
                            "success": True,
                            "order_id": order_id,
                            "cf_order_id": res_data.get("cf_order_id"),
                            "payment_session_id": payment_session_id,
                            "payment_url": pay_url
                        }
                    else:
                        return {
                            "success": False,
                            "error": res_data.get("message", "Cashfree order creation failed.")
                        }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection error with Cashfree: {str(e)}"
            }

    async def verify_payment_status(self, gateway_order_id: str) -> Dict[str, Any]:
        """
        Queries Cashfree to check if an order has been paid.
        """
        if not self.is_configured:
            return {"is_paid": False, "status": "NOT_CONFIGURED"}

        url = f"{self.base_url}/orders/{gateway_order_id}"
        headers = {
            "x-client-id": self.app_id,
            "x-client-secret": self.secret_key,
            "x-api-version": "2023-08-01"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    res_data = await response.json()
                    if response.status == 200:
                        order_status = res_data.get("order_status")
                        is_paid = (order_status == "PAID")
                        return {
                            "is_paid": is_paid,
                            "status": order_status,
                            "amount": res_data.get("order_amount", 0.0),
                            "order_id": gateway_order_id
                        }
                    else:
                        return {"is_paid": False, "status": "NOT_FOUND"}
        except Exception as e:
            return {"is_paid": False, "status": "ERROR", "error": str(e)}
