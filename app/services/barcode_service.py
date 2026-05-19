# app/services/barcode_service.py
# Barcode generation utilities.

import io
import base64

import barcode
from barcode.writer import ImageWriter


def generate_barcode_base64(patient_id: str) -> str:
    """Generate a Code128 barcode as a base64-encoded PNG string."""
    try:
        code128 = barcode.get_barcode_class('code128')
        rv = io.BytesIO()
        code128(str(patient_id), writer=ImageWriter()).write(rv)
        rv.seek(0)
        return base64.b64encode(rv.read()).decode('utf-8')
    except Exception:
        return ""
