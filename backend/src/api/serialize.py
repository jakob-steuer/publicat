"""Shared item serialisation for API responses.

Strips the 768-float embedding and the raw Semantic Scholar record: together
they are ~35 KB per paper and were being shipped with every dashboard load.
"""
from typing import Any, Optional

from src.models.item import Item

HEAVY_FIELDS = ("embedding", "raw_metadata_json", "citation_styles", "_sa_instance_state")


def item_to_dict(
    item: Item,
    score: Optional[float] = None,
    user_vote: Optional[int] = None,
    topic_id: Optional[str] = None,
    topic_name: Optional[str] = None,
    reasons: Optional[list] = None,
) -> dict[str, Any]:
    d = {k: v for k, v in item.__dict__.items() if k not in HEAVY_FIELDS}
    if score is not None:
        d["score"] = score
    if user_vote is not None:
        d["user_vote"] = user_vote
    if topic_id is not None:
        d["topic_id"] = topic_id
    if topic_name is not None:
        d["topic_name"] = topic_name
    if reasons is not None:
        d["reasons"] = reasons
    return d
