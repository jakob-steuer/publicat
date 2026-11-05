"""Push papers into the running Zotero desktop app through its local connector server.

Zotero listens on 127.0.0.1:23119 for the browser connector; the same endpoint
accepts items from any local process, so no API key or write access to the
Zotero web library is needed. Items land in the currently selected collection.
"""
from __future__ import annotations

import html
import os
import uuid
from typing import Any

import httpx

from src.models.item import Item

CONNECTOR = os.environ.get("PUBLICAT_ZOTERO_CONNECTOR", "http://127.0.0.1:23119")
HEADERS = {"Content-Type": "application/json", "X-Zotero-Connector-API-Version": "3", "X-Zotero-Version": "7.0"}


class ZoteroUnavailable(Exception):
    """Zotero desktop is not running (or the connector port is not reachable)."""


def _creators(item: Item) -> list[dict[str, str]]:
    creators = []
    for name in item.authors or []:
        parts = name.strip().split()
        if len(parts) >= 2:
            creators.append({"firstName": " ".join(parts[:-1]), "lastName": parts[-1], "creatorType": "author"})
        elif parts:
            creators.append({"lastName": parts[0], "creatorType": "author"})
    return creators


def build_zotero_item(item: Item) -> dict[str, Any]:
    summary = item.t3_summary or item.t2_summary or item.t1_tldr
    is_preprint = (item.venue or "").lower() in {"arxiv.org", "biorxiv", "medrxiv"}
    z: dict[str, Any] = {
        "itemType": "preprint" if is_preprint else "journalArticle",
        "title": item.title,
        "creators": _creators(item),
        "abstractNote": item.abstract if item.abstract and item.abstract != "No abstract available." else "",
        "date": item.published_at.strftime("%Y-%m-%d") if item.published_at else "",
        "url": item.url or (f"https://doi.org/{item.doi}" if item.doi else ""),
        "DOI": item.doi or "",
        "tags": [{"tag": t} for t in (item.tools or [])] + [{"tag": "Publicat"}],
        "notes": [],
        "attachments": [],
    }
    if is_preprint:
        z["repository"] = item.venue
    else:
        z["publicationTitle"] = item.venue or ""
    if summary:
        z["notes"].append({"note": f"<p><b>AI summary (Publicat)</b></p><p>{html.escape(summary)}</p>"})
    if item.open_access_pdf_url:
        z["attachments"].append({"title": "Full Text PDF", "url": item.open_access_pdf_url, "mimeType": "application/pdf"})
    return z


async def ping() -> bool:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{CONNECTOR}/connector/ping", timeout=2.0)
            return resp.status_code == 200
    except Exception:
        return False


async def push_items(items: list[Item]) -> int:
    """Save items into Zotero. Returns the number of items sent. Raises ZoteroUnavailable."""
    if not items:
        return 0
    payload = {"items": [build_zotero_item(i) for i in items], "uri": "publicat://starred", "sessionID": str(uuid.uuid4())}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{CONNECTOR}/connector/saveItems", json=payload, headers=HEADERS, timeout=30.0)
    except httpx.HTTPError as e:
        raise ZoteroUnavailable(str(e)) from e
    if resp.status_code not in (200, 201):
        raise ZoteroUnavailable(f"Zotero answered {resp.status_code}: {resp.text[:200]}")
    return len(items)
