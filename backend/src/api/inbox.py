"""The triage inbox: one ranked, paginated, searchable list per scope.

Replaces assembling the feed from six capped dashboard sections on the client.
"""
import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from src.api.serialize import item_to_dict
from src.database import get_db
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic

router = APIRouter()

MAX_LIMIT = 200


def preprint_clause():
    # coalesce: NOT (NULL IN (...)) is NULL in SQL and would drop venue-less papers
    venue = func.coalesce(Item.venue, "")
    url = func.coalesce(Item.url, "")
    return (
        func.coalesce(Item.source, "").in_(["OAI-PMH (arXiv)", "bioRxiv"])
        | url.like("%arxiv%")
        | url.like("%biorxiv%")
        | url.like("%medrxiv%")
        | venue.in_(["arXiv.org", "bioRxiv", "medRxiv"])
    )


def _followed_author_clause(db: Session):
    """SQL filter for papers by any followed author (S2 id, ORCID or legacy name)."""
    clauses = []
    for f in db.query(Follow).filter(Follow.entity_type == "author").all():
        value = f.entity_value
        if value.startswith("AUTHOR_ID:"):
            clauses.append(Item.author_details.like(f'%"authorId": "{value.split(":", 1)[1]}"%'))
        elif value.startswith("ORCID:"):
            clauses.append(Item.author_details.like(f'%{value.split(":", 1)[1]}%'))
        else:
            clauses.append(Item.authors.like(f"%{value}%"))
    return or_(*clauses) if clauses else None


def _author_clause(author_id: str):
    if author_id.startswith("ORCID:"):
        return Item.author_details.like(f'%{author_id.split(":", 1)[1]}%')
    return Item.author_details.like(f'%"authorId": "{author_id.replace("AUTHOR_ID:", "")}"%')


def _best_rows(db: Session, item_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Best-scoring (topic, score, vote, reasons) per item, for the all-topics scope."""
    if not item_ids:
        return {}
    rows = (
        db.query(ItemScore.item_id, ItemScore.topic_id, ItemScore.final_score, ItemScore.user_vote, ItemScore.reasons, Topic.name)
        .join(Topic, Topic.id == ItemScore.topic_id)
        .filter(ItemScore.item_id.in_(item_ids))
        .all()
    )
    best: dict[str, dict[str, Any]] = {}
    for item_id, topic_id, score, vote, reasons, name in rows:
        cur = best.get(item_id)
        # prefer the row that carries a vote, then the highest score
        key = (vote is not None, score or 0.0)
        if cur is None or key > cur["_key"]:
            best[item_id] = {"_key": key, "topic_id": topic_id, "topic_name": name, "score": score, "vote": vote, "reasons": reasons or []}
    return best


@router.get("/", response_model=Dict[str, Any])
def get_inbox(
    topic_id: Optional[str] = None,
    author_id: Optional[str] = None,
    min_score: float = 0.5,
    days: int = 56,
    show_acknowledged: bool = False,
    show_preprints: bool = True,
    show_discarded: bool = False,
    q: Optional[str] = None,
    filter: str = "all",  # all | top | week | month | authors | starred
    sort: str = "score",  # score | date
    limit: int = 50,
    offset: int = 0,
    wildcards: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, MAX_LIMIT))
    now = datetime.datetime.now(datetime.timezone.utc)

    if topic_id:
        query = (
            db.query(Item, ItemScore.final_score.label("score"))
            .join(ItemScore, ItemScore.item_id == Item.id)
            .filter(ItemScore.topic_id == topic_id)
        )
        score_col = ItemScore.final_score
    else:
        best = (
            db.query(ItemScore.item_id.label("item_id"), func.max(ItemScore.final_score).label("score"))
            .join(Topic, Topic.id == ItemScore.topic_id)
            .group_by(ItemScore.item_id)
            .subquery()
        )
        query = db.query(Item, best.c.score.label("score")).join(best, best.c.item_id == Item.id)
        score_col = best.c.score

    if filter == "starred":
        query = query.filter(Item.is_starred == True)  # noqa: E712
    else:
        query = query.filter(score_col >= min_score)
        if days > 0:
            query = query.filter(Item.published_at >= now - datetime.timedelta(days=days))
        if not show_acknowledged:
            query = query.filter(Item.is_acknowledged == False)  # noqa: E712
    if not show_discarded:
        query = query.filter(Item.is_hidden == False)  # noqa: E712
    if not show_preprints:
        query = query.filter(~preprint_clause())
    if author_id:
        query = query.filter(_author_clause(author_id))

    if filter == "top":
        query = query.filter(score_col >= 0.9)
    elif filter == "week":
        query = query.filter(Item.published_at >= now - datetime.timedelta(days=7))
    elif filter == "month":
        query = query.filter(Item.published_at >= now - datetime.timedelta(days=30))
    elif filter == "authors":
        clause = _followed_author_clause(db)
        query = query.filter(clause) if clause is not None else query.filter(False)

    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(Item.title.like(needle), Item.abstract.like(needle), Item.authors.like(needle), Item.venue.like(needle)))

    total = query.count()
    if sort == "date":
        query = query.order_by(desc(Item.published_at), desc(score_col))
    else:
        query = query.order_by(desc(score_col), desc(Item.published_at))
    rows = query.offset(offset).limit(limit).all()

    items = []
    if topic_id:
        topic = db.get(Topic, topic_id)
        ids = [r[0].id for r in rows]
        detail = {
            s.item_id: s
            for s in db.query(ItemScore).filter(ItemScore.topic_id == topic_id, ItemScore.item_id.in_(ids)).all()
        } if ids else {}
        for item, score in rows:
            s = detail.get(item.id)
            items.append(item_to_dict(item, score, s.user_vote if s else None, topic_id, topic.name if topic else None, s.reasons if s else None))
    else:
        best_rows = _best_rows(db, [r[0].id for r in rows])
        for item, score in rows:
            b = best_rows.get(item.id, {})
            items.append(item_to_dict(item, score, b.get("vote"), b.get("topic_id"), b.get("topic_name"), b.get("reasons")))

    # ---- Wildcards: a few papers from just below the threshold, against the filter bubble ----
    # The ranker only ever learns from what it chose to show. Showing a handful it would
    # have hidden lets votes correct it when interests drift, and measures what is missed.
    if wildcards > 0 and offset == 0 and filter == "all" and not (q and q.strip()) and not author_id and min_score > WILDCARD_FLOOR:
        shown = {i["id"] for i in items}
        picks = _wildcards(db, topic_id, min_score, days, show_preprints, now, min(wildcards, 10), shown)
        if topic_id:
            topic = db.get(Topic, topic_id)
            for item, score, s in picks:
                d = item_to_dict(item, score, s.user_vote if s else None, topic_id, topic.name if topic else None, s.reasons if s else None)
                d["wildcard"] = True
                items.append(d)
        else:
            names = {t.id: t.name for t in db.query(Topic).all()}
            for item, score, row in picks:
                d = item_to_dict(item, score, row.user_vote if row else None, row.topic_id if row else None, names.get(row.topic_id) if row else None, row.reasons if row else None)
                d["wildcard"] = True
                items.append(d)

    attach_topic_votes(db, items)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def attach_topic_votes(db: Session, items: list[dict]) -> None:
    """Add `topic_votes` to each serialised item: its score and vote in every topic it has a row for."""
    ids = [i["id"] for i in items]
    if not ids:
        return
    rows = (
        db.query(ItemScore.item_id, ItemScore.topic_id, Topic.name, ItemScore.final_score, ItemScore.user_vote)
        .join(Topic, Topic.id == ItemScore.topic_id)
        .filter(ItemScore.item_id.in_(ids))
        .order_by(Topic.priority, Topic.created_at)
        .all()
    )
    by_item: dict[str, list[dict]] = {}
    for item_id, tid, name, score, vote in rows:
        by_item.setdefault(item_id, []).append({"topic_id": tid, "topic_name": name, "score": score, "vote": vote})
    for i in items:
        i["topic_votes"] = by_item.get(i["id"], [])


WILDCARD_FLOOR = 0.2  # never surface papers the ranker considers plain noise
WILDCARD_BAND = 0.3  # how far below the threshold wildcards are drawn from


def _wildcards(db: Session, topic_id: Optional[str], min_score: float, days: int, show_preprints: bool, now, n: int, exclude: set):
    """Unread papers whose (best) score lies in [min_score - band, min_score): a stable daily sample.

    All-topics scope: a paper qualifies only if its *best* score over all topics is in
    the band (otherwise it is a normal inbox paper), and picks rotate over the topics
    so every topic contributes. The sample is keyed on the date, so the same wildcards
    are shown all day instead of changing on every refresh.
    """
    import hashlib

    low = max(WILDCARD_FLOOR, min_score - WILDCARD_BAND)
    q = (
        db.query(ItemScore.item_id, ItemScore.topic_id, ItemScore.final_score)
        .join(Item, Item.id == ItemScore.item_id)
        .join(Topic, Topic.id == ItemScore.topic_id)
        .filter(Item.is_acknowledged == False, Item.is_hidden == False)  # noqa: E712
    )
    if topic_id:
        q = q.filter(ItemScore.topic_id == topic_id, ItemScore.final_score >= low, ItemScore.final_score < min_score)
    else:
        q = q.filter(ItemScore.final_score >= low)  # need every row >= low to know each paper's best score
    if days > 0:
        q = q.filter(Item.published_at >= now - datetime.timedelta(days=days))
    if not show_preprints:
        q = q.filter(~preprint_clause())

    best: dict[str, tuple[str, float]] = {}  # item_id -> (topic_id of best score, best score)
    for item_id, tid, score in q.all():
        cur = best.get(item_id)
        if cur is None or (score or 0.0) > cur[1]:
            best[item_id] = (tid, score or 0.0)

    day = now.strftime("%Y-%m-%d")
    by_topic: dict[str, list[str]] = {}
    for item_id, (tid, score) in best.items():
        if item_id in exclude or not (low <= score < min_score):
            continue
        by_topic.setdefault(tid, []).append(item_id)
    for ids in by_topic.values():
        ids.sort(key=lambda i: hashlib.sha1(f"{day}:{i}".encode()).hexdigest())

    # round-robin over topics (in a stable order) until n papers are picked
    picked: list[str] = []
    order = sorted(by_topic, key=lambda t: hashlib.sha1(f"{day}:{t}".encode()).hexdigest())
    rank = 0
    while len(picked) < n and any(rank < len(by_topic[t]) for t in order):
        for t in order:
            if rank < len(by_topic[t]) and len(picked) < n:
                picked.append(by_topic[t][rank])
        rank += 1
    if not picked:
        return []

    items = {i.id: i for i in db.query(Item).filter(Item.id.in_(picked)).all()}
    rows = {
        (r.item_id, r.topic_id): r
        for r in db.query(ItemScore).filter(ItemScore.item_id.in_(picked)).all()
    }
    return [(items[i], best[i][1], rows.get((i, best[i][0]))) for i in picked if i in items]


@router.get("/counts", response_model=Dict[str, Any])
def get_counts(min_score: float = 0.5, days: int = 56, show_preprints: bool = True, db: Session = Depends(get_db)):
    """Unread papers above the threshold, overall and per topic (sidebar badges)."""
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    base = (
        db.query(ItemScore.topic_id, ItemScore.item_id)
        .join(Item, Item.id == ItemScore.item_id)
        .join(Topic, Topic.id == ItemScore.topic_id)
        .filter(
            ItemScore.final_score >= min_score,
            Item.is_acknowledged == False,  # noqa: E712
            Item.is_hidden == False,  # noqa: E712
        )
    )
    if days > 0:
        base = base.filter(Item.published_at >= since)
    if not show_preprints:
        base = base.filter(~preprint_clause())
    per_topic: dict[str, set] = {}
    all_items: set = set()
    for topic_id, item_id in base.all():
        per_topic.setdefault(topic_id, set()).add(item_id)
        all_items.add(item_id)
    return {"all": len(all_items), "topics": {k: len(v) for k, v in per_topic.items()}}
