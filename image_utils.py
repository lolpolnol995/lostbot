import hashlib
from io import BytesIO
from PIL import Image

def calculate_image_hash(image_bytes: bytes) -> str:
    """
    Вычисляет устойчивый dHash (Difference Hash) для выявления визуально одинаковых картинок.
    Если Pillow не сможет распарсить — берет sha256.
    """
    try:
        image = Image.open(BytesIO(image_bytes)).convert('L').resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(image.getdata())
        diff = []
        for row in range(8):
            for col in range(8):
                diff.append(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
        return "".join(["1" if b else "0" for b in diff])
    except Exception:
        return hashlib.sha256(image_bytes).hexdigest()
