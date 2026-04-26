from sqlmodel import SQLModel
from database import engine
from models import CalControl

def migrate():
    print("Creating CalControl table if it doesn't exist...")
    SQLModel.metadata.create_all(engine)
    print("Migration successful.")

if __name__ == "__main__":
    migrate()
