from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from src.config import settings

engine = create_engine(
    settings.database_url, 
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0
    }
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Only apply pragmas for SQLite
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
