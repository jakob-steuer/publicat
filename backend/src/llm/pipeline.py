import asyncio

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.llm.anthropic import AnthropicProvider
from src.llm.gemini import GeminiProvider
from src.llm.ollama import OllamaProvider
from src.models.app_config import AppConfig
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.ranking.paper import Paper, load_follows
from src.ranking.scoring import apply_to_entry, score_against_topic
from src.ranking.training import load_models

DASHBOARD_SECTIONS = ["do_not_miss", "this_week", "this_month", "trending", "highlighted_authors", "starred"]
SUMMARIES_PER_SECTION = 6
RERANK_CANDIDATES_PER_TOPIC = 50
# Only judge the uncertain band: clear hits and clear misses do not need an LLM opinion.
RERANK_BAND = (0.30, 0.90)


async def _wait_if_paused() -> bool:
    """Block while the sync is paused; return False if it was aborted."""
    from src.api.items import sync_state

    while sync_state["status"] == "paused":
        await asyncio.sleep(1.0)
    return sync_state["status"] != "aborted"


def _set_progress(progress: int, message: str) -> None:
    from src.api.items import sync_state

    if sync_state["status"] == "running":
        sync_state["progress"] = progress
        sync_state["message"] = message


async def run_summarization_pipeline(db: Session = None):
    """Stage 2 LLM reranking, then AI summaries for the items shown on the dashboards."""
    owns_db = False
    if db is None:
        db = SessionLocal()
        owns_db = True

    try:
        from src.api.dashboard import get_dashboard

        def get_config(key: str, default: str = "") -> str:
            conf = db.query(AppConfig).filter(AppConfig.key == key).first()
            return conf.value if conf and conf.value else default

        anthropic_key = get_config("anthropic_api_key")
        gemini_key = get_config("gemini_api_key")
        if anthropic_key:
            primary_provider = AnthropicProvider(anthropic_key)
        elif gemini_key:
            primary_provider = GeminiProvider(gemini_key)
        else:
            primary_provider = OllamaProvider()

        reranking_mode = get_config("reranking_mode", "llm")  # "llm", "local", "disabled"
        active_topics = db.query(Topic).filter(Topic.is_active == True).all()  # noqa: E712
        follows = load_follows(db)
        models = load_models(db, active_topics)

        # ---- Stage 2: LLM judge becomes a feature of the ranker for uncertain papers ----
        if reranking_mode != "disabled":
            rerank_provider = OllamaProvider() if reranking_mode == "local" else primary_provider
            for topic in active_topics:
                candidates = (
                    db.query(ItemScore, Item)
                    .join(Item, ItemScore.item_id == Item.id)
                    .filter(
                        ItemScore.topic_id == topic.id,
                        ItemScore.llm_relevance_score.is_(None),
                        ItemScore.final_score >= RERANK_BAND[0],
                        ItemScore.final_score <= RERANK_BAND[1],
                        Item.is_acknowledged == False,  # noqa: E712
                    )
                    .order_by(ItemScore.final_score.desc())
                    .limit(RERANK_CANDIDATES_PER_TOPIC)
                    .all()
                )
                total = len(candidates)
                for idx, (score, item) in enumerate(candidates):
                    if not await _wait_if_paused():
                        return
                    _set_progress(int(10 * idx / max(1, total)), f"Stage 2 reranking ({idx + 1}/{total}) for {topic.name}...")
                    llm_score, _reason = await rerank_provider.evaluate_relevance(f"{item.title}\n\n{item.abstract}", topic.description)
                    score.llm_relevance_score = float(llm_score)
                    apply_to_entry(score, score_against_topic(Paper.from_item(item), topic, models[topic.id], follows, float(llm_score)))
                    db.commit()

        # ---- Which items are visible on the dashboards (overview + per topic) ----
        target_item_ids: set[str] = set()
        dashboards = [get_dashboard(topic_id=None, show_acknowledged=False, db=db)]
        dashboards += [get_dashboard(topic_id=t.id, show_acknowledged=False, db=db) for t in active_topics]
        for dash in dashboards:
            for section in DASHBOARD_SECTIONS:
                for it in dash.get(section, [])[:SUMMARIES_PER_SECTION]:
                    target_item_ids.add(it["id"])

        if not target_item_ids:
            return

        # ---- Brief summaries for visible items that have neither a TLDR nor a summary ----
        items_to_summarize = (
            db.query(Item)
            .filter(Item.id.in_(target_item_ids), Item.t1_tldr.is_(None), Item.t2_summary.is_(None))
            .all()
        )
        total = len(items_to_summarize)
        for idx, item in enumerate(items_to_summarize):
            if not await _wait_if_paused():
                return
            _set_progress(90 + int(9 * idx / max(1, total)), f"Generating AI summary {idx + 1} of {total}...")

            item_score = db.query(ItemScore).filter(ItemScore.item_id == item.id).order_by(ItemScore.final_score.desc()).first()
            topic = db.get(Topic, item_score.topic_id) if item_score else None
            topic_desc = topic.description if topic else "cutting-edge scientific research"

            summary, rel_score = await primary_provider.summarize_brief(f"{item.title}\n\n{item.abstract}", topic_desc)
            if summary:
                item.t2_summary = summary
                if item_score and topic and item_score.llm_relevance_score is None:
                    item_score.llm_relevance_score = float(rel_score) * 10.0
                    apply_to_entry(item_score, score_against_topic(Paper.from_item(item), topic, models[topic.id], follows, item_score.llm_relevance_score))
                db.commit()

        # ---- Deep summary / tool extraction for visible items that lack it ----
        primary_candidates = (
            db.query(Item, Topic)
            .join(ItemScore, ItemScore.item_id == Item.id)
            .join(Topic, ItemScore.topic_id == Topic.id)
            .filter(Item.id.in_(target_item_ids), Item.tools.is_(None))
            .all()
        )
        seen: set[str] = set()
        for item, topic in primary_candidates:
            if item.id in seen:
                continue
            seen.add(item.id)
            if not await _wait_if_paused():
                return

            abstract_text = f"{item.title}\n\n{item.abstract}"
            if item.t1_tldr:
                abstract_text += f"\n\nTLDR Summary: {item.t1_tldr}"
                item.tools = await primary_provider.extract_keywords(abstract_text, topic.description)
                db.commit()
            else:
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
