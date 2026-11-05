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


def test_wildcards_come_from_just_below_the_threshold(client, db):
    topic = _topic(db, "A", 1)
    above = _item(db, "above", days_old=2)
    near = [_item(db, f"near {i}", days_old=2) for i in range(6)]
    noise = _item(db, "noise", days_old=2)
    db.add(ItemScore(item_id=above.id, topic_id=topic.id, final_score=0.8, semantic_score=0.8))
    for it in near:
        db.add(ItemScore(item_id=it.id, topic_id=topic.id, final_score=0.4, semantic_score=0.4))
    db.add(ItemScore(item_id=noise.id, topic_id=topic.id, final_score=0.1, semantic_score=0.1))
    db.commit()

    plain = client.get("/inbox/", params={"min_score": 0.5}).json()
    assert [i["title"] for i in plain["items"]] == ["above"]
    r = client.get("/inbox/", params={"min_score": 0.5, "wildcards": 3}).json()
    wild = [i for i in r["items"] if i.get("wildcard")]
    assert r["total"] == 1 and len(wild) == 3 and all(i["title"].startswith("near") for i in wild)
    again = client.get("/inbox/", params={"min_score": 0.5, "wildcards": 3}).json()
    assert [i["id"] for i in again["items"]] == [i["id"] for i in r["items"]]  # stable within the day
    assert not any(i.get("wildcard") for i in client.get("/inbox/", params={"min_score": 0.5, "wildcards": 3, "q": "above"}).json()["items"])


def test_wildcards_in_all_topics_rotate_over_topics_and_respect_best_score(client, db):
    t1, t2, t3 = _topic(db, "A", 1), _topic(db, "B", 2), _topic(db, "C", 3)
    # many band papers for topic A (inserted first), a few for B and C
    for i in range(40):
        it = _item(db, f"a{i}", days_old=2)
        db.add(ItemScore(item_id=it.id, topic_id=t1.id, final_score=0.4, semantic_score=0.4))
    for name, topic in (("b", t2), ("c", t3)):
        for i in range(3):
            it = _item(db, f"{name}{i}", days_old=2)
            db.add(ItemScore(item_id=it.id, topic_id=topic.id, final_score=0.45, semantic_score=0.45))
    # in the band for A but a regular inbox paper for B: must NOT be a wildcard
    both = _item(db, "both", days_old=2)
    db.add(ItemScore(item_id=both.id, topic_id=t1.id, final_score=0.4, semantic_score=0.4))
    db.add(ItemScore(item_id=both.id, topic_id=t2.id, final_score=0.8, semantic_score=0.8))
    db.commit()

    r = client.get("/inbox/", params={"min_score": 0.5, "wildcards": 3}).json()
    wild = [i for i in r["items"] if i.get("wildcard")]
    assert sorted(i["topic_name"] for i in wild) == ["A", "B", "C"]  # one per topic, not three from A
    assert "both" not in [i["title"] for i in wild]
    assert all(i["score"] < 0.5 for i in wild)
    scoped = client.get("/inbox/", params={"min_score": 0.5, "wildcards": 3, "topic_id": t3.id}).json()
    assert [i["topic_name"] for i in scoped["items"] if i.get("wildcard")] == ["C", "C", "C"]


def test_topic_tags_add_and_remove_without_touching_item_state(client, db):
    t1, t2 = _topic(db, "A", 1), _topic(db, "B", 2)
    it = _item(db, "paper", days_old=2, starred=True)
    db.add(ItemScore(item_id=it.id, topic_id=t1.id, final_score=0.8, semantic_score=0.8, user_vote=2))
    db.commit()

    # add to topic B (no score row yet): becomes a starred example for B
    r = client.put(f"/items/{it.id}/topics/{t2.id}", json={"state": "in"}).json()
    votes = {v["topic_name"]: v["vote"] for v in r["topic_votes"]}
    assert votes == {"A": 2, "B": 2}
    # remove from topic A: downvote for A only, the paper stays starred and visible
    r = client.put(f"/items/{it.id}/topics/{t1.id}", json={"state": "out"}).json()
    assert {v["topic_name"]: v["vote"] for v in r["topic_votes"]} == {"A": -1, "B": 2}
    db.expire_all()
    item = db.get(Item, it.id)
    assert item.is_starred is True and item.is_hidden is False
    # clear the statement about A
    r = client.put(f"/items/{it.id}/topics/{t1.id}", json={"state": "none"}).json()
    assert {v["topic_name"]: v["vote"] for v in r["topic_votes"]} == {"A": None, "B": 2}

    starred = client.get("/items/starred").json()
    assert {v["topic_name"]: v["vote"] for v in starred[0]["topic_votes"]} == {"A": None, "B": 2}
    inbox = client.get("/inbox/", params={"filter": "starred"}).json()
    assert len(inbox["items"][0]["topic_votes"]) == 2


def test_biorxiv_harvest_reads_every_page(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    from src.sources import oai_pmh

    calls = []

    class FakeResp:
        status_code = 200
        headers = {}

        def __init__(self, cursor):
            self.cursor = cursor

        def json(self):
            n = 30 if self.cursor < 60 else 10
            return {"messages": [{"count": 30, "total": "70"}], "collection": [{"doi": f"10.1101/x{self.cursor + i}"} for i in range(n)]}

    async def fake_get(client, url, timeout, attempts=3):
        cursor = int(url.rsplit("/", 1)[1])
        calls.append(cursor)
        return FakeResp(cursor)

    monkeypatch.setattr(oai_pmh, "_get_with_retry", fake_get)
    dois = asyncio.run(oai_pmh.harvest_biorxiv_api(datetime(2026, 11, 1, tzinfo=timezone.utc)))
    assert calls == [0, 30, 60] and len(dois) == 70


def test_arxiv_harvest_follows_resumption_tokens(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    from src.sources import oai_pmh

    def page(ids, token):
        recs = "".join(f"<record><header><identifier>oai:arXiv.org:{i}</identifier></header></record>" for i in ids)
        tok = f"<resumptionToken>{token}</resumptionToken>" if token else "<resumptionToken/>"
        return f'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>{recs}{tok}</ListRecords></OAI-PMH>'

    class FakeResp:
        status_code = 200
        headers = {}

        def __init__(self, text):
            self.text = text

    urls = []

    async def fake_get(client, url, timeout, attempts=3):
        urls.append(url)
        return FakeResp(page(["2511.00001", "2511.00002"], "tok1") if "resumptionToken=" not in url else page(["2511.00003"], ""))

    monkeypatch.setattr(oai_pmh, "_get_with_retry", fake_get)
    ids = asyncio.run(oai_pmh.harvest_arxiv_oai(["q-bio"], datetime(2026, 11, 1, tzinfo=timezone.utc)))
    assert ids == ["ARXIV:2511.00001", "ARXIV:2511.00002", "ARXIV:2511.00003"]
    assert len(urls) == 2 and "resumptionToken=tok1" in urls[1]
