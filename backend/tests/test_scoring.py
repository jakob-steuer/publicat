import numpy as np

from src.models.item_score import ItemScore
from src.models.topic import Topic
from src.ranking import scoring
from src.ranking.scoring import Follows, Paper, apply_llm_relevance, author_matches, calibrate, global_boost, keyword_boost, score_paper
from tests.conftest import unit_vector


def _topic(name="T", keywords=None, seed=1):
    return Topic(id=f"topic-{seed}", name=name, description="desc", keywords=keywords, embedding=unit_vector(seed))


def test_calibrate_maps_baseline_to_zero_and_clips():
    assert calibrate(scoring.RANDOM_BASELINE) == 0.0
    assert calibrate(0.5) == 0.0
    assert calibrate(0.99) == 1.0
    assert 0.0 < calibrate(0.80) < 1.0


def test_author_matches_by_s2_id_orcid_and_legacy_name():
    authors = [{"name": "Ada Lovelace", "authorId": "123", "orcid": "0000-0001-2345-6789"}]
    assert author_matches("AUTHOR_ID:123", authors)
    assert not author_matches("AUTHOR_ID:999", authors)
    assert author_matches("ORCID:0000-0001-2345-6789", authors)
    assert author_matches("ada lovelace", authors)
    # An ORCID follow must match the orcid field, never the name text.
    assert not author_matches("ORCID:0000-0001-2345-6789", [{"name": "ORCID:0000-0001-2345-6789 is not a name"}])


def test_global_boost_counts_follows_and_journals():
    paper = Paper("t", "a", unit_vector(5), [{"name": "Ada", "authorId": "1", "orcid": None}], "Nature")
    follows = Follows(authors=[("AUTHOR_ID:1", "Ada", 0.15)], venues={"nature": 0.05})
    boost, reasons = global_boost(paper, follows)
    assert abs(boost - (0.15 + 0.05 + 0.15)) < 1e-9
    assert len(reasons) == 3


def test_keyword_boost_title_beats_abstract():
    paper = Paper("Splicing isoforms in cancer", "we study alternative splicing", None, [], None)
    boost, reasons = keyword_boost(paper, "isoforms, alternative splicing, nothing")
    assert abs(boost - (0.15 + 0.10)) < 1e-9
    assert len(reasons) == 2


def test_score_paper_prefers_similar_topic_and_filters_noise():
    topic_vec = np.array(unit_vector(1))
    close = (topic_vec * 0.9 + np.array(unit_vector(2)) * 0.1).tolist()
    paper = Paper("t", "a", close, [], None)
    scores, max_final, boost = score_paper(paper, [_topic(seed=1), _topic(seed=3)], {}, Follows())
    assert boost == 0.0
    assert max_final > 0.5
    assert [s.topic_id for s in scores] == ["topic-1"]  # unrelated topic not stored


def test_pro_anti_vectors_adjust_score():
    paper = Paper("t", "a", unit_vector(7), [], None)
    topic = _topic(seed=7)  # identical vector -> calibrated 1.0 before adjustments
    base = score_paper(paper, [topic], {}, Follows())[0][0]
    penalised = score_paper(paper, [topic], {"topic-7": {"pro": None, "anti": unit_vector(7)}}, Follows())[0][0]
    assert penalised.final_score < base.final_score
    assert any("Anti-topic" in r for r in penalised.reasons)


def test_apply_llm_relevance_keeps_boosts_and_caps_at_one():
    s = ItemScore(item_id="i", topic_id="t", semantic_score=0.6, final_score=0.9, reasons=["x"])  # 0.3 of boosts
    apply_llm_relevance(s, 100, "great")
    assert abs(s.final_score - min(1.0, 0.6 * 1.5 + 0.3)) < 1e-9
    assert s.final_score <= 1.0
    apply_llm_relevance(s, 0, "bad")
    assert s.reasons[-1].startswith("LLM relevance: 0/100")
