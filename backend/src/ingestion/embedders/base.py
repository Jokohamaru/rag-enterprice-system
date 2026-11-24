from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Literal

import numpy as np

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY"]


def l2_normalize(vector: list[float]) -> list[float]:
    """L2-normalize a dense vector so dot product equals cosine similarity."""
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-12:
        return arr.tolist()
    return (arr / norm).tolist()


class EmbeddingProvider(ABC):
    """Abstract Bi-Encoder embedding interface."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: list[str], *, task_type: TaskType = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, query: str) -> list[float]:
        vectors = self.embed_texts([query], task_type="RETRIEVAL_QUERY")
        return vectors[0] if vectors else [0.0] * self.dimension


class MockEmbedder(EmbeddingProvider):
    """Deterministic local n-gram hashing embedder for offline tests (zero API cost)."""

    def __init__(self, dim: int = 768) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: list[str], *, task_type: TaskType = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            tokens = re.findall(r"\w+", text.lower())
            if not tokens:
                vec[0] = 1.0
                out.append(vec)
                continue
            # Use unigrams + character trigrams so semantically/lexically close strings align
            features = list(tokens)
            for tok in tokens:
                if len(tok) >= 3:
                    features.extend(tok[i : i + 3] for i in range(len(tok) - 2))
            for feat in features:
                digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self._dim
                sign = 1.0 if (digest[4] & 1) == 0 else -1.0
                vec[idx] += sign / math.sqrt(max(len(features), 1))
            out.append(l2_normalize(vec))
        return out
