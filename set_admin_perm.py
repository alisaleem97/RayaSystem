import sqlite3
import json
import os

def set_perms():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_root, 'lab_database.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get admin ID
    cursor.execute("SELECT id FROM user WHERE username='admin'")
    row = cursor.fetchone()
    if not row:
        print("Admin user not found")
        return
    admin_id = row[0]
    
    # Complete list of all pages and their buttons
    pages = {
        'dashboard': [],
        'patient_registration': ["save_registration", "discount", "print_barcode", "print_receipt"],
        'patients': ["edit", "delete", "print_barcode", "result_entry"],
        'patient_edit': ["save", "print_barcode", "print_receipt", "discount"],
        'deleted_patients': ["restore", "view"],
        'deleted_tests': [],
        'patient_history': [],
        'patient_status': [],
        'result_entry': ["save", "authorize", "duplicate", "rerun", "no_sample"],
        'double_auth': ["double_authorize", "rerun", "unauthorize"],
        'no_sample': ["mark_no_sample", "receive_sample"],
        'print_barcode': ["print"],
        'barcode_designer': ["save"],
        'print_receipt': ["print"],
        'receipt_designer': ["save"],
        'print_results': ["print", "view"],
        'call_centre': ["mark_called", "send_whatsapp"],
        'result_designer': ["save"],
        'departments': ["create", "edit", "delete"],
        'sample_types': ["create", "edit", "delete"],
        'devices': ["create", "edit", "delete"],
        'parameters': ["create", "edit", "delete"],
        'report_notes': ["create", "edit", "delete"],
        'supplies': ["create", "edit", "delete"],
        'inventory': ["create", "edit", "delete"],
        'tests': ["create", "edit", "delete"],
        'formulas': ["create", "edit", "delete"],
        'test_ranges': ["create", "edit", "delete"],
        'test_result_types': ["create", "edit", "delete"],
        'packages': ["create", "edit", "delete"],
        'expenses_types': ["create", "edit", "delete"],
        'expenses_entry': ["create", "edit", "delete"],
        'discount_report': ["view"],
        'detailed_income': ["view"],
        'net_amounts': ["view"],
        'payment_records': ["view"],
        'patients_number': ["view"],
        'tests_number': ["view"],
        'expenses_report': ["view", "edit", "delete"],
        'remain_report': ["view"],
        'partners': ["create", "edit", "delete"],
        'provinces': ["create", "edit", "delete"],
        'regions': ["create", "edit", "delete"],
        'lab_info': ["edit", "save"],
        'user_management': ["create", "edit", "delete"],
        'activity_logs': ["view"],
    }
    
    # Delete existing admin permissions and re-insert all
    cursor.execute("DELETE FROM userpermission WHERE user_id = ?", (admin_id,))
    
    for page, perms in pages.items():
        cursor.execute("INSERT INTO userpermission (user_id, page_key, allowed_buttons) VALUES (?, ?, ?)", 
                       (admin_id, page, json.dumps(perms)))
    
    conn.commit()
    conn.close()
    print(f"Successfully updated admin permissions for {len(pages)} pages")

if __name__ == "__main__":
    set_perms()
