import sqlite3

def migrate():
    # Connect to the main database
    conn = sqlite3.connect('lab_database.db')
    cursor = conn.cursor()
    
    print("Starting database migration for Double Authorisation...")
    
    try:
        cursor.execute("ALTER TABLE result ADD COLUMN double_authorized BOOLEAN DEFAULT 0")
        print("Added double_authorized to result")
    except sqlite3.OperationalError as e:
        print(f"double_authorized column might already exist: {e}")
        
    try:
        cursor.execute("ALTER TABLE result ADD COLUMN double_authorized_by INTEGER")
        print("Added double_authorized_by to result")
    except sqlite3.OperationalError as e:
        print(f"double_authorized_by column might already exist: {e}")

    try:
        cursor.execute("ALTER TABLE result ADD COLUMN double_authorized_at DATETIME")
        print("Added double_authorized_at to result")
    except sqlite3.OperationalError as e:
        print(f"double_authorized_at column might already exist: {e}")

    try:
        cursor.execute("ALTER TABLE result ADD COLUMN unauth_reason VARCHAR")
        print("Added unauth_reason to result")
    except sqlite3.OperationalError as e:
        print(f"unauth_reason column might already exist: {e}")

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
