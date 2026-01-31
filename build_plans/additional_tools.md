# Additional AI Capabilities in Hailo Submodules

**Date:** January 31, 2026  
**Purpose:** Document vision and image processing capabilities beyond basic object detection and image classification  
**Scope:** Comprehensive survey of segmentation, tracking, enhancement, and specialized detection models

---

## Executive Summary

This document details **10 additional AI capability categories** available in the Hailo git submodules that are not explicitly covered in the main README. These capabilities extend beyond basic object detection and include:

- **Segmentation:** Pixel-level object masks and scene understanding
- **Tracking & Re-Identification:** Multi-camera person tracking
- **Enhancement:** Image upscaling and quality improvement
- **Specialized Detection:** Lane detection, oriented bounding boxes, facial landmarks
- **Preprocessing:** Face alignment and embedding generation

These tools enable advanced computer vision applications including autonomous driving, surveillance analytics, medical imaging, and high-resolution content processing.

---

## 1. Instance Segmentation

### Overview
Instance segmentation provides **pixel-perfect masks** for each detected object, going beyond bounding boxes to deliver precise object boundaries. Each instance receives a unique mask, allowing distinction between overlapping objects of the same class.

### Location
- **Python Standalone:** `hailo-apps/hailo_apps/python/standalone_apps/instance_segmentation/`
- **Python Pipeline:** `hailo-apps/hailo_apps/python/pipeline_apps/instance_segmentation/`
- **C++ Standalone:** `hailo-apps/hailo_apps/cpp/instance_segmentation/`
- **Postprocessing:** `hailo-apps/hailo_apps/postprocess/cpp/yolov5seg.cpp`

### Supported Models
- **YOLOv5-seg:** YOLOv5 with segmentation head
- **YOLOv8-seg:** YOLOv8 with segmentation head
- **Architecture:** Detection backbone + segmentation decoder

### Technical Details
- **Output:** Bounding boxes + binary masks per instance
- **Mask Resolution:** 160×160 prototype masks (upsampled to full resolution)
- **Classes:** COCO 80 classes (person, car, dog, etc.)
- **Format:** HEF files optimized for Hailo-8/8L/10H

### Capabilities
- **Object Extraction:** Isolate individual objects with pixel precision
- **Occlusion Handling:** Separate overlapping objects by instance
- **Precise Counting:** Distinguish individual items in crowded scenes
- **Mask-Based Tracking:** Track object contours over time
- **Background Removal:** Extract foreground objects cleanly

### Key Files
- [instance_segmentation.py](../hailo-apps/hailo_apps/python/standalone_apps/instance_segmentation/) - Standalone implementation
- [yolov5seg.cpp](../hailo-apps/hailo_apps/postprocess/cpp/yolov5seg.cpp) - Postprocessing logic
- [yolov5seg.hpp](../hailo-apps/hailo_apps/postprocess/cpp/yolov5seg.hpp) - Header definitions

### Performance
| Model | Throughput (Hailo-8) | Latency | Accuracy (mAP) |
|-------|---------------------|---------|----------------|
| YOLOv5n-seg | ~25-30 fps | 33-40ms | 27.6% |
| YOLOv8n-seg | ~20-25 fps | 40-50ms | 30.5% |

### Example Use Cases
- **Retail:** Count individual items on shelves
- **Robotics:** Grasp planning with precise object boundaries
- **Medical Imaging:** Cell segmentation and counting
- **Automotive:** Pedestrian silhouette extraction for safety systems
- **Content Creation:** Object extraction for compositing/green screen replacement

### Comparison with Bounding Boxes
| Feature | Bounding Box | Instance Segmentation |
|---------|-------------|----------------------|
| Precision | Rectangular region | Pixel-perfect contour |
| Overlap handling | Cannot distinguish | Separate masks per instance |
| Background noise | Includes background | Only target object |
| Use for extraction | Poor quality | Clean extraction |

---

## 2. Semantic Segmentation

### Overview
Semantic segmentation classifies **every pixel** in an image by category, providing dense scene understanding. Unlike instance segmentation, it does not distinguish between individual instances—all pixels of the same class share one label.

### Location
- **C++ Application:** `hailo-apps/hailo_apps/cpp/semantic_segmentation/`
- **Postprocessing:** Built into model output (no separate postprocess file)

### Supported Models
- **FCN ResNet18:** Fully Convolutional Network based on ResNet-18
- **Training Dataset:** Cityscapes (urban street scenes)
- **Classes:** 19 categories (road, sidewalk, building, wall, fence, pole, traffic light, traffic sign, vegetation, terrain, sky, person, rider, car, truck, bus, train, motorcycle, bicycle)

### Technical Details
- **Input Resolution:** Varies (typically 1024×2048 or 512×1024)
- **Output:** H×W×C tensor where C is number of classes
- **Per-Pixel Classification:** Each pixel receives a class label
- **Post-processing:** Argmax over class dimension

### Capabilities
- **Scene Parsing:** Understand spatial layout of environments
- **Drivable Area Detection:** Identify navigable regions
- **Free Space Estimation:** Compute unoccupied areas
- **Context Understanding:** Reason about scene composition
- **Urban Planning:** Analyze infrastructure distribution

### Key Files
- [semantic_segmentation.cpp](../hailo-apps/hailo_apps/cpp/semantic_segmentation/semantic_segmentation.cpp) - Main application
- [README.md](../hailo-apps/hailo_apps/cpp/semantic_segmentation/README.md) - Usage documentation

### Features
- **Real-time processing:** Optimized for video inference
- **Cityscapes color mapping:** Standard visualization palette
- **Multi-resolution support:** Configurable input/output sizes
- **Batch processing:** Optional batching for efficiency

### Performance
| Model | Resolution | Throughput | Memory |
|-------|-----------|-----------|--------|
| FCN ResNet18 | 1024×2048 | ~10-15 fps | ~500 MB |
| FCN ResNet18 | 512×1024 | ~20-30 fps | ~300 MB |

### Example Use Cases
- **Autonomous Driving:** Understand road layout and obstacles
- **Robotics Navigation:** Path planning in complex environments
- **Urban Analytics:** Measure green space, road coverage
- **Augmented Reality:** Scene understanding for AR placement
- **Construction Monitoring:** Track progress and site layout

### Limitations
- **No instance distinction:** Cannot separate individual cars, people, etc.
- **Fixed classes:** Limited to Cityscapes taxonomy
- **Domain-specific:** Optimized for urban street scenes
- **Computationally intensive:** Higher latency than detection

---

## 3. Person Re-Identification (ReID)

### Overview
Person Re-Identification generates **discriminative embeddings** to match the same person across different camera views, times, and locations. Essential for multi-camera surveillance and tracking systems.

### Location
- **Pipeline Application:** `hailo-apps/hailo_apps/python/pipeline_apps/reid_multisource/`
- **Postprocessing:** `hailo-apps/hailo_apps/postprocess/cpp/repvgg_reid.cpp`
- **Database Integration:** `hailo-apps/hailo_apps/python/core/common/db_handler.py`

### Supported Models
- **RepVGG-based ReID:** Lightweight architecture for person embeddings
- **Embedding Dimension:** Typically 512D or 2048D feature vectors
- **Backbone:** RepVGG architecture (reparameterizable VGG)

### Technical Details
- **Input:** Cropped person images (typically 128×256 or 256×128)
- **Output:** Normalized embedding vector
- **Similarity Metric:** Cosine similarity or Euclidean distance
- **Threshold:** Configurable for matching confidence

### Architecture Flow
```
Detection (YOLOv8) → Person Crop → ReID Embedding → Similarity Matching → Track ID
```

### Capabilities
- **Cross-Camera Tracking:** Match persons across multiple cameras
- **Long-Term Tracking:** Re-identify after occlusion or disappearance
- **Appearance-Based Matching:** Invariant to pose and viewpoint changes
- **Gallery Search:** Query database for similar appearances
- **Multi-Source Fusion:** Combine tracks from multiple video sources

### Key Files
- [reid_multisource.py](../hailo-apps/hailo_apps/python/pipeline_apps/reid_multisource/) - Multi-camera application
- [repvgg_reid.cpp](../hailo-apps/hailo_apps/postprocess/cpp/repvgg_reid.cpp) - Embedding postprocessing
- [db_handler.py](../hailo-apps/hailo_apps/python/core/common/db_handler.py) - LanceDB integration

### Features
- **LanceDB Integration:** Vector database for embedding storage
- **Multi-source pipeline:** Handle multiple camera streams simultaneously
- **Telegram notifications:** Alert on person detection events
- **Appearance gallery:** Visualize person embeddings in 2D space
- **Threshold tuning:** Adjustable matching sensitivity

### Performance
| Model | Embedding Dim | Inference Time | Accuracy (mAP) |
|-------|--------------|----------------|----------------|
| RepVGG ReID | 512D | ~10-15ms | 60-70% (Market-1501) |

### Example Use Cases
- **Retail Analytics:** Track customer journey across store
- **Security Surveillance:** Multi-camera person tracking
- **Smart Buildings:** Monitor occupant movement patterns
- **Event Management:** Crowd flow analysis
- **Airport Security:** Track persons of interest across terminals

### Limitations
- **Appearance-based only:** Cannot handle dramatic clothing changes
- **Lighting sensitive:** Performance degrades in extreme lighting
- **Occlusion challenges:** Partial views reduce accuracy
- **Requires detection:** Depends on accurate person detection first

---

## 4. Tiling (High-Resolution Inference)

### Overview
Tiling enables inference on **high-resolution images** that exceed model input dimensions by dividing images into overlapping tiles, processing each tile independently, then stitching results back together with intelligent overlap handling.

### Location
- **Pipeline Application:** `hailo-apps/hailo_apps/python/pipeline_apps/tiling/`
- **Postprocessing:** `hailo-apps/hailo_apps/postprocess/cpp/hailo_tiling.cpp`

### Technical Details
- **Tile Size:** Configurable (typically 640×640 or 1024×1024)
- **Overlap:** Configurable percentage (typically 10-30%)
- **Stitching:** NMS-based deduplication at tile boundaries
- **Border Threshold:** Configurable handling of edge detections

### Algorithm
1. **Divide:** Split high-res image into overlapping tiles
2. **Infer:** Run detection model on each tile independently
3. **Transform:** Map tile-local coordinates to global image coordinates
4. **Stitch:** Merge results, removing duplicates at boundaries
5. **NMS:** Apply Non-Maximum Suppression across all detections

### Capabilities
- **High-Resolution Support:** Process images >4K resolution
- **Small Object Detection:** Improve detection of tiny objects
- **Memory Efficiency:** Process large images with limited VRAM
- **Scalable:** Handle arbitrary input sizes
- **Parallelizable:** Tiles can be processed in batches

### Key Files
- [tiling.py](../hailo-apps/hailo_apps/python/pipeline_apps/tiling/) - Tiling pipeline application
- [hailo_tiling.cpp](../hailo-apps/hailo_apps/postprocess/cpp/) - Tiling postprocessing (if exists)

### Configuration Parameters
| Parameter | Description | Typical Value |
|-----------|-------------|---------------|
| `tile_width` | Tile width in pixels | 640-1024 |
| `tile_height` | Tile height in pixels | 640-1024 |
| `overlap_ratio` | Overlap between tiles (0-1) | 0.1-0.3 |
| `border_threshold` | Suppress border detections | 0.1 |
| `iou_threshold` | NMS IoU threshold for stitching | 0.5 |

### Performance Considerations
- **Trade-off:** Higher overlap = better stitching but slower
- **Memory:** Tiles processed sequentially save memory
- **Batch size:** Can batch multiple tiles for efficiency
- **Border artifacts:** Overlap mitigates but doesn't eliminate edge issues

### Example Use Cases
- **Satellite Imagery:** Detect objects in large aerial photos
- **Medical Imaging:** Process high-resolution pathology slides
- **Document Analysis:** OCR on large scanned documents
- **Aerial Surveillance:** Drone footage analysis
- **Gigapixel Processing:** Ultra-high-resolution photography

### Best Practices
- **Overlap 15-25%:** Balance between stitching quality and speed
- **Tile size = model input:** Avoid resizing artifacts
- **Higher border threshold:** Suppress unreliable edge detections
- **Consider padding:** Add padding to tiles for better context

---

## 5. Lane Detection

### Overview
Lane detection identifies **lane markings and boundaries** in road scenes, essential for Advanced Driver Assistance Systems (ADAS) and autonomous vehicle navigation.

### Location
- **Standalone Application:** `hailo-apps/hailo_apps/python/standalone_apps/lane_detection/`

### Supported Models
- **UFLDv2 (Ultra Fast Lane Detection v2):** Lightweight row-wise classification approach
- **Architecture:** Efficient anchor-based lane detection
- **Training:** Trained on CULane/TuSimple datasets

### Technical Details
- **Output Format:** Lane coordinates as row-wise anchor points
- **Number of Lanes:** Typically detects 4-5 lanes
- **Representation:** Curve fitting or polyline segments
- **Confidence:** Per-lane confidence scores

### Capabilities
- **Multi-lane Detection:** Detect multiple lane markings simultaneously
- **Curved Lanes:** Handle curved roads and highway ramps
- **Occlusion Robustness:** Detect lanes with partial occlusion
- **Real-time Processing:** Optimized for video-rate inference
- **Distance Estimation:** Estimate lane position relative to vehicle

### Key Files
- [lane_detection.py](../hailo-apps/hailo_apps/python/standalone_apps/lane_detection/) - Main application
- [README.md](../hailo-apps/hailo_apps/python/standalone_apps/lane_detection/README.md) - Usage guide

### Features
- **Row-wise classification:** Efficient anchor-based detection
- **Video processing:** Real-time lane tracking in video streams
- **Visualization:** Overlay lane markings on original video
- **Camera input support:** Works with USB/RPi cameras

### Performance
| Model | Input Size | Throughput | Latency |
|-------|-----------|-----------|---------|
| UFLDv2 | 288×800 | ~30-40 fps | 25-33ms |

### Example Use Cases
- **ADAS:** Lane departure warning systems
- **Autonomous Driving:** Lane keeping assistance
- **Fleet Management:** Driver behavior monitoring
- **Road Maintenance:** Automated lane marking inspection
- **Simulation:** Training data generation for autonomous vehicles

### Limitations
- **Daytime focused:** Performance degrades in low light
- **Clear markings required:** Struggles with worn/faded lanes
- **Weather sensitive:** Rain/snow impacts accuracy
- **Road types:** Optimized for highways, less reliable on rural roads

---

## 6. Super-Resolution

### Overview
Super-resolution uses deep learning to **upscale low-resolution images** to higher resolutions with improved detail and reduced artifacts compared to traditional interpolation methods.

### Location
- **Standalone Application:** `hailo-apps/hailo_apps/python/standalone_apps/super_resolution/`

### Supported Models
- **ESPCN×4 (Efficient Sub-Pixel Convolutional Network):** 4× upscaling
- **SRGAN (Super-Resolution Generative Adversarial Network):** Perceptually-enhanced upscaling
- **Upscaling Factor:** 2×, 4×, or 8× depending on model

### Technical Details
- **Input:** Low-resolution image (e.g., 270×480)
- **Output:** High-resolution image (e.g., 1080×1920 for 4× upscaling)
- **Architecture:** 
  - ESPCN: Sub-pixel convolution layers
  - SRGAN: Generator + discriminator (inference uses generator only)
- **Quality Metrics:** PSNR, SSIM, perceptual quality

### Capabilities
- **Detail Recovery:** Reconstruct fine details lost in low-res images
- **Artifact Reduction:** Minimize compression artifacts
- **Edge Enhancement:** Sharpen edges and texture
- **Perceptual Quality:** SRGAN produces more realistic results
- **Batch Processing:** Process multiple images efficiently

### Key Files
- [super_resolution.py](../hailo-apps/hailo_apps/python/standalone_apps/super_resolution/super_resolution.py) - Main application
- [README.md](../hailo-apps/hailo_apps/python/standalone_apps/super_resolution/README.md) - Documentation

### Model Comparison
| Model | Type | Quality | Speed | Best For |
|-------|------|---------|-------|----------|
| **ESPCN×4** | CNN | Good PSNR | Fast | Real-time upscaling |
| **SRGAN** | GAN | Best perceptual | Slower | High-quality images |

### Performance
| Model | Input Size | Output Size | Throughput |
|-------|-----------|-------------|-----------|
| ESPCN×4 | 270×480 | 1080×1920 | ~15-20 fps |
| SRGAN | 270×480 | 1080×1920 | ~5-10 fps |

### Example Use Cases
- **Surveillance Enhancement:** Upscale low-res security footage
- **Medical Imaging:** Enhance diagnostic image quality
- **Video Streaming:** Upscale SD content to HD/4K
- **Gaming:** Upscale textures for better visuals
- **Photo Restoration:** Enhance old/degraded photographs
- **Satellite Imagery:** Improve resolution of aerial photos

### Limitations
- **Cannot recover lost information:** Synthesizes plausible details
- **Hallucination risk:** May introduce non-existent features
- **Computational cost:** Slower than simple interpolation
- **Domain-specific:** Training data affects output style
- **Diminishing returns:** Better input quality yields less improvement

### Best Practices
- **Use ESPCN for speed:** Real-time applications
- **Use SRGAN for quality:** Offline processing, photos
- **Reasonable upscaling:** 2-4× works best, 8× pushes limits
- **Preprocessing:** Denoise input images first

---

## 7. Oriented Object Detection (OBB)

### Overview
Oriented Object Detection extends traditional detection with **rotated bounding boxes**, enabling accurate localization of objects at arbitrary angles. Critical for aerial imagery, text detection, and scene text recognition.

### Location
- **Standalone Application:** `hailo-apps/hailo_apps/python/standalone_apps/oriented_object_detection/`
- **C++ Application:** `hailo-apps/hailo_apps/cpp/oriented_object_detection/`

### Supported Models
- **YOLO11 OBB:** YOLOv11 with Oriented Bounding Box head
- **Output:** (x, y, w, h, angle) + class + confidence
- **Angle Range:** Typically 0-180° or -90° to 90°

### Technical Details
- **Representation:** Rotated rectangle defined by center, width, height, angle
- **Angle Prediction:** Regression head for rotation angle
- **NMS:** Rotated IoU-based Non-Maximum Suppression
- **Format:** Similar to COCO but with additional angle parameter

### Capabilities
- **Arbitrary Rotation:** Detect objects at any angle
- **Tight Fitting:** Minimal background in bounding box
- **Text Detection:** Oriented text in natural scenes
- **Aerial Objects:** Ships, planes, vehicles in satellite imagery
- **Document Layout:** Rotated table/figure detection

### Key Files
- [oriented_object_detection.py](../hailo-apps/hailo_apps/python/standalone_apps/oriented_object_detection/) - Python implementation
- [oriented_obb.cpp](../hailo-apps/hailo_apps/cpp/oriented_object_detection/) - C++ implementation

### Features
- **Rotated visualization:** Draw angled bounding boxes
- **Multi-angle NMS:** Handle overlapping rotated boxes
- **Real-time inference:** Optimized for video streams
- **Standard YOLO interface:** Familiar API for developers

### Performance
| Model | Input Size | Throughput | Accuracy (mAP) |
|-------|-----------|-----------|----------------|
| YOLO11n-OBB | 640×640 | ~20-30 fps | Varies by dataset |

### Example Use Cases
- **Aerial Imagery:** Detect rotated objects in drone/satellite photos
  - Ships in harbors (various orientations)
  - Parked vehicles
  - Agricultural field boundaries
- **Scene Text Detection:** Tilted signs, banners, documents
- **Industrial Inspection:** Detect misaligned parts on assembly lines
- **Document Analysis:** Find rotated tables, figures, stamps
- **Augmented Reality:** Detect surface planes at arbitrary angles

### Comparison: Axis-Aligned vs. Oriented
| Feature | Axis-Aligned Box | Oriented Box |
|---------|-----------------|--------------|
| Parameters | 4 (x, y, w, h) | 5 (x, y, w, h, θ) |
| Background noise | High for rotated objects | Minimal |
| IoU calculation | Simple | Requires rotated IoU |
| Text detection | Poor | Excellent |
| Aerial imagery | Poor | Excellent |

### Limitations
- **Angle ambiguity:** 180° periodicity can cause confusion
- **Computational cost:** Rotated IoU is more expensive
- **Training data:** Requires oriented annotations
- **Visualization:** More complex to render

---

## 8. SCRFD Face Detection (with Facial Landmarks)

### Overview
SCRFD (Sample and Computation Redistribution for Face Detection) is a **lightweight face detector** that provides both bounding boxes and **5-point facial landmarks** (eyes, nose, mouth corners) for face alignment.

### Location
- **Postprocessing:** `hailo-apps/hailo_apps/postprocess/cpp/scrfd.cpp`
- **Header:** `hailo-apps/hailo_apps/postprocess/cpp/scrfd.hpp`

### Supported Models
- **SCRFD-2.5G:** Lightweight variant (2.5 GFLOPs)
- **SCRFD-10G:** Heavier variant (10 GFLOPs, higher accuracy)
- **Input Size:** 640×640
- **Anchor-based:** Uses predefined anchor boxes

### Technical Details
- **Outputs:**
  - Bounding boxes (x, y, w, h)
  - Confidence scores
  - **5 facial landmarks:** (x, y) for each of:
    1. Left eye center
    2. Right eye center
    3. Nose tip
    4. Left mouth corner
    5. Right mouth corner
- **Multi-scale detection:** 3 feature pyramid levels
- **NMS:** Standard IoU-based suppression

### Capabilities
- **Face Detection:** Detect faces at various scales
- **Facial Landmarks:** 5-point keypoints for alignment
- **Multi-face:** Handle multiple faces in one image
- **Pose Robustness:** Detect faces at various angles
- **Scale Invariance:** Detect tiny to large faces

### Key Files
- [scrfd.cpp](../hailo-apps/hailo_apps/postprocess/cpp/scrfd.cpp) - Postprocessing implementation
- [scrfd.hpp](../hailo-apps/hailo_apps/postprocess/cpp/scrfd.hpp) - Header definitions

### Architecture Details
```cpp
// Output tensors (per scale):
- Bounding boxes: [batch, anchors, 4]
- Classification: [batch, anchors, 1]
- Landmarks: [batch, anchors, 10]  // 5 points × 2 coords
```

### Performance
| Model | Input Size | Speed | Face Detection AP |
|-------|-----------|-------|-------------------|
| SCRFD-2.5G | 640×640 | ~50-60 fps | 82% (WIDER FACE) |
| SCRFD-10G | 640×640 | ~30-40 fps | 92% (WIDER FACE) |

### Example Use Cases
- **Face Alignment:** Normalize face orientation before recognition
- **Facial Attribute Analysis:** Use landmarks for expression detection
- **Face Swapping:** Align faces for realistic compositing
- **Makeup Try-On:** Position virtual makeup using landmarks
- **Glasses Detection:** Check occlusion of eye landmarks
- **Gaze Estimation:** Use eye landmarks for gaze direction

### Integration with Face Recognition Pipeline
```
SCRFD Detection → Face Alignment → ArcFace Embedding → Recognition
```

### Limitations
- **5 landmarks only:** Fewer than detailed 68-point models
- **Frontal bias:** Optimized for near-frontal faces
- **Expression invariance:** Landmarks less accurate with extreme expressions
- **Occlusion:** Performance degrades with partial occlusion

---

## 9. ArcFace (Face Recognition Embeddings)

### Overview
ArcFace generates **discriminative face embeddings** for face recognition and verification tasks. Uses angular margin loss for superior inter-class separation.

### Location
- **Postprocessing:** `hailo-apps/hailo_apps/postprocess/cpp/arcface.cpp`
- **Header:** `hailo-apps/hailo_apps/postprocess/cpp/arcface.hpp`
- **Database Integration:** `hailo-apps/hailo_apps/python/core/common/db_handler.py`

### Technical Details
- **Input:** Aligned face image (typically 112×112)
- **Output:** Normalized embedding vector (typically 512D)
- **Normalization:** L2 normalized for cosine similarity
- **Backbone:** ResNet or MobileFaceNet
- **Loss Function:** Additive Angular Margin (ArcFace)

### Capabilities
- **Face Verification:** One-to-one matching (is this the same person?)
- **Face Identification:** One-to-many matching (who is this person?)
- **Face Clustering:** Group similar faces
- **Embedding Database:** Store and query face embeddings
- **Similarity Search:** Find most similar faces in database

### Key Files
- [arcface.cpp](../hailo-apps/hailo_apps/postprocess/cpp/arcface.cpp) - Embedding extraction
- [arcface.hpp](../hailo-apps/hailo_apps/postprocess/cpp/arcface.hpp) - Header
- [db_handler.py](../hailo-apps/hailo_apps/python/core/common/db_handler.py) - LanceDB storage

### Architecture Flow
```
Face Detection (SCRFD) → Face Alignment → ArcFace Embedding → LanceDB Storage/Query
```

### Similarity Computation
```python
# Cosine similarity (embeddings are L2 normalized)
similarity = np.dot(embedding1, embedding2)

# Threshold for verification
is_same_person = similarity > 0.5  # Typical threshold
```

### Performance Metrics
| Model | Embedding Dim | Accuracy (LFW) | Speed |
|-------|--------------|----------------|-------|
| ArcFace ResNet-50 | 512D | 99.8% | ~15-20ms |
| MobileFaceNet | 512D | 99.5% | ~5-10ms |

### Database Integration
- **LanceDB:** Vector database for embedding storage
- **Search:** Efficient k-NN search for identification
- **Indexing:** Optimized for high-dimensional vectors
- **Threshold-based matching:** Configurable similarity threshold

### Example Use Cases
- **Access Control:** Face-based authentication
- **Surveillance:** Monitor and alert on persons of interest
- **Photo Organization:** Group photos by person
- **Social Media:** Face tagging and recognition
- **Attendance Systems:** Automated attendance tracking

### Best Practices
- **Face alignment first:** Use SCRFD/landmark alignment before embedding
- **Quality checks:** Filter low-quality or occluded faces
- **Multiple embeddings:** Store multiple embeddings per person for robustness
- **Threshold tuning:** Balance false accepts vs. false rejects
- **Database size:** LanceDB scales to millions of embeddings

### Limitations
- **Requires alignment:** Sensitive to face pose and alignment
- **Lighting changes:** Performance degrades with extreme lighting
- **Aging:** Embeddings drift over time as people age
- **Twins/lookalikes:** May struggle with very similar appearances
- **Cross-ethnicity:** Training data diversity affects generalization

---

## 10. Face Alignment

### Overview
Face alignment uses **detected facial landmarks** to normalize face images through geometric transformations, producing standardized inputs for face recognition models.

### Location
- **Postprocessing:** `hailo-apps/hailo_apps/postprocess/cpp/face_align.cpp`
- **Header:** `hailo-apps/hailo_apps/postprocess/cpp/face_align.hpp`

### Technical Details
- **Input:** Original image + 5 facial landmarks (from SCRFD)
- **Output:** Aligned face crop (typically 112×112 or 224×224)
- **Transformation:** Affine transformation (rotation, scale, translation)
- **Reference Points:** Canonical landmark positions

### Algorithm
1. **Receive landmarks:** 5-point facial keypoints from detector
2. **Compute transformation:** Calculate affine matrix to align landmarks to canonical positions
3. **Warp image:** Apply transformation to crop face region
4. **Resize:** Scale to target resolution (e.g., 112×112)
5. **Output:** Normalized face ready for recognition

### Transformation Types
- **Similarity Transform:** Rotation + uniform scaling + translation
- **Affine Transform:** Allows non-uniform scaling and shearing
- **Typically uses:** Similarity transform for face alignment

### Reference Landmark Positions
```cpp
// Canonical 5-point positions (example for 112×112 output)
Left eye:   (38.2946, 51.6963)
Right eye:  (73.5318, 51.5014)
Nose:       (56.0252, 71.7366)
Left mouth: (41.5493, 92.3655)
Right mouth:(70.7299, 92.2041)
```

### Capabilities
- **Pose Normalization:** Correct head rotation and tilt
- **Scale Normalization:** Standardize face size
- **Eye Alignment:** Horizontal alignment of eyes
- **Crop Consistency:** Consistent framing across images
- **Preprocessing:** Essential step before recognition

### Key Files
- [face_align.cpp](../hailo-apps/hailo_apps/postprocess/cpp/face_align.cpp) - Alignment implementation
- [face_align.hpp](../hailo-apps/hailo_apps/postprocess/cpp/face_align.hpp) - Header

### Integration in Face Recognition Pipeline
```
1. SCRFD Detection → Output: bbox + 5 landmarks
2. Face Alignment  → Input: image + landmarks → Output: aligned face crop
3. ArcFace         → Input: aligned crop → Output: embedding
4. Recognition     → Match embedding to database
```

### Performance Considerations
- **Lightweight:** Affine transformation is computationally cheap
- **Real-time:** Can process hundreds of faces per second
- **Quality improvement:** Significantly improves recognition accuracy
- **Batch processing:** Can align multiple faces in parallel

### Example Use Cases
- **Face Recognition Preprocessing:** Required step before ArcFace
- **Face Verification Systems:** Ensure consistent input format
- **Facial Attribute Analysis:** Normalize faces for age/gender prediction
- **3D Face Reconstruction:** Starting point for 3D alignment
- **Face Beautification:** Align before applying filters

### Quality Checks
Good alignment requires:
- **Accurate landmarks:** SCRFD must detect landmarks correctly
- **Visible features:** Eyes and mouth should be visible
- **Minimal occlusion:** No hands, glasses, or hair covering landmarks
- **Reasonable pose:** Extreme head angles may fail

### Limitations
- **Depends on landmarks:** Poor landmark detection → poor alignment
- **2D only:** Cannot correct for 3D head pose fully
- **Extreme poses:** Profile views cannot be aligned to frontal
- **Occlusion:** Covered landmarks cannot be aligned

---

## Comparative Analysis

### Segmentation Comparison
| Type | Output | Instance Distinction | Use Case |
|------|--------|---------------------|----------|
| **Instance Segmentation** | Per-instance masks | Yes | Object extraction, counting |
| **Semantic Segmentation** | Per-pixel class labels | No | Scene understanding, navigation |

### Detection Enhancements
| Enhancement | Input | Output | Primary Benefit |
|-------------|-------|--------|----------------|
| **Tiling** | High-res image | Detections | Handle large images |
| **Oriented OBB** | Image | Rotated boxes | Accurate localization at any angle |
| **SCRFD** | Face image | Bbox + landmarks | Face alignment preprocessing |

### Image Enhancement
| Method | Upscaling Factor | Quality | Speed | Best For |
|--------|-----------------|---------|-------|----------|
| **ESPCN×4** | 4× | Good | Fast | Real-time video |
| **SRGAN** | 4× | Excellent | Moderate | Photos/offline |

### Tracking & Identification
| System | Purpose | Output | Key Feature |
|--------|---------|--------|-------------|
| **ReID** | Multi-camera tracking | Person embeddings | Cross-camera matching |
| **ArcFace** | Face recognition | Face embeddings | Identity verification |

---

## Integration Patterns

### 1. Full Face Recognition Pipeline
```
Camera Input
    ↓
SCRFD Detection (bbox + 5 landmarks)
    ↓
Face Alignment (normalize using landmarks)
    ↓
ArcFace Embedding (512D vector)
    ↓
LanceDB Query (find nearest match)
    ↓
Identity Result (person name + confidence)
```

### 2. Multi-Camera Person Tracking
```
Camera 1, 2, 3, ...
    ↓
YOLOv8 Person Detection
    ↓
Person Crop Extraction
    ↓
RepVGG ReID Embedding
    ↓
Cross-Camera Matching
    ↓
Unified Track ID
```

### 3. High-Resolution Object Detection
```
High-Res Image (4K+)
    ↓
Tiling (split into 640×640 tiles)
    ↓
YOLOv8 Detection (per tile)
    ↓
Coordinate Transform (tile → global)
    ↓
NMS Stitching (remove duplicates)
    ↓
Global Detection Results
```

### 4. Autonomous Driving Scene Understanding
```
Road Camera Input
    ↓
Semantic Segmentation (FCN ResNet18)
    ├─→ Drivable area mask
    └─→ Lane Detection (UFLDv2)
         ↓
    Combined Scene Map (lanes + segmentation)
```

---

## Hardware Requirements

### Memory Requirements (Approximate)
| Capability | Model | VRAM | System RAM |
|-----------|-------|------|-----------|
| Instance Segmentation | YOLOv8n-seg | 300-500 MB | 1-2 GB |
| Semantic Segmentation | FCN ResNet18 | 300-500 MB | 1-2 GB |
| ReID | RepVGG ReID | 200-300 MB | 500 MB |
| Tiling | YOLOv8 + tiling | 300-500 MB | 2-3 GB (high-res) |
| Lane Detection | UFLDv2 | 100-200 MB | 500 MB |
| Super-Resolution | ESPCN×4 | 200-300 MB | 1 GB |
| Super-Resolution | SRGAN | 500-800 MB | 2 GB |
| Oriented Detection | YOLO11-OBB | 300-500 MB | 1-2 GB |
| SCRFD | SCRFD-10G | 200-300 MB | 500 MB |
| ArcFace | ResNet-50 | 200-300 MB | 500 MB |

### Concurrent Execution
Some capabilities can run simultaneously on Hailo-10H:
- ✅ **Detection + Segmentation**
- ✅ **Detection + ReID** (common pattern)
- ✅ **Face Detection (SCRFD) + ArcFace**
- ⚠️ **Multiple high-memory models** may exhaust VRAM

---

## Performance Summary

### Real-Time Capable (>30 fps on Hailo-8)
- ✅ Instance Segmentation (YOLOv5n-seg)
- ✅ Lane Detection (UFLDv2)
- ✅ SCRFD Face Detection
- ✅ ArcFace Embeddings
- ✅ Face Alignment
- ✅ Oriented Detection (YOLO11n-OBB)

### Near Real-Time (15-30 fps)
- ⚠️ Semantic Segmentation (FCN ResNet18, 1024×2048)
- ⚠️ Instance Segmentation (YOLOv8n-seg)
- ⚠️ Super-Resolution (ESPCN×4)
- ⚠️ ReID (per crop)

### Offline Processing (<15 fps)
- ⛔ Semantic Segmentation (2048×4096)
- ⛔ Super-Resolution (SRGAN)
- ⛔ Tiling (depends on image size and tile count)

---

## Software Dependencies

### Common Requirements
- **HailoRT:** 4.23.0 (Hailo-8/8L) or 5.1.1+ (Hailo-10H)
- **TAPPAS Core:** 5.1.0 or 5.2.0
- **OpenCV:** 4.5+
- **Python:** 3.10+
- **NumPy:** 1.20+

### Specific Requirements
| Capability | Additional Dependencies |
|-----------|------------------------|
| **ReID** | LanceDB, pyarrow, pydantic |
| **Face Recognition** | LanceDB, telegram-bot (optional) |
| **Super-Resolution** | PIL/Pillow |
| **Tiling** | None (uses standard detection) |
| **Lane Detection** | tqdm |

---

## References

### Papers & Documentation
- **Instance Segmentation:** YOLOv5-seg, YOLOv8-seg (Ultralytics)
- **Semantic Segmentation:** [FCN - Fully Convolutional Networks for Semantic Segmentation](https://arxiv.org/abs/1411.4038)
- **ReID:** RepVGG architecture
- **Lane Detection:** [UFLDv2 - Ultra Fast Deep Lane Detection with Hybrid Anchor Driven Ordinal Classification](https://arxiv.org/abs/2206.07389)
- **Super-Resolution:** 
  - [ESPCN - Real-Time Single Image and Video Super-Resolution](https://arxiv.org/abs/1609.05158)
  - [SRGAN - Photo-Realistic Single Image Super-Resolution](https://arxiv.org/abs/1609.04802)
- **Oriented Detection:** YOLO11 OBB (Ultralytics)
- **SCRFD:** [Sample and Computation Redistribution for Efficient Face Detection](https://arxiv.org/abs/2105.04714)
- **ArcFace:** [ArcFace: Additive Angular Margin Loss for Deep Face Recognition](https://arxiv.org/abs/1801.07698)

### Repository Links
- **Hailo Apps:** https://github.com/hailo-ai/hailo-apps
- **Hailo Model Zoo:** https://github.com/hailo-ai/hailo_model_zoo
- **HailoRT:** https://github.com/hailo-ai/hailort

---

## Version & Compatibility

**Document Version:** 1.0  
**Date Created:** January 31, 2026  
**HailoRT Compatibility:** 4.23.0 (Hailo-8/8L), 5.1.1 - 5.2.0 (Hailo-10H)  
**TAPPAS Core:** 5.1.0 - 5.2.0  
**Hailo Devices:** Hailo-8, Hailo-8L, Hailo-10H  
**Platforms:** Raspberry Pi 5, x86_64 Linux

---

*This document provides comprehensive coverage of additional AI capabilities available in the Hailo ecosystem beyond basic object detection and image classification. For implementation details and code examples, refer to the respective directories in the hailo-apps repository.*
