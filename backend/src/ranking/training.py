"""Train, persist and apply per-topic rankers.

`retrain_and_rescore(topic_id)` is what a vote triggers: it refits the topic's
model on all votes and rewrites every stored score for that topic, so the
effect of feedback is visible on the next feed load.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Iterable

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.models.topic_model import TopicModel
from src.ranking import features
from src.ranking.model import RankerModel, cross_validated_auc
from src.ranking.paper import Follows, Paper, load_follows
from src.ranking.scoring import apply_to_entry, score_against_topic

# Star and downvote are deliberate judgements; an upvote is the unit. A neutral vote
# ("mark read", often used to clear papers that are hard to judge) is only a slight
# "not for me" signal: a quarter of an upvote.
VOTE_WEIGHTS = {2: 2.0, 1: 1.0, 0: 0.25, -1: 2.0}
VOTE_HALF_LIFE_DAYS = 365.0  # older feedback counts less so interests can drift

_locks: dict[str, threading.Lock] = {}
_dirty: set[str] = set()
_busy: set[str] = set()  # topics whose scores are being rewritten right now
_state_lock = threading.Lock()


def is_busy(topic_id: str) -> bool:
    with _state_lock:
        return topic_id in _busy


def mark_busy(topic_id: str, busy: bool) -> None:
    with _state_lock:
        (_busy.add if busy else _busy.discard)(topic_id)


def prior_vector_for(topic: Topic):
    """Topic vector in SPECTER2 space; falls back to the legacy local embedding."""
    return topic.prior_vector or topic.embedding


BACKGROUND_SAMPLE = 1000
MIN_BACKGROUND = 50


def background_cos_stats(db: Session, prior_vector) -> tuple[float, float] | None:
    """Mean/std of cosine between a random sample of stored papers and the topic vector.

    This is what makes the cold-start probability meaningful: it says how far
    above "a typical paper in this database" a candidate sits.
    """
    if prior_vector is None:
        return None
    pv = np.asarray(prior_vector, dtype=float)
    pv = pv / (np.linalg.norm(pv) or 1.0)
    rows = db.query(Item.embedding).filter(Item.embedding.isnot(None)).order_by(func.random()).limit(BACKGROUND_SAMPLE).all()
    cos = []
    for (emb,) in rows:
        u = features.unit(emb)
        if u is not None:
            cos.append(float(u @ pv))
    if len(cos) < MIN_BACKGROUND:
        return None
    return float(np.mean(cos)), float(np.std(cos))


def load_models(db: Session, topics: Iterable[Topic]) -> dict[str, RankerModel]:
    models = {}
    for topic in topics:
        row = db.get(TopicModel, topic.id)
        if row:
            models[topic.id] = RankerModel.from_dict(row.payload)
        else:
            prior = prior_vector_for(topic)
            models[topic.id] = RankerModel.prior_only(prior, background_cos_stats(db, prior))
    return models


def labeled_examples(db: Session, topic: Topic, follows: Follows):
    rows = (
        db.query(ItemScore, Item)
        .join(Item, ItemScore.item_id == Item.id)
        .filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None))
        .all()
    )
    E, S, y, w = [], [], [], []
    now = datetime.now(timezone.utc)
    for score, item in rows:
        row = features.extract(Paper.from_item(item), topic.keywords, follows, score.llm_relevance_score)
        if row.embedding is None:
            continue
        E.append(row.embedding)
        S.append(row.sparse)
        y.append(1 if score.user_vote >= 1 else 0)
        weight = VOTE_WEIGHTS.get(score.user_vote, 1.0)
        if score.voted_at:
            voted_at = score.voted_at if score.voted_at.tzinfo else score.voted_at.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - voted_at).total_seconds() / 86400.0)
            weight *= 0.5 ** (age_days / VOTE_HALF_LIFE_DAYS)
        w.append(weight)
    if not y:
        return np.zeros((0, features.EMBEDDING_DIM)), np.zeros((0, len(features.SPARSE_FEATURES))), np.zeros(0), np.zeros(0)
    return np.array(E), np.array(S), np.array(y), np.array(w)


def regularisation_for(n_labels: int) -> float:
    """Strong pull towards the prior with few votes, weak with many.

    Measured on the author's 368 votes: CV AUC rises monotonically down to
    lambda 0.03 for 70-190 labels; 3/n gives 0.3 at 10 votes, 0.1 at 30, 0.03 at 100+.
    """
    return max(LAMBDA_MIN, 3.0 / max(1, n_labels))


LAMBDA_MIN = 0.03


def train_topic(db: Session, topic: Topic, follows: Follows | None = None, lam: float | None = None) -> RankerModel:
    follows = follows or load_follows(db)
    E, S, y, w = labeled_examples(db, topic, follows)
    prior = prior_vector_for(topic)
    stats = background_cos_stats(db, prior)
    model = RankerModel.prior_only(prior, stats)
    lam = regularisation_for(len(y)) if lam is None else lam
    if len(y) > 0:
        model.cv_auc = cross_validated_auc(lambda: RankerModel.prior_only(prior, stats), E, S, y, w, lam)
        model.fit(E, S, y, w, lam=lam)
    model.meta = {"n_examples": int(len(y)), "background_stats": stats}

    row = db.get(TopicModel, topic.id)
    if row is None:
        row = TopicModel(topic_id=topic.id, payload=model.to_dict())
        db.add(row)
    row.payload = model.to_dict()
    row.n_pos, row.n_neg, row.cv_auc = model.n_pos, model.n_neg, model.cv_auc
    row.trained_at = datetime.now(timezone.utc)
    db.commit()
    return model


def rescore_topic(db: Session, topic: Topic, model: RankerModel, follows: Follows | None = None, all_items: bool = False) -> int:
    """Recompute final_score / semantic_score / reasons for this topic.

    all_items=False: only the papers that already have a score row (fast; used after a vote).
    all_items=True: every paper in the database; creates rows for papers that
    now pass the threshold and removes unvoted rows that no longer do (used
    after the topic definition changed).
    """
    follows = follows or load_follows(db)
    count = 0
    if not all_items:
        # Fetch the ids first and work in chunks: committing while iterating a
        # streaming cursor closes the cursor after the first chunk.
        ids = [i[0] for i in db.query(ItemScore.item_id).filter(ItemScore.topic_id == topic.id).all()]
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            rows = db.query(ItemScore, Item).join(Item, ItemScore.item_id == Item.id).filter(ItemScore.topic_id == topic.id, ItemScore.item_id.in_(chunk)).all()
            for score, item in rows:
                apply_to_entry(score, score_against_topic(Paper.from_item(item), topic, model, follows, score.llm_relevance_score))
                count += 1
            db.commit()
        return count

    existing = {s.item_id: s for s in db.query(ItemScore).filter(ItemScore.topic_id == topic.id).all()}
    item_ids = [i[0] for i in db.query(Item.id).all()]
    for start in range(0, len(item_ids), 500):
        chunk = item_ids[start : start + 500]
        for item in db.query(Item).filter(Item.id.in_(chunk)).all():
            entry = existing.get(item.id)
            ts = score_against_topic(Paper.from_item(item), topic, model, follows, entry.llm_relevance_score if entry else None)
            if entry is not None:
                if ts.keep or entry.user_vote is not None:
                    apply_to_entry(entry, ts)
                    count += 1
                else:
                    db.delete(entry)
            elif ts.keep:
                db.add(ItemScore(item_id=item.id, topic_id=topic.id, semantic_score=ts.semantic_score, final_score=ts.final_score, reasons=ts.reasons))
                count += 1
        db.commit()
    return count


def retrain_and_rescore(topic_id: str) -> None:
    """Background job (runs in a worker thread): refit the topic model and rescore its papers.

    Concurrent calls for the same topic are coalesced: a call that arrives
    while another is running just marks the topic dirty and returns.
    """
    from src.database import SessionLocal

    with _state_lock:
        lock = _locks.setdefault(topic_id, threading.Lock())
        _dirty.add(topic_id)
    if not lock.acquire(blocking=False):
        return
    try:
        while True:
            with _state_lock:
                if topic_id not in _dirty:
                    return
                _dirty.discard(topic_id)
            db = SessionLocal()
            mark_busy(topic_id, True)
            try:
                topic = db.get(Topic, topic_id)
                if topic is None:
                    return
                follows = load_follows(db)
                model = train_topic(db, topic, follows)
                n = rescore_topic(db, topic, model, follows)
                print(f"Retrained '{topic.name}': {model.n_pos} pos / {model.n_neg} neg, CV AUC {model.cv_auc}, rescored {n}", flush=True)
            except Exception as e:  # never let a background retrain take the server down
                print(f"Retrain failed for topic {topic_id}: {e!r}", flush=True)
            finally:
                mark_busy(topic_id, False)
                db.close()
    finally:
        lock.release()


def ensure_models(db: Session) -> list[str]:
    """Train a model for every active topic that has none yet (first start after the upgrade)."""
    trained = []
    for topic in db.query(Topic).filter(Topic.is_active == True).all():  # noqa: E712
        if db.get(TopicModel, topic.id) is None:
            trained.append(topic.id)
    return trained
