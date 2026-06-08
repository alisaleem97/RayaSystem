# NexLab System Update Guide

This guide ensures you can update your NexLab Laboratory Information System (LIS) without losing any patient data or system settings.

## 🕒 Best Practices
- Always update when the lab is quiet (e.g., end of the day).
- Ensure no one is currently using the system before starting.
- Keep a backup of your `lab_database.db` file in a safe location.

> [!CAUTION]
> **NEVER delete the entire NexLab_Published folder during an update!**
> The database uses WAL mode, which stores recent writes in `lab_database.db-wal`.
> Deleting the folder destroys this file and causes **data loss** (patient results, status changes).

---

## 🚀 The Safe Way (Recommended — One Click)

### Prerequisites
1. Get the new `NexLab_Published` folder from the developer
2. **Stop the NexLab server** (close the `start_nexlab.bat` window)

### Steps
1. Copy the new `NexLab_Published` folder **next to** your existing one on the server
2. **Rename** the new folder to `NexLab_Update`
3. Place it **inside** your existing `NexLab_Published` folder
4. Double-click **`safe_update.bat`**
5. Follow the prompts — it will:
   - ✅ Flush all pending database writes (WAL checkpoint)
   - ✅ Create a timestamped backup
   - ✅ Copy only code files (your database, config, uploads are protected)
   - ✅ Install any new dependencies
   - ✅ Run database migrations
6. Once complete, run `start_nexlab.bat` to start the system
7. Delete the `NexLab_Update` folder (no longer needed)

### What is protected (NEVER overwritten):
| File/Folder | Contains |
|-------------|----------|
| `lab_database.db` | All patient data, results, orders |
| `lab_database.db-wal` | Recent uncommitted writes |
| `lab_database.db-shm` | Database shared memory |
| `.env` | Server secrets and configuration |
| `venv/` | Python virtual environment |
| `backups/` | Database backups |
| `uploads/` | Patient attachments and files |

---

## 🛠️ The Manual Way (Step-by-Step)

If you prefer to perform the update manually, follow these steps **exactly**:

### 1. Stop the Server
- Close the `start_nexlab.bat` window completely.

### 2. Checkpoint the Database
- Open a Command Prompt in the `NexLab_Published` folder.
- Run: `venv\Scripts\python.exe tools\checkpoint_db.py`
- This flushes all pending writes into the main database file.

### 3. Backup your Database
- Run: `venv\Scripts\python.exe tools\backup_db.py`
- A backup will be saved in the `backups/` folder.

### 4. Replace System Files
- **DO NOT delete the folder!**
- Delete the old files **EXCEPT** for:
  - `lab_database.db` (and `.db-wal`, `.db-shm`)
  - `.env`
  - `backups/` folder
  - `venv/` folder
  - `uploads/` folder
- Copy the new files from the update package into the folder.

### 5. Install Dependencies
- Run: `install_requirements.bat`

### 6. Run Database Migrations
- Run: `venv\Scripts\python.exe migrations\run_all.py`

### 7. Restart the Server
- Double-click `start_nexlab.bat` to bring the system back online.

---

## 🆘 Troubleshooting
- **Error: "Column already exists"**: This is normal if you have already run the migration before. The scripts are designed to skip columns that already exist.
- **Error: "Database is locked"**: Make sure you completely closed the `start_nexlab.bat` window. Wait a few seconds and try again.
- **System Won't Start**: Restore your backup by copying the latest file from `backups/` and renaming it to `lab_database.db`.
- **Patient data is missing after update**: You may have lost WAL data. Restore from the backup in the `backups/` folder.

> [!WARNING]
> DO NOT delete or overwrite `lab_database.db` during an update. This file contains all your data.
> Also protect `lab_database.db-wal` and `lab_database.db-shm` — they contain recent writes!
