import asyncio

from src.integrations import zotero_library as zl


def test_identifier_extraction():
    assert zl.identifier_for({"DOI": "10.1038/s41586-021-03819-2"}) == "DOI:10.1038/s41586-021-03819-2"
    assert zl.identifier_for({"url": "https://doi.org/10.1101/2024.01.01.123456"}) == "DOI:10.1101/2024.01.01.123456"
    assert zl.identifier_for({"url": "https://arxiv.org/abs/2106.04554"}) == "ARXIV:2106.04554"
    assert zl.identifier_for({"extra": "arXiv: 2106.04554 [cs]"}) == "ARXIV:2106.04554"
    assert zl.identifier_for({"extra": "PMID: 34265844"}) == "PMID:34265844"
    assert zl.identifier_for({"title": "A book chapter"}) is None


def test_suggest_keywords_prefers_repeated_phrases():
    titles = [
        "Alternative splicing in breast cancer",
        "Alternative splicing regulates isoform switching in cancer",
        "Isoform switching and alternative splicing in tumours",
        "Long-read sequencing of isoform diversity",
    ]
    kws = zl.suggest_keywords(titles)
    assert kws[0] == "alternative splicing"
    assert "isoform" in " ".join(kws)


def test_collection_paths_and_items(monkeypatch):
    collections = [
        {"key": "A", "data": {"name": "Splicing", "parentCollection": False}, "meta": {"numItems": 2}},
        {"key": "B", "data": {"name": "Cancer", "parentCollection": "A"}, "meta": {"numItems": 1}},
    ]
    items = [
        {"key": "i1", "data": {"itemType": "journalArticle", "title": "Paper one", "DOI": "10.1/x", "date": "2024-05-01"}},
        {"key": "i2", "data": {"itemType": "note", "title": "a note"}},
        {"key": "i3", "data": {"itemType": "preprint", "title": "Paper two", "url": "https://arxiv.org/abs/2401.00001"}},
    ]

    async def fake_get_all(access, path, params=None, limit=None):
        return collections if path == "/collections" else items

    monkeypatch.setattr(zl, "_get_all", fake_get_all)
    access = zl.ZoteroAccess("local")
    cols = asyncio.run(zl.list_collections(access))
    assert [c["path"] for c in cols] == ["Splicing", "Splicing / Cancer"] and cols[1]["parent"] == "A"
    got = asyncio.run(zl.collection_items(access, "A"))
    assert [(g["title"], g["identifier"]) for g in got] == [("Paper one", "DOI:10.1/x"), ("Paper two", "ARXIV:2401.00001")]


def test_preview_endpoint_builds_a_topic_draft(client, monkeypatch):
    from src.api import zotero_import as zi

    async def reachable(access):
        return {"reachable": True, "mode": access.mode, "message": None}

    async def fake_items(access, key):
        return [
            {"key": "1", "title": "Alternative splicing in cancer", "identifier": "DOI:10.1/a", "year": "2024"},
            {"key": "2", "title": "Alternative splicing atlas", "identifier": "DOI:10.1/b", "year": "2023"},
            {"key": "3", "title": "A thesis without identifiers", "identifier": None, "year": "2020"},
        ]

    async def fake_lookup(ids, fields="paperId,title,year"):
        return [{"paperId": "p1", "title": "Alternative splicing in cancer"}, None]

    monkeypatch.setattr(zi.zl, "status", reachable)
    monkeypatch.setattr(zi.zl, "collection_items", fake_items)
    monkeypatch.setattr(zi, "lookup_papers_s2", fake_lookup)
    r = client.post("/zotero/preview", json={"collection_key": "A", "collection_name": "Research / Splicing"}).json()
    assert r["name"] == "Splicing" and r["matched"] == 1 and r["total_items"] == 3 and r["unresolved_count"] == 2
    assert r["seed_papers"] == [{"paperId": "p1", "title": "Alternative splicing in cancer"}]
    assert "alternative splicing" in r["suggested_keywords"]


def test_local_api_disabled_gives_actionable_message(client, monkeypatch):
    from src.api import zotero_import as zi

    async def refused(access):
        return {"reachable": False, "mode": access.mode, "message": "Zotero refused: enable Settings -> Advanced"}

    monkeypatch.setattr(zi.zl, "status", refused)
    r = client.get("/zotero/collections")
    assert r.status_code == 503 and "Advanced" in r.json()["detail"]
