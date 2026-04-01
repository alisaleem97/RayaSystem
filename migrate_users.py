"""Migration script to add user profile fields and userpermission table."""
import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Check and add new columns to user table
    cursor.execute("PRAGMA table_info(user)")
    columns = [col[1] for col in cursor.fetchall()]
    
    new_columns = [
        ("date_of_birth", "TEXT"),
        ("phone_number", "TEXT"),
        ("address", "TEXT"),
        ("edited_by", "INTEGER"),
        ("edited_at", "TEXT"),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}")
            print(f"  ✅ Added column user.{col_name}")
        else:
            print(f"  ℹ️ Column user.{col_name} already exists")
    
    # Create userpermission table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS userpermission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES user(id),
            page_key TEXT NOT NULL,
            allowed_buttons TEXT
        )
    """)
    print("  ✅ userpermission table created/verified")
    
    # Create index on user_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_userpermission_user_id ON userpermission(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_userpermission_page_key ON userpermission(page_key)")
    print("  ✅ Indexes created/verified")
    
    conn.commit()
    conn.close()
    print("\n✅ User management migration complete!")

if __name__ == "__main__":
    migrate()
