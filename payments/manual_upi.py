from typing import Optional, Dict, Any
from payments.base import BasePaymentGateway
from utils.qr_generator import generate_upi_qr
import config

class ManualUPIGateway(BasePaymentGateway):
    """
    Standard Direct UPI QR Code Gateway with Manual UTR & Screenshot Verification.
    """
    async def create_payment_order(
        self,
        user_id: int,
        amount: float,
        order_id: str,
        customer_name: str,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        upi_string = f"upi://pay?pa={config.UPI_ID}&pn={config.UPI_NAME}&am={amount:.2f}&cu=INR&tn=Topup_{user_id}_{order_id}"
        qr_buf = generate_upi_qr(amount, note=f"Topup_{user_id}_{order_id}")
        return {
            "success": True,
            "order_id": order_id,
            "upi_id": config.UPI_ID,
            "upi_name": config.UPI_NAME,
            "upi_string": upi_string,
            "qr_buffer": qr_buf
        }

    async def verify_payment_status(self, gateway_order_id: str) -> Dict[str, Any]:
        return {
            "is_paid": False,
            "status": "MANUAL_VERIFICATION_REQUIRED"
        }
