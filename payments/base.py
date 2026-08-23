from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BasePaymentGateway(ABC):
    """
    Abstract interface for payment gateways (Cashfree, Razorpay, Manual UPI, Paytm, Crypto).
    """

    @abstractmethod
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
        Creates a payment session / payment link on the gateway.
        Returns dict with: payment_url, gateway_order_id, session_id, etc.
        """
        pass

    @abstractmethod
    async def verify_payment_status(self, gateway_order_id: str) -> Dict[str, Any]:
        """
        Polls or verifies the status of a payment with the gateway.
        Returns dict with: is_paid (bool), amount, transaction_id, status.
        """
        pass
