from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from src.database import get_db
from src.models.rss import RssFeed

router = APIRouter()

class RssFeedCreate(BaseModel):
    name: str
    url: str

@router.get("/", response_model=List[Dict[str, Any]])
def get_rss_feeds(db: Session = Depends(get_db)):
    feeds = db.query(RssFeed).all()
    results = []
    for f in feeds:
        d = {**f.__dict__}
        d.pop("_sa_instance_state", None)
        results.append(d)
    return results

@router.post("/", response_model=Dict[str, Any])
def create_rss_feed(feed: RssFeedCreate, db: Session = Depends(get_db)):
    existing = db.query(RssFeed).filter(RssFeed.url == feed.url).first()
    if existing:
        raise HTTPException(status_code=400, detail="RSS feed URL already exists")
        
    db_feed = RssFeed(
        name=feed.name,
        url=feed.url,
        is_active=True
    )
    db.add(db_feed)
    db.commit()
    db.refresh(db_feed)
    
    d = {**db_feed.__dict__}
    d.pop("_sa_instance_state", None)
    return d

@router.delete("/{feed_id}", response_model=dict)
def delete_rss_feed(feed_id: str, db: Session = Depends(get_db)):
    feed = db.query(RssFeed).filter(RssFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="RSS feed not found")
    
    db.delete(feed)
    db.commit()
    return {"status": "success"}


