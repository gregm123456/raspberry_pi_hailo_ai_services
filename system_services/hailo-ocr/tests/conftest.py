"""Pytest configuration for hailo-ocr tests."""

import pytest


@pytest.fixture
def sample_image_data():
    """Create a simple test image (PNG bytes)."""
    from PIL import Image, ImageDraw
    import io
    
    # Create a simple test image
    img = Image.new('RGB', (200, 100), color='white')
    d = ImageDraw.Draw(img)
    d.text((50, 40), "TEST", fill='black')
    
    # Convert to JPEG bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    return img_bytes.getvalue()


@pytest.fixture
def sample_base64_image(sample_image_data):
    """Convert sample image to base64 data URI."""
    import base64
    b64 = base64.b64encode(sample_image_data).decode()
    return f"data:image/jpeg;base64,{b64}"
