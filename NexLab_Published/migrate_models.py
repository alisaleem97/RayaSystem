import os
from sqlmodel import SQLModel, create_engine
import models # Make sure models are imported so SQLModel knows about them

# Create sqlite engine pointing to lab_system database
sqlite_url = "sqlite:///./lab_database.db"
engine = create_engine(sqlite_url, echo=True)

if __name__ == "__main__":
    print("Creating new tables...")
    SQLModel.metadata.create_all(engine)
    print("Done!")
