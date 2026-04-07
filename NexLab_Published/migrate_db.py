import sqlite3

try:
    conn = sqlite3.connect('lab_system.db')
    cursor = conn.cursor()
    cursor.execute('ALTER TABLE "order" ADD COLUMN no_sample_reason VARCHAR;')
    conn.commit()
    print("Column added successfully.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Column already exists.")
    else:
        raise e
finally:
    conn.close()
