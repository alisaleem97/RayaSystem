import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expensetype'")
    exists = cursor.fetchone()
    
    if not exists:
        cursor.execute("""
            CREATE TABLE expensetype (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type_name TEXT NOT NULL UNIQUE,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                edited_by INTEGER,
                edited_at TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES user(id),
                FOREIGN KEY (edited_by) REFERENCES user(id)
            )
        """)
        conn.commit()
        print("✅ Created expensetype table")
    else:
        print("ℹ️ expensetype table already exists")
    
    conn.close()

if __name__ == "__main__":
    migrate()
