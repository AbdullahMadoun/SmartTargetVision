# Drone Vision Tracker Docker Container

This container runs an autonomous person-tracking system using YOLOv8 on a Jetson Nano, communicating with an Orange Cube via MAVLink.

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OS_ENV` | Set to `jetson` or `windows` for camera driver selection. | `jetson` |
| `MODEL_TYPE` | `std` for standard YOLO, `visdrone` for fine-tuned version. | `std` |
| `CONNECTION_STRING` | Serial path (`/dev/ttyTHS1`) or UDP (`udp:IP:PORT`). | `/dev/ttyTHS1` |
| `BAUD_RATE` | Connection speed (Baud rate). | `921600` |
| `CAM_INDEX` | Index of the USB/CSI camera. | `0` |
| `TARGET_IDEAL_AREA` | Pixel area to maintain for distance control. | `50000` |
| `VERTICAL_DEADZONE` | Area tolerance before vertical movement triggers. | `5000` |
| `HORIZONTAL_DEADZONE`| Pixel radius tolerance for center tracking. | `25` |
| `VERTICAL_VELOCITY` | Set `true` to enable altitude-based tracking. | `false` |
| `SPEED_SAFETY` | Set `true` to cap velocities. | `false` |

## Usage on Jetson Nano

### 1. Change Directory to drone_ai folder
```bash
cd "enter folder path here"
```

### 2. Build the Image
```bash
docker build -t jetson-tracker .
```

### 3. Run the Container
```bash
docker run -it --rm \
    --device /dev/ttyTHS1 \
    --device /dev/video0 \
    --runtime nvidia \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix/:/tmp/.X11-unix \
    jetson-tracker
```
