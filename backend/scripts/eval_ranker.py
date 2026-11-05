"""Evaluate the ranker against the user's own votes (never writes votes or scores).

    uv run python scripts/eval_ranker.py [path/to/publikater.db] [--no-network]

For every topic: AUC of the stored final_score, of the description prior alone,
and 5-fold cross-validated AUC of the learned ranker for several
regularisation strengths. With network access it also builds the topic vector
in Semantic Scholar space (what production uses) and compares it with the
legacy locally embedded vector.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

db_path = next((a for a in sys.argv[1:] if not a.startswith("--")), str(ROOT / "publikater.db"))
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(db_path)}"

import numpy as np  # noqa: E402

from src.database import SessionLocal, engine  # noqa: E402
from src.db_migrate import upgrade  # noqa: E402
from src.models.item_score import ItemScore  # noqa: E402
from src.models.topic import Topic  # noqa: E402
from src.ranking.model import RankerModel, auc, cross_validated_auc  # noqa: E402
from src.ranking.paper import load_follows  # noqa: E402
from src.ranking.training import background_cos_stats, background_examples, labeled_examples, regularisation_for  # noqa: E402

LAMBDAS = [0.03, 0.1, 0.3, 1.0]
NETWORK = "--no-network" not in sys.argv


def main():
    # Additive schema upgrade only (new nullable columns); votes and items are never written.
    upgrade(engine)
    db = SessionLocal()
    follows = load_follows(db)
    topics = db.query(Topic).filter(Topic.is_active == True).all()  # noqa: E712

    s2_priors: dict[str, list[float] | None] = {}
    if NETWORK:
        from src.ranking.topic_vector import build_prior_vector

        async def build_all():
            for t in topics:
                vec, source = await build_prior_vector(t)
                s2_priors[t.id] = vec
                print(f"  S2-space prior for '{t.name}': {source}")

        print("Building Semantic Scholar-space topic vectors...")
        asyncio.run(build_all())

    for topic in topics:
        E, S, y, w = labeled_examples(db, topic, follows)
        background = background_examples(db, topic, follows, float(w.sum()))  # train-only pseudo-negatives, as in production
        stored = [
            s.final_score
            for s in db.query(ItemScore).filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None)).all()
        ]
        print(f"\n=== {topic.name}: {len(y)} votes (pos={int(y.sum())}, neg={int(len(y) - y.sum())})")
        print(f"  stored final_score (old heuristic)           AUC {auc(stored, [1 if v >= 1 else 0 for v in _votes(db, topic)]):.3f}")

        priors = {"legacy local vector": topic.embedding}
        if topic.id in s2_priors:
            priors["S2-space vector"] = s2_priors[topic.id]
        for name, prior in priors.items():
            if prior is None:
                print(f"  {name}: unavailable")
                continue
            stats = background_cos_stats(db, prior)
            prior_model = RankerModel.prior_only(prior, stats)
            cold = prior_model.logits(E, S)
            cos = E @ prior_model.prior_vector
            cold_p = prior_model.predict_proba(E, np.zeros_like(S))
            print(f"  [{name}] background cos mean {stats[0]:.3f} sd {stats[1]:.3f}; cold-start p: pos {cold_p[y == 1].mean():.2f} / neg {cold_p[y == 0].mean():.2f}")
            print(f"  [{name}] prior only (cold start)             AUC {auc(cold, y):.3f}   (cos pos {cos[y == 1].mean():.3f} / neg {cos[y == 0].mean():.3f})")
            for lam in LAMBDAS:
                cv = cross_validated_auc(lambda p=prior, st=stats: RankerModel.prior_only(p, st), E, S, y, w, lam, extra=background)
                print(f"  [{name}] learned, lambda={lam:<4}                 CV AUC {cv:.3f}")
        prod_prior = s2_priors.get(topic.id) or topic.embedding
        if prod_prior is not None:
            st = background_cos_stats(db, prod_prior)
            lam = regularisation_for(len(y))
            cv = cross_validated_auc(lambda p=prod_prior, st=st: RankerModel.prior_only(p, st), E, S, y, w, lam, extra=background)
            print(f"  PRODUCTION SETTING (lambda={lam:.3f}, with background negatives)   CV AUC {cv:.3f}")
        # Ablation: embedding only vs sparse only, S2 prior if available else legacy
        prior = s2_priors.get(topic.id) or topic.embedding
        if prior is not None:
            zero_S = np.zeros_like(S)
            st = background_cos_stats(db, prior)
            cv_emb = cross_validated_auc(lambda p=prior, st=st: RankerModel.prior_only(p, st), E, zero_S, y, w, 0.3)
            cv_sparse = cross_validated_auc(lambda: RankerModel.prior_only(None), np.zeros_like(E), S, y, w, 0.3)
            print(f"  ablation lambda=0.3: embedding only {cv_emb:.3f} | sparse features only {cv_sparse:.3f}")
    db.close()


def _votes(db, topic):
    return [s.user_vote for s in db.query(ItemScore).filter(ItemScore.topic_id == topic.id, ItemScore.user_vote.isnot(None)).all()]


if __name__ == "__main__":
    main()
