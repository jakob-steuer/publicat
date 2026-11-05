"""Stage 2 LLM judge and AI summaries.

Calls run concurrently (a few at a time for cloud providers, one at a time for
Ollama), results are written to the database on the event loop, and every
phase books its token usage against the monthly budget. When the budget for
the month is spent, the LLM phases are skipped and the sync says so.
"""
import asyncio
from typing import Awaitable, Callable, TypeVar

from sqlalchemy.orm import Session

from src import jobs
from src.database import SessionLocal
from src.llm.anthropic import AnthropicProvider
from src.llm.base import LLMProvider
from src.llm.budget import month_spend, over_budget, record_spend
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
CLOUD_CONCURRENCY = 4
LOCAL_CONCURRENCY = 1

T = TypeVar("T")


def _config(db: Session, key: str, default: str = "") -> str:
    conf = db.query(AppConfig).filter(AppConfig.key == key).first()
    return conf.value if conf and conf.value else default


def choose_providers(db: Session) -> tuple[LLMProvider, LLMProvider | None]:
    """(summariser, reranker) from the stored keys and the reranking mode."""
    anthropic_key = _config(db, "anthropic_api_key")
    gemini_key = _config(db, "gemini_api_key")
    if anthropic_key:
        primary: LLMProvider = AnthropicProvider(anthropic_key)
    elif gemini_key:
        primary = GeminiProvider(gemini_key)
    else:
        primary = OllamaProvider()
    mode = _config(db, "reranking_mode", "llm")  # llm | local | disabled
    if mode == "disabled":
        return primary, None
    return primary, (OllamaProvider() if mode == "local" else primary)


async def _run_concurrently(
    provider: LLMProvider,
    tasks: list[Callable[[], Awaitable[T]]],
    label: str,
    base_progress: int,
    span: int,
    on_result: Callable[[int, T], None] | None = None,
) -> list[T | None]:
    """Run provider calls a few at a time, honouring pause/abort and updating progress.

    `on_result(index, result)` runs on the event loop as soon as each call
    returns, so callers can commit every result immediately: an interrupted
    phase keeps what was already paid for.
    """
    sem = asyncio.Semaphore(CLOUD_CONCURRENCY if provider.is_cloud else LOCAL_CONCURRENCY)
    results: list[T | None] = [None] * len(tasks)
    done = 0

    async def one(i: int, fn: Callable[[], Awaitable[T]]):
        nonlocal done
        async with sem:
            if not await jobs.wait_if_paused():
                return
            try:
                results[i] = await fn()
                if on_result is not None and results[i] is not None:
                    on_result(i, results[i])
            except Exception as e:  # one failed call must not stop the batch
                provider.errors += 1
                jobs.note_error(f"LLM call failed ({label}): {e!r}")
            done += 1
            jobs.set_progress(base_progress + int(span * done / max(1, len(tasks))), f"{label} ({done}/{len(tasks)})...")

    await asyncio.gather(*(one(i, fn) for i, fn in enumerate(tasks)))
    return results


def _book(db: Session, provider: LLMProvider) -> None:
    calls, inp, out = provider.take_usage()
    if calls:
        total = record_spend(db, provider.name, inp, out)
        print(f"LLM usage ({provider.name}): {calls} calls, {inp} in / {out} out tokens, month total ${total:.4f}", flush=True)


async def run_summarization_pipeline(db: Session = None):
    """Stage 2 LLM reranking, then AI summaries for the items shown on the dashboards."""
    owns_db = False
    if db is None:
        db = SessionLocal()
        owns_db = True

    try:
        from src.api.dashboard import get_dashboard

        primary, reranker = choose_providers(db)
        budget = float(_config(db, "anthropic_budget_limit", "5.0") or 0)
        active_topics = db.query(Topic).filter(Topic.is_active == True).all()  # noqa: E712
        follows = load_follows(db)
        models = await asyncio.to_thread(load_models, db, active_topics)  # loads background stats, off the loop

        def budget_ok(provider: LLMProvider) -> bool:
            if over_budget(db, provider.name, budget):
                msg = f"Monthly LLM budget (${budget:.2f}) reached for {provider.name}; skipping LLM steps until next month."
                print(msg, flush=True)
                jobs.set_progress(jobs.state.get("progress", 90), msg)
                return False
            return True

        # ---- Stage 2: LLM judge becomes a feature of the ranker for uncertain papers ----
        if reranker is not None and budget_ok(reranker):
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
                if not candidates:
                    continue
                if jobs.aborted():
                    return
                def apply_rerank(i: int, res, topic=topic, candidates=candidates):
                    score, item = candidates[i]
                    llm_score, _reason = res
                    score.llm_relevance_score = float(llm_score)
                    apply_to_entry(score, score_against_topic(Paper.from_item(item), topic, models[topic.id], follows, float(llm_score)))
                    db.commit()

                await _run_concurrently(
                    reranker,
                    [lambda item=item: reranker.evaluate_relevance(f"{item.title}\n\n{item.abstract}", topic.description) for _s, item in candidates],
                    f"Stage 2 reranking for {topic.name}",
                    0,
                    10,
                    on_result=apply_rerank,
                )
                _book(db, reranker)

        if not budget_ok(primary):
            return

        # ---- Which items are visible on the dashboards (overview + per topic) ----
        def visible_item_ids() -> set[str]:
            ids: set[str] = set()
            dashboards = [get_dashboard(topic_id=None, show_acknowledged=False, db=db)]
            dashboards += [get_dashboard(topic_id=t.id, show_acknowledged=False, db=db) for t in active_topics]
            for dash in dashboards:
                for section in DASHBOARD_SECTIONS:
                    for it in dash.get(section, [])[:SUMMARIES_PER_SECTION]:
                        ids.add(it["id"])
            return ids

        target_item_ids = await asyncio.to_thread(visible_item_ids)  # several queries + author matching
        if not target_item_ids:
            return

        # ---- Brief summaries for visible items that have neither a TLDR nor a summary ----
        items_to_summarize = db.query(Item).filter(Item.id.in_(target_item_ids), Item.t1_tldr.is_(None), Item.t2_summary.is_(None)).all()
        if items_to_summarize and not jobs.aborted():
            contexts = []
            for item in items_to_summarize:
                item_score = db.query(ItemScore).filter(ItemScore.item_id == item.id).order_by(ItemScore.final_score.desc()).first()
                topic = db.get(Topic, item_score.topic_id) if item_score else None
                contexts.append((item, item_score, topic))
            def apply_summary(i: int, res):
                item, item_score, topic = contexts[i]
                summary, rel_score = res
                if not summary:
                    return
                item.t2_summary = summary
                if item_score and topic and item_score.llm_relevance_score is None:
                    item_score.llm_relevance_score = float(rel_score) * 10.0
                    apply_to_entry(item_score, score_against_topic(Paper.from_item(item), topic, models[topic.id], follows, item_score.llm_relevance_score))
                db.commit()

            await _run_concurrently(
                primary,
                [lambda item=item, topic=topic: primary.summarize_brief(f"{item.title}\n\n{item.abstract}", topic.description if topic else "cutting-edge scientific research") for item, _s, topic in contexts],
                "Generating AI summaries",
                90,
                9,
                on_result=apply_summary,
            )
            _book(db, primary)

        # ---- Deep summary / tool extraction for visible items that lack it ----
        rows = (
            db.query(Item, Topic)
            .join(ItemScore, ItemScore.item_id == Item.id)
            .join(Topic, ItemScore.topic_id == Topic.id)
            .filter(Item.id.in_(target_item_ids), Item.tools.is_(None))
            .all()
        )
        seen: set[str] = set()
        pending = []
        for item, topic in rows:
            if item.id not in seen:
                seen.add(item.id)
                pending.append((item, topic))
        if pending and not jobs.aborted():

            async def deep(item: Item, topic: Topic):
                text = f"{item.title}\n\n{item.abstract}"
                if item.t1_tldr:
                    return None, await primary.extract_keywords(f"{text}\n\nTLDR Summary: {item.t1_tldr}", topic.description)
                return await primary.summarize_deep(text, topic.description)

            def apply_deep(i: int, res):
                item, _topic = pending[i]
                deep_summary, tools = res
                if deep_summary:
                    item.t3_summary = deep_summary
                item.tools = tools if tools is not None else []
                db.commit()

            await _run_concurrently(primary, [lambda i=item, t=topic: deep(i, t) for item, topic in pending], "Extracting tools", 99, 1, on_result=apply_deep)
            _book(db, primary)

    except Exception as e:
        print(f"Pipeline error: {e!r}", flush=True)
    finally:
        if owns_db:
            db.close()


def llm_spend_this_month(db: Session) -> float:
    return month_spend(db)
