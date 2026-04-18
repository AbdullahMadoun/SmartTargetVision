import numpy as np

def decode_yolov8_output(output, orig_shape, input_size=(640, 640), conf_thresh=0.5):
    """
    Decode YOLOv8 TensorRT output.

    Parameters:
    - output: numpy array of shape (1, C, N)
    - orig_shape: (height, width) of original image
    - input_size: model input size (default 640x640)
    - conf_thresh: confidence threshold

    Returns:
    - boxes: (N, 4) bounding boxes (x1, y1, x2, y2)
    - confidences: (N,)
    - class_ids: (N,)
    """

    # Remove batch dimension
    output = output[0]  # shape: (C, N)

    # Split into bbox + class scores
    boxes = output[:4, :]          # (4, N)
    scores = output[4:, :]         # (num_classes, N)

    # Get best class per anchor
    class_ids = np.argmax(scores, axis=0)
    confidences = np.max(scores, axis=0)

    # Apply confidence threshold
    mask = confidences > conf_thresh

    boxes = boxes[:, mask]
    confidences = confidences[mask]
    class_ids = class_ids[mask]

    # Transpose boxes → (N, 4)
    boxes = boxes.T

    # Convert from center format (cx, cy, w, h) → (x1, y1, x2, y2)
    cx, cy, bw, bh = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]

    x1 = cx - bw / 2
    y1 = cy - bh / 2
    x2 = cx + bw / 2
    y2 = cy + bh / 2

    # Scale back to original image size
    orig_h, orig_w = orig_shape
    scale_x = orig_w / input_size[0]
    scale_y = orig_h / input_size[1]

    x1 *= scale_x
    x2 *= scale_x
    y1 *= scale_y
    y2 *= scale_y

    boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

    return boxes_xyxy, confidences, class_ids