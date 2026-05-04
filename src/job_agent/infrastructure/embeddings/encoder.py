"""Local sentence-transformers embedding encoder.

Downloads the model on first use (~1.3 GB for bge-large-en-v1.5).
Subsequent runs reuse the cached model from ~/.cache/huggingface/.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

log = structlog.get_logger()

_DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"


class EmbeddingEncoder:
    """Wraps SentenceTransformer with lazy loading and batch encoding."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None

    def _model_instance(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            log.info("embeddings.loading_model", model=self._model_name)
            self._model = SentenceTransformer(self._model_name)
            log.info("embeddings.model_ready", model=self._model_name)
        return self._model

    def encode(self, text: str) -> list[float]:
        vec = self._model_instance().encode(text, normalize_embeddings=True)
        return list(vec.tolist())

    def encode_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        model = self._model_instance()
        vecs = model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=True
        )
        return [v.tolist() for v in vecs]

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        return float(np.dot(va, vb) / denom) if denom > 0 else 0.0
