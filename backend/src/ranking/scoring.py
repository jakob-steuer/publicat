"""Single source of truth for relevance scoring.

The current scorer is the heuristic one the app shipped with (calibrated cosine
similarity + pro/anti feedback centroids + keyword, author, venue and journal
boosts). Phase 1 of the overhaul replaces the internals with a learned
per-topic ranker; the public functions below are the seam for that swap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from sqlalchemy.orm import Session

from src.embeddings import compute_cosine_similarity
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic

EMBEDDING_DIM = 768

# SPECTER2 cosine of unrelated papers is ~0.72-0.78; map that band onto 0.0.
RANDOM_BASELINE = 0.72
CALIBRATION_SLOPE = 5.0

# Papers below this score (and without any boost) are not stored at all.
MIN_SCORE_TO_KEEP = 0.20

KEYWORD_TITLE_BOOST = 0.15
KEYWORD_ABSTRACT_BOOST = 0.10

PRO_SIM_THRESHOLD = 0.80
ANTI_SIM_THRESHOLD = 0.80

HIGH_IMPACT_JOURNALS: dict[str, float] = {
    "nature": 0.15,
    "science": 0.15,
    "cell": 0.15,
    "the lancet": 0.15,
    "lancet": 0.15,
    "new england journal of medicine": 0.15,
    "nejm": 0.15,
    "jama": 0.15,
    "bmj": 0.15,
    "nature medicine": 0.15,
    "nature biotechnology": 0.15,
    "nature genetics": 0.15,
    "nature methods": 0.15,
    "cell stem cell": 0.15,
    "cancer cell": 0.15,
    "immunity": 0.15,
    "molecular cell": 0.10,
    "nature communications": 0.10,
    "science advances": 0.10,
    "pnas": 0.10,
    "proceedings of the national academy of sciences": 0.10,
    "blood": 0.10,
    "elife": 0.10,
    "nucleic acids research": 0.10,
    "genome biology": 0.10,
    "genome research": 0.10,
    "embo journal": 0.10,
    "plos biology": 0.10,
    "plos medicine": 0.10,
    "advanced science": 0.10,
    "cancer discovery": 0.15,
}


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass
class Paper:
    """The minimal view of a paper the scorer needs.

    Built either from a stored `Item` or from a raw Semantic Scholar record, so
    ingestion and rescoring feed the exact same function.
    """

    title: str
    abstract: str
    embedding: list[float] | None
    authors: list[dict[str, Any]]  # [{"name": str, "authorId": str|None, "orcid": str|None}]
    venue: str | None

    @classmethod
    def from_item(cls, item: Item) -> "Paper":
        authors = item.author_details or [{"name": a} for a in (item.authors or [])]
        return cls(
            title=item.title or "",
            abstract=item.abstract or "",
            embedding=item.embedding if _valid_embedding(item.embedding) else None,
            authors=authors,
            venue=item.venue,
        )

    @classmethod
    def from_s2(cls, paper: dict[str, Any]) -> "Paper":
        authors = []
        for a in paper.get("authors") or []:
            if not a.get("name"):
                continue
            ext = a.get("externalIds") or {}
            authors.append({"name": a["name"], "authorId": a.get("authorId"), "orcid": ext.get("ORCID")})
        emb = paper.get("embedding")
        vector = emb.get("vector") if isinstance(emb, dict) else None
        return cls(
            title=paper.get("title") or "",
            abstract=paper.get("abstract") or "",
            embedding=vector if _valid_embedding(vector) else None,
            authors=authors,
            venue=paper.get("venue"),
        )


@dataclass
class Follows:
    authors: list[tuple[str, str, float]] = field(default_factory=list)  # (entity_value, display_name, boost)
    venues: dict[str, float] = field(default_factory=dict)


@dataclass
class TopicScore:
    topic_id: str
    semantic_score: float
    final_score: float
    reasons: list[str]
    keyword_boost: float


def _valid_embedding(vec: Any) -> bool:
    return isinstance(vec, list) and len(vec) == EMBEDDING_DIM


# --------------------------------------------------------------------------- #
# Loading context from the database
# --------------------------------------------------------------------------- #
def load_follows(db: Session) -> Follows:
    follows = db.query(Follow).all()
    return Follows(
        authors=[(f.entity_value, f.display_name or f.entity_value, f.boost_value) for f in follows if f.entity_type == "author"],
        venues={f.entity_value.lower(): f.boost_value for f in follows if f.entity_type == "venue"},
    )


def compute_topic_vectors(db: Session, topics: Iterable[Topic]) -> dict[str, dict[str, list[float] | None]]:
    """Mean embedding of positively voted (pro) and downvoted (anti) papers per topic."""
    vectors: dict[str, dict[str, list[float] | None]] = {}
    for topic in topics:
        rows = (
            db.query(ItemScore.user_vote, Item.embedding)
            .join(Item, ItemScore.item_id == Item.id)
            .filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None), Item.embedding.isnot(None))
            .all()
        )
        pro = [emb for vote, emb in rows if vote >= 1 and _valid_embedding(emb)]
        anti = [emb for vote, emb in rows if vote == -1 and _valid_embedding(emb)]
        vectors[topic.id] = {"pro": _unit_mean(pro), "anti": _unit_mean(anti)}
    return vectors


def _unit_mean(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    mean = np.mean(np.asarray(vectors, dtype=float), axis=0)
    norm = np.linalg.norm(mean)
    return (mean / norm).tolist() if norm > 0 else mean.tolist()


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def calibrate(raw_cosine: float) -> float:
    return max(0.0, min(1.0, (raw_cosine - RANDOM_BASELINE) * CALIBRATION_SLOPE))


def author_matches(entity_value: str, authors: list[dict[str, Any]]) -> bool:
    """Match a follow (AUTHOR_ID:..., ORCID:... or a legacy plain name) against a paper's authors."""
    if entity_value.startswith("AUTHOR_ID:"):
        wanted = entity_value.split(":", 1)[1]
        return any(str(a.get("authorId")) == wanted for a in authors)
    if entity_value.startswith("ORCID:"):
        wanted = entity_value.split(":", 1)[1].lower()
        return any(wanted and wanted in str(a.get("orcid") or "").lower() for a in authors)
    needle = entity_value.lower()
    return any(needle in str(a.get("name") or "").lower() for a in authors)


def global_boost(paper: Paper, follows: Follows) -> tuple[float, list[str]]:
    """Topic-independent boosts: followed authors, followed venues, high-impact journals."""
    boost = 0.0
    reasons: list[str] = []
    for entity_value, _display, value in follows.authors:
        if author_matches(entity_value, paper.authors):
            boost += value
            reasons.append(f"Followed author boost (+{value})")
    if paper.venue:
        venue = paper.venue.lower()
        for followed_venue, value in follows.venues.items():
            if followed_venue in venue:
                boost += value
                reasons.append(f"Followed venue boost (+{value})")
        journal_boost = HIGH_IMPACT_JOURNALS.get(venue, 0.0)
        if journal_boost > 0:
            boost += journal_boost
            reasons.append(f"High-impact journal boost (+{journal_boost})")
    return boost, reasons


def keyword_boost(paper: Paper, keywords: str | None) -> tuple[float, list[str]]:
    if not keywords:
        return 0.0, []
    boost = 0.0
    reasons: list[str] = []
    title = paper.title.lower()
    abstract = paper.abstract.lower()
    for kw in (k.strip().lower() for k in keywords.split(",")):
        if not kw:
            continue
        base = kw[:-1] if kw.endswith("s") else kw  # loose singular/plural match
        if base in title:
            boost += KEYWORD_TITLE_BOOST
            reasons.append(f"Keyword in title ('{kw}', +{KEYWORD_TITLE_BOOST})")
        elif base in abstract:
            boost += KEYWORD_ABSTRACT_BOOST
            reasons.append(f"Keyword in abstract ('{kw}', +{KEYWORD_ABSTRACT_BOOST})")
    return boost, reasons


def score_against_topic(
    paper: Paper,
    topic: Topic,
    topic_vectors: dict[str, dict[str, list[float] | None]],
    boost: float,
    boost_reasons: list[str],
) -> TopicScore | None:
    if not topic.embedding or paper.embedding is None:
        return None

    sim = calibrate(compute_cosine_similarity(paper.embedding, topic.embedding))
    reasons: list[str] = []

    vectors = topic_vectors.get(topic.id, {})
    pro = vectors.get("pro")
    anti = vectors.get("anti")
    if pro:
        pro_sim = compute_cosine_similarity(paper.embedding, pro)
        if pro_sim > PRO_SIM_THRESHOLD:
            amount = min(0.3, (pro_sim - PRO_SIM_THRESHOLD) * 2.0)
            sim = min(1.0, sim + amount)
            reasons.append(f"Pro-topic similarity (+{amount:.2f})")
    if anti:
        anti_sim = compute_cosine_similarity(paper.embedding, anti)
        if anti_sim > ANTI_SIM_THRESHOLD:
            penalty = min(0.5, (anti_sim - ANTI_SIM_THRESHOLD) * 3.0)
            sim = max(0.0, sim - penalty)
            reasons.append(f"Anti-topic penalty (-{penalty:.2f})")

    kw_boost, kw_reasons = keyword_boost(paper, topic.keywords)
    final = min(1.0, sim + boost + kw_boost)
    return TopicScore(
        topic_id=topic.id,
        semantic_score=sim,
        final_score=final,
        reasons=[f"Semantic match to '{topic.name}' ({sim:.2f})"] + boost_reasons + reasons + kw_reasons,
        keyword_boost=kw_boost,
    )


def score_paper(
    paper: Paper,
    topics: Iterable[Topic],
    topic_vectors: dict[str, dict[str, list[float] | None]],
    follows: Follows,
) -> tuple[list[TopicScore], float, float]:
    """Score one paper against every active topic.

    Returns (scores worth storing, max final score, topic-independent boost).
    A score is worth storing when it clears MIN_SCORE_TO_KEEP or carries any boost.
    """
    boost, boost_reasons = global_boost(paper, follows)
    kept: list[TopicScore] = []
    max_final = 0.0
    for topic in topics:
        ts = score_against_topic(paper, topic, topic_vectors, boost, boost_reasons)
        if ts is None:
            continue
        max_final = max(max_final, ts.final_score)
        if ts.final_score >= MIN_SCORE_TO_KEEP or boost > 0.0 or ts.keyword_boost > 0.0:
            kept.append(ts)
    return kept, max_final, boost


def should_keep(max_final: float, boost: float) -> bool:
    return max_final >= MIN_SCORE_TO_KEEP or boost > 0.0


def apply_llm_relevance(score: ItemScore, llm_score: float, reason: str) -> None:
    """Fold the Stage 2 LLM judgement into an existing score without discarding the boosts.

    The semantic part is scaled by 0.5x..1.5x; keyword/author/journal boosts
    (everything above the semantic score) are carried over unchanged.
    """
    extras = max(0.0, (score.final_score or 0.0) - (score.semantic_score or 0.0))
    score.llm_relevance_score = float(llm_score)
    multiplier = 0.5 + (score.llm_relevance_score / 100.0)
    score.final_score = min(1.0, score.semantic_score * multiplier + extras)
    score.reasons = list(score.reasons or []) + [f"LLM relevance: {int(llm_score)}/100. {reason}"]
