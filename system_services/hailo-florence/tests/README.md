# hailo-florence Integration Tests

Test suite for the Florence-2 Image Captioning Service.

## Running Tests

### Prerequisites

```bash
sudo pip3 install --break-system-packages pytest requests pillow
```

### Run All Tests

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-florence
pytest tests/ -v
```

### Run Specific Test Class

```bash
pytest tests/test_hailo_florence_service.py::TestHealthEndpoint -v
pytest tests/test_hailo_florence_service.py::TestCaptionEndpoint -v
```

### Run with Coverage

```bash
pytest tests/ -v --cov=server --cov-report=html
```

## Test Categories

### 1. Health Endpoint Tests
- Service accessibility
- Response format validation
- Model loading status

### 2. Caption Endpoint Tests
- Basic caption generation
- Custom parameter handling
- Input validation
- Error handling (missing image, invalid format, etc.)

### 3. Metrics Endpoint Tests
- Metrics accessibility
- Response format
- Counter increments

### 4. Performance Tests
- Latency measurements
- Sequential request handling
- Throughput validation

### 5. Error Handling Tests
- Large image rejection
- Grayscale image conversion
- Malformed requests

## Test Configuration

Set custom API endpoint:
```bash
export FLORENCE_API_BASE=http://192.168.1.100:8082
pytest tests/ -v
```

## Expected Results

All tests should pass with service running:
```
tests/test_hailo_florence_service.py::TestHealthEndpoint::test_health_endpoint_accessible PASSED
tests/test_hailo_florence_service.py::TestHealthEndpoint::test_health_response_format PASSED
tests/test_hailo_florence_service.py::TestHealthEndpoint::test_health_model_loaded PASSED
tests/test_hailo_florence_service.py::TestCaptionEndpoint::test_caption_basic_request PASSED
tests/test_hailo_florence_service.py::TestCaptionEndpoint::test_caption_with_params PASSED
...

==================== X passed in Y seconds ====================
```

## Troubleshooting

### Service Not Ready
If tests fail with service not ready:
```bash
sudo systemctl status hailo-florence
sudo journalctl -u hailo-florence -f
```

Wait for model loading to complete (60-120 seconds on first start).

### Connection Refused
Check service is running and accessible:
```bash
curl http://localhost:8082/health
```

### Test Failures
Run with verbose output:
```bash
pytest tests/ -v -s --tb=long
```
