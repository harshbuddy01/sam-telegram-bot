import hmac
import hashlib
import json
import aiohttp
import os
from typing import Optional, Dict, Any
from payments.base import BasePaymentGateway
import config

class RazorpayGateway(BasePaymentGateway):
    """
    Razorpay Payment Gateway Integration:
    - Creates Instant Payment Links (UPI, GPay, PhonePe, Cards, NetBanking)
    - Validates Webhooks for Instant Auto-Credit
    """
    base_url = "https://api.razorpay.com/v1"

    @property
    def key_id(self):
        return os.getenv("RAZORPAY_KEY_ID") or getattr(config, "RAZORPAY_KEY_ID", "")

    @property
    def key_secret(self):
        return os.getenv("RAZORPAY_KEY_SECRET") or getattr(config, "RAZORPAY_KEY_SECRET", "")

    @property
    def webhook_secret(self):
        return os.getenv("RAZORPAY_WEBHOOK_SECRET") or getattr(config, "RAZORPAY_WEBHOOK_SECRET", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

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
        Creates a Razorpay Standard Payment Link with 100% UPI support.
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "Razorpay API keys not configured. Please set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
            }

        url = f"{self.base_url}/payment_links"
        auth = aiohttp.BasicAuth(self.key_id, self.key_secret)

        customer_data = {
            "name": customer_name or f"Telegram User {user_id}",
            "email": customer_email or f"user{user_id}@samstore.com"
        }
        if customer_phone and len(customer_phone.replace("+91", "").strip()) >= 10:
            clean_phone = customer_phone.replace("+91", "").replace(" ", "").strip()
            customer_data["contact"] = f"+91{clean_phone[-10:]}"

        # Amount in paise (1 INR = 100 paise)
        amount_in_paise = int(round(amount * 100))

        payload = {
            "amount": amount_in_paise,
            "currency": "INR",
            "accept_partial": False,
            "reference_id": order_id,
            "description": f"Wallet Top-Up #{order_id} for User {user_id}",
            "customer": customer_data,
            "notify": {
                "sms": False,
                "email": False
            },
            "reminder_enable": False,
            "notes": {
                "user_id": str(user_id),
                "deposit_order_id": order_id
            }
        }

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, auth=auth) as response:
                    res_data = await response.json()
                    if response.status in (200, 201):
                        short_url = res_data.get("short_url")
                        plink_id = res_data.get("id")
                        return {
                            "success": True,
                            "order_id": order_id,
                            "gateway_order_id": plink_id,
                            "payment_url": short_url
                        }
                    else:
                        err = res_data.get("error", {}).get("description", "Razorpay link creation failed.")
                        return {
                            "success": False,
                            "error": err
                        }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection error with Razorpay: {str(e)}"
            }

    async def verify_payment_status(self, gateway_order_id: str) -> Dict[str, Any]:
        """
        Polls Razorpay for the status of a payment link.
        """
        if not self.is_configured:
            return {"is_paid": False, "status": "NOT_CONFIGURED"}

        url = f"{self.base_url}/payment_links/{gateway_order_id}"
        auth = aiohttp.BasicAuth(self.key_id, self.key_secret)

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, auth=auth) as response:
                    res_data = await response.json()
                    if response.status == 200:
                        status = res_data.get("status") # "created", "paid", "partially_paid", "expired", "cancelled"
                        is_paid = (status in ("paid", "closed") and res_data.get("payments_count_received", 0) > 0) or (status == "paid")
                        amount = float(res_data.get("amount_paid", 0) or res_data.get("payments_amount_received", 0)) / 100.0
                        return {
                            "is_paid": is_paid,
                            "status": status,
                            "amount": amount,
                            "gateway_order_id": gateway_order_id
                        }
                    else:
                        return {"is_paid": False, "status": "NOT_FOUND"}
        except Exception as e:
            return {"is_paid": False, "status": "ERROR", "error": str(e)}

    async def create_qr_code(
        self,
        user_id: int,
        amount: float,
        order_id: str,
        customer_name: str
    ) -> Dict[str, Any]:
        """
        Creates an official Razorpay Dynamic Native UPI QR Code (single_use).
        Scanning this in PhonePe / GPay / Paytm opens the native UPI payment window directly.
        """
        if not self.is_configured:
            return {"success": False, "error": "Razorpay not configured."}

        url = f"{self.base_url}/payments/qr_codes"
        auth = aiohttp.BasicAuth(self.key_id, self.key_secret)

        amount_in_paise = int(round(amount * 100))
        payload = {
            "type": "upi_qr",
            "name": "SamStore Services",
            "usage": "single_use",
            "fixed_amount": True,
            "payment_amount": amount_in_paise,
            "description": f"Order #{order_id}",
            "notes": {
                "user_id": str(user_id),
                "order_id": order_id
            }
        }

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, auth=auth) as response:
                    res_data = await response.json()
                    if response.status in (200, 201):
                        qr_id = res_data.get("id")
                        image_url = res_data.get("image_url")
                        
                        # Download Razorpay official QR code image bytes
                        async with session.get(image_url) as img_resp:
                            img_bytes = await img_resp.read()
                            return {
                                "success": True,
                                "gateway_order_id": qr_id,
                                "qr_image_bytes": img_bytes,
                                "payment_url": image_url
                            }
                    else:
                        err = res_data.get("error", {}).get("description", "Razorpay QR creation failed.")
                        return {"success": False, "error": err}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def verify_webhook_signature(self, body_bytes: bytes, signature_header: str) -> bool:
        """
        Verifies Razorpay Webhook HMAC SHA256 Signature.
        """
        if not self.webhook_secret:
            return True # If no secret set, accept in dev
        
        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_sig, signature_header)
