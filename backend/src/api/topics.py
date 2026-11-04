from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import SessionLocal, get_db
from src.embeddings import get_embedding
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.ranking.scoring import Paper, compute_topic_vectors, load_follows, score_against_topic, global_boost
from src.schemas.topic import TopicCreate, TopicResponse, TopicUpdate

router = APIRouter(prefix="/topics", tags=["topics"])


def _topic_text(name: str, description: str, keywords: str | None) -> str:
    text = f"{name}. {description}"
    if keywords:
        text += f". Keywords: {keywords}"
    return text


def rescore_topic(db: Session, topic: Topic) -> int:
    """(Re)compute this topic's score for every stored paper, keeping existing votes."""
    existing_votes = {
        s.item_id: s.user_vote
        for s in db.query(ItemScore).filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None)).all()
    }
    db.query(ItemScore).filter(ItemScore.topic_id == topic.id).delete(synchronize_session=False)
    db.commit()

    follows = load_follows(db)
    topic_vectors = compute_topic_vectors(db, [topic])
    written = 0
    for item in db.query(Item).yield_per(500):
        paper = Paper.from_item(item)
        if paper.embedding is None:
            paper.embedding = get_embedding(f"{item.title}. {item.abstract}")
            item.embedding = paper.embedding
        boost, boost_reasons = global_boost(paper, follows)
        ts = score_against_topic(paper, topic, topic_vectors, boost, boost_reasons)
        if ts is None:
            continue
        keep = ts.final_score >= 0.20 or boost > 0.0 or ts.keyword_boost > 0.0 or item.id in existing_votes
        if not keep:
            continue
        db.add(
            ItemScore(
                item_id=item.id,
                topic_id=topic.id,
                semantic_score=ts.semantic_score,
                final_score=ts.final_score,
                reasons=ts.reasons,
                user_vote=existing_votes.get(item.id),
            )
        )
        written += 1
    db.commit()
    return written


@router.post("/", response_model=TopicResponse)
def create_topic(topic_in: TopicCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_topic = Topic(
        **topic_in.model_dump(),
        embedding=get_embedding(_topic_text(topic_in.name, topic_in.description, topic_in.keywords)),
        user_id="1",  # single-user MVP
    )
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)

    rescore_topic(db, db_topic)

    async def init_topic_task(topic_id: str):
        from src.api.items import full_sync

        db_bg = SessionLocal()
        try:
            print(f"Starting 30-day ingestion for new topic {topic_id}...")
            await full_sync(db_bg, days_back=30)
        finally:
            db_bg.close()

    background_tasks.add_task(init_topic_task, db_topic.id)
    return db_topic


@router.get("/", response_model=List[TopicResponse])
def read_topics(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Topic).filter(Topic.user_id == "1").offset(skip).limit(limit).all()


@router.put("/{topic_id}", response_model=TopicResponse)
def update_topic(topic_id: str, topic_in: TopicUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == "1").first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    if topic_in.name is not None:
        topic.name = topic_in.name
    if topic_in.description is not None:
        topic.description = topic_in.description
    if topic_in.keywords is not None:
        topic.keywords = topic_in.keywords
    topic.embedding = get_embedding(_topic_text(topic.name, topic.description, topic.keywords))
    db.commit()
    db.refresh(topic)

    def rescore_task(t_id: str):
        db_bg = SessionLocal()
        try:
            t = db_bg.query(Topic).filter(Topic.id == t_id).first()
            if t:
                print(f"Rescoring for topic {t.name}: {rescore_topic(db_bg, t)} scores written.")
        except Exception as e:
            print(f"Error rescoring topic {t_id}: {e}")
        finally:
            db_bg.close()

    background_tasks.add_task(rescore_task, topic.id)
    return topic


@router.delete("/{topic_id}")
def delete_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == "1").first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.query(ItemScore).filter(ItemScore.topic_id == topic_id).delete(synchronize_session=False)
    db.delete(topic)
    db.commit()
    return {"status": "success"}
