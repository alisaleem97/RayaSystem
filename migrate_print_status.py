import sqlite3
import os

DB_PATH = "lab_database.db"

def migrate():
    print("Checking for 'is_printed' column in 'patientvisit' table...")
    
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if the column exists
        cursor.execute("PRAGMA table_info(patientvisit);")
        columns = [column[1] for column in cursor.fetchall()]

        if "is_printed" not in columns:
            print("Adding 'is_printed' column to 'patientvisit' table...")
            cursor.execute("ALTER TABLE patientvisit ADD COLUMN is_printed BOOLEAN DEFAULT 0 NOT NULL;")
            conn.commit()
            print("Migration successful: 'is_printed' column added.")
        else:
            print("Migration skipped: 'is_printed' column already exists (applied previously).")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
