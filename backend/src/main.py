import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api import dashboard, export, follows, inbox, items, rss, settings, topics
from src.database import SessionLocal, engine
from src.db_migrate import upgrade

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# Background jobs report through print(); keep that visible when stdout is a pipe (launcher, logs).
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

scheduler = AsyncIOScheduler()


async def scheduled_fetch():
    print("Running scheduled fetch...", flush=True)
    db = SessionLocal()
    try:
        if not await items.full_sync(db, name="scheduled fetch"):
            print("Scheduled fetch skipped: another job is running.", flush=True)
    finally:
        db.close()


async def bootstrap_models() -> None:
    """First start after the ranking upgrade: give every topic an S2-space vector and a trained model."""
    from src.models.topic import Topic
    from src.ranking.training import ensure_models

    db = SessionLocal()
    try:
        topics_needing_vector = [t.id for t in db.query(Topic).filter(Topic.is_active == True, Topic.prior_vector.is_(None)).all()]  # noqa: E712
        topics_needing_model = ensure_models(db)
    finally:
        db.close()
    for topic_id in dict.fromkeys(topics_needing_vector + topics_needing_model):
        # existing score rows only: fast, and it does not resurrect previously filtered noise
        await topics.prepare_topic(topic_id, rescore_all=False)


async def startup_tasks():
    await bootstrap_models()
    if os.environ.get("PUBLICAT_FETCH_ON_START", "1") not in ("0", "false", "False"):
        await scheduled_fetch()


@asynccontextmanager
async def lifespan(app: FastAPI):
    applied = upgrade(engine)
    if applied:
        print(f"Database schema upgraded: {applied}")
    scheduler.add_job(scheduled_fetch, trigger=IntervalTrigger(hours=24), id="scheduled_fetch_job", replace_existing=True)
    scheduler.start()
    # PUBLICAT_BOOTSTRAP=0 skips model bootstrap + launch sync (tests, smoke runs).
    if os.environ.get("PUBLICAT_BOOTSTRAP", "1") not in ("0", "false", "False"):
        asyncio.create_task(startup_tasks())
    yield
    scheduler.shutdown()


app = FastAPI(title="Publicat API", lifespan=lifespan)

# The built UI is served from this same origin, so CORS is only needed for the
# Vite dev server. Never "*": the API hands out sync controls and settings.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router)
app.include_router(topics.router)
app.include_router(settings.router)
app.include_router(follows.router, prefix="/follows", tags=["Follows"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(inbox.router, prefix="/inbox", tags=["Inbox"])
app.include_router(rss.router, prefix="/rss", tags=["RSS"])
app.include_router(export.router, prefix="/api/export", tags=["export"])

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str, request: Request):
        # Unknown API paths stay 404 for API clients; a browser asking for HTML
        # always gets the app, so deep links such as /settings work.
        api_prefixes = ("items/", "topics/", "settings/", "follows/", "dashboard/", "inbox/", "rss/", "api/")
        wants_html = "text/html" in request.headers.get("accept", "")
        if not wants_html and full_path.startswith(api_prefixes):
            raise HTTPException(status_code=404, detail="Not Found")

        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path) and full_path != "":
            return FileResponse(file_path)

        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"status": "ok", "message": "API is running, but frontend build not found."}
else:

    @app.get("/")
    def read_root():
        return {"status": "ok", "message": "Publicat API is running (frontend not built)"}
