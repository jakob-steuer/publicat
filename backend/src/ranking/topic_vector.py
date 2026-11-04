"""Build a topic's prior vector in Semantic Scholar's SPECTER2 space.

Papers are compared against this vector, so it must come from the same
embedding model as the papers (the S2 API), not from a locally run model.
Sources, in order of preference:
  1. the seed papers the user picked for the topic,
  2. the top Semantic Scholar search hits for the topic name and keywords.
Votes deliberately do not enter the prior: they enter through training, which
keeps "matches the topic description" and "learned from your votes" separate.
"""
from __future__ import annotations

import numpy as np

from src.models.topic import Topic
from src.ranking.features import EMBEDDING_DIM, split_keywords
from src.sources.semantic_scholar import enrich_papers_s2, search_papers_s2

SEARCH_SEEDS = 10


def _unit_mean(vectors: list[list[float]]) -> list[float] | None:
    arr = [np.asarray(v, dtype=float) for v in vectors if v is not None and len(v) == EMBEDDING_DIM]
    if not arr:
        return None
    units = [a / np.linalg.norm(a) for a in arr if np.linalg.norm(a) > 0]
    mean = np.mean(units, axis=0)
    norm = np.linalg.norm(mean)
    return (mean / norm).tolist() if norm > 0 else None


def _vectors(papers: list[dict]) -> list[list[float]]:
    out = []
    for p in papers or []:
        emb = (p or {}).get("embedding")
        if isinstance(emb, dict) and emb.get("vector"):
            out.append(emb["vector"])
    return out


async def build_prior_vector(topic: Topic) -> tuple[list[float] | None, str]:
    """Returns (vector, source) where source is 'seeds', 'search' or 'none'."""
    seed_ids = [s.get("paperId") for s in (topic.seed_papers or []) if s.get("paperId")]
    if seed_ids:
        vecs = _vectors(await enrich_papers_s2(seed_ids))
        v = _unit_mean(vecs)
        if v is not None:
            return v, "seeds"

    query = topic.name
    kws = split_keywords(topic.keywords)
    if kws:
        query = f"{topic.name} {' '.join(kws[:3])}"
    hits = await search_papers_s2(query, limit=SEARCH_SEEDS, fields="paperId")
    ids = [h["paperId"] for h in hits if h.get("paperId")]
    if ids:
        v = _unit_mean(_vectors(await enrich_papers_s2(ids)))
        if v is not None:
            return v, "search"
    return None, "none"
