from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.topic import Topic
from src.schemas.topic import TopicCreate, TopicResponse
from src.embeddings import get_embedding

router = APIRouter(prefix="/topics", tags=["topics"])

@router.post("/", response_model=TopicResponse)
def create_topic(topic_in: TopicCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Generate embedding for the new topic
    text_to_embed = f"{topic_in.name}. {topic_in.description}"
    if topic_in.keywords:
        text_to_embed += f". Keywords: {topic_in.keywords}"
    embedding = get_embedding(text_to_embed)
    
    db_topic = Topic(
        **topic_in.model_dump(),
        embedding=embedding,
        user_id="1" # Hardcoded for single-user MVP
    )
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    
    # Backfill scores for existing items
    from src.models.item import Item
    from src.models.item_score import ItemScore
    from src.models.follow import Follow
    from src.embeddings import compute_cosine_similarity
    
    items = db.query(Item).all()
    follows = db.query(Follow).all()
    author_follows = {f.entity_value.lower(): f.boost_value for f in follows if f.entity_type == "author"}
    venue_follows = {f.entity_value.lower(): f.boost_value for f in follows if f.entity_type == "venue"}
    
    for item in items:
        if item.embedding:
            item_emb = item.embedding
        else:
            item_text = f"{item.title}. {item.abstract}"
            item_emb = get_embedding(item_text)
            
        raw_sim = compute_cosine_similarity(item_emb, embedding)
        # Calibrate Specter V2 embeddings: random papers ~0.72, highly related ~0.88+
        sim = max(0.0, min(1.0, (raw_sim - 0.72) * 5.0))
        
        boost = 0.0
        reasons = []
        item_authors = [a.lower() for a in item.authors] if item.authors else []
        for author, boost_val in author_follows.items():
            if any(author in a for a in item_authors):
                boost += boost_val
                reasons.append(f"Followed author boost (+{boost_val})")
                
        if item.venue:
            item_venue = item.venue.lower()
            for venue, boost_val in venue_follows.items():
                if venue in item_venue:
                    boost += boost_val
                    reasons.append(f"Followed venue boost (+{boost_val})")
                    
        # Topic-specific Keyword Boosting
        topic_boost = 0.0
        topic_specific_reasons = []
        if db_topic.keywords:
            kws = [k.strip().lower() for k in db_topic.keywords.split(",")]
            paper_title = item.title.lower() if item.title else ""
            paper_abs = item.abstract.lower() if item.abstract else ""
            for kw in kws:
                if not kw: continue
                # allow singular/plural loose matching
                kw_base = kw[:-1] if kw.endswith('s') else kw
                
                if kw_base in paper_title:
                    topic_boost += 0.15
                    topic_specific_reasons.append(f"Keyword in title ('{kw}', +0.15)")
                elif kw_base in paper_abs:
                    topic_boost += 0.10
                    topic_specific_reasons.append(f"Keyword in abstract ('{kw}', +0.10)")

        final_score = min(1.0, sim + boost + topic_boost)
        
        # Only add score if it passes the threshold, same as items.py
        if final_score >= 0.20 or boost > 0.0 or topic_boost > 0.0:
            combined_reasons = [f"Semantic match to '{db_topic.name}' ({sim:.2f})"] + reasons + topic_specific_reasons
            
            score = ItemScore(
                item_id=item.id,
                topic_id=db_topic.id,
                semantic_score=sim,
                final_score=final_score,
                reasons=combined_reasons
            )
            db.add(score)
    db.commit()
    
    # Run a full ingest and summarization pipeline for the last 2 months automatically
    from src.api.items import run_ingestion
    from src.llm.pipeline import run_summarization_pipeline
    from src.database import SessionLocal
    
    async def init_topic_task():
        from src.api.items import sync_state
        db_bg = SessionLocal()
        try:
            print(f"Starting 30-day ingestion for new topic: {db_topic.name}...")
            await run_ingestion(db_bg, days_back=30)
            
            if sync_state["status"] == "aborted":
                sync_state["status"] = "idle"
                sync_state["progress"] = 0
                sync_state["message"] = "Sync Aborted"
                return

            print("Ingestion complete. Running summarization pipeline...")
            await run_summarization_pipeline(db_bg)
            
            if sync_state["status"] == "aborted":
                sync_state["status"] = "idle"
                sync_state["progress"] = 0
                sync_state["message"] = "Sync Aborted"
                return

            print("Pipeline complete!")
            sync_state["status"] = "idle"
            sync_state["message"] = "Sync Complete!"
            sync_state["progress"] = 100
        except Exception as e:
            sync_state["status"] = "error"
            sync_state["message"] = f"Error during sync: {e}"
        finally:
            db_bg.close()
            
    background_tasks.add_task(init_topic_task)
    
    return db_topic

@router.get("/", response_model=List[TopicResponse])
def read_topics(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    topics = db.query(Topic).filter(Topic.user_id == "1").offset(skip).limit(limit).all()
    return topics

@router.delete("/{topic_id}")
def delete_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == "1").first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    db.delete(topic)
    db.commit()
    return {"status": "success"}
