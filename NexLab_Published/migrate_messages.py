import sqlite3
import os

DB_FILE = "lab_database.db"

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"Error: Database {DB_FILE} not found!")
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if User table exists
    cursor.execute("PRAGMA table_info(user)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if "last_seen" not in columns:
        print("Adding 'last_seen' to user table...")
        cursor.execute("ALTER TABLE user ADD COLUMN last_seen DATETIME")
        
    if "is_online" not in columns:
        print("Adding 'is_online' to user table...")
        cursor.execute("ALTER TABLE user ADD COLUMN is_online BOOLEAN DEFAULT 0")

    # The creation of the new tables will be handled by SQLModel's create_all
    # But just in case, we can trigger SQLModel create_db_and_tables directly here.
    conn.commit()
    conn.close()
    
    from database import create_db_and_tables
    print("Running sqlmodel create_db_and_tables...")
    create_db_and_tables()
    
    print("Messaging DB models successfully migrated!")

if __name__ == "__main__":
    migrate()
