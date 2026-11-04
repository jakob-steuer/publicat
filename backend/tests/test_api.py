"""Regression tests for the features that were silently broken, plus the vote -> retrain loop."""
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from src.api.items import cleanup_old_items
from src.db_migrate import NEW_COLUMNS, upgrade
from src.models.app_config import AppConfig
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.models.topic_model import TopicModel
from tests.conftest import unit_vector


def _item(db, title, days_old=1, starred=False, authors=None, emb=None, emb_seed=11):
    authors = authors or [{"name": "Some One", "authorId": "42", "orcid": "0000-0002-0000-0001"}]
    it = Item(
        source="SemanticScholar",
        source_native_id=title,
        title=title,
        abstract="abstract",
        authors=[a["name"] for a in authors],
        author_details=authors,
        published_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        url="https://example.org",
        raw_metadata_json={},
        embedding=emb or unit_vector(emb_seed),
        is_starred=starred,
    )
    db.add(it)
    db.flush()
    return it


def _topic(db, name, seed):
    t = Topic(name=name, description="d", prior_vector=unit_vector(seed))
    db.add(t)
    db.flush()
    return t


def test_vote_from_overview_goes_to_best_topic_only(client, db):
    t1, t2 = _topic(db, "A", 1), _topic(db, "B", 2)
    it = _item(db, "paper")
    db.add(ItemScore(item_id=it.id, topic_id=t1.id, semantic_score=0.3, final_score=0.3))
    db.add(ItemScore(item_id=it.id, topic_id=t2.id, semantic_score=0.8, final_score=0.8))
    db.commit()

    r = client.post(f"/items/{it.id}/vote", json={"topic_id": None, "vote": 1})
    assert r.json() == {"status": "success", "topic_id": t2.id}
    db.expire_all()
    votes = {s.topic_id: s.user_vote for s in db.query(ItemScore).all()}
    assert votes == {t1.id: None, t2.id: 1}
    assert db.query(ItemScore).filter(ItemScore.topic_id == t2.id).one().voted_at is not None

    # Explicit topic wins over best score.
    client.post(f"/items/{it.id}/vote", json={"topic_id": t1.id, "vote": -1})
    db.expire_all()
    votes = {s.topic_id: s.user_vote for s in db.query(ItemScore).all()}
    assert votes == {t1.id: -1, t2.id: 1}
    assert db.get(Item, it.id).is_hidden is True

    # Un-rating clears everywhere.
    client.post(f"/items/{it.id}/vote", json={"topic_id": None, "vote": None})
    db.expire_all()
    assert all(s.user_vote is None for s in db.query(ItemScore).all())


def test_votes_retrain_the_topic_and_rescore_feed(client, db):
    """After votes, the topic has a trained model and papers like the upvoted ones rank higher."""
    topic = _topic(db, "A", 1)
    liked = np.array(unit_vector(20))
    disliked = np.array(unit_vector(21))

    def mix(base, seed, w=0.8):
        v = w * base + (1 - w) * np.array(unit_vector(seed))
        return (v / np.linalg.norm(v)).tolist()

    items = []
    for i in range(30):
        emb = mix(liked if i % 2 == 0 else disliked, 100 + i)
        it = _item(db, f"p{i}", emb=emb)
        db.add(ItemScore(item_id=it.id, topic_id=topic.id, semantic_score=0.5, final_score=0.5))
        items.append((it, i % 2 == 0))
    probe_like = _item(db, "probe-like", emb=mix(liked, 999))
    probe_dislike = _item(db, "probe-dislike", emb=mix(disliked, 998))
    for probe in (probe_like, probe_dislike):
        db.add(ItemScore(item_id=probe.id, topic_id=topic.id, semantic_score=0.5, final_score=0.5))
    db.commit()

    for it, good in items:
        client.post(f"/items/{it.id}/vote", json={"topic_id": topic.id, "vote": 1 if good else -1})

    # background retrain runs in the TestClient's thread pool
    for _ in range(50):
        db.expire_all()
        row = db.get(TopicModel, topic.id)
        if row and row.n_pos == 15 and row.n_neg == 15:
            break
        time.sleep(0.1)
    assert row is not None and row.n_pos == 15 and row.n_neg == 15
    assert row.cv_auc is not None and row.cv_auc > 0.8

    db.expire_all()
    s_like = db.query(ItemScore).filter(ItemScore.item_id == probe_like.id).one()
    s_dislike = db.query(ItemScore).filter(ItemScore.item_id == probe_dislike.id).one()
    assert s_like.final_score > s_dislike.final_score
    assert any("upvoted" in r for r in s_like.reasons)


def test_dashboard_marks_best_topic_and_finds_followed_authors(client, db):
    t1, t2 = _topic(db, "A", 1), _topic(db, "B", 2)
    it = _item(db, "paper")
    db.add(ItemScore(item_id=it.id, topic_id=t1.id, semantic_score=0.4, final_score=0.4, reasons=["low"]))
    db.add(ItemScore(item_id=it.id, topic_id=t2.id, semantic_score=0.9, final_score=0.95, reasons=["Relevance 95%"]))
    db.add(Follow(entity_type="author", entity_value="ORCID:0000-0002-0000-0001", display_name="Some One"))
    db.commit()

    dash = client.get("/dashboard/").json()
    card = dash["this_week"][0]
    assert card["topic_id"] == t2.id and card["topic_name"] == "B"
    assert card["reasons"] == ["Relevance 95%"]
    assert "embedding" not in card and "raw_metadata_json" not in card
    assert [c["id"] for c in dash["highlighted_authors"]] == [it.id]
    assert [c["id"] for c in dash["do_not_miss"]] == [it.id]


def test_cleanup_keeps_starred_and_voted_items(db):
    t = _topic(db, "A", 1)
    old_noise = _item(db, "old noise", days_old=100)
    old_voted = _item(db, "old voted", days_old=100)
    old_starred = _item(db, "old starred", days_old=100, starred=True)
    fresh = _item(db, "fresh", days_old=2)
    for it in (old_noise, old_voted, old_starred, fresh):
        db.add(ItemScore(item_id=it.id, topic_id=t.id, final_score=0.5, user_vote=1 if it is old_voted else None))
    db.commit()
    noise_id = old_noise.id

    assert cleanup_old_items(db) == 1
    db.expire_all()
    remaining = {i.title for i in db.query(Item).all()}
    assert remaining == {"old voted", "old starred", "fresh"}
    assert db.query(ItemScore).filter(ItemScore.item_id == noise_id).count() == 0


def test_summary_candidate_query_matches_items_without_summaries(db):
    """The old filter used `Item.t1_tldr is None`, which never matched anything."""
    _item(db, "no summary")
    with_tldr = _item(db, "has tldr")
    with_tldr.t1_tldr = "tldr"
    db.commit()
    rows = db.query(Item).filter(Item.t1_tldr.is_(None), Item.t2_summary.is_(None)).all()
    assert [r.title for r in rows] == ["no summary"]


def test_settings_masks_keys_and_ignores_masked_round_trip(client, db):
    db.add(AppConfig(key="anthropic_api_key", value="sk-ant-secret-value-1234"))
    db.commit()
    masked = client.get("/settings/").json()["anthropic_api_key"]
    assert "secret" not in masked and masked.endswith("1234")

    client.post("/settings/", json={"anthropic_api_key": masked, "s2_api_key": "new-s2-key"})
    db.expire_all()
    assert db.get(AppConfig, "anthropic_api_key").value == "sk-ant-secret-value-1234"
    assert db.get(AppConfig, "s2_api_key").value == "new-s2-key"


def test_schema_upgrade_is_additive_and_idempotent(tmp_path):
    """Simulate a pre-upgrade database: tables without the new columns, rows present."""
    import sqlite3

    from sqlalchemy import create_engine, inspect

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE topics (id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL, name VARCHAR NOT NULL, description VARCHAR NOT NULL,
            keywords VARCHAR, embedding JSON, priority INTEGER, is_active BOOLEAN, created_at DATETIME);
        CREATE TABLE item_scores (item_id VARCHAR NOT NULL, topic_id VARCHAR NOT NULL, semantic_score FLOAT NOT NULL,
            llm_relevance_score FLOAT, follow_boost FLOAT NOT NULL, final_score FLOAT NOT NULL, user_vote INTEGER, reasons JSON NOT NULL,
            PRIMARY KEY (item_id, topic_id));
        INSERT INTO topics VALUES ('t1', '1', 'T', 'd', 'k', NULL, 1, 1, NULL);
        INSERT INTO item_scores VALUES ('i1', 't1', 0.5, NULL, 0, 0.7, 2, '["r"]');
        INSERT INTO item_scores VALUES ('i1', 'deleted-topic', 0.5, NULL, 0, 1.3, NULL, '["r"]');
        """
    )
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{path}")
    applied = upgrade(engine)
    assert set(applied) == {f"{t}.{c}" for t, c, _ in NEW_COLUMNS} | {"removed 1 orphaned item_scores"}
    assert upgrade(engine) == []  # second run is a no-op
    cols = {c["name"] for c in inspect(engine).get_columns("topics")}
    assert {"prior_vector", "seed_papers", "arxiv_categories", "exclude_keywords"} <= cols
    assert "topic_models" in inspect(engine).get_table_names()
    con = sqlite3.connect(path)
    assert con.execute("select user_vote, final_score from item_scores").fetchall() == [(2, 0.7)]


def test_rescore_topic_handles_more_than_one_chunk(db):
    """Regression: committing mid-iteration used to stop rescoring after 500 rows."""
    from src.ranking.model import RankerModel
    from src.ranking.training import rescore_topic

    topic = _topic(db, "A", 1)
    for i in range(1203):
        it = _item(db, f"p{i}", emb_seed=200 + i)
        db.add(ItemScore(item_id=it.id, topic_id=topic.id, semantic_score=0.5, final_score=0.5, reasons=["old"]))
    db.commit()

    n = rescore_topic(db, topic, RankerModel.prior_only(unit_vector(1), (0.0, 0.05)))
    assert n == 1203
    db.expire_all()
    assert db.query(ItemScore).filter(ItemScore.reasons == ["old"]).count() == 0
    assert db.query(ItemScore).filter(ItemScore.final_score > 1.0).count() == 0


def test_repair_votes_keeps_best_fitting_topic_only(client, db):
    t1, t2 = _topic(db, "A", 1), _topic(db, "B", 2)
    leaked = _item(db, "leaked")
    clean = _item(db, "clean")
    db.add(ItemScore(item_id=leaked.id, topic_id=t1.id, semantic_score=0.2, final_score=0.2, user_vote=2))
    db.add(ItemScore(item_id=leaked.id, topic_id=t2.id, semantic_score=0.8, final_score=0.8, user_vote=2))
    db.add(ItemScore(item_id=clean.id, topic_id=t1.id, semantic_score=0.5, final_score=0.5, user_vote=1))
    db.add(ItemScore(item_id=clean.id, topic_id=t2.id, semantic_score=0.5, final_score=0.5, user_vote=None))
    db.commit()

    assert client.get("/topics/vote_leaks").json() == {"items": 1, "rows": 2}
    r = client.post("/topics/repair_votes").json()
    assert r["items"] == 1 and r["cleared_rows"] == 1
    db.expire_all()
    votes = {(s.item_id, s.topic_id): s.user_vote for s in db.query(ItemScore).all()}
    assert votes[(leaked.id, t1.id)] is None and votes[(leaked.id, t2.id)] == 2
    assert votes[(clean.id, t1.id)] == 1
    assert client.get("/topics/vote_leaks").json() == {"items": 0, "rows": 0}


def test_deep_links_serve_the_app_but_api_404s_stay(client):
    """/settings is both an API prefix and a page route; browsers must get the page."""
    import os

    from src import main

    if not os.path.exists(main.frontend_dist):
        return  # frontend not built in this environment
    page = client.get("/settings", headers={"accept": "text/html,application/xhtml+xml"})
    assert page.status_code == 200 and "<div id=\"root\">" in page.text
    api = client.get("/items/nope/unknown", headers={"accept": "application/json"})
    assert api.status_code in (404, 405)
