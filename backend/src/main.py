import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.database import SessionLocal
from src.api import items, topics, settings, follows, dashboard, rss, export

scheduler = AsyncIOScheduler()

async def scheduled_fetch():
    print("Running scheduled fetch...")
    db = SessionLocal()
    try:
        await items.run_ingestion(db)
        from src.llm.pipeline import run_summarization_pipeline
        items.sync_state["message"] = "Running scheduled LLM summaries..."
        items.sync_state["progress"] = 90
        await run_summarization_pipeline(db)
    finally:
        items.sync_state["status"] = "idle"
        items.sync_state["message"] = "Sync Complete!"
        items.sync_state["progress"] = 100
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.add_job(
        scheduled_fetch,
        trigger=IntervalTrigger(hours=24),
        id="scheduled_fetch_job",
        replace_existing=True
    )
    scheduler.start()
    
    # Run fetch at launch
    asyncio.create_task(scheduled_fetch())
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(title="Publikater API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
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
            
        # Fallback to index.html for SPA routing
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"status": "ok", "message": "API is running, but frontend build not found."}
else:
    @app.get("/")
    def read_root():
        return {"status": "ok", "message": "Publikater API is running (Frontend not built)"}
