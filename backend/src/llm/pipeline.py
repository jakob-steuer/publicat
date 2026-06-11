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
        
        primary_provider = None
        if anthropic_key:
            primary_provider = AnthropicProvider(anthropic_key)
        elif gemini_key:
            primary_provider = GeminiProvider(gemini_key)
        else:
            primary_provider = OllamaProvider()
            
        reranking_mode = get_config("reranking_mode", "llm") # "llm", "local", "disabled"
        
        # 0. Stage 2 Reranking (LLM Judge)
        active_topics = db.query(Topic).filter(Topic.is_active).all()
        if reranking_mode != "disabled":
            rerank_provider = primary_provider
            if reranking_mode == "local":
                rerank_provider = OllamaProvider()
                
            if rerank_provider:
                for topic in active_topics:
                    # Top 50 un-reranked papers for this topic
                    candidates = db.query(ItemScore, Item).join(
                        Item, ItemScore.item_id == Item.id
                    ).filter(
                        ItemScore.topic_id == topic.id,
                        ItemScore.llm_relevance_score == None,
                        ItemScore.final_score >= 0.3
                    ).order_by(ItemScore.final_score.desc()).limit(50).all()
                    
                    total_candidates = len(candidates)
                    for idx, (score, item) in enumerate(candidates):
                        try:
                            import asyncio
                            from src.api.items import sync_state
                            while sync_state["status"] == "paused":
                                await asyncio.sleep(1.0)
                            if sync_state["status"] == "aborted":
                                return
                                
                            # Update progress bar dynamically (0 to 10 for reranking phase)
                            if sync_state["status"] == "running":
                                progress_pct = int(10 * (idx / max(1, total_candidates)))
                                sync_state["progress"] = progress_pct
                                sync_state["message"] = f"Stage 2 Reranking ({idx+1}/{total_candidates}) for {topic.name}..."
                        except ImportError:
                            pass
                            
                        print(f"Reranking item {item.id} against topic {topic.name} using {rerank_provider.__class__.__name__}")
                        abstract_text = f"{item.title}\n\n{item.abstract}"
                        llm_score, reason = await rerank_provider.evaluate_relevance(abstract_text, topic.description)
                        
                        score.llm_relevance_score = float(llm_score)
                        relevance_multiplier = 0.5 + (score.llm_relevance_score / 100.0) # 0 -> 0.5x, 100 -> 1.5x
                        score.final_score = score.semantic_score * relevance_multiplier
                        
                        score.reasons = list(score.reasons) + [f"LLM Relevance: {llm_score}/10. {reason}"]
                        
                        db.commit()
        
        # 1. Identify all items in the Dashboard Top 6
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
                    
            summary, rel_score = await primary_provider.summarize_brief(abstract_text, topic_desc)
            
            if summary:
                item.t2_summary = summary
                if item_score and item_score.llm_relevance_score is None:
                    # Legacy fallback if reranking was skipped
                    item_score.llm_relevance_score = float(rel_score * 10) # convert 1-10 to 1-100
                    relevance_multiplier = 0.5 + (item_score.llm_relevance_score / 100.0)
                    item_score.final_score = item_score.semantic_score * relevance_multiplier
                db.commit()
                
        # Primary Deep Summarization (for high relevance items missing it)
        primary_candidates = db.query(ItemScore, Item, Topic).join(
            Item, ItemScore.item_id == Item.id
        ).join(
            Topic, ItemScore.topic_id == Topic.id
        ).filter(
            Item.id.in_(target_item_ids),
            Item.tools is None
        ).all()
        
        for score, item, topic in primary_candidates:
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
                tools = await primary_provider.extract_keywords(abstract_text, topic.description)
                item.tools = tools
                db.commit()
            else:
                print(f"Running deep summarization for item: {item.id} on topic: {topic.name}")
                deep_summary, tools = await primary_provider.summarize_deep(abstract_text, topic.description)
                if deep_summary:
                    item.t3_summary = deep_summary
                    item.tools = tools
                    db.commit()
                
    except Exception as e:
        print(f"Pipeline error: {e}")
    finally:
        if owns_db:
            db.close()
