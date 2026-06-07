import os
import numpy as np
from sentence_transformers import SentenceTransformer

# Disable tokenizer parallelism to prevent multiprocessing semaphore leaks on MacOS
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Load the model globally so it stays in memory
# Apple Silicon natively supports the 'mps' device
device = "mps" if os.uname().sysname == "Darwin" and os.uname().machine == "arm64" else "cpu"
model = SentenceTransformer('allenai/specter2_base', device=device)

def get_embedding(text: str) -> list[float]:
    """Generates an embedding vector for the provided text."""
    # Ensure it's a single string, encode and convert to list
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()

def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Computes the cosine similarity between two embedding vectors."""
    a = np.array(vec1)
    b = np.array(vec2)
    
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return float(np.dot(a, b) / (norm_a * norm_b))
