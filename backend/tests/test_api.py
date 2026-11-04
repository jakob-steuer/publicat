"""Regression tests for the features that were silently broken."""
from datetime import datetime, timedelta, timezone

from src.api.items import cleanup_old_items
from src.models.app_config import AppConfig
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from tests.conftest import unit_vector


def _item(db, title, days_old=1, starred=False, authors=None, emb_seed=11):
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
        embedding=unit_vector(emb_seed),
        is_starred=starred,
    )
    db.add(it)
    db.flush()
    return it


def _topic(db, name, seed):
    t = Topic(name=name, description="d", embedding=unit_vector(seed))
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
    votes = {s.topic_id: s.user_vote for s in db.query(ItemScore).all()}
    assert votes == {t1.id: None, t2.id: 1}

    # Explicit topic wins over best score.
    client.post(f"/items/{it.id}/vote", json={"topic_id": t1.id, "vote": -1})
    votes = {s.topic_id: s.user_vote for s in db.query(ItemScore).all()}
    assert votes == {t1.id: -1, t2.id: 1}
    assert db.get(Item, it.id).is_hidden is True

    # Un-rating clears everywhere.
    client.post(f"/items/{it.id}/vote", json={"topic_id": None, "vote": None})
    assert all(s.user_vote is None for s in db.query(ItemScore).all())


def test_dashboard_marks_best_topic_and_finds_followed_authors(client, db):
    t1, t2 = _topic(db, "A", 1), _topic(db, "B", 2)
    it = _item(db, "paper")
    db.add(ItemScore(item_id=it.id, topic_id=t1.id, semantic_score=0.4, final_score=0.4))
    db.add(ItemScore(item_id=it.id, topic_id=t2.id, semantic_score=0.9, final_score=0.95))
    db.add(Follow(entity_type="author", entity_value="ORCID:0000-0002-0000-0001", display_name="Some One"))
    db.commit()

    dash = client.get("/dashboard/").json()
    card = dash["this_week"][0]
    assert card["topic_id"] == t2.id and card["topic_name"] == "B"
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
    assert db.get(AppConfig, "anthropic_api_key").value == "sk-ant-secret-value-1234"
    assert db.get(AppConfig, "s2_api_key").value == "new-s2-key"
