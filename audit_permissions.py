import os
import re

PAGES_REGISTRY = {
    # --- Main ---
    "dashboard": {"label": "Dashboard", "group": "Main", "buttons": []},
    # --- Patient Management ---
    "patient_registration": {"label": "Patient Registration", "group": "Patient Management", "buttons": [
        {"key": "save_registration", "label": "Save Registration"},
        {"key": "discount", "label": "Discount"},
        {"key": "print_barcode", "label": "Print Barcode"},
        {"key": "print_receipt", "label": "Print Receipt"},
    ]},
    "patients": {"label": "Patients", "group": "Patient Management", "buttons": [
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
        {"key": "print_barcode", "label": "Print Barcode"},
        {"key": "print_receipt", "label": "Print Receipt"},
        {"key": "result_entry", "label": "Result Entry"},
    ]},
    "patient_edit": {"label": "Patient Edit", "group": "Patient Management", "buttons": [
        {"key": "save", "label": "Save Changes"},
        {"key": "print_barcode", "label": "Print Barcode"},
        {"key": "print_receipt", "label": "Print Receipt"},
        {"key": "discount", "label": "Discount"},
    ]},
    "deleted_patients": {"label": "Deleted Patients", "group": "Patient Management", "buttons": [
        {"key": "restore", "label": "Restore"},
        {"key": "view", "label": "View"},
    ]},
    "deleted_tests": {"label": "Deleted Tests", "group": "Patient Management", "buttons": []},
    "patient_history": {"label": "Patient History", "group": "Patient Management", "buttons": []},
    "patient_status": {"label": "Patient Status", "group": "Patient Management", "buttons": []},
    # --- Results ---
    "result_entry": {"label": "Result Entry", "group": "Results", "buttons": [
        {"key": "save", "label": "Save Result"},
        {"key": "authorize", "label": "Authorize"},
        {"key": "duplicate", "label": "Duplicate"},
        {"key": "rerun", "label": "ReRun"},
        {"key": "no_sample", "label": "No Sample"},
    ]},
    "double_auth": {"label": "Double Authorisation", "group": "Results", "buttons": [
        {"key": "double_authorize", "label": "Double Authorize"},
        {"key": "rerun", "label": "ReRun"},
        {"key": "unauthorize", "label": "UnAUTH"},
    ]},
    "no_sample": {"label": "No Sample", "group": "Results", "buttons": [
        {"key": "mark_no_sample", "label": "Mark No Sample"},
        {"key": "receive_sample", "label": "Receive Sample"},
    ]},
    # --- Printing & Design ---
    "print_barcode": {"label": "Print Barcode", "group": "Printing & Design", "buttons": [
        {"key": "print", "label": "Print"},
    ]},
    "barcode_designer": {"label": "Barcode Designer", "group": "Printing & Design", "buttons": [
        {"key": "save", "label": "Save Design"},
    ]},
    "print_receipt": {"label": "Print Receipt", "group": "Printing & Design", "buttons": [
        {"key": "print", "label": "Print"},
    ]},
    "receipt_designer": {"label": "Receipt Designer", "group": "Printing & Design", "buttons": [
        {"key": "save", "label": "Save Design"},
    ]},
    "print_results": {"label": "Print Results", "group": "Printing & Design", "buttons": [
        {"key": "print", "label": "Print"},
        {"key": "view", "label": "View"},
    ]},
    "call_centre": {"label": "Call Centre", "group": "Printing & Design", "buttons": [
        {"key": "mark_called", "label": "Mark Called"},
        {"key": "send_whatsapp", "label": "Send WhatsApp"},
        {"key": "mark_printed", "label": "Mark Printed"},
    ]},
    "result_designer": {"label": "Result Designer", "group": "Printing & Design", "buttons": [
        {"key": "save", "label": "Save Design"},
    ]},
    # --- Lab Setup ---
    "departments": {"label": "Departments", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "sample_types": {"label": "Sample Types", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "inventory": {"label": "Inventory", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "supplies": {"label": "Supplies", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "devices": {"label": "Devices", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "parameters": {"label": "Parameters", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "report_notes": {"label": "Report Notes", "group": "Lab Setup", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Tests & Packages ---
    "tests": {"label": "Tests", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "formulas": {"label": "Formulas", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "cal_control": {"label": "Cal & Control", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
    ]},
    "test_ranges": {"label": "Test Ranges", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "test_result_types": {"label": "Result Types", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "packages": {"label": "Packages", "group": "Tests & Packages", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Financials ---
    "expenses_types": {"label": "Expenses Types", "group": "Financials", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "expenses_entry": {"label": "Expenses Entry", "group": "Financials", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Reports ---
    "discount_report": {"label": "Discount Report", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "detailed_income": {"label": "Detailed Income", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "net_amounts": {"label": "Net Amounts", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "payment_records": {"label": "Payment Records", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "patients_number": {"label": "Patients Number", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "tests_number": {"label": "Tests Number", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    "expenses_report": {"label": "Expenses Report", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
        {"key": "edit", "label": "Edit Expense"},
        {"key": "delete", "label": "Delete Expense"},
    ]},
    "remain_report": {"label": "Remain Report", "group": "Reports", "buttons": [
        {"key": "view", "label": "View Report"},
    ]},
    # --- Geography & Partners ---
    "partners": {"label": "Partners", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "provinces": {"label": "Provinces", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "regions": {"label": "Regions", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "patient_region": {"label": "Patient Region", "group": "Geography & Partners", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    # --- Settings ---
    "lab_info": {"label": "Lab Info", "group": "Settings", "buttons": [
        {"key": "edit", "label": "Edit"},
        {"key": "save", "label": "Save"},
    ]},
    "user_management": {"label": "User Management", "group": "Settings", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "hr": {"label": "Human Resources", "group": "Settings", "buttons": [
        {"key": "create", "label": "Create"},
        {"key": "edit", "label": "Edit"},
        {"key": "delete", "label": "Delete"},
    ]},
    "activity_logs": {"label": "Activity Logs", "group": "Settings", "buttons": [
        {"key": "view", "label": "View"},
    ]},
    "settings": {"label": "General Settings", "group": "Settings", "buttons": []},
}

def extract_from_templates(directory):
    pages = set()
    buttons = set()
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                    for match in re.finditer(r"has_page\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content):
                        pages.add(match.group(1))
                        
                    for match in re.finditer(r"has_button\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", content):
                        buttons.add((match.group(1), match.group(2)))
                        
    return pages, buttons

templates_pages, templates_buttons = extract_from_templates(r"c:\Users\aliss\Desktop\Raya System\templates")
registry_pages = set(PAGES_REGISTRY.keys())
registry_buttons = set()
for page, info in PAGES_REGISTRY.items():
    for btn in info.get("buttons", []):
        registry_buttons.add((page, btn["key"]))

missing_pages = templates_pages - registry_pages
missing_buttons = templates_buttons - registry_buttons

print(f"Missing Pages: {missing_pages}")
print(f"Missing Buttons: {missing_buttons}")

