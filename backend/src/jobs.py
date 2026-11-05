"""One background job at a time.

Manual fetch, the 24 h scheduled fetch and the fetch that follows a new topic
all used to start independently and race on the same tables and the same
progress dict. Everything now goes through `run_exclusive`: a second request
while a job is active is refused (callers tell the user), and the progress
state carries the job name so the UI can say what is running.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Optional

# Progress state read by GET /items/progress. Kept a plain dict so the
# pipeline and ingestion can update it from worker threads too.
state: dict[str, Any] = {
    "status": "idle",  # idle | running | paused | aborted | error
    "message": "Ready",
    "progress": 0,
    "job": None,
    "started_at": None,
    "errors": 0,  # failed requests / sources in the current job
    "counters": {},  # discovered / enriched / stored ... for the sync log
}


def note_error(what: str) -> None:
    """Record a failed request or source; the run will be marked partial."""
    state["errors"] = int(state.get("errors", 0)) + 1
    msgs = state["counters"].setdefault("error_messages", [])
    if len(msgs) < 10:
        msgs.append(what[:200])
    print(f"  [warn] {what}", flush=True)


def count_source(name: str, returned: int, kept: int) -> None:
    """Per-source discovery counts for the sync log: how many came back, how many were in the window."""
    sources = state["counters"].setdefault("sources", {})
    cur = sources.get(name, [0, 0])
    sources[name] = [cur[0] + int(returned), cur[1] + int(kept)]


_pending_backfill_days = 0


def request_backfill(days: int) -> None:
    """A topic was created while a job was running: fetch its history once the slot is free."""
    global _pending_backfill_days
    _pending_backfill_days = max(_pending_backfill_days, int(days))


def take_backfill() -> int:
    global _pending_backfill_days
    days, _pending_backfill_days = _pending_backfill_days, 0
    return days


def count(key: str, value: int) -> None:
    state["counters"][key] = value

_lock = asyncio.Lock()


def is_busy() -> bool:
    """True while a job holds the slot, including one that is still winding down after an abort."""
    return _lock.locked() or state["status"] in ("running", "paused")


def is_stopping() -> bool:
    return _lock.locked() and state["status"] == "aborted"


async def wait_until_free(timeout: float = 180.0) -> bool:
    """Wait for an aborted job to finish unwinding. True once the slot is free."""
    waited = 0.0
    while _lock.locked() and waited < timeout:
        await asyncio.sleep(0.5)
        waited += 0.5
    return not _lock.locked()


def set_progress(progress: int, message: str) -> None:
    if state["status"] == "running":
        state["progress"] = int(progress)
        state["message"] = message


def aborted() -> bool:
    return state["status"] == "aborted"


async def wait_if_paused() -> bool:
    """Block while paused; False once the job was aborted."""
    while state["status"] == "paused":
        await asyncio.sleep(1.0)
    return state["status"] != "aborted"


async def run_exclusive(name: str, job: Callable[[], Awaitable[Any]]) -> Optional[Any]:
    """Run `job` unless another job is active. Returns the job's result, or None if refused."""
    if _lock.locked():
        return None
    async with _lock:
        state.update(status="running", message=f"Starting {name}...", progress=0, job=name, started_at=time.time(), errors=0, counters={})
        try:
            result = await job()
            if state["status"] == "aborted":
                state.update(status="idle", message="Aborted", progress=0)
            elif state["status"] != "error":
                errors = int(state.get("errors", 0))
                done_msg = "Sync Complete!" if not errors else f"Sync finished with {errors} failed request(s); the next run re-covers this period."
                state.update(status="idle", message=done_msg, progress=100)
            return result
        except Exception as e:  # keep the server alive, surface the error in the UI
            state.update(status="error", message=f"Error during {name}: {e}")
            print(f"Job {name} failed: {e!r}", flush=True)
            return None
        finally:
            state["job"] = None


def control(action: str) -> dict[str, Any]:
    if action == "pause" and state["status"] == "running":
        state.update(status="paused", message="Paused...")
    elif action == "resume" and state["status"] == "paused":
        state.update(status="running", message="Resuming...")
    elif action == "abort" and state["status"] in ("running", "paused"):
        state.update(status="aborted", message="Aborting...")
    return state
