"""Start topics from a Zotero library: list collections, preview one as a topic draft."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src.integrations import zotero_library as zl
from src.models.app_config import AppConfig
from src.sources.semantic_scholar import lookup_papers_s2

router = APIRouter()

MAX_SEEDS = 200


def _conf(db: Session, key: str) -> str:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    return row.value if row and row.value else ""


async def _first_reachable(db: Session) -> zl.ZoteroAccess:
    """Prefer the desktop app; fall back to the web API if it is configured."""
    local = zl.ZoteroAccess("local")
    st = await zl.status(local)
    if st["reachable"]:
        return local
    user_id, api_key = _conf(db, "zotero_user_id"), _conf(db, "zotero_api_key")
    if user_id and api_key:
        web = zl.ZoteroAccess("web", user_id, api_key)
        if (await zl.status(web))["reachable"]:
            return web
    raise HTTPException(status_code=503, detail=st["message"] or "Zotero is not reachable.")


@router.get("/status", response_model=Dict[str, Any])
async def library_status(db: Session = Depends(get_db)):
    local = await zl.status(zl.ZoteroAccess("local"))
    user_id, api_key = _conf(db, "zotero_user_id"), _conf(db, "zotero_api_key")
    web = await zl.status(zl.ZoteroAccess("web", user_id, api_key)) if user_id and api_key else {"reachable": False, "mode": "web", "message": "No Zotero user ID / API key stored."}
    return {"local": local, "web": web, "available": local["reachable"] or web["reachable"]}


@router.get("/collections", response_model=List[Dict[str, Any]])
async def collections(db: Session = Depends(get_db)):
    access = await _first_reachable(db)
    try:
        return await zl.list_collections(access)
    except zl.ZoteroLibraryError as e:
        raise HTTPException(status_code=503, detail=str(e))


class PreviewRequest(BaseModel):
    collection_key: Optional[str] = None  # None = whole library
    collection_name: Optional[str] = None


@router.post("/preview", response_model=Dict[str, Any])
async def preview(req: PreviewRequest, db: Session = Depends(get_db)):
    """Turn a collection into a topic draft: seed papers matched on Semantic Scholar plus suggested keywords.

    Nothing is saved; the client shows the draft for editing and creates the topic itself.
    """
    access = await _first_reachable(db)
    try:
        items = await zl.collection_items(access, req.collection_key)
    except zl.ZoteroLibraryError as e:
        raise HTTPException(status_code=503, detail=str(e))

    with_id = [i for i in items if i["identifier"]]
    found = await lookup_papers_s2([i["identifier"] for i in with_id], fields="paperId,title,year")
    seeds, unresolved = [], [i["title"] for i in items if not i["identifier"]]
    for item, paper in zip(with_id, found):
        if paper and paper.get("paperId"):
            seeds.append({"paperId": paper["paperId"], "title": paper.get("title") or item["title"]})
        else:
            unresolved.append(item["title"])
    name = req.collection_name or "My Zotero library"
    return {
        "name": name.split(" / ")[-1],
        "description": f"Research like the papers in my Zotero collection '{name}'.",
        "suggested_keywords": zl.suggest_keywords([i["title"] for i in items]),
        "seed_papers": seeds[:MAX_SEEDS],
        "total_items": len(items),
        "matched": len(seeds),
        "unresolved_titles": unresolved[:8],
        "unresolved_count": len(unresolved),
        "source": access.mode,
    }
