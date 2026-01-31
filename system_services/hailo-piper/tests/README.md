# Hailo Piper TTS Service Tests

Integration tests for the Hailo Piper TTS service.

## Prerequisites

```bash
pip3 install pytest requests
```

## Running Tests

### Run all tests:

```bash
cd system_services/hailo-piper
pytest tests/ -v
```

### Run with custom service URL:

```bash
pytest tests/ -v --service-url http://localhost:5002
```

### Skip integration tests (unit tests only):

```bash
pytest tests/ -v --skip-integration
```

### Run specific test class:

```bash
pytest tests/test_hailo_piper_service.py::TestHealthEndpoint -v
```

### Run with coverage:

```bash
pytest tests/ --cov=hailo_piper_service --cov-report=html
```

## Test Categories

### Health Endpoint Tests
- Service availability
- Response structure
- Model loading status

### Synthesis Tests
- Basic text synthesis
- Long text handling
- Punctuation and special characters
- Error handling (empty text, too long, invalid format)
- WAV file validation

### Alternative Endpoint Tests
- `/v1/synthesize` endpoint
- Parameter validation

### Voices Tests
- Voice listing
- Response structure

### Concurrent Tests
- Multiple simultaneous requests
- Queue handling

### Error Handling Tests
- Invalid endpoints (404)
- Invalid methods (405)
- Invalid JSON (400)

### Performance Tests
- Synthesis latency
- Health check response time

## Test Markers

Tests are marked with `@pytest.mark.integration` for integration tests that require a running service.

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Test Hailo Piper

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install dependencies
        run: |
          pip3 install pytest requests pyyaml
      - name: Start service
        run: |
          cd system_services/hailo-piper
          # Start service in background
          python3 hailo_piper_service.py &
          sleep 5
      - name: Run tests
        run: |
          cd system_services/hailo-piper
          pytest tests/ -v
```

## Manual Verification

For quick manual verification without pytest:

```bash
./verify.sh
```

This runs:
1. systemd service status check
2. Health endpoint check
3. Synthesis test
4. Audio file validation
5. Recent log review

## Writing New Tests

Example test structure:

```python
import pytest

@pytest.mark.integration
class TestNewFeature:
    """Test new feature."""
    
    def test_feature_works(self, client, service_url):
        """Feature should work as expected."""
        response = client.post(
            f"{service_url}/v1/new-endpoint",
            json={"param": "value"},
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
```

## Troubleshooting Tests

### Service not available

```bash
# Check if service is running
sudo systemctl status hailo-piper.service

# Start service
sudo systemctl start hailo-piper.service

# Or run service manually for debugging
python3 hailo_piper_service.py
```

### Tests timing out

Increase timeout in conftest.py or individual tests:

```python
response = client.post(url, json=data, timeout=60)  # 60 seconds
```

### Import errors

Ensure hailo-piper module is in Python path:

```bash
export PYTHONPATH="${PYTHONPATH}:/opt/hailo-piper"
```

## Coverage

Generate coverage report:

```bash
pytest tests/ --cov=hailo_piper_service --cov-report=html
open htmlcov/index.html
```

Target: >80% code coverage for critical paths.
