"""Feature extraction for the per-topic ranker.

A paper is represented by its unit-normalised Semantic Scholar SPECTER2
embedding (768 floats) plus a handful of sparse, human-readable features.
Everything here is pure Python/NumPy so it can be ported to the mobile client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.ranking.paper import Follows, Paper, author_matches

EMBEDDING_DIM = 768

SPARSE_FEATURES = ["kw_title", "kw_abstract", "followed_author", "journal_tier", "is_preprint", "llm_score", "has_llm"]

# Sensible default weights (logits) before the user has voted. Learned weights
# are regularised towards these, so with few labels the ranker behaves like a
# tidy version of the old heuristic and drifts as evidence accumulates.
PRIOR_SPARSE_WEIGHTS = np.array([0.7, 0.4, 1.0, 3.0, 0.0, 3.0, 0.0])

HIGH_IMPACT_JOURNALS: dict[str, float] = {
    "nature": 0.15, "science": 0.15, "cell": 0.15, "the lancet": 0.15, "lancet": 0.15,
    "new england journal of medicine": 0.15, "nejm": 0.15, "jama": 0.15, "bmj": 0.15,
    "nature medicine": 0.15, "nature biotechnology": 0.15, "nature genetics": 0.15,
    "nature methods": 0.15, "cell stem cell": 0.15, "cancer cell": 0.15, "immunity": 0.15,
    "cancer discovery": 0.15,
    "molecular cell": 0.10, "nature communications": 0.10, "science advances": 0.10,
    "pnas": 0.10, "proceedings of the national academy of sciences": 0.10, "blood": 0.10,
    "elife": 0.10, "nucleic acids research": 0.10, "genome biology": 0.10,
    "genome research": 0.10, "embo journal": 0.10, "plos biology": 0.10,
    "plos medicine": 0.10, "advanced science": 0.10,
}


@dataclass
class FeatureRow:
    embedding: np.ndarray | None  # unit vector or None when the paper has no embedding
    sparse: np.ndarray  # len(SPARSE_FEATURES)
    details: dict[str, Any] = field(default_factory=dict)  # for explanations


def split_keywords(keywords: str | None) -> list[str]:
    return [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    text = text.lower()
    hits = []
    for kw in keywords:
        base = kw[:-1] if kw.endswith("s") else kw  # loose singular/plural match
        if base and base in text:
            hits.append(kw)
    return hits


def unit(vec) -> np.ndarray | None:
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=float)
    if arr.shape != (EMBEDDING_DIM,):
        return None
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else None


def extract(paper: Paper, keywords: str | None, follows: Follows, llm_score: float | None = None) -> FeatureRow:
    kws = split_keywords(keywords)
    title_hits = keyword_hits(paper.title, kws)
    abstract_hits = [k for k in keyword_hits(paper.abstract, kws) if k not in title_hits]

    matched_authors = [display for value, display, _boost in follows.authors if author_matches(value, paper.authors)]
    venue = (paper.venue or "").lower()
    journal_tier = HIGH_IMPACT_JOURNALS.get(venue, 0.0)
    followed_venue = any(v in venue for v in follows.venues) if venue else False
    if followed_venue:
        journal_tier = max(journal_tier, 0.15)

    sparse = np.array(
        [
            min(len(title_hits), 3),
            min(len(abstract_hits), 3),
            1.0 if matched_authors else 0.0,
            journal_tier,
            1.0 if paper.is_preprint else 0.0,
            (llm_score / 100.0 - 0.5) if llm_score is not None else 0.0,
            1.0 if llm_score is not None else 0.0,
        ],
        dtype=float,
    )
    return FeatureRow(
        embedding=unit(paper.embedding),
        sparse=sparse,
        details={
            "title_hits": title_hits,
            "abstract_hits": abstract_hits,
            "authors": matched_authors,
            "journal": paper.venue if journal_tier > 0 else None,
            "preprint": paper.is_preprint,
            "llm_score": llm_score,
        },
    )
