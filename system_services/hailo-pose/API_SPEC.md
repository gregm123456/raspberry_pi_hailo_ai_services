# Hailo Pose API Specification

Base URL: `http://localhost:11436`

This service provides YOLOv8-based pose estimation, detecting human keypoints and skeleton connections in COCO format.

## COCO Keypoint Format

The service detects 17 keypoints per person:

| Index | Keypoint | Index | Keypoint |
|-------|----------|-------|----------|
| 0 | nose | 9 | right_elbow |
| 1 | left_eye | 10 | left_wrist |
| 2 | right_eye | 11 | right_wrist |
| 3 | left_ear | 12 | left_hip |
| 4 | right_ear | 13 | right_hip |
| 5 | left_shoulder | 14 | left_knee |
| 6 | right_shoulder | 15 | right_knee |
| 7 | left_elbow | 16 | left_ankle |
| 8 | right_elbow | 17 | right_ankle |

---

## GET /health

Health check endpoint. Returns service status and model information.

**Response (200 OK):**
```json
{
  "status": "ok",
  "model": "yolov8s-pose",
  "model_loaded": true,
  "uptime_seconds": 3600
}
```

**Example:**
```bash
curl http://localhost:11436/health
```

---

## GET /health/ready

Readiness probe for systemd or orchestration.

**Response (200 OK):** Service is ready.
```json
{"ready": true}
```

**Response (503 Service Unavailable):** Service is loading.
```json
{"ready": false, "reason": "model_loading"}
```

---

## GET /v1/models

List available pose estimation models.

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "yolov8s-pose",
      "object": "model",
      "created": 1706745600,
      "owned_by": "hailo",
      "task": "pose-estimation"
    }
  ],
  "object": "list"
}
```

---

## POST /v1/pose/detect

Detect human poses in an image. Returns bounding boxes, keypoints, and skeleton connections.

### Request Format

The endpoint accepts two input formats:

#### 1. Multipart Form Data (Recommended for Binary Images)

```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@person.jpg" \
  -F "confidence_threshold=0.6" \
  -F "max_detections=5"
```

**Form Fields:**
- `image` (required) - Binary image file (JPEG, PNG, WebP)
- `confidence_threshold` (optional, float) - Person detection confidence (default: 0.5)
- `iou_threshold` (optional, float) - NMS IoU threshold (default: 0.45)
- `max_detections` (optional, int) - Maximum number of people to detect (default: 10)
- `keypoint_threshold` (optional, float) - Minimum keypoint confidence (default: 0.3)

#### 2. JSON with Base64 Image

```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJ...",
    "confidence_threshold": 0.6,
    "max_detections": 5
  }'
```

**JSON Fields:**
- `image` (required, string) - Base64-encoded image or data URI
- `confidence_threshold` (optional, float)
- `iou_threshold` (optional, float)
- `max_detections` (optional, int)
- `keypoint_threshold` (optional, float)

### Response Format

**Response (200 OK):**
```json
{
  "poses": [
    {
      "person_id": 0,
      "bbox": {
        "x": 120,
        "y": 50,
        "width": 180,
        "height": 380
      },
      "bbox_confidence": 0.92,
      "keypoints": [
        {
          "name": "nose",
          "x": 210,
          "y": 95,
          "confidence": 0.95
        },
        {
          "name": "left_eye",
          "x": 205,
          "y": 90,
          "confidence": 0.93
        },
        {
          "name": "right_eye",
          "x": 215,
          "y": 90,
          "confidence": 0.94
        },
        {
          "name": "left_shoulder",
          "x": 190,
          "y": 130,
          "confidence": 0.89
        },
        {
          "name": "right_shoulder",
          "x": 230,
          "y": 130,
          "confidence": 0.91
        }
      ],
      "skeleton": [
        {
          "from": "nose",
          "to": "left_eye",
          "from_index": 0,
          "to_index": 1
        },
        {
          "from": "nose",
          "to": "right_eye",
          "from_index": 0,
          "to_index": 2
        },
        {
          "from": "left_shoulder",
          "to": "right_shoulder",
          "from_index": 5,
          "to_index": 6
        }
      ]
    }
  ],
  "count": 1,
  "inference_time_ms": 45,
  "image_size": {
    "width": 640,
    "height": 480
  }
}
```

**Response Fields:**
- `poses` (array) - Detected persons with their poses
  - `person_id` (int) - Unique ID for this detection
  - `bbox` (object) - Bounding box around person
    - `x`, `y` (int) - Top-left corner coordinates
    - `width`, `height` (int) - Box dimensions
  - `bbox_confidence` (float) - Person detection confidence (0.0-1.0)
  - `keypoints` (array) - 17 body keypoints
    - `name` (string) - Keypoint name (COCO format)
    - `x`, `y` (int) - Keypoint pixel coordinates
    - `confidence` (float) - Keypoint visibility confidence (0.0-1.0)
  - `skeleton` (array, optional) - Joint connections for visualization
    - `from`, `to` (string) - Connected keypoint names
    - `from_index`, `to_index` (int) - Keypoint array indices
- `count` (int) - Total number of detected people
- `inference_time_ms` (int) - NPU inference time in milliseconds
- `image_size` (object) - Processed image dimensions

### Examples

#### Detect Poses in Image File

```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@person.jpg" | jq
```

#### Detect with Custom Thresholds

```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@group.jpg" \
  -F "confidence_threshold=0.7" \
  -F "keypoint_threshold=0.4" \
  -F "max_detections=10"
```

#### Detect from Base64-Encoded Image

```bash
IMAGE_B64=$(base64 -w 0 person.jpg)
curl -X POST http://localhost:11436/v1/pose/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$IMAGE_B64\", \"confidence_threshold\": 0.6}"
```

#### Python Example (Using requests)

```python
import requests

with open('person.jpg', 'rb') as f:
    response = requests.post(
        'http://localhost:11436/v1/pose/detect',
        files={'image': f},
        data={'confidence_threshold': 0.6}
    )

result = response.json()
for pose in result['poses']:
    print(f"Person {pose['person_id']}: {len(pose['keypoints'])} keypoints")
    for kp in pose['keypoints']:
        if kp['confidence'] > 0.5:
            print(f"  {kp['name']}: ({kp['x']}, {kp['y']})")
```

#### Python Example (Using OpenCV for Visualization)

```python
import cv2
import requests
import json

# Read and encode image
img = cv2.imread('person.jpg')
_, buffer = cv2.imencode('.jpg', img)
files = {'image': ('image.jpg', buffer.tobytes(), 'image/jpeg')}

# Detect poses
response = requests.post('http://localhost:11436/v1/pose/detect', files=files)
result = response.json()

# Draw keypoints and skeleton
for pose in result['poses']:
    # Draw keypoints
    for kp in pose['keypoints']:
        if kp['confidence'] > 0.3:
            cv2.circle(img, (kp['x'], kp['y']), 5, (0, 255, 0), -1)
    
    # Draw skeleton connections
    if 'skeleton' in pose:
        keypoints_dict = {kp['name']: kp for kp in pose['keypoints']}
        for conn in pose['skeleton']:
            kp_from = keypoints_dict[conn['from']]
            kp_to = keypoints_dict[conn['to']]
            if kp_from['confidence'] > 0.3 and kp_to['confidence'] > 0.3:
                cv2.line(img, (kp_from['x'], kp_from['y']),
                         (kp_to['x'], kp_to['y']), (255, 0, 0), 2)

cv2.imwrite('output_pose.jpg', img)
```

---

## Error Responses

Standard HTTP status codes:

- `400 Bad Request` - Invalid payload, missing required fields, or malformed image
- `404 Not Found` - Invalid endpoint or model not found
- `413 Payload Too Large` - Image exceeds size limit (~10 MB)
- `500 Internal Server Error` - Model inference failure or internal error
- `503 Service Unavailable` - Service initializing or device unavailable

**Error Response Format:**
```json
{
  "error": {
    "message": "Invalid image format or corrupted data",
    "type": "invalid_request_error"
  }
}
```

---

## Performance Characteristics

| Metric | Value (YOLOv8s-pose) |
|--------|----------------------|
| **Throughput** | ~15-25 FPS |
| **Latency (avg)** | 30-60 ms |
| **Max Image Size** | 8192x8192 pixels |
| **Memory (loaded)** | ~1.5-2 GB |
| **Max Detections** | 10 people (configurable) |
| **Input Resolution** | 640x640 (model-dependent) |

---

## Use Cases

### Fitness Tracking
Detect body posture and joint angles for exercise form analysis:
```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@squat.jpg" \
  -F "confidence_threshold=0.7"
```

### Fall Detection
Monitor elderly persons for fall detection:
```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@camera_frame.jpg" \
  -F "keypoint_threshold=0.5"
```

### Motion Capture
Track human motion for animation or analysis:
```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@dance_frame.jpg" \
  -F "max_detections=5"
```

### Sports Analytics
Analyze athlete performance and technique:
```bash
curl -X POST http://localhost:11436/v1/pose/detect \
  -F "image=@basketball_shot.jpg" \
  -F "confidence_threshold=0.8"
```

---

## Keypoint Visibility

Keypoints have confidence scores indicating visibility:
- **> 0.8:** Highly visible, reliable position
- **0.5-0.8:** Visible but may be partially occluded
- **0.3-0.5:** Low confidence, possibly occluded
- **< 0.3:** Not detected or heavily occluded

Filter keypoints by `keypoint_threshold` parameter to exclude low-confidence detections.

---

## Notes

- **Multiple Persons:** The service detects multiple people in a single image (up to `max_detections`)
- **Coordinate System:** Keypoint coordinates are in pixel space (top-left origin)
- **Skeleton Connections:** Provided for visualization; use standard COCO skeleton format
- **Model Variants:** Support for YOLOv8n/s/m/l-pose models (configure via `model.name`)
- **Real-time Processing:** Optimized for Hailo-10H NPU acceleration
