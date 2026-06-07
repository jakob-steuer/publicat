import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List

ARXIV_OAI_URL = "http://export.arxiv.org/oai2"

async def harvest_arxiv_oai(sets: List[str], since: datetime) -> List[str]:
    """
    Harvests arXiv via OAI-PMH for the given sets (e.g., 'cs', 'q-bio').
    Returns a list of arXiv identifiers formatted for S2 (e.g., 'ARXIV:2405.12345').
    """
    discovered_ids = []
    from_date = since.strftime("%Y-%m-%d")
    
    # OAI-PMH uses namespaces
    namespaces = {
        'oai': 'http://www.openarchives.org/OAI/2.0/',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/'
    }
    
    async with httpx.AsyncClient() as client:
        for s in sets:
            url = f"{ARXIV_OAI_URL}?verb=ListRecords&metadataPrefix=oai_dc&set={s}&from={from_date}"
            try:
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    root = ET.fromstring(response.text)
                    
                    # Check for errors (e.g. noRecordsMatch)
                    error = root.find('oai:error', namespaces)
                    if error is not None:
                        continue
                        
                    records = root.findall('.//oai:record', namespaces)
                    for record in records:
                        header = record.find('oai:header', namespaces)
                        if header is not None:
                            identifier = header.find('oai:identifier', namespaces)
                            if identifier is not None and identifier.text:
                                # Format: oai:arXiv.org:2405.12345 -> ARXIV:2405.12345
                                raw_id = identifier.text
                                if raw_id.startswith("oai:arXiv.org:"):
                                    clean_id = raw_id.replace("oai:arXiv.org:", "ARXIV:")
                                    discovered_ids.append(clean_id)
            except Exception as e:
                print(f"Failed to harvest arXiv set {s}: {e}")
                
    return discovered_ids

async def harvest_biorxiv_api(since: datetime) -> List[str]:
    """
    bioRxiv doesn't natively support full OAI-PMH sets easily for delta.
    We use the bioRxiv API for recent preprints.
    https://api.biorxiv.org/details/biorxiv/{start_date}/{end_date}
    Returns DOIs formatted for S2.
    """
    discovered_ids = []
    start_date = since.strftime("%Y-%m-%d")
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    url = f"https://api.biorxiv.org/details/biorxiv/{start_date}/{end_date}/0"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                if "collection" in data:
                    for item in data["collection"]:
                        doi = item.get("doi")
                        if doi:
                            discovered_ids.append(doi)
        except Exception as e:
            print(f"Failed to harvest bioRxiv: {e}")
            
    return discovered_ids
