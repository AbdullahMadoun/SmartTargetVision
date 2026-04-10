from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


class ImageEmbedder:
    def __init__(self, config: dict) -> None:
        self._backend = config.get("backend", "mobilenet_v2")
        self._fallback = config.get("fallback_backend", "simple_stats")
        self._device = config.get("device", "cpu")
        self._size = int(config.get("input_size", 224))
        self._model = None
        self._weights_error: str | None = None
        self._mtcnn = None
        self._fallback_model = None
        self._fallback_preprocess = None
        self._standardize = None

        if self._backend == "facenet":
            self._init_facenet(config)
        elif self._backend == "mobilenet_v2":
            self._init_mobilenet()
        elif self._backend != "simple_stats":
            raise ValueError(f"Unsupported embedder backend: {self._backend}")

    def _init_facenet(self, config: dict) -> None:
        try:
            from facenet_pytorch import InceptionResnetV1, MTCNN
            from facenet_pytorch.models.mtcnn import fixed_image_standardization
        except ImportError as exc:
            raise ImportError(
                "facenet-pytorch is required for the facenet embedding backend."
            ) from exc

        try:
            margin = int(config.get("margin", 14))
            pretrained = str(config.get("pretrained", "vggface2"))
            self._mtcnn = MTCNN(
                image_size=self._size,
                margin=margin,
                keep_all=False,
                post_process=False,
                select_largest=True,
                device=self._device,
            )
            self._model = InceptionResnetV1(pretrained=pretrained).eval().to(self._device)
            self._standardize = fixed_image_standardization
        except Exception as exc:
            self._weights_error = str(exc)
            self._backend = self._fallback
            self._model = None
            self._mtcnn = None
            if self._backend == "mobilenet_v2":
                self._init_mobilenet()

    @property
    def supports_face_detection(self) -> bool:
        return self._backend == "facenet" and self._mtcnn is not None and self._model is not None

    def _init_mobilenet(self) -> None:
        try:
            from torchvision.models import MobileNet_V2_Weights, mobilenet_v2

            weights = MobileNet_V2_Weights.DEFAULT
            self._model = mobilenet_v2(weights=weights).features.eval().to(self._device)
            self._preprocess = weights.transforms()
        except Exception as exc:
            self._weights_error = str(exc)
            self._backend = self._fallback
            self._model = None
            self._preprocess = None

    def embed_image_path(self, path: str | Path) -> np.ndarray:
        image = cv2.imread(str(path))
        if image is None:
            raise FileNotFoundError(f"Could not read image: {path}")
        return self.embed_bgr(image)

    def embed_bgr(self, image: np.ndarray) -> np.ndarray:
        if self._backend == "facenet" and self._model is not None and self._mtcnn is not None:
            return self._embed_facenet(image)
        if self._backend == "mobilenet_v2" and self._model is not None:
            return self._embed_mobilenet(image)
        return self._embed_simple(image)

    def analyze_face_bgr(
        self,
        image: np.ndarray,
        min_confidence: float = 0.80,
    ) -> tuple[np.ndarray | None, tuple[int, int, int, int] | None, float | None]:
        if not self.supports_face_detection:
            return None, None, None

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        boxes, probs = self._mtcnn.detect(pil_image)
        if boxes is None or probs is None:
            return None, None, None

        best = _pick_best_face_box(boxes, probs, image.shape[:2], min_confidence)
        if best is None:
            return None, None, None

        raw_box, clipped_box, probability = best
        face = self._mtcnn.extract(pil_image, np.asarray([raw_box], dtype=np.float32), None)
        if face is None:
            return None, None, None
        if face.ndim == 3:
            face = face.unsqueeze(0)
        if not self._mtcnn.post_process and self._standardize is not None:
            face = self._standardize(face)
        face = face.to(self._device)

        with torch.no_grad():
            vector = self._model(face)[0]
            vector = F.normalize(vector, dim=0)
        return vector.detach().cpu().numpy().astype(np.float32), clipped_box, probability

    def embed_face_bgr(self, image: np.ndarray) -> np.ndarray | None:
        vector, _box, _prob = self.analyze_face_bgr(image)
        return vector

    def embed_detected_face_bgr(self, image: np.ndarray) -> np.ndarray | None:
        if image is None or image.size == 0:
            return None
        if self._backend == "facenet" and self._model is not None:
            return self._embed_detected_facenet(image)
        if self._backend == "mobilenet_v2" and self._model is not None:
            return self._embed_mobilenet(image)
        return self._embed_simple(image)

    def detect_faces_bgr(
        self,
        image: np.ndarray,
        min_confidence: float = 0.90,
        max_faces: int = 1,
    ) -> list[tuple[tuple[int, int, int, int], float]]:
        if not self.supports_face_detection:
            return []

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        boxes, probs = self._mtcnn.detect(pil_image)
        if boxes is None or probs is None:
            return []

        faces: list[tuple[tuple[int, int, int, int], float]] = []
        height, width = image.shape[:2]
        for box, prob in zip(boxes, probs):
            if prob is None or float(prob) < float(min_confidence):
                continue
            clipped_box = _clip_box(tuple(float(v) for v in box), height, width)
            if clipped_box is None:
                continue
            faces.append((clipped_box, float(prob)))

        faces.sort(key=lambda item: item[1], reverse=True)
        return faces[:max_faces]

    def _embed_facenet(self, image: np.ndarray) -> np.ndarray:
        vector, _box, _probability = self.analyze_face_bgr(image)
        if vector is None:
            return self._embed_fallback(image)
        return vector

    def _embed_detected_facenet(self, image: np.ndarray) -> np.ndarray:
        tensor = _prepare_detected_face_tensor(
            image=image,
            size=self._size,
            standardize=self._standardize,
            device=self._device,
        )
        with torch.no_grad():
            vector = self._model(tensor)[0]
            vector = F.normalize(vector, dim=0)
        return vector.detach().cpu().numpy().astype(np.float32)

    def _embed_mobilenet(self, image: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_ready = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        tensor = self._preprocess(pil_ready).unsqueeze(0).to(self._device)
        with torch.no_grad():
            feats = self._model(tensor)
            pooled = F.adaptive_avg_pool2d(feats, (1, 1)).flatten(1)
            vector = pooled[0]
            vector = F.normalize(vector, dim=0)
        return vector.detach().cpu().numpy().astype(np.float32)

    def _embed_simple(self, image: np.ndarray) -> np.ndarray:
        resized = cv2.resize(image, (self._size, self._size))
        chans = cv2.split(resized)
        parts: list[np.ndarray] = []
        for chan in chans:
            hist = cv2.calcHist([chan], [0], None, [32], [0, 256]).flatten()
            parts.append(hist)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 80, 160)
        edge_hist = cv2.calcHist([edge], [0], None, [16], [0, 256]).flatten()
        parts.append(edge_hist)
        vector = np.concatenate(parts).astype(np.float32)
        norm = np.linalg.norm(vector) + 1e-12
        return vector / norm

    def _embed_fallback(self, image: np.ndarray) -> np.ndarray:
        if self._fallback == "mobilenet_v2":
            if self._fallback_model is None:
                from torchvision.models import MobileNet_V2_Weights, mobilenet_v2

                weights = MobileNet_V2_Weights.DEFAULT
                self._fallback_model = mobilenet_v2(weights=weights).features.eval().to(self._device)
                self._fallback_preprocess = weights.transforms()
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_ready = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
            tensor = self._fallback_preprocess(pil_ready).unsqueeze(0).to(self._device)
            with torch.no_grad():
                feats = self._fallback_model(tensor)
                pooled = F.adaptive_avg_pool2d(feats, (1, 1)).flatten(1)
                vector = F.normalize(pooled[0], dim=0)
            return vector.detach().cpu().numpy().astype(np.float32)
        return self._embed_simple(image)


def _pick_best_face_box(
    boxes,
    probs,
    image_shape: tuple[int, int],
    min_confidence: float,
) -> tuple[tuple[float, float, float, float], tuple[int, int, int, int], float] | None:
    height, width = image_shape
    ranked: list[tuple[tuple[float, float, float, float], tuple[int, int, int, int], float]] = []
    for box, prob in zip(boxes, probs):
        if prob is None or float(prob) < float(min_confidence):
            continue
        raw_box = tuple(float(v) for v in box)
        clipped_box = _clip_box(raw_box, height, width)
        if clipped_box is None:
            continue
        ranked.append((raw_box, clipped_box, float(prob)))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[2], reverse=True)
    return ranked[0]


def _clip_box(
    box: tuple[float, float, float, float],
    height: int,
    width: int,
) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = box
    clipped = (
        max(0, min(width, int(round(x1)))),
        max(0, min(height, int(round(y1)))),
        max(0, min(width, int(round(x2)))),
        max(0, min(height, int(round(y2)))),
    )
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        return None
    return clipped


def _prepare_detected_face_tensor(
    image: np.ndarray,
    size: int,
    standardize,
    device: str,
):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    square = _letterbox_to_square(rgb, size)
    tensor = torch.from_numpy(square).permute(2, 0, 1).float()
    if standardize is not None:
        tensor = standardize(tensor)
    tensor = tensor.unsqueeze(0).to(device)
    return tensor


def _letterbox_to_square(image_rgb: np.ndarray, size: int) -> np.ndarray:
    height, width = image_rgb.shape[:2]
    if height <= 0 or width <= 0:
        return np.zeros((size, size, 3), dtype=np.uint8)

    scale = min(size / float(width), size / float(height))
    resized_w = max(1, int(round(width * scale)))
    resized_h = max(1, int(round(height * scale)))
    resized = cv2.resize(image_rgb, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    offset_x = (size - resized_w) // 2
    offset_y = (size - resized_h) // 2
    canvas[offset_y:offset_y + resized_h, offset_x:offset_x + resized_w] = resized
    return canvas
