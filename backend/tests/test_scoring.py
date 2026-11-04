import numpy as np

from src.models.topic import Topic
from src.ranking import features
from src.ranking.model import RankerModel, auc, cross_validated_auc
from src.ranking.paper import Follows, Paper, author_matches
from src.ranking.scoring import score_against_topic, score_paper
from tests.conftest import unit_vector


def _topic(name="T", keywords=None, seed=1, exclude=None):
    return Topic(id=f"topic-{seed}", name=name, description="desc", keywords=keywords, exclude_keywords=exclude, prior_vector=unit_vector(seed))


def _paper(seed, title="t", abstract="a", authors=None, venue=None):
    return Paper(title, abstract, unit_vector(seed), authors or [], venue)


def _near(seed, other, weight=0.9):
    v = np.array(unit_vector(seed)) * weight + np.array(unit_vector(other)) * (1 - weight)
    return (v / np.linalg.norm(v)).tolist()


def _orthogonal(seed, to):
    """Unit vector from `seed` made exactly orthogonal to `to`."""
    t = np.array(to)
    u = np.array(unit_vector(seed))
    u = u - (u @ t) * t
    return (u / np.linalg.norm(u)).tolist()


def _with_cosine(t, cos, seed=9):
    """Unit vector whose cosine to unit vector t is exactly `cos`."""
    t = np.array(t)
    u = np.array(_orthogonal(seed, t))
    return (cos * t + np.sqrt(1 - cos**2) * u).tolist()


def test_author_matches_by_s2_id_orcid_and_legacy_name():
    authors = [{"name": "Ada Lovelace", "authorId": "123", "orcid": "0000-0001-2345-6789"}]
    assert author_matches("AUTHOR_ID:123", authors)
    assert not author_matches("AUTHOR_ID:999", authors)
    assert author_matches("ORCID:0000-0001-2345-6789", authors)
    assert author_matches("ada lovelace", authors)
    assert not author_matches("ORCID:0000-0001-2345-6789", [{"name": "ORCID:0000-0001-2345-6789 is not a name"}])


def test_feature_extraction():
    paper = Paper("Splicing isoforms in cancer", "we study alternative splicing", unit_vector(5), [{"name": "Ada", "authorId": "1", "orcid": None}], "Nature")
    follows = Follows(authors=[("AUTHOR_ID:1", "Ada", 0.15)])
    row = features.extract(paper, "isoforms, alternative splicing, nothing", follows, llm_score=80)
    named = dict(zip(features.SPARSE_FEATURES, row.sparse))
    assert named["kw_title"] == 1 and named["kw_abstract"] == 1
    assert named["followed_author"] == 1 and named["journal_tier"] == 0.15
    assert abs(named["llm_score"] - 0.3) < 1e-9 and named["has_llm"] == 1
    assert row.details["authors"] == ["Ada"] and row.details["journal"] == "Nature"
    assert row.embedding is not None and abs(np.linalg.norm(row.embedding) - 1) < 1e-9


def test_prior_only_is_calibrated_against_background():
    model = RankerModel.prior_only(unit_vector(1), cos_stats=(0.80, 0.02))
    typical = features.FeatureRow(embedding=None, sparse=np.zeros(len(features.SPARSE_FEATURES)))
    # A paper 2 sd above the background mean sits at p=0.5; a typical paper well below.
    e_mid = np.array(_with_cosine(unit_vector(1), 0.84))
    e_typ = np.array(_with_cosine(unit_vector(1), 0.80))
    assert abs(model.prior_proba(e_mid) - 0.5) < 0.02
    assert model.prior_proba(e_typ) < 0.15
    assert not model.is_trained
    assert typical is not None


def test_score_paper_prefers_similar_topic_and_filters_noise():
    paper = Paper("t", "a", _near(1, 2), [], None)
    unrelated = _orthogonal(3, paper.embedding)  # cosine exactly 0 = a typical background paper
    t_unrelated = _topic(seed=3)
    t_unrelated.prior_vector = unrelated
    models = {"topic-1": RankerModel.prior_only(unit_vector(1), (0.0, 0.1)), "topic-3": RankerModel.prior_only(unrelated, (0.0, 0.1))}
    scores = score_paper(paper, [_topic(seed=1), t_unrelated], models, Follows())
    # the unrelated topic (cosine ~0 = background mean) falls under the storage threshold
    assert [s.topic_id for s in scores] == ["topic-1"]
    assert scores[0].final_score > 0.9
    assert scores[0].reasons[0].startswith("Relevance")


def test_exclude_keywords_are_a_hard_filter():
    topic = _topic(seed=1, exclude="mouse model")
    model = RankerModel.prior_only(unit_vector(1), (0.0, 0.1))
    ts = score_against_topic(Paper("A mouse model of X", "a", unit_vector(1), [], None), topic, model, Follows())
    assert ts.excluded and not ts.keep and ts.final_score == 0.0


def test_fit_learns_from_votes_and_explains():
    rng = np.random.default_rng(0)
    topic_vec = np.array(unit_vector(1))
    liked = np.array(unit_vector(20))
    E, y = [], []
    for i in range(80):
        base = liked if i % 2 == 0 else np.array(unit_vector(21))
        e = 0.7 * base + 0.3 * rng.normal(size=features.EMBEDDING_DIM) / np.sqrt(features.EMBEDDING_DIM)
        E.append(e / np.linalg.norm(e))
        y.append(1 if i % 2 == 0 else 0)
    E, y = np.array(E), np.array(y)
    S = np.zeros((len(y), len(features.SPARSE_FEATURES)))
    prior = RankerModel.prior_only(topic_vec, (0.0, 0.1))
    before = auc(prior.logits(E, S), y)
    cv = cross_validated_auc(lambda: RankerModel.prior_only(topic_vec, (0.0, 0.1)), E, S, y, np.ones(len(y)), lam=0.3)
    model = RankerModel.prior_only(topic_vec, (0.0, 0.1)).fit(E, S, y, lam=0.3)
    after = auc(model.logits(E, S), y)
    assert cv > 0.9 and after > before
    assert model.is_trained and model.n_pos == 40 and model.n_neg == 40

    row = features.extract(Paper("t", "a", E[0].tolist(), [], None), None, Follows())
    p, prior_p, reasons = model.score_row(row)
    assert p > prior_p
    assert any("upvoted" in r for r in reasons)

    restored = RankerModel.from_dict(model.to_dict())
    assert np.allclose(restored.logits(E, S), model.logits(E, S))


def test_fit_with_sparse_signal_adjusts_default_weight():
    """A user who always downvotes preprints should see the preprint weight go negative."""
    E = np.zeros((60, features.EMBEDDING_DIM))
    S = np.zeros((60, len(features.SPARSE_FEATURES)))
    idx = features.SPARSE_FEATURES.index("is_preprint")
    S[:30, idx] = 1.0
    y = np.array([0] * 30 + [1] * 30)
    model = RankerModel.prior_only(None).fit(E, S, y, lam=0.3)
    assert model.sparse_weights[idx] < -1.0
