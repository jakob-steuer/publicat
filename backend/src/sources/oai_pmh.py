"""Preprint firehoses: arXiv (OAI-PMH) and bioRxiv (details API).

Both are paged. Earlier versions read only the first page, which for bioRxiv
meant 30 of ~1,100 preprints in three days.
"""
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List

import httpx

from src import jobs

ARXIV_OAI_URL = "https://oaipmh.arxiv.org/oai"
ARXIV_MAX_PAGES = 12  # per set; a page holds up to ~1,000 records
ARXIV_TIMEOUT = 120.0

BIORXIV_URL = "https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}"
BIORXIV_MAX_PAGES = 150  # newest pages are kept when a window has more

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}


async def _get_with_retry(client: httpx.AsyncClient, url: str, timeout: float, attempts: int = 3) -> httpx.Response | None:
    """GET that honours 503 Retry-After (arXiv asks clients to slow down this way)."""
    for attempt in range(attempts):
        try:
            resp = await client.get(url, timeout=timeout)
        except httpx.HTTPError as e:
            if attempt == attempts - 1:
                raise
            print(f"  retrying {url[:70]}... ({type(e).__name__})", flush=True)
            await asyncio.sleep(3 * (attempt + 1))
            continue
        if resp.status_code == 503 and attempt < attempts - 1:
            wait = min(float(resp.headers.get("Retry-After", "10") or 10), 30.0)
            await asyncio.sleep(wait)
            continue
        return resp
    return None


async def harvest_arxiv_oai(sets: List[str], since: datetime) -> List[str]:
    """arXiv identifiers ('ARXIV:2405.12345') of records in the given OAI sets updated since `since`."""
    discovered: list[str] = []
    from_date = since.strftime("%Y-%m-%d")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for s in sets:
            url = f"{ARXIV_OAI_URL}?verb=ListRecords&metadataPrefix=oai_dc&set={s}&from={from_date}"
            pages = 0
            try:
                while url and pages < ARXIV_MAX_PAGES and not jobs.aborted():
                    resp = await _get_with_retry(client, url, ARXIV_TIMEOUT)
                    if resp is None or resp.status_code != 200:
                        jobs.note_error(f"arXiv harvest for set {s} answered {resp.status_code if resp is not None else 'nothing'}")
                        break
                    root = ET.fromstring(resp.text)
                    if root.find("oai:error", NS) is not None:
                        break  # e.g. noRecordsMatch
                    for header in root.iterfind(".//oai:record/oai:header", NS):
                        ident = header.findtext("oai:identifier", default="", namespaces=NS)
                        if ident.startswith("oai:arXiv.org:"):
                            discovered.append(ident.replace("oai:arXiv.org:", "ARXIV:"))
                    pages += 1
                    token = (root.findtext(".//oai:resumptionToken", default="", namespaces=NS) or "").strip()
                    url = f"{ARXIV_OAI_URL}?verb=ListRecords&resumptionToken={token}" if token else ""
                if url and pages >= ARXIV_MAX_PAGES:
                    print(f"  arXiv set {s}: stopped after {pages} pages (more available)", flush=True)
            except Exception as e:
                jobs.note_error(f"arXiv harvest failed for set {s}: {type(e).__name__} {e}".strip())

    return list(dict.fromkeys(discovered))


async def harvest_biorxiv_api(since: datetime) -> List[str]:
    """DOIs of bioRxiv preprints posted since `since` (all pages of the details API)."""
    start = since.strftime("%Y-%m-%d")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dois: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            first = await _get_with_retry(client, BIORXIV_URL.format(start=start, end=end, cursor=0), 30.0)
            if first is None or first.status_code != 200:
                jobs.note_error(f"bioRxiv answered {first.status_code if first is not None else 'nothing'}")
                return []
            data = first.json()
            meta = (data.get("messages") or [{}])[0]
            page_size = int(meta.get("count") or len(data.get("collection", [])) or 0)
            total = int(meta.get("total") or 0)
            if page_size == 0:
                return []
            cursors = list(range(0, total, page_size))
            if len(cursors) > BIORXIV_MAX_PAGES:
                print(f"  bioRxiv: {total} preprints in the window, keeping the newest {BIORXIV_MAX_PAGES * page_size}", flush=True)
                cursors = cursors[-BIORXIV_MAX_PAGES:]
            for n, cursor in enumerate(cursors):
                if jobs.aborted():
                    break
                if cursor == 0:
                    page = data
                else:
                    resp = await _get_with_retry(client, BIORXIV_URL.format(start=start, end=end, cursor=cursor), 30.0)
                    if resp is None or resp.status_code != 200:
                        jobs.note_error(f"bioRxiv page at cursor {cursor} answered {resp.status_code if resp is not None else 'nothing'}")
                        continue
                    page = resp.json()
                dois.extend(item["doi"] for item in page.get("collection", []) if item.get("doi"))
                if n % 10 == 0:
                    jobs.set_progress(25 + int(10 * n / max(1, len(cursors))), f"Discovering bioRxiv preprints ({len(dois)}/{total})...")
        except Exception as e:
            jobs.note_error(f"bioRxiv harvest failed: {type(e).__name__} {e}".strip())

    return list(dict.fromkeys(dois))
