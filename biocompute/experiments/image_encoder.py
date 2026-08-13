"""Image Encoder: Maps image pixels to neural reservoir input features / spike vectors.

Takes raw image bytes, PNG, JPG, or 2D numpy array -> resizes/normalizes -> extracts spatial feature vector -> projects to biocompute input channels.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np


class ImageToNeuralEncoder:
    """Encodes 2D images into feature vectors or spike rate drives for biocompute models."""

    def __init__(self, target_size: tuple[int, int] = (28, 28), n_channels: int = 16, seed: int = 42):
        self.target_size = target_size
        self.n_channels = n_channels
        self.seed = seed
        rng = np.random.default_rng(seed)
        n_pixels = target_size[0] * target_size[1]
        self.proj = rng.uniform(-1.0, 1.0, size=(n_channels, n_pixels)).astype(np.float32)

    def decode_image_bytes(self, image_bytes: bytes) -> np.ndarray:
        """Decode raw image bytes (PNG, JPG, JPEG) to a normalized grayscale 2D array."""
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("L")
            img = img.resize(self.target_size)
            return np.asarray(img, dtype=np.float32) / 255.0
        except ImportError:
            try:
                import cv2

                arr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    raise ValueError("Failed to decode image using OpenCV.")
                img = cv2.resize(img, self.target_size)
                return img.astype(np.float32) / 255.0
            except ImportError:
                # Basic fallback assuming raw float array
                arr = np.frombuffer(image_bytes, dtype=np.float32)
                side = int(np.sqrt(len(arr)))
                return arr.reshape((side, side))

    def encode(self, image_2d: np.ndarray) -> np.ndarray:
        """Flatten 2D image and project into channel feature vector."""
        flat = image_2d.flatten().astype(np.float32)
        if len(flat) != self.proj.shape[1]:
            # Simple linear resize if needed
            flat = np.interp(
                np.linspace(0, len(flat), self.proj.shape[1]),
                np.arange(len(flat)),
                flat
            ).astype(np.float32)
        return np.tanh(self.proj @ flat)

    def encode_to_spike_rates(self, image_2d: np.ndarray, max_rate_hz: float = 100.0) -> np.ndarray:
        """Map image spatial features to per-channel firing rates (Hz)."""
        feats = self.encode(image_2d)
        rates = (feats + 1.0) * 0.5 * max_rate_hz
        return rates.astype(np.float32)
