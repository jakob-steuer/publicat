"""Idempotent, additive schema upgrades for existing SQLite databases.

The shipped databases were created with `create_all` and never stamped by
Alembic, so `alembic upgrade head` cannot be applied to them. New tables are
created by `create_all`; new columns on existing tables are added here with
`ALTER TABLE ... ADD COLUMN`, which SQLite supports and which never touches
existing rows. Safe to run on every start.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# (table, column, SQL type) -- all nullable so existing rows are untouched.
NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("topics", "exclude_keywords", "VARCHAR"),
    ("topics", "prior_vector", "JSON"),
    ("topics", "seed_papers", "JSON"),
    ("topics", "arxiv_categories", "JSON"),
    ("item_scores", "voted_at", "DATETIME"),
    ("items", "discovered_via", "JSON"),
]


def upgrade(engine: Engine) -> list[str]:
    """Create missing tables and columns. Returns a list of applied changes."""
    from src.models import app_config, follow, item, item_score, rss, sync_run, topic, topic_model  # noqa: F401
    from src.models.base import Base

    applied: list[str] = []
    Base.metadata.create_all(bind=engine)

    insp = inspect(engine)
    existing = {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}
    with engine.begin() as conn:
        for table, column, sql_type in NEW_COLUMNS:
            if table in existing and column not in existing[table]:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
                applied.append(f"{table}.{column}")
        # Scores of topics deleted before foreign keys were enforced: they are
        # invisible in the UI but still win the "best score" aggregation.
        if "item_scores" in existing and "topics" in existing:
            orphans = conn.execute(text("SELECT count(*) FROM item_scores WHERE topic_id NOT IN (SELECT id FROM topics)")).scalar() or 0
            if orphans:
                conn.execute(text("DELETE FROM item_scores WHERE topic_id NOT IN (SELECT id FROM topics)"))
                applied.append(f"removed {orphans} orphaned item_scores")
    return applied
