import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from src.embeddings import get_embedding, compute_cosine_similarity

topic1 = "Foundation Models in Life Sciences. Foundation models (like LLMs or transformers) applied to genomics, proteins, and biology."
topic2 = "IsoPepTracker: An interactive web application for peptide-driven isoform analysis. IsoPepTracker is a web application for analyzing differential peptides across isoforms."
topic3 = "TESSERA (Tumour Embeddings via Self-Supervised Encoding), a foundation model for the cancer genome. Pretrain it on somatic variants."

e1 = get_embedding(topic1)
e2 = get_embedding(topic2)
e3 = get_embedding(topic3)

print("Topic vs IsoPep:", compute_cosine_similarity(e1, e2))
print("Topic vs TESSERA:", compute_cosine_similarity(e1, e3))
print("IsoPep vs TESSERA:", compute_cosine_similarity(e2, e3))
