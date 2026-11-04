import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import SessionLocal, get_db
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.models.topic_model import TopicModel
from src.ranking.paper import load_follows
from src.ranking.topic_vector import build_prior_vector
from src.ranking.training import is_busy, mark_busy, rescore_topic, train_topic
from src.schemas.topic import TopicCreate, TopicModelStats, TopicResponse, TopicUpdate
from src.sources.semantic_scholar import search_papers_s2

router = APIRouter(prefix="/topics", tags=["topics"])


def _topic_text(name: str, description: str, keywords: Optional[str]) -> str:
    text = f"{name}. {description}"
    if keywords:
        text += f". Keywords: {keywords}"
    return text


def _local_embedding(text: str) -> Optional[list]:
    """Legacy local SPECTER2 vector; optional (returns None without torch / model)."""
    try:
        from src.embeddings import get_embedding

        return get_embedding(text)
    except Exception as e:
        print(f"Local topic embedding skipped: {e}")
        return None


def _response(topic: Topic) -> dict:
    d = {c.name: getattr(topic, c.name) for c in Topic.__table__.columns if c.name not in ("embedding", "prior_vector")}
    d["has_prior_vector"] = bool(topic.prior_vector or topic.embedding)
    return d


async def prepare_topic(topic_id: str, rescore_all: bool, then_sync_days: Optional[int] = None) -> None:
    """Background: build the S2-space topic vector, train, rescore, optionally fetch."""
    db = SessionLocal()
    try:
        topic = db.get(Topic, topic_id)
        if not topic:
            return
        vector, source = await build_prior_vector(topic)
        if vector is not None:
            topic.prior_vector = vector
            db.commit()
        print(f"Topic '{topic.name}': prior vector from {source}", flush=True)

        def train_and_rescore():
            mark_busy(topic_id, True)
            try:
                follows = load_follows(db)
                model = train_topic(db, topic, follows)
                n = rescore_topic(db, topic, model, follows, all_items=rescore_all)
                print(f"Topic '{topic.name}': scored {n} papers (CV AUC {model.cv_auc})", flush=True)
            finally:
                mark_busy(topic_id, False)

        await asyncio.to_thread(train_and_rescore)

        if then_sync_days:
            from src.api.items import full_sync

            await full_sync(db, days_back=then_sync_days)
    except Exception as e:
        print(f"prepare_topic failed for {topic_id}: {e!r}", flush=True)
    finally:
        db.close()


@router.post("/", response_model=TopicResponse)
def create_topic(topic_in: TopicCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    data = topic_in.model_dump()
    data["seed_papers"] = [s for s in (data.get("seed_papers") or [])] or None
    db_topic = Topic(
        **data,
        embedding=_local_embedding(_topic_text(topic_in.name, topic_in.description, topic_in.keywords)),
        user_id="1",  # single-user MVP
    )
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    background_tasks.add_task(prepare_topic, db_topic.id, True, 30)
    return _response(db_topic)


@router.get("/", response_model=List[TopicResponse])
def read_topics(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return [_response(t) for t in db.query(Topic).filter(Topic.user_id == "1").offset(skip).limit(limit).all()]


@router.get("/models", response_model=Dict[str, TopicModelStats])
def read_models(db: Session = Depends(get_db)):
    """Training state of every topic's ranker (for the topic settings page)."""
    out = {}
    for topic in db.query(Topic).filter(Topic.user_id == "1").all():
        row = db.get(TopicModel, topic.id)
        out[topic.id] = TopicModelStats(
            topic_id=topic.id,
            trained=bool(row and row.payload.get("trained_at")),
            n_pos=row.n_pos if row else 0,
            n_neg=row.n_neg if row else 0,
            cv_auc=row.cv_auc if row else None,
            trained_at=row.trained_at if row else None,
            prior_source="seeds" if topic.seed_papers else ("s2_search" if topic.prior_vector else ("local" if topic.embedding else None)),
            extra={
                "labels": db.query(ItemScore).filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None)).count(),
                "busy": is_busy(topic.id),
            },
        )
    return out


def _leaked_items(db: Session) -> dict[str, list[ItemScore]]:
    """Items whose identical vote was written to several topics by the old overview voting.

    Signature: >= 2 voted rows for the item, all carrying the same vote.
    """
    rows = db.query(ItemScore).filter(ItemScore.user_vote.isnot(None)).all()
    by_item: dict[str, list[ItemScore]] = {}
    for s in rows:
        by_item.setdefault(s.item_id, []).append(s)
    return {iid: ss for iid, ss in by_item.items() if len(ss) >= 2 and len({x.user_vote for x in ss}) == 1}


@router.get("/vote_leaks", response_model=dict)
def vote_leaks(db: Session = Depends(get_db)):
    leaked = _leaked_items(db)
    return {"items": len(leaked), "rows": sum(len(v) for v in leaked.values())}


@router.post("/repair_votes", response_model=dict)
def repair_votes(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Keep each leaked vote only on the topic it fits best (highest description score), clear the copies, retrain."""
    leaked = _leaked_items(db)
    cleared = 0
    touched: set[str] = set()
    for scores in leaked.values():
        keep = max(scores, key=lambda s: (s.semantic_score or 0.0, s.final_score or 0.0))
        for s in scores:
            touched.add(s.topic_id)
            if s is not keep:
                s.user_vote = None
                s.voted_at = None
                cleared += 1
    db.commit()
    for topic_id in touched:
        background_tasks.add_task(prepare_topic, topic_id, False, None)
    return {"status": "success", "items": len(leaked), "cleared_rows": cleared, "retraining_topics": len(touched)}


@router.get("/search_papers", response_model=List[Dict[str, Any]])
async def search_papers(q: str, limit: int = 8):
    """Semantic Scholar search for picking seed papers."""
    results = await search_papers_s2(q, limit=limit)
    return [
        {
            "paperId": r.get("paperId"),
            "title": r.get("title"),
            "year": r.get("year"),
            "venue": r.get("venue"),
            "authors": [a.get("name") for a in (r.get("authors") or [])][:4],
        }
        for r in results
        if r.get("paperId")
    ]


@router.put("/{topic_id}", response_model=TopicResponse)
def update_topic(topic_id: str, topic_in: TopicUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == "1").first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    changes = topic_in.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(topic, key, value)
    if any(k in changes for k in ("name", "description", "keywords")):
        topic.embedding = _local_embedding(_topic_text(topic.name, topic.description, topic.keywords))
    db.commit()
    db.refresh(topic)
    background_tasks.add_task(prepare_topic, topic.id, True, None)
    return _response(topic)


@router.post("/{topic_id}/retrain", response_model=dict)
def retrain(topic_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Topic, topic_id):
        raise HTTPException(status_code=404, detail="Topic not found")
    background_tasks.add_task(prepare_topic, topic_id, True, None)
    return {"status": "scheduled"}


@router.delete("/{topic_id}")
def delete_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == "1").first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.query(ItemScore).filter(ItemScore.topic_id == topic_id).delete(synchronize_session=False)
    db.query(TopicModel).filter(TopicModel.topic_id == topic_id).delete(synchronize_session=False)
    db.delete(topic)
    db.commit()
    return {"status": "success"}
