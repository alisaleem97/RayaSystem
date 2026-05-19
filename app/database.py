# app/database.py
# Database engine, session factory, and SQLite performance pragmas.
# Hardened for multi-user concurrent access (4+ PCs).

from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app.config import DATABASE_URL

# Create engine with StaticPool — optimal for SQLite with multi-threaded access.
# StaticPool uses a single connection that is reused across all threads,
# which is the safest strategy for SQLite + FastAPI (single worker).
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# Enable performance & concurrency PRAGMAs for every SQLite connection
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL mode: allows concurrent reads during writes (critical for multi-user)
    cursor.execute("PRAGMA journal_mode=WAL")
    # Busy timeout: wait up to 10 seconds instead of failing immediately on lock
    # Increased from 5s for multi-PC environments
    cursor.execute("PRAGMA busy_timeout=10000")
    # Synchronous NORMAL: safe with WAL, faster than FULL
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Cache size: ~32MB in memory for faster reads
    cursor.execute("PRAGMA cache_size=-32000")
    # Store temp tables in memory (faster joins and sorts)
    cursor.execute("PRAGMA temp_store=MEMORY")
    # Memory-mapped I/O: 256 MB for faster large reads
    cursor.execute("PRAGMA mmap_size=268435456")
    cursor.close()


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata. Runs once at startup."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Yield a database session for FastAPI dependency injection."""
    with Session(engine) as session:
        yield session
