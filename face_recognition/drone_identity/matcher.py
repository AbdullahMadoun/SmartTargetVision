from __future__ import annotations

from collections import defaultdict, deque

import numpy as np


class TemporalMatcher:
    def __init__(self, threshold: float, window: int) -> None:
        self._threshold = float(threshold)
        self._window = int(window)
        self._buffers: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self._window)
        )

    def compare(self, query: np.ndarray, enrolled: np.ndarray, key: str) -> tuple[float, float, bool]:
        similarity = float(np.dot(query, enrolled) / ((np.linalg.norm(query) * np.linalg.norm(enrolled)) + 1e-12))
        buf = self._buffers[key]
        buf.append(similarity)
        smoothed = float(sum(buf) / len(buf))
        return similarity, smoothed, smoothed >= self._threshold

    def clear(self, key: str) -> None:
        self._buffers.pop(key, None)
