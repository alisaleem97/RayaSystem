"""
NexLab LIS — WAL Checkpoint Tool
=================================
Forces SQLite to flush all pending writes from the Write-Ahead Log (WAL)
into the main database file.

WHY THIS MATTERS:
  When SQLite uses WAL mode (which NexLab enables for performance),
  recent writes live in 'lab_database.db-wal' — NOT in the main .db file.
  If you copy or move only the .db file, you LOSE those recent writes.

  Running this script BEFORE backing up or moving the database ensures
  all data is safely inside the main .db file.

WHAT IT DOES:
  1. Connects to lab_database.db
  2. Runs PRAGMA wal_checkpoint(TRUNCATE) — flushes and removes the WAL
  3. The .db file now contains ALL data and is safe to copy/move

Usage:
  python tools/checkpoint_db.py
"""

import os
import sys
import sqlite3

def checkpoint_database(db_path="lab_database.db"):
    """
    Force a WAL checkpoint on the database, flushing all pending
    writes into the main .db file and truncating the WAL.
    
    Returns True on success, False on failure.
    """
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        return False

    try:
        conn = sqlite3.connect(db_path)
        
        # Check current journal mode
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        print(f"Current journal mode: {mode}")
        
        if mode.lower() != "wal":
            print("Database is not using WAL mode. No checkpoint needed.")
            conn.close()
            return True
        
        # Run checkpoint — TRUNCATE mode flushes WAL and then truncates it to zero bytes
        result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
        # result = (busy, log_pages, checkpointed_pages)
        busy, log_pages, checkpointed = result
        
        if busy == 0:
            print(f"Checkpoint successful: {checkpointed}/{log_pages} pages written to main database.")
        else:
            print(f"Warning: Checkpoint completed but database was busy. "
                  f"{checkpointed}/{log_pages} pages written.")
        
        conn.close()
        
        # Verify WAL file is gone or empty
        wal_path = db_path + "-wal"
        if os.path.exists(wal_path):
            wal_size = os.path.getsize(wal_path)
            if wal_size == 0:
                print("WAL file truncated to 0 bytes. Database is safe to copy.")
            else:
                print(f"Warning: WAL file still has {wal_size} bytes. "
                      f"Make sure the server is stopped and try again.")
                return False
        else:
            print("WAL file removed. Database is safe to copy.")
        
        return True
        
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            print("Error: Database is locked! Please stop the NexLab server first.")
            print("Close the 'start_nexlab.bat' window, then try again.")
        else:
            print(f"Error during checkpoint: {e}")
        return False
    except Exception as e:
        print(f"Error during checkpoint: {e}")
        return False


if __name__ == "__main__":
    print("==========================================")
    print("  NexLab WAL Checkpoint Tool")
    print("==========================================")
    print()
    
    success = checkpoint_database()
    
    if success:
        print("\nDatabase is ready — safe to backup or move.")
    else:
        print("\nCheckpoint failed. Do NOT move the database until this succeeds.")
        sys.exit(1)
