"""Where Publicat keeps user data.

The database used to live inside the git checkout (backend/publikater.db).
It now lives in the platform's per-user data directory, so branch switches,
re-clones and `git clean` can never touch it:

    macOS    ~/Library/Application Support/Publicat/
    Windows  %APPDATA%\\Publicat\\
    Linux    $XDG_DATA_HOME/publicat/  (default ~/.local/share/publicat/)

Override with PUBLICAT_DATA_DIR, or point DATABASE_URL anywhere explicitly.
On first start the legacy file is copied (not moved) to the new location.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

APP_NAME = "Publicat"
DB_FILENAME = "publicat.db"
LEGACY_DB = Path(__file__).resolve().parents[1] / "publikater.db"


def data_dir() -> Path:
    override = os.environ.get("PUBLICAT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME.lower()


def database_path() -> Path:
    return data_dir() / DB_FILENAME


def migrate_legacy_database(target: Path | None = None, legacy: Path | None = None) -> bool:
    """Copy the in-repo database to the data directory once. Returns True if copied.

    Uses SQLite's online backup API so a database that is open with a WAL is
    copied consistently. The legacy file is left in place as a safety net.
    """
    target = target or database_path()
    legacy = legacy or LEGACY_DB
    if target.exists() or not legacy.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    print(f"Copied existing database to {target} (the old file at {legacy} was left untouched).", flush=True)
    return True


def default_database_url() -> str:
    """sqlite URL for the data-directory database, migrating the legacy file if needed."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    migrate_legacy_database(path)
    return f"sqlite:///{path}"
