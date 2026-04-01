import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expense'")
    exists = cursor.fetchone()
    
    if not exists:
        cursor.execute("""
            CREATE TABLE expense (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id INTEGER NOT NULL,
                expense_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                amount REAL DEFAULT 0.0,
                note TEXT,
                file_path TEXT,
                file_name TEXT,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                edited_by INTEGER,
                edited_at TIMESTAMP,
                FOREIGN KEY (type_id) REFERENCES expensetype(id),
                FOREIGN KEY (created_by) REFERENCES user(id),
                FOREIGN KEY (edited_by) REFERENCES user(id)
            )
        """)
        conn.commit()
        print("✅ Created expense table")
    else:
        print("ℹ️ expense table already exists")
    
    conn.close()

if __name__ == "__main__":
    migrate()
