import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from src.database import get_db
from src.models.item import Item
from src.models.topic import Topic
from src.models.item_score import ItemScore
from src.models.follow import Follow
from src.models.app_config import AppConfig
from src.sources.semantic_scholar import discover_new_papers_s2, enrich_papers_s2
from src.sources.oai_pmh import harvest_arxiv_oai, harvest_biorxiv_api
from src.embeddings import get_embedding, compute_cosine_similarity
from src.llm.pipeline import run_summarization_pipeline

router = APIRouter(prefix="/items", tags=["items"])

HIGH_IMPACT_JOURNALS = {
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

# Global state to track sync progress
sync_state = {
    "status": "idle", # "idle", "running", "paused", "aborted", "error"
    "message": "Ready",
    "progress": 0
}



class SyncControlRequest(BaseModel):
    action: str # "pause" | "resume" | "abort"

@router.post("/sync/control")
def control_sync(req: SyncControlRequest):
    global sync_state
    if req.action == "pause" and sync_state["status"] == "running":
        sync_state["status"] = "paused"
        sync_state["message"] = "Paused..."
    elif req.action == "resume" and sync_state["status"] == "paused":
        sync_state["status"] = "running"
        sync_state["message"] = "Resuming..."
    elif req.action == "abort" and sync_state["status"] in ["running", "paused"]:
        sync_state["status"] = "aborted"
        sync_state["message"] = "Aborted."
    return sync_state

async def run_ingestion(db: Session, days_back: int = 3):
    global sync_state
    sync_state["status"] = "running"
    sync_state["message"] = "Initializing fetch..."
    sync_state["progress"] = 5
    # Fetch configurable days back (default 3 for delta)
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    # Load active topics and follows
    active_topics = db.query(Topic).filter(Topic.is_active, Topic.embedding.isnot(None)).all()
    follows = db.query(Follow).all()
    [f.entity_value for f in follows if f.entity_type == "author"]
    
    if not active_topics:
        sync_state["message"] = "No active topics."
        return

    # 1. DISCOVERY PHASE
    sync_state["message"] = "Discovering papers via Semantic Scholar..."
    sync_state["progress"] = 10
    
    all_identifiers = set()
    s2_discovered = await discover_new_papers_s2(active_topics, since)
    for p in s2_discovered:
        if p.get("paperId"):
            all_identifiers.add(p["paperId"])
        elif p.get("corpusId"):
            all_identifiers.add(f"CorpusId:{p['corpusId']}")
        
    sync_state["message"] = "Discovering preprints via OAI-PMH..."
    sync_state["progress"] = 25
    
    arxiv_ids = await harvest_arxiv_oai(["cs", "q-bio"], since)
    for aid in arxiv_ids:
        all_identifiers.add(aid)
        
    biorxiv_ids = await harvest_biorxiv_api(since)
    for bid in biorxiv_ids:
        all_identifiers.add(f"DOI:{bid}")
        
    if sync_state["status"] == "aborted":
        return
        
    identifiers_list = list(all_identifiers)
    if not identifiers_list:
        sync_state["message"] = "No new papers discovered."
        return
        
    # 2. ENRICHMENT PHASE
    sync_state["message"] = f"Enriching {len(identifiers_list)} papers via S2 Batch..."
    sync_state["progress"] = 40
    
    enriched_papers = await enrich_papers_s2(identifiers_list)
    
    sync_state["message"] = "Processing and Scoring papers..."
    sync_state["progress"] = 60
    
    author_follows = [(f.entity_value, f.display_name or f.entity_value, f.boost_value) for f in follows if f.entity_type == "author"]
    venue_follows = {f.entity_value.lower(): f.boost_value for f in follows if f.entity_type == "venue"}
    
    total_papers = len(enriched_papers)
    for idx, paper in enumerate(enriched_papers):
        sync_state["message"] = f"Processing and Scoring papers ({idx + 1}/{total_papers})..."
        sync_state["progress"] = 60 + int((idx / max(1, total_papers)) * 20)
        
        if sync_state["status"] == "aborted":
            return
            
        if not paper:
            continue
            
        corpus_id = str(paper.get("corpusId"))
        doi = paper.get("externalIds", {}).get("DOI")
        
        # Deduplication check in DB
        conds = []
        if corpus_id and corpus_id != "None":
            conds.append(Item.corpus_id == corpus_id)
        if doi:
            conds.append(Item.doi == doi)
            
        existing = None
        if conds:
            existing = db.query(Item).filter(or_(*conds)).first()
            
        if not existing:
            existing = db.query(Item).filter(Item.title == paper.get("title", "")).first()
            
        if existing:
            continue
            
        # Parse basic fields
        title = paper.get("title", "Unknown Title")
        abstract = paper.get("abstract") or "No abstract available."
        authors_list = paper.get("authors", [])
        author_names_list = [a.get("name") for a in authors_list if a.get("name")]
        
        # Get embedding directly from S2 to save GPU compute!
        emb_obj = paper.get("embedding")
        item_emb = None
        if emb_obj and isinstance(emb_obj, dict) and "vector" in emb_obj:
            item_emb = emb_obj["vector"]
        else:
            item_emb = get_embedding(f"{title}. {abstract}")
            
        # Yield to event loop
        await asyncio.sleep(0)
        
        # Follow Boosts
        boost = 0.0
        reasons = []
        item_authors_str = [a.lower() for a in author_names_list]
        for entity_val, disp_name, boost_val in author_follows:
            matched = False
            
            if entity_val.startswith("AUTHOR_ID:"):
                aid = entity_val.split(":")[1]
                if any(str(a.get("authorId")) == aid for a in authors_list):
                    matched = True
            elif entity_val.startswith("ORCID:"):
                orcid = entity_val.split(":")[1]
                if any(orcid in str(a.get("externalIds", {}).get("ORCID", "")) for a in authors_list):
                    matched = True
            else:
                # Legacy string match
                if any(entity_val.lower() in name for name in item_authors_str):
                    matched = True
                    
            if matched:
                boost += boost_val
                reasons.append(f"Followed author boost (+{boost_val})")
                
        venue_name = paper.get("venue")
        if venue_name:
            item_venue = venue_name.lower()
            for venue, boost_val in venue_follows.items():
                if venue in item_venue:
                    boost += boost_val
                    reasons.append(f"Followed venue boost (+{boost_val})")
                    
            # High-impact journal boost
            if item_venue in HIGH_IMPACT_JOURNALS:
                journal_boost = HIGH_IMPACT_JOURNALS[item_venue]
                boost += journal_boost
                reasons.append(f"High-impact journal boost (+{journal_boost})")
                
        # Semantic Scoring against Topics
        topic_scores = []
        max_final_score = 0.0
        
        for topic in active_topics:
            if topic.embedding and item_emb:
                raw_sim = compute_cosine_similarity(item_emb, topic.embedding)
                # Calibrate Specter V2 embeddings: random papers ~0.72, highly related ~0.88+
                sim = max(0.0, min(1.0, (raw_sim - 0.72) * 5.0))
                
                # Topic-specific Keyword Boosting
                topic_boost = 0.0
                topic_specific_reasons = []
                if topic.keywords:
                    kws = [k.strip().lower() for k in topic.keywords.split(",")]
                    paper_title = paper.get("title", "").lower() if paper.get("title") else ""
                    paper_abs = paper.get("abstract", "").lower() if paper.get("abstract") else ""
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
                
                if final_score > max_final_score:
                    max_final_score = final_score
                    
                if final_score >= 0.20 or boost > 0.0 or topic_boost > 0.0:
                    combined_reasons = [f"Semantic match to '{topic.name}' ({sim:.2f})"] + reasons + topic_specific_reasons
                    topic_scores.append({
                        "topic_id": topic.id,
                        "semantic_score": sim,
                        "final_score": final_score,
                        "reasons": combined_reasons
                    })
                    
        # Filter low relevance
        if max_final_score < 0.20 and boost == 0.0:
            continue
            
        # Parse Dates
        pub_date_str = paper.get("publicationDate")
        pub_year = paper.get("year")
        published_at = datetime.now(timezone.utc)
        
        if pub_date_str:
            try:
                published_at = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
                
        # Fallbacks for missing precise dates
        if not pub_date_str and pub_year:
            # If the year is older than current year, assume Jan 1st of that year
            # If it's the current year, we leave it as "now" so it surfaces as a new paper in the feed!
            if pub_year < published_at.year:
                published_at = datetime(pub_year, 1, 1, tzinfo=timezone.utc)
            
        # Extract rich metadata
        orcid_list = [a.get("externalIds", {}).get("ORCID") for a in authors_list if "ORCID" in a.get("externalIds", {})]
        tldr_obj = paper.get("tldr")
        t1_tldr = tldr_obj.get("text") if tldr_obj else None
        
        author_details = []
        for a in authors_list:
            if a.get("name"):
                author_details.append({
                    "name": a.get("name"),
                    "authorId": a.get("authorId"),
                    "orcid": a.get("externalIds", {}).get("ORCID") if a.get("externalIds") else None
                })
                
        db_item = Item(
            source="SemanticScholar",
            source_native_id=str(paper.get("paperId")),
            corpus_id=corpus_id,
            title=title,
            abstract=abstract,
            authors=author_names_list,
            author_details=author_details,
            published_at=published_at,
            url=paper.get("url") or "",
            doi=doi,
            pmid=paper.get("externalIds", {}).get("PubMed"),
            orcid_list=orcid_list,
            venue=venue_name,
            citation_count=paper.get("citationCount", 0),
            reference_count=paper.get("referenceCount", 0),
            influential_citation_count=paper.get("influentialCitationCount", 0),
            is_open_access=paper.get("isOpenAccess", False),
            open_access_pdf_url=paper.get("openAccessPdf", {}).get("url") if paper.get("openAccessPdf") else None,
            citation_styles=paper.get("citationStyles"),
            t1_tldr=t1_tldr,
            embedding=item_emb,
            raw_metadata_json=paper
        )
        
        db.add(db_item)
        db.flush() # flush to get item.id
        
        for ts in topic_scores:
            score = ItemScore(item_id=db_item.id, **ts)
            db.add(score)
            
    db.commit()

@router.post("/fetch", response_model=dict)
async def trigger_fetch(background_tasks: BackgroundTasks):
    """Manually trigger ingestion from all sources in the background."""
    global sync_state
    if sync_state["status"] == "running":
        return {"status": "error", "message": "Sync is already running"}
        
    async def full_sync_task():
        global sync_state
        # We need a new session for the background task
        from src.database import SessionLocal
        db = SessionLocal()
        try:
            await run_ingestion(db)
            
            if sync_state["status"] == "aborted":
                sync_state["status"] = "idle"
                sync_state["progress"] = 0
                sync_state["message"] = "Sync Aborted"
                return

            sync_state["message"] = "Cleaning up old DB items..."
            sync_state["progress"] = 80
            
            # 8-week DB Cleanup
            eight_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=8)
            deleted_count = db.query(Item).filter(Item.published_at < eight_weeks_ago, not Item.is_starred).delete()
            db.commit()
            print(f"Cleaned up {deleted_count} old unstarred items.")
            
            sync_state["message"] = "Running LLM summaries (this may take a while)..."
            sync_state["progress"] = 90
            
            # Await the pipeline so we know when it's totally done
            await run_summarization_pipeline(db)
            
            if sync_state["status"] == "aborted":
                sync_state["status"] = "idle"
                sync_state["progress"] = 0
                sync_state["message"] = "Sync Aborted"
                return
                
            sync_state["status"] = "idle"
            sync_state["message"] = "Sync Complete!"
            sync_state["progress"] = 100
            
            # Save last_synced_at
            now_iso = datetime.now(timezone.utc).isoformat()
            config_entry = db.query(AppConfig).filter(AppConfig.key == "last_synced_at").first()
            if config_entry:
                config_entry.value = now_iso
            else:
                db.add(AppConfig(key="last_synced_at", value=now_iso))
            db.commit()
        except Exception as e:
            sync_state["status"] = "error"
            sync_state["message"] = f"Error during sync: {e}"
        finally:
            db.close()

    background_tasks.add_task(full_sync_task)
    return {"status": "success", "message": "Fetch started in background"}

@router.get("/progress", response_model=dict)
def get_progress():
    return sync_state

@router.get("/", response_model=List[dict])
def get_items(skip: int = 0, limit: int = 100, topic_id: Optional[str] = None, show_acknowledged: bool = False, db: Session = Depends(get_db)):
    query = db.query(Item, ItemScore.final_score).outerjoin(
        ItemScore, Item.id == ItemScore.item_id
    )
    
    if topic_id:
        query = query.filter(ItemScore.topic_id == topic_id).order_by(desc(ItemScore.final_score))
    else:
        query = query.order_by(desc(Item.published_at))
        
    if not show_acknowledged:
        query = query.filter(Item.is_acknowledged == False)
        
    results = query.offset(skip).limit(limit).all()
    items = []
    for row in results:
        item = row[0]
        score = row[1]
        d = {**item.__dict__}
        d.pop("_sa_instance_state", None)
        if score is not None:
            d["score"] = score
        items.append(d)
        
    return items

@router.get("/starred", response_model=List[dict])
def get_starred_items(db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.is_starred).order_by(desc(Item.published_at)).all()
    results = []
    for item in items:
        d = {**item.__dict__}
        d.pop("_sa_instance_state", None)
        results.append(d)
    return results

@router.put("/{item_id}/acknowledge", response_model=dict)
def acknowledge_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    
    item.is_acknowledged = True
    db.commit()
    return {"status": "success"}

@router.put("/{item_id}/unacknowledge", response_model=dict)
def unacknowledge_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    
    item.is_acknowledged = False
    db.commit()
    return {"status": "success"}

@router.put("/{item_id}/star", response_model=dict)
def star_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    
    item.is_starred = True
    db.commit()
    return {"status": "success"}

@router.put("/{item_id}/unstar", response_model=dict)
def unstar_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    
    item.is_starred = False
    db.commit()
    return {"status": "success"}

@router.put("/{item_id}/hide", response_model=dict)
def hide_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    
    item.is_hidden = True
    db.commit()
    return {"status": "success"}

@router.put("/{item_id}/unhide", response_model=dict)
def unhide_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    
    item.is_hidden = False
    db.commit()
    return {"status": "success"}
