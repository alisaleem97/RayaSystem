import sqlite3
import json

def set_perms():
    conn = sqlite3.connect('lab_database.db')
    cursor = conn.cursor()
    
    # Get admin ID
    cursor.execute("SELECT id FROM user WHERE username='admin'")
    row = cursor.fetchone()
    if not row:
        print("Admin user not found")
        return
    admin_id = row[0]
    
    # Add permissions for all financial and report pages
    pages = {
        'expenses_types': ["create", "edit", "delete"],
        'expenses_entry': ["create", "edit", "delete"],
        'detailed_income': ["view"],
    }
    for page, perms in pages.items():
        cursor.execute("INSERT OR REPLACE INTO userpermission (user_id, page_key, allowed_buttons) VALUES (?, ?, ?)", 
                       (admin_id, page, json.dumps(perms)))
    
    conn.commit()
    conn.close()
    print("✅ Successfully updated admin permissions for: " + ", ".join(pages.keys()))

if __name__ == "__main__":
    set_perms()
