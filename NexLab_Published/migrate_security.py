import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # We will add columns to the 'user' table
    columns_to_add = [
        ("failed_login_attempts", "INTEGER DEFAULT 0 NOT NULL"),
        ("locked_until", "DATETIME"),
        ("session_token", "VARCHAR")
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE user ADD COLUMN {col_name} {col_type};")
            print(f"Added {col_name} to user table.")
        except sqlite3.OperationalError as e:
            # Column likely already exists
            print(f"Could not add {col_name} (may already exist): {e}")
            
    # For any existing rows, give them a session token or initialization
    # actually session_token can be NULL and will be filled upon next login.
    # We can just update failed_login_attempts to 0 if it was null due to alter table.
    cursor.execute("UPDATE user SET failed_login_attempts = 0 WHERE failed_login_attempts IS NULL;")
    
    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
