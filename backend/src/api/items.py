import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from src.api.serialize import item_to_dict
from src.database import get_db
from src.llm.pipeline import run_summarization_pipeline
from src.models.app_config import AppConfig
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.ranking.paper import Paper, load_follows
from src.ranking.scoring import score_paper
from src.ranking.training import load_models, retrain_and_rescore
from src.sources.oai_pmh import harvest_arxiv_oai, harvest_biorxiv_api
from src.sources.orcid import orcid_recent_dois
from src.sources.semantic_scholar import _published_after, discover_new_papers_s2, enrich_papers_s2

router = APIRouter(prefix="/items", tags=["items"])

CLEANUP_AFTER = timedelta(weeks=8)
DEFAULT_ARXIV_SETS = ["cs", "q-bio"]
FEEDBACK_SEEDS = 100  # most recent positive/negative votes handed to the S2 recommender

# Global state to track sync progress
sync_state = {
    "status": "idle",  # "idle", "running", "paused", "aborted", "error"
    "message": "Ready",
    "progress": 0,
}


class SyncControlRequest(BaseModel):
    action: str  # "pause" | "resume" | "abort"


@router.post("/sync/control")
def control_sync(req: SyncControlRequest):
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


async def _fetch_missing_abstract(doi: Optional[str], pmid: Optional[str]) -> Optional[str]:
    """CrossRef, then EuropePMC, for papers Semantic Scholar has no abstract for."""
    if not (doi or pmid):
        return None
    try:
        async with httpx.AsyncClient() as client:
            if doi:
                resp = await client.get(f"https://api.crossref.org/works/{doi}", timeout=5.0)
                if resp.status_code == 200:
                    cr_abs = resp.json().get("message", {}).get("abstract")
                    if cr_abs:
                        return re.sub(r"<[^>]+>", "", cr_abs).strip()
            if pmid:
                resp = await client.get(
                    f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=ext_id:{pmid}&resultType=core&format=json",
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    results = resp.json().get("resultList", {}).get("result", [])
                    if results and results[0].get("abstractText"):
                        return re.sub(r"<[^>]+>", "", results[0]["abstractText"]).strip()
    except Exception as e:
        print(f"Fallback abstract fetch failed: {e}")
    return None


def _parse_published_at(paper: dict) -> datetime:
    published_at = datetime.now(timezone.utc)
    pub_date_str = paper.get("publicationDate")
    pub_year = paper.get("year")
    if pub_date_str:
        try:
            return datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if pub_year and pub_year < published_at.year:
        return datetime(pub_year, 1, 1, tzinfo=timezone.utc)
    return published_at


def _topic_feedback(db: Session, topics: List[Topic]) -> dict:
    """Semantic Scholar paper ids of each topic's positive and negative votes (newest first)."""
    feedback = {}
    for topic in topics:
        rows = (
            db.query(ItemScore.user_vote, Item.source_native_id)
            .join(Item, ItemScore.item_id == Item.id)
            .filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None), Item.source == "SemanticScholar")
            .order_by(ItemScore.voted_at.desc().nullslast(), Item.published_at.desc())
            .all()
        )
        feedback[topic.id] = {
            "positive": [pid for vote, pid in rows if vote >= 1 and pid][:FEEDBACK_SEEDS],
            "negative": [pid for vote, pid in rows if vote == -1 and pid][:FEEDBACK_SEEDS],
        }
    return feedback


def _local_embedding(title: str, abstract: str) -> Optional[list]:
    """Local SPECTER2 only as a last resort; works without torch installed (returns None)."""
    try:
        from src.embeddings import get_embedding

        return get_embedding(f"{title}. {abstract}")
    except Exception as e:
        print(f"Local embedding unavailable: {e}")
        return None


async def run_ingestion(db: Session, days_back: int = 3):
    sync_state["status"] = "running"
    sync_state["message"] = "Initializing fetch..."
    sync_state["progress"] = 5
    since = datetime.now(timezone.utc) - timedelta(days=days_back)

    active_topics = db.query(Topic).filter(Topic.is_active == True).all()  # noqa: E712
    active_topics = [t for t in active_topics if t.prior_vector or t.embedding]
    if not active_topics:
        sync_state["message"] = "No active topics."
        return

    follows = db.query(Follow).filter(Follow.entity_type == "author").all()
    s2_author_ids = [f.entity_value.split(":", 1)[1] for f in follows if f.entity_value.startswith("AUTHOR_ID:")]
    orcids = [f.entity_value.split(":", 1)[1] for f in follows if f.entity_value.startswith("ORCID:")]

    # 1. DISCOVERY -----------------------------------------------------------
    sync_state["message"] = "Discovering papers via Semantic Scholar (search, recommendations, authors)..."
    sync_state["progress"] = 10
    all_identifiers = set()
    for p in await discover_new_papers_s2(active_topics, since, feedback=_topic_feedback(db, active_topics), author_ids=s2_author_ids):
        all_identifiers.add(p["paperId"])

    sync_state["message"] = "Checking followed authors on ORCID..."
    sync_state["progress"] = 20
    for orcid in orcids:
        all_identifiers.update(f"DOI:{doi}" for doi in await orcid_recent_dois(orcid, since))

    sync_state["message"] = "Discovering preprints (arXiv, bioRxiv)..."
    sync_state["progress"] = 25
    arxiv_sets = sorted({c for t in active_topics for c in (t.arxiv_categories or [])}) or DEFAULT_ARXIV_SETS
    all_identifiers.update(await harvest_arxiv_oai(arxiv_sets, since))
    all_identifiers.update(f"DOI:{bid}" for bid in await harvest_biorxiv_api(since))

    if sync_state["status"] == "aborted":
        return

    # Skip everything already in the database before paying for enrichment.
    existing = {i[0] for i in db.query(Item.source_native_id).all()}
    existing |= {f"DOI:{i[0]}" for i in db.query(Item.doi).filter(Item.doi.isnot(None)).all()}
    existing |= {f"CorpusId:{i[0]}" for i in db.query(Item.corpus_id).filter(Item.corpus_id.isnot(None)).all()}
    identifiers_list = [i for i in all_identifiers if i not in existing]
    if not identifiers_list:
        sync_state["message"] = "No new papers discovered."
        return

    # 2. ENRICHMENT ----------------------------------------------------------
    sync_state["message"] = f"Enriching {len(identifiers_list)} new papers via S2 batch..."
    sync_state["progress"] = 40
    enriched_papers = [p for p in await enrich_papers_s2(identifiers_list) if _published_after(p, since - timedelta(days=7))]

    # 3. SCORING -------------------------------------------------------------
    sync_state["message"] = "Scoring papers..."
    sync_state["progress"] = 60
    follow_ctx = load_follows(db)
    models = load_models(db, active_topics)

    total = len(enriched_papers)
    for idx, paper in enumerate(enriched_papers):
        sync_state["message"] = f"Scoring papers ({idx + 1}/{total})..."
        sync_state["progress"] = 60 + int((idx / max(1, total)) * 20)
        if sync_state["status"] == "aborted":
            return

        corpus_id = str(paper.get("corpusId")) if paper.get("corpusId") is not None else None
        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        pmid = external_ids.get("PubMed")

        conds = []
        if corpus_id:
            conds.append(Item.corpus_id == corpus_id)
        if doi:
            conds.append(Item.doi == doi)
        if paper.get("paperId"):
            conds.append(Item.source_native_id == str(paper["paperId"]))
        if conds and db.query(Item.id).filter(or_(*conds)).first():
            continue
        if paper.get("title") and db.query(Item.id).filter(Item.title == paper["title"]).first():
            continue

        title = paper.get("title") or "Unknown Title"
        abstract = paper.get("abstract") or await _fetch_missing_abstract(doi, pmid) or "No abstract available."
        paper["abstract"] = abstract

        features = Paper.from_s2(paper)
        if features.embedding is None:
            features.embedding = _local_embedding(title, abstract)
        await asyncio.sleep(0)  # yield to the event loop between papers
        if features.embedding is None:
            continue

        topic_scores = score_paper(features, active_topics, models, follow_ctx)
        if not topic_scores:
            continue

        tldr_obj = paper.get("tldr")
        db_item = Item(
            source="SemanticScholar",
            source_native_id=str(paper.get("paperId")),
            corpus_id=corpus_id,
            title=title,
            abstract=abstract,
            authors=[a["name"] for a in features.authors],
            author_details=features.authors,
            published_at=_parse_published_at(paper),
            url=paper.get("url") or "",
            doi=doi,
            pmid=pmid,
            orcid_list=[a["orcid"] for a in features.authors if a.get("orcid")],
            venue=features.venue,
            citation_count=paper.get("citationCount", 0),
            reference_count=paper.get("referenceCount", 0),
            influential_citation_count=paper.get("influentialCitationCount", 0),
            is_open_access=paper.get("isOpenAccess", False),
            open_access_pdf_url=(paper.get("openAccessPdf") or {}).get("url"),
            citation_styles=paper.get("citationStyles"),
            t1_tldr=tldr_obj.get("text") if tldr_obj else None,
            embedding=features.embedding,
            raw_metadata_json=paper,
        )
        db.add(db_item)
        db.flush()
        for ts in topic_scores:
            db.add(ItemScore(item_id=db_item.id, topic_id=ts.topic_id, semantic_score=ts.semantic_score, final_score=ts.final_score, reasons=ts.reasons))

    db.commit()


def cleanup_old_items(db: Session) -> int:
    """Delete papers older than CLEANUP_AFTER that carry no user signal.

    Starred papers and anything the user voted on (even a downvote) are kept:
    they are the training data for the ranker.
    """
    cutoff = datetime.now(timezone.utc) - CLEANUP_AFTER
    voted_ids = db.query(ItemScore.item_id).filter(ItemScore.user_vote.isnot(None))
    stale_ids = [
        i[0]
        for i in db.query(Item.id)
        .filter(Item.published_at < cutoff, Item.is_starred == False, ~Item.id.in_(voted_ids))  # noqa: E712
        .all()
    ]
    if not stale_ids:
        return 0
    deleted = 0
    for start in range(0, len(stale_ids), 500):
        chunk = stale_ids[start : start + 500]
        db.query(ItemScore).filter(ItemScore.item_id.in_(chunk)).delete(synchronize_session=False)
        deleted += db.query(Item).filter(Item.id.in_(chunk)).delete(synchronize_session=False)
    db.commit()
    return deleted


def _finish_sync(db: Session) -> None:
    sync_state["status"] = "idle"
    sync_state["message"] = "Sync Complete!"
    sync_state["progress"] = 100
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = db.query(AppConfig).filter(AppConfig.key == "last_synced_at").first()
    if entry:
        entry.value = now_iso
    else:
        db.add(AppConfig(key="last_synced_at", value=now_iso))
    db.commit()


def _aborted() -> bool:
    if sync_state["status"] == "aborted":
        sync_state["status"] = "idle"
        sync_state["progress"] = 0
        sync_state["message"] = "Sync Aborted"
        return True
    return False


async def full_sync(db: Session, days_back: int = 3) -> None:
    """Ingest, clean up, summarize. Shared by the manual trigger and the scheduler."""
    try:
        await run_ingestion(db, days_back=days_back)
        if _aborted():
            return
        sync_state["message"] = "Cleaning up old DB items..."
        sync_state["progress"] = 80
        print(f"Cleaned up {cleanup_old_items(db)} old unstarred, unvoted items.")
        sync_state["message"] = "Running LLM summaries (this may take a while)..."
        sync_state["progress"] = 90
        await run_summarization_pipeline(db)
        if _aborted():
            return
        _finish_sync(db)
    except Exception as e:
        sync_state["status"] = "error"
        sync_state["message"] = f"Error during sync: {e}"


@router.post("/fetch", response_model=dict)
async def trigger_fetch(background_tasks: BackgroundTasks):
    """Manually trigger ingestion from all sources in the background."""
    if sync_state["status"] in ("running", "paused"):
        return {"status": "error", "message": "Sync is already running"}

    async def task():
        from src.database import SessionLocal

        db = SessionLocal()
        try:
            await full_sync(db)
        finally:
            db.close()

    background_tasks.add_task(task)
    return {"status": "success", "message": "Fetch started in background"}


@router.get("/progress", response_model=dict)
def get_progress():
    return sync_state


@router.get("/", response_model=List[dict])
def get_items(skip: int = 0, limit: int = 100, topic_id: Optional[str] = None, show_acknowledged: bool = False, db: Session = Depends(get_db)):
    query = db.query(Item, ItemScore.final_score, ItemScore.user_vote, ItemScore.topic_id).outerjoin(ItemScore, Item.id == ItemScore.item_id)
    if topic_id:
        query = query.filter(ItemScore.topic_id == topic_id).order_by(desc(ItemScore.final_score))
    else:
        query = query.order_by(desc(Item.published_at))
    if not show_acknowledged:
        query = query.filter(Item.is_acknowledged == False)  # noqa: E712

    items: dict[str, dict] = {}
    for item, score, vote, tid in query.offset(skip).limit(limit).all():
        if item.id not in items:
            items[item.id] = item_to_dict(item, score, vote, tid)
        elif score is not None and (items[item.id].get("score") is None or score > items[item.id]["score"]):
            items[item.id]["score"] = score
            items[item.id]["topic_id"] = tid
            if vote is not None:
                items[item.id]["user_vote"] = vote
    return list(items.values())


def _library(db: Session, flag_column, default_vote: int) -> List[dict]:
    """Starred / discarded listing with the vote and topic that produced it."""
    items = db.query(Item).filter(flag_column == True).order_by(desc(Item.published_at)).all()  # noqa: E712
    results = []
    for item in items:
        score = (
            db.query(ItemScore)
            .filter(ItemScore.item_id == item.id)
            .order_by(ItemScore.user_vote.isnot(None).desc(), ItemScore.final_score.desc())
            .first()
        )
        vote = score.user_vote if score and score.user_vote is not None else default_vote
        results.append(item_to_dict(item, score.final_score if score else None, vote, score.topic_id if score else None, reasons=score.reasons if score else None))
    return results


@router.get("/starred", response_model=List[dict])
def get_starred_items(db: Session = Depends(get_db)):
    return _library(db, Item.is_starred, default_vote=2)


@router.get("/discarded", response_model=List[dict])
def get_discarded_items(db: Session = Depends(get_db)):
    return _library(db, Item.is_hidden, default_vote=-1)


def _set_flag(db: Session, item_id: str, **flags) -> dict:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}
    for key, value in flags.items():
        setattr(item, key, value)
    db.commit()
    return {"status": "success"}


@router.put("/{item_id}/acknowledge", response_model=dict)
def acknowledge_item(item_id: str, db: Session = Depends(get_db)):
    return _set_flag(db, item_id, is_acknowledged=True)


@router.put("/{item_id}/unacknowledge", response_model=dict)
def unacknowledge_item(item_id: str, db: Session = Depends(get_db)):
    return _set_flag(db, item_id, is_acknowledged=False)


@router.put("/{item_id}/star", response_model=dict)
def star_item(item_id: str, db: Session = Depends(get_db)):
    return _set_flag(db, item_id, is_starred=True)


@router.put("/{item_id}/unstar", response_model=dict)
def unstar_item(item_id: str, db: Session = Depends(get_db)):
    return _set_flag(db, item_id, is_starred=False)


@router.put("/{item_id}/hide", response_model=dict)
def hide_item(item_id: str, db: Session = Depends(get_db)):
    return _set_flag(db, item_id, is_hidden=True)


@router.put("/{item_id}/unhide", response_model=dict)
def unhide_item(item_id: str, db: Session = Depends(get_db)):
    return _set_flag(db, item_id, is_hidden=False)


@router.delete("/unstarred", response_model=dict)
def clear_unstarred(db: Session = Depends(get_db)):
    """Delete every paper that is neither starred nor voted on."""
    try:
        voted_ids = db.query(ItemScore.item_id).filter(ItemScore.user_vote.isnot(None))
        ids = [i[0] for i in db.query(Item.id).filter(Item.is_starred == False, ~Item.id.in_(voted_ids)).all()]  # noqa: E712
        deleted = 0
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            db.query(ItemScore).filter(ItemScore.item_id.in_(chunk)).delete(synchronize_session=False)
            deleted += db.query(Item).filter(Item.id.in_(chunk)).delete(synchronize_session=False)
        db.commit()
        return {"status": "success", "deleted": deleted}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}


class BulkRescoreRequest(BaseModel):
    item_ids: List[str]


@router.post("/bulk_rescore", response_model=dict)
async def bulk_rescore(req: BulkRescoreRequest, db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.id.in_(req.item_ids)).all()
    if not items:
        return {"status": "error", "message": "No items found"}

    # Fill in missing abstracts / embeddings from Semantic Scholar first.
    missing = [i for i in items if not i.abstract or i.abstract == "No abstract available." or not i.embedding]
    if missing:
        identifiers, item_map = [], {}
        for item in missing:
            if item.corpus_id:
                key = f"CorpusId:{item.corpus_id}"
            elif item.doi:
                key = f"DOI:{item.doi}"
            elif item.source_native_id:
                key = item.source_native_id
            else:
                continue
            identifiers.append(key)
            item_map[key] = item
        if identifiers:
            try:
                for data in await enrich_papers_s2(identifiers):
                    cid = data.get("corpusId")
                    doi = (data.get("externalIds") or {}).get("DOI")
                    match = item_map.get(f"CorpusId:{cid}") or item_map.get(str(data.get("paperId"))) or item_map.get(f"DOI:{doi}")
                    if not match:
                        continue
                    if data.get("abstract"):
                        match.abstract = data["abstract"]
                    emb = data.get("embedding")
                    if isinstance(emb, dict) and emb.get("vector"):
                        match.embedding = emb["vector"]
                db.commit()
            except Exception as e:
                print(f"Failed to enrich missing items during rescore: {e}")

    active_topics = db.query(Topic).filter(Topic.is_active == True).all()  # noqa: E712
    follows = load_follows(db)
    models = load_models(db, active_topics)
    existing_llm = {(s.item_id, s.topic_id): s.llm_relevance_score for s in db.query(ItemScore).filter(ItemScore.item_id.in_(req.item_ids)).all()}

    for item in items:
        features = Paper.from_item(item)
        if features.embedding is None:
            continue
        llm = {t.id: existing_llm.get((item.id, t.id)) for t in active_topics}
        for ts in score_paper(features, active_topics, models, follows, llm_scores={k: v for k, v in llm.items() if v is not None}):
            entry = db.query(ItemScore).filter(ItemScore.item_id == item.id, ItemScore.topic_id == ts.topic_id).first()
            if not entry:
                entry = ItemScore(item_id=item.id, topic_id=ts.topic_id)
                db.add(entry)
            entry.semantic_score = ts.semantic_score
            entry.final_score = ts.final_score
            entry.reasons = ts.reasons
    db.commit()
    return {"status": "success"}


class VoteRequest(BaseModel):
    topic_id: Optional[str] = None
    vote: Optional[int] = None  # None: Unrated, 2: Star, 1: Up, 0: Neutral, -1: Down


@router.post("/{item_id}/vote", response_model=dict)
def vote_item(item_id: str, vote_req: VoteRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Record a vote and retrain that topic's ranker in the background.

    The vote is training signal for exactly one topic: the one passed in, or,
    when voting from the overview feed, the topic that gave the item its best
    score. It is never written to every topic the item happens to match, so
    research topics do not learn from each other's feedback.
    """
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return {"status": "error", "message": "Item not found"}

    if vote_req.vote is None:
        item.is_acknowledged = False
        item.is_starred = False
        item.is_hidden = False
    else:
        item.is_acknowledged = True
        item.is_starred = vote_req.vote == 2
        item.is_hidden = vote_req.vote == -1

    scores = db.query(ItemScore).filter(ItemScore.item_id == item_id).all()
    target: Optional[ItemScore] = None
    if vote_req.topic_id:
        target = next((s for s in scores if s.topic_id == vote_req.topic_id), None)
    elif scores:
        target = max(scores, key=lambda s: s.final_score or 0.0)

    touched: set[str] = set()
    if vote_req.vote is None:
        for s in scores:
            if s.user_vote is not None:
                touched.add(s.topic_id)
            s.user_vote = None
            s.voted_at = None
    elif target is not None:
        target.user_vote = vote_req.vote
        target.voted_at = datetime.now(timezone.utc)
        touched.add(target.topic_id)

    db.commit()
    for topic_id in touched:
        background_tasks.add_task(retrain_and_rescore, topic_id)
    return {"status": "success", "topic_id": target.topic_id if target else None}
