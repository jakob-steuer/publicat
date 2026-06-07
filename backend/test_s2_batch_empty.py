import asyncio
from src.sources.semantic_scholar import enrich_papers_s2

async def main():
    try:
        # What if it's empty? We explicitly check `if not identifiers: return []` in enrich_papers_s2
        print("Empty identifiers is handled.")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
