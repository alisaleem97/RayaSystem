import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(patientvisit)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "tax_applied" not in columns:
        cursor.execute("ALTER TABLE patientvisit ADD COLUMN tax_applied BOOLEAN DEFAULT 1")
        conn.commit()
        print("Added tax_applied")
    
    if "tax_amount" not in columns:
        cursor.execute("ALTER TABLE patientvisit ADD COLUMN tax_amount REAL DEFAULT 0.0")
        conn.commit()
        print("Added tax_amount")

    conn.close()

if __name__ == "__main__":
    migrate()
