"""Read a Zotero library to give topics a head start.

Two ways in, same REST shape (Zotero API v3):

  local  http://127.0.0.1:23119/api/users/0/...   Zotero 7+ desktop, no key.
         Needs Settings -> Advanced -> "Allow other applications on this
         computer to communicate with Zotero".
  web    https://api.zotero.org/users/<userID>/... with a read-only API key
         (zotero.org/settings/keys). Works without the desktop app.

A collection (or the whole library) becomes the seed set of a topic: its
papers are matched to Semantic Scholar by DOI / arXiv id / PMID and their
embeddings define the topic vector. Nothing is ever written to Zotero here.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import httpx

LOCAL_BASE = "http://127.0.0.1:23119/api/users/0"
WEB_BASE = "https://api.zotero.org/users/{user_id}"
PAGE = 100
MAX_ITEMS = 300  # most recently added items of a collection used as seeds

STOPWORDS = set(
    "a an and are as at be by for from in into is it its of on or that the their this to using with via we our new novel "
    "based study analysis approach method methods results towards toward between across under over during after through "
    "reveals reveal role roles effect effects can use high low large small human".split()
)


class ZoteroLibraryError(Exception):
    """Zotero is not reachable or refused the request; the message is user-facing."""


@dataclass
class ZoteroAccess:
    mode: str  # "local" | "web"
    user_id: str | None = None
    api_key: str | None = None

    @property
    def base(self) -> str:
        return LOCAL_BASE if self.mode == "local" else WEB_BASE.format(user_id=self.user_id)

    @property
    def headers(self) -> dict[str, str]:
        h = {"Zotero-API-Version": "3"}
        if self.mode == "web" and self.api_key:
            h["Zotero-API-Key"] = self.api_key
        return h


async def _get_all(access: ZoteroAccess, path: str, params: dict[str, Any] | None = None, limit: int | None = None) -> list[dict]:
    out: list[dict] = []
    start = 0
    async with httpx.AsyncClient() as client:
        while True:
            q = {"limit": PAGE, "start": start, "format": "json", **(params or {})}
            try:
                resp = await client.get(f"{access.base}{path}", params=q, headers=access.headers, timeout=20.0)
            except httpx.HTTPError as e:
                where = "the Zotero desktop app (is it running?)" if access.mode == "local" else "api.zotero.org"
                raise ZoteroLibraryError(f"Could not reach {where}: {e}") from e
            if resp.status_code == 403:
                hint = (
                    'Zotero refused: enable Settings -> Advanced -> "Allow other applications on this computer to communicate with Zotero".'
                    if access.mode == "local"
                    else "Zotero refused the API key (it needs read access to your library)."
                )
                raise ZoteroLibraryError(hint)
            if resp.status_code != 200:
                raise ZoteroLibraryError(f"Zotero answered {resp.status_code}: {resp.text[:160]}")
            page = resp.json()
            out.extend(page)
            start += PAGE
            if len(page) < PAGE or (limit and len(out) >= limit):
                break
    return out[:limit] if limit else out


async def status(access: ZoteroAccess) -> dict[str, Any]:
    try:
        await _get_all(access, "/collections", limit=1)
        return {"reachable": True, "mode": access.mode, "message": None}
    except ZoteroLibraryError as e:
        return {"reachable": False, "mode": access.mode, "message": str(e)}


async def list_collections(access: ZoteroAccess) -> list[dict[str, Any]]:
    """Collections with their full path ("Parent / Child") and item count, sorted by path."""
    raw = await _get_all(access, "/collections")
    by_key = {c["key"]: c for c in raw}

    def path(c: dict) -> str:
        names = [c["data"]["name"]]
        parent = c["data"].get("parentCollection")
        seen = set()
        while parent and parent in by_key and parent not in seen:
            seen.add(parent)
            names.append(by_key[parent]["data"]["name"])
            parent = by_key[parent]["data"].get("parentCollection")
        return " / ".join(reversed(names))

    cols = [
        {
            "key": c["key"],
            "name": c["data"]["name"],
            "path": path(c),
            "parent": c["data"].get("parentCollection") or None,
            "num_items": (c.get("meta") or {}).get("numItems", 0),
        }
        for c in raw
    ]
    return sorted(cols, key=lambda c: c["path"].lower())


ARXIV_RE = re.compile(r"arxiv(?:\.org/abs/|:\s*)(\d{4}\.\d{4,5})", re.I)
PMID_RE = re.compile(r"pmid:\s*(\d+)", re.I)


def identifier_for(data: dict[str, Any]) -> str | None:
    """Semantic Scholar batch identifier for a Zotero item, or None if it has none."""
    doi = (data.get("DOI") or "").strip()
    if not doi:
        m = re.search(r"doi\.org/(10\.\S+)", data.get("url") or "", re.I) or re.search(r"doi:\s*(10\.\S+)", data.get("extra") or "", re.I)
        doi = m.group(1) if m else ""
    if doi:
        return f"DOI:{doi}"
    blob = f"{data.get('url') or ''} {data.get('extra') or ''}"
    m = ARXIV_RE.search(blob)
    if m:
        return f"ARXIV:{m.group(1)}"
    m = PMID_RE.search(data.get("extra") or "")
    if m:
        return f"PMID:{m.group(1)}"
    return None


async def collection_items(access: ZoteroAccess, collection_key: str | None) -> list[dict[str, Any]]:
    """Top-level items (no notes/attachments) of a collection, or of the whole library."""
    path = f"/collections/{collection_key}/items/top" if collection_key else "/items/top"
    raw = await _get_all(access, path, params={"sort": "dateAdded", "direction": "desc"}, limit=MAX_ITEMS)
    items = []
    for r in raw:
        d = r.get("data") or {}
        if d.get("itemType") in ("attachment", "note", "annotation") or not d.get("title"):
            continue
        items.append({"key": r.get("key"), "title": d["title"], "identifier": identifier_for(d), "year": (d.get("date") or "")[:4]})
    return items


def suggest_keywords(titles: list[str], max_keywords: int = 5) -> list[str]:
    """Frequent two-word phrases (then single words) across the titles."""
    unigrams: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    for title in titles:
        words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", title.lower())]
        content = [w for w in words if w not in STOPWORDS]
        unigrams.update(set(content))
        pairs = {f"{a} {b}" for a, b in zip(words, words[1:]) if a not in STOPWORDS and b not in STOPWORDS}
        bigrams.update(pairs)
    min_count = max(2, len(titles) // 15)
    picked = [p for p, c in bigrams.most_common(12) if c >= min_count][:max_keywords]
    covered = {w for p in picked for w in p.split()}
    for w, c in unigrams.most_common(20):
        if len(picked) >= max_keywords:
            break
        if c >= min_count and w not in covered:
            picked.append(w)
    return picked
