from sqlmodel import create_engine, SQLModel, Session

# SQLite database file
DATABASE_URL = "sqlite:///./lab_database.db"

# Create engine
engine = create_engine(DATABASE_URL, echo=False)

# Create all tables (runs once)
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Get database session
def get_session():
    with Session(engine) as session:
        yield session