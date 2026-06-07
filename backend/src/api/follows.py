from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from src.database import get_db
from src.models.follow import Follow

router = APIRouter()

class FollowCreate(BaseModel):
    entity_type: str
    entity_value: str
    display_name: str | None = None
    boost_value: float = 0.15

@router.get("/", response_model=List[Dict[str, Any]])
def get_follows(db: Session = Depends(get_db)):
    follows = db.query(Follow).all()
    results = []
    for f in follows:
        d = {**f.__dict__}
        d.pop("_sa_instance_state", None)
        results.append(d)
    return results

@router.post("/", response_model=Dict[str, Any])
def create_follow(follow: FollowCreate, db: Session = Depends(get_db)):
    db_follow = Follow(
        entity_type=follow.entity_type,
        entity_value=follow.entity_value,
        display_name=follow.display_name,
        boost_value=follow.boost_value
    )
    db.add(db_follow)
    db.commit()
    db.refresh(db_follow)
    d = {**db_follow.__dict__}
    d.pop("_sa_instance_state", None)
    return d

@router.delete("/{follow_id}", response_model=dict)
def delete_follow(follow_id: str, db: Session = Depends(get_db)):
    follow = db.query(Follow).filter(Follow.id == follow_id).first()
    if not follow:
        raise HTTPException(status_code=404, detail="Follow not found")
    
    db.delete(follow)
    db.commit()
    return {"status": "success"}

@router.get("/search_author", response_model=List[Dict[str, Any]])
async def search_author(query: str):
    from src.sources.semantic_scholar import search_authors_s2
    results = await search_authors_s2(query)
    return results
