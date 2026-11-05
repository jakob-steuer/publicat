import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from src.api.serialize import item_to_dict
from src import jobs
from src.database import get_db
from src.llm.pipeline import run_summarization_pipeline
from src.models.app_config import AppConfig
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.sync_run import SyncRun
from src.models.topic import Topic
from src.ranking.paper import Paper, load_follows
from src.ranking.scoring import MIN_SCORE_TO_KEEP, score_paper
from src.ranking.training import load_models, retrain_and_rescore
from src.sources.oai_pmh import harvest_arxiv_oai, harvest_biorxiv_api
from src.sources.orcid import orcid_recent_dois
from src.sources.semantic_scholar import _published_after, discover_new_papers_s2, enrich_papers_s2

router = APIRouter(prefix="/items", tags=["items"])

CLEANUP_AFTER = timedelta(weeks=8)
MIN_LOOKBACK_DAYS = 3
MAX_LOOKBACK_DAYS = 30
DEFAULT_ARXIV_SETS = ["cs", "q-bio"]
FEEDBACK_SEEDS = 100  # most recent positive/negative votes handed to the S2 recommender

# Progress state shared with the job runner (kept under the old name for callers).
sync_state = jobs.state


class SyncControlRequest(BaseModel):
    action: str  # "pause" | "resume" | "abort"


@router.post("/sync/control")
def control_sync(req: SyncControlRequest):
    return jobs.control(req.action)


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


def preprint_venue(external_ids: dict) -> Optional[str]:
    """Semantic Scholar returns an empty venue for most preprints; recover it from the ids."""
    if external_ids.get("ArXiv"):
        return "arXiv.org"
    doi = (external_ids.get("DOI") or "").lower()
    if doi.startswith("10.1101/"):
        return "medRxiv" if "medrxiv" in doi else "bioRxiv"
    if doi.startswith("10.26434/"):
        return "ChemRxiv"
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


def local_embeddings_enabled() -> bool:
    """Opt-in: loading PyTorch/SPECTER2 inside a sync stalls the API for seconds and
    Semantic Scholar supplies a vector for nearly every paper anyway."""
    return os.environ.get("PUBLICAT_LOCAL_EMBEDDINGS", "0") in ("1", "true", "True")


def _local_embedding(title: str, abstract: str) -> Optional[list]:
    if not local_embeddings_enabled():
        return None
    try:
        from src.embeddings import get_embedding

        return get_embedding(f"{title}. {abstract}")
    except Exception as e:
        print(f"Local embedding unavailable: {e}", flush=True)
        return None


ABSTRACT_FETCH_CONCURRENCY = 6


async def _fill_missing_abstracts(papers: list) -> None:
    """Fetch missing abstracts from CrossRef / EuropePMC, a few at a time."""
    todo = [p for p in papers if not p.get("abstract") and ((p.get("externalIds") or {}).get("DOI") or (p.get("externalIds") or {}).get("PubMed"))]
    if not todo:
        return
    sem = asyncio.Semaphore(ABSTRACT_FETCH_CONCURRENCY)

    async def one(p):
        ext = p.get("externalIds") or {}
        async with sem:
            p["abstract"] = await _fetch_missing_abstract(ext.get("DOI"), ext.get("PubMed"))

    await asyncio.gather(*(one(p) for p in todo))
    print(f"  abstracts: {len(todo)} looked up, {sum(1 for p in todo if p.get('abstract'))} found", flush=True)


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
    origins: dict[str, set] = {}  # identifier (lower-case) -> discovery lanes

    def found(identifier: str, lane: str) -> None:
        all_identifiers.add(identifier)
        origins.setdefault(identifier.lower(), set()).add(lane)

    for p in await discover_new_papers_s2(active_topics, since, feedback=_topic_feedback(db, active_topics), author_ids=s2_author_ids):
        for lane in p.get("_via") or {"S2 search"}:
            found(p["paperId"], lane)

    sync_state["message"] = "Checking followed authors on ORCID..."
    sync_state["progress"] = 20
    for orcid in orcids:
        if jobs.aborted():
            return
        dois = await orcid_recent_dois(orcid, since)
        jobs.count_source("followed author (ORCID)", len(dois), len(dois))
        print(f"  discovery/orcid[{orcid}]: {len(dois)} recent DOIs", flush=True)
        for doi in dois:
            found(f"DOI:{doi}", "followed author (ORCID)")

    sync_state["message"] = "Discovering preprints (arXiv, bioRxiv)..."
    sync_state["progress"] = 25
    arxiv_sets = sorted({c for t in active_topics for c in (t.arxiv_categories or [])}) or DEFAULT_ARXIV_SETS
    arxiv_ids = await harvest_arxiv_oai(arxiv_sets, since)
    biorxiv_ids = await harvest_biorxiv_api(since)
    jobs.count_source("arXiv", len(arxiv_ids), len(arxiv_ids))
    jobs.count_source("bioRxiv", len(biorxiv_ids), len(biorxiv_ids))
    print(f"  discovery/arxiv{arxiv_sets}: {len(arxiv_ids)}; discovery/biorxiv: {len(biorxiv_ids)}", flush=True)
    for aid in arxiv_ids:
        found(aid, "arXiv")
    for bid in biorxiv_ids:
        found(f"DOI:{bid}", "bioRxiv")

    if sync_state["status"] == "aborted":
        return

    # Skip everything already in the database before paying for enrichment.
    def known_identifiers() -> set:
        known = {i[0] for i in db.query(Item.source_native_id).all()}
        known |= {f"DOI:{i[0]}" for i in db.query(Item.doi).filter(Item.doi.isnot(None)).all()}
        known |= {f"CorpusId:{i[0]}" for i in db.query(Item.corpus_id).filter(Item.corpus_id.isnot(None)).all()}
        return known

    existing = await asyncio.to_thread(known_identifiers)
    identifiers_list = [i for i in all_identifiers if i not in existing]
    jobs.count("discovered", len(all_identifiers))
    jobs.count("new_candidates", len(identifiers_list))
    print(f"  discovery: {len(all_identifiers)} candidates, {len(identifiers_list)} not yet in the database", flush=True)
    if not identifiers_list:
        sync_state["message"] = "No new papers discovered."
        return

    # 2. ENRICHMENT ----------------------------------------------------------
    sync_state["message"] = f"Enriching {len(identifiers_list)} new papers via S2 batch..."
    sync_state["progress"] = 40
    enriched_all = await enrich_papers_s2(identifiers_list)
    enriched_papers = [p for p in enriched_all if _published_after(p, since - timedelta(days=7))]
    jobs.count("enriched", len(enriched_papers))
    for paper in enriched_papers:
        ext = paper.get("externalIds") or {}
        keys = [str(paper.get("paperId") or "")]
        if ext.get("ArXiv"):
            keys.append(f"ARXIV:{ext['ArXiv']}")
        if ext.get("DOI"):
            keys.append(f"DOI:{ext['DOI']}")
        via: set = set()
        for k in keys:
            via |= origins.get(k.lower(), set())
        paper["_via"] = sorted(via)
    print(f"  enrichment: {len(enriched_all)} records from S2, {len(enriched_papers)} within the date window", flush=True)

    # 3. SCORING (CPU + DB work, in a worker thread so the API stays responsive) ----
    sync_state["message"] = "Fetching missing abstracts..."
    sync_state["progress"] = 55
    await _fill_missing_abstracts(enriched_papers)
    if sync_state["status"] == "aborted":
        return
    sync_state["message"] = "Scoring papers..."
    sync_state["progress"] = 60
    stored = await asyncio.to_thread(score_and_store, db, enriched_papers, active_topics)
    jobs.count("stored", stored)


def score_and_store(db: Session, enriched_papers: list, active_topics: list) -> int:
    """Deduplicate, score against every topic and store the keepers. Synchronous; run in a thread."""
    follow_ctx = load_follows(db)
    models = load_models(db, active_topics)
    total = len(enriched_papers)
    stored = 0
    no_embedding = 0
    stored_by_source: dict[str, int] = {}
    for idx, paper in enumerate(enriched_papers):
        if idx % 25 == 0:
            jobs.set_progress(60 + int((idx / max(1, total)) * 20), f"Scoring papers ({idx + 1}/{total})...")
        if jobs.aborted():
            break

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
        abstract = paper.get("abstract") or "No abstract available."
        paper["abstract"] = abstract
        if not paper.get("venue"):
            paper["venue"] = preprint_venue(external_ids)

        features = Paper.from_s2(paper)
        if features.embedding is None:
            features.embedding = _local_embedding(title, abstract)
        if features.embedding is None:
            no_embedding += 1
            continue

        topic_scores = score_paper(features, active_topics, models, follow_ctx)
        if not topic_scores:
            continue

        tldr_obj = paper.get("tldr")
        via = paper.pop("_via", None) or None
        for lane in via or ["unknown"]:
            stored_by_source[lane] = stored_by_source.get(lane, 0) + 1
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
            discovered_via=via,
        )
        db.add(db_item)
        db.flush()
        for ts in topic_scores:
            db.add(ItemScore(item_id=db_item.id, topic_id=ts.topic_id, semantic_score=ts.semantic_score, final_score=ts.final_score, reasons=ts.reasons))
        stored += 1
        if stored % 200 == 0:
            db.commit()

    db.commit()
    jobs.state["counters"]["stored_by_source"] = stored_by_source
    print(f"  scoring: {total} candidates scored, {stored} stored (>= {MIN_SCORE_TO_KEEP:.2f} relevance or keyword/author/journal signal), {no_embedding} skipped without embedding", flush=True)
    return stored


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


def _set_config(db: Session, key: str, value: str) -> None:
    entry = db.query(AppConfig).filter(AppConfig.key == key).first()
    if entry:
        entry.value = value
    else:
        db.add(AppConfig(key=key, value=value))


def _get_config(db: Session, key: str) -> Optional[str]:
    entry = db.query(AppConfig).filter(AppConfig.key == key).first()
    return entry.value if entry else None


def lookback_days(db: Session, now: Optional[datetime] = None) -> int:
    """How far back to fetch: since the last *complete* sync, at least 3 and at most 30 days.

    A laptop that was off for a week therefore catches up on the week, and a run
    that lost requests does not advance the mark, so the next run re-covers it.
    """
    now = now or datetime.now(timezone.utc)
    last = _get_config(db, "last_complete_sync_at")
    if not last:
        return MIN_LOOKBACK_DAYS
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return MIN_LOOKBACK_DAYS
    gap_days = (now - last_dt).total_seconds() / 86400.0
    return int(max(MIN_LOOKBACK_DAYS, min(MAX_LOOKBACK_DAYS, gap_days + 1)))


def _finish_sync(db: Session, complete: bool) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    _set_config(db, "last_synced_at", now_iso)
    if complete:
        _set_config(db, "last_complete_sync_at", now_iso)
    db.commit()


async def _sync_steps(db: Session, days_back: Optional[int], name: str) -> None:
    days = days_back or lookback_days(db)
    run = SyncRun(job=name, days_back=days, status="running")
    db.add(run)
    db.commit()
    try:
        await run_ingestion(db, days_back=days)
        if not jobs.aborted():
            jobs.set_progress(80, "Cleaning up old DB items...")
            deleted = await asyncio.to_thread(cleanup_old_items, db)
            jobs.count("cleaned_up", deleted)
            print(f"Cleaned up {deleted} old unstarred, unvoted items.", flush=True)
            # New papers change what "a typical paper" looks like: refresh every topic's
            # calibration and scores now, not only after the next vote.
            jobs.set_progress(85, "Updating topic rankers...")
            for topic_id in [t.id for t in db.query(Topic).filter(Topic.is_active == True).all()]:  # noqa: E712
                await asyncio.to_thread(retrain_and_rescore, topic_id)
            db.expire_all()
            jobs.set_progress(90, "Running LLM summaries (this may take a while)...")
            await run_summarization_pipeline(db)
    except Exception as e:
        run.status, run.message = "error", repr(e)[:500]
        raise
    finally:
        errors = int(jobs.state.get("errors", 0))
        if run.status == "running":
            run.status = "aborted" if jobs.aborted() else ("partial" if errors else "complete")
        run.errors = errors
        run.counters = dict(jobs.state.get("counters", {}))
        run.finished_at = datetime.now(timezone.utc)
        if run.status == "partial":
            details = "; ".join(run.counters.get("error_messages", [])[:5])
            run.message = f"{errors} request(s) failed; the period will be fetched again next time. {details}".strip()
        if run.status in ("complete", "partial"):
            _finish_sync(db, complete=run.status == "complete")
        db.commit()


async def full_sync(db: Session, days_back: Optional[int] = None, name: str = "sync") -> bool:
    """Ingest, clean up, summarize, as the single exclusive background job.

    days_back=None derives the window from the last complete sync. Returns False
    if another job was already running (nothing was done).
    """
    ran = await jobs.run_exclusive(name, lambda: _sync_steps(db, days_back, name)) is not None or not jobs.is_busy()
    # Topics created while this job ran asked for their history: fetch it now, once.
    backfill = jobs.take_backfill()
    if ran and backfill and not jobs.aborted():
        await jobs.run_exclusive("backfill for new topics", lambda: _sync_steps(db, backfill, "backfill for new topics"))
    return ran


@router.get("/sync_runs", response_model=List[dict])
def sync_runs(limit: int = 10, db: Session = Depends(get_db)):
    """Most recent sync jobs with their outcome and counts (Settings page)."""
    rows = db.query(SyncRun).order_by(desc(SyncRun.started_at)).limit(max(1, min(limit, 50))).all()
    return [
        {
            "id": r.id,
            "job": r.job,
            "status": r.status,
            "days_back": r.days_back,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "errors": r.errors,
            "counters": r.counters or {},
            "message": r.message,
        }
        for r in rows
    ]


@router.post("/fetch", response_model=dict)
async def trigger_fetch(background_tasks: BackgroundTasks, days: Optional[int] = None):
    """Manually trigger ingestion from all sources in the background.

    `days` forces the lookback (e.g. 30 to backfill); default derives it from the last complete sync.
    """
    if days is not None:
        days = max(1, min(int(days), 60))
    stopping = jobs.is_stopping()
    if jobs.is_busy() and not stopping:
        return {"status": "error", "message": f"{jobs.state.get('job') or 'A job'} is already running"}

    async def task():
        from src.database import SessionLocal

        # The previous job was aborted but has not unwound yet (it stops at the
        # next checkpoint): wait for the slot instead of silently dropping the request.
        if not await jobs.wait_until_free():
            print("Manual fetch dropped: previous job did not stop in time.", flush=True)
            return
        db = SessionLocal()
        try:
            await full_sync(db, days_back=days, name="manual fetch" if days is None else f"backfill ({days} days)")
        finally:
            db.close()

    background_tasks.add_task(task)
    return {"status": "success", "message": "Fetch queued: waiting for the previous job to stop" if stopping else "Fetch started in background"}


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
        topic = db.get(Topic, score.topic_id) if score else None
        results.append(item_to_dict(item, score.final_score if score else None, vote, score.topic_id if score else None, topic.name if topic else None, reasons=score.reasons if score else None))
    from src.api.inbox import attach_topic_votes

    attach_topic_votes(db, results)
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
    if vote_req.vote == 2:
        auto = db.query(AppConfig).filter(AppConfig.key == "zotero_auto_push").first()
        if auto and auto.value == "true":
            background_tasks.add_task(_zotero_push_quietly, item_id)
    return {"status": "success", "topic_id": target.topic_id if target else None}


class TopicTagRequest(BaseModel):
    state: str  # "in" | "out" | "none"


@router.put("/{item_id}/topics/{topic_id}", response_model=dict)
def tag_topic(item_id: str, topic_id: str, req: TopicTagRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Say whether a paper belongs to a topic, independently of where it was found.

    "in"   the paper is a good example of this topic (a star if it is starred, else an upvote)
    "out"  it does not belong to this topic (a downvote for this topic only; the paper stays visible elsewhere)
    "none" no statement about this topic
    Only the topic's training signal changes; the paper's own read/starred/discarded state is untouched.
    """
    item = db.get(Item, item_id)
    topic = db.get(Topic, topic_id)
    if not item or not topic:
        return {"status": "error", "message": "Item or topic not found"}
    if req.state not in ("in", "out", "none"):
        return {"status": "error", "message": "state must be in, out or none"}

    row = db.query(ItemScore).filter(ItemScore.item_id == item_id, ItemScore.topic_id == topic_id).first()
    if row is None:
        if req.state == "none":
            return {"status": "success", "topic_votes": _topic_votes(db, item_id)}
        row = ItemScore(item_id=item_id, topic_id=topic_id, semantic_score=0.0, final_score=0.0, reasons=[])
        paper = Paper.from_item(item)
        if paper.embedding is not None:
            from src.ranking.scoring import apply_to_entry, score_against_topic

            apply_to_entry(row, score_against_topic(paper, topic, load_models(db, [topic])[topic.id], load_follows(db)))
        db.add(row)
    if req.state == "in":
        row.user_vote = 2 if item.is_starred else 1
    elif req.state == "out":
        row.user_vote = -1
    else:
        row.user_vote = None
    row.voted_at = datetime.now(timezone.utc) if req.state != "none" else None
    db.commit()
    background_tasks.add_task(retrain_and_rescore, topic_id)
    return {"status": "success", "topic_votes": _topic_votes(db, item_id)}


def _topic_votes(db: Session, item_id: str) -> list:
    from src.api.inbox import attach_topic_votes

    holder = [{"id": item_id}]
    attach_topic_votes(db, holder)
    return holder[0]["topic_votes"]


async def _zotero_push_quietly(item_id: str) -> None:
    from src.database import SessionLocal
    from src.integrations.zotero import ZoteroUnavailable, push_items

    db = SessionLocal()
    try:
        item = db.get(Item, item_id)
        if item:
            await push_items([item])
    except ZoteroUnavailable as e:
        print(f"Zotero auto-push skipped: {e}", flush=True)
    finally:
        db.close()
