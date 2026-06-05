import os
import sqlite3
from datetime import datetime

def backup_database():
    """
    Safe database backup using SQLite's built-in backup API.
    Unlike shutil.copy2, this handles active connections and WAL mode correctly,
    producing a consistent, non-corrupted backup every time.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_file = os.path.join(project_root, "lab_database.db")
    backup_dir = os.path.join(project_root, "backups")
    
    if not os.path.exists(db_file):
        print(f"❌ Error: Database file '{db_file}' not found.")
        return False
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"📁 Created backup directory: {backup_dir}")
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"lab_database_{timestamp}.db")
    
    try:
        # Connect to the live database
        source = sqlite3.connect(db_file)
        # Connect to the backup destination
        dest = sqlite3.connect(backup_file)
        
        # Use SQLite's built-in backup API — safe even during active writes
        source.backup(dest)
        
        dest.close()
        source.close()
        
        size_mb = os.path.getsize(backup_file) / (1024 * 1024)
        print(f"✅ Success: Database backed up to {backup_file} ({size_mb:.2f} MB)")
        
        # Cleanup: keep only last 30 backups
        cleanup_old_backups(backup_dir, keep=30)
        
        return True
    except Exception as e:
        print(f"❌ Error during backup: {e}")
        return False

def cleanup_old_backups(backup_dir, keep=30):
    """Remove old backups, keeping only the most recent 'keep' files."""
    try:
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith("lab_database_") and f.endswith(".db")],
            reverse=True
        )
        for old_backup in backups[keep:]:
            os.remove(os.path.join(backup_dir, old_backup))
            print(f"🗑️ Removed old backup: {old_backup}")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

if __name__ == "__main__":
    backup_database()
