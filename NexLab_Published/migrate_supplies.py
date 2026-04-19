"""Migration script to create the supply table."""
import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Create supply table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS supply (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR NOT NULL,
        note VARCHAR,
        is_active BOOLEAN DEFAULT 1,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        edited_by INTEGER,
        edited_at TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES user(id),
        FOREIGN KEY (edited_by) REFERENCES user(id)
    )
    """)
    
    # Create index on name
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_supply_name ON supply (name)")
    
    conn.commit()
    conn.close()
    print("Created supply table (if not existed)")

if __name__ == "__main__":
    migrate()
