# Hailo SCRFD Service Tests

This directory contains integration tests for the hailo-scrfd service.

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip3 install pytest requests pillow opencv-python numpy

# Ensure service is running
sudo systemctl start hailo-scrfd.service
```

### Run All Tests

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-scrfd
pytest tests/ -v
```

### Run Specific Test Class

```bash
pytest tests/test_hailo_scrfd_service.py::TestHealthEndpoint -v
pytest tests/test_hailo_scrfd_service.py::TestDetectEndpoint -v
pytest tests/test_hailo_scrfd_service.py::TestAlignEndpoint -v
```

### Run Single Test

```bash
pytest tests/test_hailo_scrfd_service.py::TestDetectEndpoint::test_detect_with_landmarks -v
```

### Run with Output

```bash
pytest tests/ -v -s  # Show print statements
```

### Generate Coverage Report

```bash
pip3 install pytest-cov
pytest tests/ --cov=hailo_scrfd_service --cov-report=html
```

## Test Structure

### Test Classes

- **TestHealthEndpoint** — Health check endpoint tests
- **TestDetectEndpoint** — Face detection endpoint tests
- **TestAlignEndpoint** — Face alignment endpoint tests
- **TestPerformance** — Performance and stress tests
- **TestEdgeCases** — Boundary conditions and edge cases
- **TestErrorHandling** — Error responses and validation

### Fixtures (conftest.py)

- `service_url` — Base URL for service
- `sample_image_b64` — Random test image (base64)
- `face_image_b64` — Synthetic face image (base64)

## Environment Variables

```bash
# Override service URL (default: http://localhost:5001)
export HAILO_SCRFD_URL=http://192.168.1.100:5001

pytest tests/
```

## Test Coverage

### Endpoints Tested

- ✓ GET `/health`
- ✓ POST `/v1/detect`
- ✓ POST `/v1/align`

### Scenarios Covered

- Health check with model status
- Face detection with/without landmarks
- Face alignment for recognition
- Custom confidence thresholds
- Annotated image output
- Invalid inputs (missing image, bad base64)
- Edge cases (small/large images, PNG format)
- Concurrent requests
- Performance benchmarks

### Expected Behavior

**Mock Model:**
- All tests use mock model by default
- Returns 1 synthetic face detection
- Consistent landmarks for testing

**Real Model:**
- Tests should pass with real SCRFD model
- Detection results depend on input images
- Some tests may have 0 faces (expected)

## Troubleshooting

### Service Not Running

```bash
sudo systemctl start hailo-scrfd.service
sudo systemctl status hailo-scrfd.service
```

### Connection Refused

```bash
# Check service is listening
sudo ss -lntp | grep :5001

# Check health endpoint
curl http://localhost:5001/health
```

### Import Errors

```bash
pip3 install --user pytest requests pillow opencv-python numpy
```

### Tests Timing Out

```bash
# Increase timeout in tests or check service logs
sudo journalctl -u hailo-scrfd.service -f
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test SCRFD Service

on: [push, pull_request]

jobs:
  test:
    runs-on: self-hosted  # Raspberry Pi runner
    steps:
      - uses: actions/checkout@v3
      
      - name: Start service
        run: sudo systemctl start hailo-scrfd.service
      
      - name: Install test deps
        run: pip3 install pytest requests pillow opencv-python numpy
      
      - name: Run tests
        run: pytest system_services/hailo-scrfd/tests/ -v
      
      - name: Stop service
        run: sudo systemctl stop hailo-scrfd.service
```

## Performance Benchmarks

Expected performance (mock model):
- Health check: <50ms
- Face detection: <100ms
- Face alignment: <150ms

Expected performance (SCRFD-2.5G real model):
- Health check: <50ms
- Face detection: 15-25ms inference + 5-10ms preprocessing
- Face alignment: 20-35ms total

## Adding New Tests

### Test Template

```python
def test_new_feature(sample_image_b64):
    """Test description."""
    response = requests.post(
        f"{BASE_URL}/v1/detect",
        json={"image": f"data:image/jpeg;base64,{sample_image_b64}"},
        timeout=30
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Add assertions
    assert "expected_field" in data
```

### Best Practices

- Use descriptive test names
- Test one thing per test
- Use fixtures for common setup
- Include docstrings
- Test both success and error cases
- Use parametrize for similar tests with different inputs

## See Also

- [README.md](../README.md) — Service documentation
- [API_SPEC.md](../API_SPEC.md) — API reference
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) — Common issues
