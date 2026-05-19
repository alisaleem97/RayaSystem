import os
import sys
import subprocess
import glob

def run_migrations():
    # Set console encoding to UTF-8 to support emojis on Windows
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # Determine directories
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migrations_dir = os.path.join(base_dir, "migrations")
    
    # Find all migration files
    search_pattern = os.path.join(migrations_dir, "migrate_*.py")
    migration_files = glob.glob(search_pattern)
    migration_files.sort()  # Sort them to run in a consistent order
    
    if not migration_files:
        print("ℹ️ No migration files found.")
        return
    
    print(f"🚀 Found {len(migration_files)} migration files. Running them now...")
    
    # Set PYTHONPATH so migration scripts can import root modules (database.py, models.py)
    env = os.environ.copy()
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{base_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = base_dir
        
    # Force UTF-8 encoding in subprocesses to handle emojis correctly on Windows
    env["PYTHONUTF8"] = "1"

    for migration_file in migration_files:
        filename = os.path.basename(migration_file)
        print(f"--- Running {filename} ---")
        try:
            # Use the current python interpreter
            result = subprocess.run([sys.executable, migration_file], capture_output=True, text=True, env=env, encoding="utf-8")
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"❌ Error running {filename}:")
                print(result.stderr)
        except Exception as e:
            print(f"❌ System error running {filename}: {e}")
            
    print("✅ All migrations completed.")

if __name__ == "__main__":
    run_migrations()
