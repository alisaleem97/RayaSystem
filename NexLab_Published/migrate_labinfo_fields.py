import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(labinfo)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "welcome_message" not in columns:
        cursor.execute("ALTER TABLE labinfo ADD COLUMN welcome_message TEXT DEFAULT NULL")
        print("Added welcome_message column to labinfo table")
    else:
        print("welcome_message column already exists")
        
    if "province_id" not in columns:
        cursor.execute("ALTER TABLE labinfo ADD COLUMN province_id INTEGER DEFAULT NULL")
        print("Added province_id column to labinfo table")
    else:
        print("province_id column already exists")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
