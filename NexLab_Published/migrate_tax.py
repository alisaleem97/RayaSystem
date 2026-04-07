"""Migration script to add tax_percentage column to labinfo table."""
import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(labinfo)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "tax_percentage" not in columns:
        cursor.execute("ALTER TABLE labinfo ADD COLUMN tax_percentage REAL DEFAULT 0.0")
        conn.commit()
        print("✅ Added tax_percentage column to labinfo table")
    else:
        print("ℹ️ tax_percentage column already exists")
    
    conn.close()

if __name__ == "__main__":
    migrate()
