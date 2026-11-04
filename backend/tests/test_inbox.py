from datetime import datetime, timedelta, timezone

from src.integrations import zotero
from src.models.follow import Follow
from src.models.item import Item
from src.models.item_score import ItemScore
from src.models.topic import Topic
from tests.conftest import unit_vector


def _item(db, title, days_old=1, venue=None, authors=None, starred=False, acknowledged=False):
    authors = authors or [{"name": "Some One", "authorId": "42", "orcid": None}]
    it = Item(
        source="SemanticScholar",
        source_native_id=title,
        title=title,
        abstract=f"abstract about {title}",
        authors=[a["name"] for a in authors],
        author_details=authors,
        published_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        url="https://example.org",
        venue=venue,
        raw_metadata_json={},
        embedding=unit_vector(1),
        is_starred=starred,
        is_acknowledged=acknowledged,
    )
    db.add(it)
    db.flush()
    return it


def _topic(db, name, seed=1):
    t = Topic(name=name, description="d", prior_vector=unit_vector(seed))
    db.add(t)
    db.flush()
    return t


def test_inbox_ranks_filters_searches_and_counts(client, db):
    t1, t2 = _topic(db, "A", 1), _topic(db, "B", 2)
    hot = _item(db, "hot paper", days_old=2)
    warm = _item(db, "warm paper", days_old=20, venue="arXiv.org")
    old = _item(db, "old paper", days_old=100)
    read = _item(db, "read paper", days_old=3, acknowledged=True)
    low = _item(db, "low paper", days_old=3)
    by_author = _item(db, "author paper", days_old=4, authors=[{"name": "Ada L", "authorId": "7", "orcid": None}])
    for it, s1, s2 in [(hot, 0.95, 0.3), (warm, 0.7, 0.8), (old, 0.99, 0.1), (read, 0.9, 0.2), (low, 0.2, 0.1), (by_author, 0.6, 0.65)]:
        db.add(ItemScore(item_id=it.id, topic_id=t1.id, final_score=s1, semantic_score=s1, reasons=["r1"]))
        db.add(ItemScore(item_id=it.id, topic_id=t2.id, final_score=s2, semantic_score=s2, reasons=["r2"]))
    db.add(Follow(entity_type="author", entity_value="AUTHOR_ID:7", display_name="Ada L"))
    db.commit()

    r = client.get("/inbox/", params={"min_score": 0.5}).json()
    titles = [i["title"] for i in r["items"]]
    assert titles == ["hot paper", "warm paper", "author paper"]  # old (too old), read (acknowledged), low (score) excluded
    assert r["total"] == 3
    assert r["items"][0]["topic_name"] == "A" and r["items"][1]["topic_name"] == "B"  # best topic per item
    assert r["items"][1]["reasons"] == ["r2"]

    assert [i["title"] for i in client.get("/inbox/", params={"filter": "top"}).json()["items"]] == ["hot paper"]
    assert [i["title"] for i in client.get("/inbox/", params={"filter": "week"}).json()["items"]] == ["hot paper", "author paper"]
    assert [i["title"] for i in client.get("/inbox/", params={"show_preprints": "false"}).json()["items"]] == ["hot paper", "author paper"]
    assert [i["title"] for i in client.get("/inbox/", params={"filter": "authors"}).json()["items"]] == ["author paper"]
    assert [i["title"] for i in client.get("/inbox/", params={"q": "warm"}).json()["items"]] == ["warm paper"]
    assert [i["title"] for i in client.get("/inbox/", params={"sort": "date"}).json()["items"]] == ["hot paper", "author paper", "warm paper"]
    assert [i["title"] for i in client.get("/inbox/", params={"show_acknowledged": "true", "days": 0}).json()["items"]][:2] == ["old paper", "hot paper"]

    page = client.get("/inbox/", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and [i["title"] for i in page["items"]] == ["author paper"]

    scoped = client.get("/inbox/", params={"topic_id": t2.id, "min_score": 0.5}).json()
    assert [i["title"] for i in scoped["items"]] == ["warm paper", "author paper"]
    assert all(i["topic_id"] == t2.id for i in scoped["items"])

    counts = client.get("/inbox/counts", params={"min_score": 0.5}).json()
    assert counts == {"all": 3, "topics": {t1.id: 3, t2.id: 2}}


def test_zotero_item_builder_and_unavailable(client, db, monkeypatch):
    it = _item(db, "A great paper", venue="Nature", authors=[{"name": "Ada Lovelace", "authorId": "1", "orcid": None}])
    it.doi = "10.1000/xyz"
    it.t1_tldr = "It is great."
    it.open_access_pdf_url = "https://example.org/p.pdf"
    db.commit()

    z = zotero.build_zotero_item(it)
    assert z["itemType"] == "journalArticle" and z["publicationTitle"] == "Nature" and z["DOI"] == "10.1000/xyz"
    assert z["creators"] == [{"firstName": "Ada", "lastName": "Lovelace", "creatorType": "author"}]
    assert "It is great." in z["notes"][0]["note"]
    assert z["attachments"][0]["mimeType"] == "application/pdf"

    monkeypatch.setattr(zotero, "CONNECTOR", "http://127.0.0.1:1")  # nothing listens here
    r = client.post("/api/export/zotero/push", json={"item_ids": [it.id]})
    assert r.status_code == 503 and "Zotero" in r.json()["detail"]
    assert client.get("/api/export/zotero/status").json() == {"running": False}


def test_orcid_year_only_dates_count_as_recent():
    from datetime import datetime

    from src.sources.orcid import _work_date

    assert _work_date({"publication-date": {"year": {"value": "2026"}}})[0] == datetime(2026, 12, 31)
    assert _work_date({"publication-date": {"year": {"value": "2026"}, "month": {"value": "3"}}})[0] == datetime(2026, 3, 1)
    assert _work_date({"publication-date": {"year": {"value": "2026"}, "month": {"value": "2"}, "day": {"value": "30"}}})[0] == datetime(2026, 12, 31)
    assert _work_date({})[0] is None


def test_preprint_venue_recovered_from_ids():
    from src.api.items import preprint_venue

    assert preprint_venue({"ArXiv": "2511.01234"}) == "arXiv.org"
    assert preprint_venue({"DOI": "10.1101/2026.11.01.123456"}) == "bioRxiv"
    assert preprint_venue({"DOI": "10.1101/2026.11.01.123456medrxiv"}) == "medRxiv"
    assert preprint_venue({"DOI": "10.1038/s41586-026-00001-1"}) is None
