Here is a full, detailed architecture and software requirements guideline for the **drone face/identity recognition pipeline** on Jetson Nano.

***

## System Overview

The system is a **two-stage, real-time identity verification pipeline** running on a Jetson Nano onboard a drone. Stage 1 detects and localizes faces/persons using YOLOE. Stage 2 runs a lightweight metric-learning embedding model on each crop to verify identity via cosine similarity. Mode 2 (cloud) handles enrollment and prompt generation.

***

## Full Architecture

```
Camera Input (CSI / USB)
        │
        ▼
┌─────────────────────┐
│   YOLOE (TensorRT)  │  ← text/visual prompts injected from Mode 2
│  Person/Face Detect │
│  ~640×480 or 416×416│
└────────┬────────────┘
         │  High-confidence crops only (conf > 0.6)
         ▼
┌─────────────────────┐
│  Crop + Align       │  ← 112×112 or 128×128 normalized face/object crop
│  (optional landmark │
│   alignment for     │
│   faces)            │
└────────┬────────────┘
         │
         ▼
┌──────────────────────────┐
│  Embedding Model         │  ← MobileNetV2 / MobileFaceNet + ArcFace/Triplet
│  (TensorRT INT8/FP16)    │     output: 128D or 256D L2-normalized vector
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Cosine Similarity       │  ← compare to enrolled target embedding(s)
│  + Temporal Smoothing    │     average over N frames for stability
│  + Threshold Gate        │     e.g., sim > 0.75 = match
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Alert / Track / Log     │  ← GPS tag, timestamp, confidence score
│  → Ground Station        │
└──────────────────────────┘
```

***

## Software Requirements

### 1. OS & Runtime Environment

| Component | Requirement |
|---|---|
| OS | JetPack 4.6.x (L4T for Nano) |
| Python | 3.8+ |
| CUDA | 10.2 (JetPack 4.6) |
| TensorRT | 8.x (bundled with JetPack) |
| PyTorch | torch 1.11–1.13 (Jetson wheel) |
| ONNX Runtime | onnxruntime-gpu (Jetson build) |

***

### 2. Stage 1 — YOLOE Detector

**Model:**
- **YOLOE-S** or **YOLOE-N** (smallest variants)
- Trained/exported from Ultralytics YOLOE
- Export path: `PyTorch → ONNX → TensorRT engine (.trt)`

**Libraries:**
```
ultralytics>=8.3.x       # YOLOE support
onnx
onnxruntime-gpu
tensorrt
pycuda
```

**Config:**
- Input resolution: `416×416` or `640×480` (balance speed vs. accuracy on Nano)
- Precision: `FP16` (TensorRT) for speed
- Classes: `["person", "face"]` or open-vocab text prompts from Mode 2
- Confidence threshold: `0.6`
- NMS IoU threshold: `0.45`

**Prompt injection (from Mode 2):**
- Text prompts received as a JSON file or MQTT message: `["person in orange vest", "male with black backpack"]`
- YOLOE loads these prompts via `model.set_classes([...])` before flight or mid-flight update

***

### 3. Crop + Alignment Module

**For faces:**
- Use a **5-point facial landmark detector** (e.g., SCRFD or RetinaFace-landmark, lightweight variant)
- Align face crop to canonical 112×112 using affine transform
- This is critical for ArcFace-style embedding accuracy

**For general objects:**
- Simple bbox crop + resize to 128×128
- Center-pad to preserve aspect ratio

**Libraries:**
```
opencv-python
numpy
insightface (for SCRFD landmark detector, optional)
```

***

### 4. Stage 2 — Embedding Model

**Option A — Faces (best accuracy):**
- **MobileFaceNet** or **ArcFace with MobileNet backbone**
- Pretrained on MS1MV2 / Glint360K
- Output: 128D or 512D L2-normalized embedding
- Export: ONNX → TensorRT FP16
- Expected on Nano: ~25–30 FPS on crops (lightweight; only runs on detected faces, not every frame)

**Option B — General objects (custom targets):**
- **MobileNetV2-0.5** backbone + 128D embedding head
- Train with **ArcFace loss or Triplet loss with hard mining** on your object identity dataset
- If no custom training: use MobileNetV2 penultimate layer features (ImageNet pretrained) as a weaker but zero-training baseline

**Libraries:**
```
torch
torchvision
onnx
tensorrt
insightface        # for pretrained MobileFaceNet weights
facenet-pytorch    # alternative for FaceNet embeddings
```

***

### 5. Similarity Matching & Temporal Smoothing

**Enrollment (done on ground / Mode 2 before flight):**
- Capture 5–10 reference images of the target person/object from different angles
- Run each through the embedding model
- Store the **mean embedding** as the enrolled template

**Runtime matching:**
```python
# Per detection, per frame:
sim = cosine_similarity(query_embedding, enrolled_embedding)

# Temporal smoothing:
rolling_sim_buffer.append(sim)
smoothed_sim = mean(rolling_sim_buffer[-N:])  # N = 5–10 frames

# Decision:
if smoothed_sim > THRESHOLD:  # e.g., 0.75
    confirm_target()
```

**Libraries:**
```
numpy
scipy (cosine similarity)
collections.deque (rolling buffer)
```

***

### 6. Communication & Integration (Mode 1 ↔ Mode 2)

**Mode 2 → Drone (ground to air):**
- Protocol: **MQTT over WiFi/5G** (lightweight pub/sub, good for embedded)
- Payload: JSON with text prompts, optional reference crop (base64 encoded image)
- Library: `paho-mqtt`

**Drone → Ground:**
- GPS-tagged alert events: `{timestamp, lat, lon, identity_id, confidence}`
- Optional: periodic thumbnail of matched crop
- Protocol: same MQTT broker or **MAVLink custom message**

**MAVLink integration:**
- Use `pymavlink` or `dronekit` to read GPS coordinates and pair with detection events

```
paho-mqtt
pymavlink or dronekit-python
```

***

### 7. Camera Interface

| Camera | Interface | Library |
|---|---|---|
| RPi Camera v2 | CSI | `jetson.utils` (NVIDIA Jetson Utils) |
| USB Webcam | USB | `opencv VideoCapture` |
| IMX219 / IMX477 | CSI | `nvarguscamerasrc` (GStreamer) |

Recommended pipeline for Nano:
```python
# GStreamer pipeline for CSI camera on Jetson
gst_pipeline = "nvarguscamerasrc ! video/x-raw(memory:NVMM), width=640, height=480 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! appsink"
cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
```

***

### 8. Full Software Stack Summary

```
jetson-stats                  # monitor GPU/CPU/memory on Nano
ultralytics                   # YOLOE detection
onnx / onnxruntime-gpu        # model export/inference
tensorrt / pycuda             # TRT engine inference
torch / torchvision           # embedding model
opencv-python                 # camera, crop, alignment
insightface / facenet-pytorch # pretrained face embeddings
numpy / scipy                 # cosine similarity, math
paho-mqtt                     # Mode 2 ↔ Mode 1 comms
pymavlink / dronekit          # drone telemetry + GPS
```

***

## Key Design Decisions

**Why two-stage?**
Running the embedding model on every pixel every frame is wasteful. YOLOE localizes first, then the embedding model only runs on confirmed detections. This keeps Nano's GPU budget manageable.

**Why TensorRT?**
Both YOLOE and the embedding model must be exported to TensorRT engines for FP16 inference. Without TensorRT, you will not hit real-time speeds on Nano.

**Why temporal smoothing?**
A single-frame cosine similarity can be noisy due to motion blur, occlusion, or angle. Averaging over 5–10 frames gives a much more stable "is this the target?" decision without extra compute.

**Why MQTT for Mode 2 comms?**
MQTT is extremely lightweight and designed for constrained devices. Sending a 3KB JSON prompt update mid-flight is nearly instant. It's also async, so the drone never blocks waiting for cloud responses.

***

## Expo Demo Flow

1. **Enroll target** on ground: capture 5 photos of a volunteer → generate enrolled embedding → upload to drone via MQTT.
2. **Drone takes off**, YOLOE runs with text prompts from Mode 2 cloud VLM.
3. Drone scans area → YOLOE detects a person → crop sent to embedding model.
4. Embedding compared to enrolled template → smoothed similarity score computed.
5. If match confirmed → drone hovers, logs GPS location, sends alert to ground station with confidence score.
6. Ground station displays: `"Target located at [lat, lon] — Confidence: 91%"`.