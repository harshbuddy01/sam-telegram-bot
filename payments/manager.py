from typing import Optional, Dict, Any
from payments.manual_upi import ManualUPIGateway
from payments.cashfree import CashfreeGateway

class PaymentManager:
    """
    Central Payment Gateway Manager supporting both Direct UPI and Automated Gateways.
    """
    def __init__(self):
        self.manual_upi = ManualUPIGateway()
        self.cashfree = CashfreeGateway()

    def get_available_gateways(self) -> list[str]:
        gateways = ["MANUAL_UPI"]
        if self.cashfree.is_configured:
            gateways.append("CASHFREE")
        return gateways

    async def create_deposit_session(
        self,
        gateway_name: str,
        user_id: int,
        amount: float,
        order_id: str,
        customer_name: str,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        if gateway_name.upper() == "CASHFREE" and self.cashfree.is_configured:
            return await self.cashfree.create_payment_order(
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
