import asyncio
from datetime import datetime, timezone, timedelta
from src.sources.oai_pmh import harvest_arxiv_oai, harvest_biorxiv_api
from src.sources.semantic_scholar import enrich_papers_s2

async def main():
    since = datetime.now(timezone.utc) - timedelta(days=3)
    arxiv_ids = await harvest_arxiv_oai(["cs", "q-bio"], since)
    print("arxiv:", len(arxiv_ids))
    biorxiv_ids = await harvest_biorxiv_api(since)
    print("biorxiv:", len(biorxiv_ids))
    
    ids = [f"ARXIV:{a}" for a in arxiv_ids] + [f"DOI:{d}" for d in biorxiv_ids]
    print("total to fetch:", len(ids))
    
    try:
        res = await enrich_papers_s2(ids)
        print("Success?", len(res))
    except Exception as e:
        print("FAIL!", e)

if __name__ == "__main__":
    asyncio.run(main())
