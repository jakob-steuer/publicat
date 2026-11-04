import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.api.serialize import item_to_dict
from src.database import get_db
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.ranking.scoring import Paper, author_matches

router = APIRouter()

SECTION_LIMIT = 50


def _best_topic_lookup(db: Session, item_ids: list[str]) -> dict[str, tuple[str, str, list]]:
    """For the overview feed: which topic gave each item its (highest) score.

    The UI attributes votes made on the overview to that topic only, so feedback
    on one research topic cannot leak into another.
    """
    if not item_ids:
        return {}
    rows = (
        db.query(ItemScore.item_id, ItemScore.topic_id, ItemScore.final_score, Topic.name, ItemScore.reasons)
        .join(Topic, Topic.id == ItemScore.topic_id)
        .filter(ItemScore.item_id.in_(item_ids))
        .all()
    )
    best: dict[str, tuple[float, str, str, list]] = {}
    for item_id, topic_id, score, name, reasons in rows:
        if item_id not in best or (score or 0.0) > best[item_id][0]:
            best[item_id] = (score or 0.0, topic_id, name, reasons or [])
    return {k: (v[1], v[2], v[3]) for k, v in best.items()}


@router.get("/", response_model=Dict[str, Any])
def get_dashboard(
    topic_id: Optional[str] = None,
    author_id: Optional[str] = None,
    show_acknowledged: bool = False,
    show_preprints: bool = True,
    show_discarded: bool = False,
    min_score: float = 0.20,
    db: Session = Depends(get_db),
):
    topic_name = None
    if topic_id:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        topic_name = topic.name if topic else None
        base_query = (
            db.query(Item, ItemScore.final_score, ItemScore.user_vote, ItemScore.reasons)
            .join(ItemScore, Item.id == ItemScore.item_id)
            .filter(ItemScore.topic_id == topic_id, ItemScore.final_score >= min_score)
        )
    else:
        # No topic: best score across all topics per item.
        base_query = (
            db.query(Item, func.max(ItemScore.final_score).label("final_score"), func.max(ItemScore.user_vote).label("user_vote"))
            .outerjoin(ItemScore, Item.id == ItemScore.item_id)
            .group_by(Item.id)
            .having(func.max(ItemScore.final_score) >= min_score)
        )

    if not show_discarded:
        base_query = base_query.filter(Item.is_hidden == False)  # noqa: E712

    if author_id:
        if author_id.startswith("ORCID:"):
            orcid = author_id.split(":", 1)[1]
            base_query = base_query.filter(Item.raw_metadata_json.like(f'%"ORCID": "{orcid}"%'))
        else:
            aid = author_id.replace("AUTHOR_ID:", "")
            base_query = base_query.filter(Item.raw_metadata_json.like(f'%"authorId": "{aid}"%'))

    unfiltered_base_query = base_query

    if not show_acknowledged:
        base_query = base_query.filter(Item.is_acknowledged == False)  # noqa: E712

    if not show_preprints:
        is_preprint = (
            Item.source.in_(["OAI-PMH (arXiv)", "bioRxiv"])
            | Item.url.like("%arxiv%")
            | Item.url.like("%biorxiv%")
            | Item.url.like("%medrxiv%")
            | Item.venue.in_(["arXiv.org", "bioRxiv", "medRxiv"])
        )
        base_query = base_query.filter(~is_preprint)

    now = datetime.datetime.now(datetime.timezone.utc)
    week_ago = now - datetime.timedelta(days=7)
    month_ago = now - datetime.timedelta(days=30)
    eight_weeks_ago = now - datetime.timedelta(weeks=8)

    recent_query = base_query.filter(Item.published_at >= eight_weeks_ago)
    score_col = ItemScore.final_score if topic_id else "final_score"

    def ordered(q):
        return q.order_by(desc(score_col), desc(Item.published_at))

    if topic_id:
        do_not_miss_q = recent_query.filter(ItemScore.final_score >= 0.90)
    else:
        do_not_miss_q = recent_query.having(func.max(ItemScore.final_score) >= 0.90)

    raw_sections: dict[str, list] = {
        "do_not_miss": ordered(do_not_miss_q).limit(SECTION_LIMIT).all(),
        "this_week": ordered(recent_query.filter(Item.published_at >= week_ago)).limit(SECTION_LIMIT).all(),
        "this_month": ordered(recent_query.filter(Item.published_at >= month_ago, Item.published_at < week_ago)).limit(SECTION_LIMIT).all(),
        "starred": ordered(unfiltered_base_query.filter(Item.is_starred == True)).limit(SECTION_LIMIT).all(),  # noqa: E712
        "tools": ordered(recent_query.filter(Item.tools.isnot(None))).limit(SECTION_LIMIT).all(),
    }

    # Followed authors: match by Semantic Scholar id / ORCID / legacy name against
    # the stored author details (the entity_value is an id, not a name).
    author_follows = db.query(Follow).filter(Follow.entity_type == "author").all()
    highlighted: list = []
    if author_follows:
        for row in recent_query.all():
            paper = Paper.from_item(row[0])
            if any(author_matches(f.entity_value, paper.authors) for f in author_follows):
                highlighted.append(row)
        if topic_id:
            highlighted.sort(key=lambda r: r[1] or 0, reverse=True)
        else:
            highlighted.sort(key=lambda r: r[0].published_at, reverse=True)
        highlighted = highlighted[:SECTION_LIMIT]
    raw_sections["highlighted_authors"] = highlighted

    all_ids = list({row[0].id for rows in raw_sections.values() for row in rows})
    best_topic = {} if topic_id else _best_topic_lookup(db, all_ids)

    def serialize(row):
        item, score, vote = row[0], row[1], row[2]
        if topic_id:
            tid, tname, reasons = topic_id, topic_name, row[3]
        else:
            tid, tname, reasons = best_topic.get(item.id, (None, None, None))
        return item_to_dict(item, score, vote, tid, tname, reasons)

    return {name: [serialize(r) for r in rows] for name, rows in raw_sections.items()}
