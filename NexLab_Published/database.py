from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import event

# SQLite database file
DATABASE_URL = "sqlite:///./lab_database.db"

# Create engine
engine = create_engine(DATABASE_URL, echo=False)

# Enable foreign key enforcement for SQLite (disabled by default)
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Create all tables (runs once)
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Get database session
def get_session():
    with Session(engine) as session:
        yield session