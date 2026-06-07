import asyncio
import httpx
from typing import List, Dict, Any
from datetime import datetime
from src.config import settings

S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_AUTHOR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/author/search"

# To avoid blowing up S2 rate limits
s2_semaphore = asyncio.Semaphore(1)

async def _fetch_s2_with_retry(client: httpx.AsyncClient, url: str, method: str = "GET", params: dict = None, json_data: dict = None, retries: int = 3):
    headers = {}
    if settings.s2_api_key:
        headers["x-api-key"] = settings.s2_api_key
        
    for attempt in range(retries):
        async with s2_semaphore:
            try:
                if method == "GET":
                    response = await client.get(url, params=params, headers=headers, timeout=20.0)
                else:
                    response = await client.post(url, params=params, json=json_data, headers=headers, timeout=30.0)
                
                if response.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                    
                response.raise_for_status()
                await asyncio.sleep(1.0) # Rate limit respect
                return response.json()
            except Exception as e:
                print(f"S2 API Error on {url}: {e}")
                await asyncio.sleep(2 ** attempt)
    return None

async def discover_new_papers_s2(topics: List[Any], since: datetime) -> List[Dict[str, str]]:
    """
    Search S2 for newly indexed papers matching the topics' keywords.
    Returns a list of dicts with 'corpusId', 'paperId', 'doi'.
    """
    discovered = []
    year_str = str(since.year)
    
    async with httpx.AsyncClient() as client:
        for topic in topics:
            # We use the topic name/description as the query. We'll simplify to just the name for broad search.
            query = topic.name
            
            params = {
                "query": query,
                "year": f"{year_str}:",
                "fields": "paperId,corpusId,externalIds,publicationDate,year",
                "limit": 50
            }
            
            data = await _fetch_s2_with_retry(client, S2_SEARCH_URL, method="GET", params=params)
            if data and "data" in data:
                for p in data["data"]:
                    doi = p.get("externalIds", {}).get("DOI")
                    discovered.append({
                        "paperId": p.get("paperId"),
                        "corpusId": str(p.get("corpusId")),
                        "doi": doi
                    })
    
    return discovered

async def enrich_papers_s2(identifiers: List[str]) -> List[Dict[str, Any]]:
    """
    Batch request to S2 to fetch rich metadata.
    `identifiers` can be a mix of CorpusIds or DOIs/arXiv IDs.
    """
    if not identifiers:
        return []
        
    enriched = []
    
    fields = "paperId,corpusId,title,abstract,authors,year,publicationDate,venue,externalIds,url,openAccessPdf,isOpenAccess,citationCount,referenceCount,influentialCitationCount,tldr,embedding.specter_v2,citationStyles"
    
    # S2 batch accepts max 1000, but we do chunks of 100 to be safe
    chunk_size = 100
    
    async with httpx.AsyncClient() as client:
        for i in range(0, len(identifiers), chunk_size):
            chunk = identifiers[i:i+chunk_size]
            params = {"fields": fields}
            json_data = {"ids": chunk}
            
            data = await _fetch_s2_with_retry(client, S2_BATCH_URL, method="POST", params=params, json_data=json_data)
            if data:
                enriched.extend(data)
                
    return enriched

async def search_authors_s2(query: str) -> List[Dict[str, Any]]:
    """
    Search S2 for authors by name.
    """
    if not query:
        return []
        
    results = []
    params = {
        "query": query,
        "fields": "authorId,name,url,hIndex,paperCount,affiliations",
        "limit": 10
    }
    
    async with httpx.AsyncClient() as client:
        data = await _fetch_s2_with_retry(client, S2_AUTHOR_SEARCH_URL, method="GET", params=params)
        if data and "data" in data:
            results = data["data"]
            
    return results
