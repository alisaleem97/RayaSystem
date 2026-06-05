"""Migration script to add fasting_time column to patient table."""
import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(patient)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "fasting_time" not in columns:
        cursor.execute("ALTER TABLE patient ADD COLUMN fasting_time INTEGER DEFAULT NULL")
        conn.commit()
        print("✅ Added fasting_time column to patient table")
    else:
        print("ℹ️ fasting_time column already exists")
    
    conn.close()

if __name__ == "__main__":
    migrate()
