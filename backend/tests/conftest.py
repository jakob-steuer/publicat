"""Test fixtures: an isolated SQLite database per test, never the user's publikater.db."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Must be set before `src.config` is imported anywhere.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["PUBLICAT_FETCH_ON_START"] = "0"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src import database  # noqa: E402
from src.models.base import Base  # noqa: E402
from src.models import item, item_score, topic, follow, app_config, rss, sync_run, topic_model  # noqa: E402,F401


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)

    # Point the app's session factory and dependency at this engine.
    database.engine = engine
    database.SessionLocal = TestingSession
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from src.main import app

    def override_get_db():
        yield db

    app.dependency_overrides[database.get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


EMB_DIM = 768


def unit_vector(seed: int) -> list[float]:
    """Deterministic pseudo-random unit vector."""
    import numpy as np

    rng = np.random.default_rng(seed)
    v = rng.normal(size=EMB_DIM)
    return (v / np.linalg.norm(v)).tolist()
