"""Per-topic logistic-regression ranker with a prior.

logit(paper) = bias + w_emb . e + w_sparse . s

where e is the unit SPECTER2 embedding and s the sparse features. Weights are
fitted on the user's votes but regularised towards a prior:

    w_emb_0    = PRIOR_EMB_SCALE * topic_vector
    bias_0     = -PRIOR_EMB_SCALE * PRIOR_COS_CENTER
    w_sparse_0 = PRIOR_SPARSE_WEIGHTS

so with zero votes the model is "cosine to the topic + sensible boosts", and
with hundreds of votes it is a personalised linear classifier in embedding
space. The split w_emb = w_emb_0 + v lets explanations separate "matches the
topic description" from "learned from your votes".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.ranking.features import EMBEDDING_DIM, PRIOR_SPARSE_WEIGHTS, SPARSE_FEATURES, FeatureRow

DEFAULT_LAMBDA = 0.1
MODEL_VERSION = 2

# Cold-start calibration: a paper whose cosine to the topic vector is this many
# standard deviations above the background mean gets probability 0.5.
PRIOR_Z_CENTER = 2.0
# Background cosine statistics when the database is still too small to measure them.
FALLBACK_COS_STATS = (0.80, 0.03)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


@dataclass
class RankerModel:
    prior_vector: np.ndarray | None  # unit topic vector in SPECTER2 space (None: no embedding prior)
    emb_weights: np.ndarray  # learned deviation v (768,)
    sparse_weights: np.ndarray  # (len(SPARSE_FEATURES),)
    bias: float
    cos_mu: float = FALLBACK_COS_STATS[0]  # background mean cosine of papers to the topic vector
    cos_sigma: float = FALLBACK_COS_STATS[1]
    n_pos: int = 0
    n_neg: int = 0
    cv_auc: float | None = None
    trained_at: str | None = None
    lam: float = DEFAULT_LAMBDA
    version: int = MODEL_VERSION
    meta: dict[str, Any] = field(default_factory=dict)

    # ----------------------------------------------------------------- prior
    @classmethod
    def prior_only(cls, prior_vector, cos_stats: tuple[float, float] | None = None) -> "RankerModel":
        """Model before any vote: z-scored cosine to the topic vector plus default sparse weights.

        cos_stats = (mean, std) of the cosine between background papers and the
        topic vector; measured from the database when possible so the prior is
        calibrated regardless of which embedding region the topic sits in.
        """
        pv = None
        if prior_vector is not None:
            pv = np.asarray(prior_vector, dtype=float)
            n = np.linalg.norm(pv)
            pv = pv / n if (pv.shape == (EMBEDDING_DIM,) and n > 0) else None
        mu, sigma = cos_stats or FALLBACK_COS_STATS
        sigma = max(float(sigma), 1e-3)
        m = cls(
            prior_vector=pv,
            emb_weights=np.zeros(EMBEDDING_DIM),
            sparse_weights=PRIOR_SPARSE_WEIGHTS.copy(),
            bias=0.0,
            cos_mu=float(mu),
            cos_sigma=sigma,
        )
        m.bias = m.prior_bias
        return m

    @property
    def prior_scale(self) -> float:
        return 1.0 / self.cos_sigma

    @property
    def prior_emb_weights(self) -> np.ndarray:
        return self.prior_scale * self.prior_vector if self.prior_vector is not None else np.zeros(EMBEDDING_DIM)

    @property
    def prior_bias(self) -> float:
        # logit = (cos - mu)/sigma - PRIOR_Z_CENTER
        return -(self.cos_mu / self.cos_sigma + PRIOR_Z_CENTER) if self.prior_vector is not None else 0.0

    @property
    def is_trained(self) -> bool:
        return self.trained_at is not None

    # ------------------------------------------------------------- inference
    def logits(self, E: np.ndarray, S: np.ndarray) -> np.ndarray:
        """E: (n, 768) unit embeddings (rows may be zero when missing); S: (n, k)."""
        w_emb = self.prior_emb_weights + self.emb_weights
        return self.bias + E @ w_emb + S @ self.sparse_weights

    def predict_proba(self, E: np.ndarray, S: np.ndarray) -> np.ndarray:
        return sigmoid(self.logits(E, S))

    def prior_proba(self, e: np.ndarray | None) -> float:
        """Probability from the topic description alone (no sparse features, no learning)."""
        if e is None or self.prior_vector is None:
            return 0.0
        return float(sigmoid(self.prior_bias + float(e @ self.prior_emb_weights)))

    def score_row(self, row: FeatureRow) -> tuple[float, float, list[str]]:
        """Returns (final probability, prior probability, human-readable reasons)."""
        e = row.embedding if row.embedding is not None else np.zeros(EMBEDDING_DIM)
        p = float(self.predict_proba(e[None, :], row.sparse[None, :])[0])
        prior_p = self.prior_proba(row.embedding)
        return p, prior_p, self.explain(row, p)

    def explain(self, row: FeatureRow, p: float) -> list[str]:
        e = row.embedding
        d = row.details
        parts: list[tuple[float, str]] = []
        if e is not None and self.prior_vector is not None:
            cos = float(e @ self.prior_vector)
            z = (cos - self.cos_mu) / self.cos_sigma
            parts.append((self.prior_bias + self.prior_scale * cos, f"Topic similarity: {z:+.1f} sd vs. a typical paper (cos {cos:.2f})"))
            if self.is_trained:
                learned = float(e @ self.emb_weights)
                if abs(learned) >= 0.05:
                    parts.append((learned, "Resembles papers you upvoted" if learned > 0 else "Resembles papers you skipped or downvoted"))
        contrib = row.sparse * self.sparse_weights
        names = dict(zip(SPARSE_FEATURES, contrib))
        if d.get("title_hits"):
            parts.append((names["kw_title"], "Keyword in title: " + ", ".join(f"'{k}'" for k in d["title_hits"])))
        if d.get("abstract_hits"):
            parts.append((names["kw_abstract"], "Keyword in abstract: " + ", ".join(f"'{k}'" for k in d["abstract_hits"])))
        if d.get("authors"):
            parts.append((names["followed_author"], "Followed author: " + ", ".join(d["authors"])))
        if d.get("journal"):
            parts.append((names["journal_tier"], f"High-impact journal: {d['journal']}"))
        if d.get("preprint") and abs(names["is_preprint"]) >= 0.05:
            parts.append((names["is_preprint"], "Preprint"))
        if d.get("llm_score") is not None:
            parts.append((names["llm_score"] + names["has_llm"], f"LLM judge: {int(d['llm_score'])}/100"))
        reasons = [f"Relevance {p * 100:.0f}%" + ("" if self.is_trained else " (no votes yet, description only)")]
        reasons += [f"{text} ({val:+.1f})" for val, text in sorted(parts, key=lambda t: -abs(t[0]))]
        return reasons

    # -------------------------------------------------------------- training
    def fit(self, E: np.ndarray, S: np.ndarray, y: np.ndarray, w: np.ndarray | None = None, lam: float | None = None) -> "RankerModel":
        """Weighted L2-regularised logistic regression, regularised towards the prior.

        y in {0, 1}; w sample weights. Returns self (fitted in place).
        """
        from scipy.optimize import minimize

        lam = DEFAULT_LAMBDA if lam is None else lam
        n = len(y)
        if n == 0:
            return self
        w = np.ones(n) if w is None else np.asarray(w, dtype=float)
        yy = np.where(np.asarray(y) > 0, 1.0, -1.0)
        k = S.shape[1]
        theta0 = np.concatenate([np.zeros(EMBEDDING_DIM), PRIOR_SPARSE_WEIGHTS, [self.prior_bias]])
        # penalty scale per coordinate: full on weights, light on bias
        pen = np.concatenate([np.full(EMBEDDING_DIM, lam), np.full(k, lam), [0.1 * lam]])
        base_logit = E @ self.prior_emb_weights  # fixed prior offset

        def unpack(theta):
            return theta[:EMBEDDING_DIM], theta[EMBEDDING_DIM : EMBEDDING_DIM + k], theta[-1]

        def objective(theta):
            v, ws, b = unpack(theta)
            z = base_logit + E @ v + S @ ws + b
            m = yy * z
            loss = np.sum(w * np.logaddexp(0.0, -m))
            diff = theta - theta0
            loss += 0.5 * np.sum(pen * diff * diff)
            g = -w * yy * sigmoid(-m)  # d loss / d z
            grad = np.concatenate([E.T @ g, S.T @ g, [g.sum()]]) + pen * diff
            return loss, grad

        start = np.concatenate([self.emb_weights, self.sparse_weights, [self.bias]])
        res = minimize(objective, start, jac=True, method="L-BFGS-B", options={"maxiter": 500})
        v, ws, b = unpack(res.x)
        self.emb_weights = v
        self.sparse_weights = ws
        self.bias = float(b)
        self.lam = lam
        self.n_pos = int(np.sum(yy > 0))
        self.n_neg = int(np.sum(yy < 0))
        self.trained_at = datetime.now(timezone.utc).isoformat()
        return self

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "prior_vector": self.prior_vector.tolist() if self.prior_vector is not None else None,
            "emb_weights": self.emb_weights.tolist(),
            "sparse_weights": self.sparse_weights.tolist(),
            "sparse_features": SPARSE_FEATURES,
            "bias": self.bias,
            "cos_mu": self.cos_mu,
            "cos_sigma": self.cos_sigma,
            "n_pos": self.n_pos,
            "n_neg": self.n_neg,
            "cv_auc": self.cv_auc,
            "trained_at": self.trained_at,
            "lam": self.lam,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RankerModel":
        pv = np.asarray(d["prior_vector"], dtype=float) if d.get("prior_vector") is not None else None
        sw = np.asarray(d["sparse_weights"], dtype=float)
        if len(sw) != len(SPARSE_FEATURES):  # feature set changed: fall back to prior sparse weights
            sw = PRIOR_SPARSE_WEIGHTS.copy()
        return cls(
            prior_vector=pv,
            emb_weights=np.asarray(d["emb_weights"], dtype=float),
            sparse_weights=sw,
            bias=float(d["bias"]),
            cos_mu=float(d.get("cos_mu", FALLBACK_COS_STATS[0])),
            cos_sigma=float(d.get("cos_sigma", FALLBACK_COS_STATS[1])),
            n_pos=int(d.get("n_pos", 0)),
            n_neg=int(d.get("n_neg", 0)),
            cv_auc=d.get("cv_auc"),
            trained_at=d.get("trained_at"),
            lam=float(d.get("lam", DEFAULT_LAMBDA)),
            version=int(d.get("version", MODEL_VERSION)),
            meta=d.get("meta") or {},
        )


def auc(scores, labels) -> float:
    scores = np.asarray(scores, float)
    labels = np.asarray(labels, int)
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def cross_validated_auc(model_factory, E, S, y, w, lam, folds=5, seed=0) -> float | None:
    """AUC of a model trained on 4/5 of the votes and scored on the rest, averaged over folds."""
    y = np.asarray(y)
    if len(y) < 20 or y.sum() < 5 or (len(y) - y.sum()) < 5:
        return None
    rng = np.random.default_rng(seed)
    idx = np.arange(len(y))
    rng.shuffle(idx)
    parts = np.array_split(idx, folds)
    preds = np.zeros(len(y))
    for k in range(folds):
        test = parts[k]
        train = np.concatenate([parts[j] for j in range(folds) if j != k])
        m = model_factory().fit(E[train], S[train], y[train], w[train], lam=lam)
        preds[test] = m.logits(E[test], S[test])
    return auc(preds, y)
