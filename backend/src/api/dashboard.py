import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Dict, Any, Optional

from src.database import get_db
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.follow import Follow

router = APIRouter()

def serialize_item(item, score=None):
    d = {**item.__dict__}
    d.pop("_sa_instance_state", None)
    if score is not None:
        d["score"] = score
    return d

@router.get("/", response_model=Dict[str, Any])
def get_dashboard(topic_id: Optional[str] = None, author_id: Optional[str] = None, show_acknowledged: bool = False, show_preprints: bool = True, show_discarded: bool = False, min_score: float = 0.20, db: Session = Depends(get_db)):
    # Base query for Items
    if topic_id:
        base_query = db.query(Item, ItemScore.final_score).join(
            ItemScore, Item.id == ItemScore.item_id
        ).filter(ItemScore.topic_id == topic_id)
        base_query = base_query.filter(ItemScore.final_score >= min_score)
    else:
        # If no topic, get the max score across all topics for the item
        base_query = db.query(Item, func.max(ItemScore.final_score).label('final_score')).outerjoin(
            ItemScore, Item.id == ItemScore.item_id
        ).group_by(Item.id)
        base_query = base_query.having(func.max(ItemScore.final_score) >= min_score)
        
    # Filter hidden items unless show_discarded is True
    if not show_discarded:
        base_query = base_query.filter(Item.is_hidden == False)
    
    if author_id:
        if author_id.startswith("ORCID:"):
            orcid = author_id.split(":")[1]
            base_query = base_query.filter(Item.raw_metadata_json.like(f'%"ORCID": "{orcid}"%'))
        else:
            aid = author_id.replace("AUTHOR_ID:", "")
            base_query = base_query.filter(Item.raw_metadata_json.like(f'%"authorId": "{aid}"%'))
            
    if not show_acknowledged:
        base_query = base_query.filter(Item.is_acknowledged == False)
        
    if not show_preprints:
        is_preprint_cond = (Item.source.in_(["OAI-PMH (arXiv)", "bioRxiv"])) | (Item.url.like("%arxiv%")) | (Item.url.like("%biorxiv%")) | (Item.url.like("%medrxiv%"))
        base_query = base_query.filter(~is_preprint_cond)
        
    now = datetime.datetime.now(datetime.timezone.utc)
    week_ago = now - datetime.timedelta(days=7)
    month_ago = now - datetime.timedelta(days=30)
    eight_weeks_ago = now - datetime.timedelta(weeks=8)
    
    recent_query = base_query.filter(Item.published_at >= eight_weeks_ago)
    
    # 1. Do Not Miss (Score >= 0.90)
    if topic_id:
        do_not_miss_query = recent_query.filter(ItemScore.final_score >= 0.90).order_by(desc(ItemScore.final_score), desc(Item.published_at))
    else:
        do_not_miss_query = recent_query.having(func.max(ItemScore.final_score) >= 0.90).order_by(desc('final_score'), desc(Item.published_at))
    do_not_miss = [serialize_item(i[0], i[1]) for i in do_not_miss_query.limit(50).all()]
    
    # 2. This Week
    this_week_query = recent_query.filter(Item.published_at >= week_ago)
    if topic_id:
        this_week_query = this_week_query.order_by(desc(ItemScore.final_score), desc(Item.published_at))
    else:
        this_week_query = this_week_query.order_by(desc('final_score'), desc(Item.published_at))
    this_week = [serialize_item(i[0], i[1]) for i in this_week_query.limit(50).all()]
    
    # 3. This Month
    this_month_query = recent_query.filter(Item.published_at >= month_ago).filter(Item.published_at < week_ago)
    if topic_id:
        this_month_query = this_month_query.order_by(desc(ItemScore.final_score), desc(Item.published_at))
    else:
        this_month_query = this_month_query.order_by(desc('final_score'), desc(Item.published_at))
    this_month = [serialize_item(i[0], i[1]) for i in this_month_query.limit(50).all()]
    
    # 4. Highlighted Authors
    # Get followed authors
    author_follows = db.query(Follow).filter(Follow.entity_type == "author").all()
    author_names = [f.entity_value.lower() for f in author_follows]
    
    highlighted_authors = []
    if author_names:
        # We need to filter in python because authors is a JSON array and SQLite JSON1 might be tricky
        all_items = recent_query.all()
        for i in all_items:
            item = i[0]
            score = i[1]
            # Check if any author matches
            authors = [a.lower() for a in item.authors]
            if any(followed_author in a for a in authors for followed_author in author_names):
                highlighted_authors.append(serialize_item(item, score))
        
        # Sort if topic_id
        if topic_id:
            highlighted_authors.sort(key=lambda x: x.get('score', 0) or 0, reverse=True)
        else:
            highlighted_authors.sort(key=lambda x: x.get('published_at'), reverse=True)
            
        highlighted_authors = highlighted_authors[:50]
        

        
    # 6. Starred
    starred_query = base_query.filter(Item.is_starred)
    if topic_id:
        starred_query = starred_query.order_by(desc(ItemScore.final_score), desc(Item.published_at))
    else:
        starred_query = starred_query.order_by(desc('final_score'), desc(Item.published_at))
    starred = [serialize_item(i[0], i[1]) for i in starred_query.limit(50).all()]
    
    # 7. Tools
    tools_query = recent_query.filter(Item.tools.isnot(None))
    if topic_id:
        tools_query = tools_query.order_by(desc(ItemScore.final_score), desc(Item.published_at))
    else:
        tools_query = tools_query.order_by(desc('final_score'), desc(Item.published_at))
    tools_items = [serialize_item(i[0], i[1]) for i in tools_query.limit(50).all()]
    
    return {
        "do_not_miss": do_not_miss,
        "this_week": this_week,
        "this_month": this_month,
        "highlighted_authors": highlighted_authors,
        "starred": starred,
        "tools": tools_items
    }
