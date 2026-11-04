"""Single entry point for scoring a paper against topics.

Ingestion, bulk rescoring, topic edits and the LLM pipeline all go through
`score_against_topic`, so there is exactly one definition of a score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.ranking import features
from src.ranking.model import RankerModel
from src.ranking.paper import Follows, Paper, author_matches, load_follows  # noqa: F401  (re-exported)

# Papers below this probability (and without a keyword/author hit) are not stored for a topic.
MIN_SCORE_TO_KEEP = 0.15


@dataclass
class TopicScore:
    topic_id: str
    semantic_score: float  # prior (description) probability
    final_score: float  # learned probability
    reasons: list[str]
    excluded: bool = False  # hit an exclude keyword
    has_signal: bool = False  # keyword / followed author / journal hit

    @property
    def keep(self) -> bool:
        return not self.excluded and (self.final_score >= MIN_SCORE_TO_KEEP or self.has_signal)


def excluded_by(paper: Paper, topic: Topic) -> list[str]:
    kws = features.split_keywords(topic.exclude_keywords)
    if not kws:
        return []
    text = f"{paper.title}\n{paper.abstract}".lower()
    return [k for k in kws if k in text]


def score_against_topic(
    paper: Paper,
    topic: Topic,
    model: RankerModel,
    follows: Follows,
    llm_score: float | None = None,
) -> TopicScore:
    row = features.extract(paper, topic.keywords, follows, llm_score)
    hits = excluded_by(paper, topic)
    if hits:
        return TopicScore(topic.id, 0.0, 0.0, [f"Excluded: mentions {', '.join(repr(h) for h in hits)}"], excluded=True)
    p, prior_p, reasons = model.score_row(row)
    has_signal = bool(row.details["title_hits"] or row.details["abstract_hits"] or row.details["authors"] or row.details["journal"])
    return TopicScore(topic.id, prior_p, p, reasons, has_signal=has_signal)


def score_paper(
    paper: Paper,
    topics: Iterable[Topic],
    models: dict[str, RankerModel],
    follows: Follows,
    llm_scores: dict[str, float] | None = None,
) -> list[TopicScore]:
    """Score one paper against every topic; returns only the scores worth storing."""
    out = []
    for topic in topics:
        model = models.get(topic.id)
        if model is None:
            continue
        ts = score_against_topic(paper, topic, model, follows, (llm_scores or {}).get(topic.id))
        if ts.keep:
            out.append(ts)
    return out


def apply_to_entry(entry: ItemScore, ts: TopicScore) -> None:
    entry.semantic_score = ts.semantic_score
    entry.final_score = ts.final_score
    entry.reasons = ts.reasons
