import asyncio

from src import jobs
from src.llm.base import LLMProvider
from src.llm.budget import cost_usd, month_spend, over_budget, record_spend
from src.llm.pipeline import _run_concurrently


def test_run_exclusive_refuses_a_second_job():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow():
            started.set()
            await release.wait()
            return "done"

        first = asyncio.create_task(jobs.run_exclusive("first", slow))
        await started.wait()
        assert jobs.is_busy() and jobs.state["job"] == "first"
        second = await jobs.run_exclusive("second", slow)  # refused immediately
        assert second is None and jobs.state["job"] == "first"
        release.set()
        assert await first == "done"
        assert not jobs.is_busy() and jobs.state["status"] == "idle" and jobs.state["progress"] == 100

    asyncio.run(scenario())


def test_run_exclusive_records_errors_and_recovers():
    async def scenario():
        async def boom():
            raise RuntimeError("nope")

        assert await jobs.run_exclusive("bad", boom) is None
        assert jobs.state["status"] == "error" and "nope" in jobs.state["message"]
        jobs.state.update(status="idle")

        async def ok():
            return 1

        assert await jobs.run_exclusive("good", ok) == 1

    asyncio.run(scenario())


class FakeProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def evaluate_relevance(self, text, topic_desc):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        self.add_usage(500, 20)
        if "fail" in text:
            raise RuntimeError("provider error")
        return 80, "ok"

    async def summarize_brief(self, text, topic_desc):
        return "s", 8

    async def summarize_deep(self, text, topic_desc):
        return "d", []

    async def extract_keywords(self, text, topic_desc):
        return []

    async def generate(self, prompt):
        return ""


def test_concurrent_calls_are_bounded_and_failures_isolated():
    jobs.state.update(status="running")
    p = FakeProvider()
    texts = [f"paper {i}" for i in range(10)] + ["fail me"]
    results = asyncio.run(_run_concurrently(p, [lambda t=t: p.evaluate_relevance(t, "topic") for t in texts], "test", 0, 10))
    jobs.state.update(status="idle")
    assert 1 < p.max_active <= 4
    assert sum(r is not None for r in results) == 10 and results[-1] is None
    assert p.errors == 1 and p.calls == 11 and p.input_tokens == 5500


def test_budget_accounting(db):
    assert abs(cost_usd("anthropic", 1_000_000, 1_000_000) - 0.60) < 1e-9
    assert cost_usd("ollama", 10**9, 10**9) == 0.0
    record_spend(db, "anthropic", 2_000_000, 0)  # $0.20
    record_spend(db, "anthropic", 0, 1_000_000)  # +$0.50
    assert abs(month_spend(db, "anthropic") - 0.70) < 1e-9
    assert not over_budget(db, "anthropic", 5.0)
    assert over_budget(db, "anthropic", 0.5)
    assert not over_budget(db, "ollama", 0.0)


def test_on_result_commits_each_result_as_it_arrives():
    jobs.state.update(status="running")
    p = FakeProvider()
    seen = []
    asyncio.run(_run_concurrently(p, [lambda t=t: p.evaluate_relevance(t, "x") for t in ["a", "b", "fail", "c"]], "t", 0, 1, on_result=lambda i, r: seen.append(i)))
    jobs.state.update(status="idle")
    assert sorted(seen) == [0, 1, 3]  # the failed call never reaches on_result


def test_lookback_days_follows_last_complete_sync(db):
    from datetime import datetime, timedelta, timezone

    from src.api.items import lookback_days
    from src.models.app_config import AppConfig

    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert lookback_days(db, now) == 3  # never synced completely
    db.add(AppConfig(key="last_complete_sync_at", value=(now - timedelta(days=1)).isoformat()))
    db.commit()
    assert lookback_days(db, now) == 3  # recent: minimum window
    db.query(AppConfig).filter(AppConfig.key == "last_complete_sync_at").update({"value": (now - timedelta(days=7)).isoformat()})
    db.commit()
    assert lookback_days(db, now) == 8  # off for a week: catch up (+1 day margin)
    db.query(AppConfig).filter(AppConfig.key == "last_complete_sync_at").update({"value": (now - timedelta(days=90)).isoformat()})
    db.commit()
    assert lookback_days(db, now) == 30  # capped


def test_sync_run_is_logged_as_partial_when_requests_failed(client, db, monkeypatch):
    from src.api import items as items_api

    async def fake_ingestion(db_, days_back):
        jobs.count("stored", 5)
        jobs.note_error("S2 chunk failed")

    async def fake_pipeline(db_):
        return None

    monkeypatch.setattr(items_api, "run_ingestion", fake_ingestion)
    monkeypatch.setattr(items_api, "run_summarization_pipeline", fake_pipeline)
    monkeypatch.setattr(items_api, "cleanup_old_items", lambda db_: 0)
    assert asyncio.run(items_api.full_sync(db, name="test sync")) is True
    runs = client.get("/items/sync_runs").json()
    assert runs[0]["status"] == "partial" and runs[0]["errors"] == 1 and runs[0]["counters"]["stored"] == 5
    settings = client.get("/settings/").json()
    assert settings["last_synced_at"] and settings["last_complete_sync_at"] is None
    assert "failed request" in jobs.state["message"]

    # a clean run advances the complete marker
    async def clean_ingestion(db_, days_back):
        jobs.count("stored", 1)

    monkeypatch.setattr(items_api, "run_ingestion", clean_ingestion)
    asyncio.run(items_api.full_sync(db, name="test sync 2"))
    assert client.get("/items/sync_runs").json()[0]["status"] == "complete"
    assert client.get("/settings/").json()["last_complete_sync_at"]
