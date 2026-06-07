import asyncio
from datetime import datetime, timezone, timedelta
from src.sources.semantic_scholar import discover_new_papers_s2
from src.database import SessionLocal
from src.models.topic import Topic
import httpx

async def main():
    db = SessionLocal()
    active_topics = db.query(Topic).filter(Topic.is_active, Topic.embedding.isnot(None)).all()
    db.close()
    
    since = datetime.now(timezone.utc) - timedelta(days=3)
    s2_discovered = await discover_new_papers_s2(active_topics, since)
    
    all_identifiers = set()
    for p in s2_discovered:
        if p.get("paperId"):
            all_identifiers.add(p["paperId"])
        elif p.get("corpusId"):
            all_identifiers.add(f"CorpusId:{p['corpusId']}")
            
    ids = list(all_identifiers)
    
    fields = "paperId,corpusId,title,abstract,authors,year,publicationDate,venue,externalIds,url,openAccessPdf,isOpenAccess,citationCount,referenceCount,influentialCitationCount,tldr,embedding.specter_v2,citationStyles"
    chunk_size = 100
    
    async with httpx.AsyncClient() as client:
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i+chunk_size]
            params = {"fields": fields}
            json_data = {"ids": chunk}
            
            resp = await client.post("https://api.semanticscholar.org/graph/v1/paper/batch", params=params, json=json_data)
            if resp.status_code == 400:
                print("400 on chunk:")
                print(chunk)
                print("Response:", resp.text)
                
if __name__ == "__main__":
    asyncio.run(main())
