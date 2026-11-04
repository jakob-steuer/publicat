import asyncio
from datetime import datetime
from typing import Any, Dict, List

import httpx

from src.config import settings
from src.database import SessionLocal
from src.models.app_config import AppConfig

S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
S2_SEARCH_URL = f"{S2_GRAPH}/paper/search"
S2_BULK_SEARCH_URL = f"{S2_GRAPH}/paper/search/bulk"
S2_BATCH_URL = f"{S2_GRAPH}/paper/batch"
S2_AUTHOR_SEARCH_URL = f"{S2_GRAPH}/author/search"
S2_AUTHOR_PAPERS_URL = f"{S2_GRAPH}/author/{{author_id}}/papers"
S2_RECOMMEND_URL = "https://api.semanticscholar.org/recommendations/v1/papers"

ID_FIELDS = "paperId,corpusId,externalIds,publicationDate,year"
ENRICH_FIELDS = (
    "paperId,corpusId,title,abstract,authors.authorId,authors.name,authors.externalIds,"
    "year,publicationDate,venue,externalIds,url,openAccessPdf,isOpenAccess,citationCount,"
    "referenceCount,influentialCitationCount,tldr,embedding.specter_v2,citationStyles"
)

# One request at a time: the free tier is rate limited globally.
s2_semaphore = asyncio.Semaphore(1)


def _api_key() -> str | None:
    db = SessionLocal()
    try:
        conf = db.query(AppConfig).filter(AppConfig.key == "s2_api_key").first()
        return conf.value if conf and conf.value else settings.s2_api_key
    finally:
        db.close()


async def _fetch_s2_with_retry(client: httpx.AsyncClient, url: str, method: str = "GET", params: dict = None, json_data: dict = None, retries: int = 3):
    headers = {}
    key = _api_key()
    if key:
        headers["x-api-key"] = key

    for attempt in range(retries):
        async with s2_semaphore:
            try:
                if method == "GET":
                    response = await client.get(url, params=params, headers=headers, timeout=20.0)
                else:
                    response = await client.post(url, params=params, json=json_data, headers=headers, timeout=30.0)
                if response.status_code == 429:
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                await asyncio.sleep(1.0)  # rate-limit respect
                return response.json()
            except Exception as e:
                print(f"S2 API Error on {url}: {e}")
                await asyncio.sleep(2**attempt)
    return None


def _date_str(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _query_for_topic(topic: Any) -> str:
    """Bulk-search query: the topic name plus each keyword as an OR'ed phrase."""
    kws = [k.strip() for k in (topic.keywords or "").split(",") if k.strip()]
    phrases = [f'"{topic.name}"'] + [f'"{k}"' for k in kws]
    return " | ".join(phrases)


async def search_papers_bulk_s2(client: httpx.AsyncClient, query: str, since: datetime, limit: int = 1000) -> List[Dict[str, Any]]:
    """Newest papers matching a boolean query, published on/after `since`."""
    params = {
        "query": query,
        "publicationDateOrYear": f"{_date_str(since)}:",
        "sort": "publicationDate:desc",
        "fields": ID_FIELDS,
    }
    data = await _fetch_s2_with_retry(client, S2_BULK_SEARCH_URL, params=params)
    return (data or {}).get("data", [])[:limit]


async def recommend_papers_s2(client: httpx.AsyncClient, positive_ids: List[str], negative_ids: List[str], limit: int = 100) -> List[Dict[str, Any]]:
    """Semantic Scholar's recommender seeded with the user's starred/upvoted (and downvoted) papers."""
    if not positive_ids:
        return []
    body = {"positivePaperIds": positive_ids[:100], "negativePaperIds": negative_ids[:100]}
    data = await _fetch_s2_with_retry(client, S2_RECOMMEND_URL, method="POST", params={"fields": ID_FIELDS, "limit": limit}, json_data=body)
    return (data or {}).get("recommendedPapers", [])


async def author_papers_s2(client: httpx.AsyncClient, author_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    data = await _fetch_s2_with_retry(client, S2_AUTHOR_PAPERS_URL.format(author_id=author_id), params={"fields": ID_FIELDS, "limit": limit})
    return (data or {}).get("data", [])


def _published_after(paper: Dict[str, Any], since: datetime) -> bool:
    date = paper.get("publicationDate")
    if date:
        try:
            return datetime.strptime(date, "%Y-%m-%d") >= since.replace(tzinfo=None)
        except ValueError:
            pass
    year = paper.get("year")
    return year is None or year >= since.year


async def discover_new_papers_s2(topics: List[Any], since: datetime, feedback: Dict[str, Dict[str, List[str]]] | None = None, author_ids: List[str] | None = None) -> List[Dict[str, Any]]:
    """Discover candidate papers for all topics.

    - date-sorted bulk search on each topic's name + keywords
    - S2 recommendations seeded with each topic's positive/negative votes
    - recent papers of followed authors (S2 author ids)
    Returns dicts with paperId / corpusId / externalIds.
    """
    feedback = feedback or {}
    discovered: Dict[str, Dict[str, Any]] = {}

    def add(papers):
        for p in papers:
            if p and p.get("paperId") and _published_after(p, since):
                discovered.setdefault(p["paperId"], p)

    async with httpx.AsyncClient() as client:
        for topic in topics:
            add(await search_papers_bulk_s2(client, _query_for_topic(topic), since))
            fb = feedback.get(topic.id) or {}
            if fb.get("positive"):
                add(await recommend_papers_s2(client, fb["positive"], fb.get("negative", [])))
        for author_id in author_ids or []:
            add(await author_papers_s2(client, author_id))
    return list(discovered.values())


async def search_papers_s2(query: str, limit: int = 10, fields: str = "paperId,title,year,venue,authors.name,externalIds") -> List[Dict[str, Any]]:
    """Relevance-ranked paper search (seed-paper picker, cold-start topic vector)."""
    if not query:
        return []
    async with httpx.AsyncClient() as client:
        data = await _fetch_s2_with_retry(client, S2_SEARCH_URL, params={"query": query, "fields": fields, "limit": limit})
    return (data or {}).get("data", [])


async def enrich_papers_s2(identifiers: List[str]) -> List[Dict[str, Any]]:
    """Batch request for rich metadata. `identifiers` may mix paperIds, CorpusId:, DOI:, ARXIV: ids."""
    if not identifiers:
        return []
    enriched = []
    chunk_size = 100  # the endpoint allows 500, smaller chunks keep responses manageable
    async with httpx.AsyncClient() as client:
        for i in range(0, len(identifiers), chunk_size):
            chunk = identifiers[i : i + chunk_size]
            data = await _fetch_s2_with_retry(client, S2_BATCH_URL, method="POST", params={"fields": ENRICH_FIELDS}, json_data={"ids": chunk})
            if data:
                enriched.extend(p for p in data if p)
    return enriched


async def search_authors_s2(query: str) -> List[Dict[str, Any]]:
    if not query:
        return []
    async with httpx.AsyncClient() as client:
        data = await _fetch_s2_with_retry(client, S2_AUTHOR_SEARCH_URL, params={"query": query, "fields": "authorId,name,url,hIndex,paperCount,affiliations", "limit": 10})
    return (data or {}).get("data", [])
