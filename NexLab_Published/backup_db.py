import os
import shutil
from datetime import datetime

def backup_database():
    db_file = "lab_database.db"
    backup_dir = "backups"
    
    if not os.path.exists(db_file):
        print(f"❌ Error: Database file '{db_file}' not found.")
        return False
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"📁 Created backup directory: {backup_dir}")
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"lab_database_{timestamp}.db")
    
    try:
        shutil.copy2(db_file, backup_file)
        print(f"✅ Success: Database backed up to {backup_file}")
        return True
    except Exception as e:
        print(f"❌ Error during backup: {e}")
        return False

if __name__ == "__main__":
    backup_database()
