import io
import qrcode
from PIL import Image, ImageDraw, ImageFont
import config

def generate_upi_qr(amount: float, note: str = "Store Deposit") -> io.BytesIO:
    """
    Generates a high-resolution QR code for UPI payment.
    URI Format: upi://pay?pa=<UPI_ID>&pn=<UPI_NAME>&am=<AMOUNT>&cu=INR&tn=<NOTE>
    Returns: BytesIO stream of the PNG image
    """
    # Build standard UPI payment URI
    clean_note = note.replace(" ", "%20")
    clean_name = config.UPI_NAME.replace(" ", "%20")
    upi_uri = (
        f"upi://pay?pa={config.UPI_ID}"
        f"&pn={clean_name}"
        f"&am={amount:.2f}"
        f"&cu=INR"
        f"&tn={clean_note}"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(upi_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1E1B4B", back_color="white").convert("RGB")
    
    # Save to buffer
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio
