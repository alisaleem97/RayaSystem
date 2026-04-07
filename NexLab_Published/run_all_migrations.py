import os
import subprocess
import glob

def run_migrations():
    # Find all migration files
    migration_files = glob.glob("migrate_*.py")
    migration_files.sort()  # Sort them to run in a consistent order
    
    if not migration_files:
        print("ℹ️ No migration files found.")
        return
    
    print(f"🚀 Found {len(migration_files)} migration files. Running them now...")
    
    for migration_file in migration_files:
        print(f"--- Running {migration_file} ---")
        try:
            # Use the current python interpreter
            result = subprocess.run(["python", migration_file], capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"❌ Error running {migration_file}:")
                print(result.stderr)
        except Exception as e:
            print(f"❌ System error running {migration_file}: {e}")
            
    print("✅ All migrations completed.")

if __name__ == "__main__":
    run_migrations()
