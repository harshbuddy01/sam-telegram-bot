from typing import Optional, Dict, Any
from payments.manual_upi import ManualUPIGateway
from payments.razorpay import RazorpayGateway
from payments.paypal import PayPalGateway
from payments.oxapay import OxaPayGateway

class PaymentManager:
    """
    Central Payment Gateway Manager supporting Razorpay, PayPal, OxaPay (Crypto) & Manual UPI.
    """
    def __init__(self):
        self.manual_upi = ManualUPIGateway()
        self.razorpay = RazorpayGateway()
        self.paypal = PayPalGateway()
        self.oxapay = OxaPayGateway()

    @property
    def default_gateway(self) -> str:
        if self.razorpay.is_configured:
            return "RAZORPAY"
        elif self.paypal.is_configured:
            return "PAYPAL"
        elif self.oxapay.is_configured:
            return "OXAPAY"
        return "MANUAL_UPI"

    def get_available_gateways(self) -> list[str]:
        gateways = []
        if self.razorpay.is_configured:
            gateways.append("RAZORPAY")
        if self.paypal.is_configured:
            gateways.append("PAYPAL")
        if self.oxapay.is_configured:
            gateways.append("OXAPAY")
        if not gateways:
            gateways.append("MANUAL_UPI")
        return gateways

    async def create_deposit_session(
        self,
        gateway_name: Optional[str],
        user_id: int,
        amount: float,
        order_id: str,
        customer_name: str,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        gw = (gateway_name or self.default_gateway).upper()

        if gw == "OXAPAY" and self.oxapay.is_configured:
            return await self.oxapay.create_payment_order(
                user_id=user_id,
                amount=amount,
                order_id=order_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email
            )
        elif gw == "PAYPAL" and self.paypal.is_configured:
            return await self.paypal.create_payment_order(
                 user_id=user_id,
                 amount=amount,
                 order_id=order_id,
                 customer_name=customer_name,
                 customer_phone=customer_phone,
                 customer_email=customer_email
            )
        elif gw == "RAZORPAY" and self.razorpay.is_configured:
            return await self.razorpay.create_payment_order(
                user_id=user_id,
                amount=amount,
                order_id=order_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email
            )
        else:
            return await self.manual_upi.create_payment_order(
                user_id=user_id,
                amount=amount,
                order_id=order_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email
            )

payment_manager = PaymentManager()
