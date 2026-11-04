"""The scorer's view of a paper and of the user's follows."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from src.models.follow import Follow
from src.models.item import Item

PREPRINT_VENUES = {"arxiv.org", "arxiv", "biorxiv", "medrxiv", "chemrxiv", "ssrn", "research square"}


def looks_like_preprint(venue: str | None, url: str | None, source: str | None) -> bool:
    v = (venue or "").lower()
    u = (url or "").lower()
    s = (source or "").lower()
    return v in PREPRINT_VENUES or any(p in u for p in ("arxiv", "biorxiv", "medrxiv")) or "arxiv" in s or "biorxiv" in s


@dataclass
class Paper:
    title: str
    abstract: str
    embedding: list[float] | None
    authors: list[dict[str, Any]]  # [{"name": str, "authorId": str|None, "orcid": str|None}]
    venue: str | None
    is_preprint: bool = False

    @classmethod
    def from_item(cls, item: Item) -> "Paper":
        authors = item.author_details or [{"name": a} for a in (item.authors or [])]
        return cls(
            title=item.title or "",
            abstract=item.abstract or "",
            embedding=item.embedding,
            authors=authors,
            venue=item.venue,
            is_preprint=looks_like_preprint(item.venue, item.url, item.source),
        )

    @classmethod
    def from_s2(cls, paper: dict[str, Any]) -> "Paper":
        authors = []
        for a in paper.get("authors") or []:
            if not a.get("name"):
                continue
            ext = a.get("externalIds") or {}
            authors.append({"name": a["name"], "authorId": a.get("authorId"), "orcid": ext.get("ORCID")})
        emb = paper.get("embedding")
        vector = emb.get("vector") if isinstance(emb, dict) else None
        return cls(
            title=paper.get("title") or "",
            abstract=paper.get("abstract") or "",
            embedding=vector,
            authors=authors,
            venue=paper.get("venue"),
            is_preprint=looks_like_preprint(paper.get("venue"), paper.get("url"), None),
        )


@dataclass
class Follows:
    authors: list[tuple[str, str, float]] = field(default_factory=list)  # (entity_value, display_name, boost)
    venues: dict[str, float] = field(default_factory=dict)


def load_follows(db: Session) -> Follows:
    follows = db.query(Follow).all()
    return Follows(
        authors=[(f.entity_value, f.display_name or f.entity_value, f.boost_value) for f in follows if f.entity_type == "author"],
        venues={f.entity_value.lower(): f.boost_value for f in follows if f.entity_type == "venue"},
    )


def author_matches(entity_value: str, authors: list[dict[str, Any]]) -> bool:
    """Match a follow (AUTHOR_ID:..., ORCID:... or a legacy plain name) against a paper's authors."""
    if entity_value.startswith("AUTHOR_ID:"):
        wanted = entity_value.split(":", 1)[1]
        return any(str(a.get("authorId")) == wanted for a in authors)
    if entity_value.startswith("ORCID:"):
        wanted = entity_value.split(":", 1)[1].lower()
        return any(wanted and wanted in str(a.get("orcid") or "").lower() for a in authors)
    needle = entity_value.lower()
    return any(needle in str(a.get("name") or "").lower() for a in authors)
