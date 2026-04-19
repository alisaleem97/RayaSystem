"""Migration script to create the inventory table."""
import sqlite3

def migrate():
    conn = sqlite3.connect("lab_database.db")
    cursor = conn.cursor()
    
    # Create inventory table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        material_type VARCHAR NOT NULL,
        test_id INTEGER,
        supply_id INTEGER,
        quantity REAL DEFAULT 0.0,
        unit VARCHAR DEFAULT 'Test',
        expiration_date TIMESTAMP NOT NULL,
        note VARCHAR,
        is_active BOOLEAN DEFAULT 1,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        edited_by INTEGER,
        edited_at TIMESTAMP,
        FOREIGN KEY (test_id) REFERENCES testdefinition(id),
        FOREIGN KEY (supply_id) REFERENCES supply(id),
        FOREIGN KEY (created_by) REFERENCES user(id),
        FOREIGN KEY (edited_by) REFERENCES user(id)
    )
    """)
    
    # Create indices
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_inventory_material_type ON inventory (material_type)")
    
    conn.commit()
    conn.close()
    print("Created inventory table (if not existed)")

if __name__ == "__main__":
    migrate()
