import os
import threading

import numpy as np

# Disable tokenizer parallelism to prevent multiprocessing semaphore leaks on macOS
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# The SPECTER2 model (and PyTorch) is only needed to embed topic descriptions and
# the rare paper Semantic Scholar has no embedding for. Load it lazily so server
# start-up and tests do not pay for it.
_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                device = "mps" if os.uname().sysname == "Darwin" and os.uname().machine == "arm64" else "cpu"
                _model = SentenceTransformer("allenai/specter2_base", device=device)
    return _model


def get_embedding(text: str) -> list[float]:
    """Generates an embedding vector for the provided text."""
    embedding = _load_model().encode(text, convert_to_numpy=True)
    return embedding.tolist()


def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Computes the cosine similarity between two embedding vectors."""
    a = np.asarray(vec1, dtype=float)
    b = np.asarray(vec2, dtype=float)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
