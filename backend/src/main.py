import asyncio
import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api import dashboard, export, follows, items, rss, settings, topics
from src.database import SessionLocal

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

scheduler = AsyncIOScheduler()


async def scheduled_fetch():
    print("Running scheduled fetch...")
    db = SessionLocal()
    try:
        await items.full_sync(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(scheduled_fetch, trigger=IntervalTrigger(hours=24), id="scheduled_fetch_job", replace_existing=True)
    scheduler.start()
    # PUBLICAT_FETCH_ON_START=0 skips the launch-time sync (tests, smoke runs).
    if os.environ.get("PUBLICAT_FETCH_ON_START", "1") not in ("0", "false", "False"):
        asyncio.create_task(scheduled_fetch())
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
app.include_router(rss.router, prefix="/rss", tags=["RSS"])
app.include_router(export.router, prefix="/api/export", tags=["export"])

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Let API 404s stay 404s instead of returning the React app
        api_prefixes = ["items", "topics", "settings", "follows", "dashboard", "rss", "api"]
        if any(full_path.startswith(prefix) for prefix in api_prefixes):
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
