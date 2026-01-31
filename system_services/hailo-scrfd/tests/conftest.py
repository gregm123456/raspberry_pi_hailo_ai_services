import pytest


@pytest.fixture(scope="session")
def service_url():
    """Base URL for the SCRFD service."""
    return "http://localhost:5001"


@pytest.fixture
def sample_image_b64():
    """Sample base64-encoded test image."""
    import base64
    from io import BytesIO
    from PIL import Image
    import numpy as np
    
    # Create a simple test image
    img_array = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    img_bytes = buffer.getvalue()
    
    return base64.b64encode(img_bytes).decode('utf-8')


@pytest.fixture
def face_image_b64():
    """Sample face-like image for testing."""
    import base64
    from io import BytesIO
    from PIL import Image
    import numpy as np
    import cv2
    
    # Create image with face-like pattern
    img_array = np.ones((480, 640, 3), dtype=np.uint8) * 200
    
    # Draw simple face
    cv2.circle(img_array, (320, 240), 60, (255, 200, 150), -1)
    cv2.circle(img_array, (300, 225), 5, (0, 0, 0), -1)
    cv2.circle(img_array, (340, 225), 5, (0, 0, 0), -1)
    cv2.ellipse(img_array, (320, 260), (20, 10), 0, 0, 180, (0, 0, 0), 2)
    
    img = Image.fromarray(img_array)
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    img_bytes = buffer.getvalue()
    
    return base64.b64encode(img_bytes).decode('utf-8')
