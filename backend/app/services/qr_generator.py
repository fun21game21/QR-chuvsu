from io import BytesIO

import qrcode


def make_qr(url: str) -> bytes:
    output = BytesIO()
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    return output.getvalue()
