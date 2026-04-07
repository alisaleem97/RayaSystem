# NexLab System Update Guide

This guide ensures you can update your NexLab Laboratory Information System (LIS) without losing any patient data or system settings.

## 🕒 Best Practices
- Always update when the lab is quiet (e.g., end of the day).
- Ensure no one is currently using the system before starting.
- Keep a backup of your `lab_database.db` file in a safe location.

---

## 🚀 The Automatic Way (Recommended)
We have provided an automated tool to handle backups and database migrations for you.

1.  **Close the System**: Stop the server (close the window opened by `start_nexlab.bat`).
2.  **Run the Update Tool**: Double-click `update_system.bat`.
3.  **Follow the Prompts**:
    *   The tool will automatically create a backup in the `backups/` folder.
    *   It will ask you to confirm that you have replaced the system files with the new version.
    *   It will automatically run all database migrations (`migrate_*.py`).
4.  **Restart**: Once completed, run `start_nexlab.bat` as usual.

---

## 🛠️ The Manual Way (Step-by-Step)
If you prefer to perform the update manually, follow these steps exactly:

### 1. Backup your Database
- Go to your system folder (`lab_system`).
- Locate the file `lab_database.db`.
- Copy this file and paste it into a folder named `backups`. Rename it to something like `lab_database_backup_DATE.db`.

### 2. Replace System Files
- Delete the old files (except for `lab_database.db`, `backups/`, and `venv/`).
- Copy the new files from the update package into the `lab_system` folder.

### 3. Run Database Migrations
- If the new system version includes new database columns or features, you must run the migration scripts.
- Open a Command Prompt in the folder.
- Type: `venv\Scripts\python.exe run_all_migrations.py`
- Press Enter.

### 4. Restart the Server
- Double-click `start_nexlab.bat` to bring the system back online.

---

## 🆘 Troubleshooting
- **Error: "Column already exists"**: This is normal if you have already run the migration before. The scripts are designed to skip columns that already exist.
- **System Won't Start**: Check the `update_debug.log` if it exists, or restore your backup by renaming your latest backup file back to `lab_database.db`.

> [!WARNING]
> DO NOT delete or overwrite `lab_database.db` during an update. This file contains all your data.
