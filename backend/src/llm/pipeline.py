from sqlalchemy.orm import Session
from src.database import SessionLocal
from src.models.item_score import ItemScore
from src.models.item import Item
from src.models.topic import Topic
from src.models.app_config import AppConfig
from src.llm.gemini import GeminiProvider
from src.llm.anthropic import AnthropicProvider
from src.llm.ollama import OllamaProvider

async def run_summarization_pipeline(db: Session = None):
    """
    Background task to process LLM summaries for top items.
    Ensures all Top 6 dashboard items and Starred items have AI summaries.
    """
    owns_db = False
    if db is None:
        db = SessionLocal()
        owns_db = True
        
    try:
        from src.api.dashboard import get_dashboard
        
        # Get configurations
        def get_config(key: str, default: str = "") -> str:
            conf = db.query(AppConfig).filter(AppConfig.key == key).first()
            return conf.value if conf else default
            
        gemini_key = get_config("gemini_api_key")
        anthropic_key = get_config("anthropic_api_key")
        
        tier2_provider = GeminiProvider(gemini_key) if gemini_key else OllamaProvider()
        tier3_provider = AnthropicProvider(anthropic_key) if anthropic_key else tier2_provider
        
        # 1. Identify all items in the Dashboard Top 6
        active_topics = db.query(Topic).filter(Topic.is_active).all()
        target_item_ids = set()
        
        # Default generic dashboard (no topic)
        dash = get_dashboard(topic_id=None, show_acknowledged=False, db=db)
        for section in ["do_not_miss", "this_week", "this_month", "trending", "highlighted_authors", "starred"]:
            items = dash.get(section, [])[:6]
            for it in items:
                target_item_ids.add(it["id"])
                
        # Per-topic dashboards
        for topic in active_topics:
            dash = get_dashboard(topic_id=topic.id, show_acknowledged=False, db=db)
            for section in ["do_not_miss", "this_week", "this_month", "trending", "highlighted_authors", "starred"]:
                items = dash.get(section, [])[:6]
                for it in items:
                    target_item_ids.add(it["id"])
                    
        # 2. Fetch those items from DB that lack a t1_tldr AND lack a t2_summary
        items_to_summarize = db.query(Item).filter(
            Item.id.in_(target_item_ids), 
            Item.t1_tldr is None,
            Item.t2_summary is None
        ).all()
        
        total_items = len(items_to_summarize)
        
        for idx, item in enumerate(items_to_summarize):
            try:
                import asyncio
                from src.api.items import sync_state
                while sync_state["status"] == "paused":
                    await asyncio.sleep(1.0)
                if sync_state["status"] == "aborted":
                    return
                    
                # Update progress bar dynamically (90 to 99)
                if sync_state["status"] == "running":
                    progress_pct = 90 + int(9 * (idx / max(1, total_items)))
                    sync_state["progress"] = progress_pct
                    sync_state["message"] = f"Generating AI summary {idx+1} of {total_items}..."
            except ImportError:
                pass
            
            print(f"Running Nature Briefing summarization for item: {item.id}")
            abstract_text = f"{item.title}\n\n{item.abstract}"
            # Use a generic topic description if not bound to one, or use the first topic's desc
            item_score = db.query(ItemScore).filter(ItemScore.item_id == item.id).order_by(ItemScore.semantic_score.desc()).first()
            topic_desc = "cutting-edge scientific research"
            if item_score:
                t = db.query(Topic).filter(Topic.id == item_score.topic_id).first()
                if t:
                    topic_desc = t.description
                    
            summary, rel_score = await tier2_provider.summarize_brief(abstract_text, topic_desc)
            
            if summary:
                item.t2_summary = summary
                if item_score:
                    item_score.llm_relevance_score = float(rel_score)
                    # Boost final score based on relevance
                    relevance_multiplier = 0.5 + (item_score.llm_relevance_score / 20.0)
                    item_score.final_score = item_score.semantic_score * relevance_multiplier
                db.commit()
                
        # Tier 3 remains unchanged (deep dive for high relevance items)
        tier3_candidates = db.query(ItemScore, Item, Topic).join(
            Item, ItemScore.item_id == Item.id
        ).join(
            Topic, ItemScore.topic_id == Topic.id
        ).filter(
            Item.id.in_(target_item_ids),
            Item.tools is None
        ).all()
        
        for score, item, topic in tier3_candidates:
            try:
                import asyncio
                from src.api.items import sync_state
                while sync_state["status"] == "paused":
                    await asyncio.sleep(1.0)
                if sync_state["status"] == "aborted":
                    return
            except ImportError:
                pass
                
            abstract_text = f"{item.title}\n\n{item.abstract}"
            if item.t1_tldr:
                print(f"S2 TLDR present. Running Keyword Extraction for item: {item.id} on topic: {topic.name}")
                abstract_text += f"\n\nTLDR Summary: {item.t1_tldr}"
                tools = await tier3_provider.extract_keywords(abstract_text, topic.description)
                item.tools = tools
                db.commit()
            else:
                print(f"Running Tier 3 summarization for item: {item.id} on topic: {topic.name}")
                deep_summary, tools = await tier3_provider.summarize_deep(abstract_text, topic.description)
                if deep_summary:
                    item.t3_summary = deep_summary
                    item.tools = tools
                    db.commit()
                
    except Exception as e:
        print(f"Pipeline error: {e}")
    finally:
        if owns_db:
            db.close()
