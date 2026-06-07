import asyncio
from datetime import datetime, timezone, timedelta
from src.sources.oai_pmh import harvest_arxiv_oai, harvest_biorxiv_api
import httpx

async def main():
    since = datetime.now(timezone.utc) - timedelta(days=3)
    arxiv_ids = await harvest_arxiv_oai(["cs", "q-bio"], since)
    biorxiv_ids = await harvest_biorxiv_api(since)
    
    ids = [f"ARXIV:{a}" for a in arxiv_ids] + [f"DOI:{d}" for d in biorxiv_ids]
    
    fields = "paperId,corpusId,title,abstract,authors,year,publicationDate,venue,externalIds,url,openAccessPdf,isOpenAccess,citationCount,referenceCount,influentialCitationCount,tldr,embedding.specter_v2,citationStyles"
    chunk_size = 100
    
    async with httpx.AsyncClient() as client:
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i+chunk_size]
            params = {"fields": fields}
            json_data = {"ids": chunk}
            
            resp = await client.post("https://api.semanticscholar.org/graph/v1/paper/batch", params=params, json=json_data)
            if resp.status_code == 400:
                print("400 on chunk:", chunk)
                print("Response:", resp.text)
                
if __name__ == "__main__":
    asyncio.run(main())
